"""분석 에이전트 API (Phase C · DAG-01~09 · 설계 §20.5).

업무 사용자(리소스 `analysis_builder` + 그 분석 공간 열람 리소스):
- `GET /analysis-agents/catalog?space=` 허용 목록 · 만들 수 있는 공간
- `POST /analysis-agents/refine` 글 → 명세 초안(정제 에이전트) · 검증
- `POST /analysis-agents/validate` 고친 명세 다시 검증
- `POST /analysis-agents/preview` 명세로 계산 · 보고서 미리보기(되돌림)
- `POST /analysis-agents` 승인 요청(새 분석 또는 agent_code 의 새 버전) · `GET /analysis-agents/mine` 내 분석
관리자:
- `GET /admin/analysis-agents` · `GET /admin/analysis-agents/{code}` · `POST .../versions/{v}/approve|reject` · `POST .../{code}/pause|resume|retire`
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from nhdip.analysis_agents.lifecycle import LifecycleError, approve, preview, reject, request, set_state
from nhdip.analysis_agents.refine import refine
from nhdip.analysis_agents.spec import catalog, validate_spec
from nhdip.analysis_agents.team import team_of
from nhdip.analysis_registry import space as get_space, spaces
from nhdip.db import get_session
from nhdip.models import AnalysisAgent, AnalysisAgentVersion, AppUser, Prompt, Setting, Workflow, WorkflowRun

from .deps import require_admin, require_resource, user_resources

router = APIRouter(prefix="/analysis-agents", tags=["analysis-agents"])
admin_router = APIRouter(prefix="/admin/analysis-agents", tags=["admin"], dependencies=[Depends(require_admin)])

STATUS_LABEL = {"draft": "작성 중", "pending": "승인 대기", "active": "동작 중", "paused": "일시 중지", "retired": "폐기", "rejected": "반려"}
VSTATUS_LABEL = {"pending": "승인 대기", "approved": "승인", "rejected": "반려", "superseded": "이전 버전"}


def _iso(v):
    return v.isoformat() if v else None


def _agent_name(actor: str | None) -> str | None:
    """사람이 아닌 요청자(에이전트 제안 · §40 STW)의 표시 이름."""
    return "분석 제안 에이전트" if (actor or "").startswith("agent:") else None


def _builder_space(session: Session, user: AppUser, key: str) -> dict[str, Any]:
    sp = get_space(session, key)
    if sp is None or not sp.get("builder"):
        raise HTTPException(422, "분석을 만들 수 없는 공간입니다")
    allowed = user_resources(session, user)
    res = sp.get("tabsResource") or sp.get("resource")
    if allowed is not None and res not in allowed:
        raise HTTPException(403, f"이 분석 공간에 대한 권한이 없습니다 ({res})")
    return sp


def _builder_spaces(session: Session, user: AppUser) -> list[dict[str, Any]]:
    allowed = user_resources(session, user)
    return [{"key": k, "label": sp.get("label"), "path": sp.get("path") or f"/analysis/{k}"} for k, sp in spaces(session).items()
            if sp.get("builder") and (allowed is None or (sp.get("tabsResource") or sp.get("resource")) in allowed)]


class RefineIn(BaseModel):
    space: str
    text: str = Field(min_length=10, max_length=6000)
    datasets: list[str] = []
    doc_classes: list[str] = []


class SpecIn(BaseModel):
    space: str
    spec: dict[str, Any]


class RequestIn(BaseModel):
    space: str
    text: str = Field(default="", max_length=8000)
    spec: dict[str, Any]
    agent_code: str | None = None


@router.get("/catalog")
def get_catalog(space: str | None = None, session: Session = Depends(get_session), user: AppUser = Depends(require_resource("analysis_builder"))):
    sps = _builder_spaces(session, user)
    key = space or (sps[0]["key"] if sps else None)
    if key is None:
        raise HTTPException(403, "분석을 만들 수 있는 공간이 없습니다 — 관리자에게 화면 권한을 요청하세요")
    _builder_space(session, user, key)
    team = team_of(session, user.org_code)
    return {"spaces": sps, **catalog(session, key, team_orgs=team.orgs, team_name=team.name)}


@router.post("/refine")
def do_refine(body: RefineIn, session: Session = Depends(get_session), user: AppUser = Depends(require_resource("analysis_builder"))):
    _builder_space(session, user, body.space)
    team = team_of(session, user.org_code)
    spec, validation, meta = refine(session, body.text, body.space, {"datasets": body.datasets[:5], "doc_classes": body.doc_classes[:5], "team_orgs": sorted(team.orgs), "team_name": team.name})
    session.commit()  # LLM 호출 기록
    return {"spec": spec, "validation": validation, "meta": meta}


@router.post("/validate")
def do_validate(body: SpecIn, session: Session = Depends(get_session), user: AppUser = Depends(require_resource("analysis_builder"))):
    _builder_space(session, user, body.space)
    spec, validation = validate_spec(session, body.spec, body.space)
    return {"spec": spec, "validation": validation}


@router.post("/preview")
def do_preview(body: SpecIn, session: Session = Depends(get_session), user: AppUser = Depends(require_resource("analysis_builder"))):
    _builder_space(session, user, body.space)
    spec, validation = validate_spec(session, body.spec, body.space)
    if not validation["ok"]:
        return {"spec": spec, "validation": validation, "report": None, "nodes": []}
    pv = preview(session, spec, body.space, user.emp_no)
    return {"spec": spec, "validation": validation, **pv}


@router.post("", status_code=201)
def do_request(body: RequestIn, session: Session = Depends(get_session), user: AppUser = Depends(require_resource("analysis_builder"))):
    _builder_space(session, user, body.space)
    if body.agent_code:
        a = session.get(AnalysisAgent, body.agent_code)
        if a is None or (a.requested_by != user.emp_no and user.role != "admin"):
            raise HTTPException(404, "분석 에이전트 없음")
    spec, validation = validate_spec(session, body.spec, body.space)
    pv = preview(session, spec, body.space, user.emp_no) if validation["ok"] else None
    try:
        v = request(session, space=body.space, text=body.text, spec=spec, validation=validation, preview=pv, actor=user.emp_no, agent_code=body.agent_code)
    except LifecycleError as exc:
        session.rollback()
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return {"agent": v.agent_code, "version": v.version, "status": v.status, "validation": validation}


def _agent_json(session: Session, a: AnalysisAgent, names: dict[str, str] | None = None, full: bool = False) -> dict[str, Any]:
    names = names or {}
    vs = session.execute(select(AnalysisAgentVersion).where(AnalysisAgentVersion.agent_code == a.code).order_by(AnalysisAgentVersion.version.desc())).scalars().all()
    run = session.execute(select(WorkflowRun).where(WorkflowRun.workflow_code == a.workflow_code).order_by(WorkflowRun.started_at.desc()).limit(1)).scalar() if a.workflow_code else None
    sp = get_space(session, a.space) or {}
    out: dict[str, Any] = {
        "code": a.code, "space": a.space, "spaceLabel": sp.get("label") or a.space, "title": a.title, "status": a.status, "statusLabel": STATUS_LABEL.get(a.status, a.status),
        "version": a.version, "tabKey": a.tab_key, "workflow": a.workflow_code, "requestedBy": a.requested_by, "requestedByName": names.get(a.requested_by or "") or _agent_name(a.requested_by),
        "approvedBy": a.approved_by, "approvedAt": _iso(a.approved_at), "updatedAt": _iso(a.updated_at), "createdAt": _iso(a.created_at),
        "href": (f"{sp.get('path')}/{a.tab_key}" if sp.get("path") else f"/analysis/{a.space}/{a.tab_key}") if a.status in ("active", "paused") else None,
        "lastRun": {"id": run.id, "status": run.status, "startedAt": _iso(run.started_at), "finishedAt": _iso(run.finished_at)} if run else None,
        "pendingVersion": next((v.version for v in vs if v.status == "pending"), None),
        "versions": [{
            "version": v.version, "status": v.status, "statusLabel": VSTATUS_LABEL.get(v.status, v.status), "requestedBy": v.requested_by, "requestedByName": names.get(v.requested_by or "") or _agent_name(v.requested_by),
            "reviewedBy": v.reviewed_by, "reviewedByName": names.get(v.reviewed_by or ""), "reviewedAt": _iso(v.reviewed_at), "reviewNote": v.review_note, "createdAt": _iso(v.created_at),
            "counts": (v.validation or {}).get("counts"), "issues": len((v.validation or {}).get("issues") or []),
            **({"sourceText": v.source_text, "spec": v.spec, "validation": v.validation, "preview": v.preview} if full else {}),
        } for v in vs],
    }
    if full:
        pr = session.execute(select(Prompt).where(Prompt.agent_code == a.code).order_by(Prompt.version.desc()).limit(1)).scalar()
        out["prompt"] = {"version": pr.version, "system": pr.system} if pr else None
        wf = session.get(Workflow, a.workflow_code) if a.workflow_code else None
        out["workflowEnabled"] = bool(wf and wf.enabled)
        from nhdip.analysis_agents.lifecycle import default_cron
        from nhdip.analysis_agents.team import team_of_agent

        out["defaultCron"] = default_cron(session)  # 승인 화면 정기 실행 기본값(AGW-06)
        out["team"] = team_of_agent(session, a.code).json()
    return out


def _names(session: Session, emps: set[str]) -> dict[str, str]:
    emps = {e for e in emps if e}
    return dict(session.execute(select(AppUser.emp_no, AppUser.name).where(AppUser.emp_no.in_(emps))).all()) if emps else {}


@router.get("/mine")
def mine(session: Session = Depends(get_session), user: AppUser = Depends(require_resource("analysis_builder"))):
    rows = session.execute(select(AnalysisAgent).where(AnalysisAgent.requested_by == user.emp_no).order_by(AnalysisAgent.updated_at.desc()).limit(50)).scalars().all()
    names = _names(session, {r.approved_by or "" for r in rows})
    return [_agent_json(session, a, names) for a in rows]


@router.get("/mine/{code}")
def mine_one(code: str, session: Session = Depends(get_session), user: AppUser = Depends(require_resource("analysis_builder"))):
    a = session.get(AnalysisAgent, code)
    if a is None or a.requested_by != user.emp_no:
        raise HTTPException(404, "분석 에이전트 없음")
    return _agent_json(session, a, full=True)


# ═════════════════════════ 관리자 ═════════════════════════
class ReviewIn(BaseModel):
    note: str | None = None


class ApproveIn(ReviewIn):
    """관리자 승인 기준 (DAG-10 · Q108) — 비우면 요청 명세 그대로. cron 은 빈 문자열이면 정기 실행 없음."""

    cron: str | None = None
    on_data_change: bool | None = None
    llm: bool | None = None


def _dual(session: Session) -> bool:
    st = session.get(Setting, "governance.dual_control")
    v = st.value if st and isinstance(st.value, dict) else {}
    return bool(v.get("enabled"))


def _get(session: Session, code: str, version: int | None = None) -> tuple[AnalysisAgent, AnalysisAgentVersion | None]:
    a = session.get(AnalysisAgent, code, with_for_update=True)
    if a is None:
        raise HTTPException(404, "분석 에이전트 없음")
    v = None
    if version is not None:
        v = session.execute(select(AnalysisAgentVersion).where(AnalysisAgentVersion.agent_code == code, AnalysisAgentVersion.version == version)).scalar()
        if v is None:
            raise HTTPException(404, "버전 없음")
    return a, v


@admin_router.get("")
def admin_list(status: str | None = None, session: Session = Depends(get_session)):
    q = select(AnalysisAgent).order_by(AnalysisAgent.updated_at.desc()).limit(200)
    if status == "pending":
        sub = select(AnalysisAgentVersion.agent_code).where(AnalysisAgentVersion.status == "pending")
        q = q.where(AnalysisAgent.code.in_(sub))
    elif status:
        q = q.where(AnalysisAgent.status == status)
    rows = session.execute(q).scalars().all()
    names = _names(session, {r.requested_by or "" for r in rows} | {r.approved_by or "" for r in rows})
    counts = dict(session.execute(select(AnalysisAgent.status, func.count()).group_by(AnalysisAgent.status)).all())
    counts["pendingVersions"] = session.execute(select(func.count()).select_from(AnalysisAgentVersion).where(AnalysisAgentVersion.status == "pending")).scalar() or 0
    return {"items": [_agent_json(session, a, names) for a in rows], "counts": {k: int(v) for k, v in counts.items()}}


@admin_router.get("/{code}")
def admin_one(code: str, session: Session = Depends(get_session)):
    a = session.get(AnalysisAgent, code)
    if a is None:
        raise HTTPException(404, "분석 에이전트 없음")
    vs = session.execute(select(AnalysisAgentVersion.requested_by, AnalysisAgentVersion.reviewed_by).where(AnalysisAgentVersion.agent_code == code)).all()
    names = _names(session, {a.requested_by or "", a.approved_by or ""} | {x for r in vs for x in r if x})
    return _agent_json(session, a, names, full=True)


@admin_router.post("/{code}/versions/{version}/approve")
def admin_approve(code: str, version: int, body: ApproveIn, session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    a, v = _get(session, code, version)
    assert v is not None
    if _dual(session) and v.requested_by == admin.emp_no:
        raise HTTPException(409, "이중 승인 — 직접 요청한 분석은 다른 관리자가 승인해야 합니다")
    options = {k: val for k, val in body.model_dump(exclude_unset=True).items() if k in ("cron", "on_data_change", "llm")}
    try:
        out = approve(session, a, v, admin.emp_no, body.note, options)
    except LifecycleError as exc:
        session.rollback()
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return {**out, "agent": _agent_json(session, a)}


@admin_router.post("/{code}/versions/{version}/reject")
def admin_reject(code: str, version: int, body: ReviewIn, session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    note = (body.note or "").strip()
    if not note:
        raise HTTPException(422, "반려 사유를 적어 주세요")
    a, v = _get(session, code, version)
    assert v is not None
    try:
        reject(session, a, v, admin.emp_no, note[:1000])
    except LifecycleError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return _agent_json(session, a)


@admin_router.post("/{code}/{action}")
def admin_state(code: str, action: str, session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    if action not in ("pause", "resume", "retire"):
        raise HTTPException(404, "알 수 없는 동작")
    a, _ = _get(session, code)
    try:
        set_state(session, a, action, admin.emp_no)
    except LifecycleError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return _agent_json(session, a)
