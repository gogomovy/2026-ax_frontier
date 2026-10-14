"""관리자 [데이터 흐름] · [에이전트 결정] 화면의 파이프라인 그림 데이터.

  데이터 흐름     이벤트 → 분배(매칭 워크플로우) → 작업 → 실행(노드별 상태) → 게시 산출물   (monitor_flow 가 `run_nodes` 로 노드 상태를 싣는다)
  에이전트 결정   최근 실행마다 노드 순서 위에 에이전트 결정을 놓는다 — 노드 ↔ 결정은 결정 기록의 `detail.nodeRunId` 로 잇고,
                 오케스트레이터 결정(경로 지정 · 대기 · 허용)은 실행 앞 단계로 둔다.
수치는 새로 계산하지 않는다 — 기록된 상태 · 건수 · 문장만 보여 준다.
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from nhdip.models import Agent, AgentDecision, NodeRun, Workflow, WorkflowNode, WorkflowRun

from .pipeline_view import node_summary

DETAIL_MAX = 30000  # 결정 근거(JSON) 한 건의 응답 상한(글자) — 넘으면 키 목록만


def _iso(v: Any) -> str | None:
    return v.isoformat() if v is not None else None


def node_names(session: Session, codes: set[str]) -> dict[str, dict[str, str]]:
    """{워크플로우: {노드 key: 표시 이름}}."""
    if not codes:
        return {}
    out: dict[str, dict[str, str]] = {}
    for n in session.execute(select(WorkflowNode).where(WorkflowNode.workflow_code.in_(sorted(codes)))).scalars():
        out.setdefault(n.workflow_code, {})[n.key] = n.name
    return out


def _label(key: str, names: dict[str, str]) -> str:
    base, _, scope = key.partition("@")  # 범위 실행(다지점)의 노드는 '키@범위'
    return names.get(base, base) + (f" @{scope}" if scope else "")


def run_nodes(summary: dict[str, Any] | None, names: dict[str, str]) -> list[dict[str, Any]]:
    """실행 요약의 노드 목록 → [{key, name, status, ms}] (가벼운 정보만 — 노드 출력은 싣지 않는다)."""
    out: list[dict[str, Any]] = []
    for n in (summary or {}).get("nodes") or []:
        if isinstance(n, dict) and n.get("key"):
            key = str(n["key"])
            out.append({"key": key, "name": _label(key, names), "status": str(n.get("status") or "succeeded"), "ms": n.get("ms") if isinstance(n.get("ms"), int) else None})
    return out


def _clip(detail: Any) -> Any:
    try:
        if len(json.dumps(detail, ensure_ascii=False, default=str)) <= DETAIL_MAX:
            return detail
    except (TypeError, ValueError):
        return None
    return {"_truncated": True, "keys": list(detail)[:30] if isinstance(detail, dict) else None}


def _decision(d: AgentDecision) -> dict[str, Any]:
    det = d.detail if isinstance(d.detail, dict) else {}
    by = det.get("by")
    return {"id": d.id, "at": _iso(d.at), "agent": d.agent_code, "decision": d.decision, "summary": d.summary, "by": by if by in ("llm", "rule") else None, "detail": _clip(d.detail)}


def build_agent_pipeline(session: Session, *, workflow: str | None = None, limit: int = 8) -> dict[str, Any]:
    q = select(WorkflowRun).order_by(WorkflowRun.started_at.desc()).limit(min(max(int(limit), 1), 30))
    if workflow:
        q = q.where(WorkflowRun.workflow_code == workflow)
    runs = list(session.execute(q).scalars())
    if not runs:
        return {"runs": [], "counts": {}, "workflows": _workflow_options(session)}
    run_ids = [r.id for r in runs]
    job_ids = [r.job_id for r in runs if r.job_id]
    codes = {r.workflow_code for r in runs}
    wf_name = {w.code: w.name for w in session.execute(select(Workflow).where(Workflow.code.in_(sorted(codes)))).scalars()}
    wf_nodes: dict[str, list[WorkflowNode]] = {}
    for n in session.execute(select(WorkflowNode).where(WorkflowNode.workflow_code.in_(sorted(codes))).order_by(WorkflowNode.seq, WorkflowNode.id)).scalars():
        wf_nodes.setdefault(n.workflow_code, []).append(n)
    agents = {a.code: a for a in session.execute(select(Agent)).scalars()}

    node_rows: dict[str, list[NodeRun]] = {}
    for nr in session.execute(select(NodeRun).where(NodeRun.workflow_run_id.in_(run_ids)).order_by(NodeRun.seq, NodeRun.started_at)).scalars():
        node_rows.setdefault(nr.workflow_run_id, []).append(nr)

    cond = [AgentDecision.workflow_run_id.in_(run_ids)]
    if job_ids:
        cond.append(AgentDecision.job_id.in_(job_ids))
    decisions = list(session.execute(select(AgentDecision).where(or_(*cond)).order_by(AgentDecision.id)).scalars())
    # 경로 지정(route)은 이벤트에 붙는다 — 실행의 원인 이벤트 번호로 잇는다
    routes = list(session.execute(select(AgentDecision).where(AgentDecision.decision == "route").order_by(AgentDecision.id.desc()).limit(300)).scalars())

    def agent_info(code: str | None) -> dict[str, Any] | None:
        a = agents.get(code or "")
        return {"code": a.code, "name": a.name, "kind": a.kind, "enabled": a.enabled} if a else ({"code": code, "name": code, "kind": "rule", "enabled": True} if code else None)

    counts: dict[str, int] = {}
    out_runs: list[dict[str, Any]] = []
    for r in runs:
        rows = node_rows.get(r.id, [])
        by_node: dict[str, list[dict[str, Any]]] = {nr.id: [] for nr in rows}
        before: list[dict[str, Any]] = []
        unplaced: list[dict[str, Any]] = []
        ev_ids = {c.get("event_id") for c in (r.causes or []) if isinstance(c, dict) and c.get("event_id")}
        for d in decisions:
            if d.workflow_run_id == r.id:
                nid = (d.detail or {}).get("nodeRunId") if isinstance(d.detail, dict) else None
                item = _decision(d)
                if nid in by_node:
                    by_node[nid].append(item)
                else:
                    # nodeRunId 가 없는 옛 기록 — 같은 에이전트의 노드에 놓고, 없으면 따로 둔다
                    host = next((nr for nr in rows if nr.agent_code and nr.agent_code == d.agent_code), None)
                    (by_node[host.id] if host else unplaced).append(item)
                counts[d.decision] = counts.get(d.decision, 0) + 1
            elif r.job_id and d.job_id == r.job_id and d.workflow_run_id is None:
                before.append(_decision(d))
                counts[d.decision] = counts.get(d.decision, 0) + 1
        for d in routes:
            ev = (d.detail or {}).get("event") if isinstance(d.detail, dict) else None
            if isinstance(ev, dict) and ev.get("id") in ev_ids:
                before.append(_decision(d))
                counts[d.decision] = counts.get(d.decision, 0) + 1
        before.sort(key=lambda x: x["id"])
        names = {n.key: n for n in wf_nodes.get(r.workflow_code, [])}
        stages: list[dict[str, Any]] = []
        seen_keys: set[str] = set()
        for nr in rows:
            base = nr.node_key.split("@", 1)[0]
            seen_keys.add(nr.node_key)
            meta = names.get(base)
            stages.append({
                "nodeRunId": nr.id, "key": nr.node_key, "name": _label(nr.node_key, {k: v.name for k, v in names.items()}), "impl": nr.impl, "agent": agent_info(nr.agent_code or (meta.agent_code if meta else None)),
                "status": nr.status, "ms": nr.duration_ms, "summary": node_summary(nr.impl, nr.output, nr.error), "error": ((nr.error or "").splitlines() or [""])[0][:300] or None,
                "decisions": by_node.get(nr.id, []),
            })
        if r.status == "running":  # 아직 안 돈 뒤쪽 노드는 '대기'로 보여 준다
            for n in wf_nodes.get(r.workflow_code, []):
                if n.key not in seen_keys:
                    stages.append({"nodeRunId": None, "key": n.key, "name": n.name, "impl": n.impl, "agent": agent_info(n.agent_code), "status": "queued", "ms": None, "summary": "", "error": None, "decisions": []})
        s = r.summary or {}
        out_runs.append({
            "id": r.id, "workflow": r.workflow_code, "workflowName": wf_name.get(r.workflow_code, r.workflow_code), "status": r.status, "startedAt": _iso(r.started_at), "finishedAt": _iso(r.finished_at),
            "jobId": r.job_id, "causes": [{"type": c.get("type"), "reasons": c.get("reasons")} for c in (r.causes or []) if isinstance(c, dict)][-3:],
            "note": s.get("note") if isinstance(s.get("note"), str) else None, "error": (r.error or "")[:300] or None, "wallMs": (s.get("obs") or {}).get("wall_ms") if isinstance(s.get("obs"), dict) else None,
            "before": before, "stages": stages, "unplaced": unplaced,
        })
    return {"runs": out_runs, "counts": counts, "workflows": _workflow_options(session)}


def _workflow_options(session: Session) -> list[dict[str, str]]:
    return [{"code": w.code, "name": w.name} for w in session.execute(select(Workflow).order_by(Workflow.sort)).scalars()]
