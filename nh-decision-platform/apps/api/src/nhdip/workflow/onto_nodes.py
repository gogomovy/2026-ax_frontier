"""온톨로지 구축 에이전트 노드 (Phase M · 요구사항 §30 ONB-04~10 · 워크플로 wf_ontology_build)

  profile_datasets    구조 파악 에이전트 onto_profiler   열 통계 · 의미 유형 · 키 후보(결정론) + 열의 업무 의미(LLM · 없으면 규칙) → ops.data_profile
  design_object_types 객체 유형 설계 에이전트 onto_modeler 원천 없는 데이터셋 → 기존 클래스 원천 · 새 객체 유형(기본 키 · 제목 · 속성)
  discover_links      링크 발견 에이전트 onto_linker      포함률로 외래 키 후보 → 링크 유형(이름 · 다중도 · 원천 열)
  resolve_entities    개체 해소 에이전트 onto_resolver    미해석 후보 → 별칭 제안(유사도 · 애매한 쌍은 LLM 판정)
  check_ontology      품질 검증 에이전트 onto_qa(규칙)    스키마 · 범위 · 버려진 관계 · 키 중복 · 다중도 · 후보 적체 · 재추출 대상
  propose_ontology    변경 제안 onto_steward(규칙)        앞 단계 연산을 제안으로(대기 중 · 이미 반영된 것은 빼고), 정책이 허용하면 자동 적용

1차 판단은 결정론이고 LLM 은 이름 · 의미 · 애매한 경우만 정한다(Q182). LLM 출력은 허용 목록 · 형식으로 검증하고, 맞지 않으면 규칙 결과를 쓴다.
스키마는 이 워크플로에서 바로 바꾸지 않는다 — 제안 → 관리자 승인(Q181).
"""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select

from nhdip.data.datasets import current_rows, current_versions
from nhdip.graph import links as L
from nhdip.graph import profile as P
from nhdip.graph import resolve as R
from nhdip.graph.proposals import auto_apply, build_policy, create_proposal
from nhdip.models import Dataset

from .agent_nodes import record
from .engine import NodeResult, RunContext, node_impl
from .llm_judge import ask_json, clean_reason

LABEL_RE = re.compile(r"^[A-Z][A-Za-z0-9]{1,40}$")
REL_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,40}$")


def _schema(ctx: RunContext):
    from nhdip.graph.projection import active_schema

    return active_schema(ctx.session)


def _rows(ctx: RunContext) -> dict[str, list[dict[str, Any]]]:
    """이번 실행에서 한 번만 읽는다 — 모든 활성 데이터셋의 현재 행."""
    cache = ctx.state.get("_onto_rows")
    if cache is None:
        cache = {}
        for ds in ctx.session.execute(select(Dataset).where(Dataset.active)).scalars():
            cache[ds.code] = current_rows(ctx.session, ds)[1]
        ctx.state["_onto_rows"] = cache
    return cache


def _datasets(ctx: RunContext) -> list[Dataset]:
    return list(ctx.session.execute(select(Dataset).where(Dataset.active).order_by(Dataset.code)).scalars())


def _cause_datasets(ctx: RunContext) -> list[str]:
    out: list[str] = []
    for c in ctx.causes:
        if not isinstance(c, dict):
            continue
        p = c.get("payload") or {}
        code = p.get("dataset") if str(c.get("type") or "").startswith("dataset.") else ((p.get("code") or p.get("key")) if c.get("type") == "config.changed" and p.get("kind") == "dataset" else None)
        if code and code not in out:
            out.append(str(code))
    return out


def _ops(ctx: RunContext) -> list[dict[str, Any]]:
    return ctx.state.setdefault("onto_ops", [])


def _add_op(ctx: RunContext, op: dict[str, Any], why: str, confidence: float, by: str, group: str = "model") -> None:
    _ops(ctx).append({"op": op, "why": why[:300], "confidence": round(float(confidence), 3), "by": by, "group": group})


# ═════════════════════════ 1. 구조 파악 ═════════════════════════
PROFILE_TASK = (
    "아래 데이터셋의 열마다 업무 의미를 한국어 한 구절(20자 이내)로 쓰고, 그 열이 가리키는 업무 개체(예: 상품 · 지점 · 고객군 · 평가 모형)가 있으면 entity 에 쓴다. "
    "행 하나가 어떤 업무 개체인지(entity)와 데이터셋 요약(summary, 숫자 없이 한 문장)도 쓴다. 열 이름은 입력의 name 만 쓴다. "
    'JSON: {"columns":[{"name":"…","meaning":"…","entity":"…|null"}],"entity":"…|null","summary":"…"}'
)


@node_impl("profile_datasets", "구조 파악 에이전트 — 열 통계 · 의미 유형 · 키 후보(결정론) + 업무 의미(LLM, 없으면 규칙) → ops.data_profile")
def n_profile_datasets(ctx: RunContext, node) -> NodeResult:
    pol = build_policy(ctx.session)
    cfg = node.config or {}
    rows_by = _rows(ctx)
    all_ds = _datasets(ctx)
    by_code = {d.code: d for d in all_ds}
    wanted = [c for c in _cause_datasets(ctx) if c in by_code]
    sigs = {d.code: P.version_sig(current_versions(ctx.session, d)) for d in all_ds}
    for d in all_ds:  # 아직 이 버전으로 파악하지 않은 데이터셋
        lp = P.latest_profile(ctx.session, d.code)
        if (lp is None or lp.version_sig != sigs[d.code]) and d.code not in wanted and rows_by.get(d.code):
            wanted.append(d.code)
    cap = int(cfg.get("max_datasets") or pol["max_datasets"])
    todo, later = wanted[:cap], wanted[cap:]
    profiles: dict[str, dict[str, Any]] = {}
    done = []
    for code in todo:
        ds = by_code[code]
        rows = rows_by.get(code) or []
        lp = P.latest_profile(ctx.session, code)
        if lp is not None and lp.version_sig == sigs[code] and not cfg.get("force"):
            profiles[code] = lp.profile
            continue
        prof = P.profile_rows(ds, rows)
        sem, meta = None, {"by": "rule", "reason": "LLM 사용 안 함(설정 ontology.build.llm)"}
        if pol.get("llm", True) and rows:
            cols = [{"name": k, "label": v["label"], "semantic": v["semantic"], "baseType": v["baseType"], "distinct": v["distinct"], "examples": [t["value"] for t in v["top"][:3]]} for k, v in prof["columns"].items()]
            data, meta = ask_json(ctx.session, node.agent_code or "onto_profiler", PROFILE_TASK, {"dataset": {"code": ds.code, "name": ds.name, "kind": ds.kind, "description": ds.description[:300]}, "columns": cols},
                                  workflow_run_id=ctx.run.id, node_run_id=ctx.node_run_id, required=("columns",), shrink=("columns",))
            if data:
                names = set(prof["columns"])
                out_cols = {}
                for c in data.get("columns") or []:
                    if isinstance(c, dict) and c.get("name") in names:
                        meaning, _ = clean_reason(c.get("meaning"), 40)
                        entity, _ = clean_reason(c.get("entity"), 30)
                        out_cols[c["name"]] = {"meaning": meaning or prof["columns"][c["name"]]["label"], "entity": entity or None}
                summary, _ = clean_reason(data.get("summary"), 160)
                entity, _ = clean_reason(data.get("entity"), 30)
                sem = {"columns": out_cols, "entity": entity or None, "summary": summary, "by": "llm"}
        if sem is None:
            sem = P.rule_semantics(ds, prof)
        P.save_profile(ctx.session, ds, sigs[code], prof, sem, meta.get("model") and f"llm:{meta['model']}" or "rule", ctx.run.id)
        profiles[code] = prof
        done.append(code)
        record(ctx, node.agent_code or "onto_profiler", "profiled", f"{ds.name} 구조 파악 — 열 {len(prof['columns'])}개 · 키 후보 {len(prof['keyCandidates'])}개", {"dataset": code, "by": sem.get("by"), "llm": meta, "dimensions": prof["dimensions"][:12], "measures": prof["measures"][:12]})
    # 다음 단계는 모든 데이터셋의 최신 구조를 본다(이번에 다시 파악하지 않은 것 포함)
    for d in all_ds:
        if d.code not in profiles:
            lp = P.latest_profile(ctx.session, d.code)
            if lp is not None:
                profiles[d.code] = lp.profile
    ctx.state["onto_profiles"] = profiles
    return NodeResult({"profiled": done, "reused": [c for c in todo if c not in done], "later": later, "known": len(profiles)})


# ═════════════════════════ 2. 객체 유형 설계 ═════════════════════════
MODEL_TASK = (
    "후보마다 이 데이터셋 행을 어떤 객체 유형으로 둘지 정한다. 기존 클래스(existing 목록의 label)에 붙일 수 있으면 target 에 그 label, 새로 만들면 target=null 로 두고 "
    "label(영문 PascalCase) · ko(한국어 업무 이름) · description(한 문장, 숫자 금지)를 쓴다. title_col 은 사람이 읽는 이름 열(후보 열 중), props 는 후보 props 중 객체 속성으로 둘 열만. "
    "금액 · 비율 같은 측정값은 속성으로 두지 않는다. 확신이 없으면 keep=false. "
    'JSON: {"decisions":[{"index":0,"keep":true,"target":"…|null","label":"…","ko":"…","description":"…","title_col":"…|null","props":["…"]}]}'
)


@node_impl("design_object_types", "객체 유형 설계 에이전트 — 원천 없는 데이터셋 → 기존 클래스 원천 · 새 객체 유형(기본 키 · 제목 · 속성) 제안")
def n_design_object_types(ctx: RunContext, node) -> NodeResult:
    from nhdip.graph.extraction import Resolver

    pol = build_policy(ctx.session)
    schema = _schema(ctx)
    if schema is None:
        return NodeResult({"skipped": "활성 스키마 없음"}, "skipped")
    profiles = ctx.state.get("onto_profiles") or {}
    rows_by = _rows(ctx)
    from nhdip.data.sources import Resolver as Sources

    src = Sources(ctx.session)  # 업무 구성 '자료'의 온톨로지 연결(nodes)로 이미 객체가 되는 데이터셋은 다시 제안하지 않는다(Phase O)
    dss = _datasets(ctx)
    mapped = {d.code for d in dss if any(m.get("nodes") for m in src.mappings_for(d.code))}
    cands = L.object_type_candidates(dss, profiles, schema, rows_by, Resolver(schema), pol, mapped)
    if not cands:
        ctx.state["onto_planned"] = {}
        return NodeResult({"candidates": 0})
    labels = {c.get("label") for c in schema.classes or []}
    decisions: dict[int, dict[str, Any]] = {}
    meta: dict[str, Any] = {"by": "rule"}
    if pol.get("llm", True):
        ctxd = {"existing": [{"label": c.get("label"), "ko": c.get("ko"), "kind": c.get("kind"), "description": c.get("description")} for c in schema.classes or [] if c.get("kind") != "system"],
                "candidates": [{"index": i, "dataset": c["dataset"], "name": c["datasetName"], "suggested": c["label"], "existing": c["existing"], "key_col": c["key_col"], "title_col": c["title_col"],
                                "props": list(c["props"]), "semantics": (profiles.get(c["dataset"]) or {}).get("columns", {}) and {k: v.get("semanticKo") for k, v in profiles[c["dataset"]]["columns"].items()}} for i, c in enumerate(cands)]}
        data, meta = ask_json(ctx.session, node.agent_code or "onto_modeler", MODEL_TASK, ctxd, workflow_run_id=ctx.run.id, node_run_id=ctx.node_run_id, required=("decisions",), shrink=("candidates",))
        for d in (data or {}).get("decisions") or []:
            if isinstance(d, dict) and isinstance(d.get("index"), int) and 0 <= d["index"] < len(cands):
                decisions[d["index"]] = d
    planned: dict[str, tuple[str, str]] = {}
    out = []
    for i, c in enumerate(cands):
        d = decisions.get(i)
        by = "llm" if d else "rule"
        if d and d.get("keep") is False:
            out.append({"dataset": c["dataset"], "skipped": "에이전트가 객체 유형으로 두지 않음"})
            record(ctx, node.agent_code or "onto_modeler", "skipped", f"{c['datasetName']} — 객체 유형으로 두지 않음", {"dataset": c["dataset"], "by": "llm", "llm": meta})
            continue
        target = d.get("target") if d and isinstance(d.get("target"), str) and d.get("target") in labels else (c["label"] if c["existing"] else None)
        label = target or (d.get("label") if d and isinstance(d.get("label"), str) and LABEL_RE.match(d["label"]) and d["label"] not in labels else c["label"])
        ko, _ = clean_reason(d.get("ko") if d else None, 30)
        desc, _ = clean_reason(d.get("description") if d else None, 160)
        title = d.get("title_col") if d and d.get("title_col") in ({c["title_col"]} | set(c["props"])) else c["title_col"]
        cols = [p for p in (d.get("props") if d and isinstance(d.get("props"), list) else list(c["props"])) if p in c["props"] and p != title]
        # {속성 이름: 열} — 파일에서 만든 열(한글 머리글)은 속성 이름 규칙(영문 · 숫자 · 밑줄)에 맞춘 이름으로, 한글은 ko 로(Phase O)
        props = {L.prop_name(col, i): col for i, col in enumerate(cols)}
        backing = {"dataset": c["dataset"], "key_col": c["key_col"], **({"title_col": title} if title else {}), "props": props}
        prof_cols = (profiles.get(c["dataset"]) or {}).get("columns") or {}
        properties = [{"name": "name", "ko": "이름", "base_type": "string", "required": True}] + [
            {"name": p, "ko": prof_cols.get(col, {}).get("label") or col, "base_type": prof_cols.get(col, {}).get("baseType", "string"), "required": False} for p, col in props.items()]
        why = f"{c['datasetName']}({c['dataset']}) 행 = {'기존 ' + target if target else '새 객체 유형 ' + label} · 키 {c['key_col']}" + (f" · 기존 키 포함률 {c['containment']:.0%}" if c.get("containment") else "")
        if target:
            _add_op(ctx, {"op": "add_backing", "label": target, "backing": backing}, why, c["confidence"], by)
            have = {p.get("name") for c2 in schema.classes or [] if c2.get("label") == target for p in c2.get("properties") or []}
            for prop in properties[1:]:
                if prop["name"] not in have:
                    _add_op(ctx, {"op": "add_property", "label": target, "property": prop}, f"{target} 속성 {prop['name']} ← {c['dataset']}", c["confidence"], by)
        else:
            _add_op(ctx, {"op": "add_class", "class": {"label": label, "ko": ko or c["ko"], "kind": "object", "description": desc or f"{c['datasetName']} 의 행", "key_hint": c["key_col"],
                                                       "primary_key": "key", "title_property": "name", "properties": properties, "backing": [backing], "extractable": False, "required": []}}, why, c["confidence"], by)
            labels.add(label)
        planned[c["dataset"]] = (target or label, c["key_col"])
        out.append({"dataset": c["dataset"], "label": target or label, "existing": bool(target), "by": by})
        record(ctx, node.agent_code or "onto_modeler", "object_type", why, {"dataset": c["dataset"], "label": target or label, "existing": bool(target), "by": by, "llm": meta, "props": list(props)})
    ctx.state["onto_planned"] = planned
    return NodeResult({"candidates": len(cands), "decisions": out, "llm": meta.get("by")})


# ═════════════════════════ 3. 링크 발견 ═════════════════════════
LINK_TASK = (
    "링크 후보마다 관계 이름을 정한다. type 은 영문 대문자와 밑줄(예: IN_PRODUCT_GROUP), ko 는 한국어 업무 이름(10자 이내), inverse 는 반대 방향 이름. "
    "포함률 · 다중도는 데이터로 이미 정해졌으니 바꾸지 않는다. 업무상 의미 없는 우연한 일치면 keep=false. "
    'JSON: {"links":[{"index":0,"keep":true,"type":"…","ko":"…","inverse":"…"}]}'
)


@node_impl("discover_links", "링크 발견 에이전트 — 포함률로 외래 키 후보 → 링크 유형(이름 · 다중도 · 원천 열) 제안")
def n_discover_links(ctx: RunContext, node) -> NodeResult:
    from nhdip.graph.extraction import Resolver

    pol = build_policy(ctx.session)
    schema = _schema(ctx)
    if schema is None:
        return NodeResult({"skipped": "활성 스키마 없음"}, "skipped")
    profiles = ctx.state.get("onto_profiles") or {}
    cands = L.link_candidates(_datasets(ctx), profiles, schema, _rows(ctx), Resolver(schema), pol, ctx.state.get("onto_planned") or {})
    types = {r.get("type") for r in schema.relations or []}
    names: dict[int, dict[str, Any]] = {}
    meta: dict[str, Any] = {"by": "rule"}
    if cands and pol.get("llm", True):
        data, meta = ask_json(ctx.session, node.agent_code or "onto_linker", LINK_TASK, {"links": [{"index": i, **{k: c[k] for k in ("dataset", "from_class", "from_col", "to_class", "to_col", "containment", "cardinality", "type", "ko")}} for i, c in enumerate(cands)]},
                              workflow_run_id=ctx.run.id, node_run_id=ctx.node_run_id, required=("links",), shrink=("links",))
        for d in (data or {}).get("links") or []:
            if isinstance(d, dict) and isinstance(d.get("index"), int) and 0 <= d["index"] < len(cands):
                names[d["index"]] = d
    out = []
    for i, c in enumerate(cands):
        d = names.get(i)
        if d and d.get("keep") is False:
            record(ctx, node.agent_code or "onto_linker", "skipped", f"{c['from_class']}→{c['to_class']} 링크 후보 제외(우연한 일치)", {"candidate": c, "by": "llm", "llm": meta})
            continue
        rtype = d.get("type") if d and isinstance(d.get("type"), str) and REL_RE.match(d["type"]) and d["type"] not in types else c["type"]
        n = 2
        while rtype in types:
            rtype, n = f"{c['type']}_{n}", n + 1
        types.add(rtype)
        ko, _ = clean_reason(d.get("ko") if d else None, 20)
        inv, _ = clean_reason(d.get("inverse") if d else None, 20)
        why = f"{c['dataset']}.{c['to_col']} 값의 {c['containment']:.0%} 가 {c['to_class']} 키 · 고유값 {c['distinct']}개 · 다중도 {c['cardinality']}"
        _add_op(ctx, {"op": "add_relation", "relation": {"type": rtype, "ko": ko or c["ko"], "from": c["from_class"], "to": c["to_class"], "cardinality": c["cardinality"], **({"inverse": inv} if inv else {}),
                                                         "description": why, "extractable": False, "backing": [{"dataset": c["dataset"], "from_col": c["from_col"], "to_col": c["to_col"]}]}},
                why, c["confidence"], "llm" if d else "rule", "link")
        out.append({"type": rtype, "from": c["from_class"], "to": c["to_class"], "containment": c["containment"], "cardinality": c["cardinality"], "by": "llm" if d else "rule"})
        record(ctx, node.agent_code or "onto_linker", "link", f"{c['from_class']} → {c['to_class']} ({rtype})", {"candidate": c, "type": rtype, "by": "llm" if d else "rule", "llm": meta})
    return NodeResult({"candidates": len(cands), "links": out, "llm": meta.get("by")})


# ═════════════════════════ 4. 개체 해소 ═════════════════════════
RESOLVE_TASK = (
    "쌍마다 원문 이름(raw)이 대표 키(key) 또는 alternatives 중 하나와 같은 대상인지 판정한다. 같으면 same=true 와 그 key, 다르거나 확신이 없으면 same=false. "
    "약칭 · 띄어쓰기 · 표기 차이는 같은 대상이고, 상위 · 하위 개념이나 다른 상품은 다른 대상이다. "
    'JSON: {"decisions":[{"index":0,"same":true,"key":"…"}]}'
)


@node_impl("resolve_entities", "개체 해소 에이전트 — 미해석 후보 → 별칭 제안(유사도 · 애매한 쌍은 LLM 판정)")
def n_resolve_entities(ctx: RunContext, node) -> NodeResult:
    pol = build_policy(ctx.session)
    schema = _schema(ctx)
    if schema is None:
        return NodeResult({"skipped": "활성 스키마 없음"}, "skipped")
    cands = R.gather_candidates(ctx.session)
    uni = R.universe(schema, _rows(ctx))
    lo, hi = (pol.get("resolve_llm_band") or [0.7, 0.84])[:2]
    accept, ask = [], []
    for c in cands:
        m = R.best_match(c, uni)
        if not m:
            continue
        if m["score"] >= float(pol["resolve_min_score"]) and not m["ambiguous"]:
            accept.append((c, m["key"], m["score"], "rule"))
        elif float(lo) <= m["score"] or m["ambiguous"]:
            ask.append((c, m))
    meta: dict[str, Any] = {"by": "rule"}
    if ask and pol.get("llm", True):
        pairs = [{"index": i, "label": c["label"], "raw": c["raw"], "key": m["key"], "via": m["via"], "alternatives": m["ambiguous"]} for i, (c, m) in enumerate(ask[:30])]
        data, meta = ask_json(ctx.session, node.agent_code or "onto_resolver", RESOLVE_TASK, {"pairs": pairs}, workflow_run_id=ctx.run.id, node_run_id=ctx.node_run_id, required=("decisions",), shrink=("pairs",))
        for d in (data or {}).get("decisions") or []:
            if not isinstance(d, dict) or not isinstance(d.get("index"), int) or not 0 <= d["index"] < len(pairs) or d.get("same") is not True:
                continue
            c, m = ask[d["index"]]
            if d.get("key") in {m["key"], *m["ambiguous"]}:
                accept.append((c, d["key"], max(m["score"], 0.86), "llm"))
    for c, key, score, by in accept:
        why = f"'{c['raw']}' → {c['label']} '{key}' (유사도 {score:.2f} · 문서 {c['count']}건{' · ' + ', '.join(c['docs'][:2]) if c['docs'] else ''})"
        _add_op(ctx, {"op": "add_alias", "label": c["label"], "key": key, "aliases": [c["raw"]]}, why, score, by, "alias")
        record(ctx, node.agent_code or "onto_resolver", "alias", why[:300], {"label": c["label"], "raw": c["raw"], "key": key, "score": score, "by": by, "llm": meta if by == "llm" else None})
    return NodeResult({"candidates": len(cands), "accepted": len(accept), "asked": len(ask), "llm": meta.get("by")})


# ═════════════════════════ 5. 품질 검증 ═════════════════════════
@node_impl("check_ontology", "온톨로지 품질 검증 에이전트(규칙) — 스키마 · 범위 · 버려진 관계 · 키 중복 · 다중도 · 후보 적체 · 재추출 대상")
def n_check_ontology(ctx: RunContext, node) -> NodeResult:
    from nhdip.graph.projection import collect_graph
    from nhdip.graph.quality import run_checks

    schema = _schema(ctx)
    if schema is None:
        return NodeResult({"skipped": "활성 스키마 없음"}, "skipped")
    batch = collect_graph(ctx.session, schema)
    rep = run_checks(ctx.session, schema, batch, _rows(ctx))
    ctx.state["onto_quality"] = rep
    record(ctx, node.agent_code or "onto_qa", "quality", f"온톨로지 품질 {'정상' if rep['grade'] == 'ok' else '주의' if rep['grade'] == 'warn' else '위험'} — 점검 {len(rep['checks'])}개 중 문제 {sum(1 for c in rep['checks'] if not c['ok'])}개",
           {"grade": rep["grade"], "checks": [{k: c[k] for k in ("code", "title", "ok", "severity", "detail", "count")} for c in rep["checks"]]})
    if rep["grade"] == "risk":
        from nhdip.alerts import raise_alert
        from nhdip.models import utcnow

        raise_alert(ctx.session, "ontology_quality", "warning", "온톨로지 품질 위험 — [온톨로지 › 구축 파이프라인] 확인", {"checks": [c["code"] for c in rep["checks"] if c["severity"] == "risk"]}, f"ontology_quality:{utcnow():%Y%m%d}")
    return NodeResult(rep, "degraded" if rep["grade"] == "risk" else "succeeded")


# ═════════════════════════ 6. 변경 제안 ═════════════════════════
@node_impl("propose_ontology", "변경 제안 — 앞 단계 연산을 제안으로(대기 중 · 이미 반영된 것 제외), 정책이 허용한 연산만 자동 적용")
def n_propose_ontology(ctx: RunContext, node) -> NodeResult:
    pol = build_policy(ctx.session)
    items = _ops(ctx)
    if not items:
        return NodeResult({"proposals": [], "note": "제안할 변경 없음"})
    made = []
    groups = [("model", "객체 유형 · 링크"), ("alias", "별칭(개체 해소)")]
    for grp, title in groups:
        part = [x for x in items if (x["group"] in ("model", "link")) == (grp == "model")]
        if not part:
            continue
        ops = [x["op"] for x in part]
        ev = {"items": [{k: x[k] for k in ("why", "confidence", "by")} for x in part][:100], "minConfidence": min(x["confidence"] for x in part), "quality": (ctx.state.get("onto_quality") or {}).get("grade")}
        n_cls = sum(1 for o in ops if o["op"] == "add_class")
        n_bk = sum(1 for o in ops if o["op"] == "add_backing")
        n_rel = sum(1 for o in ops if o["op"] == "add_relation")
        n_al = sum(1 for o in ops if o["op"] == "add_alias")
        head = f"구축 에이전트 제안 — {title}"
        summary = " · ".join(x for x in [f"새 객체 유형 {n_cls}" if n_cls else "", f"원천 연결 {n_bk}" if n_bk else "", f"링크 유형 {n_rel}" if n_rel else "", f"별칭 {n_al}" if n_al else ""] if x)
        p = create_proposal(ctx.session, ops, title=f"{head} ({summary})", summary=summary, source="agent", agent_code=node.agent_code or "onto_steward", workflow_run_id=ctx.run.id, evidence=ev)
        if p is None:
            continue
        # 대기 중 제안 · 이미 반영된 연산을 뺀 뒤 남은 것으로 제목을 다시 쓴다
        kept = p.ops or []
        cnt = {k: sum(1 for o in kept if o.get("op") == k) for k in ("add_class", "add_backing", "add_relation", "add_alias", "add_property")}
        summary = " · ".join(x for x in [f"새 객체 유형 {cnt['add_class']}" if cnt["add_class"] else "", f"원천 연결 {cnt['add_backing']}" if cnt["add_backing"] else "",
                                         f"링크 유형 {cnt['add_relation']}" if cnt["add_relation"] else "", f"속성 {cnt['add_property']}" if cnt["add_property"] else "",
                                         f"별칭 {cnt['add_alias']}" if cnt["add_alias"] else ""] if x)
        p.title, p.summary = f"{head} ({summary})"[:200], summary
        res = auto_apply(ctx.session, p, pol)
        made.append({"id": p.id, "status": p.status, "ops": len(p.ops or []), "title": p.title, **({"auto": res} if res else {})})
        record(ctx, node.agent_code or "onto_steward", "proposed", f"제안 #{p.id} {p.title}"[:300], {"proposal": p.id, "status": p.status, "ops": len(p.ops or []), "impact": p.impact, "auto": res})
    return NodeResult({"proposals": made, "ops": len(items)})
