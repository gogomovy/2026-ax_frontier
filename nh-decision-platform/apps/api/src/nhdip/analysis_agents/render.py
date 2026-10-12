"""③ 범용 렌더링 에이전트 (`report_renderer`, 결정론 · Phase C · DAG-06 · Q103).

명세 구성(섹션 · 블록) + 커널 계산 결과(지표) + 집계표 + 판단(심각도 · 의견)으로 표준 보고서 산출물(ReportDoc)을 조립한다.
기존 분석 보고서와 같은 형식(목차 · 의견 · 본문 블록 · 근거 · 한계)이라 같은 화면 · 내려받기를 쓴다. LLM 을 부르지 않는다.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from nhdip.calc import formulas
from nhdip.calc.metrics import EvalContext, MetricOutcome, ResolveError, _match, resolve_where

from .spec import SEVERITIES, UNIT_LABELS, figure_id, insight_id, metric_code

SEV_RANK = {s: i for i, s in enumerate(SEVERITIES)}


def _display(oc: MetricOutcome | None) -> float | None:
    if oc is None or oc.error or oc.display is None:
        return None
    return float(oc.display)


def figures(spec: dict[str, Any], token: str, outcomes: dict[str, MetricOutcome]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for m in spec.get("metrics") or []:
        oc = outcomes.get(metric_code(token, m["key"]))
        fid = figure_id(token, m["key"])
        f: dict[str, Any] = {"id": fid, "label": m["label"], "value": _display(oc), "unit": m.get("unit") or "NONE", "decimals": m.get("decimals"), "dataOrigin": (oc.data_origin if oc else None) or "simulated"}
        if oc is not None and not oc.error:
            f["calc"] = oc.trace
        else:
            f["stale"] = True
            f["staleReason"] = ((oc.error if oc else None) or "계산 결과 없음")[:200]
            f["undefinedLabel"] = "계산 불가"
        out[fid] = f
    return out


def verdicts(spec: dict[str, Any], token: str, figs: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """명세의 지표 규칙(op · value · severity) 판정 — LLM 판단이 없을 때의 심각도 기준."""
    out = {}
    for m in spec.get("metrics") or []:
        rule = m.get("rule")
        val = figs.get(figure_id(token, m["key"]), {}).get("value")
        if not rule or val is None:
            continue
        op, th = rule["op"], float(rule["value"])
        hit = (val > th) if op == ">" else (val >= th) if op == ">=" else (val < th) if op == "<" else (val <= th)
        out[m["key"]] = {"hit": hit, "severity": rule["severity"] if hit else "info", "op": op}
    return out


def _fmt(v: Decimal | None, unit: str) -> str:
    if v is None:
        return "-"
    dec = 0 if unit in ("CNT", "KRW_MN", "NONE") and v == v.to_integral_value() else 2
    s = f"{float(v):,.{dec}f}"
    return s


def tables(ctx: EvalContext, spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """명세 표 — 데이터셋 현재 행을 조건으로 거른 뒤 묶음별 집계(결정론 · Decimal). 오류는 표의 note 로."""
    out: dict[str, dict[str, Any]] = {}
    for t in spec.get("tables") or []:
        try:
            _, rows, _ = ctx.dataset(t["dataset"])
            where = resolve_where(ctx, rows, t.get("where"))
            excl = {str(x) for x in t.get("exclude") or []}
            sel = [r for r in rows if _match(r, where, ctx) and str(r.get(t["group_by"])) not in excl]
            groups: dict[str, list[Decimal]] = {}
            for r in sel:
                g = r.get(t["group_by"])
                g = "(없음)" if g in (None, "") else str(g)
                if t["agg"] == "count":
                    groups.setdefault(g, []).append(Decimal(1))
                else:
                    v = r.get(t["value"])
                    if v is None or v == "":
                        continue
                    groups.setdefault(g, []).append(formulas.D(v))
            agg: list[tuple[str, Decimal]] = []
            for g, vals in groups.items():
                if not vals:
                    continue
                a = t["agg"]
                val = sum(vals, Decimal(0)) if a in ("sum", "count") else (sum(vals, Decimal(0)) / len(vals)) if a == "mean" else max(vals) if a == "max" else min(vals)
                agg.append((g, val))
            agg.sort(key=lambda x: x[1], reverse=t.get("sort", "desc") != "asc")
            top = agg[: int(t.get("top") or 10)]
            out[t["key"]] = {"rows": top, "total": len(agg), "note": None, "where": {k: v for k, v in where.items() if not isinstance(v, dict)}}
        except (ResolveError, KeyError, ValueError, TypeError, ArithmeticError) as exc:
            out[t["key"]] = {"rows": [], "total": 0, "note": f"표를 만들 수 없습니다 — {str(exc)[:160]}", "where": {}}
    return out


def default_statement(spec: dict[str, Any], ins: dict[str, Any], token: str) -> str:
    """기본 문장(LLM 서술 전 · 실패 시) — 숫자 없이 마커만."""
    labels = {m["key"]: m["label"] for m in spec.get("metrics") or []}
    parts = [f"{labels.get(k, k)} [[fig:{figure_id(token, k)}]]" for k in ins.get("metrics") or [] if k in labels]
    return f"{ins.get('title') or spec.get('title', '')} — " + (", ".join(parts) if parts else "계산 결과를 확인하세요") + "."


def _sev_max(*vals: str | None) -> str:
    best = "info"
    for v in vals:
        if v in SEV_RANK and SEV_RANK[v] > SEV_RANK[best]:
            best = v
    return best


def _evidence(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for i, h in enumerate(hits[:8]):
        dbc = h.get("doc_class") or h.get("docClass") or "model_method"
        out.append({
            "id": f"ev-{i + 1}", "category": "external_policy" if h.get("origin") == "ext" else "internal_direction", "sourceKind": "doc_chunk",
            "label": str(h.get("title") or "문서")[:120], "snippet": str(h.get("text") or "")[:240], "relevance": h.get("score"),
            "doc": {"title": str(h.get("title") or "")[:120], "page": h.get("page"), "dbClass": dbc, "issuer": h.get("issuer"), "isOfficial": h.get("origin") == "ext"},
        })
    return out


def render(
    spec: dict[str, Any],
    token: str,
    *,
    figs: dict[str, dict[str, Any]],
    tabs: dict[str, dict[str, Any]],
    verdict: dict[str, dict[str, Any]],
    findings: dict[str, dict[str, Any]],
    previous: dict[str, Any] | None,
    evidence: list[dict[str, Any]],
    as_of: str | None,
    version: int,
) -> dict[str, Any]:
    tab_key = f"an-{token}"
    prev_ops = {o.get("id"): o for o in ((previous or {}).get("opinions") or []) if isinstance(o, dict)}
    ev = _evidence(evidence)
    opinions = []
    for ins in spec.get("insights") or []:
        iid = insight_id(token, ins["key"])
        fids = [figure_id(token, k) for k in ins.get("metrics") or []]
        rule_sev = _sev_max(*[verdict.get(k, {}).get("severity") for k in ins.get("metrics") or []])
        found = findings.get(ins["key"]) or {}
        prev = prev_ops.get(iid) or {}
        opinions.append({
            "id": iid, "kind": "analysis_result", "persona": spec.get("persona") or "P2", "domainCode": spec.get("domain") or spec.get("space", "").upper(),
            "title": ins.get("title") or spec["title"],
            # 검증(critic)을 통과한 새 서술이 있으면 critic 이 이 문장을 바꾼다 — 그 전에는 지난 게시 문장 · 기본 문장
            "statement": prev.get("statement") or default_statement(spec, ins, token),
            "severity": _sev_max(rule_sev, found.get("severity")),
            "asOf": as_of or "", "dataOrigin": _origin(figs, fids),
            "figures": {f: figs[f] for f in fids if f in figs}, "evidence": ev[:3], "verifications": [],
            "reportKind": "dynamic", "reportAnchor": "sec-1", "tabKey": tab_key,
        })
    sections, toc = [], []
    labels = {m["key"]: m for m in spec.get("metrics") or []}
    tdefs = {t["key"]: t for t in spec.get("tables") or []}
    for i, sec in enumerate(spec.get("sections") or [], start=1):
        sid = f"sec-{i}"
        blocks: list[dict[str, Any]] = []
        for b in sec.get("blocks") or []:
            if b["type"] == "metrics":
                blocks.append({"type": "metrics", "figures": [figure_id(token, k) for k in b["metrics"] if k in labels]})
            elif b["type"] == "text":
                blocks.append({"type": "p", "text": b["text"]})
            elif b["type"] in ("table", "chart"):
                td, tv = tdefs.get(b["table"]), tabs.get(b["table"]) or {"rows": [], "note": "표 없음"}
                if td is None:
                    continue
                unit = td.get("unit") or "NONE"
                if b["type"] == "table":
                    note = tv.get("note") or (f"상위 {len(tv['rows'])}개 / 전체 {tv['total']}개 묶음" if tv.get("total", 0) > len(tv["rows"]) else None)
                    blocks.append({"type": "table", "table": {
                        "caption": td["caption"],
                        "columns": [{"key": "group", "label": td["group_label"]}, {"key": "value", "label": f"{td['value_label']}" + (f"({UNIT_LABELS[unit]})" if unit != "NONE" else ""), "align": "right"}],
                        "rows": [{"group": g, "value": _fmt(v, unit)} for g, v in tv["rows"]],
                        **({"note": note} if note else {}),
                    }})
                else:
                    blocks.append({"type": "chart", "chart": {"kind": b.get("kind") or "bar", "title": td["caption"], "unit": unit,
                                                              "series": [{"name": td["value_label"], "points": [{"label": g, "value": float(v)} for g, v in tv["rows"]]}]}})
        sections.append({"id": sid, "heading": sec["heading"], "level": 2, "blocks": blocks})
        toc.append({"id": sid, "label": sec["heading"], "level": 2})
    return {
        "id": f"rep-{tab_key}",
        "kind": "dynamic",
        "title": spec["title"],
        "subtitle": spec.get("purpose") or "부서 맞춤 분석",
        "asOf": as_of or date.today().isoformat(),
        "generatedAt": (previous or {}).get("generatedAt") or "",
        "dataOrigin": _origin(figs, list(figs)),
        "toc": toc,
        "sections": sections,
        "figures": figs,
        "opinions": opinions,
        "evidence": ev,
        "limitations": [
            "수치는 계산 커널이 데이터셋 현재 버전으로 계산했고, 의견 문장은 이 분석 전용 에이전트가 쓴 뒤 검증(숫자 직접 기재 · 인과 단정 차단)을 통과한 것만 게시합니다.",
            f"부서 요청으로 만든 맞춤 분석(명세 v{version}) — 관리자 승인 후 실행됩니다.",
        ],
    }


def _origin(figs: dict[str, dict[str, Any]], ids: list[str]) -> str:
    vals = {figs[i].get("dataOrigin") for i in ids if i in figs and figs[i].get("value") is not None}
    vals.discard(None)
    if not vals:
        return "simulated"
    return vals.pop() if len(vals) == 1 else "mixed"


def as_of_of(ctx: EvalContext, spec: dict[str, Any]) -> str | None:
    """입력 데이터셋 기준일 중 가장 늦은 값 (YYYY-MM-DD 또는 YYYYMM 그대로)."""
    from .spec import input_datasets

    best = None
    for code in input_datasets(spec):
        try:
            _, rows, ds = ctx.dataset(code)
        except Exception:  # noqa: BLE001
            continue
        col = ds.as_of_column
        vals = [str(r.get(col)) for r in rows if col and r.get(col) is not None]
        if vals:
            v = max(vals)
            best = v if best is None or v > best else best
    if best and len(best) == 6 and best.isdigit():
        best = f"{best[:4]}-{best[4:]}"
    return best
