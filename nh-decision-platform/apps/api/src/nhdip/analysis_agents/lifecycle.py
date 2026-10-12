"""분석 에이전트 수명 (Phase C · DAG-03 · DAG-04 · DAG-08) — 요청 · 미리보기 · 승인(생성) · 일시 중지 · 재개 · 폐기.

승인 = 명세로 지표(`dyn_<t>_*`) · 워크플로(`wf_an_<t>`: load_inputs → compute_metrics → [retrieve_evidence] → dynamic_task → render_report → critic → publish)
· 그 분석 전용 에이전트(`an_<t>`, 프롬프트 v{n} = 도메인 지식 + 수행 지시) · 트리거(입력 데이터셋 · 정기 실행)를 만들고 첫 실행 이벤트를 낸다.
새 버전 승인은 같은 코드로 다시 만든다(이전 지표는 끄고 이력 보존). 폐기 = 워크플로 · 트리거 끄기(이력 보존).
"""
from __future__ import annotations

import copy
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from nhdip.analysis_registry import space as get_space
from nhdip.events import audit, emit
from nhdip.models import (
    Agent,
    AnalysisAgent,
    AnalysisAgentVersion,
    LlmProfile,
    Metric,
    Prompt,
    Setting,
    Workflow,
    WorkflowNode,
    WorkflowRun,
    WorkflowTrigger,
    new_id,
    utcnow,
)

from .spec import ids, input_datasets, metric_code, new_token, system_prompt, token_of


class LifecycleError(ValueError):
    pass


def _metric_rows(spec: dict[str, Any], token: str, workflow: str) -> list[dict[str, Any]]:
    from .spec import figure_id

    out = []
    for i, m in enumerate(spec.get("metrics") or []):
        args: dict[str, Any] = {}
        for name, ref in (m.get("args") or {}).items():
            if "metric" in ref:
                args[name] = {"metric": metric_code(token, ref["metric"])}
            else:
                args[name] = copy.deepcopy(ref)
        out.append({
            "code": metric_code(token, m["key"]), "label": m["label"], "formula": m["formula"], "args": args, "workflow_code": workflow, "unit": m.get("unit") or "NONE",
            "decimals": m.get("decimals"), "scale": m.get("scale"), "figure_ids": [figure_id(token, m["key"])], "description": f"분석 에이전트 {token} — {spec.get('title', '')}"[:300], "enabled": True, "sort": 900 + i,
        })
    return out


def _nodes(spec: dict[str, Any], agent: str) -> list[tuple[str, str, str, str | None, dict[str, Any]]]:
    nodes: list[tuple[str, str, str, str | None, dict[str, Any]]] = [
        ("load", "입력 고정", "load_inputs", None, {"datasets": input_datasets(spec)}),
        ("compute", "지표 계산(커널)", "compute_metrics", None, {}),
    ]
    ev = spec.get("evidence")
    if ev:
        nodes.append(("evidence", "근거 검색", "retrieve_evidence", None, {"query": ev["query"], "doc_classes": ev.get("doc_classes") or None, "k": ev.get("k", 4), "optional": True, "respect_plan": False}))
    nodes += [
        ("task", "동적 수행(분석 에이전트)", "dynamic_task", agent, {"agent": agent, "optional": True}),
        ("render", "범용 렌더링", "render_report", "report_renderer", {"agent": agent}),
        ("critic", "서술 검증", "critic", "critic", {"rule": "CRITIC_RULES"}),
        ("publish", "게시", "publish", None, {}),
    ]
    return nodes


def _default_profile(session: Session) -> int | None:
    p = session.execute(select(LlmProfile).where(LlmProfile.is_default)).scalars().first()
    return p.id if p else None


def request(session: Session, *, space: str, text: str, spec: dict[str, Any], validation: dict[str, Any], preview: dict[str, Any] | None, actor: str, agent_code: str | None = None) -> AnalysisAgentVersion:
    """분석 요청 — 새 에이전트(draft → pending) 또는 기존 에이전트의 새 버전(pending)."""
    if not validation.get("ok"):
        raise LifecycleError("검증을 통과하지 못한 명세는 요청할 수 없습니다 — 고친 뒤 다시 정제 · 미리보기 하세요")
    if agent_code:
        a = session.get(AnalysisAgent, agent_code)
        if a is None or a.space != space:
            raise LifecycleError("분석 에이전트 없음")
        if a.status == "retired":
            raise LifecycleError("폐기된 분석은 수정할 수 없습니다 — 새로 만드세요")
        if session.execute(select(AnalysisAgentVersion).where(AnalysisAgentVersion.agent_code == a.code, AnalysisAgentVersion.status == "pending")).first():
            raise LifecycleError("승인 대기 중인 버전이 있습니다")
    else:
        i = ids(new_token())
        a = AnalysisAgent(code=i["agent"], space=space, title=spec["title"], status="pending", version=0, spec={}, workflow_code=None, tab_key=i["tab"], requested_by=actor)
        session.add(a)
        session.flush()
    last = session.execute(select(AnalysisAgentVersion.version).where(AnalysisAgentVersion.agent_code == a.code).order_by(AnalysisAgentVersion.version.desc()).limit(1)).scalar() or 0
    v = AnalysisAgentVersion(agent_code=a.code, version=last + 1, source_text=text[:8000], spec=spec, validation=validation, preview=_preview_summary(preview), status="pending", requested_by=actor)
    session.add(v)
    if a.status in ("draft", "rejected"):
        a.status = "pending"
    a.updated_at = utcnow()
    session.flush()
    audit(session, actor, "analysis_agent.request", "analysis_agent", a.code, {"version": v.version, "space": space, "title": spec["title"], "counts": validation.get("counts")})
    return v


def _preview_summary(pv: dict[str, Any] | None) -> dict[str, Any]:
    if not pv:
        return {}
    doc = pv.get("report") or {}
    return {
        "figures": {k: {"label": f.get("label"), "value": f.get("value"), "unit": f.get("unit"), "stale": f.get("stale")} for k, f in (doc.get("figures") or {}).items()},
        "opinions": [{"id": o.get("id"), "severity": o.get("severity"), "statement": o.get("statement")} for o in doc.get("opinions") or []],
        "sections": len(doc.get("sections") or []),
        "nodes": pv.get("nodes"),
        "at": pv.get("at"),
    }


def apply_options(spec: dict[str, Any], options: dict[str, Any] | None) -> dict[str, Any]:
    """관리자 승인 기준 (DAG-10 · Q108) — 실행 주기(cron) · 자료 변경 때 실행 · LLM 의견 사용을 승인하면서 정한다."""
    from nhdip.workflow.scheduler import is_valid as cron_ok

    if not options:
        return spec
    spec = dict(spec)
    sch = dict(spec.get("schedule") or {"cron": None, "on_data_change": True})
    if "cron" in options:
        cron = (str(options["cron"]).strip() if options["cron"] else "") or None
        if cron and not cron_ok(cron):
            raise LifecycleError(f"정기 실행 cron 식이 올바르지 않습니다: {cron}")
        sch["cron"] = cron
    if options.get("on_data_change") is not None:
        sch["on_data_change"] = bool(options["on_data_change"])
    spec["schedule"] = sch
    if options.get("llm") is not None:
        spec["llm"] = bool(options["llm"])
    if not sch.get("cron") and not sch.get("on_data_change"):
        raise LifecycleError("실행 조건이 없습니다 — 정기 실행(cron) 이나 '자료가 바뀌면 다시 계산' 중 하나는 있어야 합니다")
    return spec


def approve(session: Session, a: AnalysisAgent, v: AnalysisAgentVersion, actor: str, note: str | None = None, options: dict[str, Any] | None = None) -> dict[str, Any]:
    if v.status != "pending":
        raise LifecycleError("승인 대기 상태가 아닙니다")
    sp = get_space(session, a.space)
    if sp is None:
        raise LifecycleError(f"분석 공간이 없습니다: {a.space}")
    spec = apply_options(dict(v.spec), options)
    v.spec = spec  # 승인된 기준을 그 버전 기록에도 남긴다
    token = token_of(a.code)
    i = ids(token)
    wf_code = i["workflow"]
    # 그 분석 전용 에이전트 + 프롬프트(버전마다 새 프롬프트 버전)
    ag = session.get(Agent, a.code)
    if ag is None:
        ag = Agent(code=a.code, name=f"분석 · {spec['title']}"[:100], role=f"동적 수행 — {spec.get('purpose') or spec['title']}"[:300], kind="llm", profile_id=_default_profile(session), override={}, enabled=True)
        session.add(ag)
        session.flush()
    else:
        ag.name, ag.enabled = f"분석 · {spec['title']}"[:100], True
    last_p = session.execute(select(Prompt.version).where(Prompt.agent_code == a.code).order_by(Prompt.version.desc()).limit(1)).scalar() or 0
    session.add(Prompt(agent_code=a.code, version=last_p + 1, system=system_prompt(spec), user_template="", note=f"분석 명세 v{v.version} 승인", created_by=actor))
    ag.prompt_version = last_p + 1
    # 워크플로 · 노드 · 트리거 (다시 만든다)
    wf = session.get(Workflow, wf_code)
    if wf is None:
        wf = Workflow(code=wf_code, name=f"분석 · {spec['title']}"[:150], description=(spec.get("purpose") or spec["title"])[:500], outputs=[i["artifact"]], sort=900, enabled=True)
        session.add(wf)
        session.flush()
    else:
        wf.name, wf.description, wf.outputs, wf.enabled = f"분석 · {spec['title']}"[:150], (spec.get("purpose") or spec["title"])[:500], [i["artifact"]], True
        for n in session.execute(select(WorkflowNode).where(WorkflowNode.workflow_code == wf_code)).scalars():
            session.delete(n)
        for t in session.execute(select(WorkflowTrigger).where(WorkflowTrigger.workflow_code == wf_code)).scalars():
            session.delete(t)
        session.flush()
    for seq, (key, name, impl, agent, cfg) in enumerate(_nodes(spec, a.code), start=1):
        session.add(WorkflowNode(workflow_code=wf_code, seq=seq * 10, key=key, name=name, impl=impl, agent_code=agent, enabled=True, config=cfg))
    sch = spec.get("schedule") or {}
    if sch.get("on_data_change", True):
        for ds in input_datasets(spec):
            session.add(WorkflowTrigger(workflow_code=wf_code, kind="dataset", target=ds, debounce_sec=None, enabled=True))
    if sch.get("cron"):
        session.add(WorkflowTrigger(workflow_code=wf_code, kind="cron", target=sch["cron"], debounce_sec=None, enabled=True))
    # 지표 — 이번 명세에 없는 이전 지표는 끈다(계산 이력 보존)
    rows = _metric_rows(spec, token, wf_code)
    want = {r["code"] for r in rows}
    for m in session.execute(select(Metric).where(Metric.workflow_code == wf_code)).scalars():
        if m.code not in want:
            m.enabled = False
    for r in rows:
        cur = session.get(Metric, r["code"])
        if cur is None:
            session.add(Metric(**r))
        else:
            for k, val in r.items():
                setattr(cur, k, val)
    # 화면에서 '다시 실행' 권한 — 그 공간 열람 리소스 (설정 assist.workflow_resources)
    st = session.get(Setting, "assist.workflow_resources")
    if st is not None and isinstance(st.value, dict):
        st.value = {**st.value, wf_code: sp.get("resource") or "reports"}
    # 상태
    for old in session.execute(select(AnalysisAgentVersion).where(AnalysisAgentVersion.agent_code == a.code, AnalysisAgentVersion.status == "approved")).scalars():
        old.status = "superseded"
    v.status, v.reviewed_by, v.reviewed_at, v.review_note = "approved", actor, utcnow(), note
    a.status, a.version, a.spec, a.title, a.workflow_code = "active", v.version, spec, spec["title"], wf_code
    a.approved_by, a.approved_at, a.updated_at = actor, utcnow(), utcnow()
    session.flush()
    emit(session, "manual", {"workflow": wf_code, "reason": f"분석 에이전트 승인(v{v.version}) 후 첫 실행"}, actor)
    audit(session, actor, "analysis_agent.approve", "analysis_agent", a.code, {"version": v.version, "workflow": wf_code, "metrics": len(rows), "note": note, "schedule": spec.get("schedule"), "llm": spec.get("llm", True)})
    return {"workflow": wf_code, "metrics": len(rows), "agent": a.code, "tab": a.tab_key, "promptVersion": last_p + 1, "schedule": spec.get("schedule"), "llm": spec.get("llm", True)}


def reject(session: Session, a: AnalysisAgent, v: AnalysisAgentVersion, actor: str, note: str) -> None:
    if v.status != "pending":
        raise LifecycleError("승인 대기 상태가 아닙니다")
    v.status, v.reviewed_by, v.reviewed_at, v.review_note = "rejected", actor, utcnow(), note
    if a.status == "pending":
        a.status = "rejected"
    a.updated_at = utcnow()
    audit(session, actor, "analysis_agent.reject", "analysis_agent", a.code, {"version": v.version, "note": note})


def set_state(session: Session, a: AnalysisAgent, action: str, actor: str) -> None:
    """pause · resume · retire — 워크플로 · 트리거를 끄고 켠다(이력 보존)."""
    want = {"pause": "paused", "resume": "active", "retire": "retired"}[action]
    if action == "resume" and a.status != "paused":
        raise LifecycleError("일시 중지된 분석만 재개할 수 있습니다")
    if action == "pause" and a.status != "active":
        raise LifecycleError("동작 중인 분석만 일시 중지할 수 있습니다")
    if action == "retire" and a.status == "retired":
        raise LifecycleError("이미 폐기되었습니다")
    on = want == "active"
    if a.workflow_code:
        wf = session.get(Workflow, a.workflow_code)
        if wf is not None:
            wf.enabled = on
        for t in session.execute(select(WorkflowTrigger).where(WorkflowTrigger.workflow_code == a.workflow_code)).scalars():
            t.enabled = on
    if action == "retire":
        for v in session.execute(select(AnalysisAgentVersion).where(AnalysisAgentVersion.agent_code == a.code, AnalysisAgentVersion.status == "pending")).scalars():
            v.status, v.reviewed_by, v.reviewed_at, v.review_note = "rejected", actor, utcnow(), "분석 폐기"
        ag = session.get(Agent, a.code)
        if ag is not None:
            ag.enabled = False
    a.status, a.updated_at = want, utcnow()
    audit(session, actor, f"analysis_agent.{action}", "analysis_agent", a.code, {"status": want})


def preview(session: Session, spec: dict[str, Any], space: str, actor: str) -> dict[str, Any]:
    """미리보기 (DAG-03) — 임시 워크플로 · 지표로 같은 노드를 한 저장점 안에서 돌리고 보고서를 돌려준 뒤 되돌린다.
    지표 값 · 계산 기록 · 산출물 · 실행 기록이 남지 않는다. 의견 문장은 규칙 기본 문장(LLM 은 승인 후 실행에서)."""
    from nhdip.calc.metrics import EvalContext
    from nhdip.workflow import nodes as _nodes_mod  # noqa: F401 — 노드 등록
    from nhdip.workflow.engine import NODE_IMPLS, RunContext

    sp = get_space(session, space) or {}
    spec = {**spec, "persona": sp.get("persona") or "P2", "domain": sp.get("domain") or space.upper()}
    token = "pv" + new_token()[:6]
    i = ids(token)
    out: dict[str, Any] = {"nodes": [], "at": utcnow().isoformat()}
    sp_tx = session.begin_nested()
    try:
        wf = Workflow(code=i["workflow"], name="미리보기", description="분석 에이전트 미리보기(되돌림)", outputs=[i["artifact"]], sort=999, enabled=False)
        session.add(wf)
        session.flush()
        for r in _metric_rows(spec, token, wf.code):
            session.add(Metric(**r))
        run = WorkflowRun(id=new_id(), workflow_code=wf.code, status="running", causes=[{"type": "preview", "payload": {"actor": actor}}], summary={})
        session.add(run)
        session.flush()
        ctx = RunContext(session=session, run=run, workflow=wf, causes=run.causes, eval=EvalContext(session, workflow_run_id=run.id))
        ctx.state["preview"] = True
        ctx.state["analysis_spec"] = {"spec": spec, "token": token, "version": 0}
        for key, _name, impl, agent, cfg in _nodes(spec, i["agent"]):
            if impl in ("critic", "publish"):
                continue
            node = WorkflowNode(workflow_code=wf.code, seq=0, key=key, name=_name, impl=impl, agent_code=None, enabled=True, config=cfg)
            try:
                res = NODE_IMPLS[impl](ctx, node)
                out["nodes"].append({"key": key, "impl": impl, "status": res.status})
            except Exception as exc:  # noqa: BLE001 — 미리보기는 실패 노드를 보여 준다
                out["nodes"].append({"key": key, "impl": impl, "status": "failed", "error": str(exc)[:300]})
                if not cfg.get("optional"):
                    break
        doc = (ctx.artifacts or {}).get(i["artifact"])
        out["report"] = copy.deepcopy(doc) if doc else None
    finally:
        sp_tx.rollback()
    if out.get("report"):
        # 미리보기 식별자는 결과에서만 보이고 저장되지 않는다
        out["report"]["id"] = "rep-preview"
        out["report"]["generatedAt"] = out["at"]
    return out
