"""경영목표 확정 전 정합성 검증 (작업 6.4.7 · GOAL-xx) — 상위 제약 · 기조 방향 · 목표 간 영향.

검사 항목은 규칙 `GOAL_CONSISTENCY` 에서 관리한다(관리자 편집). 비교에 쓰는 수치는 계산 커널 지표 값(최근 metric_value)과
커널 수식(LINEAR)만 쓴다.
  max_metric  : 값 ≤ 지표 값 (예: 지주 총자산 한도 환산 상한)
  min_value   : 값 ≥ 고정 하한
  direction   : 기조(GOAL_REC_POLICY.<policy>.stance)와 반대 방향 변경
  asset_limit : 현재 은행 목표 총자산 증가율 + (값 − 현재 목표) × 비중 ≤ 지주 총자산 최대 증가율
심각도: block(확정 불가) · warn(사유 입력 후 강제 확정 가능) · info(참고)
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from nhdip.calc import execute
from nhdip.models import MetricValue, Rule, RuleVersion, Setting


def _rule(session: Session, code: str) -> dict[str, Any]:
    r = session.get(Rule, code)
    if not r:
        return {}
    v = session.execute(select(RuleVersion).where(RuleVersion.rule_code == code, RuleVersion.version == r.active_version)).scalar()
    return dict(v.body) if v else {}


def _path(obj: Any, path: str) -> Any:
    for p in path.split("."):
        obj = obj.get(p) if isinstance(obj, dict) else None
    return obj


def _metric(session: Session, code: str) -> Decimal | None:
    mv = session.execute(select(MetricValue).where(MetricValue.metric_code == code).order_by(MetricValue.created_at.desc()).limit(1)).scalar()
    if mv is None or mv.value is None:
        return None
    return Decimal(str(mv.value))


def current_goal_value(session: Session, goal_id: str) -> Decimal | None:
    links = session.get(Setting, "goal.rule_links")
    link = (links.value if links else {}).get(goal_id)
    if not link:
        return None
    v = _rule(session, link["rule"]).get(link["path"])
    return None if v is None else Decimal(str(v))


def _fmt(v: Decimal | None, unit: str = "%") -> str:
    from decimal import ROUND_HALF_UP

    return "-" if v is None else f"{v.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)}{unit}"


def check_goal(session: Session, goal_id: str, value: float | None) -> dict[str, Any]:
    body = _rule(session, "GOAL_CONSISTENCY")
    checks = (body.get("goals") or {}).get(goal_id) or []
    issues: list[dict[str, Any]] = []
    if value is None:
        return {"goal": goal_id, "passed": True, "issues": [], "checked": 0}
    v = Decimal(str(value))
    cur = current_goal_value(session, goal_id)
    policy = _rule(session, "GOAL_REC_POLICY")
    for c in checks:
        kind, sev = c.get("kind"), c.get("severity", "warn")
        msg = c.get("message", "")
        if kind == "max_metric":
            lim = _metric(session, c["metric"])
            if lim is not None and v > lim:
                issues.append({"code": f"max:{c['metric']}", "severity": sev, "message": msg.format(value=_fmt(v), limit=_fmt(lim)), "limit": float(lim)})
        elif kind == "min_value":
            lim = Decimal(str(c["value"]))
            if v < lim:
                issues.append({"code": "min_value", "severity": sev, "message": msg.format(value=_fmt(v), limit=_fmt(lim)), "limit": float(lim)})
        elif kind == "direction" and cur is not None:
            stance = _path(policy, f"{c['policy']}.stance")
            if stance is not None and ((stance > 0 and v < cur) or (stance < 0 and v > cur)):
                issues.append({"code": "direction", "severity": sev, "message": msg.format(value=_fmt(v), current=_fmt(cur)), "current": float(cur)})
        elif kind == "asset_limit" and cur is not None:
            base, lim = _metric(session, c.get("base_metric", "bank_asset_target")), _metric(session, c.get("limit_metric", "cap_asset_growth"))
            weight = _path(_rule(session, c.get("weight_rule", "PROPOSAL_IMPACT")), c.get("weight_path", "corp_loan_asset_weight"))
            if base is not None and lim is not None and weight is not None:
                expected = execute("LINEAR", {"a": base, "b": v - cur, "c": weight}).value
                if expected > lim:
                    issues.append({"code": "asset_limit", "severity": sev, "message": msg.format(value=_fmt(v), expected=_fmt(expected), limit=_fmt(lim)), "expected": float(expected), "limit": float(lim)})
    order = {"block": 0, "warn": 1, "info": 2}
    issues.sort(key=lambda i: order.get(i["severity"], 3))
    return {"goal": goal_id, "passed": not any(i["severity"] in ("block", "warn") for i in issues), "blocked": any(i["severity"] == "block" for i in issues), "issues": issues, "checked": len(checks), "current": None if cur is None else float(cur)}
