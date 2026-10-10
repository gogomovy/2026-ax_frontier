"""정기 실행(cron 트리거) — 일배치 · 주기 재계산 (Phase 6.7 선행).

cfg.workflow_trigger(kind='cron', target='분 시 일 월 요일')를 업무 시간대(setting ui.timezone) 기준으로 평가해
실행 시각이 지나면 'schedule' 이벤트를 아웃박스에 넣는다. 이후 경로는 다른 변경 이벤트와 같다(디스패처 → 작업 → 엔진).
놓친 실행이 여러 번이어도 1회만 실행한다(따라잡기 없음).
"""
from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from croniter import croniter
from sqlalchemy import select
from sqlalchemy.orm import Session

from nhdip.events import emit
from nhdip.models import Setting, Workflow, WorkflowTrigger, utcnow

log = logging.getLogger("nhdip.scheduler")


def _tz(session: Session) -> ZoneInfo:
    s = session.get(Setting, "ui.timezone")
    try:
        return ZoneInfo(s.value if s else "Asia/Seoul")
    except Exception:  # noqa: BLE001
        return ZoneInfo("Asia/Seoul")


def is_valid(expr: str) -> bool:
    return bool(expr) and croniter.is_valid(expr)


def next_fire(expr: str, after: datetime, tz: ZoneInfo) -> datetime:
    return croniter(expr, after.astimezone(tz)).get_next(datetime)


def schedule_due(session: Session, now: datetime | None = None) -> int:
    now = now or utcnow()
    tz = _tz(session)
    enabled = {w.code for w in session.execute(select(Workflow).where(Workflow.enabled)).scalars()}
    fired = 0
    for t in session.execute(select(WorkflowTrigger).where(WorkflowTrigger.kind == "cron", WorkflowTrigger.enabled).with_for_update(skip_locked=True)).scalars():
        if t.workflow_code not in enabled or not is_valid(t.target):
            continue
        if t.last_fired_at is None:
            t.last_fired_at = now  # 새 트리거는 다음 예정 시각부터
            continue
        due = next_fire(t.target, t.last_fired_at, tz)
        if due <= now:
            emit(session, "schedule", {"workflow": t.workflow_code, "trigger_id": t.id, "cron": t.target, "scheduled_for": due.isoformat()}, "scheduler")
            t.last_fired_at = now
            fired += 1
            log.info("cron %s → %s (예정 %s)", t.target, t.workflow_code, due.isoformat())
    session.commit()
    return fired
