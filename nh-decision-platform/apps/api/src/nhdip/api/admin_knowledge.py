"""관리자 — 질문하기 지식 색인 (요구사항 NFR-KB-03/04 · 설계 §21.8).

- `GET  /admin/knowledge/status`                 컬렉션별 청크 · 임베딩 · 미분류, 대조 필요 건수, 임베딩 모델 · 그래프 상태
- `GET  /admin/knowledge/collections`            컬렉션 정의(담당 · 공유 팀 이름 포함)
- `PUT  /admin/knowledge/collections/{code}`     담당 · 공유 팀, 화면 리소스, 공개 범위, 포함 규칙, 가산점, 사용 여부 수정
- `POST /admin/knowledge/reindex`                전체 재색인(임베딩은 워커가 이어서 채운다)
- `POST /admin/knowledge/calibrate`              임베딩 모델별 코사인 거리 기준 측정 · 적용(설계 §21.15)
- `GET  /admin/knowledge/quality`                질문하기 품질 지표 — 답 못 한 비율 · 피드백 · 자주 답 못 한 질문(설계 §21.16)
- `POST /admin/knowledge/search`                 검색 진단 — 지정 사용자 관점으로 같은 검색을 돌려 채널별 후보 · 거부 사유 · 소요를 본다(읽기 전용)
담당 · 공유 팀 · 공개 범위는 검색 때 읽으므로 바꾸면 다음 질문부터 적용된다. 포함 규칙을 바꾸면 워커 대조(1분)가 다시 색인한다.
"""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from nhdip.db import get_session
from nhdip.events import audit
from nhdip.graph.neo4j_client import health as graph_health
from nhdip.knowledge.access import AUDIENCES, resolve_scope, setting_dict
from nhdip.knowledge.calibration import apply_calibration, calibrate, calibrated_model
from nhdip.knowledge import elastic
from nhdip.knowledge.defaults import SEARCH_DEFAULT
from nhdip.knowledge.maintenance import embedding_agent, reconcile, status as kb_status
from nhdip.knowledge.search import retrieve, search_mode
from nhdip.knowledge.quality import quality as kb_quality
from nhdip.llm import LlmUnavailable, resolve
from nhdip.models import AppUser, KbCollection, OrgUnit
from nhdip.privacy import audit_text

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
    scfg = setting_dict(session, "knowledge.search", SEARCH_DEFAULT)
    graph = graph_health()
    return {
        "totals": st["totals"], "stale": st["stale"], "state": st["state"], "documentsByClass": docs, "embedding": emb, "graph": graph,
        "distance": {"threshold": float(scfg["max_cosine_distance"]), "calibratedModel": calibrated_model(session), "fusion": scfg.get("fusion", "convex")},
        "searchBackend": _search_backend(session, search_mode(scfg), bool(graph.get("ok"))),
        "unassigned": st["collections"].get("analysis.unassigned", {}).get("chunks", 0), "collections": sorted(items, key=lambda x: (x["sort"], x["code"])),
        "orphanChunks": int(session.execute(text("SELECT count(*) FROM app.kb_chunk c WHERE c.collection_code NOT IN (SELECT code FROM cfg.kb_collection)")).scalar() or 0),
    }


def _search_backend(session: Session, setting: str, graph_ok: bool = False) -> dict[str, Any]:
    """AI 어시스턴트 검색 엔진(3-way) — 설정(auto | es | pg) · ES 연결 · 색인별 동기화 상태 · 실제로 쓸 엔진.
    ES 를 쓰지 않으면 연결 확인(네트워크)을 하지 않는다. `engines` 는 지금 질문이 들어오면 키워드 · 의미 후보를 어디서 찾는지(분석 결과 · 문서)."""
    out: dict[str, Any] = {"setting": setting, "configured": elastic.configured()}
    engines = {"analysis": "pg", "documents": "pg", "graph": "neo4j" if graph_ok else "postgres"}
    if elastic.configured():
        try:
            out["es"] = elastic.status(session)
            if out["es"].get("up"):
                for part, which in (("analysis", "kb"), ("documents", "doc")):
                    st, _why = elastic.readiness(session, which, setting)
                    engines[part] = "es" if st is not None else "pg"
        except Exception as exc:  # noqa: BLE001 — 상태 화면이 ES 때문에 깨지지 않게
            session.rollback()
            out["es"] = {"configured": True, "up": False, "error": f"{type(exc).__name__}: {str(exc)[:120]}"}
    out["engines"] = engines
    return out


# ── Elasticsearch 연결 설정 (Phase K · ES-01~03 · Q154) ─────────────────────
class EsConnIn(BaseModel):
    url: str = Field(min_length=1, max_length=300)
    user: str = Field(default="", max_length=80)
    # 비우면 지금 저장된(또는 환경변수) 비밀번호를 그대로 쓴다 — 화면에는 가린 값만 보여 주므로
    password: str | None = Field(default=None, max_length=200)
    force: bool = False  # 시험이 실패해도 저장(ES 를 나중에 띄울 때)


def _es_url(url: str) -> str:
    from .admin_core import _check_base_url

    try:
        return _check_base_url(url) or ""
    except HTTPException as exc:
        raise HTTPException(exc.status_code, str(exc.detail).replace("LLM", "Elasticsearch")) from exc


def _mask_pw(p: str) -> str:
    """비밀번호는 앞뒤 글자도 보이지 않게 — 저장 여부만."""
    return "••••••••" if p else ""


def _es_conn_view(session: Session) -> dict[str, Any]:
    from nhdip.config import get_settings
    from nhdip.models import Secret
    from nhdip.security import decrypt_secret

    st = get_settings()
    row = session.get(Secret, elastic.SECRET_KEY)
    meta = row.meta if row is not None and isinstance(row.meta, dict) else {}
    return {
        "source": "db" if row is not None and meta.get("url") else "env",
        "saved": {"url": elastic.safe_url(str(meta.get("url") or "")), "user": str(meta.get("user") or ""), "password": _mask_pw(decrypt_secret(row.secret_enc)) if row is not None else "", "updatedBy": row.updated_by if row else None, "updatedAt": row.updated_at.isoformat() if row and row.updated_at else None} if row is not None else None,
        "env": {"url": elastic.safe_url(st.es_url), "user": st.es_user, "passwordSet": bool(st.es_password)},
    }


def _es_password_for(session: Session, body: EsConnIn) -> str:
    """입력 비밀번호가 없으면 저장값 → 환경변수 순으로."""
    if body.password:
        return body.password
    from nhdip.config import get_settings
    from nhdip.models import Secret
    from nhdip.security import decrypt_secret

    row = session.get(Secret, elastic.SECRET_KEY)
    return decrypt_secret(row.secret_enc) if row is not None and row.secret_enc else get_settings().es_password


@router.get("/es-connection")
def es_connection(session: Session = Depends(get_session)):
    """지금 쓰는 Elasticsearch 연결 — 출처(db = 관리자 입력 · env = 환경변수) · 주소 · 계정 · 가린 비밀번호."""
    return _es_conn_view(session)


@router.post("/es-connection/test")
def es_connection_test(body: EsConnIn, session: Session = Depends(get_session)):
    """저장하지 않고 연결 시험 — 인증 실패 · 연결 불가 · 거절을 나눠 알려 준다."""
    return elastic.probe(_es_url(body.url), body.user.strip(), _es_password_for(session, body))


@router.put("/es-connection")
def es_connection_save(body: EsConnIn, request: Request, session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    """연결 값 저장 — 시험을 통과해야 저장(force 면 실패해도). 비밀번호는 암호화, 감사 기록에는 가린 값만."""
    from nhdip.models import Secret
    from nhdip.security import encrypt_secret

    url = _es_url(body.url)
    password = _es_password_for(session, body)
    result = elastic.probe(url, body.user.strip(), password)
    if not result["ok"] and not body.force:
        raise HTTPException(422, f"연결 시험 실패 — {result['message']}")
    row = session.get(Secret, elastic.SECRET_KEY)
    meta = {"url": url, "user": body.user.strip()}
    if row is None:
        session.add(Secret(key=elastic.SECRET_KEY, meta=meta, secret_enc=encrypt_secret(password), updated_by=admin.emp_no))
    else:
        row.meta, row.secret_enc, row.updated_by = meta, encrypt_secret(password), admin.emp_no
    audit(session, admin.emp_no, "admin.es_connection.save", "secret", elastic.SECRET_KEY, {"url": elastic.safe_url(url), "user": meta["user"], "password": _mask_pw(password), "test": result.get("errorKind") or "ok", "forced": bool(body.force and not result["ok"])}, client_ip(request))
    session.commit()
    elastic.invalidate_override()
    return {**_es_conn_view(session), "test": result}


@router.delete("/es-connection")
def es_connection_clear(request: Request, session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    """관리자 입력 값을 지우고 환경변수(ES_URL · ES_USER · ES_PASSWORD)로 되돌린다."""
    from nhdip.models import Secret

    row = session.get(Secret, elastic.SECRET_KEY)
    if row is not None:
        session.delete(row)
        audit(session, admin.emp_no, "admin.es_connection.clear", "secret", elastic.SECRET_KEY, None, client_ip(request))
        session.commit()
    elastic.invalidate_override()
    return _es_conn_view(session)


@router.post("/es-reconnect")
def es_reconnect(session: Session = Depends(get_session)):
    """차단기 · 클라이언트를 비우고 바로 다시 연결해 본다(비밀번호를 맞춘 뒤 30초를 기다리지 않게). 워커는 다음 주기에."""
    elastic.invalidate_override()
    return elastic.status(session) if elastic.configured() else {"configured": False, "up": False}


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


@router.get("/quality")
def quality(days: int = Query(7, ge=1, le=90), session: Session = Depends(get_session)):
    """질문하기 품질 지표 — 답 못 한 비율 · 피드백 · 동작 방식, 자주 답을 못 한 질문 · 도움이 안 됐다는 질문(감사 기록에서 집계, 질문은 개인정보 가림)."""
    return kb_quality(session, days)


class CalibrateIn(BaseModel):
    apply: bool = False


@router.post("/calibrate")
def calibrate_distance(body: CalibrateIn, request: Request, session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    """현재 임베딩 모델 기준 코사인 거리 임계값 보정(설계 §21.15). apply=false 는 측정만(읽기 전용), true 는 확신할 수 있을 때만 검색 설정에 반영."""
    try:
        rep = calibrate(session)
    except LlmUnavailable as exc:
        raise HTTPException(409, f"임베딩 모델을 쓸 수 없습니다 — {str(exc)[:160]}") from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    if body.apply:
        try:
            apply_calibration(session, rep, admin.emp_no)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        rep["applied"] = True
        audit(session, admin.emp_no, "admin.knowledge.calibrate", "kb_chunk", rep["model"], {"suggested": rep["suggested"], "previous": rep["current"]}, client_ip(request))
    session.commit()
    return rep


@router.post("/search")
def search_diagnostic(body: SearchIn, request: Request, session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    target = admin
    if body.as_emp_no:
        target = session.get(AppUser, body.as_emp_no)
        if target is None:
            raise HTTPException(404, "사용자 없음")
    scope = resolve_scope(session, access_context(session, target, body.screen))
    ret = retrieve(session, scope, body.query.strip(), user=target, explain=True)
    audit(session, admin.emp_no, "admin.knowledge.search", "assist", target.emp_no, {"query": audit_text(session, body.query), "analysis": len(ret.analysis), "documents": len(ret.documents)}, client_ip(request))
    session.commit()
    return {
        "asEmpNo": target.emp_no, "scope": scope.public(), "query": ret.query, "concepts": ret.concepts, "expanded": ret.expanded,
        "analysis": [{**_analysis_view(h), "parts": h.get("parts")} for h in ret.analysis], "documents": [_evidence_view(h) for h in ret.documents],
        "rejected": ret.rejected[:30], "diagnostics": ret.diagnostics,
    }
