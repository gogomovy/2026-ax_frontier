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

from nhdip.models import Job, Metric, OutboxEvent, Setting, ViewBinding, Workflow, WorkflowNode, WorkflowTrigger, utcnow


def _datasets_in(obj: Any) -> set[str]:
    from nhdip.graph.projection import _datasets_in_args

    return _datasets_in_args(obj)


BASE_WORKFLOWS = {"wf_graph_projection", "wf_ontology_build"}  # 기반 흐름 — 업무 판단 전파 대상이 아니다


def _is_common_event(session: Session, etype: str, p: dict[str, Any]) -> bool:
    if p.get("common"):
        return True
    if etype.startswith("dataset.") and p.get("dataset"):
        from nhdip.models import Dataset

        d = session.get(Dataset, p["dataset"])
        return bool(d is not None and getattr(d, "common", False))
    if etype.startswith("document.") and p.get("doc_class"):
        from nhdip.common_db import is_common_doc_class

        return is_common_doc_class(session, p.get("doc_class"))
    return False


def downstream_of(session: Session, p: dict[str, Any]) -> dict[str, list[str]]:
    """상위 흐름 결과 변화(metrics.changed) → 그 지표를 참조하는 다른 흐름 {흐름: [지표...]} (Phase P · AGW-03).
    이 이벤트를 낸 실행이 끝난 뒤 이미 시작한 하위 실행이 있으면 뺀다(그 실행이 새 값을 읽었다 — 두 번 돌지 않게)."""
    from datetime import datetime

    from nhdip.models import WorkflowRun

    changed = {str(c) for c in p.get("metrics") or []}
    src = p.get("workflow")
    out: dict[str, list[str]] = {}
    for m in session.execute(select(Metric).where(Metric.enabled)).scalars():
        if m.workflow_code == src or not m.workflow_code:
            continue
        hit = [ref["metric"] for ref in (m.args or {}).values() if isinstance(ref, dict) and ref.get("metric") in changed]
        if hit:
            out.setdefault(m.workflow_code, [])
            out[m.workflow_code] += [h for h in hit if h not in out[m.workflow_code]]
    fin = None
    try:
        fin = datetime.fromisoformat(str(p["finished_at"])) if p.get("finished_at") else None
    except ValueError:
        fin = None
    if fin is not None:
        for wf in list(out):
            if session.execute(select(WorkflowRun.id).where(WorkflowRun.workflow_code == wf, WorkflowRun.started_at >= fin).limit(1)).first():
                out.pop(wf)
    return out


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
    # 이 이벤트의 데이터셋을 가리키는 이름들 — 코드 + 업무 구성의 자료 이름(Phase O · BIZ-03: 구성은 코드가 아니라 자료 이름으로 원천을 적는다)
    refs: set[str] = set()
    if ev.type.startswith("dataset.") and p.get("dataset"):
        from nhdip.data.sources import Resolver

        refs = Resolver(session).refs_for(p["dataset"])
    # 팀 · 공통 조건 (Phase P · TDB-07 · AGW-04) — 자료 · 문서 이벤트의 소유 조직 · 공통 통합 DB 여부
    data_ev = ev.type.startswith("dataset.") or ev.type.startswith("document.")
    owner = p.get("owner_org") if data_ev else None
    is_common = data_ev and _is_common_event(session, ev.type, p)
    team_orgs: dict[str, set[str]] = {}

    def in_team(root: str) -> bool:
        if not owner:
            return False
        if root not in team_orgs:
            from nhdip.analysis_agents.team import subtree

            team_orgs[root] = subtree(session, root)
        return owner in team_orgs[root]

    for t in session.execute(select(WorkflowTrigger).where(WorkflowTrigger.enabled)).scalars():
        if t.kind == "team" and data_ev:
            if in_team(t.target):
                add(t.workflow_code, f"trigger:team({t.target}·{owner})")
        elif t.kind == "common" and data_ev:
            if is_common:
                add(t.workflow_code, "trigger:common(공통 통합 DB)")
        elif t.kind == "any" and t.target in ("*", ev.type.split(".")[0]):
            add(t.workflow_code, f"trigger:any({t.target})")
        elif t.kind in ("dataset", "master") and ev.type.startswith("dataset.") and (t.target == "*" or t.target in refs):
            add(t.workflow_code, f"trigger:{t.kind}({p.get('dataset') if t.target == '*' else t.target})")
        elif t.kind == "config" and ev.type == "config.changed" and t.target in ("*", p.get("kind")):
            # 정의 변경(Phase M · DYN-01) — 예: 데이터셋 정의가 생기거나 바뀌면 온톨로지 구축이 구조를 다시 파악
            add(t.workflow_code, f"trigger:config({p.get('kind')}:{p.get('code') or p.get('key') or ''})")
        elif t.kind == "doc_class" and ev.type.startswith("document.") and t.target == p.get("doc_class"):
            add(t.workflow_code, f"trigger:doc_class({t.target})")
        elif t.kind == "event" and t.target == ev.type:
            add(t.workflow_code, f"trigger:event({t.target})")
        elif t.kind == "rule" and ev.type == "rule.changed" and t.target in ("*", p.get("rule")):
            add(t.workflow_code, f"trigger:rule({t.target})")
        elif t.kind == "setting" and ev.type == "config.changed" and p.get("kind") == "setting" and t.target == p.get("key"):
            add(t.workflow_code, f"trigger:setting({t.target})")
    if ev.type == "contract.changed":
        # 정의서 계보 (B.38) — 바뀐 표를 적재하는 워크플로우(적재 노드 config.tables)
        changed = set(p.get("tables") or ([p["table"]] if p.get("table") else []))
        for n in session.execute(select(WorkflowNode).where(WorkflowNode.impl == "materialize_contracts", WorkflowNode.enabled)).scalars():
            hit = sorted(changed & set((n.config or {}).get("tables") or []))
            if hit:
                add(n.workflow_code, f"lineage:contract({', '.join(hit[:3])})")
    if is_common and ev.type.startswith("document."):
        # 공통 통합 DB 문서(AGW-04) — 모든 업무 흐름이 공통 분류를 근거로 보므로 근거 검색 노드가 있는 흐름(기반 흐름 제외). 서술 갱신 여부는 플래너가 판단
        for n in session.execute(select(WorkflowNode).where(WorkflowNode.impl == "retrieve_evidence", WorkflowNode.enabled)).scalars():
            if n.workflow_code not in BASE_WORKFLOWS:
                add(n.workflow_code, f"lineage:common_doc({p.get('doc_class')})")
    if ev.type == "metrics.changed" and p.get("metrics"):
        for wf, codes in downstream_of(session, p).items():
            add(wf, f"lineage:upstream({p.get('workflow')} · {codes[0]}{f' 외 {len(codes) - 1}' if len(codes) > 1 else ''})")
    if ev.type.startswith("dataset.") and p.get("dataset"):
        for m in session.execute(select(Metric).where(Metric.enabled)).scalars():
            if refs & _datasets_in(m.args):
                add(m.workflow_code, f"lineage:metric({m.code})")
        for b in session.execute(select(ViewBinding).where(ViewBinding.enabled)).scalars():
            if refs & _datasets_in(b.params):
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
        return max(0, min(trig))
    s = session.get(Setting, "workflow.debounce_default_sec")
    try:
        return max(0, int(s.value)) if s is not None else 60
    except (TypeError, ValueError):  # 관리자가 숫자가 아닌 값을 넣어도 모든 이벤트의 디스패치가 멈추지 않게
        return 60


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
        if job.attempts:
            return job  # 실패 뒤 재시도 대기 중인 작업 — 원인만 더하고 실행 시각(백오프)은 앞당기지 않는다
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


IMPACT_AGENT = "impact_assessor"
IMPACT_EVENTS = ("dataset.", "document.", "metrics.changed", "goal.", "rule.changed", "contract.changed", "change.detected")
REASON_KIND = (("trigger:team", "팀"), ("trigger:common", "공통"), ("lineage:common_doc", "공통 문서"), ("lineage:upstream", "상위 흐름"), ("lineage:metric", "계보"), ("lineage:binding", "계보"),
               ("lineage:contract", "정의서"), ("agent:orchestrator", "LLM 경로"), ("trigger:", "조건"))


def unchanged_reason(ev: OutboxEvent) -> str | None:
    """같은 구획 현재 판과 같은 파일(해시 · 행 수)을 다시 반영한 자료 이벤트 — 재계산하지 않는 사유 (UPV-05)."""
    p = ev.payload or {}
    if ev.type == "dataset.committed" and p.get("unchanged") and not p.get("rollback"):
        return f"변경 없음 — 같은 파일 · 같은 행(판 {p.get('same_as') or '-'})을 다시 반영해 다시 계산하지 않음"
    return None


def _event_label(ev: OutboxEvent) -> str:
    p = ev.payload or {}
    if ev.type.startswith("dataset."):
        return f"자료 {p.get('dataset')} " + ("되돌림" if p.get("rollback") else "삭제" if ev.type == "dataset.deleted" else f"새 판 v{p.get('version')}")
    if ev.type.startswith("document."):
        return f"문서 {p.get('doc_code') or p.get('document_id')}({p.get('doc_class')}) " + ("삭제" if ev.type == "document.deleted" else "반영")
    if ev.type == "metrics.changed":
        return f"상위 흐름 {p.get('workflow')} 지표 {len(p.get('metrics') or [])}개 변화"
    return ev.type


def record_impact(session: Session, ev: OutboxEvent, matched: dict[str, list[str]], blocked: list[dict[str, Any]], skip: str | None = None) -> None:
    """영향 판단 기록 (Phase P · AGW-02) — 자동 이벤트마다 영향받는 흐름과 이유를 ops.agent_decision 에 남긴다. 실패는 디스패치를 막지 않는다."""
    if not ev.type.startswith(IMPACT_EVENTS):
        return
    from nhdip.models import AgentDecision

    kinds: dict[str, int] = {}
    for reasons in matched.values():
        seen = set()
        for r in reasons:
            k = next((lbl for pre, lbl in REASON_KIND if r.startswith(pre)), "기타")
            if k not in seen:
                seen.add(k)
                kinds[k] = kinds.get(k, 0) + 1
    label = _event_label(ev)
    if skip:
        summary = f"{label} → {skip}"
    elif matched:
        summary = f"{label} → 흐름 {len(matched)}개 다시 계산 ({' · '.join(f'{k} {v}' for k, v in kinds.items())})" + (f" · 막음 {len(blocked)}" if blocked else "")
    else:
        summary = f"{label} → 영향받는 흐름 없음" + (f" · 막음 {len(blocked)}" if blocked else "")
    try:
        with session.begin_nested():
            session.add(AgentDecision(agent_code=IMPACT_AGENT, workflow_code=None, decision="skip" if skip else "impact", summary=summary[:500],
                                      detail={"event": {"id": ev.id, "type": ev.type, "label": label}, "matched": matched, "blocked": blocked, "kinds": kinds, **({"skip": skip} if skip else {})}))
    except Exception:  # noqa: BLE001
        import logging

        logging.getLogger("nhdip.dispatcher").exception("impact record failed (event %s)", ev.id)


ROUTE_CLAIM_MIN = 5
ROUTE_BATCH = 5  # 한 번의 디스패치 순회에서 LLM 경로 판단을 하는 이벤트 수


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
    routed = routed[:ROUTE_BATCH]  # LLM 경로 판단은 직렬이라 한 번에 몇 건만 — 나머지는 다음 순회에서(작업 집기 · 정기 작업이 오래 막히지 않게)
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
            skip = unchanged_reason(ev)
            if skip:
                # 판단 에이전트(AGW-02) — 같은 파일 · 같은 행을 다시 반영한 이벤트는 결과가 바뀌지 않으므로 다시 계산하지 않는다
                ev.matched = [{"workflow": "(변경 없음)", "reasons": [], "blocked": skip}]
                ev.dispatched_at = utcnow()
                record_impact(session, ev, {}, [], skip=skip)
                session.commit()
                n += 1
                continue
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
            record_impact(session, ev, {r["workflow"]: r["reasons"] for r in record}, blocked)
            session.commit()
            n += 1
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            log.exception("dispatch failed (event %s)", eid)
            _note_dispatch_failure(session, eid, exc)
    return n


DISPATCH_MAX_ATTEMPTS = 5


def _note_dispatch_failure(session: Session, eid: int, exc: Exception) -> None:
    """디스패치가 실패한 이벤트 — 시도 횟수를 이벤트에 남기고, 몇 번 되풀이해도 안 되면 포기(처리됨 표시 + 운영 알림).
    예전에는 오류를 로그에만 남기고 이벤트를 그대로 둬서 매 순회 영원히 다시 시도했고, 50건이 막히면 뒤 이벤트가 영영 처리되지 않았다."""
    import logging

    try:
        ev = session.execute(select(OutboxEvent).where(OutboxEvent.id == eid, OutboxEvent.dispatched_at.is_(None)).with_for_update(skip_locked=True)).scalar()
        if ev is None:
            session.rollback()
            return
        prev = next((m.get("dispatchAttempts", 0) for m in (ev.matched or []) if isinstance(m, dict) and "dispatchAttempts" in m), 0)
        n = int(prev) + 1
        err = f"{type(exc).__name__}: {str(exc)[:200]}"
        if n >= DISPATCH_MAX_ATTEMPTS:
            ev.matched = [{"workflow": "(디스패치 실패)", "reasons": [], "blocked": f"{n}회 시도 후 포기 — {err}", "dispatchAttempts": n}]
            ev.dispatched_at = utcnow()
            from nhdip.alerts import raise_alert

            raise_alert(session, "dispatch_failed", "critical", f"이벤트 #{eid}({ev.type}) 디스패치 {n}회 실패 — 포기", {"event": eid, "type": ev.type, "error": err}, f"dispatch_failed:{eid}")
        else:
            ev.matched = [{"workflow": f"(재시도 {n}/{DISPATCH_MAX_ATTEMPTS})", "reasons": [], "blocked": err, "dispatchAttempts": n}]
        session.commit()
    except Exception:  # noqa: BLE001 — 실패 기록이 실패해도 디스패치 순회를 멈추지 않는다
        session.rollback()
        logging.getLogger("nhdip.dispatcher").exception("dispatch failure note failed (event %s)", eid)


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
        try:
            with session.begin_nested():  # 관리자가 고친 오케스트레이터 정책값이 잘못돼도(숫자 아님 등) 모든 작업이 영영 집히지 않는 일이 없게
                allowed = gate(session, cand)
        except Exception:  # noqa: BLE001
            import logging

            logging.getLogger("nhdip.dispatcher").exception("orchestrator gate failed — 정책 없이 실행 허용 (job %s)", cand.id)
            allowed = True
        if allowed:
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


RECOVER_GIVE_UP = "워커가 중단돼 복구했으나 최대 시도 횟수를 넘어 더 이상 다시 실행하지 않습니다(같은 작업이 계속 워커를 멈추게 할 수 있음) — 관리자 [파이프라인]에서 수동 실행하세요"


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
            "UPDATE ops.job SET status = CASE WHEN attempts >= max_attempts THEN 'failed' ELSE 'queued' END, locked_by=NULL, run_after=now(), "
            "finished_at = CASE WHEN attempts >= max_attempts THEN now() ELSE finished_at END, "
            "error = CASE WHEN attempts >= max_attempts THEN :why ELSE error END "
            "WHERE status='running' AND locked_by LIKE :h AND locked_by <> :me RETURNING id"
        ),
        {"h": f"{hostname}:%", "me": worker_id, "why": RECOVER_GIVE_UP},
    )
    ids = [r[0] for r in res]
    _close_runs(session, ids, "워커 재시작 — 작업을 다시 대기열로 돌림")
    session.commit()
    return len(ids)


def recover_stale(session: Session, older_than_min: int = 5, heartbeat_stale_sec: int = 120, idle_busy_min: int = 3) -> int:
    """멈춘 작업 복구 (B.32) — 다시 대기로 돌릴 실행 중 작업:
    ① 잡은 워커의 심장박동이 끊긴 것(컨테이너를 새로 만든 뒤 호스트 이름이 달라진 경우도 여기서 잡힌다),
    ② 워커는 살아 있는데 그 워커가 지금 이 작업을 하고 있지 않다고 알리는 것(작업을 끝내고 상태를 저장하다 실패해 'running' 으로 남은 경우).
    오래 걸리는 정상 실행(워커가 그 작업을 하고 있다고 알림)은 건드리지 않는다(실행 시간 상한은 워커 감시 스레드가 지킨다).
    고아가 된 실행(running 인 workflow_run)은 실패로 닫고, 이미 최대 시도 횟수만큼 집힌 작업은 다시 돌리지 않고 실패로 끝낸다(무한 반복 방지).
    """
    res = session.execute(
        text(
            "UPDATE ops.job j SET status = CASE WHEN j.attempts >= j.max_attempts THEN 'failed' ELSE 'queued' END, locked_by=NULL, run_after=now(), "
            "finished_at = CASE WHEN j.attempts >= j.max_attempts THEN now() ELSE j.finished_at END, "
            "error = CASE WHEN j.attempts >= j.max_attempts THEN :why ELSE j.error END "
            "WHERE j.status='running' AND ("
            " (j.locked_at < now() - make_interval(mins => :m) "
            "  AND NOT EXISTS (SELECT 1 FROM ops.worker_heartbeat h WHERE h.worker_id = j.locked_by AND h.seen_at > now() - make_interval(secs => :hb))) "
            " OR (j.locked_at < now() - make_interval(mins => :idle) "
            "  AND EXISTS (SELECT 1 FROM ops.worker_heartbeat h WHERE h.worker_id = j.locked_by AND h.seen_at > now() - make_interval(secs => :hb) "
            # busy_job 키가 없는 심장박동(기동 직후 · 이전 판 워커)은 '모름' — 건드리지 않는다. 키가 있고 다른 값(또는 null)일 때만
            "             AND (h.info -> 'busy_job') IS NOT NULL AND (h.info->>'busy_job') IS DISTINCT FROM CAST(j.id AS text)))) "
            "RETURNING j.id"
        ),
        {"m": older_than_min, "hb": heartbeat_stale_sec, "idle": idle_busy_min, "why": RECOVER_GIVE_UP},
    )
    ids = [r[0] for r in res]
    _close_runs(session, ids, "워커 중단 — 작업을 다시 대기열로 돌림")
    session.commit()
    return len(ids)
