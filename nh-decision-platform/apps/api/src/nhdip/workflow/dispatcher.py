"""아웃박스 디스패처 — 변경 이벤트 → 관련 워크플로우만 작업 생성 (EVT-02~05).

매칭 = 명시 트리거(cfg.workflow_trigger) ∪ 계보(지표·바인딩이 참조하는 데이터셋).
같은 워크플로우의 대기 작업이 있으면 원인을 누적하고 실행 시각을 디바운스만큼 늦춘다(병합).
실행 중인 워크플로우의 작업은 끝날 때까지 대기한다(동시 실행 1개).
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import and_, exists, select, text
from sqlalchemy.orm import Session, aliased

from nhdip.models import Job, Metric, OutboxEvent, Setting, ViewBinding, Workflow, WorkflowTrigger, utcnow


def _datasets_in(obj: Any) -> set[str]:
    from nhdip.graph.projection import _datasets_in_args

    return _datasets_in_args(obj)


def match_event(session: Session, ev: OutboxEvent) -> dict[str, list[str]]:
    """{workflow_code: [사유...]}"""
    p = ev.payload or {}
    out: dict[str, list[str]] = {}
    enabled = {w.code for w in session.execute(select(Workflow).where(Workflow.enabled)).scalars()}

    def add(wf: str, reason: str):
        if wf in enabled:
            out.setdefault(wf, []).append(reason)

    if ev.type == "manual" and p.get("workflow"):
        add(p["workflow"], "수동 실행")
        return out
    if ev.type == "schedule" and p.get("workflow"):
        add(p["workflow"], f"trigger:cron({p.get('cron')})")
        return out
    for t in session.execute(select(WorkflowTrigger).where(WorkflowTrigger.enabled)).scalars():
        if t.kind == "any" and t.target in ("*", ev.type.split(".")[0]):
            add(t.workflow_code, f"trigger:any({t.target})")
        elif t.kind in ("dataset", "master") and ev.type.startswith("dataset.") and t.target == p.get("dataset"):
            add(t.workflow_code, f"trigger:{t.kind}({t.target})")
        elif t.kind == "doc_class" and ev.type.startswith("document.") and t.target == p.get("doc_class"):
            add(t.workflow_code, f"trigger:doc_class({t.target})")
        elif t.kind == "event" and t.target == ev.type:
            add(t.workflow_code, f"trigger:event({t.target})")
        elif t.kind == "rule" and ev.type == "rule.changed" and t.target in ("*", p.get("rule")):
            add(t.workflow_code, f"trigger:rule({t.target})")
        elif t.kind == "setting" and ev.type == "config.changed" and p.get("kind") == "setting" and t.target == p.get("key"):
            add(t.workflow_code, f"trigger:setting({t.target})")
    if ev.type.startswith("dataset.") and p.get("dataset"):
        ds = p["dataset"]
        for m in session.execute(select(Metric).where(Metric.enabled)).scalars():
            if ds in _datasets_in(m.args):
                add(m.workflow_code, f"lineage:metric({m.code})")
        for b in session.execute(select(ViewBinding).where(ViewBinding.enabled)).scalars():
            if ds in _datasets_in(b.params):
                add(b.workflow_code, f"lineage:binding({b.builder})")
    # 사유 중복 제거 + 요약(지표 계보는 개수만)
    for wf, reasons in out.items():
        lineage = [r for r in reasons if r.startswith("lineage:metric")]
        others = list(dict.fromkeys(r for r in reasons if not r.startswith("lineage:metric")))
        out[wf] = others + ([f"lineage:metrics×{len(lineage)} ({lineage[0][15:-1]} 등)"] if lineage else [])
    return out


def _debounce(session: Session, wf: str, ev: OutboxEvent) -> int:
    if ev.type in ("manual", "schedule"):
        return 0
    trig = [t.debounce_sec for t in session.execute(select(WorkflowTrigger).where(WorkflowTrigger.workflow_code == wf, WorkflowTrigger.enabled)).scalars() if t.debounce_sec is not None]
    if trig:
        return min(trig)
    s = session.get(Setting, "workflow.debounce_default_sec")
    return int(s.value) if s is not None else 60


def enqueue(session: Session, wf: str, cause: dict[str, Any], delay_sec: int) -> Job:
    now = utcnow()
    job = session.execute(
        select(Job).where(Job.kind == "workflow", Job.workflow_code == wf, Job.status == "queued").with_for_update(skip_locked=True).limit(1)
    ).scalar()
    if job:
        job.causes = [*job.causes, cause][-200:]
        # 디바운스 연장(최초 대기 생성 후 최대 5배까지만)
        cap = job.created_at + timedelta(seconds=max(delay_sec, 1) * 5)
        job.run_after = min(max(job.run_after, now + timedelta(seconds=delay_sec)), cap) if delay_sec else now
        return job
    job = Job(kind="workflow", workflow_code=wf, causes=[cause], status="queued", run_after=now + timedelta(seconds=delay_sec))
    session.add(job)
    return job


def dispatch_once(session: Session, limit: int = 50) -> int:
    events = session.execute(
        select(OutboxEvent).where(OutboxEvent.dispatched_at.is_(None)).order_by(OutboxEvent.id).with_for_update(skip_locked=True).limit(limit)
    ).scalars().all()
    for ev in events:
        matched = match_event(session, ev)
        cause = {"event_id": ev.id, "type": ev.type, "payload": ev.payload, "at": ev.created_at.isoformat(), "actor": ev.actor, "trace_id": ev.trace_id}
        for wf, reasons in matched.items():
            enqueue(session, wf, {**cause, "reasons": reasons}, _debounce(session, wf, ev))
        ev.matched = [{"workflow": wf, "reasons": r} for wf, r in matched.items()]
        ev.dispatched_at = utcnow()
    session.commit()
    return len(events)


def claim_job(session: Session, worker_id: str) -> Job | None:
    running = aliased(Job)
    q = (
        select(Job)
        .where(
            Job.status == "queued",
            Job.run_after <= utcnow(),
            ~exists().where(and_(running.workflow_code == Job.workflow_code, running.status == "running")),
        )
        .order_by(Job.run_after, Job.id)
        .with_for_update(skip_locked=True, of=Job)
        .limit(10)
    )
    from .orchestrator import gate

    job = None
    for cand in session.execute(q).scalars().all():
        # 오케스트레이터 — 상위 워크플로우 작업이 남아 있으면 미루고 다음 후보 (B.30)
        if gate(session, cand):
            job = cand
            break
    if not job:
        session.commit()  # 미룬 작업의 run_after · 결정 기록 저장
        return None
    job.status = "running"
    job.locked_by = worker_id
    job.locked_at = utcnow()
    job.attempts += 1
    session.commit()
    return job


def recover_stale(session: Session, older_than_min: int = 30) -> int:
    res = session.execute(
        text("UPDATE ops.job SET status='queued', locked_by=NULL WHERE status='running' AND locked_at < now() - make_interval(mins => :m)"),
        {"m": older_than_min},
    )
    session.commit()
    return res.rowcount or 0
