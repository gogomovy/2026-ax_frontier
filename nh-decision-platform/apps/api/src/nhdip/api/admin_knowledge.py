"""관리자 — 질문하기 지식 색인 (요구사항 NFR-KB-03/04 · 설계 §21.8).

- `GET  /admin/knowledge/status`                 컬렉션별 청크 · 임베딩 · 미분류, 대조 필요 건수, 임베딩 모델 · 그래프 상태
- `GET  /admin/knowledge/collections`            컬렉션 정의(담당 · 공유 팀 이름 포함)
- `PUT  /admin/knowledge/collections/{code}`     담당 · 공유 팀, 화면 리소스, 공개 범위, 포함 규칙, 가산점, 사용 여부 수정
- `POST /admin/knowledge/reindex`                전체 재색인(임베딩은 워커가 이어서 채운다)
- `POST /admin/knowledge/search`                 검색 진단 — 지정 사용자 관점으로 같은 검색을 돌려 채널별 후보 · 거부 사유 · 소요를 본다(읽기 전용)
담당 · 공유 팀 · 공개 범위는 검색 때 읽으므로 바꾸면 다음 질문부터 적용된다. 포함 규칙을 바꾸면 워커 대조(1분)가 다시 색인한다.
"""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from nhdip.db import get_session
from nhdip.events import audit
from nhdip.graph.neo4j_client import health as graph_health
from nhdip.knowledge.access import AUDIENCES, resolve_scope
from nhdip.knowledge.maintenance import embedding_agent, reconcile, status as kb_status
from nhdip.knowledge.search import retrieve
from nhdip.llm import LlmUnavailable, resolve
from nhdip.models import AppUser, KbCollection, OrgUnit

from .assist import _analysis_view, _evidence_view, access_context
from .deps import client_ip, require_admin

router = APIRouter(prefix="/admin/knowledge", tags=["admin-knowledge"], dependencies=[Depends(require_admin)])

SOURCE_KEYS = ("doc_classes", "artifact_keys", "artifact_prefixes", "spaces", "personas", "screens")


class CollectionPatch(BaseModel):
    label: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)
    owner_orgs: list[str] | None = Field(None, max_length=50)
    shared_orgs: list[str] | None = Field(None, max_length=50)
    required_resources: list[str] | None = Field(None, max_length=50)
    audience: Literal["all", "restricted", "owner_only"] | None = None
    sources: dict[str, list[str]] | None = None
    boost: float | None = Field(None, ge=-1.0, le=1.0)
    enabled: bool | None = None


class SearchIn(BaseModel):
    query: str = Field(..., min_length=2, max_length=500)
    as_emp_no: str | None = Field(None, alias="asEmpNo", max_length=8)
    screen: str | None = Field(None, max_length=200)


def _org_names(session: Session) -> dict[str, str]:
    return {c: n for c, n in session.execute(select(OrgUnit.code, OrgUnit.name)).all()}


def _view(c: KbCollection, names: dict[str, str]) -> dict[str, Any]:
    return {
        "code": c.code, "label": c.label, "description": c.description, "kind": c.kind, "audience": c.audience, "enabled": c.enabled, "boost": c.boost, "sort": c.sort,
        "ownerOrgs": [{"code": o, "name": names.get(o, o)} for o in (c.owner_orgs or [])], "sharedOrgs": [{"code": o, "name": names.get(o, o)} for o in (c.shared_orgs or [])],
        "requiredResources": list(c.required_resources or []), "sources": c.sources or {}, "updatedBy": c.updated_by, "updatedAt": c.updated_at.isoformat() if c.updated_at else None,
    }


@router.get("/collections")
def collections(session: Session = Depends(get_session)):
    names = _org_names(session)
    return {"items": [_view(c, names) for c in session.execute(select(KbCollection).order_by(KbCollection.sort, KbCollection.code)).scalars()]}


@router.get("/status")
def status(session: Session = Depends(get_session)):
    st = kb_status(session)
    docs: dict[str, int] = {}
    for origin in ("bank", "ext"):
        for cls, n in session.execute(text(f"SELECT doc_class, count(*) FROM {origin}.document WHERE is_current GROUP BY doc_class")).all():
            docs[cls] = docs.get(cls, 0) + int(n)
    try:
        emb = {"agent": embedding_agent(session), "model": resolve(session, embedding_agent(session)).model, "on": True}
    except LlmUnavailable as exc:
        emb = {"agent": embedding_agent(session), "model": None, "on": False, "reason": str(exc)[:160]}
    names = _org_names(session)
    cols = {c.code: c for c in session.execute(select(KbCollection)).scalars()}
    items = []
    for code, c in cols.items():
        v = _view(c, names)
        v["stats"] = st["collections"].get(code, {"chunks": 0, "embedded": 0, "sources": 0, "lastIndexedAt": None})
        if c.kind == "document":
            classes = [x for x in (c.sources or {}).get("doc_classes", []) if x != "*"]
            v["stats"]["documents"] = sum(docs.get(x, 0) for x in classes)
        items.append(v)
    return {
        "totals": st["totals"], "stale": st["stale"], "state": st["state"], "documentsByClass": docs, "embedding": emb, "graph": graph_health(),
        "unassigned": st["collections"].get("analysis.unassigned", {}).get("chunks", 0), "collections": sorted(items, key=lambda x: (x["sort"], x["code"])),
        "orphanChunks": int(session.execute(text("SELECT count(*) FROM app.kb_chunk c WHERE c.collection_code NOT IN (SELECT code FROM cfg.kb_collection)")).scalar() or 0),
    }


def _clean_orgs(session: Session, codes: list[str], field: str) -> list[str]:
    out = list(dict.fromkeys(c.strip() for c in codes if c and c.strip()))
    bad = [c for c in out if session.get(OrgUnit, c) is None]
    if bad:
        raise HTTPException(422, f"{field}: 없는 조직 코드 {', '.join(bad[:5])}")
    return out


@router.put("/collections/{code}")
def update_collection(code: str, body: CollectionPatch, request: Request, session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    c = session.get(KbCollection, code)
    if c is None:
        raise HTTPException(404, "컬렉션 없음")
    before = _view(c, {})
    patch = body.model_dump(exclude_unset=True)
    if "owner_orgs" in patch:
        patch["owner_orgs"] = _clean_orgs(session, patch["owner_orgs"] or [], "담당 팀")
    if "shared_orgs" in patch:
        patch["shared_orgs"] = _clean_orgs(session, patch["shared_orgs"] or [], "공유 팀")
    if "required_resources" in patch:
        patch["required_resources"] = [r.strip() for r in (patch["required_resources"] or []) if r.strip()][:50]
    if "sources" in patch:
        src = patch["sources"] or {}
        bad = [k for k in src if k not in SOURCE_KEYS]
        if bad:
            raise HTTPException(422, f"포함 규칙 키는 {', '.join(SOURCE_KEYS)} 만 쓸 수 있습니다")
        patch["sources"] = {k: [str(x)[:100] for x in v][:100] for k, v in src.items()}
    if patch.get("audience") and patch["audience"] not in AUDIENCES:
        raise HTTPException(422, "공개 범위는 all · restricted · owner_only")
    # 빈 값(null) — 설명은 빈 글로, 필수 값(이름 · 켜짐 · 가중치 · 공개 범위)은 422 (NOT NULL 열이라 그대로 넣으면 500)
    if "description" in patch and patch["description"] is None:
        patch["description"] = ""
    nulls = [k for k, v in patch.items() if v is None]
    if nulls:
        raise HTTPException(422, f"비울 수 없는 항목: {', '.join(nulls)}")
    for k, v in patch.items():
        setattr(c, k, v)
    c.updated_by = admin.emp_no
    audit(session, admin.emp_no, "admin.knowledge.collection.update", "kb_collection", code, {"before": before, "patch": patch}, client_ip(request))
    session.commit()
    return {**_view(c, _org_names(session)), "note": "팀 · 공개 범위는 다음 질문부터, 포함 규칙은 워커 대조(1분) 뒤 색인에 반영됩니다."}


@router.post("/reindex")
def reindex(request: Request, session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    stats = reconcile(session, full=True)
    audit(session, admin.emp_no, "admin.knowledge.reindex", "kb_chunk", None, stats.as_dict(), client_ip(request))
    session.commit()
    return {**stats.as_dict(), "note": "텍스트 · 개념 색인을 마쳤습니다. 임베딩은 워커가 60초 주기로 이어서 채웁니다."}


@router.post("/search")
def search_diagnostic(body: SearchIn, request: Request, session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    target = admin
    if body.as_emp_no:
        target = session.get(AppUser, body.as_emp_no)
        if target is None:
            raise HTTPException(404, "사용자 없음")
    scope = resolve_scope(session, access_context(session, target, body.screen))
    ret = retrieve(session, scope, body.query.strip(), user=target, explain=True)
    audit(session, admin.emp_no, "admin.knowledge.search", "assist", target.emp_no, {"query": body.query[:200], "analysis": len(ret.analysis), "documents": len(ret.documents)}, client_ip(request))
    session.commit()
    return {
        "asEmpNo": target.emp_no, "scope": scope.public(), "query": ret.query, "concepts": ret.concepts, "expanded": ret.expanded,
        "analysis": [{**_analysis_view(h), "parts": h.get("parts")} for h in ret.analysis], "documents": [_evidence_view(h) for h in ret.documents],
        "rejected": ret.rejected[:30], "diagnostics": ret.diagnostics,
    }
