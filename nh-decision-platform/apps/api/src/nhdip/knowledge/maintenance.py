"""색인 유지보수 — 워커 housekeeping 이 60초마다 돈다 (요구사항 KB-09 · 설계 §21.5).

1) 대조: 산출물 현재 세대와 색인 세대가 다른 키(직접 게시 · 장애로 놓친 것)와, 컬렉션 규칙 · 매핑 설정이 바뀐 경우 전체를 다시 색인한다.
2) 임베딩: 임베딩이 없거나 모델이 바뀐 청크를 배치로 채운다(네트워크 호출이라 게시 트랜잭션과 분리).
3) 그래프: 색인이 바뀌었으면 이벤트 `kb.indexed` 를 한 번 내 그래프 투영이 산출물 → 개념 관계를 반영하게 한다.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from sqlalchemy import func, or_, select, update
from sqlalchemy import text as text_ddl
from sqlalchemy.orm import Session

from nhdip.analysis_registry import spaces as analysis_spaces
from nhdip.events import emit
from nhdip.llm import LlmError, LlmUnavailable, embed, resolve
from nhdip.models import KbChunk, Setting, utcnow

from . import elastic
from .access import load_collections, setting_dict
from .defaults import ARTIFACT_RESOURCES, ARTIFACT_ROUTES, INDEX_DEFAULT, PERSONA_RESOURCES, SEARCH_DEFAULT
from .indexer import IndexStats, index_artifacts, stale_keys

log = logging.getLogger("nhdip.knowledge")
STATE_KEY = "knowledge.state"


def get_state(session: Session) -> dict[str, Any]:
    s = session.get(Setting, STATE_KEY)
    return dict(s.value) if s is not None and isinstance(s.value, dict) else {}


def set_state(session: Session, **updates: Any) -> dict[str, Any]:
    st = {**get_state(session), **updates}
    s = session.get(Setting, STATE_KEY)
    if s is None:
        session.add(Setting(key=STATE_KEY, value=st, description="질문하기 지식 색인 내부 상태(지문 · 그래프 반영 표지) — 직접 고치지 않는다"))
    else:
        s.value = st
    session.flush()
    return st


def config_fingerprint(session: Session) -> str:
    """청크에 저장되는 값(컬렉션 배정 · 리소스 · 주소 · 분할 설정)에 영향을 주는 설정의 지문.
    담당/공유 팀 · 공개 범위는 검색 때 읽으므로 포함하지 않는다(바꿔도 재색인 불필요)."""
    cols = [[c.code, c.kind, c.sources] for c in load_collections(session, enabled_only=False)]
    blob = {
        "collections": cols,
        "resources": setting_dict(session, "knowledge.artifact_resources", ARTIFACT_RESOURCES),
        "persona": setting_dict(session, "knowledge.persona_resources", PERSONA_RESOURCES),
        "routes": setting_dict(session, "knowledge.artifact_routes", ARTIFACT_ROUTES),
        "index": setting_dict(session, "knowledge.index", INDEX_DEFAULT),
        # 분석 공간의 열람 리소스 · 화면 주소는 맞춤 분석 보고서(report.an-*) 청크에 저장된다 — 바뀌면 재색인
        "spaces": {k: [sp.get("resource"), sp.get("path")] for k, sp in sorted(analysis_spaces(session).items())},
    }
    return hashlib.sha1(json.dumps(blob, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()[:20]


def embedding_agent(session: Session) -> str:
    s = session.get(Setting, "embedding.agent")
    return str(s.value) if s is not None and s.value else "embedder"


def embed_pending(session: Session, limit: int | None = None) -> dict[str, Any]:
    """임베딩 대기 청크를 채운다. 모델 미설정 · 호출 실패 · 예산 초과는 건너뛰고(다음 주기에 재시도) 사유를 돌려준다."""
    cfg = setting_dict(session, "knowledge.index", INDEX_DEFAULT)
    batch = max(1, int(cfg.get("embed_batch", 32)))
    cap = int(limit if limit is not None else cfg.get("embed_max_per_run", 500))
    try:
        llm = resolve(session, embedding_agent(session))
    except LlmUnavailable as exc:
        return {"embedded": 0, "skipped": str(exc)[:200]}
    done = 0
    reason = None
    while done < cap:
        rows = session.execute(
            select(KbChunk.id, KbChunk.text).where(or_(KbChunk.embedding.is_(None), KbChunk.embedding_model != llm.model)).order_by(KbChunk.id).limit(min(batch, cap - done))
            # 배치마다 commit 하면 워커 잠금(xact)이 풀린다 — 다른 워커가 같은 청크를 다시 임베딩(비용 중복)하지 않게 행을 잡고 건너뛴다
            .with_for_update(skip_locked=True, of=KbChunk)
        ).all()
        if not rows:
            break
        try:
            vecs = embed(session, llm, [t[:4000] for _, t in rows])
        except LlmError as exc:
            reason = str(exc)[:200]
            log.warning("지식 청크 임베딩 실패: %s", reason)
            break
        if len(vecs) != len(rows):
            reason = "임베딩 개수 불일치"
            break
        for (cid, _), vec in zip(rows, vecs):
            session.execute(update(KbChunk).where(KbChunk.id == cid).values(embedding=vec, embedding_model=llm.model))
        session.commit()
        done += len(rows)
    out: dict[str, Any] = {"embedded": done, "model": llm.model}
    if reason:
        out["skipped"] = reason
    return out


def _signature(session: Session) -> str:
    n, last = session.execute(select(func.count(), func.max(KbChunk.indexed_at))).one()
    return f"{n}:{last.isoformat() if last else ''}"


def reconcile(session: Session, *, full: bool = False) -> IndexStats:
    """산출물 ↔ 색인 대조. full=True 면 전체를 다시 색인한다."""
    st = get_state(session)
    fp = config_fingerprint(session)
    if full or st.get("fingerprint") != fp:
        stats = index_artifacts(session, None)
        empty = stats.empty
    else:
        todo, drop = stale_keys(session, st.get("empty"))
        stats = index_artifacts(session, [*todo, *drop]) if (todo or drop) else IndexStats()
        empty = {**(st.get("empty") or {}), **stats.empty}
    set_state(session, fingerprint=fp, empty=empty, reconciled_at=utcnow().isoformat())
    return stats


def run_maintenance(session: Session) -> dict[str, Any]:
    """워커 주기 작업 한 번 — 대조 → 임베딩 → 그래프 이벤트. 호출자가 마지막에 commit 한다(임베딩은 배치마다 commit)."""
    out: dict[str, Any] = {}
    stats = reconcile(session)
    out["index"] = stats.as_dict()
    session.commit()
    out["embed"] = embed_pending(session)
    if elastic.configured():
        # 선택 검색 엔진(ES) 동기화 — 검색 설정이 아직 pg 여도 미리 올려 둬 전환 시 바로 쓰게 한다. ES 문제가 색인 작업을 막지 않는다(설계 §21.18)
        try:
            out["es"] = elastic.sync(session, limit=int(setting_dict(session, "knowledge.search", SEARCH_DEFAULT).get("es_sync_max_per_run", 2000)))
            session.commit()
        except Exception as exc:  # noqa: BLE001 — ES 동기화 실패는 경고만, 다음 주기에 다시
            session.rollback()
            log.warning("ES 동기화 중 오류: %s", exc)
            out["es"] = {"skipped": f"오류 — {type(exc).__name__}: {str(exc)[:120]}"}
    sig = _signature(session)
    if sig != get_state(session).get("graph_signature"):
        emit(session, "kb.indexed", {"signature": sig}, "knowledge")
        set_state(session, graph_signature=sig)
        out["graph_event"] = True
    session.commit()
    return out


def status(session: Session) -> dict[str, Any]:
    """관리자 상태 — 컬렉션별 청크 · 임베딩 · 미분류, 마지막 색인 시각."""
    rows = session.execute(
        select(
            KbChunk.collection_code, func.count(), func.count(KbChunk.embedding), func.count(func.distinct(KbChunk.source_key)), func.max(KbChunk.indexed_at),
        ).group_by(KbChunk.collection_code)
    ).all()
    by_coll = {c: {"chunks": n, "embedded": e, "sources": s, "lastIndexedAt": t.isoformat() if t else None} for c, n, e, s, t in rows}
    total = sum(v["chunks"] for v in by_coll.values())
    embedded = sum(v["embedded"] for v in by_coll.values())
    todo, drop = stale_keys(session, get_state(session).get("empty"))
    return {
        "collections": by_coll,
        "totals": {"chunks": total, "embedded": embedded, "pendingEmbedding": total - embedded},
        "stale": {"toIndex": todo[:20], "toDelete": drop[:20], "count": len(todo) + len(drop)},
        "state": {k: v for k, v in get_state(session).items() if k in ("reconciled_at", "fingerprint")},
    }


def ensure_hnsw(session: Session, dim: int) -> dict[str, Any]:
    """임베딩 모델이 확정되어 차원을 알 때 부분 HNSW 인덱스를 만들고 검색이 쓰게 한다 (설계 §21.2 · Q119).

    열 차원을 고정하지 않으므로 `vector(N)` 으로 형변환한 식 위에 `vector_dims(embedding) = N` 인 행만 담는 인덱스를 둔다.
    검색은 설정 `knowledge.search.hnsw_dim` 이 질의 벡터 차원과 같을 때만 같은 식을 써서 인덱스를 탄다(다르면 순차 탐색으로 계속 동작)."""
    dim = int(dim)
    if not 2 <= dim <= 2000:  # pgvector HNSW 는 vector 2000차원까지
        raise ValueError("차원은 2~2000 사이여야 합니다")
    name = f"ix_kb_chunk_emb_hnsw_{dim}"
    # HNSW 그래프가 maintenance_work_mem(기본 64MB)에 들어가지 않으면 디스크로 넘쳐 몇 배 느려진다(10만 건 × 1024차원에서 확인) → 이 트랜잭션에만 넉넉히
    session.execute(text_ddl("SET LOCAL maintenance_work_mem = '1GB'"))
    session.execute(text_ddl("SET LOCAL max_parallel_maintenance_workers = 4"))
    session.execute(  # 정수만 식별자 · 식에 들어간다(형변환 검증 후) — 값 바인딩이 불가능한 DDL
        text_ddl(f"CREATE INDEX IF NOT EXISTS {name} ON app.kb_chunk USING hnsw ((embedding::vector({dim})) vector_cosine_ops) WHERE vector_dims(embedding) = {dim}")
    )
    s = session.get(Setting, "knowledge.search")
    value = {**(s.value if s is not None and isinstance(s.value, dict) else {}), "hnsw_dim": dim}
    if s is None:
        session.add(Setting(key="knowledge.search", value=value, description="질문하기 하이브리드 검색 설정"))
    else:
        s.value = value
    session.commit()
    return {"index": name, "dim": dim}
