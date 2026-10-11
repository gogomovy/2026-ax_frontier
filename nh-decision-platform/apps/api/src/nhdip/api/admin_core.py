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

from .deps import client_ip, require_admin, user_json

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
    litellm: dict[str, Any] = {"ok": False}
    if conn:
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


class PasswordReset(BaseModel):
    password: str


@router.get("/users")
def users(status: str | None = None, session: Session = Depends(get_session)):
    q = select(AppUser).order_by(AppUser.status != "pending", AppUser.created_at.desc())
    if status:
        q = q.where(AppUser.status == status)
    return [{**user_json(session, u), "failedCount": u.failed_count, "createdAt": _iso(u.created_at), "approvedBy": u.approved_by, "approvedAt": _iso(u.approved_at)} for u in session.execute(q).scalars()]


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
    for k, v in patch.items():
        setattr(a, k, v)
    emit(session, "config.changed", {"kind": "agent", "code": code}, admin.emp_no)
    audit(session, admin.emp_no, "admin.agent.update", "agent", code, patch, client_ip(request))
    session.commit()
    return _agent_json(session, a)


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
