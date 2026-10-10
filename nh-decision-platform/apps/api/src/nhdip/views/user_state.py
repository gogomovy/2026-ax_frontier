"""업무 사용자 상태 (app.user_state) — 경영목표 처리 · 진행사업 등록/전파/수정.

산출물(view_artifact)이 워크플로우로 재생성되어도 이 상태는 보존된다(설계 §8.8).
응답 형식은 프론트 GoalStateProvider · PlanStateProvider 의 상태 구조와 같다.
"""
from __future__ import annotations

import copy
from datetime import date
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from nhdip.models import UserState
from nhdip.views.store import get_current

NS_GOAL_OVERRIDE = "goal.override"
NS_PROPOSAL_ACTION = "goal.proposal_action"
NS_GOAL_ADDED = "goal.added"
NS_REVIEW_ITEM = "goal.review_item"
NS_PLAN_RUNTIME = "plan.runtime"
NS_PLAN_USER = "plan.user"
NS_PLAN_DELETED = "plan.deleted"


def today() -> str:
    return date.today().isoformat()


def get_ns(session: Session, ns: str) -> dict[str, Any]:
    rows = session.execute(select(UserState).where(UserState.namespace == ns).order_by(UserState.updated_at)).scalars().all()
    return {r.item_id: r.payload for r in rows}


def put(session: Session, ns: str, item_id: str, payload: Any, actor: str | None) -> None:
    row = session.get(UserState, (ns, item_id))
    if row:
        row.payload = payload
        row.updated_by = actor
    else:
        session.add(UserState(namespace=ns, item_id=item_id, payload=payload, updated_by=actor))


def remove(session: Session, ns: str, item_id: str) -> None:
    session.execute(delete(UserState).where(UserState.namespace == ns, UserState.item_id == item_id))


def clear(session: Session, prefix: str) -> None:
    session.execute(delete(UserState).where(UserState.namespace.like(f"{prefix}.%")))


# ── 경영목표 ──────────────────────────────────────────────────
def goal_state(session: Session) -> dict[str, Any]:
    return {
        "overrides": get_ns(session, NS_GOAL_OVERRIDE),
        "proposalActions": {k: v.get("action") for k, v in get_ns(session, NS_PROPOSAL_ACTION).items()},
        "addedGoals": list(get_ns(session, NS_GOAL_ADDED).values()),
        "reviewItems": [v.get("title") for v in get_ns(session, NS_REVIEW_ITEM).values()],
    }


# ── 진행사업 ──────────────────────────────────────────────────
def plan_state(session: Session) -> dict[str, Any]:
    return {
        "runtime": get_ns(session, NS_PLAN_RUNTIME),
        "userPlans": list(get_ns(session, NS_PLAN_USER).values()),
        "deleted": list(get_ns(session, NS_PLAN_DELETED).keys()),
    }


def merged_plans(session: Session) -> list[dict[str, Any]]:
    """PlanStateProvider.plans 와 같은 병합 결과 (메뉴 건수 · 영업점 화면 등 서버 계산용)."""
    base = get_current(session, "action_plans") or []
    st = plan_state(session)
    out = []
    for p in [*base, *st["userPlans"]]:
        if p["id"] in st["deleted"]:
            continue
        rt = st["runtime"].get(p["id"])
        if rt:
            p = {**copy.deepcopy(p), **(rt.get("patch") or {}), "status": rt.get("status", p.get("status")), "branchShared": rt.get("branchShared", p.get("branchShared"))}
        out.append(p)
    return out
