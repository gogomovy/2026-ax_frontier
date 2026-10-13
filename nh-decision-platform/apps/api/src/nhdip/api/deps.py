"""인증 · 권한 의존성 (AUTH-06~10, 설계 §19.7).

권한 = 사용자 조직 + 모든 상위 조직의 화면 권한(screen_grant) 합집합.
API 는 화면이 쓰는 리소스 키(setting 'screen.resources') 단위로 같은 판정을 강제한다.
관리자(role=admin)는 전 화면·전 리소스.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from nhdip import obs
from nhdip.config import get_settings
from nhdip.db import get_session
from nhdip.models import AppUser, OrgUnit, Screen, ScreenGrant, Setting, UserSession, utcnow
from nhdip.security import session_hash, unsign_session

COMMON_RESOURCES = {"terms", "meta", "menu", "assist"}  # assist 는 답변 안의 지표를 사용자 권한으로 다시 거른다


_NETS: dict[str, Any] = {"at": 0.0, "nets": []}


def _trusted_nets():
    """신뢰 프록시 목록 — CIDR 또는 호스트 이름(예: compose 의 web). 이름은 60초마다 다시 해석한다."""
    import ipaddress
    import socket
    import time

    if time.monotonic() - _NETS["at"] < 60 and _NETS["nets"]:
        return _NETS["nets"]
    from nhdip.config import get_settings

    out = []
    for x in get_settings().trusted_proxies.split(","):
        x = x.strip()
        if not x:
            continue
        try:
            out.append(ipaddress.ip_network(x, strict=False))
        except ValueError:
            try:
                for ai in socket.getaddrinfo(x, None):
                    out.append(ipaddress.ip_network(ai[4][0].split("%", 1)[0]))
            except OSError:
                pass
    _NETS.update(at=time.monotonic(), nets=out)
    return out


def client_ip(request: Request) -> str | None:
    """요청한 사용자 IP (B.33) — 바로 앞이 신뢰 프록시(설정 TRUSTED_PROXIES — 기본: 이 컴퓨터 · compose 의 web 컨테이너)일 때만
    X-Forwarded-For 의 오른쪽에서 TRUSTED_PROXY_HOPS(기본 1 = Next 가 붙인 값)번째를 쓴다.
    사용자가 보낸 앞쪽 값은 보지 않으므로 위조할 수 없다. 속도 제한 · 감사 기록 기준."""
    import ipaddress

    from nhdip.config import get_settings

    peer = request.client.host if request.client else None
    try:
        trusted = peer is not None and any(ipaddress.ip_address(peer) in n for n in _trusted_nets())
    except ValueError:
        trusted = False
    if not trusted:
        return peer
    chain = [h.strip() for h in (request.headers.get("x-forwarded-for") or "").split(",") if h.strip()]
    hops = max(1, int(get_settings().trusted_proxy_hops))
    return chain[-hops][:64] if len(chain) >= hops else peer


from nhdip.orgs import org_chain  # noqa: E402,F401 — 조직 경로는 핵심 계층(orgs)에서 제공(계층 규칙)


def user_screen_codes(session: Session, user: AppUser) -> set[str]:
    screens = session.execute(select(Screen).where(Screen.active)).scalars().all()
    if user.role == "admin":
        return {s.code for s in screens}
    orgs = [o.code for o in org_chain(session, user.org_code)]
    granted = set(session.execute(select(ScreenGrant.screen_code).where(ScreenGrant.org_code.in_(orgs))).scalars())
    return {s.code for s in screens if s.code in granted and not s.admin_only}


def user_resources(session: Session, user: AppUser, screens: set[str] | None = None) -> set[str] | None:
    """None = 제한 없음(관리자)."""
    if user.role == "admin":
        return None
    screens = screens if screens is not None else user_screen_codes(session, user)
    s = session.get(Setting, "screen.resources")
    mapping: dict[str, list[str]] = s.value if s else {}
    res = set(COMMON_RESOURCES)
    for code in screens:
        res |= set(mapping.get(code, []))
    return res


def _idle_minutes(session: Session) -> int:
    s = session.get(Setting, "auth.session_idle_minutes")
    return int(s.value) if s else 120


def current_user(request: Request, session: Session = Depends(get_session)) -> AppUser:
    sid = unsign_session(request.cookies.get(get_settings().session_cookie))
    if not sid:
        raise HTTPException(401, "로그인이 필요합니다")
    us = session.get(UserSession, session_hash(sid))
    now = utcnow()
    if not us or us.revoked_at or us.expires_at < now or us.last_seen_at + timedelta(minutes=_idle_minutes(session)) < now:
        raise HTTPException(401, "세션이 만료되었습니다")
    user = session.get(AppUser, us.emp_no)
    if not user or user.status != "active":
        raise HTTPException(401, "사용할 수 없는 계정입니다")
    if (now - us.last_seen_at).total_seconds() > 60:
        us.last_seen_at = now
        session.commit()
    request.state.user = user
    request.state.session_id_hash = us.id_hash
    obs.note("actor", user.emp_no)
    return user


def require_admin(user: AppUser = Depends(current_user)) -> AppUser:
    if user.role != "admin":
        raise HTTPException(403, "관리자 권한이 필요합니다")
    return user


def is_data_admin(user: AppUser) -> bool:
    """데이터 관리자 (Phase J · DEL-01 · Q143) — 관리자 중 지정된 사람. 업로드 자료(데이터셋 버전 · 문서) 삭제 권한."""
    return user.role == "admin" and bool(getattr(user, "data_admin", False))


def require_data_admin(user: AppUser = Depends(current_user)) -> AppUser:
    if not is_data_admin(user):
        raise HTTPException(403, "데이터 관리자 권한이 필요합니다(업로드 자료 삭제는 [사용자]에서 '데이터 관리자'로 지정된 관리자만 할 수 있습니다)")
    return user


def require_resource(resource: str):
    def dep(user: AppUser = Depends(current_user), session: Session = Depends(get_session)) -> AppUser:
        allowed = user_resources(session, user)
        if allowed is not None and resource not in allowed:
            raise HTTPException(403, f"이 화면에 대한 권한이 없습니다 ({resource})")
        return user

    return dep


def user_json(session: Session, user: AppUser) -> dict[str, Any]:
    from nhdip.orgs import type_labels

    chain = org_chain(session, user.org_code)
    labels = type_labels(session)
    return {
        "empNo": user.emp_no,
        "name": user.name,
        "position": user.position,
        "role": user.role,
        "status": user.status,
        "org": {"code": user.org_code, "name": chain[0].name if chain else user.org_code},
        "orgPath": [{"code": o.code, "name": o.name, "level": o.level, "unitType": o.unit_type, "levelLabel": labels.get(o.unit_type or "", "조직")} for o in reversed(chain)],
        "lastLoginAt": user.last_login_at.isoformat() if user.last_login_at else None,
        "dataAdmin": is_data_admin(user),
        **_steward_json(session, user),
    }


def _steward_json(session: Session, user: AppUser) -> dict[str, Any]:
    """부서 데이터 책임자 (UPL-04 · Q107) — 맡은 부서."""
    if not getattr(user, "data_steward", False):
        return {"dataSteward": False}
    from nhdip.orgs import steward_scope

    sc = steward_scope(session, user.org_code)
    return {"dataSteward": True, "stewardScope": {"code": sc.code, "name": sc.name} if sc else None}
