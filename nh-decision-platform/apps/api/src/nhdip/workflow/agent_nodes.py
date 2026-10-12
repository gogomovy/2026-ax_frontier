"""워크플로우 안의 판단 에이전트 노드 (B.30 · B.31) — 변화 감지 · 실행 계획. LLM 이 판단하고 규칙이 안전장치 · 대체 경로.

  detect_changes (변화 감지 에이전트 `change_detector`)
    1) 커널이 지표 직전값 대비 변화(DIFF · GROWTH_RATE)와 데이터 버전 변화를 계산하고, 규칙 CHANGE_SIGNIFICANCE 의
       기준 배수로 후보(candidate_factor 이상)와 규칙 등급(주요 · 일반)을 붙인다
    2) LLM 이 후보마다 업무상 중요도(major · minor · ignore)와 사유를 판단한다 — 숫자를 새로 만들지 않고, 사유에 숫자를 쓰면 버린다
       규칙상 주요 변화는 LLM 이 '무시' 로 내릴 수 없다(protect_major)
    3) LLM 미연결 · 실패면 규칙 등급을 그대로 쓴다. 최종 유의 변화만 change_feed · change.detected 로
  plan_run (플래너 에이전트 `planner`)
    1) 규칙 계획(원인 × 변화 × 서술 이력)을 기준안으로 만든다
    2) LLM 이 원인 · 판단된 변화 · 인사이트 · 서술 이력 · 후속 후보를 보고 서술 대상 · 근거 검색(추가 검색어) · 후속 워크플로우를 정한다
    3) 허용 목록으로 검증(대상 인사이트 · 사용 중 워크플로우 · 연쇄 깊이 · 건수 상한), 수동 실행 대상은 항상 포함
    4) LLM 미연결 · 실패면 규칙 계획. 후속 워크플로우는 게시 후 이벤트 agent.followup 으로 실행된다
결정 · 근거 · 판단 주체(llm/rule) · LLM 호출 ID 는 ops.agent_decision 에 남는다.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select

from nhdip.calc import execute
from nhdip.calc.metrics import ResolveError, resolve_ref
from nhdip.llm import LlmUnavailable, resolve
from nhdip.models import AgentDecision, Workflow, WorkflowNode, WorkflowRun
from nhdip.views.store import find_insight

from .engine import NodeResult, RunContext, node_impl
from .llm_judge import ask_json, clean_reason
from .nodes import _rule_body, _setting

DETECTOR, PLANNER = "change_detector", "planner"
LEVELS = ("major", "minor", "ignore")


def record(ctx: RunContext, agent: str, decision: str, summary: str, detail: dict[str, Any]) -> None:
    ctx.session.add(AgentDecision(agent_code=agent, workflow_code=ctx.workflow.code, job_id=ctx.run.job_id, workflow_run_id=ctx.run.id, decision=decision, summary=summary[:500], detail=detail))


def run_chain(ctx: RunContext) -> list[str]:
    """이 실행을 일으킨 워크플로우 연쇄(후속 · 경로 지정) — 순환 · 과도한 연쇄 방지에 쓴다."""
    out: list[str] = []
    for c in ctx.causes:
        p = (c.get("payload") or {}) if isinstance(c, dict) else {}
        for w in [*(p.get("chain") or []), *([p["from"]] if p.get("from") else [])]:
            if w not in out:
                out.append(w)
    return out


def _threshold(pol: dict[str, Any], code: str, unit: str) -> dict[str, Any]:
    units = pol.get("units") or {}
    t = dict(units.get(unit or "") or (units.get("KRW_*") if (unit or "").startswith("KRW") else None) or {})
    t.update((pol.get("metrics") or {}).get(code) or {})
    return t or {"pct": pol.get("default_pct", 1.0)}


def _ratio(delta: Decimal, pct: Decimal | None, th: dict[str, Any]) -> Decimal:
    ratios = []
    if th.get("abs"):
        ratios.append(abs(delta) / Decimal(str(th["abs"])))
    if th.get("pct") and pct is not None:
        ratios.append(abs(pct) / Decimal(str(th["pct"])))
    return max(ratios) if ratios else Decimal(0)


def _rule_level(r: Decimal, mult: Decimal) -> str | None:
    return "major" if r >= mult else "minor" if r >= 1 else None


def _scope(ctx: RunContext, pol: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for key, ref in ((pol.get("scope") or {}).get(ctx.workflow.code) or {}).items():
        try:
            out[key] = str(resolve_ref(ctx.eval, ref)[0])
        except ResolveError:
            pass
    return out


DETECT_TASK = (
    "아래는 계산 커널이 확정한 지표 · 데이터 변화 후보다(직전 확정값 대비). 각 후보의 업무상 중요도를 판단하라.\n"
    "- level: major(경영 · 리스크 판단에 바로 영향) · minor(관찰 필요) · ignore(업무상 의미 없음)\n"
    "- ruleLevel 이 major 인 후보는 ignore 로 내리지 않는다. 같은 원인으로 움직인 변화는 group 에 같은 이름을 준다.\n"
    "- reason 은 숫자 없이 한 문장. 수치를 새로 만들거나 계산하지 않는다.\n"
    '출력: {"changes": [{"code": "...", "level": "major|minor|ignore", "reason": "...", "group": "..."}], "summary": "숫자 없는 한 문장"}'
)


@node_impl("detect_changes", "변화 감지 에이전트 — 커널이 변화를 계산하고 LLM 이 업무상 중요도를 판단(규칙 CHANGE_SIGNIFICANCE 가 후보 · 안전장치 · 대체), 유의 변화만 변화 피드 · 이벤트로")
def n_detect_changes(ctx: RunContext, node: WorkflowNode) -> NodeResult:
    cfg = node.config or {}
    pol = _rule_body(ctx.session, cfg.get("rule", "CHANGE_SIGNIFICANCE"))
    mult = Decimal(str(pol.get("major_multiplier", 5)))
    cand_bar = Decimal(str(pol.get("candidate_factor", 0.5)))
    ignore = set(pol.get("ignore") or [])
    scope = _scope(ctx, pol)
    items: list[dict[str, Any]] = []
    for code, oc in ctx.eval.outcomes.items():
        if oc.error or oc.display is None or oc.previous is None or code in ignore or not oc.figure_ids:
            continue
        before, after = Decimal(str(oc.previous)), Decimal(str(oc.display))
        if before == after:
            continue
        delta = execute("DIFF", {"a": after, "b": before}).value
        pct = execute("GROWTH_RATE", {"v0": before, "v1": after}).value if before != 0 else None
        ratio = _ratio(delta, pct, _threshold(pol, code, oc.unit))
        if ratio < cand_bar:
            continue
        items.append({"kind": "metric", "code": code, "label": oc.label, "unit": oc.unit, "decimals": oc.decimals, "before": float(before), "after": float(after),
                      "delta": float(delta), "deltaPct": None if pct is None else round(float(pct), 2), "ruleLevel": _rule_level(ratio, mult), "ratio": round(float(ratio), 2),
                      "direction": "up" if delta > 0 else "down", "figureIds": list(oc.figure_ids), "calcId": oc.calc_run_id})
    # 데이터 버전 변화 — 직전 감지 때 본 버전과 비교
    # 직전 '성공한' 실행의 감지 기록만 — 실패한 실행이 본 버전을 기준으로 삼으면 그 변화를 놓친다 (B.32)
    last = ctx.session.execute(
        select(AgentDecision)
        .join(WorkflowRun, WorkflowRun.id == AgentDecision.workflow_run_id)
        .where(AgentDecision.agent_code == DETECTOR, AgentDecision.workflow_code == ctx.workflow.code, AgentDecision.decision == "detect", WorkflowRun.status.in_(["succeeded", "degraded"]))
        .order_by(AgentDecision.id.desc())
        .limit(1)
    ).scalar()
    seen_before = (last.detail or {}).get("seen", {}) if last else {}
    seen: dict[str, Any] = {}
    row_pct = Decimal(str((pol.get("data") or {}).get("row_change_pct", 1.0)))
    for code, (vs, rows, ds) in ctx.eval.rows.items():
        ids = sorted(v.id for v in getattr(vs, "versions", []) or [vs])
        seen[code] = {"versions": ids, "rows": len(rows)}
        prev = seen_before.get(code)
        if not prev or prev.get("versions") == ids:
            continue
        b, a = Decimal(prev.get("rows") or 0), Decimal(len(rows))
        pct = execute("GROWTH_RATE", {"v0": b, "v1": a}).value if b else None
        new_files = sorted({v.file_name for v in getattr(vs, "versions", []) if v.id not in set(prev.get("versions") or []) and v.file_name})
        items.append({"kind": "data", "code": code, "label": ds.name, "unit": "CNT", "decimals": 0, "before": float(b), "after": float(a), "delta": float(a - b),
                      "deltaPct": None if pct is None else round(float(pct), 2), "ruleLevel": "major" if pct is not None and abs(pct) >= row_pct * mult else "minor",
                      "direction": "up" if a > b else "down" if a < b else "same", "files": new_files, "dataOrigin": getattr(vs, "data_origin", None)})
    # LLM 판단 (후보가 있을 때만)
    judged_by, meta, llm_summary = "rule", {"by": "rule", "reason": "후보 없음"}, None
    if items:
        # 후보가 많으면(예: 영업점 50여 개) 규칙상 주요 · 변화율 큰 순으로 상한(규칙 CHANGE_SIGNIFICANCE.llm_max_candidates)만 LLM 에 묻고, 나머지는 규칙 판단 (B.40)
        cap = int(pol.get("llm_max_candidates", 25) or 0)
        ranked = sorted(items, key=lambda i: (i.get("ruleLevel") != "major", -abs(float(i.get("deltaPct") or 0))))
        ask_items = ranked[:cap] if cap else ranked
        context = {"workflow": {"code": ctx.workflow.code, "name": ctx.workflow.name, "description": ctx.workflow.description}, "guidance": pol.get("llm_guidance"),
                   "candidates": [{k: i.get(k) for k in ("kind", "code", "label", "unit", "before", "after", "delta", "deltaPct", "direction", "ruleLevel", "files")} for i in ask_items]}
        data, meta = ask_json(ctx.session, node.agent_code or DETECTOR, DETECT_TASK, context, workflow_run_id=ctx.run.id, node_run_id=ctx.node_run_id, required=("changes",), shrink=("candidates",))
        # 입력 글자 상한으로 뒤쪽 후보를 덜어 냈으면(B.43) 실제로 보낸 후보만 LLM 판단을 받는다 — 나머지는 규칙
        sent = ask_items[: len(ask_items) - int((meta.get("contextTrimmed") or {}).get("candidates", 0))]
        if len(sent) < len(items):
            meta = {**meta, "llmCandidates": len(sent), "ruleOnly": len(items) - len(sent)}
        by_code = {}
        if data:
            sent_codes = {i["code"] for i in sent}
            for d in data.get("changes") or []:
                if isinstance(d, dict) and d.get("code") in sent_codes and d.get("level") in LEVELS:
                    by_code[d["code"]] = d
            judged_by = "llm" if by_code else "rule"
            llm_summary, _ = clean_reason(data.get("summary"))
        for i in items:
            d = by_code.get(i["code"])
            if d:
                lvl = d["level"]
                if lvl == "ignore" and i["ruleLevel"] == "major" and pol.get("protect_major", True):
                    lvl = "minor"
                reason, dropped = clean_reason(d.get("reason"))
                i.update({"level": None if lvl == "ignore" else lvl, "judgedBy": "llm", "reason": reason or None, "group": str(d.get("group") or "")[:40] or None, **({"reasonDropped": True} if dropped else {})})
            else:
                i.update({"level": i["ruleLevel"], "judgedBy": "rule"})
    final = [i for i in items if i.get("level")]
    final.sort(key=lambda x: (x["level"] != "major", -(x.get("ratio") or 0)))
    ctx.state["changes"] = final
    chain = run_chain(ctx)
    now = datetime.now(ZoneInfo(_setting(ctx.session, "ui.timezone", "Asia/Seoul"))).isoformat(timespec="seconds")
    major = sum(1 for i in final if i["level"] == "major")
    data_n = sum(1 for i in final if i["kind"] == "data")
    if final:
        arts = ctx.load_artifacts()
        feed = arts.get("change_feed") if isinstance(arts.get("change_feed"), dict) else {"items": []}
        entries = [{**i, "id": f"{ctx.run.id[:10]}-{i['kind']}-{i['code']}", "at": now, "workflow": ctx.workflow.code, "workflowName": ctx.workflow.name, "runId": ctx.run.id, **({"scope": scope} if scope else {})} for i in final]
        arts["change_feed"] = {"items": (entries + list(feed.get("items") or []))[: int(pol.get("max_feed", 200))], "updatedAt": now}
        ctx.changed.add("change_feed")
        ctx.emit_after_success("change.detected", {"workflow": ctx.workflow.code, "run": ctx.run.id, "major": major, "total": len(final), "data": data_n, "chain": [*chain, ctx.workflow.code],
                                              "changes": [{k: i.get(k) for k in ("code", "label", "level", "direction", "reason", "kind")} for i in final[:15]], **({"scope": scope} if scope else {})}, DETECTOR)
    summary = (f"유의 변화 {len(final)}건(주요 {major} · 데이터 {data_n}) · 후보 {len(items)}건 · 판단 {'LLM' if judged_by == 'llm' else '규칙'}" if final else (f"후보 {len(items)}건 모두 유의하지 않음 · 판단 {'LLM' if judged_by == 'llm' else '규칙'}" if items else "유의 변화 없음"))
    detail = {"by": judged_by, "meta": meta, "llmSummary": llm_summary, "items": final[:50], "candidates": items[:80], "seen": seen, "scope": scope}
    record(ctx, node.agent_code or DETECTOR, "detect", summary, detail)
    return NodeResult({"summary": summary, "by": judged_by, "meta": meta, "items": final[:50], "candidates": len(items), "datasets": seen})


def _nodes(ctx: RunContext) -> tuple[WorkflowNode | None, WorkflowNode | None]:
    nodes = ctx.session.execute(select(WorkflowNode).where(WorkflowNode.workflow_code == ctx.workflow.code, WorkflowNode.enabled)).scalars().all()
    return next((n for n in nodes if n.impl == "narrate"), None), next((n for n in nodes if n.impl == "retrieve_evidence"), None)


def _clean_query(q: Any) -> str:
    s = " ".join(str(q or "").split())[:120]
    return "".join(ch for ch in s if ch not in "{}<>[]")


PLAN_TASK = (
    "너는 이번 워크플로우 실행의 계획 에이전트다. 원인 · 판단된 변화 · 인사이트(의견) · 서술 이력을 보고 다음을 결정하라.\n"
    "1) narrate: 이번에 LLM 서술을 다시 써야 할 인사이트(id 는 insights 에 있는 것만). 바뀐 수치 · 근거와 관련 없는 의견은 기존 서술을 유지한다.\n"
    "2) evidence: 근거 검색을 할지(run)와 이번 변화에 맞춘 추가 검색어(query, 선택 · 짧게).\n"
    "3) followups: 이번 변화가 다른 업무 판단에 영향을 주면 후속 실행할 워크플로우(followupCandidates 의 code 만, 필요할 때만).\n"
    "forced 에 있는 인사이트는 반드시 포함된다. 수치를 계산하거나 새로 만들지 않는다. reason · summary 는 숫자 없이.\n"
    '출력: {"narrate": [{"insight": "...", "reason": "..."}], "evidence": {"run": true, "query": "..."}, "followups": [{"workflow": "...", "reason": "..."}], "summary": "..."}'
)


@node_impl("plan_run", "플래너 에이전트 — LLM 이 원인 · 변화 · 서술 이력으로 서술 대상 · 근거 검색어 · 후속 워크플로우를 결정(허용 목록 검증, 실패 시 규칙 계획)")
def n_plan_run(ctx: RunContext, node: WorkflowNode) -> NodeResult:
    cfg = node.config or {}
    pol = _rule_body(ctx.session, cfg.get("rule", "PLANNER_POLICY"))
    nar, ev = _nodes(ctx)
    chain = run_chain(ctx)
    if nar is None:
        ctx.state["plan"] = {"narrate": [], "candidates": [], "evidence": False, "skip": {}, "llm": False, "by": "rule"}
        record(ctx, node.agent_code or PLANNER, "plan", "서술 노드 없음", ctx.state["plan"])
        return NodeResult(ctx.state["plan"])
    targets_cfg = (nar.config or {}).get("targets", [])
    targets = [t["insight_id"] for t in targets_cfg]
    types = [str(c.get("type", "")) for c in ctx.causes if isinstance(c, dict)]
    full = [t for t in types if t in set(pol.get("full_refresh_on") or ["manual", "rule.changed", "config.changed"])]
    forced_types = [t for t in types if t in set(pol.get("force_on") or ["manual"])]
    ev_classes = set((ev.config or {}).get("doc_classes") or []) if ev else set()
    doc_change = [c for c in ctx.causes if isinstance(c, dict) and str(c.get("type", "")).startswith("document.") and (not ev_classes or (c.get("payload") or {}).get("doc_class") in ev_classes)]
    if "schedule" in types and pol.get("refresh_on_schedule"):
        full.append("schedule")
    changes = ctx.state.get("changes") or []
    changed_figs = {f for i in changes if i["kind"] == "metric" for f in i.get("figureIds") or []}
    data_changed = [i["code"] for i in changes if i["kind"] == "data"]
    narrated = set(ctx.session.execute(select(AgentDecision.detail["insight"].astext).where(AgentDecision.agent_code == (nar.agent_code or ""), AgentDecision.decision == "narrated")).scalars())
    arts = ctx.load_artifacts()
    # 1) 규칙 계획(기준안 · 대체 경로)
    rule_choice, rule_skip, why, info = [], {}, {}, []
    for t in targets_cfg:
        tid = t["insight_id"]
        ins = find_insight(arts, tid) or {}
        hit = sorted(set(ins.get("figures") or {}) & changed_figs)
        info.append({"id": tid, "title": ins.get("title"), "severity": ins.get("severity"), "figures": [f.get("label") for f in (ins.get("figures") or {}).values()][:12],
                     "changedFigures": hit, "narratedBefore": tid in narrated, "instruction": t.get("instruction")})
        if full:
            why[tid] = f"전체 갱신({', '.join(sorted(set(full)))})"
        elif doc_change:
            why[tid] = f"근거 문서 변경 {len(doc_change)}건"
        elif hit:
            why[tid] = f"수치 변화: {', '.join(hit[:5])}"
        elif data_changed and pol.get("narrate_on_data_change", True) and not ins.get("figures"):
            why[tid] = f"데이터 변경: {', '.join(data_changed[:3])}"
        elif tid not in narrated:
            why[tid] = "LLM 서술 이력 없음 — 최초 1회"
        else:
            rule_skip[tid] = "수치 · 근거 변화 없음 — 기존 서술 유지"
            continue
        rule_choice.append(tid)
    forced = list(targets) if forced_types else []
    # 2) 후속 후보 — 사용 중 · 자기 자신 아님 · 연쇄에 없음 · 깊이 이내
    from .orchestrator import policy as orch_policy

    # 연쇄 깊이는 오케스트레이터 정책이 상한 (디스패처가 같은 값으로 강제) — B.32
    max_chain = min(int(pol.get("max_chain", 3)), int(orch_policy(ctx.session).get("max_chain", 3)))
    allow_follow = len(chain) + 1 < max_chain
    wfs = ctx.session.execute(select(Workflow).where(Workflow.enabled)).scalars().all()
    follow_cands = [{"code": w.code, "name": w.name, "description": w.description} for w in wfs if allow_follow and w.code != ctx.workflow.code and w.code not in chain and w.code not in set(pol.get("followup_exclude") or ["wf_graph_projection"])]
    # 3) LLM 계획
    context = {"workflow": {"code": ctx.workflow.code, "name": ctx.workflow.name, "description": ctx.workflow.description},
               "causes": [{"type": c.get("type"), "reasons": c.get("reasons"), "payload": {k: v for k, v in (c.get("payload") or {}).items() if k in ("dataset", "doc_class", "workflow", "reason", "rule", "key", "from", "major")}} for c in ctx.causes if isinstance(c, dict)][:20],
               "changes": [{k: i.get(k) for k in ("kind", "code", "label", "level", "direction", "reason", "group")} for i in changes][:40],
               "insights": info, "forced": forced, "ruleSuggestion": {"narrate": rule_choice, "skip": rule_skip},
               "evidence": {"available": ev is not None, "baseQuery": (ev.config or {}).get("query") if ev else None}, "followupCandidates": follow_cands, "chain": chain,
               "limits": {"max_targets": int(pol.get("max_targets") or 0), "max_followups": int(pol.get("max_followups", 2))}, "guidance": pol.get("llm_guidance")}
    data, meta = ask_json(ctx.session, node.agent_code or PLANNER, PLAN_TASK, context, workflow_run_id=ctx.run.id, node_run_id=ctx.node_run_id, required=("narrate",))
    by = "rule"
    chosen, skip, followups, ev_query = list(rule_choice), dict(rule_skip), [], ""
    run_evidence = None
    llm_summary = None
    if data:
        by = "llm"
        picks = []
        for d in data.get("narrate") or []:
            tid = d.get("insight") if isinstance(d, dict) else d
            if tid in targets and tid not in picks:
                picks.append(tid)
                reason, _ = clean_reason(d.get("reason") if isinstance(d, dict) else "")
                why[tid] = f"LLM: {reason}" if reason else why.get(tid) or "LLM 판단"
        chosen = [t for t in targets if t in set(forced) | set(picks)]
        skip = {t: ("LLM: 변화와 관련 없음 — 기존 서술 유지") for t in targets if t not in chosen}
        evd = data.get("evidence") if isinstance(data.get("evidence"), dict) else {}
        run_evidence = bool(evd.get("run", True))
        ev_query = _clean_query(evd.get("query"))
        allowed = {f["code"] for f in follow_cands}
        for f in data.get("followups") or []:
            if isinstance(f, dict) and f.get("workflow") in allowed and f["workflow"] not in {x["workflow"] for x in followups}:
                reason, _ = clean_reason(f.get("reason"))
                followups.append({"workflow": f["workflow"], "reason": reason or "LLM 판단"})
        followups = followups[: int(pol.get("max_followups", 2))]
        llm_summary, _ = clean_reason(data.get("summary"))
    else:
        for t in forced:
            if t not in chosen:
                chosen.append(t)
    mx = int(pol.get("max_targets") or 0)
    if mx and len(chosen) > mx:
        keep = [t for t in chosen if t in forced] + [t for t in chosen if t not in forced]
        for tid in keep[mx:]:
            skip[tid] = f"한 번에 최대 {mx}건(규칙 PLANNER_POLICY)"
        chosen = keep[:mx]
    llm_ok, llm_reason = True, None
    try:
        resolve(ctx.session, nar.agent_code)
    except LlmUnavailable as exc:
        llm_ok, llm_reason = False, str(exc)
    evidence = bool(chosen) and llm_ok and ev is not None and (run_evidence if run_evidence is not None else True)
    plan = {"by": by, "meta": meta, "narrate": chosen if llm_ok else [], "candidates": chosen, "why": {k: v for k, v in why.items() if k in chosen}, "skip": skip, "evidence": evidence,
            "evidenceQuery": ev_query, "followups": followups, "llm": llm_ok, "llmReason": llm_reason, "causes": sorted(set(types)), "changedFigures": sorted(changed_figs)[:30],
            "dataChanged": data_changed, "chain": chain, "llmSummary": llm_summary, "ruleSuggestion": {"narrate": rule_choice}}
    ctx.state["plan"] = plan
    ctx.state["followups"] = [{**f, "chain": [*chain, ctx.workflow.code]} for f in followups]
    who = "LLM" if by == "llm" else "규칙"
    if not chosen:
        summary = f"[{who}] 변화 없음 — 서술 {len(skip)}건 유지, LLM 서술 · 근거 검색 생략"
    elif not llm_ok:
        summary = f"[{who}] 서술 대상 {len(chosen)}건 — 서술 LLM 미연결로 기존 문장 유지, 근거 검색 생략"
    else:
        summary = f"[{who}] 서술 {len(chosen)}건 · 유지 {len(skip)}건 · 근거 검색 {'실행' if evidence else '생략'}"
    if followups:
        summary += f" · 후속 {', '.join(f['workflow'] for f in followups)}"
    record(ctx, node.agent_code or PLANNER, "plan", summary, plan)
    return NodeResult({"summary": summary, **plan})
