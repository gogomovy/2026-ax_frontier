"""그래프 필터드 하이브리드 검색 (설계 §19.2 검색 순서 2~3 · 3-way 구성 설계 §24) — 워크플로 근거 검색(retrieve_evidence) · 화면 검색 · 골든셋.

- 그래프: 질의 개념과 연결된 문서 집합 (Neo4j) — 비어 있거나 장애면 필터 없이 진행
- 키워드 · 의미: **Elasticsearch 문서 색인**(nori BM25 · kNN, 같은 조건 필터)이 동기화돼 있으면 거기서, 아니면 PostgreSQL
  (tsvector 접두 일치 OR 질의 · pgvector 코사인 거리). ES 후보는 PostgreSQL 에서 같은 조건(현재 버전 · 분류 · 개념 경로 문서)으로 다시 걸러 읽고,
  ES 에 아직 못 올린 새 청크(출처별 id > 동기화 위치)는 PostgreSQL 이 보충한다. ES 오류면 PostgreSQL 로 폴백한다.
- 결합: RRF(Reciprocal Rank Fusion)
"""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from .neo4j_client import GraphUnavailable, run

TERM = re.compile(r"[0-9A-Za-z가-힣]{2,}")
COLS = "c.id, c.text, c.page, c.section_path, d.id AS doc_id, d.title, d.doc_class"


def query_terms(query: str) -> list[str]:
    return TERM.findall(query or "")[:12]


def graph_documents(concepts: list[str]) -> dict[str, list[int]] | None:
    if not concepts:
        return None
    try:
        rows = run(
            "MATCH (d:Document)-[:MENTIONS|STATES_STANCE|SETS_CONSTRAINT]->(c) WHERE c.key IN $keys OR c.name IN $keys "
            "RETURN DISTINCT d.doc_origin AS origin, d.doc_id AS id",
            keys=concepts,
        )
    except GraphUnavailable:
        return None
    out: dict[str, list[int]] = {}
    for r in rows:
        if r.get("origin") and r.get("id") is not None:
            out.setdefault(r["origin"], []).append(int(r["id"]))
    return out or None


def _es_ready(session: Session, diag: dict[str, Any]) -> dict[str, Any] | None:
    """문서 색인을 써도 되면 동기화 상태, 아니면 None(이유는 diag['esFallback'])."""
    from nhdip.knowledge import elastic  # 지연 import — knowledge 가 graph 를 쓰므로 모듈 순환을 피한다

    st, why = elastic.readiness(session, "doc", elastic.backend_mode(session))
    if why:
        diag["esFallback"] = why
    return st


def _es_hits(
    terms: list[str], origins: tuple[str, ...], doc_filter: dict[str, list[int]] | None, query_vec: list[float] | None, model: str | None, doc_classes: list[str] | None,
    lim: int, st: dict[str, Any], diag: dict[str, Any],
) -> tuple[list[tuple[str, int, float, int]] | None, list[tuple[str, int, float]] | None]:
    """(키워드 후보, 의미 후보) — 채널마다 ES 를 못 쓰면 None(그 채널은 PostgreSQL 전체)."""
    from nhdip.knowledge import elastic

    flt = elastic.doc_es_filter_for(origins, doc_filter, doc_classes)
    kw: list[tuple[str, int, float, int]] | None = None
    vec: list[tuple[str, int, float]] | None = None
    try:
        kw = elastic.doc_keyword_hits(flt, terms, size=lim) if terms else []
    except (elastic.EsUnavailable, ValueError, KeyError, TypeError) as exc:
        diag["esFallback"] = f"keyword: {str(exc)[:140]}"
        return None, None
    if query_vec:
        if st.get("dims") == len(query_vec):
            try:
                vec = elastic.doc_vector_hits(flt, query_vec, model, k=lim)
            except (elastic.EsUnavailable, ValueError, KeyError, TypeError) as exc:
                diag["esFallback"] = f"vector: {str(exc)[:140]}"
        else:
            diag["esFallback"] = "vector: ES 임베딩 색인 없음 또는 차원 불일치"
    return kw, vec


def hybrid_search(
    session: Session,
    query: str,
    *,
    origins: tuple[str, ...] = ("bank", "ext"),
    doc_filter: dict[str, list[int]] | None = None,
    query_vec: list[float] | None = None,
    doc_classes: list[str] | None = None,
    k: int = 5,
    rrf_k: int = 60,
    model: str | None = None,
    diag: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """근거 후보 — 결과 모양은 엔진과 관계없이 같다. `diag` 를 넘기면 실제로 쓴 엔진(engine = es | pg) · 폴백 사유를 채운다."""
    diag = diag if diag is not None else {}
    terms = TERM.findall(query or "")[:12]
    tsq = " | ".join(f"{t}:*" for t in terms)
    lim = k * 4
    st = _es_ready(session, diag)
    es_kw, es_vec = (None, None)
    if st is not None:
        es_kw, es_vec = _es_hits(terms, origins, doc_filter, query_vec, model, doc_classes, lim, st, diag)
    mid: dict[str, int] = (st or {}).get("synced_max_id") or {}
    diag["engine"] = "es" if (es_kw is not None or es_vec is not None) else "pg"
    diag.setdefault("es", {})
    # 출처(bank/ext)별로 조회한 뒤 원점수로 전역 순위를 매기고 RRF 결합
    kw_rows: list[tuple[str, Any]] = []
    vec_rows: list[tuple[str, Any]] = []
    for origin in origins:
        if doc_filter is not None and origin not in doc_filter:
            continue
        where = ["d.is_current"]
        params: dict[str, Any] = {"lim": lim}
        if doc_filter is not None:
            where.append("d.id = ANY(:ids)")
            params["ids"] = doc_filter[origin]
        if doc_classes:
            where.append("d.doc_class = ANY(:classes)")
            params["classes"] = doc_classes
        w = " AND ".join(where)
        base = f"FROM {origin}.chunk c JOIN {origin}.document d ON d.id = c.document_id WHERE {w}"
        newer = f" AND c.id > {int(mid.get(origin, 0))}"  # ES 보충 — 정수만 들어간다
        # ES 후보 — PostgreSQL 에서 같은 조건으로 다시 걸러 읽는다(이전 판 · 분류 밖 · 개념 경로 밖 청크는 사라진다)
        es_ids = sorted({n for o, n, *_ in (es_kw or []) if o == origin} | {n for o, n, _ in (es_vec or []) if o == origin})
        got: dict[int, Any] = {}
        if es_ids:
            for r in session.execute(text(f"SELECT {COLS} {base} AND c.id = ANY(CAST(:es_ids AS int[]))"), {**params, "es_ids": es_ids}).mappings().all():
                got[int(r["id"])] = dict(r)
        if es_kw is not None:
            hits = [h for h in es_kw if h[0] == origin]
            top = max((h[2] for h in es_kw), default=0.0) or 1.0
            kept = 0
            for _, n, bm25, matched in hits:
                if n in got:
                    kw_rows.append((origin, {**got[n], "s": float(matched) + 0.1 * (bm25 / top)}))
                    kept += 1
            diag["es"].setdefault("keyword", {"hits": 0, "kept": 0})
            diag["es"]["keyword"]["hits"] += len(hits)
            diag["es"]["keyword"]["kept"] += kept
        if tsq and (es_kw is None or mid):
            # 질의어 커버리지(서로 다른 질의어가 몇 개 맞는지)를 먼저, 빈도 기반 ts_rank 는 보조로 — ES 를 쓰면 아직 못 올린 새 청크만
            cover = " + ".join(f"(c.tsv @@ to_tsquery('simple', :t{i}))::int" for i in range(len(terms)))
            term_params = {f"t{i}": f"{t}:*" for i, t in enumerate(terms)}
            extra = newer if es_kw is not None else ""
            rows = session.execute(
                text(f"SELECT {COLS}, ({cover}) + 0.1 * ts_rank(c.tsv, to_tsquery('simple', :q)) AS s {base}{extra} AND c.tsv @@ to_tsquery('simple', :q) ORDER BY s DESC LIMIT :lim"),
                {**params, **term_params, "q": tsq},
            ).mappings().all()
            kw_rows += [(origin, r) for r in rows]
        if query_vec:
            if es_vec is not None:
                for _, n, dist in (h for h in es_vec if h[0] == origin):
                    if n in got:
                        vec_rows.append((origin, {**got[n], "dist": dist}))
            if es_vec is None or mid:
                vec = "[" + ",".join(f"{x:.7f}" for x in query_vec) + "]"
                extra = newer if es_vec is not None else ""
                same_model = " AND c.embedding_model = :model" if model else ""
                rows = session.execute(
                    text(f"SELECT {COLS}, (c.embedding <=> CAST(:v AS vector)) AS dist {base}{extra}{same_model} AND c.embedding IS NOT NULL AND vector_dims(c.embedding) = :dim ORDER BY dist LIMIT :lim"),
                    {**params, "v": vec, "dim": len(query_vec), **({"model": model} if model else {})},
                ).mappings().all()
                vec_rows += [(origin, r) for r in rows]

    scored: dict[tuple[str, int], dict[str, Any]] = {}

    def item(origin: str, r: Any) -> dict[str, Any]:
        return scored.setdefault((origin, r["id"]), {"origin": origin, "chunk_id": r["id"], "document_id": r["doc_id"], "title": r["title"], "doc_class": r["doc_class"], "page": r["page"], "section_path": r["section_path"], "text": r["text"], "score": 0.0, "signals": {}})

    seen_kw: set[tuple[str, int]] = set()
    for rank, (origin, r) in enumerate(sorted(kw_rows, key=lambda x: float(x[1]["s"]), reverse=True), start=1):
        if (origin, r["id"]) in seen_kw:
            continue
        seen_kw.add((origin, r["id"]))
        it = item(origin, r)
        it["score"] += 1.0 / (rrf_k + rank)
        it["signals"]["keyword_rank"] = rank
        it["signals"]["keyword_score"] = round(float(r["s"]), 4)
    seen_vec: set[tuple[str, int]] = set()
    for rank, (origin, r) in enumerate(sorted(vec_rows, key=lambda x: float(x[1]["dist"])), start=1):
        if (origin, r["id"]) in seen_vec:
            continue
        seen_vec.add((origin, r["id"]))
        it = item(origin, r)
        it["score"] += 1.0 / (rrf_k + rank)
        it["signals"]["vector_rank"] = rank
        it["signals"]["cosine_distance"] = round(float(r["dist"]), 4)
    return sorted(scored.values(), key=lambda x: x["score"], reverse=True)[:k]
