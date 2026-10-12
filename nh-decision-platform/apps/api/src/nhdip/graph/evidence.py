"""근거 선별 (작업 3.6.1 ~ 3.6.3 · 8.4.2) — 하이브리드 검색 후보를 관련성 게이팅 → 우선순위 점수 → 3범주 균형으로 고른다.

게이팅 6단계(거부 사유를 남긴다)
  1 권한   : 부서한정 문서는 소유 부서(설정 docs.owner_orgs · 상위 조직 포함) 사용자 · 관리자만
  2 부문   : 요청 부문(예: 여신)과 문서 적용 부문(domainLabels)이 겹쳐야 함 — '전행' 문서는 모든 부문
  3 시점   : 기준일 이후 발행 문서 · 최대 경과일을 넘긴 문서 제외
  4 문서유형: 요청 분류(doc_classes) 밖 제외
  5 의미임계: 키워드 질의어 커버리지 · 벡터 거리 기준
  6 개념경로: 그래프 필터가 있으면 개념과 연결된 문서만(그래프 장애 시 생략)
우선순위 = 공식성 0.40 + 시점 0.25 + 의미 0.20 + 개념경로 0.15 (가중치 · 기준은 설정 evidence.policy)
범주 = 외부 정책(gov_policy) · 내부 경영방향(mgmt_decision · model_method) — 범주별 최소 1건을 먼저 채우고, 없는 범주는 '부재'로 명시
"""
from __future__ import annotations

import math
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from nhdip.models import AppUser, Setting, source

DEFAULT_POLICY: dict[str, Any] = {
    "weights": {"official": 0.40, "recency": 0.25, "semantic": 0.20, "path": 0.15},
    "recency_half_life_days": 365,
    "max_age_days": 1825,
    "min_keyword_coverage": 1,
    "max_cosine_distance": 0.65,
    "category_of": {"gov_policy": "external_policy", "mgmt_decision": "internal_direction", "model_method": "internal_direction", "branch_ref": "internal_direction", "reference": "external_policy", "term": "internal_direction"},
    "require_categories": ["external_policy", "internal_direction"],
}
STAGES = ("permission", "domain", "time", "doc_type", "semantic", "concept_path")


def policy(session: Session) -> dict[str, Any]:
    s = session.get(Setting, "evidence.policy")
    return {**DEFAULT_POLICY, **(s.value if s and isinstance(s.value, dict) else {})}


def _user_orgs(session: Session, user: AppUser | None) -> set[str] | None:
    if user is None or user.role == "admin":
        return None  # 제한 없음 (시스템 실행 · 관리자)
    from nhdip.orgs import org_chain

    return {o.code for o in org_chain(session, user.org_code)}


def doc_visible(session: Session, user: AppUser | None, doc_code: str, meta: dict[str, Any] | None) -> tuple[bool, str | None]:
    """문서 등급 검증 — 목록 · 검색 · 원본 열람 3지점 공통 (8.4.2)."""
    access = (meta or {}).get("accessClass", "internal")
    if access != "dept_only":
        return True, None
    orgs = _user_orgs(session, user)
    if orgs is None:
        return True, None
    owners_s = session.get(Setting, "docs.owner_orgs")
    owners = set(((owners_s.value if owners_s else {}) or {}).get(doc_code, []))
    if owners & orgs:
        return True, None
    return False, "부서한정 문서 — 소유 부서 사용자만 열람"


def _doc_rows(session: Session, hits: list[dict[str, Any]]) -> dict[tuple[str, int], Any]:
    out: dict[tuple[str, int], Any] = {}
    for origin in {h["origin"] for h in hits}:
        t = source(origin)
        ids = list({h["document_id"] for h in hits if h["origin"] == origin})
        for d in session.execute(select(t.document).where(t.document.id.in_(ids))).scalars():
            out[(origin, d.id)] = d
    return out


def _published(d: Any) -> date | None:
    if d.published_at:
        return d.published_at
    v = (d.meta or {}).get("effectiveDate")
    try:
        return date.fromisoformat(v[:10]) if v else None
    except ValueError:
        return None


def rank_evidence(
    session: Session,
    hits: list[dict[str, Any]],
    *,
    k: int = 5,
    user: AppUser | None = None,
    as_of: str | None = None,
    domain: str | None = None,
    doc_classes: list[str] | None = None,
    doc_filter: dict[str, list[int]] | None = None,
    query_terms: int = 0,
) -> dict[str, Any]:
    pol = policy(session)
    docs = _doc_rows(session, hits)
    ref = date.fromisoformat(as_of[:10]) if as_of else date.today()
    accepted, rejected = [], []
    for h in hits:
        d = docs.get((h["origin"], h["document_id"]))
        meta = (d.meta if d else {}) or {}
        reason = None
        ok, why = doc_visible(session, user, d.doc_code if d else "", meta)
        if not ok:
            reason = ("permission", why)
        elif domain and meta.get("domainLabels") and domain not in meta["domainLabels"] and "전행" not in meta["domainLabels"]:
            reason = ("domain", f"적용 부문 {', '.join(meta['domainLabels'])} — 요청 부문 '{domain}' 아님")
        else:
            pub = _published(d) if d else None
            if pub and pub > ref:
                reason = ("time", f"기준일({ref}) 이후 발행({pub})")
            elif pub and (ref - pub).days > int(pol["max_age_days"]):
                reason = ("time", f"발행 후 {(ref - pub).days}일 경과(최대 {pol['max_age_days']}일)")
            elif doc_classes and h["doc_class"] not in doc_classes:
                reason = ("doc_type", f"문서 분류 {h['doc_class']} — 요청 분류 밖")
            else:
                sig = h.get("signals", {})
                kw = sig.get("keyword_score")
                dist = sig.get("cosine_distance")
                kw_ok = kw is not None and float(kw) >= float(pol["min_keyword_coverage"])
                vec_ok = dist is not None and float(dist) <= float(pol["max_cosine_distance"])
                graph_ok = bool(sig.get("graph"))  # 그래프 채널로 들어온 후보(질의 개념과 연결된 문서 — 하이브리드 검색 §21.6)
                if not (kw_ok or vec_ok or graph_ok):
                    reason = ("semantic", f"의미 기준 미달(키워드 {kw} · 거리 {dist})")
                elif doc_filter is not None and h["document_id"] not in (doc_filter.get(h["origin"]) or []):
                    reason = ("concept_path", "질의 개념과 그래프로 연결되지 않은 문서")
        if reason:
            rejected.append({"chunk_id": h["chunk_id"], "origin": h["origin"], "title": h["title"], "stage": reason[0], "reason": reason[1]})
            continue
        # 우선순위 점수
        w = pol["weights"]
        official = 1.0 if meta.get("isOfficial") else 0.5
        pub = _published(d) if d else None
        recency = 0.5 if pub is None else math.exp(-math.log(2) * max(0, (ref - pub).days) / float(pol["recency_half_life_days"]))
        sig = h.get("signals", {})
        cover = float(sig.get("keyword_score") or 0) / max(1, query_terms) if query_terms else 0.0
        vec = 1.0 - float(sig["cosine_distance"]) if sig.get("cosine_distance") is not None else 0.0
        semantic = min(1.0, max(cover, vec))
        if sig.get("graph"):
            semantic = max(semantic, 0.6)
        path = 1.0 if doc_filter is not None or sig.get("graph") else 0.5
        prio = w["official"] * official + w["recency"] * recency + w["semantic"] * semantic + w["path"] * path
        cat = pol["category_of"].get(h["doc_class"], "external_policy")
        accepted.append({**h, "category": cat, "priority": round(prio, 4), "priorityParts": {"official": official, "recency": round(recency, 3), "semantic": round(semantic, 3), "path": path}, "sectionPath": h.get("section_path"), "issuer": d.issuer if d else None, "docCode": d.doc_code if d else None})
    accepted.sort(key=lambda x: (x["priority"], x["score"]), reverse=True)
    # 3범주 — 범주별 최소 1건을 먼저 채운다
    picked, seen = [], set()
    for cat in pol["require_categories"]:
        first = next((x for x in accepted if x["category"] == cat), None)
        if first is not None and len(picked) < k:
            picked.append(first)
            seen.add((first["origin"], first["chunk_id"]))
    for x in accepted:
        if len(picked) >= k:
            break
        if (x["origin"], x["chunk_id"]) not in seen:
            picked.append(x)
            seen.add((x["origin"], x["chunk_id"]))
    picked.sort(key=lambda x: (x["priority"], x["score"]), reverse=True)
    present = {x["category"] for x in picked}
    return {
        "hits": picked,
        "rejected": rejected,
        "categories": {c: sum(1 for x in picked if x["category"] == c) for c in pol["require_categories"]},
        "missingCategories": [c for c in pol["require_categories"] if c not in present],
    }
