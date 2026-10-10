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


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


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
    }
