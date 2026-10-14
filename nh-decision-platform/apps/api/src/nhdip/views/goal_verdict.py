"""경영목표 판정(gapVerdict) — 실적 수치와 확정 목표 값으로 서버가 계산한다.

예전에는 시드 JSON 의 고정 값(정상 · 미달 · 한도 근접 · 한도 초과)이 그대로 화면에 남아, 실제 자료를 넣어도 배지가 바뀌지 않았다.
이제 `build_views` 단계에서 목표의 `actual.value`(계산 커널 수치)와 목표 값을 비교해 채운다. 계산할 수 없으면 None(화면은 판정 배지를 달지 않는다).

  limit  (이하 관리)      실적 > 목표 → breach · 실적 ≥ 목표 × (1 − near_pct%) → near_limit · 그 외 on_track
  growth · ratio 증가     실적 ≥ 목표 → on_track · 아니면 below            (감소 방향은 반대)
  ratio  유지             실적 ≥ 목표 → on_track · 부족분 ≤ maintain_tol_pp → near_limit · 그 외 below
  amount (누계 금액 목표)   기간 진행률에 따라 달라지므로 판정하지 않는다(None)

목표 값 우선순위: 규칙에 연결된 확정 값(설정 goal.rule_links) → 목표 수치(targetFigure) → targetValue.
기준은 설정 `goal.verdict_policy`({"near_pct": 10, "maintain_tol_pp": 1.0}) — 관리자가 편집한다.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy.orm import Session

from nhdip.models import Setting

DEFAULT_POLICY = {"near_pct": 10.0, "maintain_tol_pp": 1.0}
VERDICTS = ("on_track", "below", "near_limit", "breach")


def _policy(session: Session) -> dict[str, float]:
    st = session.get(Setting, "goal.verdict_policy")
    raw = st.value if st is not None and isinstance(st.value, dict) else {}
    out = dict(DEFAULT_POLICY)
    for k in out:
        try:
            v = float(raw[k])
        except (KeyError, TypeError, ValueError):
            continue
        if v == v and v >= 0:  # NaN · 음수 제외
            out[k] = v
    return out


def _num(v: Any) -> Decimal | None:
    if isinstance(v, bool) or v is None:
        return None
    try:
        d = Decimal(str(v))
    except (InvalidOperation, ValueError):
        return None
    return d if d.is_finite() else None


def target_of(session: Session, goal: dict[str, Any]) -> tuple[Decimal | None, str | None]:
    """(목표 값, 단위) — 규칙 연결 값 → targetFigure → targetValue."""
    from nhdip.views.goal_check import current_goal_value

    unit = goal.get("unit")
    try:
        linked = current_goal_value(session, str(goal.get("id")))
    except (KeyError, TypeError, ValueError, ArithmeticError):
        linked = None
    if linked is not None:
        return linked, unit
    tf = goal.get("targetFigure")
    if isinstance(tf, dict) and not tf.get("stale") and _num(tf.get("value")) is not None:
        return _num(tf.get("value")), tf.get("unit") or unit
    return _num(goal.get("targetValue")), unit


def verdict_of(goal: dict[str, Any], target: Decimal | None, target_unit: str | None, policy: dict[str, float]) -> str | None:
    """목표 하나의 판정 — 계산할 수 없으면 None."""
    actual = goal.get("actual")
    if not isinstance(actual, dict) or actual.get("stale"):
        return None
    a = _num(actual.get("value"))
    if a is None or target is None:
        return None
    if actual.get("unit") and target_unit and actual["unit"] != target_unit:
        return None  # 단위가 달라 직접 비교할 수 없다
    kind, direction = goal.get("targetType"), goal.get("direction")
    if kind == "limit":
        if a > target:
            return "breach"
        near = Decimal(str(policy["near_pct"])) / 100
        return "near_limit" if target > 0 and a >= target * (1 - near) else "on_track"
    if kind == "ratio" and direction == "maintain":
        if a >= target:
            return "on_track"
        return "near_limit" if target - a <= Decimal(str(policy["maintain_tol_pp"])) else "below"
    if kind in ("growth", "ratio"):
        if direction == "decrease":
            return "on_track" if a <= target else "below"
        if direction == "increase":
            return "on_track" if a >= target else "below"
    return None  # amount(누계 금액) · 알 수 없는 유형


def apply_goal_verdicts(session: Session, arts: dict[str, Any]) -> tuple[set[str], list[dict[str, Any]]]:
    """산출물의 목표(`goals`)마다 gapVerdict 를 계산해 채우고, 같은 목표를 가리키는 여신 구분(`goalId`)에도 옮긴다.
    (바뀐 산출물 키, 판정 요약) 을 돌려준다."""
    changed: set[str] = set()
    out: list[dict[str, Any]] = []
    policy = _policy(session)
    by_goal: dict[str, str | None] = {}
    goals = arts.get("goals")
    for g in goals if isinstance(goals, list) else []:
        if not isinstance(g, dict) or not g.get("id"):
            continue
        target, tunit = target_of(session, g)
        v = verdict_of(g, target, tunit, policy)
        by_goal[str(g["id"])] = v
        if g.get("gapVerdict") != v:
            g["gapVerdict"] = v
            changed.add("goals")
        a = g.get("actual") if isinstance(g.get("actual"), dict) else {}
        out.append({"goal": g["id"], "verdict": v, "actual": a.get("value"), "target": None if target is None else float(target)})
    if not by_goal:
        return changed, out
    for key, payload in arts.items():
        stack = [payload]
        while stack:
            o = stack.pop()
            if isinstance(o, dict):
                if "goalId" in o and "gapVerdict" in o and str(o["goalId"]) in by_goal and o["gapVerdict"] != by_goal[str(o["goalId"])]:
                    o["gapVerdict"] = by_goal[str(o["goalId"])]
                    changed.add(key)
                stack.extend(o.values())
            elif isinstance(o, list):
                stack.extend(o)
    return changed, out
