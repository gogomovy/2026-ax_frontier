"""워크플로우 안의 판단 에이전트 노드 (B.30) — 변화 감지 · 실행 계획.

  detect_changes (변화 감지 에이전트, 규칙 기반)
    - 지표: 이번 계산값 vs 직전 확정값을 커널(DIFF · GROWTH_RATE)로 비교, 규칙 CHANGE_SIGNIFICANCE 의
      단위 · 지표별 기준으로 주요(major) · 일반(minor) 판정. 화면에 쓰이지 않는 중간 지표는 제외
    - 데이터: 워크플로우가 읽은 데이터셋 버전이 직전 감지 때와 다르면 데이터 변경(행 수 증감 · 새 파일)
    - 유의 변화는 산출물 change_feed(업무 화면 '최근 감지된 변화')와 이벤트 change.detected 로 내보낸다
  plan_run (플래너 에이전트, 규칙 기반)
    - 원인(수동 · 규칙/설정 변경 · 문서 변경 · 데이터/정기) × 변화 감지 결과 × 서술 이력으로
      서술(LLM) 대상 인사이트와 근거 검색 필요 여부를 정한다. 바뀐 것이 없으면 LLM 을 부르지 않는다
    - 근거 검색 · 서술 노드는 계획을 따른다(노드 설정 respect_plan=false 로 끌 수 있음)
결정과 근거는 ops.agent_decision 에 남는다. 수치는 모두 커널이 계산하고 LLM 은 판단에 쓰지 않는다.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select

from nhdip.calc import execute
from nhdip.calc.metrics import ResolveError, resolve_ref
from nhdip.events import emit
from nhdip.llm import LlmUnavailable, resolve
from nhdip.models import AgentDecision, WorkflowNode
from nhdip.views.store import find_insight

from .engine import NodeResult, RunContext, node_impl
from .nodes import _rule_body, _setting

DETECTOR, PLANNER = "change_detector", "planner"


def record(ctx: RunContext, agent: str, decision: str, summary: str, detail: dict[str, Any]) -> None:
    ctx.session.add(AgentDecision(agent_code=agent, workflow_code=ctx.workflow.code, job_id=ctx.run.job_id, workflow_run_id=ctx.run.id, decision=decision, summary=summary[:500], detail=detail))


def _threshold(pol: dict[str, Any], code: str, unit: str) -> dict[str, Any]:
    units = pol.get("units") or {}
    t = dict(units.get(unit or "") or (units.get("KRW_*") if (unit or "").startswith("KRW") else None) or {})
    t.update((pol.get("metrics") or {}).get(code) or {})
    return t or {"pct": pol.get("default_pct", 1.0)}


def _level(delta: Decimal, pct: Decimal | None, th: dict[str, Any], mult: Decimal) -> tuple[str | None, Decimal]:
    ratios = []
    if th.get("abs"):
        ratios.append(abs(delta) / Decimal(str(th["abs"])))
    if th.get("pct") and pct is not None:
        ratios.append(abs(pct) / Decimal(str(th["pct"])))
    r = max(ratios) if ratios else Decimal(0)
    return ("major" if r >= mult else "minor" if r >= 1 else None), r


def _scope(ctx: RunContext, pol: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for key, ref in ((pol.get("scope") or {}).get(ctx.workflow.code) or {}).items():
        try:
            out[key] = str(resolve_ref(ctx.eval, ref)[0])
        except ResolveError:
            pass
    return out


@node_impl("detect_changes", "변화 감지 에이전트 — 지표 값 · 데이터 버전 변화를 규칙 CHANGE_SIGNIFICANCE 로 판정, 유의 변화만 변화 피드 · 이벤트로")
def n_detect_changes(ctx: RunContext, node: WorkflowNode) -> NodeResult:
    cfg = node.config or {}
    pol = _rule_body(ctx.session, cfg.get("rule", "CHANGE_SIGNIFICANCE"))
    mult = Decimal(str(pol.get("major_multiplier", 5)))
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
        level, ratio = _level(delta, pct, _threshold(pol, code, oc.unit), mult)
        if level is None:
            continue
        items.append({"kind": "metric", "code": code, "label": oc.label, "unit": oc.unit, "decimals": oc.decimals, "before": float(before), "after": float(after),
                      "delta": float(delta), "deltaPct": None if pct is None else round(float(pct), 2), "level": level, "ratio": round(float(ratio), 2),
                      "direction": "up" if delta > 0 else "down", "figureIds": list(oc.figure_ids), "calcId": oc.calc_run_id})
    # 데이터 버전 변화 — 직전 감지 때 본 버전과 비교
    last = ctx.session.execute(select(AgentDecision).where(AgentDecision.agent_code == DETECTOR, AgentDecision.workflow_code == ctx.workflow.code, AgentDecision.decision == "detect").order_by(AgentDecision.id.desc()).limit(1)).scalar()
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
                      "deltaPct": None if pct is None else round(float(pct), 2), "level": "major" if pct is not None and abs(pct) >= row_pct * mult else "minor",
                      "direction": "up" if a > b else "down" if a < b else "same", "files": new_files, "dataOrigin": getattr(vs, "data_origin", None)})
    items.sort(key=lambda x: (x["level"] != "major", -(x.get("ratio") or 0)))
    ctx.state["changes"] = items
    now = datetime.now(ZoneInfo(_setting(ctx.session, "ui.timezone", "Asia/Seoul"))).isoformat(timespec="seconds")
    major = sum(1 for i in items if i["level"] == "major")
    data_n = sum(1 for i in items if i["kind"] == "data")
    if items:
        arts = ctx.load_artifacts()
        feed = arts.get("change_feed") if isinstance(arts.get("change_feed"), dict) else {"items": []}
        entries = [{**i, "id": f"{ctx.run.id[:10]}-{i['kind']}-{i['code']}", "at": now, "workflow": ctx.workflow.code, "workflowName": ctx.workflow.name, "runId": ctx.run.id, **({"scope": scope} if scope else {})} for i in items]
        feed = {"items": (entries + list(feed.get("items") or []))[: int(pol.get("max_feed", 200))], "updatedAt": now}
        arts["change_feed"] = feed
        ctx.changed.add("change_feed")
        emit(ctx.session, "change.detected", {"workflow": ctx.workflow.code, "run": ctx.run.id, "major": major, "total": len(items), "data": data_n, "codes": [i["code"] for i in items[:20]], **({"scope": scope} if scope else {})}, "change_detector")
    summary = f"유의 변화 {len(items)}건(주요 {major} · 데이터 {data_n})" if items else "유의 변화 없음"
    record(ctx, DETECTOR, "detect", summary, {"items": items[:50], "seen": seen, "scope": scope})
    return NodeResult({"summary": summary, "items": items[:50], "datasets": seen})


def _narrator(ctx: RunContext) -> tuple[WorkflowNode | None, WorkflowNode | None]:
    nodes = ctx.session.execute(select(WorkflowNode).where(WorkflowNode.workflow_code == ctx.workflow.code, WorkflowNode.enabled)).scalars().all()
    return next((n for n in nodes if n.impl == "narrate"), None), next((n for n in nodes if n.impl == "retrieve_evidence"), None)


@node_impl("plan_run", "플래너 에이전트 — 원인 · 변화 감지 · 서술 이력으로 서술(LLM) 대상과 근거 검색 필요 여부를 결정 (변화 없으면 LLM 미호출)")
def n_plan_run(ctx: RunContext, node: WorkflowNode) -> NodeResult:
    cfg = node.config or {}
    pol = _rule_body(ctx.session, cfg.get("rule", "PLANNER_POLICY"))
    nar, ev = _narrator(ctx)
    if nar is None:
        ctx.state["plan"] = {"narrate": [], "evidence": False, "skip": {}, "llm": False}
        record(ctx, PLANNER, "plan", "서술 노드 없음", ctx.state["plan"])
        return NodeResult(ctx.state["plan"])
    targets = [t["insight_id"] for t in (nar.config or {}).get("targets", [])]
    types = [str(c.get("type", "")) for c in ctx.causes if isinstance(c, dict)]
    full = [t for t in types if t in set(pol.get("full_refresh_on") or ["manual", "rule.changed", "config.changed"])]
    ev_classes = set((ev.config or {}).get("doc_classes") or []) if ev else set()
    doc_change = [c for c in ctx.causes if isinstance(c, dict) and str(c.get("type", "")).startswith("document.") and (not ev_classes or (c.get("payload") or {}).get("doc_class") in ev_classes)]
    if "schedule" in types and pol.get("refresh_on_schedule"):
        full.append("schedule")
    changes = ctx.state.get("changes") or []
    changed_figs = {f for i in changes if i["kind"] == "metric" for f in i.get("figureIds") or []}
    data_changed = [i["code"] for i in changes if i["kind"] == "data"]
    narrated = set(ctx.session.execute(select(AgentDecision.detail["insight"].astext).where(AgentDecision.agent_code == (nar.agent_code or ""), AgentDecision.decision == "narrated")).scalars())
    arts = ctx.load_artifacts()
    chosen, skip, why = [], {}, {}
    for tid in targets:
        ins = find_insight(arts, tid) or {}
        hit = sorted(set(ins.get("figures") or {}) & changed_figs)
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
            skip[tid] = "수치 · 근거 변화 없음 — 기존 서술 유지"
            continue
        chosen.append(tid)
    mx = int(pol.get("max_targets") or 0)
    if mx and len(chosen) > mx:
        for tid in chosen[mx:]:
            skip[tid] = f"한 번에 최대 {mx}건(규칙 PLANNER_POLICY)"
        chosen = chosen[:mx]
    llm_ok, llm_reason = True, None
    try:
        resolve(ctx.session, nar.agent_code)
    except LlmUnavailable as exc:
        llm_ok, llm_reason = False, str(exc)
    plan = {"narrate": chosen if llm_ok else [], "candidates": chosen, "why": why, "skip": skip, "evidence": bool(chosen) and llm_ok and ev is not None,
            "llm": llm_ok, "llmReason": llm_reason, "causes": sorted(set(types)), "changedFigures": sorted(changed_figs)[:30], "dataChanged": data_changed}
    ctx.state["plan"] = plan
    if not chosen:
        summary = f"변화 없음 — 서술 {len(skip)}건 유지, LLM · 근거 검색 생략"
    elif not llm_ok:
        summary = f"LLM 미연결 — 서술 대상 {len(chosen)}건은 기존 문장 유지, 근거 검색 생략"
    else:
        summary = f"서술 {len(chosen)}건 · 유지 {len(skip)}건 · 근거 검색 {'실행' if plan['evidence'] else '생략'}"
    record(ctx, PLANNER, "plan", summary, plan)
    return NodeResult({"summary": summary, **plan})
