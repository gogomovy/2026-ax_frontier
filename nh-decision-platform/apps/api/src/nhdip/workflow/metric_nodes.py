"""새 지표 제안 (요구사항 §35 MET) — 자료가 올라오면 지표 제안 에이전트가 아직 어떤 지표도 읽지 않는 자료에서 지표 후보를 만든다.

- 후보(결정론): 구조 파악(profile_datasets)이 찾은 측정 열(금액 · 건수 · 수치) × 기준일 열이 있는 자료
  → 최근 기준일 합계(VALUE · q.agg=sum), 기준일이 둘 이상이면 처음 기준일 대비 증가율(GROWTH_RATE)
- 고르기 · 이름(LLM, 없으면 규칙): 업무에 쓸 만한 것만 고르고 한국어 이름 · 이유를 붙인다(숫자 없이)
- 저장: 꺼진 지표(cfg.metric enabled=false, 흐름 wf_data_metrics) — 관리자가 [지표]에서 승인하면 켜지고 계산 커널이 계산한다(값 · 계산 추적 · 이력)
- 같은 코드의 지표가 이미 있으면(제안 · 승인 · 반려 모두) 다시 만들지 않는다
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

from sqlalchemy import select

from nhdip.models import Dataset, Metric, Workflow, WorkflowNode

from .engine import NodeResult, RunContext, node_impl
from .llm_judge import ask_json, clean_reason

WORKFLOW = "wf_data_metrics"
PROPOSED = "[에이전트 제안]"
APPROVED = "[승인]"
REJECTED = "[반려]"
TASK = (
    "자료의 측정 열로 만든 지표 후보 목록이다. 경영 의사결정 화면에서 추적할 만한 것만 고르고(최대 max 개), 후보마다 한국어 지표 이름(label, 20자 이내)과 "
    "추적 이유(reason, 한 문장 · 숫자 금지)를 쓴다. 식별자 · 순번 · 코드값처럼 합계가 의미 없는 열은 고르지 않는다. "
    'JSON: {"picks":[{"code":"…","label":"…","reason":"…"}]}'
)


def _used_codes(ctx: RunContext) -> set[str]:
    """켜진 지표가 이미 읽는 데이터셋 코드(자료 이름 · 코드로 가리킨 것 모두)."""
    from nhdip.data.sources import Resolver
    from nhdip.graph.projection import _datasets_in_args

    res = Resolver(ctx.session)
    out: set[str] = set()
    for m in ctx.session.execute(select(Metric).where(Metric.enabled)).scalars():
        for ref in _datasets_in_args(m.args):
            d = res.resolve(ref)
            if d is not None:
                out.add(d.code)
    return out


def _slug(s: str) -> str:
    return re.sub(r"[^0-9A-Za-z]+", "_", s).strip("_").lower() or "c"


def candidates(ctx: RunContext, profiles: dict[str, dict[str, Any]], per_dataset: int = 3) -> list[dict[str, Any]]:
    used = _used_codes(ctx)
    have = {c for c in ctx.session.execute(select(Metric.code)).scalars()}
    out: list[dict[str, Any]] = []
    for code, prof in profiles.items():
        ds = ctx.session.get(Dataset, code)
        if ds is None or not ds.as_of_column or code in used:
            continue
        cols = prof.get("columns") or {}
        periods = int((cols.get(ds.as_of_column) or {}).get("distinct") or 1)
        n = 0
        for col in prof.get("measures") or []:
            c = cols.get(col) or {}
            if col == ds.as_of_column or c.get("semantic") not in ("amount", "count", "number") or c.get("keyCandidate"):
                continue
            label = c.get("label") or col
            unit = "CNT" if c.get("semantic") == "count" else "NONE"
            base = f"auto_{_slug(code)[:40]}_{hashlib.sha1(col.encode()).hexdigest()[:6]}"  # 같은 자료 · 열이면 같은 코드(다시 제안하지 않게)
            q1 = {"dataset": ds.code, "col": col, "agg": "sum", "where": {ds.as_of_column: "$latest"}}
            items = [{"code": f"{base}_sum"[:80], "label": f"{label} 합계", "formula": "VALUE", "unit": unit, "decimals": 0,
                      "args": {"value": {"q": q1, "label": f"{label} 합계(최근 기준일)"}}, "dataset": ds.name, "column": col, "kind": "합계"}]
            if periods >= 2:
                q0 = {**q1, "where": {ds.as_of_column: "$earliest"}}
                items.append({"code": f"{base}_growth"[:80], "label": f"{label} 증가율", "formula": "GROWTH_RATE", "unit": "PCT", "decimals": 2,
                              "args": {"v0": {"q": q0, "label": f"{label} 합계(처음 기준일)"}, "v1": {"q": q1, "label": f"{label} 합계(최근 기준일)"}}, "dataset": ds.name, "column": col, "kind": "증가율"})
            for it in items:
                if it["code"] not in have:
                    out.append(it)
            n += 1
            if n >= per_dataset:
                break
    return out


def ensure_workflow(session) -> None:
    """제안 지표를 계산하는 공통 흐름 — 자료 입력 고정 → 지표 계산(산출물 없음 · 값은 calc · 지표 이력)."""
    if session.get(Workflow, WORKFLOW) is not None:
        return
    session.add(Workflow(code=WORKFLOW, name="데이터 지표(에이전트 제안)", description="지표 제안 에이전트가 만들고 관리자가 승인한 지표를 계산 커널로 계산", outputs=[], sort=7, enabled=True))
    session.flush()
    for i, (key, name, impl) in enumerate((("load_inputs", "입력 고정", "load_inputs"), ("compute", "지표 계산", "compute_metrics")), start=1):
        session.add(WorkflowNode(workflow_code=WORKFLOW, seq=i * 10, key=key, name=name, impl=impl, agent_code=None, enabled=True, config={}))
    session.flush()


@node_impl("propose_metrics", "지표 제안 에이전트 — 지표가 없는 자료의 측정 열로 지표 후보(합계 · 증가율)를 만들고 LLM 이 골라 이름을 붙인다(없으면 규칙) → 관리자 승인 대기")
def n_propose_metrics(ctx: RunContext, node: WorkflowNode) -> NodeResult:
    from .agent_nodes import record

    cfg = node.config or {}
    profiles = ctx.state.get("onto_profiles") or {}
    if not profiles:
        return NodeResult({"skipped": "구조 파악 결과 없음"})
    cands = candidates(ctx, profiles, int(cfg.get("per_dataset", 3)))
    if not cands:
        return NodeResult({"proposed": 0, "note": "새 자료의 측정 열이 없거나 이미 지표가 있음"})
    mx = int(cfg.get("max", 6))
    picks: dict[str, dict[str, Any]] = {}
    data, meta = ask_json(ctx.session, node.agent_code or "metric_proposer", TASK,
                          {"max": mx, "candidates": [{k: c[k] for k in ("code", "label", "kind", "dataset", "column")} for c in cands]},
                          workflow_run_id=ctx.run.id, node_run_id=ctx.node_run_id, required=("picks",), shrink=("candidates",))
    if data:
        allowed = {c["code"] for c in cands}
        for p in data.get("picks") or []:
            if isinstance(p, dict) and p.get("code") in allowed and p["code"] not in picks:
                label, _ = clean_reason(p.get("label"), 40)
                reason, _ = clean_reason(p.get("reason"), 160)
                picks[p["code"]] = {"label": label, "reason": reason, "by": "llm"}
    else:
        for c in cands[:mx]:
            picks[c["code"]] = {"label": None, "reason": f"{c['dataset']} 의 {c['column']} 열 — 아직 이 자료를 읽는 지표가 없음", "by": "rule"}
    ensure_workflow(ctx.session)
    made = []
    for c in cands:
        p = picks.get(c["code"])
        if p is None or len(made) >= mx:
            continue
        ctx.session.add(Metric(code=c["code"], label=(p["label"] or c["label"])[:150], formula=c["formula"], args=c["args"], unit=c["unit"], decimals=c["decimals"],
                               workflow_code=WORKFLOW, figure_ids=[c["code"]], enabled=False, sort=900,
                               description=f"{PROPOSED} {p['reason']} (자료 {c['dataset']} · 열 {c['column']} · {c['kind']} · {p['by']})"[:900]))
        made.append(c["code"])
    ctx.session.flush()
    if made:
        record(ctx, node.agent_code or "metric_proposer", "metric_proposed", f"새 지표 {len(made)}개 제안 — 관리자 승인 대기", {"metrics": made, "by": "llm" if data else "rule", "llm": meta})
    return NodeResult({"proposed": made, "candidates": len(cands), "by": "llm" if data else "rule"})
