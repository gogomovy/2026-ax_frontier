"""선택 검색 엔진 — Elasticsearch (설계 §21.18).

기본은 PostgreSQL(pgvector + 전문 검색)이고, 이 모듈은 청크가 아주 많아지거나 한국어 형태소 분석(nori)이 필요할 때 **키워드 · 의미 채널만** Elasticsearch 로 옮기는 선택 경로다.
원칙(권한 누수 0 — NFR-KB-02)
- **원장은 PostgreSQL** 이다. ES 는 검색 색인일 뿐이고, ES 가 돌려준 후보는 **PostgreSQL 에서 접근 규칙으로 한 번 더 걸러** 본문 · 메타를 읽는다(ES 의 권한 필드가 늦거나 틀려도 새지 않는다).
- 사전 필터(collection · 리소스 · 지점)는 ES 질의에도 같은 규칙으로 건다(`es_filter` — SQL `kb_filter` 와 같은 결과를 내는지 시험으로 고정).
- 동기화는 워커 주기 작업이 한다(게시 트랜잭션에서 ES 를 부르지 않는다). 주기마다 PG ↔ ES 목록(id · 내용 해시 · 임베딩 모델)을 대조해 다른 것만 올리고 사라진 것은 지운다.
  아직 올리지 못한 새 청크(`id > synced_max_id`)는 검색이 PG 로 보충한다 — 게시 직후에도 검색에 잡힌다(KB-01).
- ES 가 꺼지면(연결 오류 · 5xx) 차단기가 열려 PG 채널로 자동 폴백한다(지수 대기 30초 → 300초).
그래프 채널과 문서(bank/ext) 청크는 PostgreSQL 에 그대로 둔다.
"""
from __future__ import annotations

import json
import logging
import math
import ssl
import threading
import time
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from nhdip.config import get_settings
from nhdip.models import Setting

from .access import AccessScope

log = logging.getLogger("nhdip.knowledge.es")
STATE_KEY = "knowledge.es_state"
BULK_BATCH = 500
KEYWORD_PHRASE = True  # 키워드 절을 구문 일치로(아래 keyword_hits). False 면 분해된 조각이 어디든 있으면 맞음(재현율↑ 정밀도↓)


class EsUnavailable(RuntimeError):
    """ES 에 닿지 못함(연결 · 시간 초과 · 5xx) — 호출자는 PostgreSQL 채널로 폴백한다."""


class EsError(EsUnavailable):
    """ES 가 요청을 거절(4xx) — 설정 · 매핑 문제. 폴백은 같지만 원인은 로그 · 상태에 남긴다."""

    def __init__(self, status: int, body: str):
        super().__init__(f"HTTP {status}: {body[:300]}")
        self.status, self.body = status, body


# ── 연결 · 차단기 ─────────────────────────────────────────────
_client: httpx.Client | None = None
_lock = threading.Lock()
_DOWN_UNTIL = 0.0
_FAILS = 0


def configured() -> bool:
    return bool(get_settings().es_url.strip())


def index_name() -> str:
    return get_settings().es_index


def client() -> httpx.Client:
    global _client
    with _lock:
        if _client is None:
            s = get_settings()
            verify: Any = s.es_verify_certs
            if s.es_ca_certs and s.es_verify_certs:
                verify = ssl.create_default_context(cafile=s.es_ca_certs)  # 사설 CA 만 추가로 믿는다
            _client = httpx.Client(
                base_url=s.es_url.rstrip("/"),
                auth=(s.es_user, s.es_password) if s.es_user else None,
                verify=verify,
                timeout=httpx.Timeout(connect=3.0, read=float(s.es_timeout_sec), write=15.0, pool=5.0),
                headers={"Accept": "application/json"},
            )
        return _client


def set_client(c: httpx.Client | None) -> None:
    """시험용 — 가짜 전송(MockTransport)이나 다른 주소의 클라이언트로 바꾼다."""
    global _client
    with _lock:
        _client = c


def es_up() -> bool:
    return time.monotonic() >= _DOWN_UNTIL


def mark_down() -> None:
    global _DOWN_UNTIL, _FAILS
    _FAILS += 1
    _DOWN_UNTIL = time.monotonic() + min(30.0 * (2 ** (_FAILS - 1)), 300.0)


def mark_ok() -> None:
    global _DOWN_UNTIL, _FAILS
    _DOWN_UNTIL, _FAILS = 0.0, 0


def reset_breaker() -> None:
    mark_ok()


def request(method: str, path: str, *, json_body: Any = None, content: str | None = None, ok: tuple[int, ...] = (200, 201), params: dict[str, Any] | None = None) -> Any:
    """ES REST 호출 — 연결 오류 · 5xx 는 EsUnavailable(+차단기), 4xx 는 EsError."""
    headers = {"Content-Type": "application/x-ndjson"} if content is not None else {}
    try:
        r = client().request(method, path, json=json_body, content=content, headers=headers, params=params)
    except (httpx.HTTPError, OSError) as exc:
        mark_down()
        raise EsUnavailable(f"{type(exc).__name__}: {exc}") from exc
    if r.status_code in ok:
        mark_ok()
        return r.json() if r.content and "json" in r.headers.get("content-type", "") else {}
    if r.status_code >= 500 or r.status_code == 429:
        mark_down()
        raise EsUnavailable(f"HTTP {r.status_code}: {r.text[:300]}")
    raise EsError(r.status_code, r.text)


# ── 접근 규칙 → ES 질의 (SQL kb_filter 와 같은 결과) ───────────
def es_filter(scope: AccessScope) -> dict[str, Any]:
    """분석 결과 청크 사전 필터의 ES 판. 컬렉션(전체 열람) 또는 (청크 단위 열람 컬렉션 ∧ 내 화면 리소스), 그리고 지점 범위."""
    res = sorted(scope.ctx.resources or [])
    should: list[dict[str, Any]] = [{"terms": {"collection_code": list(scope.full)}}]
    if scope.gated and res:
        should.append({"bool": {"filter": [{"terms": {"collection_code": list(scope.gated)}}, {"terms": {"required_resource": res}}]}})
    flt: list[dict[str, Any]] = [{"bool": {"should": should, "minimum_should_match": 1}}]
    scopes = scope.scope_keys()
    if scopes is not None:
        flt.append({"bool": {"should": [{"bool": {"must_not": [{"exists": {"field": "scope_key"}}]}}, {"terms": {"scope_key": scopes}}], "minimum_should_match": 1}})
    return {"bool": {"filter": flt}}


# ── 색인 정의 ─────────────────────────────────────────────────
def index_body(analyzer: str = "nori") -> dict[str, Any]:
    """키워드 필드는 한국어 분석기(nori — 조사 · 어미 제거, 합성어 분해). 플러그인이 없으면 standard 로 대신한다."""
    if analyzer == "nori":
        analysis: dict[str, Any] = {
            "tokenizer": {"ko_tokenizer": {"type": "nori_tokenizer", "decompound_mode": "mixed"}},
            "analyzer": {"ko": {"type": "custom", "tokenizer": "ko_tokenizer", "filter": ["nori_part_of_speech", "nori_readingform", "lowercase"]}},
        }
    else:
        analysis = {"analyzer": {"ko": {"type": "standard"}}}
    s = get_settings()
    return {
        "settings": {"index": {"number_of_shards": 1, "number_of_replicas": int(s.es_replicas), "refresh_interval": "1s"}, "analysis": analysis},
        "mappings": {
            "_source": {"excludes": ["title", "text", "embedding"]},  # 본문 · 제목 · 벡터는 PostgreSQL 이 원본이다 — ES 에는 검색용으로만(저장 공간 절약)
            "dynamic": "strict",
            "properties": {
                "v": {"type": "keyword", "index": False, "doc_values": False},
                "e": {"type": "keyword", "index": False, "doc_values": False},
                "collection_code": {"type": "keyword"},
                "source_key": {"type": "keyword"},
                "scope_key": {"type": "keyword"},
                "required_resource": {"type": "keyword"},
                "owner_org": {"type": "keyword"},
                "concepts": {"type": "keyword"},
                "embedding_model": {"type": "keyword"},
                "as_of": {"type": "date", "ignore_malformed": True},
                "title": {"type": "text", "analyzer": "ko"},
                "text": {"type": "text", "analyzer": "ko"},
            },
        },
    }


def ensure_index() -> str:
    """색인이 없으면 만든다 — 돌려주는 값은 쓰는 분석기('nori' | 'standard')."""
    idx = index_name()
    try:
        request("HEAD", f"/{idx}", ok=(200,))
        got = request("GET", f"/{idx}/_settings")
        tok = json.dumps(got)
        return "nori" if "nori_tokenizer" in tok else "standard"
    except EsError as exc:
        if exc.status != 404:
            raise
    for analyzer in ("nori", "standard"):
        try:
            request("PUT", f"/{idx}", json_body=index_body(analyzer))
            if analyzer == "standard":
                log.warning("ES nori 플러그인이 없어 standard 분석기로 색인을 만들었습니다 — 한국어 조사 · 합성어 처리가 약합니다(analysis-nori 설치 권장)")
            return analyzer
        except EsError as exc:
            if analyzer == "nori" and ("nori" in exc.body or "analysis-nori" in exc.body or "tokenizer" in exc.body):
                continue
            raise
    raise EsError(500, "색인을 만들지 못했습니다")


def ensure_vector_mapping(dims: int) -> int:
    """의미 검색용 dense_vector 필드 — 처음 임베딩이 올라올 때 차원으로 추가한다. 이미 다른 차원이면 그 차원을 돌려준다(차원이 바뀌면 `kb-es --rebuild`)."""
    idx = index_name()
    m = request("GET", f"/{idx}/_mapping")
    props = ((m.get(idx) or next(iter(m.values()), {})).get("mappings") or {}).get("properties") or {}
    cur = (props.get("embedding") or {}).get("dims")
    if cur:
        return int(cur)
    request("PUT", f"/{idx}/_mapping", json_body={"properties": {"embedding": {"type": "dense_vector", "dims": int(dims), "index": True, "similarity": "cosine"}}})
    return int(dims)


# ── 목록 대조 (순수 함수 + PG · ES 읽기) ───────────────────────
PG_MANIFEST = text(
    "SELECT id, md5(concat_ws('|', collection_code, coalesce(required_resource, ''), coalesce(scope_key, ''), coalesce(owner_org, ''), title, coalesce(section_path, ''), "
    "unit_hash, coalesce(as_of::text, ''), meta::text, concepts::text)) AS v, "
    "CASE WHEN embedding IS NULL THEN '' ELSE coalesce(embedding_model, '') END AS e FROM app.kb_chunk ORDER BY id"
)


def diff(pg: dict[int, tuple[str, str]], es: dict[int, tuple[str, str]]) -> tuple[list[int], list[int]]:
    """(올릴 id 오름차순, 지울 id) — 내용 해시나 임베딩 모델이 다르거나 ES 에 없는 것 / PG 에 없는 것."""
    upsert = sorted(i for i, ve in pg.items() if es.get(i) != ve)
    delete = sorted(i for i in es if i not in pg)
    return upsert, delete


def manifest_pg(session: Session) -> dict[int, tuple[str, str]]:
    return {int(i): (v, e) for i, v, e in session.execute(PG_MANIFEST.execution_options(stream_results=True))}


def manifest_es() -> dict[int, tuple[str, str]]:
    idx = index_name()
    out: dict[int, tuple[str, str]] = {}
    r = request("POST", f"/{idx}/_search", params={"scroll": "2m"}, json_body={"size": 5000, "_source": ["v", "e"], "sort": ["_doc"], "query": {"match_all": {}}})
    sid = r.get("_scroll_id")
    try:
        while True:
            hits = (r.get("hits") or {}).get("hits") or []
            if not hits:
                break
            for h in hits:
                src = h.get("_source") or {}
                out[int(h["_id"])] = (src.get("v", ""), src.get("e", ""))
            r = request("POST", "/_search/scroll", json_body={"scroll": "2m", "scroll_id": sid})
            sid = r.get("_scroll_id", sid)
    finally:
        if sid:
            try:
                request("DELETE", "/_search/scroll", json_body={"scroll_id": sid}, ok=(200, 404))
            except EsUnavailable:
                pass
    return out


def _bulk(lines: list[dict[str, Any]]) -> tuple[int, list[int]]:
    """NDJSON 일괄 요청 — (성공 건수, 실패한 id). 전부 실패면 예외."""
    if not lines:
        return 0, []
    body = "\n".join(json.dumps(x, ensure_ascii=False) for x in lines) + "\n"
    r = request("POST", "/_bulk", content=body, params={"refresh": "false"})
    bad: list[int] = []
    first = None
    items = r.get("items") or []
    for it in items:
        d = next(iter(it.values()))
        if d.get("status", 200) >= 300 and d.get("status") != 404:
            try:
                bad.append(int(d.get("_id")))
            except (TypeError, ValueError):
                pass
            first = first or json.dumps(d.get("error"), ensure_ascii=False)[:300]
    if first:
        log.warning("ES 일괄 처리 실패 %d/%d: %s", len(bad), len(items), first)
        if len(bad) >= len(items):
            raise EsError(400, first)
    return len(items) - len(bad), bad


def _docs_for(session: Session, ids: list[int], dims: int | None) -> tuple[list[dict[str, Any]], int | None]:
    rows = session.execute(
        text(
            "SELECT id, collection_code, source_key, scope_key, required_resource, owner_org, title, text, concepts, as_of, embedding_model, embedding::text AS emb, "
            "md5(concat_ws('|', collection_code, coalesce(required_resource, ''), coalesce(scope_key, ''), coalesce(owner_org, ''), title, coalesce(section_path, ''), unit_hash, coalesce(as_of::text, ''), meta::text, concepts::text)) AS v "
            "FROM app.kb_chunk WHERE id = ANY(CAST(:ids AS bigint[]))"
        ),
        {"ids": ids},
    ).mappings().all()
    lines: list[dict[str, Any]] = []
    idx = index_name()
    for r in rows:
        doc: dict[str, Any] = {
            "v": r["v"], "e": (r["embedding_model"] or "") if r["emb"] else "", "collection_code": r["collection_code"], "source_key": r["source_key"],
            "title": r["title"] or "", "text": (r["text"] or "")[:20000], "concepts": list(r["concepts"] or []),
        }
        for k in ("scope_key", "required_resource", "owner_org"):
            if r[k]:
                doc[k] = r[k]
        if r["as_of"]:
            doc["as_of"] = r["as_of"].isoformat()
        if r["emb"]:
            vec = json.loads(r["emb"])
            if dims is None:
                dims = ensure_vector_mapping(len(vec))
            if len(vec) == dims:
                doc["embedding"] = vec
                doc["embedding_model"] = r["embedding_model"]
        lines.append({"index": {"_index": idx, "_id": str(r["id"])}})
        lines.append(doc)
    return lines, dims


def _state(session: Session) -> dict[str, Any]:
    s = session.get(Setting, STATE_KEY)
    return dict(s.value) if s is not None and isinstance(s.value, dict) else {}


def _save_state(session: Session, **updates: Any) -> dict[str, Any]:
    st = {**_state(session), **updates}
    s = session.get(Setting, STATE_KEY)
    if s is None:
        session.add(Setting(key=STATE_KEY, value=st, description="질문하기 ES 동기화 내부 상태(올린 위치 · 마지막 점검) — 직접 고치지 않는다"))
    else:
        s.value = st
    session.flush()
    return st


def synced_max_id(session: Session) -> int | None:
    """이 id 이하의 청크는 ES 에 올라가 있다. 상태가 없으면 None(= ES 를 믿지 않는다)."""
    v = _state(session).get("synced_max_id")
    return int(v) if v is not None else None


def search_state(session: Session) -> dict[str, Any] | None:
    """검색이 ES 를 써도 되는 상태면 {'synced_max_id', 'dims'}, 아니면 None. 한 번도 동기화되지 않았으면 ES 를 믿지 않는다."""
    st = _state(session)
    if st.get("synced_max_id") is None:
        return None
    return {"synced_max_id": int(st["synced_max_id"]), "dims": int(st["dims"]) if st.get("dims") else None}


def sync(session: Session, *, limit: int = 2000, full_diff_min: float = 15.0, force: bool = False) -> dict[str, Any]:
    """PG → ES 동기화 한 번. limit 건까지 올리고(오름차순) 사라진 것은 모두 지운다. 호출자가 commit 한다."""
    if not configured():
        return {"skipped": "ES_URL 미설정"}
    if not es_up():
        return {"skipped": "ES 차단기 열림(잠시 뒤 재시도)"}
    t0 = time.monotonic()
    st = _state(session)
    try:
        analyzer = ensure_index()
        sig = session.execute(text("SELECT count(*), coalesce(max(id), 0), max(indexed_at)::text, count(embedding) FROM app.kb_chunk")).one()
        signature = [int(sig[0]), int(sig[1]), sig[2], int(sig[3])]
        last_full = st.get("last_full_at")
        due = force or not last_full or (time.time() - float(last_full)) > full_diff_min * 60
        if not due and st.get("signature") == signature and not st.get("pending"):
            return {"skipped": "변경 없음", "docs": st.get("docs")}
        pg = manifest_pg(session)
        es = manifest_es()
        upsert, delete = diff(pg, es)
        dims = None
        try:
            m = request("GET", f"/{index_name()}/_mapping")
            props = ((m.get(index_name()) or next(iter(m.values()), {})).get("mappings") or {}).get("properties") or {}
            dims = (props.get("embedding") or {}).get("dims")
        except EsError:
            pass
        done = 0
        failed_ids: list[int] = []
        batch_ids = upsert[:limit]
        for i in range(0, len(batch_ids), BULK_BATCH):
            lines, dims = _docs_for(session, batch_ids[i : i + BULK_BATCH], dims)
            ok, bad = _bulk(lines)
            done += ok
            failed_ids += bad
        removed = 0
        for i in range(0, len(delete), BULK_BATCH):
            ok, _ = _bulk([{"delete": {"_index": index_name(), "_id": str(x)}} for x in delete[i : i + BULK_BATCH]])
            removed += ok
        pending_ids = upsert[len(batch_ids) :]
        remaining = len(pending_ids) + len(failed_ids)
        if done or removed:
            request("POST", f"/{index_name()}/_refresh")
        # '동기화됨' = ES 에 아직 없는(새) 청크 중 가장 작은 id 바로 앞까지. 그 뒤의 새 청크는 검색이 PostgreSQL 로 보충한다.
        # 이미 ES 에 있고 내용만 달라 다시 올릴 청크(오래된 판)는 ES 에서 계속 검색되므로 여기 넣지 않는다(최대 한 주기 지난 판을 본다 — 본문은 PG 에서 읽으므로 화면에는 최신).
        missing_new = [i for i in (*pending_ids, *failed_ids) if i not in es]
        max_id = int(sig[1])
        synced = (min(missing_new) - 1) if missing_new else max_id
        out = {
            "indexed": done, "failed": len(failed_ids), "deleted": removed, "pending": remaining, "docs": len(pg) - len(missing_new), "analyzer": analyzer, "sec": round(time.monotonic() - t0, 1),
        }
        _save_state(
            session,
            signature=signature if not remaining else None, pending=remaining, synced_max_id=synced, synced_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            last_full_at=time.time(), docs=out["docs"], analyzer=analyzer, last_error=None, dims=dims,
        )
        return out
    except EsUnavailable as exc:
        _save_state(session, last_error=str(exc)[:300], last_error_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
        log.warning("ES 동기화 실패: %s", exc)
        return {"skipped": f"ES 오류 — {str(exc)[:160]}"}


def rebuild(session: Session) -> dict[str, Any]:
    """색인을 지우고 처음부터 다시 올린다(임베딩 차원이 바뀌었거나 분석기를 바꿀 때). 제한 없이 한 번에."""
    if not configured():
        return {"skipped": "ES_URL 미설정"}
    request("DELETE", f"/{index_name()}", ok=(200, 404))
    _save_state(session, signature=None, pending=0, synced_max_id=None, last_full_at=None, docs=0, dims=None)
    return sync(session, limit=10**9, force=True)


# ── 검색 ──────────────────────────────────────────────────────
def keyword_hits(scope: AccessScope, stems: list[str], total: int, *, size: int, min_ratio: float) -> list[tuple[int, float, int]]:
    """(청크 id, BM25 점수, 맞춘 어절 수) — 어절 중 `min_ratio` 비율 이상이 제목 · 본문에 나온 청크, 점수 높은 순. PG 키워드 채널의 최소 어절 수와 같은 기준.
    맞춘 어절 수는 어절마다 이름 붙인 절(`s0`, `s1` …)의 `matched_queries` 개수다 — nori 가 활용형을 풀어 맞춘 경우도 세어지므로 파이썬에서 부분 문자열로 다시 세지 않는다."""
    low = max(1, math.ceil(total * float(min_ratio) - 1e-9))
    if not stems or len(stems) < low:
        return []
    # 어절 하나 = 한 절. 구문(phrase) 일치 — nori 가 풀어 낸 조각(가계 · 자금 · 대출 · 금)이 문서 안에 흩어져 있어도 맞는 것으로 치지 않고, 이어서 나올 때만 맞춘다(PostgreSQL 접두 일치와 같은 정밀도).
    # 조사 · 어미는 분석기가 떼므로 '증가율과' 가 '증가율이' 에도 맞는다.
    mode = {"type": "phrase"} if KEYWORD_PHRASE else {"operator": "and"}
    should = [{"multi_match": {"query": s, "fields": ["title^2", "text"], **mode, "_name": f"s{i}"}} for i, s in enumerate(stems)]
    body = {"size": size, "_source": False, "track_total_hits": False, "query": {"bool": {"filter": [es_filter(scope)], "should": should, "minimum_should_match": low}}}
    r = request("POST", f"/{index_name()}/_search", json_body=body)
    return [(int(h["_id"]), float(h.get("_score") or 0.0), len(h.get("matched_queries") or [])) for h in (r.get("hits") or {}).get("hits") or []]


def vector_hits(scope: AccessScope, qvec: list[float], model: str, *, k: int) -> list[tuple[int, float]]:
    """(청크 id, 코사인 거리) — 가까운 순. ES 의 cosine 점수는 (1+cos)/2 이므로 거리 = 2 − 2×점수."""
    flt = {"bool": {"filter": [es_filter(scope), {"term": {"embedding_model": model}}]}}
    body = {"size": k, "_source": False, "knn": {"field": "embedding", "query_vector": qvec, "k": k, "num_candidates": max(100, k * 10), "filter": flt}}
    r = request("POST", f"/{index_name()}/_search", json_body=body)  # 매핑이 없거나 차원이 다르면 400(EsError) — 호출자가 PostgreSQL 로 폴백
    return [(int(h["_id"]), max(0.0, 2.0 - 2.0 * float(h.get("_score") or 0.0))) for h in (r.get("hits") or {}).get("hits") or []]


# ── 상태 ──────────────────────────────────────────────────────
def status(session: Session) -> dict[str, Any]:
    """관리자 상태 — 설정 여부 · 연결 · 문서 수 · 뒤처진 청크 수 · 분석기."""
    st = _state(session)
    out: dict[str, Any] = {"configured": configured(), "up": False, "index": index_name() if configured() else None, "state": {k: st.get(k) for k in ("synced_at", "docs", "pending", "analyzer", "last_error", "last_error_at", "dims")}}
    if not configured():
        return out
    try:
        h = request("GET", "/_cluster/health")
        out["up"] = True
        out["cluster"] = {"status": h.get("status"), "nodes": h.get("number_of_nodes")}
        try:
            out["es_docs"] = int(request("GET", f"/{index_name()}/_count").get("count", 0))
        except EsError:
            out["es_docs"] = None  # 색인 아직 없음
        pg = int(session.execute(text("SELECT count(*) FROM app.kb_chunk")).scalar() or 0)
        out["pg_chunks"] = pg
        out["lag"] = None if out.get("es_docs") is None else max(0, pg - int(out["es_docs"]))
    except EsUnavailable as exc:
        out["error"] = str(exc)[:200]
    return out
