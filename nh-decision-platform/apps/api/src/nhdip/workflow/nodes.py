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
from nhdip.views.store import find_insight, find_paths, get_current, patch_figures, patch_insight, publish

from nhdip.llm.guard import GUARD, fence

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
    missing = []
    for c in sorted(codes):
        try:
            ctx.eval.dataset(c)
        except ResolveError as exc:
            missing.append(str(exc))
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


@node_impl("build_views", "계산 결과로 화면 산출물의 수치(Figure)·표·차트를 갱신 (세대 교체 전 단계)")
def n_build_views(ctx: RunContext, node: WorkflowNode) -> NodeResult:
    arts = ctx.load_artifacts()
    figs: dict[str, dict[str, Any]] = {}
    # 지표 단위가 화면 단위 코드일 때만 수치 단위도 갱신 (관리자가 지표 단위 · 배율을 바꾼 경우) — B.32
    fig_units = {"KRW_MN", "KRW_BN", "KRW_TN", "PCT", "PP", "CNT", "RATIO", "NONE"}
    for oc in ctx.eval.outcomes.values():
        if oc.error or oc.display is None:
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
        except (ResolveError, KeyError, ValueError, TypeError) as exc:
            bind_out.append({"id": b.id, "artifact": b.artifact_key, "error": str(exc)})
            continue
        targets = _resolve_target(payload, b.path)
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
    from nhdip.views.template import apply_metric_fields, figure_index, render_templates

    _as_of_stamp(ctx, arts, {fid for oc in ctx.eval.outcomes.values() if not oc.error for fid in oc.figure_ids})
    for key, payload in arts.items():
        if apply_metric_fields(payload, ctx.eval.outcomes):
            ctx.changed.add(key)
    units = _setting(ctx.session, "format.unit_labels", None)
    idx = figure_index(arts)
    rendered = 0
    for key, payload in arts.items():
        if render_templates(payload, idx, ctx.eval, units if isinstance(units, dict) else None):
            ctx.changed.add(key)
            rendered += 1
    return NodeResult({"figures_patched": len(changes), "figure_changes": changes[:200], "bindings": bind_out, "templates_rendered": rendered}, "degraded" if any("error" in x for x in bind_out) else "succeeded")


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
    return re.sub(r"\[\[fig:[^\]]+\]\]|\{\{term:[^}]+\}\}", " ", text)


@node_impl("narrate", "LLM 서술 — 확정 수치는 [[fig:ID]] 마커로만 참조 (실패 시 기존 서술 유지 = 템플릿 폴백)")
def n_narrate(ctx: RunContext, node: WorkflowNode) -> NodeResult:
    cfg = node.config or {}
    arts = ctx.load_artifacts()
    results = []
    targets = list(cfg.get("targets", []))
    plan = ctx.state.get("plan")
    if plan is not None and cfg.get("respect_plan", True):
        # 플래너 계획 — 바뀐 것이 있는 인사이트만 서술 (나머지는 기존 서술 유지)
        allowed = set(plan.get("candidates") or plan.get("narrate") or [])
        results = [{"insight": t["insight_id"], "skipped": (plan.get("skip") or {}).get(t["insight_id"], "계획에서 제외")} for t in targets if t["insight_id"] not in allowed]
        targets = [t for t in targets if t["insight_id"] in allowed]
        if not targets:
            return NodeResult({"plan": "서술 대상 없음 — 기존 서술 유지", "results": results})
    if ctx.llm_off:
        # 범위 서술 상한 밖 지점(B.47 · BRM-07) — 의도한 생략이라 축소가 아님. 기존 문장(또는 안내 문구) 유지
        return NodeResult({"skipped": ctx.llm_off, "targets": [t["insight_id"] for t in targets], "results": results})
    try:
        llm = resolve(ctx.session, node.agent_code)
    except LlmUnavailable as exc:
        return NodeResult({"fallback": "template", "reason": str(exc), "targets": [t["insight_id"] for t in targets], "results": results}, "degraded")
    degraded = False
    for target in targets:
        ins = find_insight(arts, target["insight_id"])
        if not ins:
            results.append({"insight": target["insight_id"], "error": "인사이트 없음"})
            continue
        figures = ins.get("figures") or {}
        fig_lines = [f"- [[fig:{fid}]] {f.get('label')} = {f.get('value')} {f.get('unit')}" for fid, f in figures.items()]
        verdicts = {k: v for k, v in (ctx.state.get("verdicts") or {}).items()}
        ev = ctx.state.get("evidence", [])[: int(cfg.get("evidence_k", 4))]
        ev_lines = [f"- ({e['origin']}) {e['title']} p.{e.get('page') or '-'}: {e['text'][:300]}" for e in ev]
        tmpl = llm.user_template or (
            "다음 확정 수치와 근거로 '{title}' 의견 문장을 작성하라.\n규칙: 숫자를 직접 쓰지 말고 반드시 [[fig:ID]] 마커로만 수치를 참조한다(마커가 단위까지 표시하므로 마커 뒤에 건 · % · 원 같은 단위를 붙이지 않는다). 인과를 단정하지 않는다. 2~4문장.\n\n"
            "수치:\n{figures}\n\n판정:\n{verdicts}\n\n근거:\n{evidence}\n\n기존 서술(참고):\n{current}\n\n{instruction}\n출력: {{\"statement\": \"...\"}}"
        )
        # 산출물 문장(제목 · 기존 서술)도 자료로 구분자 안에 넣는다 — 편집 가능한 값이 지시문으로 읽히지 않도록 (B.32)
        try:
            user = tmpl.format(
                title=ins.get("title", ""),
                figures="\n".join(fig_lines),
                verdicts=json.dumps(verdicts, ensure_ascii=False, default=str),
                evidence=fence("\n".join(ev_lines) or "(없음)"),
                current=fence(str(ins.get("statement", "") or "(없음)")),
                instruction=target.get("instruction", ""),
            )
        except (KeyError, IndexError, ValueError) as exc:
            # 관리자가 편집한 프롬프트 자리표시자 오류 — 이 인사이트만 기존 서술 유지
            degraded = True
            results.append({"insight": target["insight_id"], "fallback": "template", "error": f"프롬프트 자리표시자 오류: {exc}"})
            continue
        messages = [{"role": "system", "content": (llm.system_prompt or "너는 은행 경영 분석 보고서를 쓰는 분석가다. JSON 으로만 답한다.") + "\n\n" + GUARD}, {"role": "user", "content": user}]
        try:
            res = chat(ctx.session, llm, messages, json_mode=True, workflow_run_id=ctx.run.id, node_run_id=ctx.node_run_id)
            data = parse_json(res.text)
            statement = str(data.get("statement", "")).strip()
            if not statement:
                raise ValueError("statement 비어 있음")
            ctx.state.setdefault("narratives", {})[target["insight_id"]] = {"statement": statement, "llm_call_id": res.call_id, "figures": list(figures.keys())}
            results.append({"insight": target["insight_id"], "llm_call_id": res.call_id, "statement": statement})
            ctx.state["narratives"][target["insight_id"]] |= {"agent": node.agent_code, "why": ((plan or {}).get("why") or {}).get(target["insight_id"])}
        except (LlmError, ValueError, AttributeError) as exc:
            degraded = True
            results.append({"insight": target["insight_id"], "fallback": "template", "error": str(exc)[:300]})
    return NodeResult({"model": llm.model, "results": results}, "degraded" if degraded else "succeeded")


@node_impl("critic", "검증 — 리터럴 숫자 · 미등록 수치 마커 · 인과 단정 표현 차단 (통과분만 반영)")
def n_critic(ctx: RunContext, node: WorkflowNode) -> NodeResult:
    rules = _rule_body(ctx.session, (node.config or {}).get("rule", "CRITIC_RULES"))
    num_re = re.compile(rules.get("literal_number_regex") or LITERAL_NUM_DEFAULT)
    causal = rules.get("causal_phrases") or []
    arts = ctx.load_artifacts()
    out = []
    degraded = False
    for insight_id, nar in (ctx.state.get("narratives") or {}).items():
        st = nar["statement"]
        checks = []
        lits = num_re.findall(_strip_markers(st))
        checks.append({"checkCode": "numeric_provenance", "passed": not lits, "detail": "모든 수치가 계산 결과를 참조" if not lits else f"리터럴 숫자: {lits[:5]}"})
        used = set(re.findall(r"\[\[fig:([^\]]+)\]\]", st))
        unknown = used - set(nar["figures"])
        checks.append({"checkCode": "figure_reference", "passed": not unknown, "detail": "마커 전부 확정 수치" if not unknown else f"없는 수치 마커: {sorted(unknown)}"})
        hit = [p for p in causal if p in st]
        checks.append({"checkCode": "causality_language", "passed": not hit, "detail": "인과 단정 표현 미검출" if not hit else f"검출: {hit}"})
        passed = all(c["passed"] for c in checks)
        if passed:
            for key, payload in arts.items():
                if patch_insight(payload, insight_id, {"statement": st}):
                    ctx.changed.add(key)
            from .agent_nodes import record

            # 범위 실행(다지점 · B.47)은 서술 이력을 범위별로 — 다른 지점 서술 이력 때문에 '최초 1회' 서술을 건너뛰지 않게
            scoped_id = f"{insight_id}{ctx.eval.scope_suffix}"
            record(ctx, nar.get("agent") or "narrator", "narrated", f"{scoped_id} 서술 갱신(검증 통과)", {"insight": scoped_id, "llm_call_id": nar.get("llm_call_id"), "why": nar.get("why")})
        else:
            degraded = True
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
    # 플래너가 정한 후속 워크플로우 — 게시가 끝난 뒤 실행되도록 이벤트로 넘긴다(오케스트레이터가 연쇄 · 순서 관리)
    followups = []
    for f in ctx.state.get("followups") or []:
        ctx.emit_after_success("agent.followup", {"workflow": f["workflow"], "reason": f.get("reason"), "by": "planner", "from": ctx.workflow.code, "run": ctx.run.id, "chain": f.get("chain") or [ctx.workflow.code]}, "planner")
        followups.append(f["workflow"])
    events = ctx.flush_deferred()  # 게시와 같은 트랜잭션 (B.33)
    return NodeResult({"events": events, "published": published, **({"merged": merged} if merged else {}), **({"followups": followups} if followups else {}), **({"knowledge": kb} if kb else {})})


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
        return NodeResult({"skipped": str(exc)}, "succeeded")
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
    seen = set()
    results = []
    for origin, did in targets:
        if (origin, did) in seen:
            continue
        seen.add((origin, did))
        doc = ctx.session.get(source(origin).document, did)
        if not doc or not doc.is_current:
            continue
        results.append(extract_document(ctx.session, origin, doc, agent_code=node.agent_code or "ontology_extractor", max_chunks=int((node.config or {}).get("max_chunks", 12)), workflow_run_id=ctx.run.id, node_run_id=ctx.node_run_id))
    return NodeResult({"documents": results}, "degraded" if any(r.get("issues") for r in results) else "succeeded")


@node_impl("project_graph", "PostgreSQL → Neo4j 멱등 투영 (세대 기반 정리)")
def n_project(ctx: RunContext, node: WorkflowNode) -> NodeResult:
    ctx.session.flush()
    try:
        return NodeResult(project_all(ctx.session))
    except GraphUnavailable as exc:
        return NodeResult({"error": f"그래프 장애 — 다음 이벤트에서 재투영: {exc}"[:500]}, "degraded")


# ═════════════════════════ 컬럼 정의서 ═════════════════════════
@node_impl("materialize_contracts", "컬럼 정의서 테이블(mart.*) 적재 + 정의서 화면값 대조 (Critic 이후 · 게시 전)")
def n_contracts(ctx: RunContext, node: WorkflowNode) -> NodeResult:
    from nhdip.contracts.materialize import materialize

    reports = materialize(ctx.session, ctx.eval, ctx.load_artifacts(), (node.config or {}).get("tables"), ctx.run.id)
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
    arts = ctx.load_artifacts()
    out = []
    for att_id, comps in (body.get("items") or {}).items():
        resolved = []
        try:
            for c in comps:
                if c.get("metric"):
                    val, _, _ = resolve_ref(ctx.eval, {"metric": c["metric"]})
                    resolved.append({"label": c["label"], "value": val, "per_unit": c.get("per_unit", 1), "max": c.get("max"), "text": _num_text(abs(val), int(c.get("decimals", 2)), c.get("unit", ""))})
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
                if d.get("id") == att_id and "rankScore" in d and (d.get("rankScore") != score or d.get("rankBasis") != basis or d.get("rankCalcId") is None):
                    d["rankScore"], d["rankBasis"], d["rankCalcId"] = score, basis, run.id
                    ctx.changed.add(key)
                    hits += 1
        out.append({"id": att_id, "score": score, "basis": basis, "calc_run_id": run.id, "patched": hits})
    return NodeResult({"rule": rule_code, "attentions": out}, "degraded" if any("error" in x or "skipped" in x for x in out) else "succeeded")


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
                detail.append(f"3개년 추세 {_num_text(float(to.value), 2, '%')}")
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
    cfg = node.config or {}
    art_key = cfg.get("artifact", "default_rate_trend")
    arts = ctx.load_artifacts()
    payload = arts.get(art_key)
    if not isinstance(payload, dict):
        return NodeResult({"skipped": "산출물 없음"}, "degraded")
    overrides = _setting(ctx.session, cfg.get("setting", "risk.segment_labels"), {}) or {}
    data_labels: dict[str, str] = {}
    try:
        _, rows, _ = ctx.eval.dataset(cfg.get("dataset", "DEFAULT_RATE_MONTHLY"))
        for r in sorted(rows, key=lambda r: str(r.get("ym") or "")):
            if r.get("segment_key") and r.get("segment_label"):
                data_labels[r["segment_key"]] = r["segment_label"]
    except (ResolveError, KeyError, ValueError):
        pass
    changed = []
    for list_key in cfg.get("lists", ["corpSegments", "retailPools"]):
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
    note = _setting(ctx.session, cfg.get("note_setting", "risk.retail_pool_note"), "")
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
