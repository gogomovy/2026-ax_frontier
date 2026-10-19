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

from .deps import client_ip, current_user, user_json, user_resources, user_screen_codes
from .menu_counts import menu_counts

router = APIRouter(tags=["auth"])
EMP_RE = re.compile(r"^\d{8}$")
# 로그인 아이디 — 가입 사번(8자리) 또는 인사 .dat 개인번호(Phase R · 동기화 형식과 같음)
LOGIN_ID_RE = re.compile(r"^[0-9A-Za-z]{1,20}$")
GENERIC_FAIL = "사번 또는 비밀번호가 올바르지 않습니다"
PW_REQUEST = "pwRequest"  # app_user.hr 안 — 인사 동기화 사번의 사번 · 비밀번호 로그인 신청(관리자 승인 대기)


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


def _hr_user(session: Session, emp_no: str | None) -> AppUser | None:
    """인사 .dat 동기화로 들어온 사번(Phase R) — 가입 화면이 소속 · 이름을 인사 정보로 채운다."""
    if not emp_no or not LOGIN_ID_RE.match(emp_no):
        return None
    u = session.get(AppUser, emp_no)
    return u if u is not None and (u.source or "local") == "dat" else None


def _same_name(a: str | None, b: str | None) -> bool:
    return re.sub(r"\s+", "", a or "") == re.sub(r"\s+", "", b or "") != ""


def _mask_name(name: str) -> str:
    n = (name or "").strip()
    return "*" if len(n) <= 1 else n[0] + "*" if len(n) == 2 else n[0] + "*" * (len(n) - 2) + n[-1]


@router.get("/auth/signup/lookup")
def signup_lookup(emp_no: str, request: Request, session: Session = Depends(get_session)):
    """가입 화면 — 사번이 인사 정보(.dat 동기화)에 있으면 소속을 자동 선택한다 (공개 · 속도 제한).
    이름은 가려서(홍*동) 본인 확인용으로만 보여 준다. 설정 auth.signup_hr_prefill=false 면 끈다."""
    from nhdip.orgs import org_chain
    from nhdip.ratelimit import check as rate_check

    rate_check(session, "signup_lookup_ip", client_ip(request))
    if not bool(_setting(session, "auth.signup_hr_prefill", True)):
        return {"found": False}
    u = _hr_user(session, emp_no)
    if u is None:
        return {"found": False, "registered": bool(LOGIN_ID_RE.match(emp_no or "") and session.get(AppUser, emp_no) is not None)}
    if (u.hr or {}).get(PW_REQUEST):
        return {"found": False, "registered": True, "pending": True}
    if u.password_hash or u.status != "active":
        return {"found": False, "registered": True}
    org = session.get(OrgUnit, u.org_code) if u.org_code else None
    if org is None or not org.active:
        return {"found": False}
    return {
        "found": True,
        "name": _mask_name(u.name),
        "orgCode": org.code,
        "orgPath": [o.name for o in reversed(org_chain(session, org.code))],  # 최상위 → 소속
        "position": u.position,
    }


def _claim_hr_user(session: Session, u: AppUser, body: SignupIn, request: Request) -> dict[str, Any]:
    """인사 동기화 사번의 가입 = 사번 · 비밀번호 로그인 신청. 소속 · 이름은 인사 정보 그대로(다음 동기화도 덮어쓴다).
    남의 사번으로 비밀번호를 걸지 못하게 이름을 대조하고, 승인 설정과 무관하게 관리자 승인 후에만 비밀번호 로그인이 된다.
    신청 중에도 계정은 사용 상태라 사내 SSO 로그인은 그대로 된다."""
    if (u.hr or {}).get(PW_REQUEST):
        raise HTTPException(409, "이미 가입 신청이 접수된 사번입니다 (관리자 승인 대기)")
    if u.password_hash or u.status != "active":
        raise HTTPException(409, "이미 가입된 사번입니다")
    if not _same_name(body.name, u.name):
        raise HTTPException(422, "인사 정보의 이름과 다릅니다 — 본인 이름을 그대로 입력하세요")
    err = password_policy_error(body.password)
    if err:
        raise HTTPException(422, err)
    u.password_hash = hash_password(body.password)
    u.failed_count = 0
    u.hr = {**(u.hr or {}), PW_REQUEST: {"at": utcnow().isoformat(), "ip": client_ip(request)}}
    audit(session, u.emp_no, "user.signup_hr", "user", u.emp_no, {"org": u.org_code}, client_ip(request))
    session.commit()
    return {"empNo": u.emp_no, "status": "pending", "message": "인사 정보로 확인했습니다. 관리자 승인 후 사번 · 비밀번호로 로그인할 수 있습니다. (사내 SSO 로그인은 지금도 됩니다)"}


@router.post("/auth/signup", status_code=201)
def signup(body: SignupIn, request: Request, session: Session = Depends(get_session)):
    from nhdip.ratelimit import check as rate_check

    rate_check(session, "signup_ip", client_ip(request))
    hr_user = _hr_user(session, body.emp_no)
    if hr_user is not None:
        return _claim_hr_user(session, hr_user, body, request)
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
    if not LOGIN_ID_RE.match(body.emp_no or ""):
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
    if not user.password_hash:
        # 인사 .dat 동기화 계정(SSO 전용 · 비밀번호 없음, Phase R) — 실패 횟수를 올리지 않는다(남이 사번으로 잠가 SSO 를 막지 못하게)
        verify_password(body.password, "$2b$12$" + "x" * 53)
        audit(session, user.emp_no, "auth.login_failed", "user", user.emp_no, {"reason": "sso_only"}, ip)
        session.commit()
        raise HTTPException(401, GENERIC_FAIL)
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
    if user.status == "pending" or (user.hr or {}).get(PW_REQUEST):
        raise HTTPException(403, "관리자 승인 대기 중입니다")
    if not local_login_allowed(session, user):
        raise HTTPException(403, "이 계정은 SSO 로 로그인합니다")
    start_session(session, user, request, response, "auth.login")
    return {"user": user_json(session, user), "home": _home(session, user)}


def local_login_allowed(session: Session, user: AppUser) -> bool:
    """사번 · 비밀번호 로그인 허용 범위 — 배포 설정 OIDC_LOCAL_LOGIN: all(기본) · admin(관리자 비상 로그인만) · none."""
    st = get_settings()
    modes = []
    if st.oidc_issuer:
        modes.append((st.oidc_local_login or "all").lower())
    if st.nc_sso_enabled:  # 사내 SSO(NC · Phase R) — NC_SSO_LOCAL_LOGIN
        modes.append((st.nc_sso_local_login or "all").lower())
    return all(m == "all" or (m == "admin" and user.role == "admin") for m in modes)


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
    # 관리자의 첫 화면은 [관리자 홈] — 처리할 일 · 시스템 상태부터 (Phase E · NAV-01 · Q122)
    if user.role == "admin":
        home = next((s for s in screens if s.code == "ADMIN_HOME"), None)
        if home is not None:
            return home.path
    biz = [s for s in screens if s.kind != "admin"]
    # 볼 화면이 하나도 없으면(업무 구성 전 · 권한 없음) '/' 로 돌려보내면 자기 자신으로 계속 넘어간다 — 권한 안내 화면으로
    return (biz or screens)[0].path if (biz or screens) else "/forbidden?from=/"


def _data_origin(session: Session) -> str:
    """현재 버전 데이터의 성격 (Phase E · NAV-05 · Q124) — simulated · mixed · actual · none(자료 없음)."""
    from nhdip.models import source

    kinds: set[str] = set()
    for origin in ("bank", "ext"):
        t = source(origin)
        kinds |= {str(x or "simulated") for x in session.execute(select(t.version.data_origin).where(t.version.is_current).distinct()).scalars()}
    if not kinds:
        return "none"
    if kinds == {"actual"}:
        return "actual"
    return "simulated" if "actual" not in kinds else "mixed"


@router.get("/me")
def me(user: AppUser = Depends(current_user), session: Session = Depends(get_session)):
    return {"user": user_json(session, user), "screens": sorted(user_screen_codes(session, user)), "home": _home(session, user)}


def _match_len(path: str, pattern: str) -> int:
    """화면 활성 판정 접두어(`=` 이면 정확히 같을 때만)와 주소의 일치 길이 — 맞지 않으면 -1 (웹 lib/nav.ts 와 같은 규칙)."""
    exact = pattern.startswith("=")
    p = pattern[1:] if exact else pattern
    if not p:
        return -1
    if path == p:
        return len(p)
    if not exact and path.startswith(p.rstrip("/") + "/"):
        return len(p)
    return -1


@router.get("/me/screen")
def screen_for_path(path: str, user: AppUser = Depends(current_user), session: Session = Depends(get_session)):
    """권한 없음 안내용 — 주소에 맞는 화면 이름 · 묶음 · 권한 여부 (Phase E · NAV-03). 화면 이름만 알려 주고 내용은 주지 않는다."""
    path = path.split("?", 1)[0][:200]
    best: Screen | None = None
    best_len = -1
    for s in session.execute(select(Screen).where(Screen.active, Screen.kind != "hidden")).scalars():
        n = max((_match_len(path, m.strip()) for m in (s.match or s.path).split(",") if m.strip()), default=-1)
        if n > best_len:
            best, best_len = s, n
    if best is None:
        return {"screen": None}
    admin = bool(best.admin_only or best.kind == "admin")
    return {
        "screen": {"code": best.code, "label": best.label, "section": best.section, "admin": admin},
        "granted": best.code in user_screen_codes(session, user),
        "home": _home(session, user),
    }


@router.get("/me/menu")
def my_menu(user: AppUser = Depends(current_user), session: Session = Depends(get_session)):
    from nhdip.ui_config import client_config, section_scopes

    codes = user_screen_codes(session, user)
    screens = session.execute(select(Screen).where(Screen.code.in_(codes)).order_by(Screen.sort)).scalars().all()
    # 메뉴 묶음 → 업무 영역(종류 · 조직) — 설정 ui.scopes 의 단위와 이름으로 맞춘다 (Phase K · SCP-01 · Q151)
    owners = section_scopes(session)
    sections: dict[str, dict[str, Any]] = {}
    for s in screens:
        if s.kind == "hidden":
            continue
        own = owners.get(s.section) or {}
        sec = sections.setdefault(
            s.section,
            {"section": s.section, "admin": s.kind == "admin", "flow": [], "reference": [], "sort": s.sort, "scope": None if s.kind == "admin" else own.get("scope"), "orgCode": own.get("orgCode"), "orgName": own.get("orgName") or s.section},
        )
        item = {
            "code": s.code,
            "label": s.label,
            "href": s.path,
            "match": [m.strip() for m in (s.match or s.path).split(",") if m.strip()],
            "step": s.step,
            "countKey": s.count_key,
        }
        (sec["flow"] if s.kind == "flow" else sec["reference"]).append(item)
    from nhdip.data.datasets import display_as_of

    batch = session.get(Setting, "ui.batch_label")
    return {
        "user": user_json(session, user),
        "home": _home(session, user),
        "sections": sorted(sections.values(), key=lambda x: x["sort"]),
        "screens": sorted(codes),
        "counts": menu_counts(session, user),
        "asOf": display_as_of(session),  # 관리자 지정 기준일 또는 올라온 자료의 최신 기준일 (자료가 없으면 null)
        "batchLabel": batch.value if batch else "",
        "dataOrigin": _data_origin(session),
        # 화면 설정 (Phase K · Q148) — 판정 구간 · 기준값 · 목표 역할 · 업무 영역 단위 · 예시 질문 · 알림 · 지점 목록
        "config": client_config(session, user, branch=_has_resource(session, user, "branch_dashboard")),
    }


def _has_resource(session: Session, user: AppUser, resource: str) -> bool:
    allowed = user_resources(session, user)
    return allowed is None or resource in allowed
