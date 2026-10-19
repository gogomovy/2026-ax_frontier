"""사내 SSO 로그인 — INISAFE Nexess(NC) 티켓 방식 (Phase R · 가이드 §2).

흐름(같은 출처 /backend/* 로 프록시):
  ① GET /auth/nc/init        nonce 생성 → 서명 쿠키(5분 · HttpOnly) → 302 /sso-proxy.html?nonce&callback&loginUrl
  ② /sso-proxy.html          사용자 PC 의 NC 에이전트(https://127.0.0.1:13015)에서 nonce 로 티켓을 받는다(미로그인이면 NLS 로그인)
  ③ GET /auth/nc/callback    티켓 검증(검증기 · nonce 대조) → TOA 허용 → 사번으로 사용자 조회 → 세션 쿠키 → 첫 화면
가이드 구현과 다른 점: nonce 를 실제로 대조하고 1회용으로 지운다 · 토큰을 주소에 싣지 않는다(세션 쿠키) · 사용 중지 사용자를 다시 켜지 않는다(설정).
계정: 인사 .dat 동기화로 들어온 사번만(설정 sso.auto_create_user=false 기본). 권한은 소속 조직 화면 권한 · 역할(관리자 지정)로 정해진다.
"""
from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import quote, urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.orm import Session

from nhdip import ncsso
from nhdip.config import get_settings
from nhdip.db import get_session
from nhdip.events import audit
from nhdip.models import AppUser, OrgUnit, Setting
from nhdip.security import hash_password, sign_session, unsign_session

from .auth import _home, start_session
from .deps import client_ip

router = APIRouter(prefix="/auth/nc", tags=["auth"])
CALLBACK = "/backend/auth/nc/callback"
ASSET_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,80}\.js$")


def _setting(session: Session, key: str, default: Any) -> Any:
    s = session.get(Setting, key)
    return s.value if s is not None and s.value is not None else default


def _safe_next(n: str | None) -> str:
    return n if n and n.startswith("/") and not n.startswith("//") and "\\" not in n and re.fullmatch(r"[\x21-\x7e]{1,300}", n) else ""


@router.get("/config")
def nc_config():
    st = get_settings()
    return {"enabled": ncsso.enabled(), "label": st.nc_sso_label, "localLogin": (st.nc_sso_local_login if ncsso.enabled() else "all")}


@router.get("/init")
def nc_init(next: str | None = Query(None, max_length=300), retry: int = Query(0, ge=0, le=1)):
    if not ncsso.enabled():
        return RedirectResponse("/login?sso_error=disabled", status_code=303)
    st = get_settings()
    nonce = ncsso.new_nonce()
    params = {"nonce": nonce, "callback": CALLBACK, "loginUrl": st.nc_sso_login_url}
    if st.nc_sso_verifier == "stub" and st.nhdip_env != "prod":
        params["stub"] = "1"  # 개발 — 에이전트 없이 사번을 넣어 흐름을 시험
    resp = RedirectResponse("/sso-proxy.html?" + urlencode(params, quote_via=quote), status_code=303)
    # nonce 는 서명 쿠키로 콜백까지 — 서버 저장소 없이 여러 API 인스턴스에서 같게 검증(세션 서명 키 · 용도 접두어 'ncsso:')
    resp.set_cookie(ncsso.FLOW_COOKIE, sign_session(ncsso.flow_value(nonce, _safe_next(next), retry)), max_age=ncsso.FLOW_TTL, httponly=True, secure=st.cookie_secure, samesite="lax", path="/")
    return resp


def _fail(session: Session, request: Request, code: str, detail: str = "", emp: str | None = None) -> RedirectResponse:
    audit(session, emp, "auth.nc_sso_failed", "user", emp, {"reason": code, "detail": detail[:200]}, client_ip(request))
    session.commit()
    r = RedirectResponse(f"/login?sso_error={code}", status_code=303)
    r.delete_cookie(ncsso.FLOW_COOKIE, path="/")
    return r


def _auto_create(session: Session, emp: str) -> AppUser | None:
    """미동기화 사번 자동 생성(설정 sso.auto_create_user — 기본 끔). 소속은 설정 sso.default_org(없으면 만들지 않음)."""
    org_code = _setting(session, "sso.default_org", None)
    org = session.get(OrgUnit, str(org_code)) if org_code else None
    if org is None or not org.active:
        return None
    import secrets

    u = AppUser(emp_no=emp, name=emp, password_hash=hash_password(secrets.token_urlsafe(32)), org_code=org.code, role="user", status="active", source="sso", hr={})
    session.add(u)
    session.flush()
    return u


@router.get("/callback")
def nc_callback(request: Request, ticket: str | None = None, nlsurl: str | None = None, session: Session = Depends(get_session)):
    if not ncsso.enabled():
        return RedirectResponse("/login?sso_error=disabled", status_code=303)
    flow = ncsso.read_flow(unsign_session(request.cookies.get(ncsso.FLOW_COOKIE)))
    if flow is None:
        return _fail(session, request, "state", "nonce 쿠키 없음 · 만료")
    ticket = ncsso.clean_ticket(ticket)
    if not ticket:
        # NLS 로그인 뒤 티켓 없이 돌아온 경우 — 한 번만 처음부터 다시(에이전트가 이제 로그인 상태라 티켓을 준다)
        if int(flow.get("r") or 0) < 1:
            nxt = flow.get("next") or ""
            return RedirectResponse("/backend/auth/nc/init?retry=1" + (f"&next={quote(nxt, safe='')}" if nxt else ""), status_code=303)
        return _fail(session, request, "no_ticket")
    try:
        res = ncsso.verify(ticket, str(flow.get("n") or ""))
    except ncsso.SsoError as exc:
        return _fail(session, request, exc.code, exc.detail)
    emp = res.sso_id
    user = session.get(AppUser, emp)
    if user is None and bool(_setting(session, "sso.auto_create_user", False)):
        user = _auto_create(session, emp)
    if user is None:
        return _fail(session, request, "user_not_found", "인사 동기화에 없는 사번", emp)
    if user.status == "disabled":
        if not bool(_setting(session, "sso.reactivate_disabled", False)):
            return _fail(session, request, "account", "사용 중지된 계정", emp)
        user.status = "active"
    if user.status != "active":
        return _fail(session, request, "account", f"계정 상태 {user.status}", emp)
    resp = RedirectResponse(flow.get("next") or _home(session, user), status_code=303)
    start_session(session, user, request, resp, "auth.login_nc_sso", {"toa": res.toa, "nls": (nlsurl or "")[:200] or None})
    resp.delete_cookie(ncsso.FLOW_COOKIE, path="/")  # nonce 1회용
    return resp


@router.get("/assets/{name}")
def nc_asset(name: str):
    """벤더 NC JS(NexessDemonFunc.js · json2.js · jquery-3.5.1(.min).js) — 배포 시 넣은 폴더(NC_SSO_ASSETS_DIR)에서. 웹이 /nc/* 로 연결한다."""
    if not ASSET_RE.match(name):
        raise HTTPException(404, "없음")
    base = os.path.realpath(get_settings().nc_sso_assets_dir)
    path = os.path.realpath(os.path.join(base, name))
    if not path.startswith(base + os.sep) or not os.path.isfile(path):
        raise HTTPException(404, "NC 스크립트가 배포되지 않았습니다 — infra/sso/nc-js 에 벤더 JS 를 넣으세요")
    return FileResponse(path, media_type="application/javascript", headers={"Cache-Control": "public, max-age=3600"})
