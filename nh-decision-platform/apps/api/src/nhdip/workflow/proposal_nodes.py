"""새 자료에 대한 에이전트 제안 (요구사항 §40 STW) — 온톨로지 구축 흐름(wf_ontology_build) 끝에서, 구조 파악 결과로 돈다.

  propose_concepts  개념 연결 에이전트 concept_linker    자료 이름 · 설명 · 열 이름 · 열 의미 · 묶음 열 값 → 기존 업무 개념(kind=concept: 정책 주제 · 상품군 ·
                                                         세그먼트 · 사업부문 …) 후보(결정론: 온톨로지 별칭 사전) → LLM 이 '이 자료가 그 개념에 관한 것인가'를
                                                         고르고 사유를 쓴다(없으면 규칙 점수) → 자료 정의의 개념 연결 제안(mapping.proposed_concepts)
  propose_analysis  분석 제안 에이전트 analysis_proposer  아직 아무 지표 · 분석도 읽지 않는 자료 → 측정 열 · 묶음 열 · 기준일로 분석 명세 초안(결정론 —
                                                         기준일이 둘 이상이면 직전 보관 기준일($prev) 대비 비교) → LLM 이 열을 고르고 제목 · 목적 · 의견 지시
                                                         (없으면 규칙) → 명세 검증 · 미리보기 → 분석 요청(승인 대기)

어느 것도 승인 전에는 계산 · 화면 · 그래프에 나가지 않는다. 승인은 자료를 소유한 부서의 데이터 책임자 또는 관리자(nhdip.stewardship).
같은 자료 · 같은 개념은 다시 제안하지 않는다(반려 · 에이전트가 관련 없다고 본 것 포함). 열 이름 · 값 · 단위는 자료에서 오고 코드에 고정된 업무 값은 없다.
"""
from __future__ import annotations

import copy
import re
from typing import Any

from sqlalchemy import select

from nhdip.models import AnalysisAgentVersion, Dataset, WorkflowNode, utcnow

from .engine import NodeResult, RunContext, node_impl
from .llm_judge import ask_json, clean_reason

_TOKEN = re.compile(r"[0-9A-Za-z가-힣]+")
_TOTAL = re.compile(r"(합계|소계|총계|total)", re.I)
_GRAND = re.compile(r"(합계|소계|총계|전체|total)", re.I)
_REMAINDER = re.compile(r"(기타|그\s*외|others?|etc)", re.I)
# 근거 출처별 가중치 — 자료 이름이 그 개념을 말하면 가장 강하고, 열 의미(에이전트가 붙인 말)는 약하다
WEIGHTS = {"name": 0.95, "description": 0.8, "column": 0.75, "value": 0.7, "meaning": 0.6}
WHERE_KO = {"name": "자료 이름", "description": "자료 설명", "column": "열 이름", "value": "열 값", "meaning": "열 의미"}


def _norm(s: Any) -> str:
    return re.sub(r"\s+", "", str(s or "")).lower()


# ═════════════════════════ 개념 연결 ═════════════════════════
def concept_candidates(classes: list[dict[str, Any]], aliases: dict[str, dict[str, list[str]]], texts: list[tuple[str, str, str]],
                       values: dict[str, list[str]], *, min_score: float = 0.6, limit: int = 6) -> list[dict[str, Any]]:
    """별칭 사전(개념 종류 → 대표 키 → [별칭])으로 자료가 가리키는 업무 개념 후보와 근거를 모은다 — 결정론.

    texts  [(글, 출처 종류 name|description|column|meaning, 출처 이름)]
    values {열 이름: [값 …]} — 묶음 열의 자주 나오는 값
    두 글자 별칭은 낱말이 같을 때만(예: '외감' 이 '비외감' 에 걸리지 않게), 세 글자 이상은 글 안에 들어 있으면 맞는 것으로 본다.
    """
    concept = {c["label"] for c in classes if isinstance(c, dict) and c.get("kind") == "concept"}
    found: dict[tuple[str, str], dict[str, Any]] = {}

    def add(label: str, key: str, score: float, ev: str) -> None:
        cur = found.setdefault((label, key), {"label": label, "key": key, "score": 0.0, "evidence": []})
        cur["score"] = max(cur["score"], score)
        if ev not in cur["evidence"]:
            cur["evidence"].append(ev)

    prepared = [(_norm(t), {_norm(x) for x in _TOKEN.findall(str(t or ""))}, kind, where) for t, kind, where in texts if t]
    vals = {col: {_norm(v): str(v) for v in vs if str(v or "").strip()} for col, vs in values.items()}
    for label, entries in (aliases or {}).items():
        if label not in concept or not isinstance(entries, dict):
            continue
        for key, als in entries.items():
            names = [a for a in dict.fromkeys([key, *(als or [])]) if _norm(a)]
            normed = {_norm(a): a for a in names}
            for t, toks, kind, where in prepared:
                hit = next((a for na, a in normed.items() if na in toks or (len(na) >= 3 and na in t)), None)
                if hit:
                    add(label, key, WEIGHTS[kind], f"{WHERE_KO[kind]}{f' {where}' if where else ''}에 '{hit}'")
            for col, vm in vals.items():
                hits = [vm[n] for n in normed if n in vm]
                if hits:
                    add(label, key, WEIGHTS["value"], f"열 '{col}' 값에 '{hits[0]}'")
    out = [c for c in found.values() if c["score"] >= min_score]
    for c in out:
        # 근거가 여러 출처에서 겹치면 조금 더 믿는다(상한 1)
        c["score"] = round(min(1.0, c["score"] + 0.05 * (len(c["evidence"]) - 1)), 3)
    out.sort(key=lambda c: (-c["score"], c["label"], c["key"]))
    return out[:limit]


CONCEPT_TASK = (
    "자료마다 그 자료가 어떤 업무 개념에 관한 것인지 고른다. 후보(개념 종류 label · 대표 키 key · 근거 evidence) 가운데 이 자료가 실제로 그 개념을 다루는 것만 "
    "picks 에 넣고 사유(reason, 한 문장 · 숫자 금지)를 쓴다. 이름이 우연히 겹친 것뿐이면 고르지 않는다. 후보에 없는 개념을 만들지 않는다. "
    'JSON: {"picks":[{"dataset":"…","label":"…","key":"…","reason":"…"}]}'
)


def _profile_texts(ds: Dataset, prof: dict[str, Any], sem: dict[str, Any] | None) -> tuple[list[tuple[str, str, str]], dict[str, list[str]]]:
    cols = prof.get("columns") or {}
    meanings = ((sem or {}).get("columns") or {}) if isinstance(sem, dict) else {}
    texts: list[tuple[str, str, str]] = [(ds.name, "name", ""), (ds.description or "", "description", "")]
    values: dict[str, list[str]] = {}
    for name, c in cols.items():
        if c.get("pii"):
            continue
        texts.append((str(c.get("label") or name), "column", f"'{c.get('label') or name}'"))
        mean = (meanings.get(name) or {}).get("meaning") if isinstance(meanings.get(name), dict) else None
        if mean:
            texts.append((str(mean), "meaning", f"'{c.get('label') or name}'"))
        if c.get("semantic") in ("code", "name") and name != prof.get("asOfColumn"):
            values[str(c.get("label") or name)] = [str(t.get("value")) for t in c.get("top") or [] if isinstance(t, dict)]
    return texts, values


@node_impl("propose_concepts", "개념 연결 에이전트 — 자료 이름 · 열 · 값을 온톨로지 별칭 사전과 맞춰 업무 개념 후보를 찾고(결정론) LLM 이 관련 있는 것만 골라 사유를 붙인다 → 데이터 책임자 승인 대기")
def n_propose_concepts(ctx: RunContext, node: WorkflowNode) -> NodeResult:
    from nhdip.data.sources import Resolver
    from nhdip.graph import profile as P
    from nhdip.graph.projection import active_schema
    from nhdip.stewardship import PROPOSED_CONCEPTS, REJECTED_CONCEPTS, SKIPPED_CONCEPTS

    from .agent_nodes import record

    cfg = node.config or {}
    profiles = ctx.state.get("onto_profiles") or {}
    sc = active_schema(ctx.session)
    if not profiles or sc is None:
        return NodeResult({"skipped": "구조 파악 결과 또는 활성 온톨로지 없음"})
    res = Resolver(ctx.session)
    min_score, limit = float(cfg.get("min_score", 0.6)), int(cfg.get("per_dataset", 6))
    work: list[tuple[Dataset, list[dict[str, Any]], str | None]] = []
    for code in _ordered(ctx, profiles):
        ds = ctx.session.get(Dataset, code)
        if ds is None or not ds.active:
            continue
        if any((m.get("concepts") or m.get("nodes")) for m in res.mappings_for(code)):
            continue  # 업무 구성이 개념 연결을 정해 둔 자료 — 에이전트가 덧붙이지 않는다
        m = ds.mapping or {}
        taken = {(c.get("label"), c.get("key")) for k in ("concepts", PROPOSED_CONCEPTS, REJECTED_CONCEPTS, SKIPPED_CONCEPTS) for c in m.get(k) or [] if isinstance(c, dict)}
        lp = P.latest_profile(ctx.session, code)
        texts, values = _profile_texts(ds, profiles[code], lp.semantics if lp is not None else None)
        cands = [c for c in concept_candidates(sc.classes or [], sc.aliases or {}, texts, values, min_score=min_score, limit=limit) if (c["label"], c["key"]) not in taken]
        if cands:
            work.append((ds, cands, ((lp.semantics or {}).get("summary") if lp is not None else None)))
    if not work:
        return NodeResult({"proposed": 0, "note": "새 개념 후보 없음"})
    max_ds = int(cfg.get("max_datasets", 6))
    work = work[:max_ds]
    ko = {c["label"]: c.get("ko") or c["label"] for c in sc.classes or []}
    data, meta = ask_json(ctx.session, node.agent_code or "concept_linker", CONCEPT_TASK,
                          {"datasets": [{"dataset": ds.code, "name": ds.name, "summary": summary, "candidates": [{"label": c["label"], "labelKo": ko.get(c["label"]), "key": c["key"], "evidence": c["evidence"][:3]} for c in cands]}
                                        for ds, cands, summary in work]},
                          workflow_run_id=ctx.run.id, node_run_id=ctx.node_run_id, required=("picks",), shrink=("datasets",))
    picks: dict[tuple[str, str, str], str] = {}
    # 입력 글자 상한으로 뒤쪽 자료를 덜어 냈으면(LLM 이 보지 못한 자료) 이번에는 판단하지 않고 다음 실행에 다시 묻는다
    trimmed = int(((meta or {}).get("contextTrimmed") or {}).get("datasets", 0) or 0) if data else 0
    judged = {ds.code for ds, _, _ in work[: len(work) - trimmed]} if data else {ds.code for ds, _, _ in work}
    if data:
        allowed = {(ds.code, c["label"], c["key"]) for ds, cands, _ in work for c in cands}
        for p in data.get("picks") or []:
            if isinstance(p, dict) and (p.get("dataset"), p.get("label"), p.get("key")) in allowed:
                reason, _ = clean_reason(p.get("reason"), 160)
                picks[(p["dataset"], p["label"], p["key"])] = reason
    rule_min = float(cfg.get("rule_min_score", 0.7))
    now = utcnow().isoformat()
    made: list[dict[str, Any]] = []
    for ds, cands, _ in work:
        if ds.code not in judged:
            continue
        # 승인함에서 같은 자료를 동시에 승인 · 반려할 수 있다 — 잠그고 다시 읽은 정의에 더한다(덮어써 결정을 잃지 않게 · 노드가 끝나면 커밋으로 풀린다)
        fresh = ctx.session.get(Dataset, ds.code, with_for_update=True, populate_existing=True)
        if fresh is None:
            continue
        m = copy.deepcopy(fresh.mapping or {})
        taken = {(c.get("label"), c.get("key")) for k in ("concepts", PROPOSED_CONCEPTS, REJECTED_CONCEPTS, SKIPPED_CONCEPTS) for c in m.get(k) or [] if isinstance(c, dict)}
        cands = [c for c in cands if (c["label"], c["key"]) not in taken]
        props = list(m.get(PROPOSED_CONCEPTS) or [])
        skipped = list(m.get(SKIPPED_CONCEPTS) or [])
        for c in cands:
            if data:
                reason = picks.get((ds.code, c["label"], c["key"]))
                keep, by = (ds.code, c["label"], c["key"]) in picks, "llm"
            else:
                keep, by, reason = c["score"] >= rule_min, "rule", None
            entry = {"label": c["label"], "key": c["key"], "name": c["key"], "score": c["score"], "evidence": c["evidence"][:5], "by": by, "at": now,
                     "reason": reason or ("근거: " + " · ".join(c["evidence"][:2]))}
            if keep:
                props.append(entry)
                made.append({"dataset": ds.code, "label": c["label"], "key": c["key"], "score": c["score"], "by": by})
            elif data:
                # LLM 이 관련 없다고 본 후보만 기억한다(같은 후보로 매번 묻지 않게). 규칙 점수 미달은 기억하지 않는다 — LLM 이 연결되면 다시 판단
                skipped.append({**entry, "reason": "에이전트가 관련 없다고 판단"})
        if props == list(m.get(PROPOSED_CONCEPTS) or []) and skipped == list(m.get(SKIPPED_CONCEPTS) or []):
            continue  # 바뀐 것 없음 — 정의를 다시 쓰지 않는다
        m[PROPOSED_CONCEPTS] = props
        m[SKIPPED_CONCEPTS] = skipped[-200:]
        fresh.mapping = m
    ctx.session.flush()
    if made:
        record(ctx, node.agent_code or "concept_linker", "concept_proposed", f"개념 연결 {len(made)}건 제안 — 데이터 책임자 승인 대기", {"items": made, "by": "llm" if data else "rule", "llm": meta})
    return NodeResult({"proposed": made, "datasets": len(work), "by": "llm" if data else "rule"})


# ═════════════════════════ 분석 제안 ═════════════════════════
MEASURE_ORDER = {"amount": 0, "count": 1, "number": 2, "rate": 3}


def usable_measures(prof: dict[str, Any]) -> list[str]:
    cols = prof.get("columns") or {}
    asof = prof.get("asOfColumn")
    out = [c for c in prof.get("measures") or [] if c != asof and c in cols and not cols[c].get("keyCandidate") and not cols[c].get("pii") and float(cols[c].get("nullRate") or 0) < 0.9]
    return sorted(out, key=lambda c: (MEASURE_ORDER.get(cols[c].get("semantic"), 9), float(cols[c].get("nullRate") or 0)))


def usable_dimensions(prof: dict[str, Any], max_distinct: int = 200) -> list[str]:
    cols = prof.get("columns") or {}
    asof = prof.get("asOfColumn")
    out = [c for c in prof.get("dimensions") or [] if c != asof and c in cols and cols[c].get("semantic") in ("code", "name") and not cols[c].get("pii")
           and not cols[c].get("keyCandidate") and 2 <= int(cols[c].get("distinct") or 0) <= max_distinct and float(cols[c].get("nullRate") or 0) < 0.5]
    return sorted(out, key=lambda c: int(cols[c].get("distinct") or 0))


def auto_spec(ds: dict[str, Any], prof: dict[str, Any], sem: dict[str, Any] | None = None, *, measures: list[str] | None = None, dimensions: list[str] | None = None,
              max_measures: int = 4, max_tables: int = 2, agg_rows: dict[str, list[str]] | None = None, naming: dict[str, str] | None = None) -> dict[str, Any]:
    """자료 하나의 분석 명세 초안(결정론) — 열 이름 · 의미 · 기준일 수는 모두 구조 파악 결과에서 온다.

    기준일 열이 있고 보관 기준일이 둘 이상이면 각 측정 열을 최신 기준일($latest)과 직전 보관 기준일($prev)로 나눠 계산하고
    증감률(금액 · 건수 · 수치) · 증감(비율)을 더한다 — 올린 기준일이 월마다 이어지지 않아도(예: 1월 · 8월) 두 판을 견준다.
    합계 행 표시 열은 거짓만, 묶음 열의 합계 · 기타 행(agg_rows)은 빼고 더한다(두 번 세지 않게).
    """
    cols = prof.get("columns") or {}
    meanings = ((sem or {}).get("columns") or {}) if isinstance(sem, dict) else {}
    code, name = ds["code"], ds.get("name") or ds["code"]
    asof = ds.get("as_of_column") or prof.get("asOfColumn")
    periods = int((cols.get(asof) or {}).get("distinct") or 0) if asof else 0
    compare = bool(asof) and periods >= 2
    ms = [c for c in (measures if measures is not None else usable_measures(prof)) if c in cols][:max_measures]
    dims = [c for c in (dimensions if dimensions is not None else usable_dimensions(prof)) if c in cols][:max_tables]
    base: dict[str, Any] = {}
    flag = next((c for c, v in cols.items() if v.get("semantic") == "flag" and _TOTAL.search(f"{c} {v.get('label') or ''}")), None)
    if flag:
        base[flag] = False
    for col, vals in (agg_rows or {}).items():
        if vals and col in cols:
            base[col] = {"nin": list(vals)[:20]}

    def where(token: str | None) -> dict[str, Any]:
        return {**base, **({asof: token} if asof and token else {})}

    def label(c: str) -> str:
        return str(cols[c].get("label") or c)[:40]

    metrics: list[dict[str, Any]] = []
    now_keys: list[str] = []
    prev_keys: list[str] = []
    chg_keys: list[str] = []
    for i, c in enumerate(ms, start=1):
        sm = cols[c].get("semantic")
        f = "MEAN" if sm == "rate" else "SUM"
        mx = cols[c].get("max")
        small = isinstance(mx, (int, float)) and not isinstance(mx, bool) and abs(mx) < 100
        unit, dec = ("CNT", 0) if sm == "count" else ("NONE", 2 if sm == "rate" or small else 0)
        agg_ko = "평균" if f == "MEAN" else "합계"
        now = {"key": f"m{i}_now", "label": f"{label(c)} {agg_ko}" + ("(최근 기준일)" if compare else ""), "formula": f, "unit": unit, "decimals": dec,
               "args": {"values": {"q": {"dataset": code, "col": c, "agg": "list", "where": where("$latest")}, "label": f"{label(c)}(최근 기준일)"}}}
        metrics.append(now)
        now_keys.append(now["key"])
        if compare:
            metrics.append({"key": f"m{i}_prev", "label": f"{label(c)} {agg_ko}(직전 기준일)", "formula": f, "unit": unit, "decimals": dec,
                            "args": {"values": {"q": {"dataset": code, "col": c, "agg": "list", "where": where("$prev")}, "label": f"{label(c)}(직전 기준일)"}}})
            prev_keys.append(f"m{i}_prev")
            if sm == "rate":
                metrics.append({"key": f"m{i}_chg", "label": f"{label(c)} 증감(직전 기준일 대비)", "formula": "DIFF", "unit": "NONE", "decimals": 2,
                                "args": {"a": {"metric": f"m{i}_now"}, "b": {"metric": f"m{i}_prev"}}})
            else:
                metrics.append({"key": f"m{i}_chg", "label": f"{label(c)} 증감률(직전 기준일 대비)", "formula": "GROWTH_RATE", "unit": "PCT", "decimals": 2,
                                "args": {"v0": {"metric": f"m{i}_prev"}, "v1": {"metric": f"m{i}_now"}}})
            chg_keys.append(f"m{i}_chg")
    metrics.append({"key": "rows_now", "label": f"{name} 건수" + ("(최근 기준일)" if compare else ""), "formula": "VALUE", "unit": "CNT", "decimals": 0,
                    "args": {"value": {"q": {"dataset": code, "agg": "count", "where": where("$latest")}, "label": "행 수"}}})
    now_keys.append("rows_now")
    if compare:
        metrics.append({"key": "rows_prev", "label": f"{name} 건수(직전 기준일)", "formula": "VALUE", "unit": "CNT", "decimals": 0,
                        "args": {"value": {"q": {"dataset": code, "agg": "count", "where": where("$prev")}, "label": "행 수(직전 기준일)"}}})
        metrics.append({"key": "rows_chg", "label": f"{name} 건수 증감률", "formula": "GROWTH_RATE", "unit": "PCT", "decimals": 2,
                        "args": {"v0": {"metric": "rows_prev"}, "v1": {"metric": "rows_now"}}})
        prev_keys.append("rows_prev")
        chg_keys.append("rows_chg")
    tables: list[dict[str, Any]] = []
    sections: list[dict[str, Any]] = [{"heading": "핵심 지표", "blocks": [{"type": "metrics", "metrics": now_keys[:12]}]}]
    if compare:
        sections.append({"heading": "직전 기준일 대비", "blocks": [{"type": "metrics", "metrics": chg_keys[:12]}, {"type": "metrics", "metrics": prev_keys[:12]}]})
    if ms:
        val = ms[0]
        for j, g in enumerate(dims, start=1):
            cap = f"{label(g)}별 {label(val)}" + ("(최근 기준일)" if compare else "")
            tables.append({"key": f"t{j}", "caption": cap[:80], "dataset": code, "where": where("$latest"), "group_by": g, "value": val,
                           "agg": "mean" if cols[val].get("semantic") == "rate" else "sum", "top": 10})
            sections.append({"heading": cap[:60], "blocks": [{"type": "table", "table": f"t{j}"}, {"type": "chart", "table": f"t{j}", "kind": "bar"}]})
    summary = str((sem or {}).get("summary") or "").strip() if isinstance(sem, dict) else ""
    naming = naming or {}
    mean_txt = ", ".join(f"{label(c)}({(meanings.get(c) or {}).get('meaning')})" if isinstance(meanings.get(c), dict) and (meanings.get(c) or {}).get("meaning") else label(c) for c in [*ms, *dims])
    instruction = naming.get("instruction") or (
        "최근 기준일과 직전 기준일을 견주어 변화가 큰 항목과 그 업무상 의미를 근거 문서와 함께 쓴다." if compare else "최근 기준일의 규모와 구성에서 눈에 띄는 점과 그 업무상 의미를 근거 문서와 함께 쓴다.")
    title = (naming.get("title") or f"{name} 분석")[:60]
    return {
        "title": title,
        "purpose": (naming.get("purpose") or summary or f"새로 올라온 '{name}' 자료를 에이전트가 살펴 만든 분석")[:300],
        "domain_knowledge": f"자료: {name}. 열: {mean_txt}."[:2000] + (f" 요약: {summary}" if summary else ""),
        "task": instruction,
        "metrics": metrics,
        "tables": tables,
        "sections": sections,
        "insights": [{"key": "main", "title": title, "metrics": (chg_keys or now_keys)[:6], "instruction": instruction}],
        "evidence": {"query": f"{name} {summary}".strip()[:200]},
        "schedule": {"cron": None, "on_data_change": True},
    }


ANALYSIS_TASK = (
    "새로 올라온 자료로 에이전트가 만든 분석 초안이다. 측정 열 후보(measures)와 묶음 열 후보(dimensions) 가운데 업무 화면에서 볼 만한 것을 고르고"
    "(measures 최대 max_measures 개, dimensions 최대 max_tables 개 — 후보의 name 만), 탭 제목(title, 20자 이내), 목적(purpose, 한 문장), "
    "의견 작성 지시(instruction, 두 문장 이내)를 쓴다. 식별자 · 순번 · 코드값처럼 합계가 의미 없는 열은 고르지 않는다. 숫자를 쓰지 않는다. "
    'JSON: {"measures":["…"],"dimensions":["…"],"title":"…","purpose":"…","instruction":"…"}'
)


def _ordered(ctx: RunContext, profiles: dict[str, Any]) -> list[str]:
    """이번 실행을 깨운 자료(방금 올라온 자료)를 먼저, 나머지는 코드 순 — 실행당 상한에 새 자료가 밀리지 않게."""
    from .onto_nodes import _cause_datasets

    first = [c for c in _cause_datasets(ctx) if c in profiles]
    return first + sorted(c for c in profiles if c not in first)


def _auto_seen(session) -> set[str]:
    """이미 자동 분석을 제안한 자료(승인 · 반려 · 대기 모두) — 다시 제안하지 않는다."""
    out: set[str] = set()
    for spec in session.execute(select(AnalysisAgentVersion.spec)).scalars():
        d = ((spec or {}).get("auto") or {}).get("dataset") if isinstance(spec, dict) else None
        if d:
            out.add(str(d))
    return out


def _pending_inputs(session) -> set[str]:
    """승인 대기 중인 분석 요청(사용자 · 에이전트)이 읽는 자료."""
    from nhdip.analysis_agents.spec import input_datasets

    out: set[str] = set()
    for spec in session.execute(select(AnalysisAgentVersion.spec).where(AnalysisAgentVersion.status == "pending")).scalars():
        if isinstance(spec, dict):
            out |= set(input_datasets(spec))
    return out


@node_impl("propose_analysis", "분석 제안 에이전트 — 아직 아무 분석도 읽지 않는 새 자료로 분석 명세 초안(측정 · 묶음 열 · 직전 기준일 대비)을 만들고 LLM 이 열을 고르고 이름을 붙인다(없으면 규칙) → 검증 · 미리보기 → 데이터 책임자 승인 대기")
def n_propose_analysis(ctx: RunContext, node: WorkflowNode) -> NodeResult:
    from nhdip.analysis_agents.lifecycle import LifecycleError, preview, request
    from nhdip.analysis_agents.spec import aggregate_values, validate_spec
    from nhdip.data.datasets import current_versions
    from nhdip.graph import profile as P
    from nhdip.stewardship import AUTO_ACTOR, auto_policy, owner_org_of, pick_space

    from .agent_nodes import record
    from .metric_nodes import _used_codes

    cfg = node.config or {}
    pol = {**auto_policy(ctx.session), **{k: v for k, v in cfg.items() if k in ("max_per_run", "max_measures", "max_tables", "llm", "preview")}}
    if not pol.get("enabled", True):
        return NodeResult({"skipped": "설정 analysis.auto.enabled 꺼짐"})
    profiles = ctx.state.get("onto_profiles") or {}
    if not profiles:
        return NodeResult({"skipped": "구조 파악 결과 없음"})
    used, seen, pending = _used_codes(ctx), _auto_seen(ctx.session), _pending_inputs(ctx.session)
    max_runs, max_m, max_t = int(pol.get("max_per_run", 2)), int(pol.get("max_measures", 4)), int(pol.get("max_tables", 2))
    made, skipped = [], []
    for code in _ordered(ctx, profiles):
        if len(made) >= max_runs:
            break
        ds = ctx.session.get(Dataset, code)
        if ds is None or not ds.active or code in used or code in seen or code in pending or not current_versions(ctx.session, ds):
            continue
        prof = {**profiles[code], "asOfColumn": ds.as_of_column or (profiles[code] or {}).get("asOfColumn")}
        measures = usable_measures(prof)
        if not measures:
            skipped.append({"dataset": code, "reason": "측정 열 없음"})
            continue
        owner = owner_org_of(ctx.session, ds)
        space = pick_space(ctx.session, owner)
        if space is None:
            skipped.append({"dataset": code, "reason": "자료를 올린 팀이 볼 수 있는 분석 공간이 없음"})
            continue
        dims = usable_dimensions(prof)
        lp = P.latest_profile(ctx.session, code)
        sem = lp.semantics if lp is not None else None
        cols = prof.get("columns") or {}
        naming: dict[str, str] = {}
        pick_m, pick_d, by, meta = measures, dims, "rule", {"by": "rule"}
        if pol.get("llm", True):
            ctx_llm = {"dataset": {"code": code, "name": ds.name, "description": (ds.description or "")[:300], "summary": (sem or {}).get("summary") if isinstance(sem, dict) else None,
                                   "periods": int((cols.get(ds.as_of_column) or {}).get("distinct") or 0) if ds.as_of_column else 0},
                       "measures": [{"name": c, "label": cols[c].get("label"), "semantic": cols[c].get("semanticKo")} for c in measures[:12]],
                       "dimensions": [{"name": c, "label": cols[c].get("label"), "distinct": cols[c].get("distinct")} for c in dims[:12]],
                       "max_measures": max_m, "max_tables": max_t}
            data, meta = ask_json(ctx.session, node.agent_code or "analysis_proposer", ANALYSIS_TASK, ctx_llm, workflow_run_id=ctx.run.id, node_run_id=ctx.node_run_id,
                                  required=("measures",), shrink=("measures", "dimensions"))
            if data:
                lm = [c for c in data.get("measures") or [] if isinstance(c, str) and c in measures]
                ld = [c for c in data.get("dimensions") or [] if isinstance(c, str) and c in dims]
                if lm:
                    pick_m, pick_d, by = lm, ld, "llm"
                for k, lim in (("title", 30), ("purpose", 160), ("instruction", 300)):
                    txt, _ = clean_reason(data.get(k), lim)
                    if txt:
                        naming[k] = txt
        # 합계 · 소계 행은 상세의 합이라 더하면 두 번 센다 — 뺀다. '기타 · 그 외' 행은 상세의 나머지라 남긴다(analysis_agents.spec 의 합계 규칙과 같음)
        agg = {}
        for g in pick_d[:max_t]:
            vals = [x for x in aggregate_values(ctx.session, ds, g) if _GRAND.search(x) and not _REMAINDER.search(x)]
            if vals:
                agg[g] = vals
        raw = auto_spec({"code": code, "name": ds.name, "as_of_column": ds.as_of_column}, prof, sem, measures=pick_m, dimensions=pick_d,
                        max_measures=max_m, max_tables=max_t, agg_rows=agg, naming=naming)
        spec, validation = validate_spec(ctx.session, raw, space)
        if not validation.get("ok"):
            skipped.append({"dataset": code, "reason": "명세 검증 실패", "issues": [i.get("message") for i in validation.get("issues") or []][:5]})
            continue
        periods = int((cols.get(ds.as_of_column) or {}).get("distinct") or 0) if ds.as_of_column else 0
        spec["auto"] = {"dataset": code, "datasetName": ds.name, "ownerOrg": owner, "by": by, "at": utcnow().isoformat(), "periods": periods,
                        "measures": pick_m[:max_m], "dimensions": pick_d[:max_t], "run": ctx.run.id}
        pv = None
        if pol.get("preview", True):
            try:
                pv = preview(ctx.session, spec, space, AUTO_ACTOR)
            except Exception as exc:  # noqa: BLE001 — 미리보기 실패가 제안을 막지 않는다(승인 뒤 실행에서 계산)
                pv = None
                meta = {**meta, "previewError": f"{type(exc).__name__}: {str(exc)[:160]}"}
        text = (f"[에이전트 제안] '{ds.name}' 자료가 올라왔고 아직 이 자료를 읽는 지표 · 분석이 없어 분석 화면을 제안합니다. "
                f"측정 열: {', '.join(str(cols[c].get('label') or c) for c in pick_m[:max_m])}"
                + (f" · 묶음 열: {', '.join(str(cols[c].get('label') or c) for c in pick_d[:max_t])}" if pick_d else "")
                + (f" · 보관 기준일 {periods}개 — 직전 기준일 대비 비교 포함" if periods >= 2 else ""))
        try:
            v = request(ctx.session, space=space, text=text, spec=spec, validation=validation, preview=pv, actor=AUTO_ACTOR)
        except LifecycleError as exc:
            skipped.append({"dataset": code, "reason": str(exc)[:200]})
            continue
        made.append({"dataset": code, "agent": v.agent_code, "version": v.version, "space": space, "owner": owner, "metrics": validation["counts"]["metrics"], "by": by})
        seen.add(code)
    ctx.session.flush()
    if made:
        record(ctx, node.agent_code or "analysis_proposer", "analysis_proposed", f"분석 화면 {len(made)}건 제안 — 데이터 책임자 승인 대기", {"items": made, "skipped": skipped[:20]})
    return NodeResult({"proposed": made, "skipped": skipped[:20]})
