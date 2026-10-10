"""골든셋 평가 하네스 (작업 8.1 · QA-02) — `python -m nhdip.evals` · 관리자 `/admin/evals` · CI(pytest)."""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from nhdip.calc import execute
from nhdip.models import AppUser, MetricValue, Rule, RuleVersion
from nhdip.views.store import get_current

GOLDEN = os.path.join(os.path.dirname(__file__), "golden.json")
LITERAL = re.compile(r"\d+(?:[.,]\d+)+\s*(?:%p?|bp|배)?|\d+\s*(?:%p?|bp|억|조|만|천|원|건|배)")
MARKER = re.compile(r"\[\[fig:([a-zA-Z0-9_\-]+)\]\]")


def load(path: str | None = None) -> dict[str, Any]:
    with open(path or GOLDEN, encoding="utf-8") as fh:
        return json.load(fh)


def _metric(session: Session, code: str) -> Decimal | None:
    mv = session.execute(select(MetricValue).where(MetricValue.metric_code == code).order_by(MetricValue.created_at.desc()).limit(1)).scalar()
    return None if mv is None or mv.display_value is None else Decimal(str(mv.display_value))


def _rule(session: Session, code: str) -> dict[str, Any]:
    r = session.get(Rule, code)
    v = session.execute(select(RuleVersion).where(RuleVersion.rule_code == code, RuleVersion.version == r.active_version)).scalar() if r else None
    return dict(v.body) if v else {}


def _close(a: Any, b: Any, tol: float) -> bool:
    try:
        return abs(float(a) - float(b)) <= tol + 1e-9
    except (TypeError, ValueError):
        return a == b


def _get(obj: Any, path: str) -> Any:
    for p in path.split("."):
        obj = obj.get(p) if isinstance(obj, dict) else None
    return obj


def _walk(obj: Any):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v)


def _case(name: str, ok: bool, **detail: Any) -> dict[str, Any]:
    return {"case": name, "passed": bool(ok), **detail}


def run(session: Session, golden: dict[str, Any] | None = None) -> dict[str, Any]:
    g = golden or load()
    cats: dict[str, list[dict[str, Any]]] = {k: [] for k in ("metrics", "verdicts", "artifacts", "narration", "retrieval", "assist")}
    for c in g.get("metrics", []):
        v = _metric(session, c["code"])
        cats["metrics"].append(_case(c["code"], v is not None and _close(v, c["expected"], c.get("tol", 0)), actual=None if v is None else float(v), expected=c["expected"]))
    for c in g.get("verdicts", []):
        if "compare" in c:
            a, op, b = c["compare"]
            va, vb = _metric(session, a), _metric(session, b)
            res = None if va is None or vb is None else {"<=": va <= vb, "<": va < vb, ">": va > vb, ">=": va >= vb}[op]
            cats["verdicts"].append(_case(c.get("label", f"{a} {op} {b}"), res == c["expected"], actual=res, expected=c["expected"]))
        else:
            v = _metric(session, c["metric"])
            band = execute("BAND", {"value": v, "bands": _rule(session, c["rule"]).get("bands", [])}).extra.get("verdict") if v is not None else None
            cats["verdicts"].append(_case(f"{c['metric']}·{c['rule']}", band == c["expected"], actual=band, expected=c["expected"]))
    for c in g.get("artifacts", []):
        art = get_current(session, c["key"])
        actual = None
        if "figure" in c:
            actual = next((d.get("value") for d in _walk(art) if d.get("id") == c["figure"] and "unit" in d), None)
        else:
            target = next((d for d in _walk(art) if all(d.get(k) == v for k, v in c["find"].items())), None)
            actual = _get(target, c["path"]) if target else None
        name = f"{c['key']}:{c.get('figure') or c.get('path')}" + (f"[{list(c['find'].values())[0]}]" if c.get("find") else "")
        cats["artifacts"].append(_case(name, actual is not None and _close(actual, c["expected"], c.get("tol", 0)), actual=actual, expected=c["expected"]))
    # 서술 — 확정 수치는 마커로만, 마커는 같은 인사이트의 수치로 해결돼야 한다 (PRIN-05 · CALC-08)
    for key in ("insights", "attentions", "risk_dashboard", "hq_dashboard", "proposals", "report.branch-prime-corp", "report.branch-seomin"):
        for d in _walk(get_current(session, key)):
            st = d.get("statement")
            if not isinstance(st, str) or "figures" not in d:
                continue
            figs = d["figures"] if isinstance(d["figures"], dict) else {f.get("id"): f for f in d["figures"] if isinstance(f, dict)}
            stripped = MARKER.sub(" ", re.sub(r"\{\{term:[^}]+\}\}", " ", st))
            literals = LITERAL.findall(stripped)
            missing = [m for m in MARKER.findall(st) if m not in figs]
            cats["narration"].append(_case(f"{key}:{d.get('id')}", not literals and not missing, literals=literals[:5], unresolved=missing[:5]))
    # 근거 검색 (게이팅 · 우선순위 포함, 시스템 권한)
    from nhdip.graph.evidence import rank_evidence
    from nhdip.graph.search import hybrid_search, query_terms

    for c in g.get("retrieval", []):
        k = int(c.get("k", 4))
        ranked = rank_evidence(session, hybrid_search(session, c["query"], k=k * 3), k=k, query_terms=len(query_terms(c["query"])))
        got = [h.get("docCode") for h in ranked["hits"]]
        want = c.get("expect_any") or [c["expect"]]
        cats["retrieval"].append(_case(c["query"], any(w in got for w in want), expected=want, top=got))
    # 질의 패널 — 질문 → 지표 선택
    from nhdip.api.assist import concepts_of, metrics_for

    admin = session.execute(select(AppUser).where(AppUser.role == "admin").limit(1)).scalar()
    for c in g.get("assist", []):
        got = [m["code"] for m in metrics_for(session, admin, c["question"], concepts_of(session, c["question"]))] if admin else []
        cats["assist"].append(_case(c["question"], c["expect_metric"] in got, expected=c["expect_metric"], top=got[:8]))
    th = g.get("thresholds", {})
    summary = {}
    for name, cases in cats.items():
        total = len(cases)
        ok = sum(1 for x in cases if x["passed"])
        rate = ok / total if total else 1.0
        summary[name] = {"passed": ok, "total": total, "rate": round(rate, 4), "threshold": th.get(name, 1.0), "ok": rate >= th.get(name, 1.0), "failures": [x for x in cases if not x["passed"]][:20]}
    return {"version": g.get("version"), "at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "passed": all(v["ok"] for v in summary.values()), "categories": summary}
