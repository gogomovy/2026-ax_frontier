"""오케스트레이터 에이전트 (B.30) — 워크플로우 간 실행 순서 · 대기 결정.

디스패처가 만든 작업(job)을 워커가 가져갈 때, 상위(upstream) 워크플로우의 작업이 대기 · 실행 중이면
하위 작업을 잠시 미룬다. 상위 관계는 두 가지를 합친다.
  1) 정의에서 도출 — 지표가 다른 워크플로우의 지표를 참조(mref)하면 그 워크플로우가 상위
                     근거 검색 노드가 있으면 그래프 투영 · 문서 구조화(wf_graph_projection)가 상위
  2) 설정 `orchestrator.policy.depends_on` — {"워크플로우": ["상위", ...], "*": [...]} 명시 관계
순환은 서로를 기다리지 않도록 끊고, 최대 대기(`max_hold_sec`)가 지나면 무조건 실행한다.
결정은 ops.agent_decision 에 근거와 함께 남는다(규칙 기반 · LLM 미사용).
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from nhdip.models import AgentDecision, Job, Metric, Setting, WorkflowNode, utcnow

AGENT = "orchestrator"
DEFAULT_POLICY: dict[str, Any] = {"enabled": True, "depends_on": {}, "derive": True, "evidence_upstream": "wf_graph_projection", "hold_sec": 15, "max_hold_sec": 300}


def policy(session: Session) -> dict[str, Any]:
    s = session.get(Setting, "orchestrator.policy")
    return {**DEFAULT_POLICY, **(s.value if s and isinstance(s.value, dict) else {})}


def dependency_graph(session: Session, pol: dict[str, Any] | None = None) -> dict[str, dict[str, list[str]]]:
    """{워크플로우: {상위 워크플로우: [근거...]}}"""
    pol = pol or policy(session)
    out: dict[str, dict[str, list[str]]] = {}

    def add(wf: str, up: str, why: str) -> None:
        if wf != up:
            out.setdefault(wf, {}).setdefault(up, []).append(why)

    if pol.get("derive", True):
        owner = {m.code: m.workflow_code for m in session.execute(select(Metric).where(Metric.enabled)).scalars()}
        for m in session.execute(select(Metric).where(Metric.enabled)).scalars():
            for ref in (m.args or {}).values():
                if isinstance(ref, dict) and ref.get("metric") in owner and owner[ref["metric"]] != m.workflow_code:
                    add(m.workflow_code, owner[ref["metric"]], f"지표 {m.code} → {ref['metric']}")
        up = pol.get("evidence_upstream")
        if up:
            for n in session.execute(select(WorkflowNode).where(WorkflowNode.impl == "retrieve_evidence", WorkflowNode.enabled)).scalars():
                add(n.workflow_code, up, "근거 검색 전 그래프 투영 · 문서 구조화")
    for wf, ups in (pol.get("depends_on") or {}).items():
        for u in ups or []:
            add(wf, u, "설정 orchestrator.policy.depends_on")
    # '*' 는 모든 워크플로우에 적용 (자기 자신 제외)
    star = out.pop("*", {})
    if star:
        wfs = {n.workflow_code for n in session.execute(select(WorkflowNode)).scalars()}
        for wf in wfs:
            for u, why in star.items():
                for w in why:
                    add(wf, u, w)
    # 순환 끊기 — 서로를 상위로 두면 양쪽 모두 기다리지 않는다
    for wf, ups in list(out.items()):
        for u in list(ups):
            if wf in out.get(u, {}):
                ups.pop(u, None)
                out[u].pop(wf, None)
    return out


def _record(session: Session, job: Job, decision: str, summary: str, detail: dict[str, Any]) -> None:
    session.add(AgentDecision(agent_code=AGENT, workflow_code=job.workflow_code, job_id=job.id, decision=decision, summary=summary[:500], detail=detail))


def hold_reason(session: Session, job: Job, graph: dict[str, dict[str, list[str]]], pol: dict[str, Any]) -> dict[str, Any] | None:
    """미뤄야 하면 {upstream, jobs, reasons} — 상위 워크플로우 작업이 대기(실행 시각 도래 전후 무관) · 실행 중."""
    ups = graph.get(job.workflow_code or "", {})
    if not ups:
        return None
    pending = session.execute(select(Job).where(Job.kind == "workflow", Job.workflow_code.in_(list(ups)), Job.status.in_(["queued", "running"]), Job.id != job.id)).scalars().all()
    # 이 작업보다 나중에 생긴 상위 대기 작업은 기다리지 않는다(이 작업의 원인과 무관할 수 있음 — 다음 실행에서 반영)
    pending = [p for p in pending if p.status == "running" or p.created_at <= job.run_after]
    if not pending:
        return None
    return {"upstream": sorted({p.workflow_code for p in pending}), "jobs": [{"id": p.id, "workflow": p.workflow_code, "status": p.status} for p in pending][:10],
            "reasons": {p.workflow_code: ups.get(p.workflow_code, []) for p in pending}}


def gate(session: Session, job: Job) -> bool:
    """실행해도 되면 True. 미루면 run_after 를 늦추고 결정을 남긴 뒤 False."""
    pol = policy(session)
    if not pol.get("enabled", True) or job.kind != "workflow":
        return True
    reason = hold_reason(session, job, dependency_graph(session, pol), pol)
    if reason is None:
        return True
    waited = (utcnow() - job.created_at).total_seconds()
    if waited >= float(pol.get("max_hold_sec", 300)):
        _record(session, job, "release", f"최대 대기 {int(waited)}초 경과 — 상위 {', '.join(reason['upstream'])} 를 기다리지 않고 실행", {**reason, "waited_sec": int(waited)})
        return True
    job.run_after = utcnow() + timedelta(seconds=float(pol.get("hold_sec", 15)))
    _record(session, job, "hold", f"상위 워크플로우 {', '.join(reason['upstream'])} 완료 후 실행", {**reason, "waited_sec": int(waited)})
    return False


def release_downstream(session: Session, workflow_code: str) -> list[int]:
    """상위 작업이 끝나면 그 작업을 기다리던 하위 작업을 바로 실행 가능 상태로 (대기 시간 단축)."""
    pol = policy(session)
    if not pol.get("enabled", True):
        return []
    graph = dependency_graph(session, pol)
    downs = [wf for wf, ups in graph.items() if workflow_code in ups]
    if not downs:
        return []
    released = []
    now = utcnow()
    for j in session.execute(select(Job).where(Job.kind == "workflow", Job.status == "queued", Job.workflow_code.in_(downs), Job.run_after > now)).scalars():
        last = session.execute(select(AgentDecision).where(AgentDecision.agent_code == AGENT, AgentDecision.job_id == j.id).order_by(AgentDecision.id.desc()).limit(1)).scalar()
        if last is not None and last.decision == "hold" and hold_reason(session, j, graph, pol) is None:
            j.run_after = now
            _record(session, j, "release", f"상위 {workflow_code} 완료 — 바로 실행", {"upstream": [workflow_code]})
            released.append(j.id)
    session.commit()
    return released
