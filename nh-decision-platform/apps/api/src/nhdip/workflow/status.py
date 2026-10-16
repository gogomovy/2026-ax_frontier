"""흐름 갱신 상태 (Phase P · AGW-08 · AGW-09) — 언제 · 왜 다시 계산되는지(감지 조건 · 정기 실행 · 상위 흐름)와 지금 반영 대기 · 실행 중인지.

업무 화면(`GET /analysis/status`)과 관리자 [자동 실행 · 변경 감지](`GET /admin/automation`)가 같은 계산을 쓴다. 읽기만 한다.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from nhdip.models import AgentDecision, Dataset, Job, Workflow, WorkflowRun, WorkflowTrigger, utcnow

EVENT_LABEL = {"goal.confirmed": "경영목표 확정 · 수정", "contract.changed": "정의서 변경", "change.detected": "변화 감지", "kb.indexed": "지식 색인"}
CAUSE_LABEL = {"manual": "수동 실행", "schedule": "정기 실행", "agent.followup": "플래너 후속 실행", "change.detected": "다른 흐름 변화 감지", "metrics.changed": "상위 흐름 결과 변화",
               "rule.changed": "판정 규칙 변경", "config.changed": "정의 · 설정 변경", "goal.confirmed": "경영목표 확정", "contract.changed": "정의서 변경"}
DAYS = {"*": "매일", "1-5": "평일", "0,6": "주말", "6,0": "주말", "0": "일요일", "1": "월요일", "2": "화요일", "3": "수요일", "4": "목요일", "5": "금요일", "6": "토요일"}


def cron_label(expr: str) -> str:
    """'40 6 * * *' → '매일 06:40' — 흔한 꼴만 말로, 나머지는 식 그대로."""
    parts = (expr or "").split()
    if len(parts) == 5 and re.fullmatch(r"\d{1,2}", parts[0]) and re.fullmatch(r"\d{1,2}", parts[1]) and parts[2] == "*" and parts[3] == "*":
        day = DAYS.get(parts[4])
        if day:
            return f"{day} {int(parts[1]):02d}:{int(parts[0]):02d}"
    if len(parts) == 5 and re.fullmatch(r"\d{1,2}", parts[0]) and re.fullmatch(r"\d{1,2}", parts[1]) and re.fullmatch(r"\d{1,2}", parts[2]) and parts[3] == "*" and parts[4] == "*":
        return f"매월 {int(parts[2])}일 {int(parts[1]):02d}:{int(parts[0]):02d}"
    return expr


def cause_label(c: dict[str, Any], names: dict[str, str] | None = None) -> str:
    t = str(c.get("type") or "")
    p = c.get("payload") or {}
    names = names or {}
    if t.startswith("dataset."):
        ds = p.get("dataset")
        nm = names.get(str(ds), ds)
        return f"자료 '{nm}' " + ("되돌림" if p.get("rollback") else "삭제" if t == "dataset.deleted" else "새 판")
    if t.startswith("document."):
        return f"문서 {'삭제' if t == 'document.deleted' else '반영'}({p.get('doc_class') or '-'})"
    if t == "metrics.changed":
        return f"상위 흐름 '{names.get(str(p.get('workflow')), p.get('workflow'))}' 결과 변화"
    return CAUSE_LABEL.get(t, t)


def _triggers(session: Session, wf: str, tz: Any, now: datetime, ds_names: dict[str, str]) -> dict[str, Any]:
    from .scheduler import is_valid, next_fire

    out: dict[str, Any] = {"data": [], "team": None, "common": False, "events": [], "rules": [], "docClasses": [], "any": [], "cron": []}
    for t in session.execute(select(WorkflowTrigger).where(WorkflowTrigger.workflow_code == wf, WorkflowTrigger.enabled).order_by(WorkflowTrigger.id)).scalars():
        if t.kind in ("dataset", "master"):
            nm = "모든 자료" if t.target == "*" else ds_names.get(t.target, t.target)
            if nm not in out["data"]:
                out["data"].append(nm)
        elif t.kind == "team":
            out["team"] = t.target
        elif t.kind == "common":
            out["common"] = True
        elif t.kind == "event":
            out["events"].append(EVENT_LABEL.get(t.target, t.target))
        elif t.kind == "rule":
            out["rules"].append(t.target)
        elif t.kind == "doc_class":
            out["docClasses"].append(t.target)
        elif t.kind == "any":
            out["any"].append(t.target)
        elif t.kind == "cron" and is_valid(t.target):
            nxt = next_fire(t.target, max(now, t.last_fired_at) if t.last_fired_at else now, tz)
            out["cron"].append({"expr": t.target, "label": cron_label(t.target), "next": nxt.isoformat(), "lastFiredAt": t.last_fired_at.isoformat() if t.last_fired_at else None})
    return out


def _pending(session: Session, wf: str, names: dict[str, str]) -> tuple[str, dict[str, Any] | None]:
    job = session.execute(select(Job).where(Job.kind == "workflow", Job.workflow_code == wf, Job.status.in_(("running", "queued", "approval"))).order_by(Job.id.desc()).limit(1)).scalar()
    if job is None:
        return "idle", None
    state = {"running": "running", "approval": "approval"}.get(job.status, "queued")
    if state == "queued":
        last = session.execute(select(AgentDecision).where(AgentDecision.agent_code == "orchestrator", AgentDecision.job_id == job.id).order_by(AgentDecision.id.desc()).limit(1)).scalar()
        if last is not None and last.decision == "hold":
            state = "held"
    labels = list(dict.fromkeys(cause_label(c, names) for c in (job.causes or []) if isinstance(c, dict)))
    return state, {"jobId": job.id, "since": job.created_at.isoformat() if job.created_at else None, "runAfter": job.run_after.isoformat() if job.run_after else None,
                   "causes": labels[-5:], "causeCount": len(job.causes or [])}


def workflow_status(session: Session, wf: Workflow, *, graph: dict[str, dict[str, list[str]]] | None = None, names: dict[str, str] | None = None,
                    ds_names: dict[str, str] | None = None, tz: Any = None) -> dict[str, Any]:
    from .orchestrator import dependency_graph
    from .scheduler import _tz

    tz = tz or _tz(session)
    now = utcnow()
    names = names if names is not None else {w.code: w.name for w in session.execute(select(Workflow)).scalars()}
    ds_names = ds_names if ds_names is not None else {d.code: d.name for d in session.execute(select(Dataset)).scalars()}
    graph = graph if graph is not None else dependency_graph(session)
    ups = [u for u in (graph.get(wf.code) or {}) if u not in ("wf_graph_projection", "wf_ontology_build")]
    downs = [w for w, u in graph.items() if wf.code in u]
    state, pending = _pending(session, wf.code, {**names, **ds_names})
    last = session.execute(select(WorkflowRun).where(WorkflowRun.workflow_code == wf.code).order_by(WorkflowRun.started_at.desc()).limit(1)).scalar()
    ok = session.execute(select(WorkflowRun).where(WorkflowRun.workflow_code == wf.code, WorkflowRun.status.in_(("succeeded", "degraded"))).order_by(WorkflowRun.started_at.desc()).limit(1)).scalar()
    trig = _triggers(session, wf.code, tz, now, ds_names)
    # 계보 — 지표 · 화면 연결이 읽는 자료도 '자료 변경 시' 다시 계산된다(디스패처 lineage:metric · binding)
    from nhdip.graph.projection import _datasets_in_args
    from nhdip.models import Metric, ViewBinding

    refs: set[str] = set()
    for m in session.execute(select(Metric).where(Metric.workflow_code == wf.code, Metric.enabled)).scalars():
        refs |= _datasets_in_args(m.args)
    for b in session.execute(select(ViewBinding).where(ViewBinding.workflow_code == wf.code, ViewBinding.enabled)).scalars():
        refs |= _datasets_in_args(b.params)
    for r in sorted(refs):
        nm = ds_names.get(r, r)
        if nm not in trig["data"]:
            trig["data"].append(nm)
    return {
        "workflow": wf.code, "name": wf.name, "enabled": wf.enabled, "state": state, "pending": pending,
        "lastRun": {"id": last.id, "status": last.status, "startedAt": last.started_at.isoformat() if last.started_at else None, "finishedAt": last.finished_at.isoformat() if last.finished_at else None} if last else None,
        "lastSuccessAt": (ok.finished_at or ok.started_at).isoformat() if ok and (ok.finished_at or ok.started_at) else None,
        "triggers": {**trig, "upstream": [names.get(u, u) for u in ups], "upstreamCodes": ups, "downstream": len(downs), "lineage": True},
    }
