"""SSO — OpenID Connect Authorization Code + PKCE (F.13 · AUTH-01, 작업 8.4.1).

배포 환경변수 OIDC_ISSUER 를 넣을 때만 켜진다(기본 꺼짐). 클라이언트 비밀은 환경변수로만 받는다.
보안: state(CSRF) · nonce(재전송) · PKCE(S256) · ID 토큰 서명(JWKS) · iss · aud · exp 검증.
계정: ID 토큰의 사번 클레임(OIDC_EMP_CLAIM)으로 기존 사용자와 연결한다. 미등록 · 승인 대기 · 중지 · 잠금 계정은 거부(자동 가입 없음).
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import secrets
import time
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from nhdip.config import get_settings
from nhdip.db import get_session
from nhdip.events import audit
from nhdip.models import AppUser
from nhdip.security import sign_session, unsign_session

from .auth import _home, start_session
from .deps import client_ip

router = APIRouter(prefix="/auth/oidc", tags=["auth"])
FLOW_COOKIE = "nhdip_oidc"
FLOW_TTL = 600
_cache: dict[str, tuple[float, Any]] = {}


def enabled() -> bool:
    st = get_settings()
    return bool(st.oidc_issuer and st.oidc_client_id and st.oidc_redirect_uri)


def _get_json(url: str) -> dict[str, Any]:
    r = httpx.get(url, timeout=10)
    r.raise_for_status()
    return r.json()


def discovery() -> dict[str, Any]:
    st = get_settings()
    hit = _cache.get("disc")
    if hit and time.time() - hit[0] < 3600:
        return hit[1]
    doc = _get_json(st.oidc_issuer.rstrip("/") + "/.well-known/openid-configuration")
    _cache["disc"] = (time.time(), doc)
    return doc


def jwks(force: bool = False) -> dict[str, Any]:
    hit = _cache.get("jwks")
    if hit and not force and time.time() - hit[0] < 3600:
        return hit[1]
    keys = _get_json(discovery()["jwks_uri"])
    _cache["jwks"] = (time.time(), keys)
    return keys


def exchange_code(code: str, verifier: str) -> dict[str, Any]:
    st = get_settings()
    data = {"grant_type": "authorization_code", "code": code, "redirect_uri": st.oidc_redirect_uri, "client_id": st.oidc_client_id, "code_verifier": verifier}
    if st.oidc_client_secret:
        data["client_secret"] = st.oidc_client_secret
    r = httpx.post(discovery()["token_endpoint"], data=data, timeout=10, headers={"Accept": "application/json"})
    r.raise_for_status()
    return r.json()


def verify_id_token(token: str, nonce: str) -> dict[str, Any]:
    st = get_settings()
    header = jwt.get_unverified_header(token)
    alg = header.get("alg")
    if alg not in ("RS256", "RS384", "RS512", "ES256", "ES384", "PS256"):
        raise jwt.InvalidTokenError(f"허용하지 않는 서명 알고리즘: {alg}")
    key = None
    for force in (False, True):  # 키 교체(rotation) 대비 1회 재조회
        for k in jwks(force).get("keys", []):
            if k.get("kid") == header.get("kid") or (header.get("kid") is None and len(jwks().get("keys", [])) == 1):
                key = jwt.PyJWK(k).key
                break
        if key is not None:
            break
    if key is None:
        raise jwt.InvalidTokenError("서명 키(kid)를 찾을 수 없습니다")
    claims = jwt.decode(token, key=key, algorithms=[alg], audience=st.oidc_client_id, issuer=discovery().get("issuer", st.oidc_issuer), options={"require": ["exp", "iat", "iss", "aud", "sub"]}, leeway=60)
    if not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
        raise jwt.InvalidTokenError("nonce 불일치")
    return claims


def _safe_next(n: str | None) -> str:
    # 같은 사이트의 상대 경로만 — 열린 리디렉션 차단
    return n if n and n.startswith("/") and not n.startswith("//") and "\\" not in n and re.fullmatch(r"[\x21-\x7e]{1,300}", n) else ""


@router.get("/config")
def oidc_config():
    st = get_settings()
    return {"enabled": enabled(), "label": st.oidc_label, "localLogin": (st.oidc_local_login if enabled() else "all")}


@router.get("/login")
def oidc_login(next: str | None = Query(None, max_length=300)):
    if not enabled():
        return RedirectResponse("/login?sso_error=disabled", status_code=303)
    st = get_settings()
    state, nonce, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(24), secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    params = {"response_type": "code", "client_id": st.oidc_client_id, "redirect_uri": st.oidc_redirect_uri, "scope": st.oidc_scopes, "state": state, "nonce": nonce, "code_challenge": challenge, "code_challenge_method": "S256"}
    resp = RedirectResponse(discovery()["authorization_endpoint"] + "?" + urlencode(params), status_code=303)
    flow = json.dumps({"s": state, "n": nonce, "v": verifier, "next": _safe_next(next), "t": int(time.time())})
    # 세션 쿠키와 같은 키로 서명하되 용도 접두어로 구분(교차 사용 방지)
    resp.set_cookie(FLOW_COOKIE, sign_session("oidc:" + base64.urlsafe_b64encode(flow.encode()).decode()), max_age=FLOW_TTL, httponly=True, secure=st.cookie_secure, samesite="lax", path="/")
    return resp


def _fail(reason: str) -> RedirectResponse:
    r = RedirectResponse(f"/login?sso_error={reason}", status_code=303)
    r.delete_cookie(FLOW_COOKIE, path="/")
    return r


@router.get("/callback")
def oidc_callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None, session: Session = Depends(get_session)):
    ip = client_ip(request)
    if error or not code or not state:
        audit(session, None, "auth.sso_failed", "user", None, {"reason": error or "missing_code"}, ip)
        session.commit()
        return _fail("denied")
    raw = unsign_session(request.cookies.get(FLOW_COOKIE))
    try:
        flow = json.loads(base64.urlsafe_b64decode(raw[5:].encode()).decode()) if raw and raw.startswith("oidc:") else None
    except (ValueError, UnicodeDecodeError):
        flow = None
    if not flow or not secrets.compare_digest(flow.get("s", ""), state) or time.time() - int(flow.get("t", 0)) > FLOW_TTL:
        audit(session, None, "auth.sso_failed", "user", None, {"reason": "state"}, ip)
        session.commit()
        return _fail("state")
    try:
        tokens = exchange_code(code, flow["v"])
        claims = verify_id_token(tokens.get("id_token", ""), flow["n"])
    except (httpx.HTTPError, jwt.PyJWTError, KeyError, ValueError) as exc:
        audit(session, None, "auth.sso_failed", "user", None, {"reason": "token", "detail": str(exc)[:200]}, ip)
        session.commit()
        return _fail("token")
    emp = str(claims.get(get_settings().oidc_emp_claim) or "")
    user = session.get(AppUser, emp) if re.fullmatch(r"\d{8}", emp) else None
    if user is None or user.status != "active":
        audit(session, emp or None, "auth.sso_failed", "user", emp or None, {"reason": "account", "status": user.status if user else "unknown", "sub": claims.get("sub")}, ip)
        session.commit()
        return _fail("account")
    resp = RedirectResponse(flow.get("next") or _home(session, user), status_code=303)
    start_session(session, user, request, resp, "auth.login_sso", {"sub": claims.get("sub"), "iss": claims.get("iss")})
    resp.delete_cookie(FLOW_COOKIE, path="/")
    return resp
