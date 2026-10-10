"""전파 경로 트리 서버 계산 (F.16 · 요구사항 PROP-01 ~ PROP-04).

입력: 화면 산출물 `cascade`(기본 트리) · `goals` + 사용자 상태(경영목표 처리 · 진행사업).
프론트 `useCascadeModel` 과 같은 규칙으로 다시 계산해, 모든 사용자에게 같은 트리를 준다.

반영 대상
 - 종합기획부에서 수정·신설한 경영목표 → 목표 노드 라벨·신규 노드
 - 사업부서에서 진행사업으로 등록한 수행방안 → 목표 하위 노드로 편입
 - 영업점 참고 토글 → 영업점 노드 노출 여부
"""
from __future__ import annotations

import copy
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy.orm import Session

from nhdip.models import Setting
from nhdip.views.store import get_current

#: 설정 `format.unit_labels` 가 없을 때의 기본값 (프론트 UNIT_LABEL 과 같음)
DEFAULT_UNIT_LABELS = {"KRW_MN": "백만원", "KRW_BN": "억원", "KRW_TN": "조원", "PCT": "%", "PP": "%p", "CNT": "건", "RATIO": "", "NONE": ""}


def fixed(value: float, decimals: int) -> str:
    """JS `Number.prototype.toFixed` 와 같은 결과 (이진값 기준 사사오입)."""
    q = Decimal(1).scaleb(-decimals) if decimals > 0 else Decimal(1)
    return str(Decimal(value).quantize(q, rounding=ROUND_HALF_UP))


def build_tree(
    base: list[dict[str, Any]],
    goals: list[dict[str, Any]],
    goal_state: dict[str, Any],
    in_progress: list[dict[str, Any]],
    unit_labels: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    units = unit_labels or DEFAULT_UNIT_LABELS
    overrides = goal_state.get("overrides") or {}
    by_goal = {g["id"]: g for g in goals}

    # 1) 목표 노드 라벨을 현재 목표값으로 갱신
    nodes: list[dict[str, Any]] = []
    for node in base:
        n = copy.deepcopy(node)
        goal = by_goal.get(n["id"])
        ov = overrides.get(n["id"]) or {}
        tv = ov.get("targetValue")
        if goal and tv is not None and goal.get("targetValue") is not None and tv != goal["targetValue"]:
            unit = units.get(goal.get("unit", "NONE"), "")
            d = goal.get("decimals")
            d = 1 if d is None else int(d)
            before = f"{fixed(goal['targetValue'], d)}{unit}"
            after = f"{fixed(tv, d)}{unit}"
            n["label"] = n["label"].replace(before, after)
            n["detail"] = f"{n.get('detail') or ''} · 목표 변경 {before} → {after}".removeprefix(" · ")
        nodes.append(n)

    # 2) 종합기획부에서 신설한 목표 추가
    for added in goal_state.get("addedGoals") or []:
        if any(n["id"] == added["id"] or n["label"] == added.get("title") for n in nodes):
            continue
        nodes.append({
            "id": added["id"],
            "kind": "goal",
            "label": added.get("title", ""),
            "detail": f"종합기획부 · 신규 확정 · 목표 {added.get('targetLabel', '')}",
            "org": "종합기획부",
            "children": [],
        })

    # 3) 진행사업으로 등록된 수행방안을 목표 하위에 편입
    def attach(plan: dict[str, Any]) -> dict[str, Any]:
        shared = bool(plan.get("branchShared"))
        detail = [f"{plan.get('ownerOrg', '')} · 진행사업", "영업점 Agent 참고 가능" if shared else "영업점 참고 중단"]
        if plan.get("linkedAnalysisLabel"):
            detail.append(f"연결 분석 {plan['linkedAnalysisLabel']}")
        node: dict[str, Any] = {"id": plan["id"], "kind": "plan", "label": plan.get("title", ""), "detail": " · ".join(detail), "org": plan.get("ownerOrg", "")}
        if shared:
            metrics = (plan.get("monitoringMetrics") or [])[:2]
            node["children"] = [{
                "id": f"{plan['id']}-branch",
                "kind": "branch_target",
                "label": "영업점 가이드로 전파됨",
                "detail": f"모니터링 지표 {' · '.join(metrics) or '미지정'}",
                "org": "전 영업점",
            }]
        return node

    unmatched: list[dict[str, Any]] = []
    for plan in in_progress:
        node = attach(plan)
        parent = None
        if plan.get("relatedGoalId"):
            parent = next((n for n in nodes if n["id"] == plan["relatedGoalId"]), None)
        elif plan.get("relatedGoalTitle"):
            key = plan["relatedGoalTitle"].replace("(제안) ", "")
            parent = next((n for n in nodes if key in n["label"]), None)
        if parent is not None:
            # 기본 트리에 같은 수행방안이 있으면 현재 상태 노드로 바꾼다(중복 노드 방지)
            kids = [k for k in (parent.get("children") or []) if k.get("id") != node["id"]]
            parent["children"] = [*kids, node]
        else:
            unmatched.append(node)

    # 4) 연결 목표가 없는 진행사업도 누락 없이 보여준다
    if unmatched:
        nodes.append({
            "id": "plan-unlinked",
            "kind": "goal",
            "label": "연결 경영목표 없음",
            "detail": "상위 목표가 지정되지 않은 진행사업입니다. 목표 연결 후 전파 범위가 확정됩니다.",
            "org": "—",
            "children": unmatched,
        })
    return nodes


def current_tree(session: Session) -> list[dict[str, Any]]:
    from nhdip.views import user_state as S

    units = session.get(Setting, "format.unit_labels")
    plans = [p for p in S.merged_plans(session) if p.get("status") == "in_progress"]
    return build_tree(
        get_current(session, "cascade") or [],
        get_current(session, "goals") or [],
        S.goal_state(session),
        plans,
        units.value if units else None,
    )


def find_node(nodes: list[dict[str, Any]], node_id: str) -> dict[str, Any] | None:
    for n in nodes:
        if n["id"] == node_id:
            return n
        hit = find_node(n.get("children") or [], node_id)
        if hit:
            return hit
    return None
