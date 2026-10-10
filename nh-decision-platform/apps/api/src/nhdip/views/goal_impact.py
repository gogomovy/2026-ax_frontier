"""경영목표 변경 영향 분석 (작업 6.6.3) — 목표 값이 바뀌면 무엇이 다시 계산되고 누가 재검토해야 하는가.

  지표   : 목표 규칙 경로(설정 goal.rule_links)를 참조하는 지표 → 그 지표를 참조하는 지표 … (지표 정의 의존 그래프)
  화면   : 영향 지표의 수치(Figure)를 담은 현재 산출물
  방안   : 이 목표에 연결된 수행방안(진행사업이면 재검토 필요)
  전파   : 전파 경로 트리의 하위 노드 수
  검증   : 새 값의 정합성 검증 결과(GOAL_CONSISTENCY)
"""
from __future__ import annotations

from collections import deque
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from nhdip.models import Metric, Setting, ViewArtifact

from .goal_check import check_goal, current_goal_value


def _refs(obj: Any):
    if isinstance(obj, dict):
        if "metric" in obj or "rule" in obj:
            yield obj
        for v in obj.values():
            yield from _refs(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _refs(v)


def dependent_metrics(session: Session, rule: str, path: str) -> list[Metric]:
    metrics = session.execute(select(Metric).where(Metric.enabled)).scalars().all()
    direct, by_dep = set(), {}
    for m in metrics:
        for r in _refs(m.args or {}):
            if r.get("rule") == rule and r.get("path") == path:
                direct.add(m.code)
            if r.get("metric"):
                by_dep.setdefault(r["metric"], set()).add(m.code)
    seen, q = set(direct), deque(direct)
    while q:
        for nxt in by_dep.get(q.popleft(), ()):
            if nxt not in seen:
                seen.add(nxt)
                q.append(nxt)
    by_code = {m.code: m for m in metrics}
    return sorted((by_code[c] for c in seen), key=lambda m: (m.workflow_code, m.sort))


def _figure_artifacts(session: Session, figure_ids: set[str]) -> list[str]:
    keys = []
    for row in session.execute(select(ViewArtifact).where(ViewArtifact.is_current)).scalars():
        stack = [row.payload]
        found = False
        while stack and not found:
            o = stack.pop()
            if isinstance(o, dict):
                if o.get("id") in figure_ids and "unit" in o:
                    found = True
                stack.extend(o.values())
            elif isinstance(o, list):
                stack.extend(o)
        if found:
            keys.append(row.key)
    return sorted(keys)


def impact(session: Session, goal_id: str, value: float | None = None) -> dict[str, Any]:
    from nhdip.views import user_state as S
    from nhdip.views.cascade import current_tree, find_node

    links = session.get(Setting, "goal.rule_links")
    link = (links.value if links else {}).get(goal_id)
    cur = current_goal_value(session, goal_id)
    ov = (S.goal_state(session)["overrides"].get(goal_id) or {}).get("targetValue")
    new = value if value is not None else ov
    deps = dependent_metrics(session, link["rule"], link["path"]) if link else []
    fig_ids = {f for m in deps for f in (m.figure_ids or [m.code])}
    plans = [p for p in S.merged_plans(session) if p.get("relatedGoalId") == goal_id]
    node = find_node(current_tree(session), goal_id)

    def count(n: dict[str, Any] | None, kind: str | None = None) -> int:
        if not n:
            return 0
        return sum((1 if (kind is None or c.get("kind") == kind) else 0) + count(c, kind) for c in n.get("children") or [])

    return {
        "goal": goal_id,
        "current": None if cur is None else float(cur),
        "proposed": new,
        "rule": link,
        "metrics": [{"code": m.code, "label": m.label, "workflow": m.workflow_code} for m in deps],
        "workflows": sorted({m.workflow_code for m in deps}),
        "artifacts": _figure_artifacts(session, fig_ids) if fig_ids else [],
        "plans": [{"id": p["id"], "title": p.get("title"), "status": p.get("status"), "branchShared": bool(p.get("branchShared")), "ownerOrg": p.get("ownerOrg"), "needsReview": p.get("status") == "in_progress"} for p in plans],
        "cascade": {"nodes": count(node), "plans": count(node, "plan"), "targets": count(node, "branch_target")},
        "consistency": check_goal(session, goal_id, new) if new is not None else None,
    }
