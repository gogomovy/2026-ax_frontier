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
    if ev.type == "agent.followup" and p.get("workflow"):
        # 플래너가 정한 후속 실행 (B.31) — 연쇄(chain)는 원인에 남아 오케스트레이터가 순서 · 깊이를 관리
        add(p["workflow"], f"agent:{p.get('by', 'planner')}({str(p.get('reason') or '')[:80]})")
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


def needs_approval(session: Session, wf: str, cause: dict[str, Any]) -> bool:
    """사람 승인 (B.32 · HITL) — 설정 orchestrator.policy.require_approval 에 든 워크플로우는
    자동 이벤트(데이터 · 규칙 · 에이전트 판단)로 생긴 작업을 관리자가 승인해야 실행한다. 수동 실행은 바로 실행."""
    from .orchestrator import policy

    req = policy(session).get("require_approval") or []
    if cause.get("type") in ("manual",) or not req:
        return False
    return "*" in req or wf in req


def enqueue(session: Session, wf: str, cause: dict[str, Any], delay_sec: int) -> Job:
    now = utcnow()
    approval = needs_approval(session, wf, cause)
    status = "approval" if approval else "queued"
    job = session.execute(
        select(Job).where(Job.kind == "workflow", Job.workflow_code == wf, Job.status == status).with_for_update(skip_locked=True).limit(1)
    ).scalar()
    if job and approval:
        job.causes = [*job.causes, cause][-200:]  # 승인 대기 작업에 원인만 누적
        return job
    if job:
        job.causes = [*job.causes, cause][-200:]
        # 디바운스 연장(최초 대기 생성 후 최대 5배까지만)
        cap = job.created_at + timedelta(seconds=max(delay_sec, 1) * 5)
        job.run_after = min(max(job.run_after, now + timedelta(seconds=delay_sec)), cap) if delay_sec else now
        return job
    job = Job(kind="workflow", workflow_code=wf, causes=[cause], status=status, run_after=now + timedelta(seconds=delay_sec))
    session.add(job)
    return job


def _chain_block(session: Session, ev: OutboxEvent, wf: str) -> str | None:
    """연쇄 안전장치 (B.32) — 이미 연쇄에 있는 워크플로우(순환)와 최대 연쇄 깊이를 넘는 후속 실행을 막는다."""
    if ev.type in ("manual", "schedule"):
        return None
    p = ev.payload or {}
    chain = list(p.get("chain") or [])
    if wf in chain:
        return f"순환 방지 — {wf} 는 이미 연쇄({' → '.join(chain)})에 있음"
    if chain:
        from .orchestrator import policy

        if len(chain) >= int(policy(session).get("max_chain", 3)):
            return f"최대 연쇄 깊이 {len(chain)} 도달 (orchestrator.policy.max_chain)"
    return None


ROUTE_CLAIM_MIN = 5


def _needs_route(session: Session, ev: OutboxEvent) -> bool:
    from .orchestrator import policy

    pol = policy(session)
    return bool(pol.get("enabled", True)) and ev.type in set(pol.get("route_on") or [])


def dispatch_once(session: Session, limit: int = 50) -> int:
    """이벤트 → 작업. 두 단계 (B.32):
    1) 이벤트 잠금 → 명시 매칭(빠름) — LLM 경로 지정이 필요한 이벤트는 잠금을 풀고 따로 처리
    2) 경로 지정(LLM 호출)은 잠금 밖에서 → 다시 잠가 아직 미처리면 작업 생성
    이벤트 하나의 오류는 롤백 후 다음 이벤트로 넘어간다(전체 디스패치가 멈추지 않음).
    """
    import logging

    log = logging.getLogger("nhdip.dispatcher")
    events = session.execute(
        select(OutboxEvent).where(OutboxEvent.dispatched_at.is_(None)).order_by(OutboxEvent.id).with_for_update(skip_locked=True).limit(limit)
    ).scalars().all()
    plain, routed = [], []
    for ev in events:
        (routed if _needs_route(session, ev) else plain).append(ev.id)
    if routed:
        # 경로 판단 선점 (B.33) — 잠금을 쥔 동안 routing_at 을 찍은 이벤트만 이 워커가 판단한다.
        # 다른 워커가 판단 중(5분 이내 선점)이면 건너뛰고, 그 워커가 디스패치한다. 선점 후 워커가 죽으면 5분 뒤 다시 선점 가능.
        claimed = session.execute(
            text(
                "UPDATE ops.outbox_event SET routing_at = now() WHERE id = ANY(:ids) AND dispatched_at IS NULL "
                "AND (routing_at IS NULL OR routing_at < now() - make_interval(mins => :m)) RETURNING id"
            ),
            {"ids": routed, "m": ROUTE_CLAIM_MIN},
        ).scalars().all()
        routed = [i for i in routed if i in set(claimed)]
    session.commit()  # 잠금 해제 — 경로 지정 대상은 LLM 호출 동안 잠그지 않는다
    n = 0
    for eid in plain + routed:
        matched_pre: dict[str, list[str]] | None = None
        if eid in routed:
            ev0 = session.get(OutboxEvent, eid)
            if ev0 is None or ev0.dispatched_at is not None:
                continue
            try:
                from .orchestrator import route

                matched_pre = route(session, ev0, match_event(session, ev0))  # 오케스트레이터 경로 지정 (LLM 판단 · 규칙 대체)
                session.commit()  # 판단 기록 보존
            except Exception:  # noqa: BLE001 — 경로 지정 실패가 디스패치를 막지 않는다
                session.rollback()
                logging.getLogger("nhdip.orchestrator").exception("route failed")
                matched_pre = None
        try:
            # 선점한(경로 판단한) 이벤트는 기다려서라도 잠근다 — 다른 워커의 1단계 묶음 잠금은 짧고, 건너뛰면 선점 만료까지 묶인다 (B.33)
            q_ev = select(OutboxEvent).where(OutboxEvent.id == eid, OutboxEvent.dispatched_at.is_(None))
            ev = session.execute(q_ev.with_for_update() if eid in routed else q_ev.with_for_update(skip_locked=True)).scalar()
            if ev is None:
                session.rollback()
                continue  # 다른 워커가 처리함
            matched = matched_pre if matched_pre is not None else match_event(session, ev)
            cause = {"event_id": ev.id, "type": ev.type, "payload": ev.payload, "at": ev.created_at.isoformat(), "actor": ev.actor, "trace_id": ev.trace_id}
            record, blocked = [], []
            for wf, reasons in matched.items():
                why = _chain_block(session, ev, wf)
                if why:
                    blocked.append({"workflow": wf, "reason": why})
                    continue
                enqueue(session, wf, {**cause, "reasons": reasons}, _debounce(session, wf, ev))
                record.append({"workflow": wf, "reasons": reasons})
            ev.matched = record + [{"workflow": b["workflow"], "reasons": [], "blocked": b["reason"]} for b in blocked]
            ev.dispatched_at = utcnow()
            session.commit()
            n += 1
        except Exception:  # noqa: BLE001
            session.rollback()
            log.exception("dispatch failed (event %s)", eid)
    return n


def claim_job(session: Session, worker_id: str) -> Job | None:
    from nhdip.locks import try_lock

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
        # 같은 워크플로우를 두 워커가 동시에 집지 않도록 — 워크플로우 잠금 후 실행 중 작업을 다시 확인 (B.32)
        if cand.workflow_code and not try_lock(session, f"workflow:{cand.workflow_code}"):
            continue
        if cand.workflow_code and session.execute(select(Job.id).where(Job.workflow_code == cand.workflow_code, Job.status == "running").limit(1)).first():
            continue
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


def _close_runs(session: Session, ids: list[int], why: str) -> None:
    if ids:
        session.execute(
            text("UPDATE ops.workflow_run SET status='failed', error=:why, finished_at=now() WHERE status='running' AND job_id = ANY(:ids)"),
            {"ids": ids, "why": why},
        )


def recover_own_orphans(session: Session, hostname: str, worker_id: str) -> int:
    """기동 시 — 같은 호스트의 이전 기동이 실행 중으로 남긴 작업을 다시 대기열로 (B.33).
    컨테이너 재시작은 hostname 이 같으므로, 이 호스트에서 잡혔는데 지금 워커가 아닌 작업은 모두 고아다."""
    res = session.execute(
        text(
            "UPDATE ops.job SET status='queued', locked_by=NULL, run_after=now() "
            "WHERE status='running' AND locked_by LIKE :h AND locked_by <> :me RETURNING id"
        ),
        {"h": f"{hostname}:%", "me": worker_id},
    )
    ids = [r[0] for r in res]
    _close_runs(session, ids, "워커 재시작 — 작업을 다시 대기열로 돌림")
    session.commit()
    return len(ids)


def recover_stale(session: Session, older_than_min: int = 30, heartbeat_stale_sec: int = 120) -> int:
    """멈춘 작업 복구 (B.32) — 잡은 워커의 심장박동이 끊긴 실행 중 작업만 다시 대기로.

    오래 걸리는 정상 실행(워커 살아 있음)은 건드리지 않는다(실행 시간 상한은 워커 감시 스레드가 지킨다).
    고아가 된 실행(running 인 workflow_run)은 실패로 닫는다.
    """
    res = session.execute(
        text(
            "UPDATE ops.job j SET status='queued', locked_by=NULL, run_after=now() "
            "WHERE j.status='running' AND j.locked_at < now() - make_interval(mins => :m) "
            "AND NOT EXISTS (SELECT 1 FROM ops.worker_heartbeat h WHERE h.worker_id = j.locked_by AND h.seen_at > now() - make_interval(secs => :hb)) "
            "RETURNING j.id"
        ),
        {"m": older_than_min, "hb": heartbeat_stale_sec},
    )
    ids = [r[0] for r in res]
    _close_runs(session, ids, "워커 중단 — 작업을 다시 대기열로 돌림")
    session.commit()
    return len(ids)
