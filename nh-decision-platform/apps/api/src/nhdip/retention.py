"""보관 기간 정리 (B.32) — 운영 기록이 끝없이 쌓이지 않도록 워커가 하루 한 번 정리한다.

기준은 설정 `retention.policy` (관리자 편집, 0 = 정리하지 않음):
  artifact_generations  화면 산출물 키별로 남길 이전 세대 수 (현재 세대는 항상 보존)
  llm_call_days · node_run_days · agent_decision_days · outbox_days · job_days  일 단위 보관 기간
감사 로그(ops.audit_log)는 정리하지 않는다(추가 전용). 계산 기록(calc_run · metric_value)은 화면 수치의 계산 근거라 남긴다.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from nhdip.models import Setting, utcnow

log = logging.getLogger("nhdip.retention")
DEFAULTS: dict[str, Any] = {"enabled": True, "artifact_generations": 50, "llm_call_days": 180, "node_run_days": 180, "agent_decision_days": 180, "outbox_days": 90, "job_days": 90}

# (설정 키, 테이블, 시각 열, 추가 조건) — 끝나지 않은 작업 · 미처리 이벤트는 지우지 않는다
_TABLES = [
    ("llm_call_days", "ops.llm_call", "created_at", ""),
    ("node_run_days", "ops.node_run", "started_at", ""),
    ("agent_decision_days", "ops.agent_decision", "at", ""),
    ("outbox_days", "ops.outbox_event", "created_at", "AND dispatched_at IS NOT NULL"),
    ("job_days", "ops.job", "created_at", "AND status IN ('done','failed','rejected')"),
]


def policy(session: Session) -> dict[str, Any]:
    s = session.get(Setting, "retention.policy")
    return {**DEFAULTS, **(s.value if s and isinstance(s.value, dict) else {})}


def purge(session: Session) -> dict[str, int]:
    pol = policy(session)
    out: dict[str, int] = {}
    if not pol.get("enabled", True):
        return out
    keep = int(pol.get("artifact_generations") or 0)
    if keep > 0:
        res = session.execute(
            text(
                "DELETE FROM app.view_artifact v USING (SELECT key, max(generation) AS g FROM app.view_artifact GROUP BY key) m "
                "WHERE v.key = m.key AND NOT v.is_current AND v.generation < m.g - :keep"
            ),
            {"keep": keep},
        )
        out["view_artifact"] = res.rowcount or 0
    for key, table, col, extra in _TABLES:
        days = int(pol.get(key) or 0)
        if days <= 0:
            continue
        res = session.execute(text(f"DELETE FROM {table} WHERE {col} < :cut {extra}"), {"cut": utcnow() - timedelta(days=days)})  # noqa: S608 — 고정 목록
        out[table] = res.rowcount or 0
    session.commit()
    if any(out.values()):
        log.info("보관 기간 정리 %s", out)
    return out
