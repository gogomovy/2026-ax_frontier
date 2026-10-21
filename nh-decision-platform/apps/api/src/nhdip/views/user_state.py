"""업무 사용자 상태 (app.user_state) — 경영목표 처리 · 진행사업 등록/전파/수정.

산출물(view_artifact)이 워크플로우로 재생성되어도 이 상태는 보존된다(설계 §8.8).
응답 형식은 프론트 GoalStateProvider · PlanStateProvider 의 상태 구조와 같다.
동시 수정(B.32): 쓰기는 upsert, 읽고-고쳐-쓰는 수정은 lock_item 으로 같은 항목을 직렬화한다.
"""
from __future__ import annotations

import copy
import re
from datetime import date
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from nhdip.locks import lock
from nhdip.models import UserState, utcnow
from nhdip.views.store import get_current

NS_GOAL_OVERRIDE = "goal.override"
NS_PROPOSAL_ACTION = "goal.proposal_action"
NS_GOAL_ADDED = "goal.added"
NS_REVIEW_ITEM = "goal.review_item"
NS_PLAN_RUNTIME = "plan.runtime"
NS_PLAN_USER = "plan.user"
NS_PLAN_DELETED = "plan.deleted"
NS_REPORT_REQUEST = "request.user"


def today() -> str:
    return date.today().isoformat()


def get_ns(session: Session, ns: str) -> dict[str, Any]:
    rows = session.execute(select(UserState).where(UserState.namespace == ns).order_by(UserState.updated_at)).scalars().all()
    return {r.item_id: r.payload for r in rows}


def lock_item(session: Session, ns: str, item_id: str) -> None:
    """같은 항목의 읽고-고쳐-쓰기를 트랜잭션 끝까지 직렬화 (두 사용자가 동시에 고쳐도 한쪽이 사라지지 않음)."""
    lock(session, f"user_state:{ns}:{item_id}")


def put(session: Session, ns: str, item_id: str, payload: Any, actor: str | None) -> None:
    if session.get_bind().dialect.name == "postgresql":
        stmt = insert(UserState).values(namespace=ns, item_id=item_id, payload=payload, updated_by=actor)
        session.execute(stmt.on_conflict_do_update(index_elements=[UserState.namespace, UserState.item_id], set_={"payload": payload, "updated_by": actor, "updated_at": utcnow()}))
        session.expire_all()
        return
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


GOAL_EVENTS = ("goal.confirmed",)  # 종합기획부 목표 확정 · 수정 · 신설 · 삭제 · 복원 — 사업부서 · 영업점 서술이 근거로 읽는 확정 목표가 바뀐다
_PLACEHOLDER = re.compile(r"\s[–-](?=\s|$)")  # 값이 아직 없는 목표 제목의 자리표시('… – 이상')


def _no_digits(text: Any) -> str:
    """서술 근거 줄용 — 값 숫자(단위 붙은 정수 · 소수 · 천단위)를 뺀다. 서술 검증(numguard)이 리터럴 숫자를 막고 확정 수치는 [[fig]] 마커로만 쓴다.
    기간 표현('2026년 3분기')은 검증도 막지 않으므로 남긴다."""
    from nhdip.workflow.numguard import BUILTIN, normalize

    s = _PLACEHOLDER.sub(" ", BUILTIN.sub(" ", normalize(str(text or ""))))
    return " ".join(s.split()).strip(" ·-–()")


def goal_lines(session: Session, limit: int = 8) -> list[str]:
    """사업부서 · 영업점 서술 에이전트의 근거 줄 — 종합기획부가 확정한 현재 경영목표(보관 제외 · 신설 포함, 숫자 없이).
    NAVI 흐름: 종합기획부 확정 목표 → 사업부서 · 영업점이 공유된 목표를 의견의 근거로."""
    from nhdip.ui_config import hq_org_name

    from .readiness import gate, has_value, session_lookup

    hq = hq_org_name(session) or "종합기획부"
    overrides = get_ns(session, NS_GOAL_OVERRIDE)
    out: list[str] = []
    goals = gate("goals", get_current(session, "goals") or [], session_lookup(session)) or []
    for g in goals:
        if not isinstance(g, dict) or not g.get("id") or (overrides.get(g["id"]) or {}).get("status") == "archived":
            continue
        ov = overrides.get(g["id"]) or {}
        if not ov and not has_value(g):
            continue  # 자료로 계산되지 않았고 담당자가 확정하지도 않은 시연 목표
        title = _no_digits(g.get("title") or g.get("label"))
        if not title:
            continue
        changed = ov.get("targetValue") is not None and ov.get("targetValue") != g.get("targetValue")
        period = _no_digits(g.get("periodLabel"))
        out.append(f"- [{g.get('ownerOrg') or hq} 확정 목표] {title}" + (f" · {period}" if period else "") + (" · 목표값 수정 확정" if changed else ""))
    for a in get_ns(session, NS_GOAL_ADDED).values():
        if not isinstance(a, dict) or a.get("status") == "archived":
            continue
        title = _no_digits(a.get("title"))
        if title:
            period = _no_digits(a.get("periodLabel"))
            out.append(f"- [{a.get('ownerOrg') or hq} 신설 목표] {title}" + (f" · {period}" if period else ""))
    return out[:limit]


# ── 진행사업 ──────────────────────────────────────────────────
def plan_state(session: Session) -> dict[str, Any]:
    return {
        "runtime": get_ns(session, NS_PLAN_RUNTIME),
        "userPlans": list(get_ns(session, NS_PLAN_USER).values()),
        "deleted": list(get_ns(session, NS_PLAN_DELETED).keys()),
    }


def shared_plan_state(session: Session) -> dict[str, Any]:
    """진행사업 수정 권한이 없는 사용자(영업점 등)용 — 영업점 참고가 켜진 진행사업만 (B.32 · 본부 미공개 사업 비노출)."""
    st = plan_state(session)
    shared = {p["id"] for p in merged_plans(session) if p.get("branchShared") and p.get("status") == "in_progress"}
    return {"runtime": {k: v for k, v in st["runtime"].items() if k in shared}, "userPlans": [p for p in st["userPlans"] if p.get("id") in shared], "deleted": st["deleted"]}


def merged_plans(session: Session) -> list[dict[str, Any]]:
    """PlanStateProvider.plans 와 같은 병합 결과 (메뉴 건수 · 영업점 화면 등 서버 계산용)."""
    from .readiness import gate, session_lookup

    st = plan_state(session)
    raw = get_current(session, "action_plans") or []
    # 근거가 아직 계산되지 않은 시연 수행방안은 빼되(M.19 · Q204), 사용자가 이미 처리한 것은 남긴다
    ready = {p.get("id") for p in gate("action_plans", raw, session_lookup(session)) or [] if isinstance(p, dict)}
    base = [p for p in raw if isinstance(p, dict) and (p.get("id") in ready or p.get("id") in st["runtime"])]
    out = []
    for p in [*base, *st["userPlans"]]:
        if p["id"] in st["deleted"]:
            continue
        rt = st["runtime"].get(p["id"])
        if rt:
            p = {**copy.deepcopy(p), **(rt.get("patch") or {}), "status": rt.get("status", p.get("status")), "branchShared": rt.get("branchShared", p.get("branchShared"))}
        out.append(p)
    return out
