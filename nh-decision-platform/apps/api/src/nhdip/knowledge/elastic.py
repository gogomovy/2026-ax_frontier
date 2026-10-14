"""검색 엔진 — Elasticsearch (설계 §21.18 · §24 3-way 구성).

3-way 구성: **PostgreSQL = 원장**(사실 · 문서 · 청크 · 임베딩 값 · 권한 · 감사) · **Elasticsearch = 키워드(BM25 + nori) · 의미(kNN) 검색**
· **Neo4j = 개념 그래프**. ES 에는 색인 두 개를 둔다.
  - 분석 결과 청크(`app.kb_chunk`) → `ES_INDEX`(기본 nhdip-kb-chunk), 문서 id = 청크 id
  - 문서 청크(`{bank,ext}.chunk`, **현재 버전 문서만**) → `ES_DOC_INDEX`(기본 nhdip-doc-chunk), 문서 id = '<출처>:<청크 id>'
원칙(권한 누수 0 — NFR-KB-02)
- **원장은 PostgreSQL** 이다. ES 는 검색 색인일 뿐이고, ES 가 돌려준 후보는 **PostgreSQL 에서 접근 규칙으로 한 번 더 걸러** 본문 · 메타를 읽는다(ES 의 권한 필드가 늦거나 틀려도 새지 않는다).
- 사전 필터는 ES 질의에도 같은 규칙으로 건다(분석 결과 `es_filter` ↔ SQL `kb_filter`, 문서 `doc_es_filter` ↔ SQL `doc_filter` — 같은 결과를 내는지 시험으로 고정).
- 동기화는 워커 주기 작업이 한다(게시 · 적재 트랜잭션에서 ES 를 부르지 않는다). 주기마다 PG ↔ ES 목록(id · 내용 해시 · 임베딩 모델)을 대조해 다른 것만 올리고 사라진 것은 지운다.
  아직 올리지 못한 새 청크(`id > synced_max_id`, 문서는 출처별)는 검색이 PG 로 보충한다 — 게시 · 적재 직후에도 검색에 잡힌다(KB-01).
- ES 가 꺼지면(연결 오류 · 5xx) 차단기가 열려 PG 채널로 자동 폴백한다(지수 대기 30초 → 300초).
- 색인 정의(매핑 판 · nori 사용자 사전 = 온톨로지 별칭 사전)가 바뀌면 동기화가 색인을 다시 만든다(원장이 PG 라 언제든 다시 올릴 수 있다).
그래프 채널은 PostgreSQL(개념 태그 · 데이터셋 매핑 간선) + Neo4j(문서 ↔ 개념, 개념 이웃)다.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import ssl
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from nhdip.config import get_settings
from nhdip.models import Setting

from .access import AccessScope, setting_dict
from .defaults import SEARCH_DEFAULT

log = logging.getLogger("nhdip.knowledge.es")
STATE_KEY = "knowledge.es_state"
DOC_STATE_KEY = "knowledge.es_doc_state"
BULK_BATCH = 500
KEYWORD_PHRASE = True  # 키워드 절을 구문 일치로(아래 keyword_hits). False 면 분해된 조각이 어디든 있으면 맞음(재현율↑ 정밀도↓)
KB_MAPPING_VERSION = 2  # 2: 매핑 판 표시(_meta) · nori 사용자 사전(온톨로지 별칭)
DOC_MAPPING_VERSION = 1
ORIGINS = ("bank", "ext")
BACKENDS = ("auto", "es", "pg")


class EsUnavailable(RuntimeError):
    """ES 에 닿지 못함(연결 · 시간 초과 · 5xx) — 호출자는 PostgreSQL 채널로 폴백한다."""


class EsError(EsUnavailable):
    """ES 가 요청을 거절(4xx) — 설정 · 매핑 문제. 폴백은 같지만 원인은 로그 · 상태에 남긴다."""

    def __init__(self, status: int, body: str):
        super().__init__(f"HTTP {status}: {body[:300]}")
        self.status, self.body = status, body


AUTH_MESSAGE = {
    401: "Elasticsearch 인증 실패 — 계정(ES_USER) 또는 비밀번호(ES_PASSWORD)가 Elasticsearch 에 저장된 값과 다릅니다",
    403: "Elasticsearch 권한 부족 — 계정에 색인 · 클러스터 조회 권한이 없습니다",
}
AUTH_REMEDY = [
    "내장 Elasticsearch: 서버에서 `make es-password` — ES 볼륨의 elastic 비밀번호를 .env 의 ES_PASSWORD 로 맞추고 api · worker 를 다시 띄웁니다(데이터 유지)",
    "비밀번호를 알고 있거나 외부 Elasticsearch 를 쓰면: 이 화면 [연결 설정]에서 주소 · 계정 · 비밀번호를 입력하고 [연결 시험] 후 저장",
    ".env 를 고친 뒤에는 컨테이너를 다시 만들어야 반영됩니다: docker compose up -d api worker (restart 로는 환경변수가 바뀌지 않음)",
]


class EsAuthError(EsError):
    """ES 가 인증 · 권한을 거절(401 · 403) — 저절로 낫지 않으므로 차단기를 걸고 조치 안내를 남긴다 (Phase K · ES-01 · Q154)."""

    def __init__(self, status: int, body: str):
        super().__init__(status, body)
        self.args = (f"{AUTH_MESSAGE.get(status, AUTH_MESSAGE[401])} (HTTP {status})",)


# ── 연결 · 차단기 ─────────────────────────────────────────────
_client: httpx.Client | None = None
_lock = threading.Lock()
_DOWN_UNTIL = 0.0
_FAILS = 0

# 관리자 입력 연결 값 (Phase K · ES-03) — cfg.secret['es.connection'] 이 있으면 환경변수보다 먼저. 프로세스(api · worker)마다 30초 캐시
SECRET_KEY = "es.connection"
OVERRIDE_TTL = 30.0
_OVERRIDE: dict[str, str] | None = None
_OVERRIDE_AT = -1e9


def _read_override() -> dict[str, str] | None:
    from nhdip.db import SessionLocal
    from nhdip.models import Secret
    from nhdip.security import decrypt_secret

    with SessionLocal() as s:
        row = s.get(Secret, SECRET_KEY)
        if row is None:
            return None
        meta = row.meta if isinstance(row.meta, dict) else {}
        url = str(meta.get("url") or "").strip()
        if not url:
            return None
        return {"url": url, "user": str(meta.get("user") or ""), "password": decrypt_secret(row.secret_enc)}


def _override() -> dict[str, str] | None:
    global _OVERRIDE, _OVERRIDE_AT, _client
    now = time.monotonic()
    if now - _OVERRIDE_AT < OVERRIDE_TTL:
        return _OVERRIDE
    _OVERRIDE_AT = now
    try:
        new = _read_override()
    except Exception:  # noqa: BLE001 — DB 가 잠시 안 되면 직전 값 유지(검색은 계속)
        return _OVERRIDE
    if new != _OVERRIDE:
        with _lock:
            _client = None
        mark_ok()
    _OVERRIDE = new
    return new


def invalidate_override() -> None:
    """관리자가 연결 값을 바꾼 뒤 — 이 프로세스는 바로, 다른 프로세스(worker)는 30초 안에 새 값으로 다시 연결한다."""
    global _OVERRIDE_AT, _client
    _OVERRIDE_AT = -1e9
    with _lock:
        _client = None
    mark_ok()


def connection() -> dict[str, Any]:
    """지금 쓰는 연결 값 — {url, user, password, source: db|env}."""
    o = _override()
    if o:
        return {**o, "source": "db"}
    s = get_settings()
    return {"url": s.es_url.strip(), "user": s.es_user, "password": s.es_password, "source": "env"}


def configured() -> bool:
    return bool(connection()["url"])


def index_name() -> str:
    return get_settings().es_index


def doc_index_name() -> str:
    return get_settings().es_doc_index


def client() -> httpx.Client:
    global _client
    conn = connection()
    with _lock:
        if _client is None:
            _client = make_client(conn["url"], conn["user"], conn["password"])
        return _client


def make_client(url: str, user: str, password: str, *, read_timeout: float | None = None) -> httpx.Client:
    """ES HTTP 클라이언트 — 인증서 검증 · 사설 CA 는 환경변수(ES_VERIFY_CERTS · ES_CA_CERTS)."""
    s = get_settings()
    verify: Any = s.es_verify_certs
    if s.es_ca_certs and s.es_verify_certs:
        verify = ssl.create_default_context(cafile=s.es_ca_certs)  # 사설 CA 만 추가로 믿는다
    return httpx.Client(
        base_url=url.rstrip("/"),
        auth=(user, password) if user else None,
        verify=verify,
        timeout=httpx.Timeout(connect=3.0, read=float(read_timeout or s.es_timeout_sec), write=15.0, pool=5.0),
        headers={"Accept": "application/json"},
    )


def probe(url: str, user: str, password: str) -> dict[str, Any]:
    """저장 없이 연결 시험 (관리자 [연결 설정]) — {ok, errorKind, message, cluster}."""
    try:
        with make_client(url, user, password, read_timeout=8.0) as c:
            r = c.get("/_cluster/health")
    except (httpx.HTTPError, OSError) as exc:
        return {"ok": False, "errorKind": "down", "message": f"연결할 수 없습니다 — {type(exc).__name__}: {str(exc)[:160]}"}
    if r.status_code in (401, 403):
        return {"ok": False, "errorKind": "auth", "message": AUTH_MESSAGE[r.status_code]}
    if r.status_code != 200:
        return {"ok": False, "errorKind": "rejected", "message": f"HTTP {r.status_code}: {r.text[:160]}"}
    h = r.json() if "json" in r.headers.get("content-type", "") else {}
    return {"ok": True, "errorKind": None, "message": "연결됨", "cluster": {"status": h.get("status"), "nodes": h.get("number_of_nodes")}}


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
    if r.status_code in (401, 403):
        # 인증 · 권한 거절은 다시 불러도 같다 — 차단기로 호출을 줄이고(검색은 PostgreSQL 폴백) 조치를 안내한다
        mark_down()
        log.warning("Elasticsearch 인증 실패 HTTP %s (%s %s)", r.status_code, method, path)
        raise EsAuthError(r.status_code, r.text)
    raise EsError(r.status_code, r.text)


# ── 검색 엔진 선택 (3-way) ────────────────────────────────────
def backend_mode(session: Session) -> str:
    """검색 설정 knowledge.search.backend — 'auto'(기본: ES 가 설정 · 동기화돼 있으면 ES, 아니면 PG) · 'es'(ES 를 쓰기로 함 — 안 되면 경고 + PG) · 'pg'(PG 만)."""
    v = str(setting_dict(session, "knowledge.search", SEARCH_DEFAULT).get("backend", "auto")).strip().lower()
    return v if v in BACKENDS else "auto"


def readiness(session: Session, which: str, mode: str) -> tuple[dict[str, Any] | None, str | None]:
    """(검색 상태, 못 쓰는 이유). which = 'kb'(분석 결과) | 'doc'(문서).
    상태가 None 이고 이유도 None 이면 'ES 를 쓰지 않는 구성'(pg · 또는 auto 인데 ES_URL 없음)이라 조용히 PostgreSQL."""
    if mode == "pg":
        return None, None
    if not configured():
        return None, ("ES_URL 미설정" if mode == "es" else None)
    if not es_up():
        return None, "ES 연결 대기(차단기 열림)"
    st = search_state(session) if which == "kb" else doc_search_state(session)
    if st is None:
        return None, "ES 아직 동기화 전"
    return st, None


# ── 접근 규칙 → ES 질의 (SQL kb_filter · doc_filter 와 같은 결과) ───────────
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


NOTHING: dict[str, Any] = {"bool": {"filter": [{"match_none": {}}]}}


def doc_es_filter(scope: AccessScope) -> dict[str, Any]:
    """문서 청크 사전 필터의 ES 판(SQL `doc_filter` 와 같은 규칙) — 열람 가능한 문서 분류 + 부서한정 문서는 내 부서 문서만.
    현재 버전 조건은 색인 자체가 현재 버전만 담는 것으로 대신한다(이전 판 청크는 동기화가 지우고, 그 사이는 PG 재확인이 거른다)."""
    flt: list[dict[str, Any]] = []
    if scope.doc_classes is not None:
        if not scope.doc_classes:
            return NOTHING
        flt.append({"terms": {"doc_class": sorted(scope.doc_classes)}})
    dept = scope.ctx.dept_docs
    if dept is not None:
        flt.append({"bool": {"should": [{"bool": {"must_not": [{"term": {"access_class": "dept_only"}}]}}, {"terms": {"doc_code": sorted(dept)}}], "minimum_should_match": 1}})
    return {"bool": {"filter": flt}}


def doc_es_filter_for(origins: tuple[str, ...] | list[str], doc_ids: dict[str, list[int]] | None, doc_classes: list[str] | None) -> dict[str, Any]:
    """워크플로 근거 검색(시스템 실행)용 — 출처 · 문서 분류 · 개념 경로 문서(Neo4j 가 고른 문서 id) 조건. graph.search.hybrid_search 의 SQL 과 같은 규칙."""
    flt: list[dict[str, Any]] = [{"terms": {"origin": list(origins)}}]
    if doc_classes:
        flt.append({"terms": {"doc_class": sorted(doc_classes)}})
    if doc_ids is not None:
        should = [{"bool": {"filter": [{"term": {"origin": o}}, {"terms": {"document_id": sorted(int(i) for i in ids)}}]}} for o, ids in sorted(doc_ids.items()) if o in origins and ids]
        if not should:
            return NOTHING
        flt.append({"bool": {"should": should, "minimum_should_match": 1}})
    return {"bool": {"filter": flt}}


def doc_es_id(origin: str, chunk_id: int) -> str:
    return f"{origin}:{int(chunk_id)}"


def parse_doc_id(v: Any) -> tuple[str, int]:
    o, _, n = str(v).partition(":")
    if o not in ORIGINS or not n.isdigit():
        raise ValueError(f"문서 청크 id 형식이 아님: {v!r}")
    return o, int(n)


# ── 색인 정의 ─────────────────────────────────────────────────
HANGUL_WORD = re.compile(r"^[가-힣]{2,30}$")
# 별칭이 이 낱말로 끝나면 앞부분과 나눠 등록한다 — '새희망홀씨대출' = 새희망홀씨 + 대출 (질문 '대출' · '새희망홀씨' 모두 맞게)
DICT_SUFFIXES = ("증가율", "성장률", "대출", "모형", "한도", "배분", "관리", "확대", "금융", "여신", "부채", "기업", "상품", "자금", "비율", "제약")
_DICT_CACHE: dict[str, list[str]] = {}


def _analysis(analyzer: str, rules: list[str] | None = None) -> dict[str, Any]:
    if analyzer == "nori":
        tok: dict[str, Any] = {"type": "nori_tokenizer", "decompound_mode": "mixed"}
        if rules:
            tok["user_dictionary_rules"] = list(rules)
        return {
            "tokenizer": {"ko_tokenizer": tok},
            "analyzer": {"ko": {"type": "custom", "tokenizer": "ko_tokenizer", "filter": ["nori_part_of_speech", "nori_readingform", "lowercase"]}},
        }
    return {"analyzer": {"ko": {"type": "standard"}}}


def _settings_body(analyzer: str, rules: list[str] | None) -> dict[str, Any]:
    s = get_settings()
    return {"index": {"number_of_shards": 1, "number_of_replicas": int(s.es_replicas), "refresh_interval": "1s"}, "analysis": _analysis(analyzer, rules)}


def index_body(analyzer: str = "nori", rules: list[str] | None = None, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """분석 결과 색인. 키워드 필드는 한국어 분석기(nori — 조사 · 어미 제거, 합성어 분해 + 온톨로지 별칭 사용자 사전). 플러그인이 없으면 standard 로 대신한다."""
    mappings: dict[str, Any] = {
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
    }
    if meta:
        mappings["_meta"] = {"nhdip": meta}
    return {"settings": _settings_body(analyzer, rules), "mappings": mappings}


def doc_index_body(analyzer: str = "nori", rules: list[str] | None = None, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """문서 청크 색인 — 권한 · 분류 필드(SQL doc_filter 와 같은 조건) + 제목 · 절 경로 · 본문(한국어 분석기). 본문 · 벡터 원본은 PostgreSQL."""
    mappings: dict[str, Any] = {
        "_source": {"excludes": ["title", "section", "text", "embedding"]},
        "dynamic": "strict",
        "properties": {
            "v": {"type": "keyword", "index": False, "doc_values": False},
            "e": {"type": "keyword", "index": False, "doc_values": False},
            "origin": {"type": "keyword"},
            "document_id": {"type": "integer"},
            "doc_code": {"type": "keyword"},
            "doc_class": {"type": "keyword"},
            "access_class": {"type": "keyword"},
            "page": {"type": "integer"},
            "published": {"type": "date", "ignore_malformed": True},
            "embedding_model": {"type": "keyword"},
            "title": {"type": "text", "analyzer": "ko"},
            "section": {"type": "text", "analyzer": "ko"},
            "text": {"type": "text", "analyzer": "ko"},
        },
    }
    if meta:
        mappings["_meta"] = {"nhdip": meta}
    return {"settings": _settings_body(analyzer, rules), "mappings": mappings}


def _segment(word: str, vocab: set[str]) -> list[str] | None:
    """사용자 사전 분해 — 사전의 더 짧은 낱말로 시작하면 그 낱말 + 나머지, 아니면 흔한 끝말(대출 · 모형 …) 앞뒤로. 없으면 None."""
    pre = max((p for p in vocab if p != word and word.startswith(p) and len(word) > len(p)), key=len, default=None)
    if pre:
        return [pre, word[len(pre) :]]
    for suf in DICT_SUFFIXES:
        if word.endswith(suf) and len(word) - len(suf) >= 2:
            return [word[: -len(suf)], suf]
    return None


def _drops_chars(word: str) -> bool:
    """기본 nori 가 이 낱말의 글자를 버리는지(관형사 '새' · 접미사 '론' 처럼 품사 필터에 걸려) — 버리면 사용자 사전에 넣는다."""
    try:
        r = request("POST", "/_analyze", json_body={"tokenizer": {"type": "nori_tokenizer", "decompound_mode": "mixed"}, "filter": ["nori_part_of_speech"], "text": word})
    except EsUnavailable:
        return False
    got = "".join(t.get("token", "") for t in r.get("tokens") or [])
    return any(ch not in got for ch in word)


def user_dictionary(session: Session) -> list[str]:
    """nori 사용자 사전 = 활성 온톨로지 별칭 사전(마스터 키 + 별칭) 중 한글 낱말.
    - 더 짧은 사전 낱말 · 흔한 끝말로 나눌 수 있으면 '낱말 앞 뒤' 로(합성어 + 조각을 함께 색인 → 부분 질문도 맞음)
    - 나눌 수 없으면 기본 분석이 글자를 버리는 낱말만 통째로(버리지 않는 낱말은 기본 분해가 더 낫다)
    같은 사전이면 다시 묻지 않는다(프로세스 안 보관)."""
    from nhdip.graph.projection import active_schema

    schema = active_schema(session)
    vocab: set[str] = set()
    for entries in ((schema.aliases or {}) if schema is not None else {}).values():
        for key, aliases in (entries or {}).items():
            for a in [key, *(aliases or [])]:
                a = str(a).strip()
                if HANGUL_WORD.match(a):
                    vocab.add(a)
    sig = hashlib.sha1("\n".join(sorted(vocab)).encode("utf-8")).hexdigest()
    if sig in _DICT_CACHE:
        return _DICT_CACHE[sig]
    rules: list[str] = []
    for w in sorted(vocab):
        seg = _segment(w, vocab)
        if seg:
            rules.append(" ".join([w, *seg]))
        elif _drops_chars(w):
            rules.append(w)
    _DICT_CACHE.clear()
    _DICT_CACHE[sig] = rules
    return rules


def dict_signature(rules: list[str] | None) -> str:
    return hashlib.sha1("\n".join(rules or []).encode("utf-8")).hexdigest()[:12]


def _create(idx: str, body_fn: Callable[[str, list[str] | None], dict[str, Any]], rules: list[str] | None) -> str:
    """색인을 만든다 — nori(+사용자 사전) → nori(사전 없이) → standard 순. 돌려주는 값은 쓰는 분석기."""
    attempts: list[tuple[str, list[str] | None]] = [("nori", rules)] if rules else []
    attempts += [("nori", None), ("standard", None)]
    last: EsError | None = None
    for analyzer, r in attempts:
        try:
            request("PUT", f"/{idx}", json_body=body_fn(analyzer, r))
            if analyzer == "standard":
                log.warning("ES nori 플러그인이 없어 standard 분석기로 색인을 만들었습니다 — 한국어 조사 · 합성어 처리가 약합니다(analysis-nori 설치 권장)")
            elif rules and r is None:
                log.warning("ES nori 사용자 사전(온톨로지 별칭)을 받아들이지 않아 사전 없이 색인을 만들었습니다: %s", (last.body if last else "")[:200])
            return analyzer
        except EsError as exc:
            last = exc
            if analyzer == "nori" and r is not None:
                continue  # 사전 문제 — 사전 없이 다시
            if analyzer == "nori" and ("nori" in exc.body or "analysis-nori" in exc.body or "tokenizer" in exc.body):
                continue
            raise
    raise EsError(500, "색인을 만들지 못했습니다")


def _ensure(idx: str, body_fn: Callable[[str, list[str] | None], dict[str, Any]], rules: list[str] | None = None, meta: dict[str, Any] | None = None) -> tuple[str, bool]:
    """색인이 없으면 만들고, `meta`(매핑 판 · 사전 서명)가 다르면 지우고 다시 만든다 — (분석기, 새로 만들었는지).
    원장이 PostgreSQL 이라 다시 만들어도 잃는 것이 없다(그동안 검색은 PG 로 보충 · 폴백)."""
    try:
        request("HEAD", f"/{idx}", ok=(200,))
        exists = True
    except EsError as exc:
        if exc.status != 404:
            raise
        exists = False
    if exists:
        if meta is not None:
            m = request("GET", f"/{idx}/_mapping")
            cur = (((m.get(idx) or next(iter(m.values()), {})).get("mappings") or {}).get("_meta") or {}).get("nhdip")
            if cur != meta:
                log.warning("ES 색인 %s 정의가 바뀌어(%s → %s) 다시 만듭니다", idx, cur, meta)
                request("DELETE", f"/{idx}", ok=(200, 404))
                return _create(idx, body_fn, rules), True
        got = request("GET", f"/{idx}/_settings")
        return ("nori" if "nori_tokenizer" in json.dumps(got) else "standard"), False
    return _create(idx, body_fn, rules), True


def ensure_index() -> str:
    """분석 결과 색인이 없으면 만든다(사전 · 판 확인 없이) — 돌려주는 값은 쓰는 분석기('nori' | 'standard')."""
    return _ensure(index_name(), lambda a, r: index_body(a, r))[0]


def ensure_vector_mapping(dims: int, idx: str | None = None) -> int:
    """의미 검색용 dense_vector 필드 — 처음 임베딩이 올라올 때 차원으로 추가한다. 이미 다른 차원이면 그 차원을 돌려준다(차원이 바뀌면 `kb-es --rebuild`)."""
    idx = idx or index_name()
    m = request("GET", f"/{idx}/_mapping")
    props = ((m.get(idx) or next(iter(m.values()), {})).get("mappings") or {}).get("properties") or {}
    cur = (props.get("embedding") or {}).get("dims")
    if cur:
        return int(cur)
    request("PUT", f"/{idx}/_mapping", json_body={"properties": {"embedding": {"type": "dense_vector", "dims": int(dims), "index": True, "similarity": "cosine"}}})
    return int(dims)


def _mapped_dims(idx: str) -> int | None:
    try:
        m = request("GET", f"/{idx}/_mapping")
    except EsError:
        return None
    props = ((m.get(idx) or next(iter(m.values()), {})).get("mappings") or {}).get("properties") or {}
    d = (props.get("embedding") or {}).get("dims")
    return int(d) if d else None


# ── 목록 대조 (순수 함수 + PG · ES 읽기) ───────────────────────
PG_MANIFEST = text(
    "SELECT id, md5(concat_ws('|', collection_code, coalesce(required_resource, ''), coalesce(scope_key, ''), coalesce(owner_org, ''), title, coalesce(section_path, ''), "
    "unit_hash, coalesce(as_of::text, ''), meta::text, concepts::text)) AS v, "
    "CASE WHEN embedding IS NULL THEN '' ELSE coalesce(embedding_model, '') END AS e FROM app.kb_chunk ORDER BY id"
)
# 문서 청크 내용 해시 — 권한(부서한정) · 분류 · 문서 코드 · 제목 · 위치 · 본문 · 시행일이 바뀌면 다시 올린다
DOC_V = (
    "md5(concat_ws('|', d.id::text, d.doc_code, d.doc_class, coalesce(d.meta->>'accessClass', 'internal'), d.title, coalesce(c.section_path, ''), "
    "coalesce(c.page::text, ''), md5(c.text), coalesce(d.published_at::text, d.meta->>'effectiveDate', '')))"
)


def diff(pg: dict[Any, tuple[str, str]], es: dict[Any, tuple[str, str]], key: Callable[[Any], Any] | None = None) -> tuple[list[Any], list[Any]]:
    """(올릴 id 오름차순, 지울 id) — 내용 해시나 임베딩 모델이 다르거나 ES 에 없는 것 / PG 에 없는 것."""
    upsert = sorted((i for i, ve in pg.items() if es.get(i) != ve), key=key)
    delete = sorted((i for i in es if i not in pg), key=key)
    return upsert, delete


def manifest_pg(session: Session) -> dict[int, tuple[str, str]]:
    return {int(i): (v, e) for i, v, e in session.execute(PG_MANIFEST.execution_options(stream_results=True))}


def manifest_doc_pg(session: Session) -> dict[str, tuple[str, str]]:
    out: dict[str, tuple[str, str]] = {}
    for o in ORIGINS:
        sql = text(
            f"SELECT c.id, {DOC_V} AS v, CASE WHEN c.embedding IS NULL THEN '' ELSE coalesce(c.embedding_model, '') END AS e "
            f"FROM {o}.chunk c JOIN {o}.document d ON d.id = c.document_id WHERE d.is_current ORDER BY c.id"
        )
        for i, v, e in session.execute(sql.execution_options(stream_results=True)):
            out[doc_es_id(o, i)] = (v, e)
    return out


def _scroll_manifest(idx: str, conv: Callable[[Any], Any]) -> dict[Any, tuple[str, str]]:
    out: dict[Any, tuple[str, str]] = {}
    r = request("POST", f"/{idx}/_search", params={"scroll": "2m"}, json_body={"size": 5000, "_source": ["v", "e"], "sort": ["_doc"], "query": {"match_all": {}}})
    sid = r.get("_scroll_id")
    try:
        while True:
            hits = (r.get("hits") or {}).get("hits") or []
            if not hits:
                break
            for h in hits:
                src = h.get("_source") or {}
                out[conv(h["_id"])] = (src.get("v", ""), src.get("e", ""))
            r = request("POST", "/_search/scroll", json_body={"scroll": "2m", "scroll_id": sid})
            sid = r.get("_scroll_id", sid)
    finally:
        if sid:
            try:
                request("DELETE", "/_search/scroll", json_body={"scroll_id": sid}, ok=(200, 404))
            except EsUnavailable:
                pass
    return out


def manifest_es() -> dict[int, tuple[str, str]]:
    return _scroll_manifest(index_name(), int)


def manifest_doc_es() -> dict[str, tuple[str, str]]:
    return _scroll_manifest(doc_index_name(), str)


def _bulk(lines: list[dict[str, Any]], conv: Callable[[Any], Any] = int) -> tuple[int, list[Any]]:
    """NDJSON 일괄 요청 — (성공 건수, 실패한 id). 전부 실패면 예외."""
    if not lines:
        return 0, []
    body = "\n".join(json.dumps(x, ensure_ascii=False) for x in lines) + "\n"
    r = request("POST", "/_bulk", content=body, params={"refresh": "false"})
    bad: list[Any] = []
    first = None
    items = r.get("items") or []
    for it in items:
        d = next(iter(it.values()))
        if d.get("status", 200) >= 300 and d.get("status") != 404:
            try:
                bad.append(conv(d.get("_id")))
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
                dims = ensure_vector_mapping(len(vec), idx)
            if len(vec) == dims:
                doc["embedding"] = vec
                doc["embedding_model"] = r["embedding_model"]
        lines.append({"index": {"_index": idx, "_id": str(r["id"])}})
        lines.append(doc)
    return lines, dims


def _doc_lines(session: Session, keys: list[str], dims: int | None) -> tuple[list[dict[str, Any]], int | None]:
    """문서 청크 → 일괄 요청 줄. 그사이 이전 판이 된 문서의 청크는 건너뛴다(다음 대조에서 지워진다)."""
    by: dict[str, list[int]] = {}
    for k in keys:
        o, n = parse_doc_id(k)
        by.setdefault(o, []).append(n)
    lines: list[dict[str, Any]] = []
    idx = doc_index_name()
    for o, ids in by.items():
        rows = session.execute(
            text(
                f"SELECT c.id, d.id AS doc_id, d.doc_code, d.doc_class, coalesce(d.meta->>'accessClass', 'internal') AS ac, d.title, c.section_path, c.page, c.text, "
                f"coalesce(d.published_at::text, d.meta->>'effectiveDate') AS pub, c.embedding_model, c.embedding::text AS emb, {DOC_V} AS v "
                f"FROM {o}.chunk c JOIN {o}.document d ON d.id = c.document_id WHERE d.is_current AND c.id = ANY(CAST(:ids AS int[]))"
            ),
            {"ids": ids},
        ).mappings().all()
        for r in rows:
            doc: dict[str, Any] = {
                "v": r["v"], "e": (r["embedding_model"] or "") if r["emb"] else "", "origin": o, "document_id": int(r["doc_id"]), "doc_code": r["doc_code"],
                "doc_class": r["doc_class"], "access_class": r["ac"] or "internal", "title": r["title"] or "", "text": (r["text"] or "")[:20000],
            }
            if r["section_path"]:
                doc["section"] = r["section_path"]
            if r["page"] is not None:
                doc["page"] = int(r["page"])
            if r["pub"]:
                doc["published"] = str(r["pub"])[:10]
            if r["emb"]:
                vec = json.loads(r["emb"])
                if dims is None:
                    dims = ensure_vector_mapping(len(vec), idx)
                if len(vec) == dims:
                    doc["embedding"] = vec
                    doc["embedding_model"] = r["embedding_model"]
            lines.append({"index": {"_index": idx, "_id": doc_es_id(o, r["id"])}})
            lines.append(doc)
    return lines, dims


# ── 동기화 상태 ───────────────────────────────────────────────
def _state_of(session: Session, key: str) -> dict[str, Any]:
    s = session.get(Setting, key)
    return dict(s.value) if s is not None and isinstance(s.value, dict) else {}


def _save_state_of(session: Session, key: str, **updates: Any) -> dict[str, Any]:
    st = {**_state_of(session, key), **updates}
    s = session.get(Setting, key)
    if s is None:
        what = "문서 청크" if key == DOC_STATE_KEY else "분석 결과 청크"
        session.add(Setting(key=key, value=st, description=f"AI 어시스턴트 ES 동기화 내부 상태({what} — 올린 위치 · 마지막 점검) — 직접 고치지 않는다"))
    else:
        s.value = st
    session.flush()
    return st


def _state(session: Session) -> dict[str, Any]:
    return _state_of(session, STATE_KEY)


def _save_state(session: Session, **updates: Any) -> dict[str, Any]:
    return _save_state_of(session, STATE_KEY, **updates)


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


def doc_search_state(session: Session) -> dict[str, Any] | None:
    """문서 색인 — {'synced_max_id': {출처: id}, 'dims'} 또는 None(한 번도 동기화 안 됨)."""
    st = _state_of(session, DOC_STATE_KEY)
    m = st.get("synced_max_id")
    if not isinstance(m, dict):
        return None
    return {"synced_max_id": {o: int(m.get(o, 0)) for o in ORIGINS}, "dims": int(st["dims"]) if st.get("dims") else None}


def _meta_for(version: int, rules: list[str] | None) -> dict[str, Any]:
    return {"version": version, "dict": dict_signature(rules)}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ── 동기화 ────────────────────────────────────────────────────
def sync(session: Session, *, limit: int = 2000, full_diff_min: float = 15.0, force: bool = False) -> dict[str, Any]:
    """분석 결과 청크 PG → ES 동기화 한 번. limit 건까지 올리고(오름차순) 사라진 것은 모두 지운다. 호출자가 commit 한다."""
    if not configured():
        return {"skipped": "ES_URL 미설정"}
    if not es_up():
        return {"skipped": "ES 차단기 열림(잠시 뒤 재시도)"}
    t0 = time.monotonic()
    try:
        rules = user_dictionary(session)
        meta = _meta_for(KB_MAPPING_VERSION, rules)
        analyzer, created = _ensure(index_name(), lambda a, r: index_body(a, r, meta), rules, meta)
        if created:
            _save_state(session, signature=None, pending=0, synced_max_id=None, last_full_at=None, docs=0, dims=None)
        st = _state(session)
        sig = session.execute(text("SELECT count(*), coalesce(max(id), 0), max(indexed_at)::text, count(embedding) FROM app.kb_chunk")).one()
        signature = [int(sig[0]), int(sig[1]), sig[2], int(sig[3])]
        last_full = st.get("last_full_at")
        due = force or not last_full or (time.time() - float(last_full)) > full_diff_min * 60
        if not due and st.get("signature") == signature and not st.get("pending"):
            return {"skipped": "변경 없음", "docs": st.get("docs")}
        pg = manifest_pg(session)
        es = manifest_es()
        upsert, delete = diff(pg, es)
        dims = _mapped_dims(index_name())
        done = 0
        failed_ids: list[int] = []
        batch_ids = upsert[:limit]
        for i in range(0, len(batch_ids), BULK_BATCH):
            lines, dims = _docs_for(session, batch_ids[i : i + BULK_BATCH], dims)
            ok, bad = _bulk(lines)
            done += ok
            failed_ids += bad
        removed = 0
        del_failed = 0
        for i in range(0, len(delete), BULK_BATCH):
            ok, bad = _bulk([{"delete": {"_index": index_name(), "_id": str(x)}} for x in delete[i : i + BULK_BATCH]])
            removed += ok
            del_failed += len(bad)  # 지우지 못한 것도 '남은 일' — 다음 주기(1분)에 다시 (15분 전체 대조를 기다리지 않는다)
        pending_ids = upsert[len(batch_ids) :]
        remaining = len(pending_ids) + len(failed_ids) + del_failed
        if done or removed:
            request("POST", f"/{index_name()}/_refresh")
        # '동기화됨' = ES 에 아직 없는(새) 청크 중 가장 작은 id 바로 앞까지. 그 뒤의 새 청크는 검색이 PostgreSQL 로 보충한다.
        # 이미 ES 에 있고 내용만 달라 다시 올릴 청크(오래된 판)는 ES 에서 계속 검색되므로 여기 넣지 않는다(최대 한 주기 지난 판을 본다 — 본문은 PG 에서 읽으므로 화면에는 최신).
        missing_new = [i for i in (*pending_ids, *failed_ids) if i not in es]
        max_id = int(sig[1])
        synced = (min(missing_new) - 1) if missing_new else max_id
        out = {
            "indexed": done, "failed": len(failed_ids), "deleted": removed, "pending": remaining, "docs": len(pg) - len(missing_new), "analyzer": analyzer, "dictionary": len(rules),
            "recreated": created, "sec": round(time.monotonic() - t0, 1),
        }
        _save_state(
            session,
            signature=signature if not remaining else None, pending=remaining, synced_max_id=synced, synced_at=_now_iso(),
            last_full_at=time.time(), docs=out["docs"], analyzer=analyzer, dictionary=len(rules), last_error=None, dims=dims,
        )
        return out
    except EsUnavailable as exc:
        _save_state(session, last_error=str(exc)[:300], last_error_at=_now_iso())
        log.warning("ES 동기화 실패: %s", exc)
        return {"skipped": f"ES 오류 — {str(exc)[:160]}"}


def sync_docs(session: Session, *, limit: int = 2000, full_diff_min: float = 15.0, force: bool = False) -> dict[str, Any]:
    """문서 청크(현재 버전) PG → ES 동기화 한 번. 새 판이 적재되면 이전 판 청크는 목록에서 빠져 지워진다. 호출자가 commit 한다."""
    if not configured():
        return {"skipped": "ES_URL 미설정"}
    if not es_up():
        return {"skipped": "ES 차단기 열림(잠시 뒤 재시도)"}
    t0 = time.monotonic()
    idx = doc_index_name()
    try:
        rules = user_dictionary(session)
        meta = _meta_for(DOC_MAPPING_VERSION, rules)
        analyzer, created = _ensure(idx, lambda a, r: doc_index_body(a, r, meta), rules, meta)
        if created:
            _save_state_of(session, DOC_STATE_KEY, signature=None, pending=0, synced_max_id=None, last_full_at=None, docs=0, dims=None)
        st = _state_of(session, DOC_STATE_KEY)
        signature: dict[str, list[int]] = {}
        for o in ORIGINS:
            r = session.execute(
                text(f"SELECT count(*), coalesce(max(c.id), 0), count(c.embedding), coalesce(max(d.id), 0) FROM {o}.chunk c JOIN {o}.document d ON d.id = c.document_id WHERE d.is_current")
            ).one()
            signature[o] = [int(x) for x in r]
        last_full = st.get("last_full_at")
        due = force or not last_full or (time.time() - float(last_full)) > full_diff_min * 60
        if not due and st.get("signature") == signature and not st.get("pending"):
            return {"skipped": "변경 없음", "docs": st.get("docs")}
        pg = manifest_doc_pg(session)
        es = manifest_doc_es()
        upsert, delete = diff(pg, es, key=parse_doc_id)
        dims = _mapped_dims(idx)
        done = 0
        failed: list[str] = []
        batch = upsert[:limit]
        for i in range(0, len(batch), BULK_BATCH):
            lines, dims = _doc_lines(session, batch[i : i + BULK_BATCH], dims)
            ok, bad = _bulk(lines, str)
            done += ok
            failed += bad
        removed = 0
        del_failed = 0
        for i in range(0, len(delete), BULK_BATCH):
            ok, bad = _bulk([{"delete": {"_index": idx, "_id": x}} for x in delete[i : i + BULK_BATCH]], str)
            removed += ok
            del_failed += len(bad)
        pending = upsert[len(batch) :]
        remaining = len(pending) + len(failed) + del_failed
        if done or removed:
            request("POST", f"/{idx}/_refresh")
        missing_new = [parse_doc_id(k) for k in (*pending, *failed) if k not in es]
        synced: dict[str, int] = {}
        for o in ORIGINS:
            miss = [n for oo, n in missing_new if oo == o]
            synced[o] = (min(miss) - 1) if miss else signature[o][1]
        out = {
            "indexed": done, "failed": len(failed), "deleted": removed, "pending": remaining, "docs": len(pg) - len(missing_new), "analyzer": analyzer, "dictionary": len(rules),
            "recreated": created, "sec": round(time.monotonic() - t0, 1),
        }
        _save_state_of(
            session, DOC_STATE_KEY,
            signature=signature if not remaining else None, pending=remaining, synced_max_id=synced, synced_at=_now_iso(),
            last_full_at=time.time(), docs=out["docs"], analyzer=analyzer, dictionary=len(rules), last_error=None, dims=dims,
        )
        return out
    except EsUnavailable as exc:
        _save_state_of(session, DOC_STATE_KEY, last_error=str(exc)[:300], last_error_at=_now_iso())
        log.warning("ES 문서 색인 동기화 실패: %s", exc)
        return {"skipped": f"ES 오류 — {str(exc)[:160]}"}


def sync_all(session: Session, *, limit: int = 2000, force: bool = False) -> dict[str, Any]:
    """두 색인을 차례로(분석 결과 → 문서). 한쪽이 실패해도 다른 쪽은 진행한다. 호출자가 commit 한다."""
    out = {"analysis": sync(session, limit=limit, force=force)}
    session.flush()
    out["documents"] = sync_docs(session, limit=limit, force=force)
    return out


def rebuild(session: Session) -> dict[str, Any]:
    """분석 결과 색인을 지우고 처음부터 다시 올린다(임베딩 차원이 바뀌었거나 분석기를 바꿀 때). 제한 없이 한 번에."""
    if not configured():
        return {"skipped": "ES_URL 미설정"}
    request("DELETE", f"/{index_name()}", ok=(200, 404))
    _save_state(session, signature=None, pending=0, synced_max_id=None, last_full_at=None, docs=0, dims=None)
    return sync(session, limit=10**9, force=True)


def rebuild_docs(session: Session) -> dict[str, Any]:
    if not configured():
        return {"skipped": "ES_URL 미설정"}
    request("DELETE", f"/{doc_index_name()}", ok=(200, 404))
    _save_state_of(session, DOC_STATE_KEY, signature=None, pending=0, synced_max_id=None, last_full_at=None, docs=0, dims=None)
    return sync_docs(session, limit=10**9, force=True)


# ── 검색 ──────────────────────────────────────────────────────
def _named_clauses(stems: list[str], fields: list[str]) -> list[dict[str, Any]]:
    # 어절 하나 = 한 절. 구문(phrase) 일치 — nori 가 풀어 낸 조각(가계 · 자금 · 대출 · 금)이 문서 안에 흩어져 있어도 맞는 것으로 치지 않고, 이어서 나올 때만 맞춘다(PostgreSQL 접두 일치와 같은 정밀도).
    # 조사 · 어미는 분석기가 떼므로 '증가율과' 가 '증가율이' 에도 맞는다.
    mode = {"type": "phrase"} if KEYWORD_PHRASE else {"operator": "and"}
    return [{"multi_match": {"query": s, "fields": fields, **mode, "_name": f"s{i}"}} for i, s in enumerate(stems)]


def keyword_hits(scope: AccessScope, stems: list[str], total: int, *, size: int, min_ratio: float) -> list[tuple[int, float, int]]:
    """(청크 id, BM25 점수, 맞춘 어절 수) — 어절 중 `min_ratio` 비율 이상이 제목 · 본문에 나온 청크, 점수 높은 순. PG 키워드 채널의 최소 어절 수와 같은 기준.
    맞춘 어절 수는 어절마다 이름 붙인 절(`s0`, `s1` …)의 `matched_queries` 개수다 — nori 가 활용형을 풀어 맞춘 경우도 세어지므로 파이썬에서 부분 문자열로 다시 세지 않는다."""
    low = max(1, math.ceil(total * float(min_ratio) - 1e-9))
    if not stems or len(stems) < low:
        return []
    should = _named_clauses(stems, ["title^2", "text"])
    body = {"size": size, "_source": False, "track_total_hits": False, "query": {"bool": {"filter": [es_filter(scope)], "should": should, "minimum_should_match": low}}}
    r = request("POST", f"/{index_name()}/_search", json_body=body)
    return [(int(h["_id"]), float(h.get("_score") or 0.0), len(h.get("matched_queries") or [])) for h in (r.get("hits") or {}).get("hits") or []]


def vector_hits(scope: AccessScope, qvec: list[float], model: str, *, k: int) -> list[tuple[int, float]]:
    """(청크 id, 코사인 거리) — 가까운 순. ES 의 cosine 점수는 (1+cos)/2 이므로 거리 = 2 − 2×점수."""
    flt = {"bool": {"filter": [es_filter(scope), {"term": {"embedding_model": model}}]}}
    body = {"size": k, "_source": False, "knn": {"field": "embedding", "query_vector": qvec, "k": k, "num_candidates": max(100, k * 10), "filter": flt}}
    r = request("POST", f"/{index_name()}/_search", json_body=body)  # 매핑이 없거나 차원이 다르면 400(EsError) — 호출자가 PostgreSQL 로 폴백
    return [(int(h["_id"]), max(0.0, 2.0 - 2.0 * float(h.get("_score") or 0.0))) for h in (r.get("hits") or {}).get("hits") or []]


def doc_keyword_hits(flt: dict[str, Any], stems: list[str], *, size: int, min_should: int = 1) -> list[tuple[str, int, float, int]]:
    """문서 청크 키워드 — (출처, 청크 id, BM25, 맞춘 어절 수). 제목 · 절 경로 · 본문 중 어디서든 맞으면 센다. 기본은 어절 하나라도(PG 문서 채널의 OR 질의와 같은 범위)."""
    if not stems:
        return []
    should = _named_clauses(stems, ["title", "section", "text"])
    body = {"size": size, "_source": False, "track_total_hits": False, "query": {"bool": {"filter": [flt], "should": should, "minimum_should_match": max(1, int(min_should))}}}
    r = request("POST", f"/{doc_index_name()}/_search", json_body=body)
    out = []
    for h in (r.get("hits") or {}).get("hits") or []:
        o, n = parse_doc_id(h["_id"])
        out.append((o, n, float(h.get("_score") or 0.0), len(h.get("matched_queries") or [])))
    return out


def doc_vector_hits(flt: dict[str, Any], qvec: list[float], model: str | None, *, k: int) -> list[tuple[str, int, float]]:
    """문서 청크 의미 — (출처, 청크 id, 코사인 거리). 모델을 알면 같은 모델 임베딩만."""
    f: list[dict[str, Any]] = [flt]
    if model:
        f.append({"term": {"embedding_model": model}})
    body = {"size": k, "_source": False, "knn": {"field": "embedding", "query_vector": qvec, "k": k, "num_candidates": max(100, k * 10), "filter": {"bool": {"filter": f}}}}
    r = request("POST", f"/{doc_index_name()}/_search", json_body=body)
    out = []
    for h in (r.get("hits") or {}).get("hits") or []:
        o, n = parse_doc_id(h["_id"])
        out.append((o, n, max(0.0, 2.0 - 2.0 * float(h.get("_score") or 0.0))))
    return out


# ── 상태 ──────────────────────────────────────────────────────
STATE_FIELDS = ("synced_at", "docs", "pending", "analyzer", "dictionary", "last_error", "last_error_at", "dims")


def _count(idx: str) -> int | None:
    try:
        return int(request("GET", f"/{idx}/_count").get("count", 0))
    except EsError:
        return None  # 색인 아직 없음


def status(session: Session) -> dict[str, Any]:
    """관리자 상태 — 설정 여부 · 연결 · 색인별(분석 결과 · 문서) 문서 수 · 뒤처진 청크 수 · 분석기 · 사용자 사전 낱말 수."""
    st = _state(session)
    dst = _state_of(session, DOC_STATE_KEY)
    out: dict[str, Any] = {
        "configured": configured(), "up": False, "index": index_name() if configured() else None, "state": {k: st.get(k) for k in STATE_FIELDS},
        "documents": {"index": doc_index_name() if configured() else None, "state": {k: dst.get(k) for k in STATE_FIELDS}},
    }
    if not configured():
        return out
    try:
        h = request("GET", "/_cluster/health")
        out["up"] = True
        out["cluster"] = {"status": h.get("status"), "nodes": h.get("number_of_nodes")}
        out["es_docs"] = _count(index_name())
        pg = int(session.execute(text("SELECT count(*) FROM app.kb_chunk")).scalar() or 0)
        out["pg_chunks"] = pg
        out["lag"] = None if out.get("es_docs") is None else max(0, pg - int(out["es_docs"]))
        d = out["documents"]
        d["es_docs"] = _count(doc_index_name())
        dpg = sum(int(session.execute(text(f"SELECT count(*) FROM {o}.chunk c JOIN {o}.document d ON d.id = c.document_id WHERE d.is_current")).scalar() or 0) for o in ORIGINS)
        d["pg_chunks"] = dpg
        d["lag"] = None if d.get("es_docs") is None else abs(dpg - int(d["es_docs"]))
    except EsAuthError as exc:
        out["error"] = str(exc)[:200]
        out["errorKind"] = "auth"
        out["remedy"] = AUTH_REMEDY
    except EsError as exc:
        out["error"] = str(exc)[:200]
        out["errorKind"] = "rejected"
    except EsUnavailable as exc:
        out["error"] = str(exc)[:200]
        out["errorKind"] = "down"
    conn = connection()
    out["connection"] = {"source": conn["source"], "url": safe_url(conn["url"]), "user": conn["user"]}
    return out


def safe_url(url: str) -> str:
    """화면 · 로그용 주소 — 주소에 섞인 계정 정보(user:pass@)는 뺀다."""
    return re.sub(r"//[^/@]*@", "//", url or "")


def healthy(st: dict[str, Any]) -> tuple[bool, list[str]]:
    """`status()` 결과로 3-way 검색이 온전한지 — (온전함, 문제 목록). CLI `kb-es --check` · 운영 점검이 쓴다."""
    probs: list[str] = []
    if not st.get("configured"):
        return False, ["ES_URL 미설정 — PostgreSQL 축소 동작"]
    if not st.get("up"):
        return False, [f"ES 연결 불가 — {st.get('error', '')[:120]}"]
    for name, part in (("분석 결과", st), ("문서", st.get("documents") or {})):
        s = part.get("state") or {}
        if not s.get("synced_at"):
            probs.append(f"{name} 색인 동기화 전")
        elif part.get("lag"):
            probs.append(f"{name} 색인 뒤처짐 {part.get('es_docs')}/{part.get('pg_chunks')}")
        if s.get("analyzer") == "standard":
            probs.append(f"{name} 색인 nori 없음(standard)")
    return not probs, probs
