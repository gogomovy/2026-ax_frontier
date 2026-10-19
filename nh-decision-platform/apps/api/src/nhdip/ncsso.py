"""사내 SSO — INISAFE Nexess(NC) 티켓 검증 (Phase R · 가이드 SSO-ORG-SYNC-INTEGRATION-GUIDE §2).

티켓 = encNonce&&encSKIPAndTime&&encIDAndTOA. 복호화 알고리즘 · 키는 벤더 jar(com.initech.eam.nls.TicketV3) 안에 있어
파이썬에서 직접 풀 수 없다 — 같은 내부망의 검증기 서비스(infra/sso-verifier, 벤더 jar 를 쓰는 작은 Java 프로그램)에 맡긴다.

    verifier=http  POST {url}/verify (ticket, nonce) + X-Verifier-Token → {"ok":true,"ssoId":"사번","toa":3}
    verifier=stub  개발 · 시험 전용(운영 기동 거부) — 티켓 'stub:<사번>:<toa>:<nonce>'

가이드 구현의 알려진 문제를 고친다: 콜백에서 nonce 를 검증한다(1회용 · 서명 쿠키), 토큰을 주소에 싣지 않는다(세션 쿠키만).
"""
from __future__ import annotations

import base64
import json
import re
import secrets
import time
from dataclasses import dataclass

import httpx

from nhdip.config import get_settings

FLOW_COOKIE = "nhdip_ncsso"
FLOW_TTL = 300  # nonce 유효 5분 (가이드 NONCE_TTL)
EMP_RE = re.compile(r"^[0-9A-Za-z]{1,20}$")


class SsoError(Exception):
    """사용자에게 보일 실패 사유 코드 — no_ticket · verify_failed · toa · nonce · verifier_down."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(detail or code)
        self.code = code
        self.detail = detail


@dataclass
class VerifyResult:
    sso_id: str
    toa: int


def enabled() -> bool:
    return bool(get_settings().nc_sso_enabled)


def allowed_toa() -> set[int]:
    out = set()
    for x in (get_settings().nc_sso_allowed_toa or "").split(","):
        x = x.strip()
        if x.isdigit():
            out.add(int(x))
    return out


def new_nonce() -> str:
    # 가이드와 같은 모양(무작위 8바이트 → Base64, 개행 없음) — 에이전트 · NLS 가 다루는 길이
    return base64.b64encode(secrets.token_bytes(8)).decode("ascii")


def flow_value(nonce: str, nxt: str, retry: int = 0) -> str:
    return "ncsso:" + base64.urlsafe_b64encode(json.dumps({"n": nonce, "next": nxt, "r": retry, "t": int(time.time())}).encode()).decode()


def read_flow(raw: str | None) -> dict | None:
    if not raw or not raw.startswith("ncsso:"):
        return None
    try:
        flow = json.loads(base64.urlsafe_b64decode(raw[6:].encode()).decode())
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(flow, dict) or time.time() - int(flow.get("t", 0)) > FLOW_TTL:
        return None
    return flow


def clean_ticket(ticket: str | None) -> str:
    # 가이드 AuthController — HTML 엔티티로 바뀐 구분자를 되돌린다
    return (ticket or "").replace("&amp;", "&").strip()


def verify(ticket: str, nonce: str) -> VerifyResult:
    """티켓 → (사번, TOA). nonce 는 티켓 안의 암호화된 nonce 와 같아야 한다(재전송 방지)."""
    st = get_settings()
    if not ticket:
        raise SsoError("no_ticket")
    if st.nc_sso_verifier == "stub":
        if st.nhdip_env == "prod":
            raise SsoError("verify_failed", "운영에서 stub 검증기는 쓸 수 없습니다")
        parts = ticket.split(":")
        if len(parts) != 4 or parts[0] != "stub" or not parts[2].isdigit():
            raise SsoError("verify_failed", "stub 티켓 형식 오류")
        if not secrets.compare_digest(parts[3], nonce):
            raise SsoError("nonce", "nonce 불일치")
        return _result(parts[1], int(parts[2]))
    try:
        r = httpx.post(st.nc_sso_verifier_url.rstrip("/") + "/verify", data={"ticket": ticket, "nonce": nonce},
                       headers={"X-Verifier-Token": st.nc_sso_verifier_token}, timeout=10)
    except httpx.HTTPError as exc:
        raise SsoError("verifier_down", f"검증기 연결 실패: {str(exc)[:150]}") from exc
    try:
        body = r.json()
    except ValueError as exc:
        raise SsoError("verifier_down", f"검증기 응답 오류 HTTP {r.status_code}") from exc
    if r.status_code != 200 or not body.get("ok"):
        code = str(body.get("error") or "verify_failed")
        raise SsoError("nonce" if code == "nonce" else "verify_failed", str(body.get("detail") or code)[:200])
    try:
        return _result(str(body.get("ssoId") or ""), int(body.get("toa")))
    except (TypeError, ValueError) as exc:
        raise SsoError("verify_failed", "검증기 응답에 사번 · TOA 가 없습니다") from exc


def _result(sso_id: str, toa: int) -> VerifyResult:
    sso_id = sso_id.strip()
    if not EMP_RE.match(sso_id):
        raise SsoError("verify_failed", "티켓의 사번 형식이 올바르지 않습니다")
    if toa not in allowed_toa():
        raise SsoError("toa", f"허용하지 않는 인증 방식(TOA {toa})")
    return VerifyResult(sso_id, toa)


def verifier_health() -> dict:
    st = get_settings()
    if not enabled():
        return {"enabled": False}
    if st.nc_sso_verifier == "stub":
        return {"enabled": True, "verifier": "stub", "ok": st.nhdip_env != "prod"}
    try:
        r = httpx.get(st.nc_sso_verifier_url.rstrip("/") + "/health", timeout=5)
        return {"enabled": True, "verifier": "http", "ok": r.status_code == 200, "detail": r.text[:200]}
    except httpx.HTTPError as exc:
        return {"enabled": True, "verifier": "http", "ok": False, "detail": str(exc)[:200]}
