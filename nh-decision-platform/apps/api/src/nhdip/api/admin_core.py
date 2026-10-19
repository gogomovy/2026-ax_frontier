"""관리자 API (1/2) — 시스템 상태 · 사용자 · 조직 · 화면 권한 · 설정 · 감사 · LLM 연동 · 에이전트 · 규칙 (ADM-01~07, 12~14)."""
from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from nhdip.db import get_session
from nhdip.events import audit, emit
from nhdip.graph.neo4j_client import health as graph_health
from nhdip.llm import LlmError, LlmUnavailable, resolve, test_connection
from nhdip.models import (
    Agent,
    AgentGroup,
    AppUser,
    AuditLog,
    Job,
    LlmConnection,
    LlmProfile,
    OrgUnit,
    OutboxEvent,
    Prompt,
    Rule,
    RuleVersion,
    Screen,
    ScreenGrant,
    Setting,
    UserSession,
    WorkerHeartbeat,
    WorkflowRun,
    utcnow,
)
from nhdip.security import decrypt_secret, encrypt_secret, hash_password, mask_secret, password_policy_error

from .auth import PW_REQUEST
from .deps import client_ip, is_data_admin, require_admin, user_json

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


def _iso(v):
    return v.isoformat() if v else None


# ═════════════════════════ 시스템 상태 ═════════════════════════
@router.get("/readiness")
def readiness(session: Session = Depends(get_session)):
    """운영 준비 점검 (B.34) — 설정 · 상태가 권장값과 맞는지."""
    from nhdip.preflight import run_checks

    return run_checks(session)


@router.get("/system")
def system(session: Session = Depends(get_session)):
    pg = {"ok": True}
    try:
        pg["version"] = session.execute(text("SHOW server_version")).scalar()
        pg["vector"] = session.execute(text("SELECT extversion FROM pg_extension WHERE extname='vector'")).scalar()
        pg["size"] = session.execute(text("SELECT pg_size_pretty(pg_database_size(current_database()))")).scalar()
    except Exception as exc:  # noqa: BLE001
        pg = {"ok": False, "error": str(exc)[:200]}
    conn = session.execute(select(LlmConnection).where(LlmConnection.active).order_by(LlmConnection.id)).scalars().first()
    litellm: dict[str, Any] = {"ok": False, "error": "LLM 주소 미입력 — 관리자 [LLM 연동]"}
    if conn and (conn.base_url or "").strip():
        base = conn.base_url.rstrip("/").removesuffix("/v1")
        try:
            r = httpx.get(f"{base}/health/liveliness", timeout=5)
            litellm = {"ok": r.status_code == 200, "status": r.status_code, "base_url": conn.base_url, "connection": conn.name}
        except httpx.HTTPError as exc:
            litellm = {"ok": False, "error": str(exc)[:200], "base_url": conn.base_url}
    workers = [{"id": w.worker_id, "seenAt": _iso(w.seen_at), "alive": (utcnow() - w.seen_at).total_seconds() < 30, "info": w.info} for w in session.execute(select(WorkerHeartbeat).order_by(WorkerHeartbeat.seen_at.desc())).scalars()]
    jobs = dict(session.execute(select(Job.status, func.count()).group_by(Job.status)).all())
    pending_events = session.execute(select(func.count()).select_from(OutboxEvent).where(OutboxEvent.dispatched_at.is_(None))).scalar()
    runs = session.execute(select(WorkflowRun).order_by(WorkflowRun.started_at.desc()).limit(8)).scalars().all()
    users = dict(session.execute(select(AppUser.status, func.count()).group_by(AppUser.status)).all())
    return {
        "postgres": pg,
        "neo4j": graph_health(),
        "litellm": litellm,
        "workers": workers,
        "jobs": jobs,
        "pendingEvents": pending_events,
        "users": users,
        "recentRuns": [{"id": r.id, "workflow": r.workflow_code, "status": r.status, "startedAt": _iso(r.started_at), "finishedAt": _iso(r.finished_at)} for r in runs],
    }


# ═════════════════════════ 사용자 ═════════════════════════
class UserPatch(BaseModel):
    name: str | None = None
    org_code: str | None = None
    role: str | None = None
    position: str | None = None
    # 부서 데이터 책임자 지정 (UPL-04 · Q107)
    data_steward: bool | None = None
    # 데이터 관리자 지정 (Phase J · DEL-01 · Q143) — 업로드 자료 삭제 권한. 데이터 관리자만 바꿀 수 있다
    data_admin: bool | None = None


class PasswordReset(BaseModel):
    password: str


@router.get("/users")
def users(status: str | None = None, session: Session = Depends(get_session)):
    q = select(AppUser).order_by(AppUser.status != "pending", AppUser.created_at.desc())
    if status:
        q = q.where(AppUser.status == status)
    return [{**user_json(session, u), "failedCount": u.failed_count, "createdAt": _iso(u.created_at), "approvedBy": u.approved_by, "approvedAt": _iso(u.approved_at),
             # 인사 동기화 사번의 사번 · 비밀번호 로그인 신청 (Phase R — 가입 화면)
             "passwordRequestAt": ((u.hr or {}).get(PW_REQUEST) or {}).get("at")} for u in session.execute(q).scalars()]


def _user(session: Session, emp: str) -> AppUser:
    u = session.get(AppUser, emp)
    if not u:
        raise HTTPException(404, "사용자 없음")
    return u


def _revoke(session: Session, emp: str) -> None:
    for us in session.execute(select(UserSession).where(UserSession.emp_no == emp, UserSession.revoked_at.is_(None))).scalars():
        us.revoked_at = utcnow()


@router.post("/users/{emp}/{action}")
def user_action(emp: str, action: str, request: Request, session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    u = _user(session, emp)
    if emp == admin.emp_no and action in ("disable", "reject"):
        raise HTTPException(400, "본인 계정은 중지할 수 없습니다")
    if action in ("approve", "reject") and (u.hr or {}).get(PW_REQUEST):
        # 인사 동기화 사번의 비밀번호 로그인 신청 — 계정 상태(사내 SSO)는 그대로, 비밀번호만 승인 · 반려
        hr = {k: v for k, v in (u.hr or {}).items() if k != PW_REQUEST}
        if action == "approve":
            u.approved_by, u.approved_at = admin.emp_no, utcnow()
        else:
            u.password_hash, u.failed_count = "", 0
        u.hr = hr
        audit(session, admin.emp_no, f"admin.user.password_{action}", "user", emp, None, client_ip(request))
        session.commit()
        return user_json(session, u)
    if action == "approve":
        u.status, u.approved_by, u.approved_at = "active", admin.emp_no, utcnow()
    elif action == "reject" or action == "disable":
        u.status = "disabled"
        _revoke(session, emp)
    elif action == "enable":
        u.status = "active"
    elif action == "unlock":
        u.status, u.failed_count = "active", 0
    elif action == "revoke-sessions":
        _revoke(session, emp)
    else:
        raise HTTPException(404, "알 수 없는 작업")
    audit(session, admin.emp_no, f"admin.user.{action}", "user", emp, None, client_ip(request))
    session.commit()
    return user_json(session, u)


def _check_data_admin_change(session: Session, actor: AppUser, target: AppUser, grant: bool, role: str) -> None:
    """데이터 관리자 지정 · 해제 (Q143) — 데이터 관리자만 바꾸고, 관리자에게만 주며, 마지막 데이터 관리자는 해제할 수 없다."""
    if not is_data_admin(actor):
        raise HTTPException(403, "데이터 관리자 지정은 데이터 관리자만 바꿀 수 있습니다")
    if grant and role != "admin":
        raise HTTPException(422, "데이터 관리자는 관리자 역할인 사용자에게만 지정할 수 있습니다")
    if not grant:
        others = session.execute(
            select(func.count()).select_from(AppUser).where(AppUser.data_admin, AppUser.role == "admin", AppUser.status == "active", AppUser.emp_no != target.emp_no)
        ).scalar()
        if not others:
            raise HTTPException(409, "마지막 데이터 관리자는 해제할 수 없습니다 — 다른 관리자를 먼저 지정하세요")


@router.patch("/users/{emp}")
def user_patch(emp: str, body: UserPatch, request: Request, session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    u = _user(session, emp)
    patch = body.model_dump(exclude_none=True)
    if "org_code" in patch and not session.get(OrgUnit, patch["org_code"]):
        raise HTTPException(422, "조직 없음")
    if "role" in patch and patch["role"] not in ("admin", "user"):
        raise HTTPException(422, "role 은 admin | user")
    if emp == admin.emp_no and patch.get("role") == "user":
        raise HTTPException(400, "본인 관리자 권한은 해제할 수 없습니다")
    if "data_admin" in patch and bool(patch["data_admin"]) != bool(u.data_admin):
        _check_data_admin_change(session, admin, u, bool(patch["data_admin"]), patch.get("role", u.role))
    if patch.get("role") == "user" and u.data_admin:
        _check_data_admin_change(session, admin, u, False, "user")
        patch["data_admin"] = False  # 관리자 권한을 회수하면 데이터 관리자 지정도 함께 해제
    for k, v in patch.items():
        setattr(u, k, v)
    audit(session, admin.emp_no, "admin.user.update", "user", emp, patch, client_ip(request))
    session.commit()
    return user_json(session, u)


@router.post("/users/{emp}/password")
def user_password(emp: str, body: PasswordReset, request: Request, session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    u = _user(session, emp)
    err = password_policy_error(body.password)
    if err:
        raise HTTPException(422, err)
    u.password_hash = hash_password(body.password)
    u.failed_count = 0
    if u.status == "locked":
        u.status = "active"
    if (u.hr or {}).get(PW_REQUEST):  # 관리자가 직접 비밀번호를 정하면 신청은 끝난 것으로
        u.hr = {k: v for k, v in u.hr.items() if k != PW_REQUEST}
    _revoke(session, emp)
    audit(session, admin.emp_no, "admin.user.password_reset", "user", emp, None, client_ip(request))
    session.commit()
    return {"ok": True}


# ═════════════════════════ 조직 ═════════════════════════
class OrgIn(BaseModel):
    code: str
    name: str
    unit_type: str
    parent_code: str | None = None
    sort: int = 0
    active: bool = True


class OrgPatch(BaseModel):
    name: str | None = None
    unit_type: str | None = None
    parent_code: str | None = None
    sort: int | None = None
    active: bool | None = None


@router.get("/orgs")
def orgs(session: Session = Depends(get_session)):
    from nhdip.orgs import type_labels, unit_types

    rows = session.execute(select(OrgUnit).order_by(OrgUnit.sort, OrgUnit.code)).scalars().all()
    counts = dict(session.execute(select(AppUser.org_code, func.count()).group_by(AppUser.org_code)).all())
    lbl = type_labels(session)
    return {
        "unitTypes": unit_types(session),
        "orgs": [{"code": o.code, "name": o.name, "level": o.level, "unitType": o.unit_type, "unitLabel": lbl.get(o.unit_type or "", "조직"), "parent": o.parent_code, "sort": o.sort, "active": o.active, "users": counts.get(o.code, 0)} for o in rows],
    }


@router.post("/orgs", status_code=201)
def org_create(body: OrgIn, request: Request, session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    from nhdip.orgs import OrgError, recompute_levels, validate_parent

    if session.get(OrgUnit, body.code):
        raise HTTPException(409, "이미 있는 조직 코드")
    try:
        validate_parent(session, body.unit_type, body.parent_code)
    except OrgError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.add(OrgUnit(**body.model_dump(), level=1))
    session.flush()
    recompute_levels(session)
    audit(session, admin.emp_no, "admin.org.create", "org", body.code, body.model_dump(), client_ip(request))
    session.commit()
    return orgs(session)


@router.patch("/orgs/{code}")
def org_patch(code: str, body: OrgPatch, request: Request, session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    from nhdip.orgs import OrgError, recompute_levels, validate_parent

    o = session.get(OrgUnit, code)
    if not o:
        raise HTTPException(404, "조직 없음")
    patch = body.model_dump(exclude_unset=True)
    if "parent_code" in patch or "unit_type" in patch:
        try:
            validate_parent(session, patch.get("unit_type", o.unit_type) or "", patch.get("parent_code", o.parent_code), self_code=code)
        except OrgError as exc:
            raise HTTPException(422, str(exc)) from exc
    for k, v in patch.items():
        setattr(o, k, v)
    session.flush()
    recompute_levels(session)
    audit(session, admin.emp_no, "admin.org.update", "org", code, patch, client_ip(request))
    session.commit()
    return orgs(session)


# ═════════════════════════ 화면 권한 ═════════════════════════
class GrantIn(BaseModel):
    org_code: str
    screen_code: str
    granted: bool


class ScreenPatch(BaseModel):
    label: str | None = None
    section: str | None = None
    sort: int | None = None
    active: bool | None = None
    kind: str | None = None
    step: int | None = None
    count_key: str | None = None
    resources: list[str] | None = None


@router.get("/screens")
def screens(session: Session = Depends(get_session)):
    rows = session.execute(select(Screen).order_by(Screen.sort)).scalars().all()
    grants = session.execute(select(ScreenGrant)).scalars().all()
    res = session.get(Setting, "screen.resources")
    resmap = res.value if res else {}
    return {
        "screens": [{"code": s.code, "path": s.path, "label": s.label, "section": s.section, "kind": s.kind, "step": s.step, "countKey": s.count_key, "sort": s.sort, "adminOnly": s.admin_only, "active": s.active, "resources": resmap.get(s.code, [])} for s in rows],
        "grants": [{"org": g.org_code, "screen": g.screen_code} for g in grants],
        "orgs": orgs(session)["orgs"],
    }


@router.put("/screens/grants")
def set_grant(body: GrantIn, request: Request, session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    if not session.get(OrgUnit, body.org_code) or not session.get(Screen, body.screen_code):
        raise HTTPException(404, "조직 또는 화면 없음")
    g = session.get(ScreenGrant, (body.org_code, body.screen_code))
    if body.granted and not g:
        session.add(ScreenGrant(org_code=body.org_code, screen_code=body.screen_code, granted_by=admin.emp_no))
    elif not body.granted and g:
        session.delete(g)
    audit(session, admin.emp_no, "admin.screen.grant", "screen", body.screen_code, body.model_dump(), client_ip(request))
    session.commit()
    return {"ok": True}


class ScreenIn(BaseModel):
    code: str
    path: str
    label: str
    section: str
    kind: str = "reference"
    sort: int = 90
    resources: list[str] = []
    grant_orgs: list[str] = []
    # 새 부서 분석 공간(Phase C · DAG-07) — 주면 설정 analysis.spaces 에 등록(경로 /analysis/<key>)
    analysis_space: dict[str, Any] | None = None


@router.post("/screens", status_code=201)
def screen_create(body: ScreenIn, request: Request, session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    """화면 등록 (Phase C · DAG-07) — 새 부서 분석 공간처럼 코드 변경 없이 화면 · 권한 · 리소스를 더한다."""
    import re

    code = body.code.strip().upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9_]{2,39}", code):
        raise HTTPException(422, "화면 코드는 영문 대문자 · 숫자 · _ 3~40자")
    if not re.fullmatch(r"/[a-z0-9\-/\[\]]{1,80}", body.path) or ".." in body.path:
        raise HTTPException(422, "경로 형식이 올바르지 않습니다 (예: /analysis/consumer)")
    if body.kind not in ("flow", "reference", "hidden"):
        raise HTTPException(422, "kind 는 flow | reference | hidden")
    if session.get(Screen, code) or session.execute(select(Screen).where(Screen.path == body.path)).first():
        raise HTTPException(409, "같은 코드나 경로의 화면이 있습니다")
    if not all(re.fullmatch(r"[a-z][a-z0-9_]{1,40}", r) for r in body.resources):
        raise HTTPException(422, "리소스 키는 영문 소문자 · 숫자 · _")
    session.add(Screen(code=code, path=body.path, label=body.label.strip()[:60], section=body.section.strip()[:60], kind=body.kind, sort=body.sort, active=True, admin_only=False))
    session.flush()
    st = session.get(Setting, "screen.resources")
    value = dict(st.value) if st else {}
    value[code] = list(dict.fromkeys(body.resources))
    if st:
        st.value = value
    else:
        session.add(Setting(key="screen.resources", value=value, description="화면 → 화면 API 리소스 (권한 판정)"))
    for org in body.grant_orgs:
        if session.get(OrgUnit, org) and not session.get(ScreenGrant, (org, code)):
            session.add(ScreenGrant(org_code=org, screen_code=code, granted_by=admin.emp_no))
    if body.analysis_space:
        sp = dict(body.analysis_space)
        key = str(sp.get("key") or "").strip().lower()
        if not re.fullmatch(r"[a-z][a-z0-9_]{1,30}", key):
            raise HTTPException(422, "분석 공간 키는 영문 소문자 · 숫자 · _")
        res = sp.get("resource") or (body.resources[0] if body.resources else None)
        if not res:
            raise HTTPException(422, "분석 공간 열람 리소스가 필요합니다(resources 첫 항목)")
        cur = session.get(Setting, "analysis.spaces")
        spaces_v = dict(cur.value) if cur and isinstance(cur.value, dict) else {}
        spaces_v[key] = {"label": str(sp.get("label") or body.label)[:60], "path": body.path, "tabs": None, "tabsResource": res, "resource": res, "reportPrefix": "report.", "builder": bool(sp.get("builder", True)), "domain": str(sp.get("domain") or key.upper())[:20], "persona": str(sp.get("persona") or "P1")[:4]}
        if cur:
            cur.value = spaces_v
        else:
            session.add(Setting(key="analysis.spaces", value=spaces_v, description="부서 분석 공간"))
    audit(session, admin.emp_no, "admin.screen.create", "screen", code, body.model_dump(), client_ip(request))
    session.commit()
    return screens(session)


@router.patch("/screens/{code}")
def screen_patch(code: str, body: ScreenPatch, request: Request, session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    s = session.get(Screen, code)
    if not s:
        raise HTTPException(404, "화면 없음")
    patch = body.model_dump(exclude_unset=True)
    resources = patch.pop("resources", None)
    for k, v in patch.items():
        setattr(s, k, v)
    if resources is not None:
        st = session.get(Setting, "screen.resources")
        value = dict(st.value) if st else {}
        value[code] = resources
        if st:
            st.value = value
        else:
            session.add(Setting(key="screen.resources", value=value))
    audit(session, admin.emp_no, "admin.screen.update", "screen", code, body.model_dump(exclude_unset=True), client_ip(request))
    session.commit()
    return screens(session)


# ═════════════════════════ 설정 · 감사 ═════════════════════════
class SettingIn(BaseModel):
    value: Any
    description: str | None = None


@router.get("/settings")
def settings(session: Session = Depends(get_session)):
    return [{"key": s.key, "value": s.value, "description": s.description, "updatedBy": s.updated_by, "updatedAt": _iso(s.updated_at)} for s in session.execute(select(Setting).order_by(Setting.key)).scalars()]


@router.put("/settings/{key}")
def setting_put(key: str, body: SettingIn, request: Request, session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    if key.startswith("governance.") and _dual_control(session):
        # 이중 승인이 켜져 있으면 통제 설정 자체도 두 사람 — 첫 관리자는 요청만, 다른 관리자가 같은 값을 저장하면 반영 (B.33)
        from nhdip.locks import lock

        lock(session, "setting:governance")
        pend = session.get(Setting, "governance.pending")
        req = (pend.value or {}).get(key) if pend and isinstance(pend.value, dict) else None
        if not req or req.get("by") == admin.emp_no or req.get("value") != body.value:
            reqs = {**(pend.value if pend and isinstance(pend.value, dict) else {}), key: {"value": body.value, "by": admin.emp_no, "at": utcnow().isoformat()}}
            if pend:
                pend.value = reqs
            else:
                session.add(Setting(key="governance.pending", value=reqs, description="이중 승인 대기 중인 통제 설정 변경 요청 (다른 관리자가 같은 값을 저장하면 반영)", updated_by=admin.emp_no))
            audit(session, admin.emp_no, "admin.setting.request", "setting", key, {"value": body.value}, client_ip(request))
            session.commit()
            return {"ok": True, "pending": True, "message": "이중 승인 — 다른 관리자가 같은 값을 저장하면 반영됩니다"}
        reqs = dict(pend.value)
        reqs.pop(key, None)
        pend.value = reqs
    if key.startswith("ui."):
        # 화면 설정 형식 검사 (Phase K · Q148) — 깨진 값이 저장되면 모든 화면이 기본값으로 돌아가므로 저장 전에 막는다
        from nhdip.ui_config import UiConfigError, validate

        try:
            body.value = validate(session, key, body.value)
        except UiConfigError as exc:
            raise HTTPException(422, str(exc)) from exc
    s = session.get(Setting, key)
    before = s.value if s else None
    if s:
        s.value = body.value
        if body.description is not None:
            s.description = body.description
        s.updated_by = admin.emp_no
    else:
        session.add(Setting(key=key, value=body.value, description=body.description or "", updated_by=admin.emp_no))
    emit(session, "config.changed", {"kind": "setting", "key": key}, admin.emp_no)
    audit(session, admin.emp_no, "admin.setting.update", "setting", key, {"before": before, "after": body.value}, client_ip(request))
    session.commit()
    return {"ok": True}


@router.get("/ui-config")
def ui_config_meta(session: Session = Depends(get_session)):
    """관리자 [화면 설정] (Phase K · Q148) — 현재 값 · 기본값 · 설명 · 선택지(목표 · 조직 · 메뉴 묶음 · 건수 키). 저장은 PUT /admin/settings/{key}."""
    from nhdip.ui_config import admin_meta

    return admin_meta(session)


@router.get("/audit")
def audit_log(actor: str | None = None, action: str | None = None, limit: int = 200, session: Session = Depends(get_session)):
    q = select(AuditLog).order_by(AuditLog.at.desc()).limit(min(limit, 1000))
    if actor:
        q = q.where(AuditLog.actor == actor)
    if action:
        q = q.where(AuditLog.action.like(f"{action}%"))
    return [{"id": a.id, "at": _iso(a.at), "actor": a.actor, "action": a.action, "targetKind": a.target_kind, "targetId": a.target_id, "detail": a.detail, "ip": a.ip} for a in session.execute(q).scalars()]


# ═════════════════════════ LLM 연동 ═════════════════════════
_BLOCKED_HOSTS = {"metadata.google.internal", "metadata", "instance-data"}


def _check_base_url(url: str | None) -> str | None:
    """LLM 연결 주소 점검 (B.32 · SSRF) — http(s) 만, 링크 로컬(169.254.* · fe80::) · 클라우드 메타데이터 주소 차단.

    사내 게이트웨이(사설 대역)는 허용한다 — 폐쇄망 LLM 이 사설 주소에 있기 때문이다.
    """
    if url is None:
        return None
    import ipaddress
    import socket
    from urllib.parse import urlparse

    u = urlparse(url.strip())
    if u.scheme not in ("http", "https") or not u.hostname:
        raise HTTPException(422, "LLM 주소는 http(s)://호스트 형식이어야 합니다")
    host = u.hostname.lower()
    if host in _BLOCKED_HOSTS:
        raise HTTPException(422, "메타데이터 주소는 LLM 연결로 쓸 수 없습니다")
    try:
        addrs = {ai[4][0] for ai in socket.getaddrinfo(host, None)}
    except OSError:
        addrs = {host}  # 아직 해석되지 않는 이름(배포 전 등록) — 문자 그대로 검사
    for a in addrs:
        try:
            ip = ipaddress.ip_address(a.split("%", 1)[0])
        except ValueError:
            continue
        mapped = getattr(ip, "ipv4_mapped", None) or ip
        if mapped.is_link_local or mapped.is_multicast or mapped.is_unspecified or str(mapped) == "fd00:ec2::254":
            raise HTTPException(422, "링크 로컬 · 메타데이터 주소는 LLM 연결로 쓸 수 없습니다")
    return url.strip()


class ConnIn(BaseModel):
    name: str
    base_url: str
    api_key: str | None = None
    active: bool = True
    note: str | None = None


class ConnPatch(BaseModel):
    name: str | None = None
    base_url: str | None = None
    api_key: str | None = None  # 비우면 유지, "" 이면 삭제
    active: bool | None = None
    note: str | None = None


class TestIn(BaseModel):
    model: str | None = None


class ProfileIn(BaseModel):
    name: str
    connection_id: int | None = None
    model: str = ""
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    timeout_sec: float = 60
    retries: int = 2
    tools_enabled: bool = False
    extra: dict[str, Any] = {}
    is_default: bool = False


def _conn_json(c: LlmConnection) -> dict[str, Any]:
    try:
        key = decrypt_secret(c.api_key_enc)
    except Exception:  # noqa: BLE001
        key = ""
    return {"id": c.id, "name": c.name, "baseUrl": c.base_url, "apiKeyMasked": mask_secret(key), "hasKey": bool(key), "active": c.active, "note": c.note, "lastTest": c.last_test, "updatedAt": _iso(c.updated_at)}


def _profile_json(p: LlmProfile) -> dict[str, Any]:
    return {"id": p.id, "name": p.name, "connectionId": p.connection_id, "model": p.model, "temperature": p.temperature, "topP": p.top_p, "maxTokens": p.max_tokens, "timeoutSec": p.timeout_sec, "retries": p.retries, "toolsEnabled": p.tools_enabled, "extra": p.extra, "isDefault": p.is_default}


@router.get("/llm")
def llm(session: Session = Depends(get_session)):
    return {
        "connections": [_conn_json(c) for c in session.execute(select(LlmConnection).order_by(LlmConnection.id)).scalars()],
        "profiles": [_profile_json(p) for p in session.execute(select(LlmProfile).order_by(LlmProfile.id)).scalars()],
    }


class LlmSetupIn(BaseModel):
    base_url: str
    api_key: str | None = None  # None = 유지, "" = 삭제
    model: str | None = None  # 기본 프로필 모델 (None = 유지)
    embedding_model: str | None = None  # 임베딩 프로필 모델 (None = 유지, "" = 끔)


@router.get("/llm/setup")
def llm_setup_get(session: Session = Depends(get_session)):
    """간단 설정 화면 — 기본 프로필이 쓰는 연결 · 모델 (B.36)."""
    prof = session.execute(select(LlmProfile).where(LlmProfile.is_default)).scalars().first()
    conn = session.get(LlmConnection, prof.connection_id) if prof and prof.connection_id else session.execute(select(LlmConnection).order_by(LlmConnection.id)).scalars().first()
    emb = session.execute(select(LlmProfile).where(LlmProfile.name == "embedding")).scalars().first()
    return {"connection": _conn_json(conn) if conn else None, "model": prof.model if prof else "", "embeddingModel": emb.model if emb else ""}


@router.post("/llm/setup")
def llm_setup(body: LlmSetupIn, request: Request, session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    """외부 LiteLLM 주소 · 키 · 모델을 한 번에 저장하고 연결을 확인한다 (B.36).
    기본 프로필이 쓰는 연결을 고친다(없으면 'litellm' 연결을 만든다). 확인 결과의 모델 목록으로 모델을 고를 수 있다."""
    url = _check_base_url(body.base_url)
    prof = session.execute(select(LlmProfile).where(LlmProfile.is_default)).scalars().first()
    conn = session.get(LlmConnection, prof.connection_id) if prof and prof.connection_id else None
    conn = conn or session.execute(select(LlmConnection).where(LlmConnection.name == "litellm")).scalar()
    if conn is None:
        conn = LlmConnection(name="litellm", base_url=url, api_key_enc=encrypt_secret(""), active=True, note="외부 LiteLLM 게이트웨이")
        session.add(conn)
        session.flush()
    conn.base_url, conn.active = url, True
    if body.api_key is not None:
        conn.api_key_enc = encrypt_secret(body.api_key)
    if prof is None:
        prof = LlmProfile(name="default", connection_id=conn.id, model=(body.model or "").strip(), timeout_sec=60, retries=2, is_default=True, extra={})
        session.add(prof)
    prof.connection_id = conn.id
    if body.model is not None:
        prof.model = body.model.strip()
    emb = session.execute(select(LlmProfile).where(LlmProfile.name == "embedding")).scalars().first()
    if body.embedding_model is not None:
        if emb is None:
            emb = LlmProfile(name="embedding", connection_id=conn.id, model="", timeout_sec=60, retries=2, extra={})
            session.add(emb)
        emb.connection_id, emb.model = conn.id, body.embedding_model.strip()
    session.flush()
    res = test_connection(conn.base_url, decrypt_secret(conn.api_key_enc), prof.model or None)
    conn.last_test = {**res, "models": (res.get("models") or [])[:50], "at": utcnow().isoformat()}
    audit(session, admin.emp_no, "admin.llm.setup", "llm_connection", str(conn.id), {"base_url": url, "api_key": "변경" if body.api_key is not None else "유지", "model": prof.model, "embedding_model": emb.model if emb else None, "ok": res.get("ok")}, client_ip(request))
    session.commit()
    from nhdip.workflow.llm_judge import reset_cooldown

    reset_cooldown()  # 연결을 바꿨으므로 판단 에이전트의 '최근 오류 쉼'을 푼다
    return {"connection": _conn_json(conn), "model": prof.model, "embeddingModel": emb.model if emb else "", "test": res}


@router.post("/llm/connections", status_code=201)
def conn_create(body: ConnIn, request: Request, session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    c = LlmConnection(name=body.name, base_url=_check_base_url(body.base_url), api_key_enc=encrypt_secret(body.api_key or ""), active=body.active, note=body.note)
    session.add(c)
    audit(session, admin.emp_no, "admin.llm.connection_create", "llm_connection", body.name, {"base_url": body.base_url}, client_ip(request))
    session.commit()
    return _conn_json(c)


@router.patch("/llm/connections/{cid}")
def conn_patch(cid: int, body: ConnPatch, request: Request, session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    c = session.get(LlmConnection, cid)
    if not c:
        raise HTTPException(404, "연결 없음")
    patch = body.model_dump(exclude_unset=True)
    if patch.get("base_url") is not None:
        patch["base_url"] = _check_base_url(patch["base_url"])
    if "api_key" in patch:
        if patch["api_key"] is not None:
            c.api_key_enc = encrypt_secret(patch["api_key"])
        patch.pop("api_key")
    for k, v in patch.items():
        setattr(c, k, v)
    audit(session, admin.emp_no, "admin.llm.connection_update", "llm_connection", str(cid), {**patch, "api_key": "변경" if body.api_key is not None else "유지"}, client_ip(request))
    session.commit()
    return _conn_json(c)


@router.delete("/llm/connections/{cid}")
def conn_delete(cid: int, request: Request, session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    c = session.get(LlmConnection, cid)
    if not c:
        raise HTTPException(404, "연결 없음")
    session.delete(c)
    audit(session, admin.emp_no, "admin.llm.connection_delete", "llm_connection", str(cid), None, client_ip(request))
    session.commit()
    return {"ok": True}


@router.post("/llm/connections/{cid}/test")
def conn_test(cid: int, body: TestIn, request: Request, session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    c = session.get(LlmConnection, cid)
    if not c:
        raise HTTPException(404, "연결 없음")
    _check_base_url(c.base_url)
    res = test_connection(c.base_url, decrypt_secret(c.api_key_enc), body.model)
    c.last_test = {**res, "models": (res.get("models") or [])[:50], "at": utcnow().isoformat()}
    audit(session, admin.emp_no, "admin.llm.connection_test", "llm_connection", str(cid), {"ok": res.get("ok"), "model": body.model}, client_ip(request))
    session.commit()
    return res


@router.post("/llm/profiles", status_code=201)
def profile_create(body: ProfileIn, request: Request, session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    if body.is_default:
        for p in session.execute(select(LlmProfile).where(LlmProfile.is_default)).scalars():
            p.is_default = False
    p = LlmProfile(**body.model_dump())
    session.add(p)
    audit(session, admin.emp_no, "admin.llm.profile_create", "llm_profile", body.name, body.model_dump(), client_ip(request))
    session.commit()
    return _profile_json(p)


@router.patch("/llm/profiles/{pid}")
def profile_patch(pid: int, body: dict[str, Any], request: Request, session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    p = session.get(LlmProfile, pid)
    if not p:
        raise HTTPException(404, "프로필 없음")
    allowed = set(ProfileIn.model_fields)
    patch = {k: v for k, v in body.items() if k in allowed}
    if patch.get("is_default"):
        for other in session.execute(select(LlmProfile).where(LlmProfile.is_default, LlmProfile.id != pid)).scalars():
            other.is_default = False
    for k, v in patch.items():
        setattr(p, k, v)
    audit(session, admin.emp_no, "admin.llm.profile_update", "llm_profile", str(pid), patch, client_ip(request))
    session.commit()
    return _profile_json(p)


# ═════════════════════════ 에이전트 ═════════════════════════
class AgentPatch(BaseModel):
    name: str | None = None
    role: str | None = None
    profile_id: int | None = None
    override: dict[str, Any] | None = None
    enabled: bool | None = None
    prompt_version: int | None = None
    group_code: str | None = None  # 기능 묶음(Phase M · AGG-01) — 빈 문자열이면 그룹 해제


class PromptIn(BaseModel):
    system: str
    user_template: str = ""
    note: str | None = None


class AskIn(BaseModel):
    message: str
    use_tools: bool = True


def _agent_json(session: Session, a: Agent) -> dict[str, Any]:
    resolved: dict[str, Any]
    try:
        r = resolve(session, a.code)
        resolved = {"ok": True, "connection": r.connection_name, "baseUrl": r.base_url, "model": r.model, "params": r.params, "timeout": r.timeout, "retries": r.retries, "toolsEnabled": r.tools_enabled, "promptVersion": r.prompt_version, "apiKeyMasked": mask_secret(r.api_key)}
    except LlmUnavailable as exc:
        resolved = {"ok": False, "reason": str(exc)}
    prompts = session.execute(select(Prompt).where(Prompt.agent_code == a.code).order_by(Prompt.version.desc())).scalars().all()
    from nhdip.models import LlmCall

    calls = session.execute(select(func.count(), func.avg(LlmCall.latency_ms)).where(LlmCall.agent_code == a.code)).one()
    return {
        "code": a.code,
        "name": a.name,
        "role": a.role,
        "kind": a.kind,
        "groupCode": a.group_code,
        "profileId": a.profile_id,
        "override": a.override,
        "enabled": a.enabled,
        "promptVersion": a.prompt_version,
        "resolved": resolved if a.kind == "llm" else {"ok": True, "rule": True},
        "prompts": [{"version": p.version, "system": p.system, "userTemplate": p.user_template, "note": p.note, "createdBy": p.created_by, "createdAt": _iso(p.created_at)} for p in prompts],
        "stats": {"calls": calls[0], "avgLatencyMs": int(calls[1]) if calls[1] else None},
    }


@router.get("/agents")
def agents(session: Session = Depends(get_session)):
    return [_agent_json(session, a) for a in session.execute(select(Agent).order_by(Agent.code)).scalars()]


@router.patch("/agents/{code}")
def agent_patch(code: str, body: AgentPatch, request: Request, session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    a = session.get(Agent, code)
    if not a:
        raise HTTPException(404, "에이전트 없음")
    patch = body.model_dump(exclude_unset=True)
    if "override" in patch:
        ov = {k: v for k, v in (patch["override"] or {}).items() if v not in ("", None)}
        if "connection_id" in ov and not session.get(LlmConnection, int(ov["connection_id"])):
            raise HTTPException(422, "연결 없음")
        patch["override"] = ov
    if "group_code" in patch:
        patch["group_code"] = patch["group_code"] or None
        if patch["group_code"] and session.get(AgentGroup, patch["group_code"]) is None:
            raise HTTPException(422, "그룹 없음")
    for k, v in patch.items():
        setattr(a, k, v)
    emit(session, "config.changed", {"kind": "agent", "code": code}, admin.emp_no)
    audit(session, admin.emp_no, "admin.agent.update", "agent", code, patch, client_ip(request))
    session.commit()
    return _agent_json(session, a)


# ── 에이전트 그룹 (Phase M · AGG-01 · AGG-02 · Q188) ──
GROUP_APPLY_KEYS = ("connection_id", "model", "temperature", "top_p", "max_tokens", "timeout_sec", "retries", "tools_enabled")


class GroupPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    sort: int | None = None


class GroupApplyIn(BaseModel):
    override: dict[str, Any]  # GROUP_APPLY_KEYS 만 — 값이 null/빈 문자열이면 그 키를 에이전트 override 에서 뺀다(프로필 값으로 돌아감)
    agents: list[str] | None = None  # 고른 에이전트만(없으면 그룹의 LLM 에이전트 전체)


def agent_stats_24h(session: Session) -> dict[str, dict[str, Any]]:
    """에이전트별 최근 24시간 호출 · 오류 · 평균 지연 · 토큰(ops.llm_call)."""
    from datetime import timedelta

    from nhdip.models import LlmCall, utcnow

    since = utcnow() - timedelta(hours=24)
    rows = session.execute(
        select(LlmCall.agent_code, func.count(), func.count().filter(LlmCall.status == "error"), func.count().filter(LlmCall.status == "skipped"), func.avg(LlmCall.latency_ms),
               func.coalesce(func.sum(LlmCall.prompt_tokens), 0) + func.coalesce(func.sum(LlmCall.completion_tokens), 0))
        .where(LlmCall.created_at >= since).group_by(LlmCall.agent_code)
    ).all()
    return {code: {"calls": n, "errors": e, "skipped": sk, "avgLatencyMs": int(lat) if lat else None, "tokens": int(tok or 0)} for code, n, e, sk, lat, tok in rows if code}


def _group_summary(agents_: list[Agent], stats: dict[str, dict[str, Any]]) -> dict[str, Any]:
    calls = sum(stats.get(a.code, {}).get("calls", 0) for a in agents_)
    errors = sum(stats.get(a.code, {}).get("errors", 0) for a in agents_)
    lat = [stats[a.code]["avgLatencyMs"] for a in agents_ if stats.get(a.code, {}).get("avgLatencyMs")]
    return {"agents": len(agents_), "llm": sum(1 for a in agents_ if a.kind == "llm"), "rule": sum(1 for a in agents_ if a.kind != "llm"), "enabled": sum(1 for a in agents_ if a.enabled),
            "calls24h": calls, "errors24h": errors, "errorRate": round(errors / calls * 100, 1) if calls else None, "avgLatencyMs": int(sum(lat) / len(lat)) if lat else None,
            "tokens24h": sum(stats.get(a.code, {}).get("tokens", 0) for a in agents_)}


@router.get("/agent-groups")
def agent_groups(session: Session = Depends(get_session)):
    """그룹 탭 — 그룹마다 요약(에이전트 수 · LLM/규칙 · 24시간 호출 · 오류율 · 평균 지연)과 소속 에이전트 코드. 그룹 없는 에이전트는 'ungrouped'."""
    stats = agent_stats_24h(session)
    all_agents = session.execute(select(Agent).order_by(Agent.code)).scalars().all()
    groups = session.execute(select(AgentGroup).order_by(AgentGroup.sort, AgentGroup.code)).scalars().all()
    known = {g.code for g in groups}
    out = []
    for g in groups:
        mem = [a for a in all_agents if a.group_code == g.code]
        out.append({"code": g.code, "name": g.name, "description": g.description, "sort": g.sort, "agents": [a.code for a in mem], "summary": _group_summary(mem, stats)})
    loose = [a for a in all_agents if a.group_code not in known]
    return {"groups": out, "ungrouped": {"agents": [a.code for a in loose], "summary": _group_summary(loose, stats)}, "stats": stats, "applyKeys": list(GROUP_APPLY_KEYS)}


@router.patch("/agent-groups/{code}")
def agent_group_patch(code: str, body: GroupPatch, request: Request, session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    g = session.get(AgentGroup, code)
    if g is None:
        raise HTTPException(404, "그룹 없음")
    patch = body.model_dump(exclude_unset=True)
    if "name" in patch and not (patch["name"] or "").strip():
        raise HTTPException(422, "그룹 이름을 입력하세요")
    for k, v in patch.items():
        setattr(g, k, v.strip() if isinstance(v, str) else v)
    audit(session, admin.emp_no, "admin.agent_group.update", "agent_group", code, patch, client_ip(request))
    session.commit()
    return {"code": g.code, "name": g.name, "description": g.description, "sort": g.sort}


@router.post("/agent-groups/{code}/apply")
def agent_group_apply(code: str, body: GroupApplyIn, request: Request, session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    """그룹 일괄 적용(AGG-02) — 그룹의 LLM 에이전트 override 에 같은 연결 · 모델 · 파라미터를 넣는다(다른 키는 그대로). 규칙형 에이전트는 건너뛴다."""
    if session.get(AgentGroup, code) is None:
        raise HTTPException(404, "그룹 없음")
    bad = [k for k in body.override if k not in GROUP_APPLY_KEYS]
    if bad:
        raise HTTPException(422, f"일괄 적용할 수 없는 항목: {', '.join(bad)}")
    if not body.override:
        raise HTTPException(422, "적용할 항목이 없습니다")
    ov_in = dict(body.override)
    if ov_in.get("connection_id") not in (None, "") and not session.get(LlmConnection, int(ov_in["connection_id"])):
        raise HTTPException(422, "연결 없음")
    for k in ("temperature", "top_p"):
        if ov_in.get(k) not in (None, "") and not 0 <= float(ov_in[k]) <= 2:
            raise HTTPException(422, f"{k} 는 0~2")
    for k in ("max_tokens", "retries"):
        if ov_in.get(k) not in (None, "") and int(ov_in[k]) < 0:
            raise HTTPException(422, f"{k} 는 0 이상")
    q = select(Agent).where(Agent.group_code == code, Agent.kind == "llm")
    if body.agents:
        q = q.where(Agent.code.in_(body.agents))
    changed = []
    for a in session.execute(q.order_by(Agent.code)).scalars():
        ov = dict(a.override or {})
        for k, v in ov_in.items():
            if v in (None, ""):
                ov.pop(k, None)
            else:
                ov[k] = v
        if ov != (a.override or {}):
            a.override = ov
            changed.append(a.code)
            emit(session, "config.changed", {"kind": "agent", "code": a.code}, admin.emp_no)
    audit(session, admin.emp_no, "admin.agent_group.apply", "agent_group", code, {"override": ov_in, "agents": changed}, client_ip(request))
    session.commit()
    return {"group": code, "changed": changed, "agents": [_agent_json(session, a) for a in session.execute(select(Agent).where(Agent.code.in_(changed))).scalars()] if changed else []}


@router.post("/agents/{code}/prompts", status_code=201)
def prompt_create(code: str, body: PromptIn, request: Request, session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    a = session.get(Agent, code)
    if not a:
        raise HTTPException(404, "에이전트 없음")
    last = session.execute(select(func.max(Prompt.version)).where(Prompt.agent_code == code)).scalar() or 0
    session.add(Prompt(agent_code=code, version=last + 1, system=body.system, user_template=body.user_template, note=body.note, created_by=admin.emp_no))
    a.prompt_version = last + 1
    audit(session, admin.emp_no, "admin.agent.prompt", "agent", code, {"version": last + 1}, client_ip(request))
    session.commit()
    return _agent_json(session, a)


@router.post("/agents/{code}/ask")
def agent_ask(code: str, body: AskIn, request: Request, session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    """에이전트 시험 호출. query_assistant 등 tools_enabled 면 커널 도구 루프(CALC-10)."""
    audit(session, admin.emp_no, "admin.agent.ask", "agent", code, {"chars": len(body.message), "useTools": body.use_tools}, client_ip(request))
    try:
        cfg = resolve(session, code)
    except LlmUnavailable as exc:
        raise HTTPException(409, f"LLM 설정 미완료: {exc}") from exc
    from nhdip.llm.tools import chat_with_tools

    messages: list[dict[str, Any]] = [{"role": "system", "content": cfg.system_prompt or "You are a helpful assistant."}, {"role": "user", "content": body.message}]
    try:
        out = chat_with_tools(session, cfg, messages, use_tools=body.use_tools, purpose="test")
        session.commit()
        return {"answer": out["answer"], "trace": out["trace"], "model": cfg.model, "toolsUsed": out["tools_used"], **({"error": out["error"]} if out.get("error") else {})}
    except LlmError as exc:
        session.commit()
        raise HTTPException(502, f"LLM 호출 실패: {exc}") from exc


# ═════════════════════════ 판정 규칙 ═════════════════════════
class RuleVersionIn(BaseModel):
    body: dict[str, Any]
    note: str | None = None


class ActivateIn(BaseModel):
    version: int


def _dual_control(session: Session) -> bool:
    """규칙 이중 승인 (B.32 · 설정 governance.dual_control.rules) — 켜면 새 버전은 다른 관리자가 적용해야 활성화된다."""
    st = session.get(Setting, "governance.dual_control")
    v = st.value if st and isinstance(st.value, dict) else {}
    return bool(v.get("enabled")) and bool(v.get("rules", True))


@router.get("/rules")
def rules(session: Session = Depends(get_session)):
    out = []
    dual = _dual_control(session)
    for r in session.execute(select(Rule).order_by(Rule.code)).scalars():
        vs = session.execute(select(RuleVersion).where(RuleVersion.rule_code == r.code).order_by(RuleVersion.version.desc())).scalars().all()
        out.append({"code": r.code, "name": r.name, "kind": r.kind, "description": r.description, "activeVersion": r.active_version, "dualControl": dual,
                    "versions": [{"version": v.version, "body": v.body, "note": v.note, "createdBy": v.created_by, "createdAt": _iso(v.created_at), "pending": dual and v.version > r.active_version} for v in vs]})
    return out


@router.post("/rules/{code}/versions", status_code=201)
def rule_version(code: str, body: RuleVersionIn, request: Request, session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    r = session.get(Rule, code)
    if not r:
        raise HTTPException(404, "규칙 없음")
    from nhdip.locks import lock

    lock(session, f"rule:{code}")
    last = session.execute(select(func.max(RuleVersion.version)).where(RuleVersion.rule_code == code)).scalar() or 0
    session.add(RuleVersion(rule_code=code, version=last + 1, body=body.body, note=body.note, created_by=admin.emp_no))
    dual = _dual_control(session)
    if not dual:
        r.active_version = last + 1
        emit(session, "rule.changed", {"rule": code, "version": last + 1}, admin.emp_no)
    audit(session, admin.emp_no, "admin.rule.version", "rule", code, {"version": last + 1, "body": body.body, "pendingApproval": dual}, client_ip(request))
    session.commit()
    return rules(session)


@router.post("/rules/{code}/activate")
def rule_activate(code: str, body: ActivateIn, request: Request, session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    r = session.get(Rule, code)
    v = session.execute(select(RuleVersion).where(RuleVersion.rule_code == code, RuleVersion.version == body.version)).scalar() if r else None
    if not r or v is None:
        raise HTTPException(404, "규칙 버전 없음")
    if _dual_control(session) and v.created_by == admin.emp_no:
        raise HTTPException(409, "이중 승인 — 직접 만든 규칙 버전은 다른 관리자가 적용해야 합니다")
    r.active_version = body.version
    emit(session, "rule.changed", {"rule": code, "version": body.version}, admin.emp_no)
    audit(session, admin.emp_no, "admin.rule.activate", "rule", code, {"version": body.version}, client_ip(request))
    session.commit()
    return rules(session)
