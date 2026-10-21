"""워크플로우 노드 구현 레지스트리. 관리자 화면의 노드 '구현' 선택지가 된다."""
from __future__ import annotations

import copy
import json
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from nhdip.calc import run_and_record
from nhdip.calc.metrics import ResolveError, evaluate
from nhdip.graph.extraction import extract_document
from nhdip.graph.neo4j_client import GraphUnavailable
from nhdip.graph.projection import project_all
from nhdip.graph.evidence import rank_evidence
from nhdip.graph.search import graph_documents, hybrid_search, query_terms
from nhdip.llm import LlmError, LlmUnavailable, chat, embed, parse_json, resolve
from nhdip.models import Metric, Rule, RuleVersion, Setting, ViewBinding, WorkflowNode, source
from nhdip.views import builders
from nhdip.views.period_words import PERIOD_GUIDE, basis_range, basis_short, figure_note, figures_span, relabel
from nhdip.views.store import find_insight, find_paths, get_current, patch_figures, patch_insight, publish

from nhdip.llm.guard import GUARD, fence

from . import numguard
from .engine import NodeResult, RunContext, node_impl


def _setting(session: Session, key: str, default: Any = None) -> Any:
    s = session.get(Setting, key)
    return s.value if s is not None else default


def _rule_body(session: Session, code: str) -> dict[str, Any]:
    rule = session.get(Rule, code)
    if not rule:
        return {}
    rv = session.execute(select(RuleVersion).where(RuleVersion.rule_code == code, RuleVersion.version == rule.active_version)).scalar()
    return rv.body if rv else {}


def _workflow_metrics(ctx: RunContext, codes: list[str] | None = None) -> list[Metric]:
    q = select(Metric).where(Metric.workflow_code == ctx.workflow.code, Metric.enabled)
    ms = ctx.session.execute(q).scalars().all()
    return [m for m in ms if not codes or m.code in codes]


# ═════════════════════════ 데이터 · 계산 ═════════════════════════
@node_impl("load_inputs", "사용 데이터셋의 현재 버전을 고정(계보 기록)")
def n_load_inputs(ctx: RunContext, node: WorkflowNode) -> NodeResult:
    from nhdip.graph.projection import _datasets_in_args

    codes = set((node.config or {}).get("datasets") or [])
    for m in _workflow_metrics(ctx):
        codes |= _datasets_in_args(m.args)
    for b in ctx.session.execute(select(ViewBinding).where(ViewBinding.workflow_code == ctx.workflow.code, ViewBinding.enabled)).scalars():
        codes |= _datasets_in_args(b.params)
    missing, missing_codes = [], []
    for c in sorted(codes):
        try:
            ctx.eval.dataset(c)
        except ResolveError as exc:
            missing.append(str(exc))
            missing_codes.append(c)
    ctx.state["missing_datasets"] = missing_codes  # 실행 요약 · 관리자 화면의 '필요 자료 미업로드' 안내 (engine 이 읽는다)
    out = {"datasets": list(ctx.eval.used_versions.values()), "missing": missing}
    return NodeResult(out, "degraded" if missing else "succeeded")


@node_impl("compute_metrics", "지표 정의(cfg.metric)를 커널 수식으로 계산 → calc_run · metric_value")
def n_compute_metrics(ctx: RunContext, node: WorkflowNode) -> NodeResult:
    metrics = _workflow_metrics(ctx, (node.config or {}).get("metrics"))
    outcomes = evaluate(ctx.eval, metrics)
    errors = {c: o.error for c, o in outcomes.items() if o.error}
    values = {c: {"display": None if o.display is None else float(o.display), "previous": None if o.previous is None else float(o.previous), "formula": o.formula, "calc_run_id": o.calc_run_id, **({"verdict": o.extra.get("verdict")} if o.extra.get("verdict") else {})} for c, o in outcomes.items() if not o.error}
    changed = {c: v for c, v in values.items() if v["previous"] is not None and v["display"] != v["previous"]}
    return NodeResult({"computed": len(values), "errors": errors, "changed": changed, "values": values}, "degraded" if errors else "succeeded")


@node_impl("judge", "규칙(rule) 구간으로 지표를 판정하고 인사이트 심각도 등에 반영")
def n_judge(ctx: RunContext, node: WorkflowNode) -> NodeResult:
    out = []
    arts = ctx.load_artifacts()
    for item in (node.config or {}).get("items", []):
        oc = ctx.eval.outcomes.get(item["metric"])
        if not oc or oc.error or oc.value is None:
            out.append({"metric": item["metric"], "skipped": "지표 값 없음"})
            continue
        bands = _rule_body(ctx.session, item["rule"]).get("bands", [])
        run, result, _ = run_and_record(ctx.session, "BAND", {"value": oc.value, "bands": bands}, metric_code=f"{item['metric']}#band", sources=[{"rule": item["rule"]}], workflow_run_id=ctx.run.id)
        verdict = result.extra if result else {}
        ctx.state.setdefault("verdicts", {})[item["metric"]] = verdict
        applied = 0
        if item.get("insight") and verdict.get("severity"):
            for key, payload in arts.items():
                n = patch_insight(payload, item["insight"], {"severity": verdict["severity"]})
                if n:
                    ctx.changed.add(key)
                    applied += n
        out.append({"metric": item["metric"], "rule": item["rule"], "verdict": verdict.get("verdict"), "severity": verdict.get("severity"), "calc_run_id": run.id, "applied": applied})
    return NodeResult({"judgements": out})


def _resolve_target(payload: Any, path: str) -> list[tuple[str, str]]:
    """바인딩 경로 → [(dotted path, field)] — 'table:캡션' · 'chart:제목' · 점 표기 경로 (서식 캡션이면 처음 캡션 bindKey 로도)."""
    from nhdip.views.template import binding_targets

    return binding_targets(payload, path)


def mark_binding_stale(payload: Any, path: str, targets: list[tuple[str, str]], reason: str | None) -> bool:
    from nhdip.views.template import mark_binding_stale as _mark

    return _mark(payload, path, targets, reason)


def _as_of_stamp(ctx: RunContext, arts: dict[str, Any], computed: set[str]) -> None:
    """산출물 기준일(asOf) = 입력 데이터셋 현재 버전 기준일 중 가장 늦은 날 (RD-06). 출력 산출물 최상위 + 이번 실행이 수치를 고친 의견."""
    dates = [vs.as_of for vs, _, _ in ctx.eval.rows.values() if getattr(vs, "as_of", None)]
    if not dates:
        return
    iso = max(dates).isoformat()
    outputs = set(ctx.workflow.outputs or [])
    for key, payload in arts.items():
        if key not in outputs or not isinstance(payload, dict):
            continue
        hit = False
        if "asOf" in payload and payload["asOf"] != iso:
            payload["asOf"] = iso
            hit = True
        stack = list(payload.values())
        while stack:
            o = stack.pop()
            if isinstance(o, dict):
                figs = o.get("figures")
                if "asOf" in o and "statement" in o and isinstance(figs, dict) and set(figs) & computed and o["asOf"] != iso:
                    o["asOf"] = iso
                    hit = True
                stack.extend(o.values())
            elif isinstance(o, list):
                stack.extend(o)
        if hit:
            ctx.changed.add(key)


from nhdip.calc.metrics import DELETED_INPUT  # noqa: E402 — 다른 흐름 지표가 지운 자료로만 계산돼 있을 때의 오류 문구


def gone_metrics(ctx: RunContext) -> set[str]:
    """입력 자료가 없어 계산할 수 없는 지표(이 실행의 '필요 자료 미업로드' 자료를 읽는 지표 + 그 지표를 참조하는 지표).
    자료를 지우면 여기에 든다 — 그 지표의 옛 값은 '갱신 실패'로 남기지 않고 비운다. 실행마다 한 번 계산한다."""
    if "gone_metrics" in ctx.state:
        return ctx.state["gone_metrics"]
    from nhdip.graph.projection import _datasets_in_args

    missing = set(ctx.state.get("missing_datasets") or [])
    out: set[str] = set()
    if missing:
        metrics = {m.code: m for m in ctx.session.execute(select(Metric)).scalars()}
        out = {c for c, m in metrics.items() if _datasets_in_args(m.args) & missing}
        grew = True
        while grew:
            grew = False
            for c, m in metrics.items():
                if c not in out and any(isinstance(r, dict) and r.get("metric") in out for r in (m.args or {}).values()):
                    out.add(c)
                    grew = True
    ctx.state["gone_metrics"] = out
    return out


def _binding_gone(ctx: RunContext, b: ViewBinding) -> bool:
    """바인딩이 읽는 자료가 지워졌거나(필요 자료 미업로드) 지워진 자료의 지표를 쓰는지."""
    from nhdip.graph.projection import _datasets_in_args

    missing = set(ctx.state.get("missing_datasets") or [])
    if missing and _datasets_in_args(b.params) & missing:
        return True
    gone = gone_metrics(ctx)
    blob = json.dumps(b.params or {}, ensure_ascii=False, default=str)
    return any(f'"{c}"' in blob for c in gone)


@node_impl("build_views", "계산 결과로 화면 산출물의 수치(Figure)·표·차트를 갱신 (세대 교체 전 단계)")
def n_build_views(ctx: RunContext, node: WorkflowNode) -> NodeResult:
    arts = ctx.load_artifacts()
    figs: dict[str, dict[str, Any]] = {}
    # 지표 단위가 화면 단위 코드일 때만 수치 단위도 갱신 (관리자가 지표 단위 · 배율을 바꾼 경우) — B.32
    fig_units = {"KRW_MN", "KRW_BN", "KRW_TN", "PCT", "PP", "CNT", "RATIO", "NONE"}
    gone = gone_metrics(ctx)
    for code, oc in ctx.eval.outcomes.items():
        if oc.error or oc.display is None:
            if code in gone or DELETED_INPUT in (oc.error or ""):
                # 입력 자료가 지워졌다 — 지운 자료로 낸 옛 값을 남기지 않고 비운다(남은 자료로 다시 계산되는 것만 화면에 남는다)
                for fid in oc.figure_ids:
                    figs[fid] = {"cleared": True, "reason": "입력 자료 삭제"}
                continue
            # 계산 실패 — 이전 값은 두되 '갱신 실패' 로 표시해 최신 값으로 오인하지 않게 한다 (B.32)
            for fid in oc.figure_ids:
                figs[fid] = {"stale": True, "staleReason": (oc.error or "값 없음")[:200]}
            continue
        val = float(oc.display)
        if oc.decimals == 0:
            val = int(oc.display)
        payload = {"value": val, "dataOrigin": oc.data_origin, "decimals": oc.decimals, **({"unit": oc.unit} if oc.unit in fig_units else {})}
        for k in ("verdict", "severity"):  # 판정형 수식(BAND · 검정)의 문구 — 화면 칩 · 서식 문구 [[fig:ID|verdict]] (RD-07)
            if isinstance((oc.extra or {}).get(k), str):
                payload[k] = oc.extra[k]
        if oc.formula != "VALUE":
            payload["calc"] = oc.trace
        else:
            payload["sourceRef"] = oc.trace["inputs"][0]["source"] if oc.trace.get("inputs") else None
        # 기간 대체(전년 동기 자료가 없어 가장 가까운 기준일과 견줌) — 라벨 · 서식 문구가 실제 기간을 말하게(patch_figures · render_templates)
        # 비교 기간 맞춤(목표 환산 · 기간 인자) · 경영목표 수치 표시 — 목표 판정 · 서식 문구가 같은 비교 기간으로 견주게
        payload["basis"] = list(oc.fallbacks or [])
        payload["align"] = oc.align
        payload["goal"] = bool(oc.goal)
        for fid in oc.figure_ids:
            figs[fid] = payload
    changes: list[dict[str, Any]] = []
    for key, payload in arts.items():
        before = len(changes)
        patch_figures(payload, figs, changes, key)
        if len(changes) > before:
            ctx.changed.add(key)
    bind_out = []
    for b in ctx.session.execute(select(ViewBinding).where(ViewBinding.workflow_code == ctx.workflow.code, ViewBinding.enabled)).scalars():
        payload = arts.get(b.artifact_key)
        fn = builders.BUILDERS.get(b.builder)
        if payload is None or fn is None:
            bind_out.append({"id": b.id, "error": "산출물 또는 빌더 없음"})
            continue
        try:
            value = fn(ctx.eval, b.params or {})
        except (ResolveError, KeyError, ValueError, TypeError, IndexError, ArithmeticError) as exc:  # 업로드 값이 비었을 때(Decimal 변환 · 0 나눗셈)도 노드가 실패하지 않게
            bind_out.append({"id": b.id, "artifact": b.artifact_key, "error": str(exc)})
            if _binding_gone(ctx, b):
                # 입력 자료가 지워졌다 — 지운 자료로 그린 표 · 차트를 비운다(수치와 같은 정책)
                from nhdip.views.template import clear_binding

                if clear_binding(payload, b.path):
                    ctx.changed.add(b.artifact_key)
                continue
            # 계산 실패 — 표 · 차트의 이전 값은 두되 '갱신 실패' 로 표시한다(수치와 같은 정책) (DEL-11)
            if mark_binding_stale(payload, b.path, _resolve_target(payload, b.path), str(exc) or "계산 실패"):
                ctx.changed.add(b.artifact_key)
            continue
        targets = _resolve_target(payload, b.path)
        if mark_binding_stale(payload, b.path, targets, None):  # 다시 계산됐으니 갱신 실패 표시를 뗀다
            ctx.changed.add(b.artifact_key)
        for parent, fld in targets:
            obj = payload
            for p in [x for x in parent.split(".") if x]:
                obj = obj[int(p)] if isinstance(obj, list) else obj[p]
            if obj.get(fld) != value:
                obj[fld] = value
                ctx.changed.add(b.artifact_key)
        bind_out.append({"id": b.id, "artifact": b.artifact_key, "builder": b.builder, "targets": len(targets)})
    ctx.changes += changes
    # 기준일 · 서식 문구(Tpl) — 수치 · 기간이 든 평문(캡션 · 근거 · 판정 근거 · 표 머리글 · 라벨)을 계산 결과로 (설계 §25.4)
    from nhdip.views.template import apply_metric_fields, figure_index, render_templates, template_figure_ids

    # 에이전트가 쓴 문장 중 기대는 수치가 이번에 바뀐 것 — 규칙 문장으로 되돌리고(서술 단계가 다시 쓴다) 옛 서술이 새 수치 옆에 남지 않게
    moved = {c["figure"] for c in changes if not c.get("trace_only") and not c.get("stale")}
    refresh: set[str] = set()
    if moved:
        for payload in arts.values():
            for d in _walk_dicts(payload):
                if isinstance(d.get("id"), str) and any(k.endswith("By") and d[k] == "llm" for k in d) and template_figure_ids(d) & moved:
                    refresh.add(d["id"])
        ctx.state["refreshed"] = sorted(refresh)

    _as_of_stamp(ctx, arts, {fid for oc in ctx.eval.outcomes.values() if not oc.error for fid in oc.figure_ids})
    for key, payload in arts.items():
        if apply_metric_fields(payload, ctx.eval.outcomes):
            ctx.changed.add(key)
    # 경영목표 판정(정상 · 미달 · 한도 근접 · 초과) — 실적 수치와 목표 값으로 계산한다 (시드의 고정 판정이 실제 자료와 어긋나지 않게)
    from nhdip.views.goal_verdict import apply_goal_verdicts

    verdict_keys, verdicts = apply_goal_verdicts(ctx.session, arts)
    ctx.changed |= verdict_keys
    units = _setting(ctx.session, "format.unit_labels", None)
    idx = figure_index(arts)
    rendered = 0
    for key, payload in arts.items():
        if render_templates(payload, idx, ctx.eval, units if isinstance(units, dict) else None, refresh=refresh):
            ctx.changed.add(key)
            rendered += 1
    return NodeResult({"figures_patched": len(changes), "figure_changes": changes[:200], "bindings": bind_out, "templates_rendered": rendered, "goal_verdicts": verdicts,
                       **({"llm_text_refreshed": sorted(refresh)} if refresh else {})}, "degraded" if any("error" in x for x in bind_out) else "succeeded")


# ═════════════════════════ 근거 검색 · LLM ═════════════════════════
def _embedder(ctx: RunContext):
    code = _setting(ctx.session, "embedding.agent", "embedder")
    try:
        return resolve(ctx.session, code)
    except LlmUnavailable:
        return None


@node_impl("retrieve_evidence", "그래프 필터(Neo4j) → 하이브리드(키워드 · 의미 — Elasticsearch, 없으면 PostgreSQL) 검색으로 근거 구간 수집")
def n_retrieve(ctx: RunContext, node: WorkflowNode) -> NodeResult:
    cfg = node.config or {}
    plan = ctx.state.get("plan")
    if plan is not None and cfg.get("respect_plan", True) and not plan.get("evidence"):
        return NodeResult({"skipped": "플래너 — 서술 대상이 없거나 LLM 미연결이라 근거 검색 생략", "plan": {k: plan.get(k) for k in ("narrate", "llm")}})
    extra_q = (plan or {}).get("evidenceQuery") if cfg.get("respect_plan", True) else None
    if extra_q:
        # 플래너가 이번 변화에 맞춰 덧붙인 검색어 (LLM 판단 · 정제 후)
        cfg = {**cfg, "query": f"{cfg.get('query', '')} {extra_q}".strip()}
    concepts = cfg.get("concepts") or []
    if not concepts and cfg.get("concepts_from_context"):
        # 분석 에이전트(Phase P · TDB-05) — 팀 데이터 노드가 온톨로지에서 찾은 개념으로 그래프 필터
        concepts = list(ctx.state.get("context_concepts") or [])[:20]
    doc_filter = graph_documents(concepts)
    qvec = None
    emb = _embedder(ctx)
    status = "succeeded"
    note = []
    if emb:
        try:
            qvec = embed(ctx.session, emb, [cfg.get("query", "")], workflow_run_id=ctx.run.id, node_run_id=ctx.node_run_id)[0]
        except LlmError as exc:
            note.append(f"임베딩 실패 → 키워드 검색만 사용: {exc}")
    else:
        note.append("임베딩 모델 미설정 → 키워드 검색만 사용")
    if extra_q:
        note.append(f"플래너 추가 검색어: {extra_q}")
    if doc_filter is None:
        note.append("그래프 필터 없음(개념 미연결 또는 그래프 장애) → 권한 범위 전체 검색")
    k = int(cfg.get("k", 5))
    from .evidence_nodes import _doc_meta, owner_gate, with_common_classes

    # 공통 통합 DB 문서 분류도 함께(§38 CMN) — 흐름의 분류에 더한다
    cfg = {**cfg, "doc_classes": with_common_classes(ctx.session, cfg.get("doc_classes"))}
    model = emb.model if (emb is not None and qvec is not None) else None
    sdiag: dict[str, Any] = {}  # 3-way — 키워드 · 의미 후보를 ES 문서 색인에서 찾았는지(engine) · 폴백 사유
    cand = hybrid_search(ctx.session, cfg.get("query", ""), doc_filter=doc_filter, query_vec=qvec, doc_classes=cfg.get("doc_classes"), k=k * 3, model=model, diag=sdiag)
    if doc_filter is not None and not cand:
        doc_filter = None
        sdiag = {}
        cand = hybrid_search(ctx.session, cfg.get("query", ""), query_vec=qvec, doc_classes=cfg.get("doc_classes"), k=k * 3, model=model, diag=sdiag)
        note.append("그래프 필터 결과 없음 → 전체 검색으로 확장")
    if sdiag.get("esFallback") and sdiag.get("esFallback") != "ES 아직 동기화 전":
        note.append(f"검색 엔진 폴백(PostgreSQL): {sdiag['esFallback']}")
    # 영업점이 올린 문서는 그 영업점 실행에만 — 근거 붙이기와 같은 소유 규칙(§33 OWN · 다른 영업점 문서가 다른 흐름 근거로 새지 않게)
    gate_ok = owner_gate(ctx)
    metas = _doc_meta(ctx, cand)
    before = len(cand)
    cand = [h for h in cand if gate_ok(metas.get((h["origin"], h["document_id"])))]
    if len(cand) < before:
        note.append(f"영업점 소유 문서 {before - len(cand)}건 제외(다른 영업점 · 영업점 범위 밖 실행)")
    if cfg.get("team_only") and ctx.state.get("team_orgs") is not None:
        # 팀 문서 우선(Phase P · TDB-04) — 팀 소유 · 소유 없음(전행) · 공통 분류 문서만. 하나도 없으면 원래 후보로(사유 기록)
        from nhdip.common_db import common_doc_classes

        team_orgs, common_cls = set(ctx.state.get("team_orgs") or []), set(common_doc_classes(ctx.session))

        def _mine(h: dict[str, Any]) -> bool:
            d = metas.get((h["origin"], h["document_id"]))
            owner = getattr(d, "owner_org", None)
            return not owner or owner in team_orgs or h.get("doc_class") in common_cls

        mine = [h for h in cand if _mine(h)]
        if mine:
            if len(mine) < len(cand):
                note.append(f"다른 부서 문서 {len(cand) - len(mine)}건 제외(팀 문서 · 전행 · 공통 우선)")
            cand = mine
        elif cand:
            note.append("팀 · 전행 · 공통 문서가 없어 다른 부서 문서까지 넓혀 검색")
    ctx.state["evidence_meta"] = {"engine": sdiag.get("engine", "pg"), "graphFilter": doc_filter is not None, "concepts": concepts[:10], "note": " · ".join(note[-2:]) if note else None}
    # 근거 선별(3.6) — 시스템 실행이라 권한 단계는 통과, 부문 · 시점 · 문서유형 · 의미 · 개념경로 게이팅 후 우선순위 · 범주 균형
    from nhdip.data.datasets import display_as_of

    ranked = rank_evidence(ctx.session, cand, k=k, as_of=display_as_of(ctx.session), domain=cfg.get("domain"), doc_classes=cfg.get("doc_classes"), doc_filter=doc_filter, query_terms=len(query_terms(cfg.get("query", ""))))
    hits = ranked["hits"]
    if ranked["missingCategories"]:
        note.append("근거 범주 부재: " + ", ".join(ranked["missingCategories"]))
    ctx.state.setdefault("evidence", []).extend(hits)
    return NodeResult({"concepts": concepts, "graph_docs": doc_filter, "searchEngine": sdiag.get("engine", "pg"), "hits": [{k_: v for k_, v in h.items() if k_ != "text"} | {"text": h["text"][:300]} for h in hits], "rejected": ranked["rejected"][:30], "categories": ranked["categories"], "missing_categories": ranked["missingCategories"], "notes": note}, status)


LITERAL_NUM_DEFAULT = r"\d+(?:[.,]\d+)+\s*(?:%p?|bp|배)?|\d+\s*(?:%p?|bp|억|조|만|천|원|건|배)"


def _strip_markers(text: str) -> str:
    """수치 마커는 빼고 용어 마커는 라벨 글자를 남긴다 — 라벨은 화면에 그대로 보이므로 숫자 점검 대상 (numguard)."""
    return numguard.strip_markers(text)


def _statement_of(text: str) -> str:
    """서술 출력 모양 검증(LLM-P02) — JSON 객체 · statement 문자열 · 비어 있지 않음 · 2000자 이내."""
    data = parse_json(text)
    if not isinstance(data, dict):
        raise ValueError("JSON 객체가 아님")
    st = data.get("statement")
    if not isinstance(st, str) or not st.strip():
        raise ValueError("statement 비어 있음")
    if len(st) > 2000:
        raise ValueError("statement 가 너무 김(2000자 초과)")
    return st.strip()


def _narrate_call(ctx: RunContext, llm: Any, messages: list[dict[str, Any]]) -> tuple[str, Any]:
    """서술 호출 + 형식 오류면 오류를 알려 주고 같은 내용을 다시 받는다(설정 agents.llm_judge.format_retries, 기본 1 — LLM-P02).
    재요청 뒤에도 형식이 틀리면 ValueError(그 인사이트만 기존 문장 유지 — 연결 장애가 아니므로 나머지 서술은 계속)."""
    from .llm_judge import policy as judge_policy

    res = chat(ctx.session, llm, messages, json_mode=True, workflow_run_id=ctx.run.id, node_run_id=ctx.node_run_id)
    try:
        return _statement_of(res.text), res
    except ValueError as exc:
        err = exc
    for _ in range(max(0, int(judge_policy(ctx.session).get("format_retries", 1)))):
        fix = messages + [{"role": "assistant", "content": (res.text or "")[:4000]},
                          {"role": "user", "content": f"앞 응답은 형식 오류({str(err)[:120]})로 읽을 수 없다. 같은 내용을 {{\"statement\": \"...\"}} JSON 객체 하나로만 다시 출력하라. 수치는 [[fig:ID]] 마커로만, 설명 · 코드펜스 금지."}]
        res = chat(ctx.session, llm, fix, json_mode=True, workflow_run_id=ctx.run.id, node_run_id=ctx.node_run_id, purpose="chat:format-retry")
        try:
            return _statement_of(res.text), res
        except ValueError as exc:
            err = exc
    raise ValueError(f"서술 출력 형식 오류(재요청 후에도): {err}")


def target_field(t: dict[str, Any]) -> str:
    """서술 대상 필드 — 의견 문장(statement, 기본) · 제안 판단(judgement) · 수행방안 본문(body) · 영업점 가이드(guideline)."""
    return str(t.get("field") or "statement")


def target_key(t: dict[str, Any]) -> str:
    """계획 · 서술 · 검증이 대상을 부르는 이름 — 의견 문장은 id 그대로, 다른 필드는 'id.필드'."""
    f = target_field(t)
    return t["insight_id"] if f == "statement" else f"{t['insight_id']}.{f}"


def target_figures(arts: dict[str, Any], obj: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """서술 대상이 쓸 수 있는 수치 — figures 사전 + 품은 수치 + 연결된 의견(sourceInsightId)의 수치."""
    from nhdip.views.template import is_figure

    out: dict[str, dict[str, Any]] = {}
    if isinstance(obj.get("figures"), dict):
        out.update({k: v for k, v in obj["figures"].items() if isinstance(v, dict)})
    for d in _walk_dicts({k: v for k, v in obj.items() if k not in ("evidence", "figures")}):
        if is_figure(d):
            out.setdefault(d["id"], d)
    src = obj.get("sourceInsightId")
    if isinstance(src, str):
        ins = find_insight(arts, src) or {}
        for k, v in (ins.get("figures") or {}).items():
            out.setdefault(k, v)
    return out


# 필드별 서술 지침 — 노드 설정의 instruction 앞에 붙는다(관리자가 바꾸는 것은 instruction · 에이전트 프롬프트)
FIELD_GUIDE = {
    "statement": "분석 의견 문장 — 수치가 보여 주는 상태와 변화, 판정 결과, 주의할 점을 쓴다.",
    "judgement": "경영목표 조정 · 신설이 왜 필요한지(또는 필요하지 않은지) 판단 문단 — 실적과 목표의 차이, 상위 기조(근거 문서), 제약을 함께 쓴다. 추천 범위 숫자는 쓰지 않는다(화면이 따로 보여 준다).",
    "body": "수행방안 본문 — 담당 부서가 할 일을 실행 항목 중심으로 쓴다(점검 대상 · 주기 · 보고 조건). 규칙 가이드가 있으면 그 방향을 따른다.",
    "guideline": "영업점에 전달할 취급 가이드 한두 문장 — 무엇을 우선 취급하고 무엇을 조심할지. 근거 문서에 없는 기준을 만들지 않는다.",
}
SHARED_PLAN_GUIDE = ("근거의 [사업부서 진행사업] 줄은 사업부서가 영업점 참고를 켠 수행방안과 그 연결 분석이다 — 이 지점 수치와 관련 있을 때만 방향(우선 · 주의)으로 반영하고, "
                     "사업부서 분석의 수치를 이 지점 수치처럼 쓰지 않는다.")


@node_impl("narrate", "LLM 서술 — 의견 · 제안 판단 · 수행방안 본문 · 영업점 가이드. 확정 수치는 [[fig:ID]] 마커로만 참조 (실패 시 규칙 문장 유지)")
def n_narrate(ctx: RunContext, node: WorkflowNode) -> NodeResult:
    cfg = node.config or {}
    arts = ctx.load_artifacts()
    results = []
    targets = list(cfg.get("targets", []))
    plan = ctx.state.get("plan")
    if plan is not None and cfg.get("respect_plan", True):
        # 플래너 계획 — 바뀐 것이 있는 대상만 서술 (나머지는 기존 서술 유지)
        allowed = set(plan.get("candidates") or plan.get("narrate") or [])
        results = [{"insight": target_key(t), "skipped": (plan.get("skip") or {}).get(target_key(t), "계획에서 제외")} for t in targets if target_key(t) not in allowed]
        targets = [t for t in targets if target_key(t) in allowed]
        if not targets:
            return NodeResult({"plan": "서술 대상 없음 — 기존 서술 유지", "results": results})
    if ctx.llm_off:
        # 범위 서술 상한 밖 지점(B.47 · BRM-07) — 의도한 생략이라 축소가 아님. 기존 문장(또는 안내 문구) 유지
        return NodeResult({"skipped": ctx.llm_off, "targets": [target_key(t) for t in targets], "results": results})
    try:
        llm = resolve(ctx.session, node.agent_code)
    except LlmUnavailable as exc:
        return NodeResult({"fallback": "template", "reason": str(exc), "targets": [target_key(t) for t in targets], "results": results}, "degraded")
    degraded = False
    broken: str | None = None  # 첫 LLM 호출 실패 뒤에는 나머지 대상에서 같은 대기 · 재시도를 되풀이하지 않는다(게이트웨이 장애 때 실행이 수십 분 묶이는 것을 막음)
    # 영업점 흐름 — 사업부서가 '영업점 참고'를 켠 진행사업과 그 연결 분석을 근거로 읽는다(수치 이름만, 값은 영업점 자체 확정 수치 마커로).
    # 노드 설정 shared_plans: false 로 끈다
    from nhdip.views.plan_share import agent_lines, is_branch_outputs

    shared_lines = agent_lines(ctx.session) if cfg.get("shared_plans", True) and is_branch_outputs(ctx.workflow.outputs) else []
    for target in targets:
        key, field = target_key(target), target_field(target)
        if broken:
            degraded = True
            results.append({"insight": key, "fallback": "template", "error": f"앞선 LLM 호출 실패로 건너뜀: {broken}"[:300]})
            continue
        ins = find_insight(arts, target["insight_id"], field)
        if not ins:
            results.append({"insight": key, "error": "서술 대상 없음"})
            continue
        figures = target_figures(arts, ins)
        # 갱신 실패(stale) · 값 없는 수치는 서술 재료에서 뺀다 — 다시 계산하지 못한 옛 값을 최신 값처럼 서술하지 않도록 (DEL-11)
        usable = {fid: f for fid, f in figures.items() if not f.get("stale") and f.get("value") is not None}
        # 비교 기준 — 전년 동기 자료가 없어 다른 기준일과 견준 수치 · 비교 기간에 맞춘 목표를 에이전트가 알고 서술하게(PER-05)
        span = figures_span(usable)
        notes = {fid: figure_note(f, span) for fid, f in usable.items()}
        fig_lines = [f"- [[fig:{fid}]] {f.get('label')} = {f.get('value')} {f.get('unit')}" + (f" (판정 {f['verdict']})" if f.get("verdict") else "")
                     + (f" — 비교 기준: {notes[fid]}" if notes[fid] else "") for fid, f in usable.items()]
        verdicts = {k: v for k, v in (ctx.state.get("verdicts") or {}).items()}
        # 근거 — 이 대상에 붙인 문서 근거(attach_evidence)를 먼저, 이어서 이번 실행의 근거 검색 결과
        own = [e for e in (ins.get("evidence") or []) if isinstance(e, dict) and isinstance(e.get("doc"), dict)]
        ev_lines = [f"- [{e.get('category')}] {e['doc'].get('title')} p.{e['doc'].get('page') or '-'}: {(e.get('snippet') or '')[:300]}" for e in own]
        ev_lines += [f"- ({e['origin']}) {e['title']} p.{e.get('page') or '-'}: {e['text'][:300]}" for e in ctx.state.get("evidence", [])[: int(cfg.get("evidence_k", 4))]]
        ev_lines += shared_lines
        guide = ins.get("guide") if isinstance(ins.get("guide"), dict) else None
        instruction = " ".join(x for x in (FIELD_GUIDE.get(field, ""), f"규칙 가이드: {guide.get('title')} — {guide.get('text')}" if guide and guide.get("text") else "", target.get("instruction", ""),
                                           PERIOD_GUIDE if any(notes.values()) else "", SHARED_PLAN_GUIDE if shared_lines else "") if x)
        tmpl = llm.user_template or (
            "다음 확정 수치와 근거로 '{title}' 문장을 작성하라.\n규칙: 숫자를 직접 쓰지 말고 반드시 [[fig:ID]] 마커로만 수치를 참조한다(마커가 단위까지 표시하므로 마커 뒤에 건 · % · 원 같은 단위를 붙이지 않는다). 인과를 단정하지 않는다. 2~4문장.\n\n"
            "수치:\n{figures}\n\n판정:\n{verdicts}\n\n근거:\n{evidence}\n\n기존 서술(참고):\n{current}\n\n{instruction}\n출력: {{\"statement\": \"...\"}}"
        )
        # 산출물 문장(제목 · 기존 서술)도 자료로 구분자 안에 넣는다 — 편집 가능한 값이 지시문으로 읽히지 않도록 (B.32)
        try:
            user = tmpl.format(
                title=ins.get("title") or ins.get("label") or "",
                figures="\n".join(fig_lines) or "(값이 있는 수치 없음)",
                verdicts=json.dumps(verdicts, ensure_ascii=False, default=str),
                evidence=fence("\n".join(ev_lines) or "(없음)"),
                current=fence(str(ins.get(field, "") or "(없음)")),
                instruction=instruction,
            )
        except (KeyError, IndexError, ValueError) as exc:
            # 관리자가 편집한 프롬프트 자리표시자 오류 — 이 대상만 기존 서술 유지
            degraded = True
            results.append({"insight": key, "fallback": "template", "error": f"프롬프트 자리표시자 오류: {exc}"})
            continue
        messages = [{"role": "system", "content": (llm.system_prompt or "너는 은행 경영 분석 보고서를 쓰는 분석가다. JSON 으로만 답한다.") + "\n\n" + GUARD}, {"role": "user", "content": user}]
        try:
            statement, res = _narrate_call(ctx, llm, messages)
            ctx.state.setdefault("narratives", {})[key] = {"statement": statement, "llm_call_id": res.call_id, "figures": list(usable.keys()), "id": target["insight_id"], "field": field,
                                                           "agent": node.agent_code, "why": ((plan or {}).get("why") or {}).get(key)}
            results.append({"insight": key, "llm_call_id": res.call_id, "statement": statement})
        except (LlmError, ValueError, AttributeError) as exc:
            degraded = True
            results.append({"insight": key, "fallback": "template", "error": str(exc)[:300]})
            if isinstance(exc, LlmError):  # 모델 · 연결 문제(출력 형식 오류 ValueError 와 구분) — 이번 실행의 나머지 서술은 시도하지 않는다
                broken = str(exc)[:200]
    return NodeResult({"model": llm.model, "results": results}, "degraded" if degraded else "succeeded")


GROUNDING_DEFAULT = {"enabled": True, "block": False, "max_per_run": 6}
GROUNDING_TASK = (
    "문장(statement)의 주장이 판정(verdicts) · 근거 구간(evidence)과 맞는지 판정한다. [[fig:ID]] 마커는 계산 커널의 확정 값이라 맞다고 본다(figures 는 마커의 이름). "
    "verdict: supported(근거 있음) | unsupported(근거와 어긋나거나 근거 없음) | unknown(근거가 비어 판단 불가). reason 은 숫자 없이 한 문장. "
    "claims 는 근거 없는 주장 구절(문장에서 그대로, 최대 3개). "
    'JSON: {"verdict":"supported|unsupported|unknown","reason":"…","claims":["…"]}'
)


def _grounding_policy(session: Session) -> dict[str, Any]:
    s = session.get(Setting, "agents.grounding")
    raw = s.value if s is not None and isinstance(s.value, dict) else {}
    out = {**GROUNDING_DEFAULT, **raw}
    out["enabled"], out["block"] = bool(out.get("enabled")), bool(out.get("block"))
    try:
        out["max_per_run"] = max(0, int(out.get("max_per_run", 6)))
    except (TypeError, ValueError):
        out["max_per_run"] = 6
    return out


def _grounded_check(ctx: RunContext, insight_id: str, statement: str, arts: dict[str, Any], field: str = "statement") -> dict[str, Any] | None:
    """critic_grounded 한 번 — (verdict · reason · claims · llm_call_id) 또는 None(LLM 없음 · 형식 오류 → 점검 생략, 규칙 점검 결과 그대로)."""
    from .llm_judge import ask_json, clean_reason

    ins = find_insight(arts, insight_id, field) or {}
    figs = {fid: f.get("label") for fid, f in target_figures(arts, ins).items()}
    own = [{"origin": "doc", "title": (e.get("doc") or {}).get("title"), "text": (e.get("snippet") or "")[:400]} for e in (ins.get("evidence") or []) if isinstance(e, dict) and isinstance(e.get("doc"), dict)]
    ev = (own + [{"origin": e.get("origin"), "title": e.get("title"), "text": (e.get("text") or "")[:400]} for e in (ctx.state.get("evidence") or [])])[:4]
    context = {"title": ins.get("title"), "statement": statement, "figures": figs, "verdicts": ctx.state.get("verdicts") or {}, "evidence": ev}
    data, meta = ask_json(ctx.session, "critic_grounded", GROUNDING_TASK, context, workflow_run_id=ctx.run.id, node_run_id=ctx.node_run_id, shrink=("evidence",))
    if not data or data.get("verdict") not in ("supported", "unsupported", "unknown"):
        return None
    reason, _ = clean_reason(data.get("reason"), 200)
    claims = [str(c)[:120] for c in (data.get("claims") or []) if isinstance(c, str) and c.strip() and c.strip() in statement][:3]  # 문장에 실제로 있는 구절만
    return {"verdict": data["verdict"], "reason": reason, "claims": claims, "llm_call_id": meta.get("llm_call_id")}


@node_impl("critic", "검증 — 리터럴 숫자 · 미등록 수치 마커 · 인과 단정 표현 차단 (통과분만 반영)")
def n_critic(ctx: RunContext, node: WorkflowNode) -> NodeResult:
    rules = _rule_body(ctx.session, (node.config or {}).get("rule", "CRITIC_RULES"))
    extra_num = rules.get("literal_number_regex") or LITERAL_NUM_DEFAULT  # 규칙(DB)의 패턴은 내장 패턴(numguard)과 함께 적용
    causal = rules.get("causal_phrases") or []
    arts = ctx.load_artifacts()
    from nhdip.views.template import figure_index

    fig_idx = figure_index(arts)
    out = []
    degraded = False
    gpol = _grounding_policy(ctx.session)
    grounded_n = 0
    for insight_id, nar in (ctx.state.get("narratives") or {}).items():
        # 꾸밈이 붙은 수치 표식([[fig:ID|signed]])은 화면이 칩으로 그리지 못한다 — 꾸밈을 떼고 같은 수치 표식으로
        st = re.sub(r"\[\[fig:([A-Za-z0-9_\-]+)\|[a-z0-9+]+\]\]", r"[[fig:\1]]", nar["statement"])
        checks = []
        # 비교 기준 — 문장이 기대는 수치가 전년 동기 자료 없이 다른 기준일과 견준 값이면, 에이전트가 '전년 동기'라고 써도 실제 기간으로 고친다(PER-05)
        basis = [b for fid in nar.get("figures") or [] for b in (fig_idx.get(fid) or {}).get("basis") or []]
        if basis:
            fixed = relabel(st, basis)
            checks.append({"checkCode": "period_basis", "passed": True,
                           "detail": "기간 표현을 실제 비교 기준으로 고침" if fixed != st else "기간 표현이 실제 비교 기준과 맞음"})
            st = fixed
        lits = numguard.literal_numbers(st, extra_num)
        checks.append({"checkCode": "numeric_provenance", "passed": not lits, "detail": "모든 수치가 계산 결과를 참조" if not lits else f"리터럴 숫자: {lits[:5]}"})
        used = set(re.findall(r"\[\[fig:([^\]]+)\]\]", st))
        unknown = used - set(nar["figures"])
        checks.append({"checkCode": "figure_reference", "passed": not unknown, "detail": "마커 전부 확정 수치" if not unknown else f"없는 수치 마커: {sorted(unknown)}"})
        hit = [p for p in causal if p in st]
        checks.append({"checkCode": "causality_language", "passed": not hit, "detail": "인과 단정 표현 미검출" if not hit else f"검출: {hit}"})
        from .agent_nodes import record

        # 근거 일치 점검(critic_grounded · LLM-P05 · Q185) — 규칙 점검을 통과한 문장만, 실행당 상한까지. 기본 권고(막지 않음), block 이면 근거 없음 판정을 반려
        obj_id, field = nar.get("id") or insight_id, nar.get("field") or "statement"
        if all(c["passed"] for c in checks) and gpol["enabled"] and grounded_n < gpol["max_per_run"] and not ctx.llm_off:
            g = _grounded_check(ctx, obj_id, st, arts, field)
            if g is not None:
                grounded_n += 1
                bad = g["verdict"] == "unsupported"
                checks.append({"checkCode": "grounding", "passed": not (bad and gpol["block"]), "advisory": not gpol["block"], "verdict": g["verdict"],
                               "detail": ({"supported": "근거와 맞음", "unsupported": "근거와 어긋나거나 근거 없음", "unknown": "판단 불가"}[g["verdict"]] + (f" — {g['reason']}" if g.get("reason") else ""))[:300]})
                record(ctx, "critic_grounded", "grounding", f"{insight_id} 근거 일치 {g['verdict']}" + (" (권고)" if bad and not gpol["block"] else ""),
                       {"insight": insight_id, "verdict": g["verdict"], "reason": g.get("reason"), "claims": g.get("claims") or [], "block": gpol["block"], "llm_call_id": g.get("llm_call_id")})
        passed = all(c["passed"] for c in checks)

        # 범위 실행(다지점 · B.47)은 서술 이력을 범위별로 — 다른 지점 서술 이력 때문에 '최초 1회' 서술을 건너뛰지 않게
        scoped_id = f"{insight_id}{ctx.eval.scope_suffix}"
        if passed:
            fields: dict[str, Any] = {field: st, f"{field}By": "llm"}  # 규칙 문장(서식 문구)이 기대는 수치가 바뀌기 전까지 덮어쓰지 않는다
            if field == "statement":
                # 화면의 검증 표시 — 이번 점검 결과 + 근거 범주(문서 근거 · 데이터 근거)
                own = (find_insight(arts, obj_id, field) or {}).get("evidence") or []
                cats = {e.get("category") for e in own if isinstance(e, dict)}
                ev_ok = bool(cats & {"external_policy", "internal_direction"}) and "bank_data" in cats
                fields["verifications"] = [{"checkCode": c["checkCode"], "passed": c["passed"], "detail": c["detail"]} for c in checks if c["checkCode"] != "figure_reference"] + [
                    {"checkCode": "evidence_present", "passed": ev_ok, "detail": "근거 범주(문서 · 데이터) 충족" if ev_ok else "근거 범주 일부 없음 — 관련 문서를 올리면 채워짐"}]
            for key, payload in arts.items():
                if patch_insight(payload, obj_id, fields, field):
                    ctx.changed.add(key)
            record(ctx, nar.get("agent") or "narrator", "narrated", f"{scoped_id} 서술 갱신(검증 통과)", {"insight": scoped_id, "llm_call_id": nar.get("llm_call_id"), "why": nar.get("why"), "statement": st[:600]})
        else:
            degraded = True
            # 반려도 기록한다 — 어떤 문장이 어떤 점검에서 막혔는지 관리자가 [에이전트 결정]에서 볼 수 있게(예전에는 노드 출력에만 남았다)
            failed_codes = [c["checkCode"] for c in checks if not c["passed"]]
            record(ctx, nar.get("agent") or "narrator", "rejected", f"{scoped_id} 서술 반려({', '.join(failed_codes)}) — 기존 문장 유지", {"insight": scoped_id, "llm_call_id": nar.get("llm_call_id"), "why": nar.get("why"), "statement": st[:600], "checks": checks})
        out.append({"insight": insight_id, "passed": passed, "checks": checks})
    return NodeResult({"reviewed": out}, "degraded" if degraded else "succeeded")


# ═════════════════════════ 게시 ═════════════════════════
def _index_knowledge(session: Session, keys: list[str]) -> dict[str, Any] | None:
    """게시한 산출물을 같은 트랜잭션에서 질문하기 지식 색인에 반영한다(텍스트 · 개념 · 컬렉션 — 네트워크 호출 없음, KB-01).
    임베딩은 워커가 이어서 채운다. 색인 실패는 게시를 막지 않는다 — 워커 대조(1분)가 다시 색인한다."""
    import logging

    from nhdip.knowledge.indexer import index_artifacts

    try:
        with session.begin_nested():
            session.flush()
            return index_artifacts(session, keys).as_dict()
    except Exception as exc:  # noqa: BLE001
        logging.getLogger("nhdip.workflow").warning("지식 색인 실패(게시는 유지, 워커 대조가 복구): %s", exc, exc_info=True)
        return {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}


@node_impl("publish", "변경된 산출물만 새 세대로 게시 (이전 세대 보존, 사용자 상태는 별도 보존) — 같은 트랜잭션에서 질문하기 지식 색인 반영")
def n_publish(ctx: RunContext, node: WorkflowNode) -> NodeResult:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    arts = ctx.load_artifacts()
    # 화면 표시 시각은 업무 시간대(기본 Asia/Seoul) 기준
    now = datetime.now(ZoneInfo(_setting(ctx.session, "ui.timezone", "Asia/Seoul"))).isoformat(timespec="seconds")
    from nhdip.locks import lock
    from nhdip.views.store import merge3

    published, merged = [], []
    for key in sorted(ctx.changed):
        payload = arts[key]
        if isinstance(payload, dict) and "generatedAt" in payload:
            payload["generatedAt"] = now
        # 같은 산출물을 여러 워크플로우가 동시에 게시할 수 있다 — 키별 잠금 후, 읽은 뒤 바뀌었으면 3방향 병합 (B.32)
        lock(ctx.session, f"artifact:{key}")
        current = get_current(ctx.session, key)
        base = ctx.base.get(key)
        if current is not None and base is not None and json.dumps(current, sort_keys=True, default=str) != json.dumps(base, sort_keys=True, default=str):
            payload = merge3(base, payload, current)
            arts[key] = payload
            merged.append(key)
        if json.dumps(current, sort_keys=True, default=str) == json.dumps(payload, sort_keys=True, default=str):
            continue
        row = publish(ctx.session, key, copy.deepcopy(payload), produced_by=ctx.workflow.code, workflow_run_id=ctx.run.id, changes=[c for c in ctx.changes if c["artifact"] == key][:200])
        ctx.session.flush()
        published.append({"key": key, "generation": row.generation})
    ctx.changed = {p["key"] for p in published}
    kb = _index_knowledge(ctx.session, [p["key"] for p in published]) if published else None
    # 영업점 참고 수행방안의 연결 분석 보고서가 새로 게시됐으면 영업점 참고 산출물(질문하기 색인)도 지금 보고서로
    from nhdip.views.plan_share import refresh_if_linked

    plans_refreshed = refresh_if_linked(ctx.session, [p["key"] for p in published], ctx.workflow.code) if published else False
    # 플래너가 정한 후속 워크플로우 — 게시가 끝난 뒤 실행되도록 이벤트로 넘긴다(오케스트레이터가 연쇄 · 순서 관리)
    followups = []
    for f in ctx.state.get("followups") or []:
        ctx.emit_after_success("agent.followup", {"workflow": f["workflow"], "reason": f.get("reason"), "by": "planner", "from": ctx.workflow.code, "run": ctx.run.id, "chain": f.get("chain") or [ctx.workflow.code]}, "planner")
        followups.append(f["workflow"])
    events = ctx.flush_deferred()  # 게시와 같은 트랜잭션 (B.33)
    return NodeResult({"events": events, "published": published, **({"merged": merged} if merged else {}), **({"followups": followups} if followups else {}), **({"knowledge": kb} if kb else {}),
                       **({"branchSharedPlans": "갱신"} if plans_refreshed else {})})


# ═════════════════════════ 문서 · 그래프 ═════════════════════════
def _cause_documents(ctx: RunContext) -> list[tuple[str, int]]:
    out = []
    for c in ctx.causes:
        p = c.get("payload") or {}
        if c.get("type") == "document.ingested" and p.get("document_id"):
            out.append((p["origin"], int(p["document_id"])))
    return out


@node_impl("embed_chunks", "임베딩 미생성 · 다른 모델 청크를 임베딩 모델로 벡터화 (PostgreSQL 원장 → 워커가 ES 문서 색인으로 동기화)")
def n_embed(ctx: RunContext, node: WorkflowNode) -> NodeResult:
    emb = None
    try:
        emb = resolve(ctx.session, node.agent_code or _setting(ctx.session, "embedding.agent", "embedder"))
    except LlmUnavailable as exc:
        # 임베딩 모델이 없으면 일을 하지 않았다 — '성공'(초록)이 아니라 '건너뜀'으로 보여 준다
        return NodeResult({"skipped": str(exc)}, "skipped")
    limit = int((node.config or {}).get("limit", 200))
    batch = int((node.config or {}).get("batch", 16))
    done = 0
    for origin in ("bank", "ext"):
        t = source(origin)
        # 임베딩 없음 + 지금 모델과 다른 모델로 만든 것(모델 교체 후 다시 — 분석 결과 색인 embed_pending 과 같은 규칙). 현재 버전 문서 우선
        stale = t.chunk.embedding.is_(None) | t.chunk.embedding_model.is_distinct_from(emb.model)
        chunks = ctx.session.execute(
            select(t.chunk).join(t.document, t.document.id == t.chunk.document_id).where(stale).order_by(t.document.is_current.desc(), t.chunk.id).limit(limit)
        ).scalars().all()
        for i in range(0, len(chunks), batch):
            part = chunks[i : i + batch]
            try:
                vecs = embed(ctx.session, emb, [c.text for c in part], workflow_run_id=ctx.run.id, node_run_id=ctx.node_run_id)
            except LlmError as exc:
                return NodeResult({"embedded": done, "error": str(exc)[:300]}, "degraded")
            for c, v in zip(part, vecs):
                c.embedding = v
                c.embedding_model = emb.model
            done += len(part)
    return NodeResult({"embedded": done, "model": emb.model})


@node_impl("extract_documents", "문서 → 온톨로지 구조화 (LLM + 스키마 검증, 미설정 시 규칙 추출)")
def n_extract(ctx: RunContext, node: WorkflowNode) -> NodeResult:
    targets = _cause_documents(ctx)
    if (node.config or {}).get("all_pending", True):
        for origin in ("bank", "ext"):
            t = source(origin)
            for d in ctx.session.execute(select(t.document.id).where(t.document.is_current, t.document.status == "ingested")).scalars():
                targets.append((origin, d))
    # 스키마 판이 바뀌면 이전 판으로 추출한 문서를 실행당 몇 건씩 다시 추출한다(Phase M · ONB-11) — 새 클래스 · 관계 · 별칭이 문서 근거에도 반영되게
    from nhdip.graph.projection import active_schema
    from nhdip.graph.proposals import build_policy

    sc = active_schema(ctx.session)
    n_re = int(build_policy(ctx.session).get("reextract_per_run", 5) or 0) if sc is not None else 0
    reextract = 0
    if n_re > 0:
        for origin in ("bank", "ext"):
            t = source(origin)
            for d in ctx.session.execute(select(t.document).where(t.document.is_current, t.document.status.in_(["extracted", "partial"])).order_by(t.document.id)).scalars():
                if reextract >= n_re:
                    break
                if int(((d.extraction or {}).get("schema_version")) or 0) < sc.version:
                    targets.append((origin, d.id))
                    reextract += 1
    import time as _time

    cfg = node.config or {}
    # 한 번에 처리할 문서 수 · 시간 상한 — 문서가 많이 올라와도 한 실행이 몇 시간씩 묶여 감시 스레드에 끊기고 처음부터 반복되는 것을 막는다(남은 문서는 이어서)
    max_docs, budget = int(cfg.get("max_documents", 20) or 0), float(cfg.get("budget_sec", 600) or 0)
    t0 = _time.monotonic()
    seen = set()
    results = []
    todo = []
    for origin, did in targets:
        if (origin, did) not in seen:
            seen.add((origin, did))
            todo.append((origin, did))
    done = 0
    for origin, did in todo:
        if (max_docs and done >= max_docs) or (budget and _time.monotonic() - t0 > budget):
            break
        doc = ctx.session.get(source(origin).document, did)
        done += 1
        if not doc or not doc.is_current:
            continue
        results.append(extract_document(ctx.session, origin, doc, agent_code=node.agent_code or "ontology_extractor", max_chunks=int(cfg.get("max_chunks", 12)), workflow_run_id=ctx.run.id, node_run_id=ctx.node_run_id))
        ctx.session.commit()  # 문서마다 확정 — 뒤쪽 문서가 실패해도 앞에서 끝낸 구조화는 남는다
    remaining = len(todo) - done
    out: dict[str, Any] = {"documents": results, **({"reextracted": reextract} if reextract else {})}
    if remaining > 0:
        out["remaining"] = remaining
        # 이번에 실제로 구조화가 진행됐을 때만 이어서 실행한다(진행이 없는데 되풀이하는 무한 반복 방지)
        if any(r.get("by") for r in results):
            ctx.emit_after_success("manual", {"workflow": ctx.workflow.code, "reason": f"남은 문서 {remaining}건 이어서 구조화"}, "system")
    return NodeResult(out, "degraded" if any(r.get("issues") for r in results) or remaining > 0 else "succeeded")


@node_impl("project_graph", "PostgreSQL → Neo4j 멱등 투영 (세대 기반 정리)")
def n_project(ctx: RunContext, node: WorkflowNode) -> NodeResult:
    ctx.session.flush()
    try:
        return NodeResult(project_all(ctx.session))
    except GraphUnavailable as exc:
        return NodeResult({"error": f"그래프 장애 — 다음 이벤트에서 재투영: {exc}"[:500]}, "degraded")
    except (ValueError, TypeError, KeyError) as exc:  # 그래프 드라이버 설정 오류(주소 형식 등) · 잘못된 저장 값 — 실행 전체를 실패시켜 3번 되풀이하지 않고 축소로 알린다
        import logging

        logging.getLogger("nhdip.workflow").warning("그래프 투영 오류", exc_info=True)
        return NodeResult({"error": f"그래프 투영 오류 — {type(exc).__name__}: {str(exc)[:300]}"}, "degraded")


# ═════════════════════════ 컬럼 정의서 ═════════════════════════
@node_impl("materialize_contracts", "컬럼 정의서 테이블(mart.*) 적재 + 정의서 화면값 대조 (Critic 이후 · 게시 전)")
def n_contracts(ctx: RunContext, node: WorkflowNode) -> NodeResult:
    from nhdip.contracts.materialize import materialize

    try:
        reports = materialize(ctx.session, ctx.eval, ctx.load_artifacts(), (node.config or {}).get("tables"), ctx.run.id)
    except ResolveError as exc:
        # 기준 자료(예: 월별 여신현황)가 아직 올라오지 않았다 — 오류가 아니라 '건너뜀'. 자료가 올라오면 다음 실행에서 적재된다
        ctx.session.rollback()
        return NodeResult({"reason": "필요 자료 미업로드", "detail": str(exc)[:300]}, "skipped")
    for code, rep in reports.items():
        key = f"contract.{code}"
        ctx.artifacts[key] = rep
        ctx.changed.add(key)
    bad = {c: r["summary"] for c, r in reports.items() if r["summary"].get("mismatch") or r["summary"].get("error")}
    return NodeResult({"tables": {c: {"table": r["table"], "summary": r["summary"], "notes": r["notes"]} for c, r in reports.items()}, "attention": bad}, "degraded" if bad else "succeeded")


# ═════════════════════════ 목표 추천 · Attention 순위 (Phase 2.5.4 · 2.6) ═════════════════════════
def _walk_dicts(obj: Any):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _walk_dicts(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_dicts(v)


def _num_text(v: Any, decimals: int, unit: str = "", sign: bool = False) -> str:
    from decimal import ROUND_HALF_UP, Decimal

    q = Decimal(str(v)).quantize(Decimal(1).scaleb(-decimals) if decimals > 0 else Decimal(1), rounding=ROUND_HALF_UP)
    s = f"{q:,.{decimals}f}"
    return f"{'+' if sign and q > 0 else ''}{s}{unit}"


@node_impl("rank_attentions", "AI Attention 우선순위 점수(규칙 ATTENTION_SCORE) → rankScore · rankBasis · 계산 추적")
def n_rank_attentions(ctx: RunContext, node: WorkflowNode) -> NodeResult:
    from nhdip.calc.metrics import resolve_ref

    rule_code = (node.config or {}).get("rule", "ATTENTION_SCORE")
    body = _rule_body(ctx.session, rule_code)
    importance = body.get("importance_points") or {}
    # 화면의 산출 규칙 표시 — 규칙 코드 · 적용 판 (Phase K · HC-04: 화면 코드에 규칙 판을 두지 않는다)
    rule_row = ctx.session.get(Rule, rule_code)
    rule_label = f"{rule_code} v{rule_row.active_version}" if rule_row is not None else rule_code
    arts = ctx.load_artifacts()
    out = []
    for att_id, comps in (body.get("items") or {}).items():
        resolved = []
        try:
            for c in comps:
                if c.get("metric"):
                    val, _, detail = resolve_ref(ctx.eval, {"metric": c["metric"]})
                    # 비교 기준 — 전년 동기 자료 없이 다른 기준일과 견줬거나 목표를 비교 기간으로 환산한 값이면 점수 근거에 드러낸다(PER-05)
                    src_oc = ctx.eval.outcomes.get(c["metric"])
                    note = basis_short((detail or {}).get("fallback"), src_oc.align if src_oc is not None else None)
                    text = _num_text(abs(val), int(c.get("decimals", 2)), c.get("unit", "")) + (f" · {note}" if note else "")
                    resolved.append({"label": c["label"], "value": val, "per_unit": c.get("per_unit", 1), "max": c.get("max"), "text": text})
                elif c.get("importance"):
                    resolved.append({"label": c["label"], "points": importance.get(c["importance"], 0), "text": c["importance"]})
                else:
                    resolved.append({"label": c["label"], "points": c.get("points", 0), "text": c.get("text")})
        except ResolveError as exc:
            out.append({"id": att_id, "skipped": str(exc)})
            continue
        run, res, _ = run_and_record(ctx.session, "ATTENTION_SCORE", {"components": resolved}, metric_code=f"attention#{att_id}", sources=[{"rule": rule_code}], decimals=1, workflow_run_id=ctx.run.id)
        if res is None:
            out.append({"id": att_id, "error": run.error})
            continue
        score = float(res.value)  # 항목 점수가 0.1 단위로 확정되어 합계도 0.1 단위
        basis = " + ".join(f"{p['label']}({p['text']} → {p['points']}점)" if p.get("text") else f"{p['label']}({p['points']}점)" for p in res.extra["parts"])
        hits = 0
        for key, payload in arts.items():
            for d in _walk_dicts(payload):
                if d.get("id") == att_id and "rankScore" in d and (d.get("rankScore") != score or d.get("rankBasis") != basis or d.get("rankCalcId") is None or d.get("rankRule") != rule_label):
                    d["rankScore"], d["rankBasis"], d["rankCalcId"], d["rankRule"] = score, basis, run.id, rule_label
                    ctx.changed.add(key)
                    hits += 1
        out.append({"id": att_id, "score": score, "basis": basis, "calc_run_id": run.id, "patched": hits})
        # 해설 에이전트(curate_attentions)가 쓸 점수 구성 — 항목 이름과 점수만(숫자는 해설에 쓰지 않는다)
        ctx.state.setdefault("attention_parts", {})[att_id] = [{"label": p["label"], "points": p.get("points", 0)} for p in res.extra["parts"]]
    return NodeResult({"rule": rule_code, "attentions": out}, "degraded" if any("error" in x or "skipped" in x for x in out) else "succeeded")


CURATE_TASK = (
    "주목 사항(items)마다 왜 지금 주목해야 하는지 한두 문장(reason, 80자 이내)으로 쓴다. 숫자를 쓰지 않는다(점수 · 비율은 화면이 따로 보여 준다). 순위는 바꾸지 않는다. "
    "점수 구성 항목(parts — 점수가 큰 순)과 판정 · 관련 의견을 근거로, 인과를 단정하지 않는다. id 는 입력 그대로. "
    'JSON: {"items":[{"id":"…","reason":"…"}]}'
)


def _rule_rank_reason(parts: list[dict[str, Any]]) -> str:
    """LLM 이 없거나 실패했을 때 — 점수가 큰 구성 항목 이름으로 만든 문장(숫자 없음)."""
    top = [p["label"] for p in sorted(parts, key=lambda p: -float(p.get("points") or 0)) if float(p.get("points") or 0) > 0][:2]
    if not top:
        return "점수 구성 항목이 고르게 반영되어 순위가 정해졌습니다."
    return f"{' · '.join(top)} 항목이 점수를 가장 많이 올려 상위에 올랐습니다." if len(top) > 1 else f"{top[0]} 항목이 점수를 가장 많이 올려 상위에 올랐습니다."


@node_impl("curate_attentions", "AI 주목 사항 해설(attention_curator) — 순위는 규칙 그대로, 항목마다 숫자 없는 해설 rankReason (LLM 없음 · 실패면 점수 구성 문장)")
def n_curate_attentions(ctx: RunContext, node: WorkflowNode) -> NodeResult:
    from .llm_judge import ask_json, clean_reason

    parts_of: dict[str, list[dict[str, Any]]] = ctx.state.get("attention_parts") or {}
    if not parts_of:
        return NodeResult({"skipped": "점수 매긴 주목 사항 없음(앞 단계 rank_attentions)"})
    arts = ctx.load_artifacts()
    found: dict[str, dict[str, Any]] = {}
    for payload in arts.values():
        for d in _walk_dicts(payload):
            if d.get("id") in parts_of and "rankScore" in d and d["id"] not in found:
                found[d["id"]] = d
    items = [{"id": aid, "title": d.get("title") or d.get("label"), "severity": d.get("severity") or d.get("level"), "status": d.get("status"),
              "parts": [p["label"] for p in sorted(parts_of[aid], key=lambda p: -float(p.get("points") or 0))],
              "note": re.sub(r"\d[\d,.]*", "", str(d.get("statement") or d.get("summary") or d.get("description") or ""))[:200]}
             for aid, d in found.items()]
    reasons: dict[str, tuple[str, str]] = {aid: (_rule_rank_reason(parts_of[aid]), "rule") for aid in found}
    meta: dict[str, Any] = {"by": "rule"}
    dropped = 0
    if items and not ctx.llm_off:
        data, meta = ask_json(ctx.session, node.agent_code or "attention_curator", CURATE_TASK, {"items": items}, workflow_run_id=ctx.run.id, node_run_id=ctx.node_run_id, required=("items",), shrink=("items",))
        for it in (data or {}).get("items") or []:
            if not isinstance(it, dict) or it.get("id") not in reasons:
                continue
            text, bad = clean_reason(it.get("reason"), 160)
            if text and not bad and not re.search(r"\d", text):  # 숫자 점검을 통과한 문장만
                reasons[it["id"]] = (text, "llm")
            else:
                dropped += 1
    changed = 0
    for aid, d in found.items():
        text, by = reasons[aid]
        for payload_key, payload in arts.items():
            for x in _walk_dicts(payload):
                if x.get("id") == aid and "rankScore" in x and (x.get("rankReason") != text or x.get("rankReasonBy") != by):
                    x["rankReason"], x["rankReasonBy"] = text, by
                    ctx.changed.add(payload_key)
                    changed += 1
    from .agent_nodes import record

    llm_n = sum(1 for _, by in reasons.values() if by == "llm")
    record(ctx, node.agent_code or "attention_curator", "curated", f"주목 사항 {len(reasons)}건 해설(LLM {llm_n} · 규칙 {len(reasons) - llm_n})",
           {"items": {k: {"reason": v[0], "by": v[1]} for k, v in reasons.items()}, "llm": {k: meta.get(k) for k in ("by", "reason", "model", "llm_call_id")}, "dropped": dropped})
    return NodeResult({"items": len(reasons), "llm": llm_n, "dropped": dropped, "patched": changed, "by": meta.get("by"), "reason": meta.get("reason")})


@node_impl("recommend_goals", "경영목표 추천 범위(GOAL_RANGE_REC 등 지표) → 제안의 추천범위 · 문구 · 산출 근거 갱신 (숫자는 커널 값만)")
def n_recommend_goals(ctx: RunContext, node: WorkflowNode) -> NodeResult:
    units = _setting(ctx.session, "format.unit_labels", {}) or {}
    arts = ctx.load_artifacts()
    proposals = arts.get("proposals")
    if not isinstance(proposals, list):
        return NodeResult({"skipped": "제안 산출물 없음"}, "degraded")
    out = []
    for item in (node.config or {}).get("items", []):
        oc = ctx.eval.outcomes.get(item["metric"])
        prop = next((p for p in proposals if p.get("id") == item["proposal"]), None)
        if prop is not None and (item["metric"] in gone_metrics(ctx) or DELETED_INPUT in ((oc.error if oc else "") or "")):
            # 추천 근거 자료가 지워졌다 — 지운 자료로 낸 추천 범위를 남기지 않는다(검토 목록에서 빠지고, 자료가 다시 오르면 다시 계산)
            rec = dict(prop.get("recommendation") or {})
            cleared = {**rec, **{k: None for k in ("low", "high", "value", "currentValue") if k in rec}, "text": ""}
            cleared.pop("calcId", None)
            cleared.pop("engine", None)
            label = item.get("input_label", "⑤ 엔진 산출 범위")
            inputs = [x for x in (prop.get("ruleInputs") or []) if x.get("label") != label]
            if cleared != rec or inputs != (prop.get("ruleInputs") or []):
                prop["recommendation"], prop["ruleInputs"] = cleared, inputs
                ctx.changed.add("proposals")
            out.append({"proposal": item["proposal"], "cleared": "입력 자료 삭제 — 추천 범위를 비움"})
            continue
        if prop is None or oc is None or oc.error or oc.value is None:
            out.append({"proposal": item["proposal"], "skipped": "제안 또는 지표 값 없음" if not (oc and oc.error) else oc.error})
            continue
        d = int(item.get("decimals", 1))
        unit = units.get(item.get("unit", "NONE"), "")
        scale = float(item.get("scale") or oc_scale(ctx, item["metric"]))
        low = (oc.extra.get("low") if oc.extra.get("low") is not None else oc.value)
        high = (oc.extra.get("high") if oc.extra.get("high") is not None else oc.value)
        low, high = float(low) / scale, float(high) / scale
        sign = bool(item.get("sign"))
        vals = {"low": _num_text(low, d, unit, sign), "high": _num_text(high, d, unit, sign)}
        cur = None
        if item.get("current"):
            co = ctx.eval.outcomes.get(item["current"])
            if co and co.value is not None:
                cur = float(co.value)
                vals["current"] = _num_text(cur, d, unit, sign)
        rec = dict(prop.get("recommendation") or {})
        new = {
            **rec,
            "low": float(_num_text(low, d)),
            "high": float(_num_text(high, d)),
            "text": item["text"].format(**vals),
            "calcId": oc.calc_run_id,
            "engine": {k: (float(v) if hasattr(v, "quantize") else v) for k, v in oc.extra.items() if k in ("anchor", "direction", "clamped")},
        }
        if cur is not None:
            new["currentValue"] = cur
        changed = new != rec
        prop["recommendation"] = new
        # 산출 근거(ruleInputs) — 엔진 항목만 교체, 문서 근거 항목은 유지
        label = item.get("input_label", "⑤ 엔진 산출 범위")
        detail = [f"{vals['low']} ~ {vals['high']}"]
        if oc.extra.get("anchor") is not None:
            detail.append(f"기준 {_num_text(float(oc.extra['anchor']) / scale, d, unit, sign)}")
        if oc.extra.get("direction"):
            detail.append({"expand": "기조 확대", "control": "기조 관리", "maintain": "기조 유지"}.get(oc.extra["direction"], oc.extra["direction"]))
        if oc.extra.get("clamped"):
            detail.append("제약 적용: " + ", ".join({"ceiling": "상한", "floor": "하한"}.get(x, x) for x in oc.extra["clamped"]))
        if item.get("trend"):
            to = ctx.eval.outcomes.get(item["trend"])
            if to and to.value is not None:
                # 추세 구간 — 2년 전 동기 자료가 없어 다른 기준일부터 잰 추세면 실제 구간(연평균은 그 기간으로 맞춰 계산 — CAGR 기간 인자)
                span = basis_range(to.fallbacks)
                detail.append(f"추세({span} 연평균) {_num_text(float(to.value), 2, '%')}" if span else f"{item.get('trend_label') or '3개년 추세'} {_num_text(float(to.value), 2, '%')}")
        entry = {"label": label, "value": " · ".join(detail), "source": f"calc_run {oc.calc_run_id} · {oc.formula}"}
        inputs = [x for x in (prop.get("ruleInputs") or []) if x.get("label") != label]
        if inputs + [entry] != prop.get("ruleInputs"):
            prop["ruleInputs"] = inputs + [entry]
            changed = True
        if changed:
            ctx.changed.add("proposals")
        out.append({"proposal": item["proposal"], "low": new["low"], "high": new["high"], "text": new["text"], "calc_run_id": oc.calc_run_id, "changed": changed})
    return NodeResult({"proposals": out}, "degraded" if any("skipped" in x for x in out) else "succeeded")


def oc_scale(ctx: RunContext, code: str) -> float:
    m = ctx.session.get(Metric, code)
    return float(m.scale) if m and m.scale else 1.0


# ═════════════════════════ 구분 표시명 · 분석 탭 (F.18 · 5.6) ═════════════════════════
@node_impl("apply_segment_labels", "부도율 추이 구분 표시명 — 설정 risk.segment_labels → 데이터 구분명(segment_label) 순 (개인 풀 코드 확정 시 설정만 교체)")
def n_segment_labels(ctx: RunContext, node: WorkflowNode) -> NodeResult:
    # 산출물 · 설정 · 자료는 노드 설정(config)으로만 받는다 — 코드에 기본 자료 코드를 두지 않는다 (Phase O · BIZ-08)
    cfg = node.config or {}
    art_key = cfg.get("artifact")
    arts = ctx.load_artifacts()
    payload = arts.get(art_key) if art_key else None
    if not isinstance(payload, dict):
        return NodeResult({"skipped": "산출물 없음(config.artifact)"}, "degraded")
    overrides = (_setting(ctx.session, cfg["setting"], {}) if cfg.get("setting") else {}) or {}
    data_labels: dict[str, str] = {}
    key_col, label_col, order_col = cfg.get("key_col", "segment_key"), cfg.get("label_col", "segment_label"), cfg.get("order_col", "ym")
    if cfg.get("dataset"):
        try:
            _, rows, _ = ctx.eval.dataset(cfg["dataset"])
            for r in sorted(rows, key=lambda r: str(r.get(order_col) or "")):
                if r.get(key_col) and r.get(label_col):
                    data_labels[r[key_col]] = r[label_col]
        except (ResolveError, KeyError, ValueError):
            pass
    changed = []
    for list_key in cfg.get("lists") or []:
        for series in payload.get(list_key) or []:
            key, old = series.get("key"), series.get("label")
            new = overrides.get(key) or data_labels.get(key) or old
            if not new or new == old:
                continue
            series["label"] = new
            for fig in _walk_dicts(series):
                if isinstance(fig.get("label"), str) and old and old in fig["label"] and fig is not series:
                    fig["label"] = fig["label"].replace(old, new)
            changed.append({"key": key, "from": old, "to": new})
    note = _setting(ctx.session, cfg["note_setting"], "") if cfg.get("note_setting") else ""
    if note and payload.get("retailNote") != note:
        payload["retailNote"] = note
        changed.append({"note": True})
    if changed:
        ctx.changed.add(art_key)
    return NodeResult({"changed": changed, "overrides": len(overrides), "data_labels": len(data_labels)})


@node_impl("sync_analysis_tabs", "분석 탭 심각도 · 생성 시각을 현재 인사이트 판정과 맞춤 (탭 = 인사이트별 보고서)")
def n_sync_tabs(ctx: RunContext, node: WorkflowNode) -> NodeResult:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    arts = ctx.load_artifacts()
    tab_key = (node.config or {}).get("artifact") or "analysis_tabs"  # 부서별 탭 산출물 (예: 영업점 branch_tabs)
    tabs = arts.get(tab_key)
    if not isinstance(tabs, dict):
        return NodeResult({"skipped": f"탭 산출물 없음: {tab_key}"}, "degraded")
    tz = ZoneInfo(_setting(ctx.session, "ui.timezone", "Asia/Seoul"))
    now = datetime.now(tz).isoformat(timespec="seconds")
    sev: dict[str, str] = {}
    for key, payload in arts.items():
        if key == tab_key:
            continue
        for d in _walk_dicts(payload):
            if d.get("id", "").startswith((node.config or {}).get("insight_prefix", "ins-")) and d.get("severity") and "statement" in d:
                sev.setdefault(d["id"], d["severity"])
    own = set((node.config or {}).get("reports") or [])
    out = []
    for tab in tabs.get("current") or []:
        s = sev.get(tab.get("insightId"))
        upd = {}
        if s and s != tab.get("severity"):
            upd["severity"] = s
        report_key = tab.get("reportKey") or f"report.{tab.get('tabKey')}"
        if tab.get("reportKind") in own and (report_key in ctx.changed):
            upd["generatedAt"] = now
        if upd:
            tab.update(upd)
            out.append({"tab": tab["tabKey"], **upd})
    if out:
        ctx.changed.add(tab_key)
    return NodeResult({"updated": out})


# ═════════════════════════ 가이드 카탈로그 (Phase 2.5.3) ═════════════════════════
_OPS = {">": lambda a, b: a > b, ">=": lambda a, b: a >= b, "<": lambda a, b: a < b, "<=": lambda a, b: a <= b, "==": lambda a, b: a == b}


@node_impl("select_guides", "수행방안 가이드 선택 — 규칙 GUIDE_CATALOG 의 조건(지표 · 비교 · 기준)으로 방안별 가이드를 고른다")
def n_select_guides(ctx: RunContext, node: WorkflowNode) -> NodeResult:
    from decimal import Decimal

    from nhdip.calc.metrics import resolve_ref

    rule_code = (node.config or {}).get("rule", "GUIDE_CATALOG")
    body = _rule_body(ctx.session, rule_code)
    guides, plans_map = body.get("guides") or {}, body.get("plans") or {}
    only = set((node.config or {}).get("plans") or plans_map)
    arts = ctx.load_artifacts()
    plan_key = (node.config or {}).get("artifact") or "action_plans"  # 수행방안 산출물 키 (노드 설정)
    plans = arts.get(plan_key)
    if not isinstance(plans, list):
        return NodeResult({"skipped": f"수행방안 산출물 없음: {plan_key}"}, "degraded")
    out = []
    for p in plans:
        if p.get("id") not in only or p.get("id") not in plans_map:
            continue
        chosen, basis_all = None, []
        for code in plans_map[p["id"]]:
            g = guides.get(code)
            if not g:
                continue
            basis, ok = [], True
            for cond in g.get("when") or []:
                try:
                    val, _, _ = resolve_ref(ctx.eval, {"metric": cond["metric"]})
                except ResolveError as exc:
                    ok = False
                    basis.append({"metric": cond["metric"], "error": str(exc)})
                    break
                hit = _OPS[cond.get("op", ">")](Decimal(str(val)), Decimal(str(cond["value"])))
                basis.append({"metric": cond["metric"], "label": cond.get("label", cond["metric"]), "value": float(val), "op": cond.get("op", ">"), "threshold": cond["value"], "met": hit})
                ok = ok and hit
            basis_all.append({"guide": code, "met": ok, "basis": basis})
            if ok:
                chosen = (code, g, basis)
                break
        if not chosen:
            out.append({"plan": p["id"], "selected": None, "tried": basis_all})
            continue
        code, g, basis = chosen
        guide = {"ruleId": code, "title": g.get("title"), "text": g.get("text"), "basis": basis, "rule": rule_code}
        if p.get("guideRuleId") != code or p.get("guide") != guide:
            p["guideRuleId"], p["guide"] = code, guide
            ctx.changed.add(plan_key)
        out.append({"plan": p["id"], "selected": code})
    return NodeResult({"rule": rule_code, "plans": out})


# 판단 에이전트 노드(변화 감지 · 플래너) 등록 — B.30
from . import agent_nodes as _agent_nodes  # noqa: E402,F401
# 분석 에이전트 노드(동적 수행 · 범용 렌더링) 등록 — Phase C
from . import analysis_nodes as _analysis_nodes  # noqa: E402,F401

# 온톨로지 구축 에이전트 노드(구조 파악 · 객체 유형 · 링크 · 해소 · 품질 · 제안) 등록 — Phase M
from . import onto_nodes as _onto_nodes  # noqa: E402,F401
# 문서 근거 붙이기(화면 근거 칸 · 제약 근거 문서를 올라온 문서로) 등록
from . import evidence_nodes as _evidence_nodes  # noqa: E402,F401
# 새 지표 제안(지표가 없는 자료의 측정 열 → 승인 대기 지표) 등록
from . import metric_nodes as _metric_nodes  # noqa: E402,F401
# 새 자료 → 개념 연결 · 분석 화면 제안(데이터 책임자 승인 대기 · §40 STW) 등록
from . import proposal_nodes as _proposal_nodes  # noqa: E402,F401
