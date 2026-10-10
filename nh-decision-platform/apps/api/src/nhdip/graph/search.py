"""그래프 필터드 하이브리드 검색 (설계 §19.2 검색 순서 2~3).

- 그래프: 질의 개념과 연결된 문서 집합 (Neo4j) — 비어 있거나 장애면 필터 없이 진행
- 키워드: PostgreSQL tsvector (접두 일치 OR 질의)
- 벡터: pgvector 코사인 거리 (임베딩 모델이 설정된 경우)
- 결합: RRF(Reciprocal Rank Fusion)
"""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from .neo4j_client import GraphUnavailable, run

TERM = re.compile(r"[0-9A-Za-z가-힣]{2,}")


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
) -> list[dict[str, Any]]:
    terms = TERM.findall(query or "")[:12]
    tsq = " | ".join(f"{t}:*" for t in terms)
    # 출처(bank/ext)별로 조회한 뒤 원점수로 전역 순위를 매기고 RRF 결합
    kw_rows: list[tuple[str, Any]] = []
    vec_rows: list[tuple[str, Any]] = []
    for origin in origins:
        if doc_filter is not None and origin not in doc_filter:
            continue
        where = ["d.is_current"]
        params: dict[str, Any] = {"lim": k * 4}
        if doc_filter is not None:
            where.append("d.id = ANY(:ids)")
            params["ids"] = doc_filter[origin]
        if doc_classes:
            where.append("d.doc_class = ANY(:classes)")
            params["classes"] = doc_classes
        w = " AND ".join(where)
        base = f"FROM {origin}.chunk c JOIN {origin}.document d ON d.id = c.document_id WHERE {w}"
        if tsq:
            # 질의어 커버리지(서로 다른 질의어가 몇 개 맞는지)를 먼저, 빈도 기반 ts_rank 는 보조로
            cover = " + ".join(f"(c.tsv @@ to_tsquery('simple', :t{i}))::int" for i in range(len(terms)))
            term_params = {f"t{i}": f"{t}:*" for i, t in enumerate(terms)}
            rows = session.execute(
                text(f"SELECT c.id, c.text, c.page, c.section_path, d.id AS doc_id, d.title, d.doc_class, ({cover}) + 0.1 * ts_rank(c.tsv, to_tsquery('simple', :q)) AS s {base} AND c.tsv @@ to_tsquery('simple', :q) ORDER BY s DESC LIMIT :lim"),
                {**params, **term_params, "q": tsq},
            ).mappings().all()
            kw_rows += [(origin, r) for r in rows]
        if query_vec:
            vec = "[" + ",".join(f"{x:.7f}" for x in query_vec) + "]"
            rows = session.execute(
                text(f"SELECT c.id, c.text, c.page, c.section_path, d.id AS doc_id, d.title, d.doc_class, (c.embedding <=> CAST(:v AS vector)) AS dist {base} AND c.embedding IS NOT NULL AND vector_dims(c.embedding) = :dim ORDER BY dist LIMIT :lim"),
                {**params, "v": vec, "dim": len(query_vec)},
            ).mappings().all()
            vec_rows += [(origin, r) for r in rows]

    scored: dict[tuple[str, int], dict[str, Any]] = {}

    def item(origin: str, r: Any) -> dict[str, Any]:
        return scored.setdefault((origin, r["id"]), {"origin": origin, "chunk_id": r["id"], "document_id": r["doc_id"], "title": r["title"], "doc_class": r["doc_class"], "page": r["page"], "section_path": r["section_path"], "text": r["text"], "score": 0.0, "signals": {}})

    for rank, (origin, r) in enumerate(sorted(kw_rows, key=lambda x: float(x[1]["s"]), reverse=True), start=1):
        it = item(origin, r)
        it["score"] += 1.0 / (rrf_k + rank)
        it["signals"]["keyword_rank"] = rank
        it["signals"]["keyword_score"] = round(float(r["s"]), 4)
    for rank, (origin, r) in enumerate(sorted(vec_rows, key=lambda x: float(x[1]["dist"])), start=1):
        it = item(origin, r)
        it["score"] += 1.0 / (rrf_k + rank)
        it["signals"]["vector_rank"] = rank
        it["signals"]["cosine_distance"] = round(float(r["dist"]), 4)
    return sorted(scored.values(), key=lambda x: x["score"], reverse=True)[:k]
