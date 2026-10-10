"""인증 — 사번(8자리) 가입 · 승인 대기 · 로그인 · 잠금 · 로그아웃 · 내 정보 · 메뉴."""
from __future__ import annotations

import re
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from nhdip.config import get_settings
from nhdip.db import get_session
from nhdip.events import audit
from nhdip.models import AppUser, OrgUnit, Screen, Setting, UserSession, utcnow
from nhdip.security import hash_password, new_session_id, password_policy_error, session_hash, sign_session, verify_password

from .deps import client_ip, current_user, user_json, user_screen_codes
from .menu_counts import menu_counts

router = APIRouter(tags=["auth"])
EMP_RE = re.compile(r"^\d{8}$")
GENERIC_FAIL = "사번 또는 비밀번호가 올바르지 않습니다"


class SignupIn(BaseModel):
    emp_no: str = Field(..., description="사번 8자리")
    name: str = Field(..., min_length=1, max_length=50)
    password: str
    org_code: str
    position: str | None = Field(None, max_length=30)


class LoginIn(BaseModel):
    emp_no: str
    password: str


class PasswordIn(BaseModel):
    current_password: str
    new_password: str


def _setting(session: Session, key: str, default: Any) -> Any:
    s = session.get(Setting, key)
    return s.value if s is not None else default


@router.get("/auth/orgs")
def signup_orgs(session: Session = Depends(get_session)):
    """가입 화면용 조직 트리 (공개)."""
    from nhdip.orgs import depth_labels, type_labels

    orgs = session.execute(select(OrgUnit).where(OrgUnit.active).order_by(OrgUnit.sort, OrgUnit.code)).scalars().all()
    lbl = type_labels(session)
    return {
        "levels": depth_labels(session, orgs),
        "orgs": [{"code": o.code, "name": o.name, "level": o.level, "parent": o.parent_code, "unitType": o.unit_type, "unitLabel": lbl.get(o.unit_type or "", "조직")} for o in orgs],
    }


@router.post("/auth/signup", status_code=201)
def signup(body: SignupIn, request: Request, session: Session = Depends(get_session)):
    from nhdip.ratelimit import check as rate_check

    rate_check(session, "signup_ip", client_ip(request))
    if not EMP_RE.match(body.emp_no):
        raise HTTPException(422, "사번은 숫자 8자리입니다")
    err = password_policy_error(body.password)
    if err:
        raise HTTPException(422, err)
    org = session.get(OrgUnit, body.org_code)
    if not org or not org.active:
        raise HTTPException(422, "소속 조직을 선택하세요")
    if session.get(AppUser, body.emp_no):
        raise HTTPException(409, "이미 가입된 사번입니다")
    needs_approval = bool(_setting(session, "auth.signup_requires_approval", True))
    user = AppUser(emp_no=body.emp_no, name=body.name.strip(), password_hash=hash_password(body.password), org_code=org.code, position=(body.position or "").strip() or None, role="user", status="pending" if needs_approval else "active")
    session.add(user)
    audit(session, body.emp_no, "user.signup", "user", body.emp_no, {"org": org.code}, client_ip(request))
    session.commit()
    return {"empNo": user.emp_no, "status": user.status, "message": "가입 신청이 접수되었습니다. 관리자 승인 후 로그인할 수 있습니다." if needs_approval else "가입되었습니다."}


@router.post("/auth/login")
def login(body: LoginIn, request: Request, response: Response, session: Session = Depends(get_session)):
    from nhdip.ratelimit import check as rate_check

    st = get_settings()
    ip = client_ip(request)
    rate_check(session, "login_ip", ip)
    if not EMP_RE.match(body.emp_no or ""):
        raise HTTPException(401, GENERIC_FAIL)
    rate_check(session, "login_emp", body.emp_no)
    user = session.get(AppUser, body.emp_no)
    if not user:
        verify_password(body.password, "$2b$12$" + "x" * 53)  # 타이밍 균일화
        audit(session, body.emp_no, "auth.login_failed", "user", body.emp_no, {"reason": "unknown"}, ip)
        session.commit()
        raise HTTPException(401, GENERIC_FAIL)
    if user.status == "locked":
        # 시간 경과 잠금 해제 (설정 auth.lockout_minutes, 0 = 관리자만 해제) — 잠금 악용(대상 계정 차단) 완화 (B.32)
        mins = int(_setting(session, "auth.lockout_minutes", 30) or 0)
        if mins and user.updated_at and user.updated_at + timedelta(minutes=mins) <= utcnow():
            user.status, user.failed_count = "active", 0
            audit(session, user.emp_no, "auth.unlock_timeout", "user", user.emp_no, {"minutes": mins}, ip)
            session.commit()
        else:
            raise HTTPException(423, "로그인 실패 횟수 초과로 잠긴 계정입니다. 잠시 후 다시 시도하거나 관리자에게 잠금 해제를 요청하세요.")
    if user.status == "disabled":
        raise HTTPException(403, "사용 중지된 계정입니다")
    if not verify_password(body.password, user.password_hash):
        user.failed_count += 1
        limit = int(_setting(session, "auth.max_failed_logins", 5))
        if user.failed_count >= limit:
            user.status = "locked"
        audit(session, user.emp_no, "auth.login_failed", "user", user.emp_no, {"failed_count": user.failed_count, "locked": user.status == "locked"}, ip)
        session.commit()
        if user.status == "locked":
            raise HTTPException(423, "로그인 실패 횟수 초과로 계정이 잠겼습니다. 관리자에게 잠금 해제를 요청하세요.")
        raise HTTPException(401, GENERIC_FAIL)  # 실패 횟수는 알려 주지 않는다(계정 존재 여부 추정 방지)
    if user.status == "pending":
        raise HTTPException(403, "관리자 승인 대기 중입니다")
    if not local_login_allowed(session, user):
        raise HTTPException(403, "이 계정은 SSO 로 로그인합니다")
    start_session(session, user, request, response, "auth.login")
    return {"user": user_json(session, user), "home": _home(session, user)}


def local_login_allowed(session: Session, user: AppUser) -> bool:
    """사번 · 비밀번호 로그인 허용 범위 — 배포 설정 OIDC_LOCAL_LOGIN: all(기본) · admin(관리자 비상 로그인만) · none."""
    st = get_settings()
    if not st.oidc_issuer:
        return True
    mode = (st.oidc_local_login or "all").lower()
    return mode == "all" or (mode == "admin" and user.role == "admin")


def start_session(session: Session, user: AppUser, request: Request, response: Response, action: str, detail: dict | None = None) -> None:
    """세션 생성 + 쿠키(HttpOnly · SameSite=Lax) — 사번 로그인 · SSO 공통."""
    st = get_settings()
    ip = client_ip(request)
    sid = new_session_id()
    now = utcnow()
    session.add(UserSession(id_hash=session_hash(sid), emp_no=user.emp_no, created_at=now, last_seen_at=now, expires_at=now + timedelta(hours=st.session_ttl_hours), ip=ip, user_agent=(request.headers.get("user-agent") or "")[:300]))
    user.failed_count = 0
    user.last_login_at = now
    audit(session, user.emp_no, action, "user", user.emp_no, detail, ip)
    session.commit()
    response.set_cookie(st.session_cookie, sign_session(sid), max_age=st.session_ttl_hours * 3600, httponly=True, secure=st.cookie_secure, samesite="lax", path="/")


@router.post("/auth/logout")
def logout(request: Request, response: Response, session: Session = Depends(get_session)):
    from nhdip.security import unsign_session

    st = get_settings()
    sid = unsign_session(request.cookies.get(st.session_cookie))
    if sid:
        us = session.get(UserSession, session_hash(sid))
        if us and not us.revoked_at:
            us.revoked_at = utcnow()
            audit(session, us.emp_no, "auth.logout", "user", us.emp_no, None, client_ip(request))
            session.commit()
    response.delete_cookie(st.session_cookie, path="/")
    return {"ok": True}


@router.post("/auth/password")
def change_password(body: PasswordIn, request: Request, user: AppUser = Depends(current_user), session: Session = Depends(get_session)):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, "현재 비밀번호가 올바르지 않습니다")
    err = password_policy_error(body.new_password)
    if err:
        raise HTTPException(422, err)
    user.password_hash = hash_password(body.new_password)
    # 다른 세션 모두 폐기
    for us in session.execute(select(UserSession).where(UserSession.emp_no == user.emp_no, UserSession.revoked_at.is_(None), UserSession.id_hash != request.state.session_id_hash)).scalars():
        us.revoked_at = utcnow()
    audit(session, user.emp_no, "user.password_changed", "user", user.emp_no, None, client_ip(request))
    session.commit()
    return {"ok": True}


def _home(session: Session, user: AppUser) -> str:
    codes = user_screen_codes(session, user)
    screens = session.execute(select(Screen).where(Screen.code.in_(codes), Screen.kind.in_(["flow", "reference", "admin"])).order_by(Screen.sort)).scalars().all()
    biz = [s for s in screens if s.kind != "admin"]
    return (biz or screens)[0].path if (biz or screens) else "/"


@router.get("/me")
def me(user: AppUser = Depends(current_user), session: Session = Depends(get_session)):
    return {"user": user_json(session, user), "screens": sorted(user_screen_codes(session, user)), "home": _home(session, user)}


@router.get("/me/menu")
def my_menu(user: AppUser = Depends(current_user), session: Session = Depends(get_session)):
    codes = user_screen_codes(session, user)
    screens = session.execute(select(Screen).where(Screen.code.in_(codes)).order_by(Screen.sort)).scalars().all()
    sections: dict[str, dict[str, Any]] = {}
    for s in screens:
        if s.kind == "hidden":
            continue
        sec = sections.setdefault(s.section, {"section": s.section, "admin": s.kind == "admin", "flow": [], "reference": [], "sort": s.sort})
        item = {
            "code": s.code,
            "label": s.label,
            "href": s.path,
            "match": [m.strip() for m in (s.match or s.path).split(",") if m.strip()],
            "step": s.step,
            "countKey": s.count_key,
        }
        (sec["flow"] if s.kind == "flow" else sec["reference"]).append(item)
    ui_as_of = session.get(Setting, "ui.as_of")
    batch = session.get(Setting, "ui.batch_label")
    return {
        "user": user_json(session, user),
        "home": _home(session, user),
        "sections": sorted(sections.values(), key=lambda x: x["sort"]),
        "screens": sorted(codes),
        "counts": menu_counts(session, user),
        "asOf": ui_as_of.value if ui_as_of else get_settings().as_of_default,
        "batchLabel": batch.value if batch else "",
    }
