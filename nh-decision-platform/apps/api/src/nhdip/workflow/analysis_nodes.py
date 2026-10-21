"""분석 에이전트 노드 (Phase C · DAG-05 · DAG-06 · Q100 · Q103).

- `dynamic_task` ② 동적 수행 — 명세의 도메인 지식 · 수행 지시를 프롬프트로 가진 그 분석 전용 에이전트(`an_*`)가
  커널 확정 수치(그림 ID) · 집계표 · 근거 · 규칙 판정을 받아 의견 대상마다 판단(심각도) · 서술(마커만)한다.
  서술은 `ctx.state.narratives` 로 넘겨 critic 이 검증 · 반영한다. LLM 미연결 · 실패 · 미리보기면 규칙 판정 + 기존 문장.
- `render_report` ③ 범용 렌더링 — 명세 구성대로 `report.an-<t>` 산출물 조립(결정론, LLM 없음).
명세는 노드 설정 `agent`(분석 에이전트 코드)로 cfg.analysis_agent 에서 읽는다(미리보기는 ctx.state.analysis_spec).
"""
from __future__ import annotations

from typing import Any

from nhdip.analysis_agents import render as R
from nhdip.analysis_agents.spec import SEVERITIES, figure_id, insight_id, token_of
from nhdip.analysis_registry import space as get_space
from nhdip.models import AnalysisAgent, WorkflowNode

from .engine import NodeResult, RunContext, node_impl


def _load(ctx: RunContext, node: WorkflowNode) -> tuple[dict[str, Any], str, int]:
    pv = ctx.state.get("analysis_spec")
    if pv is not None:
        return pv["spec"], pv["token"], int(pv.get("version") or 0)
    code = (node.config or {}).get("agent") or ""
    a = ctx.session.get(AnalysisAgent, code)
    if a is None or not a.spec:
        raise RuntimeError(f"분석 에이전트 명세 없음: {code}")
    spec = dict(a.spec)
    sp = get_space(ctx.session, a.space) or {}
    spec.setdefault("persona", sp.get("persona") or "P2")
    spec.setdefault("domain", sp.get("domain") or a.space.upper())
    return spec, token_of(a.code), int(a.version or 0)


def _prepare(ctx: RunContext, node: WorkflowNode) -> dict[str, Any]:
    an = ctx.state.get("an")
    if an is not None:
        return an
    spec, token, version = _load(ctx, node)
    figs = R.figures(spec, token, ctx.eval.outcomes)
    an = {"spec": spec, "token": token, "version": version, "figures": figs, "tables": R.tables(ctx.eval, spec), "verdicts": R.verdicts(spec, token, figs), "findings": {}}
    ctx.state["an"] = an
    return an


@node_impl("team_context", "팀 데이터 — 요청 팀의 정형 자료(PostgreSQL) · 상위 부서 KPI · 온톨로지 관계(Neo4j)를 실행마다 다시 찾아 근거 검색 · 서술 · 보고서에 넘긴다(결정론)")
def n_team_context(ctx: RunContext, node: WorkflowNode) -> NodeResult:
    from nhdip.analysis_agents.spec import input_datasets
    from nhdip.analysis_agents.team import build_context, team_of_agent, team_of_user

    spec, _token, _v = _load(ctx, node)
    cfg = node.config or {}
    actor = ctx.state.get("team_actor")
    org = ctx.state.get("team_org")
    if org:
        from nhdip.analysis_agents.team import team_of

        team = team_of(ctx.session, str(org))  # 에이전트 제안 분석의 미리보기 — 자료 소유 조직의 팀 (§40 STW)
    else:
        team = team_of_user(ctx.session, actor) if actor else team_of_agent(ctx.session, cfg.get("agent"))
    tc = build_context(ctx.session, spec, team, inputs=input_datasets(spec), own_workflow=ctx.workflow.code, use_graph=cfg.get("graph", True))
    ctx.state["team_context"] = tc
    ctx.state["context_concepts"] = tc.get("concepts") or []
    ctx.state["team_orgs"] = sorted(team.orgs)
    g = tc.get("graph") or {}
    return NodeResult({"team": tc["team"], "datasets": [{k: d[k] for k in ("code", "scope", "use", "periodText")} for d in tc["datasets"]], "kpis": [k["code"] for k in tc["kpis"]],
                       "graph": {"available": g.get("available"), "reason": g.get("reason"), "relations": len(g.get("relations") or []), "concepts": tc.get("concepts")}})


@node_impl("dynamic_task", "분석 에이전트 동적 수행 — 명세의 도메인 지식 · 수행 지시로 확정 수치 · 집계표 · 근거를 판단 · 서술(수치는 마커만, 실패 시 규칙 판정 · 기존 문장)")
def n_dynamic_task(ctx: RunContext, node: WorkflowNode) -> NodeResult:
    from .llm_judge import ask_json

    an = _prepare(ctx, node)
    spec, token, figs = an["spec"], an["token"], an["figures"]
    rule_out = {"verdicts": an["verdicts"], "figures": {k: v.get("value") for k, v in figs.items()}}
    if ctx.state.get("preview"):
        return NodeResult({"skipped": "미리보기 — 의견 문장은 승인 후 실행에서 분석 에이전트가 작성(규칙 판정만)", **rule_out})
    if spec.get("llm") is False:
        # 관리자 승인 기준(Q108) — 이 분석은 LLM 의견을 쓰지 않는다(규칙 판정 · 기본 문장, 의도한 생략이라 축소 아님)
        return NodeResult({"skipped": "관리자 승인 기준 — LLM 의견 사용 안 함(규칙 판정 · 기본 문장)", **rule_out})
    if ctx.llm_off:
        return NodeResult({"skipped": ctx.llm_off, **rule_out})
    if not node.agent_code:
        return NodeResult({"skipped": "담당 에이전트 없음 — 규칙 판정 · 기존 문장", **rule_out}, "degraded")
    ev = (ctx.state.get("evidence") or [])[:4]
    from nhdip.views.period_words import PERIOD_GUIDE, figure_note, figures_span

    span = figures_span(figs)
    notes = {fid: figure_note(f, span) for fid, f in figs.items()}
    context = {
        "title": spec["title"],
        # 비교 기준(basis) — 전년 동기 자료가 없어 다른 기준일과 견준 수치 · 비교 기간에 맞춘 목표(PER-05)
        "figures": [{"id": fid, "label": f["label"], "value": f.get("value"), "unit": f.get("unit"), "stale": bool(f.get("stale")), **({"basis": notes[fid]} if notes[fid] else {})}
                    for fid, f in figs.items()],
        "verdicts": an["verdicts"],
        "tables": [{"key": k, "caption": next((t["caption"] for t in spec.get("tables") or [] if t["key"] == k), k), "rows": [[g, float(v)] for g, v in tv["rows"][:10]], "note": tv.get("note")} for k, tv in an["tables"].items()],
        "insights": [{"key": i["key"], "title": i["title"], "figures": [figure_id(token, m) for m in i.get("metrics") or []], "instruction": i.get("instruction") or ""} for i in spec.get("insights") or []],
        "evidence": [{"title": e.get("title"), "page": e.get("page"), "text": str(e.get("text") or "")[:300]} for e in ev],
    }
    if ctx.state.get("team_context"):
        # 팀 데이터(TDB-06) — 팀 자료 · 보관 기간 · 상위 부서 KPI 방향 · 온톨로지 관계 (숫자 값 없음)
        from nhdip.analysis_agents.team import llm_summary

        context["teamData"] = llm_summary(ctx.state["team_context"])
    from .nodes import _rule_body

    # 검증(critic)이 막는 표현을 미리 알려 준다 — 실 LLM 시험에서 '원인은 …' 같은 문장이 막혀 기본 문장으로 남았다
    banned = [str(p) for p in (_rule_body(ctx.session, "CRITIC_RULES").get("causal_phrases") or [])][:30]
    task = (
        "insights 의 의견 대상마다 확정 수치(figures) · 판정(verdicts) · 집계표(tables) · 근거(evidence)로 판단하고 의견 문장을 써라.\n"
        "teamData 는 요청 팀이 올린 자료 · 공통 통합 DB · 상위 부서 KPI 의 방향 · 온톨로지 관계다 — 관련 있으면 맥락으로 말로만 언급한다(값은 쓰지 않는다).\n"
        "출력: {\"findings\": [{\"insight\": 의견 key, \"severity\": \"info\"|\"watch\"|\"caution\"|\"critical\", \"statement\": \"2~4문장\"}], \"summary\": \"한 문장\"}\n"
        "규칙: 숫자를 직접 쓰지 말고 수치는 그 의견의 figures 에 있는 [[fig:ID]] 마커로만 참조한다(마커 뒤에 단위를 붙이지 않는다). 집계표 값은 '상위 항목' 처럼 말로만 언급한다. 인과를 단정하지 않는다."
        + (f"\n다음 표현은 쓰지 않는다(검증에서 막힌다): {', '.join(banned)}" if banned else "")
        + (f"\n{PERIOD_GUIDE} figures 의 basis 가 그 수치의 실제 비교 기준이다." if any(notes.values()) else "")
    )
    data, meta = ask_json(ctx.session, node.agent_code, task, context, workflow_run_id=ctx.run.id, node_run_id=ctx.node_run_id, required=("findings",), shrink=("tables", "evidence"))
    if data is None:
        return NodeResult({"fallback": "rule", "reason": meta.get("reason"), **rule_out}, "degraded")
    keys = {i["key"]: i for i in spec.get("insights") or []}
    allowed = list(figs)
    results = []
    for f in data.get("findings") or []:
        if not isinstance(f, dict) or not isinstance(f.get("insight"), str) or f["insight"] not in keys:
            continue
        key = f["insight"]
        sev = f.get("severity") if f.get("severity") in SEVERITIES else None
        an["findings"][key] = {"severity": sev}
        st = str(f.get("statement") or "").strip()[:1200]
        if st:
            ctx.state.setdefault("narratives", {})[insight_id(token, key)] = {"statement": st, "llm_call_id": meta.get("llm_call_id"), "figures": allowed, "agent": node.agent_code}
        results.append({"insight": key, "severity": sev, "statement": st[:300]})
    return NodeResult({"by": "llm", "llm_call_id": meta.get("llm_call_id"), "model": meta.get("model"), "results": results, **rule_out}, "succeeded" if results else "degraded")


@node_impl("render_report", "범용 렌더링 — 명세 구성 + 계산 결과 + 판단으로 표준 보고서 산출물 조립(결정론, LLM 없음)")
def n_render_report(ctx: RunContext, node: WorkflowNode) -> NodeResult:
    an = _prepare(ctx, node)
    spec, token = an["spec"], an["token"]
    key = f"report.an-{token}"
    arts = ctx.load_artifacts()
    doc = R.render(
        spec, token, figs=an["figures"], tabs=an["tables"], verdict=an["verdicts"], findings=an["findings"], previous=arts.get(key),
        evidence=ctx.state.get("evidence") or [], as_of=R.as_of_of(ctx.eval, spec), version=an["version"],
        team=ctx.state.get("team_context"), data_evidence=R.data_evidence(ctx.eval, spec, token),
        evidence_meta=ctx.state.get("evidence_meta"),
    )
    arts[key] = doc
    ctx.changed.add(key)
    stale = [fid for fid, f in an["figures"].items() if f.get("stale")]
    return NodeResult({"artifact": key, "sections": len(doc["sections"]), "figures": len(doc["figures"]), "opinions": [{"id": o["id"], "severity": o["severity"]} for o in doc["opinions"]], **({"stale": stale} if stale else {})},
                      "degraded" if stale else "succeeded")
