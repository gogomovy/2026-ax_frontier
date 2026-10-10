"""아웃박스 이벤트 · 감사 로그 기록 헬퍼 — 업무 변경과 같은 트랜잭션에서 호출한다 (EVT-01)."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from nhdip.models import AuditLog, OutboxEvent


def emit(session: Session, type_: str, payload: dict[str, Any], actor: str | None = None) -> OutboxEvent:
    ev = OutboxEvent(type=type_, payload=payload, actor=actor)
    session.add(ev)
    return ev


def audit(
    session: Session,
    actor: str | None,
    action: str,
    target_kind: str | None = None,
    target_id: str | None = None,
    detail: Any = None,
    ip: str | None = None,
) -> None:
    session.add(AuditLog(actor=actor, action=action, target_kind=target_kind, target_id=target_id, detail=detail, ip=ip))
