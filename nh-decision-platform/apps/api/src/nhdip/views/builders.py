"""표·차트 빌더 — 화면 산출물의 표·차트 블록을 현재 데이터셋 버전과 커널 계산으로 다시 그린다.

바인딩(cfg.view_binding)이 어떤 산출물의 어느 블록을 어떤 빌더로 그릴지 지정한다.
모든 수치는 커널(calc.execute) 로 계산하고, 표시 반올림은 round_display 를 따른다.
새 화면 형식이 필요하면 @builder 로 등록하고 관리자 화면에서 바인딩만 추가한다.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Callable

from nhdip.calc import execute, round_display
from nhdip.calc.metrics import EvalContext, _match, resolve_ref, resolve_token, resolve_where

BUILDERS: dict[str, Callable[[EvalContext, dict[str, Any]], Any]] = {}
DESCRIPTIONS: dict[str, str] = {}


def builder(name: str, description: str):
    def deco(fn):
        BUILDERS[name] = fn
        DESCRIPTIONS[name] = description
        return fn

    return deco


def _rows(ctx: EvalContext, dataset: str, where: dict[str, Any] | None = None, order_by: str | None = None) -> list[dict[str, Any]]:
    _, rows, _ = ctx.dataset(dataset)
    where = resolve_where(ctx, rows, where)
    sel = [r for r in rows if _match(r, where, ctx)]
    if order_by:
        sel.sort(key=lambda r: (r.get(order_by) is None, r.get(order_by)))
    return sel


def _r(v: Decimal | None, d: int, rounding: str = "HALF_UP") -> Decimal | None:
    return round_display(v, d, rounding)


def _fmt(v: Decimal | float | int | None, d: int = 0, sign: bool = False) -> str:
    if v is None:
        return "-"
    q = _r(Decimal(str(v)), d)
    s = f"{q:,.{d}f}"
    return f"+{s}" if sign and q > 0 else s


# ═════════════════════════ 모형 모니터링 ═════════════════════════
def _grade_stats(ctx: EvalContext, p: dict[str, Any]) -> list[dict[str, Any]]:
    grades = _rows(ctx, p["dataset"], p.get("where"), p.get("order_by", "grade_seq"))
    master = {r["grade"]: r for r in _rows(ctx, p["master"], p.get("master_where"))} if p.get("master") else {}
    rates: list[Decimal] = []
    out = []
    for g in grades:
        dr = execute("DEFAULT_RATE", {"default_count": g["default_count"], "obs_count": g["obs_count"]}).value
        m = master.get(g["grade"], {})
        breach = None
        if m.get("pd_mid") is not None and m.get("pd_max") is not None:
            breach = execute("PD_BREACH_CHECK", {"actual_dr": dr, "pd_mid": m["pd_mid"], "pd_max": m["pd_max"]}).extra["verdict"]
        rates.append(dr)
        out.append({**g, "default_rate": dr, "pd_mid": m.get("pd_mid"), "pd_max": m.get("pd_max"), "breach": breach})
    breaks = execute("MONOTONIC_BREAKS", {"labels": [g["grade"] for g in out], "rates": rates}).extra["breaks"] if out else []
    total = sum(Decimal(str(g["obs_count"])) for g in out) or Decimal(1)
    for g in out:
        g["monotonic_break"] = g["grade"] in breaks
        g["obs_share"] = execute("SHARE", {"numerator": g["obs_count"], "denominator": total}).value
    return out


@builder("grade_table", "등급별 모니터링 표 (건수·구성비·부도율·예측 대표값/최대값·판정)")
def b_grade_table(ctx: EvalContext, p: dict[str, Any]):
    labels = p.get("verdict_labels") or {}
    rows = []
    for g in _grade_stats(ctx, p):
        verdict = labels.get(g["breach"] or "", None)
        if g["breach"] == "within_mid" or not verdict:
            verdict = labels.get("monotonic_break") if g["monotonic_break"] else labels.get("within_mid", "예측 범위 내")
        rows.append(
            {
                "grade": g["grade"],
                "obsCount": _fmt(g["obs_count"]),
                "obsShare": _fmt(g["obs_share"], 2),
                "defaultCount": _fmt(g["default_count"]),
                "defaultRate": _fmt(g["default_rate"], 3),
                "pdMid": _fmt(g["pd_mid"], 3),
                "pdMax": _fmt(g["pd_max"], 3),
                "ks": _fmt(g.get("ks"), 1) if g.get("ks") is not None else "-",
                "sdrRank": g.get("sdr_rank") if g.get("sdr_rank") is not None else "-",
                "verdict": verdict,
            }
        )
    return rows


@builder("grade_series", "등급별 실제부도율 vs 예측 대표값·최대값 차트 시리즈")
def b_grade_series(ctx: EvalContext, p: dict[str, Any]):
    stats = _grade_stats(ctx, p)
    names = p.get("names") or {"default_rate": "실제부도율", "pd_mid": "예측 대표값", "pd_max": "예측 최대값"}
    return [
        {"name": label, "points": [{"label": g["grade"], "value": None if g[key] is None else float(_r(Decimal(str(g[key])), 3))} for g in stats]}
        for key, label in names.items()
    ]


def _psi_parts(ctx: EvalContext, p: dict[str, Any]):
    base = _rows(ctx, p["dataset"], p["base_where"], p.get("order_by", "grade_seq"))
    cur = _rows(ctx, p["dataset"], p["current_where"], p.get("order_by", "grade_seq"))
    col = p.get("share_col", "obs_share")
    res = execute("PSI", {"base": [r[col] for r in base], "current": [r[col] for r in cur], "eps": p.get("eps", 1e-6)})
    return base, cur, col, res


@builder("psi_table", "등급별 분포 비교 및 PSI 기여도 표")
def b_psi_table(ctx: EvalContext, p: dict[str, Any]):
    base, cur, col, res = _psi_parts(ctx, p)
    return [
        {
            "bucket": b["grade"],
            "baseShare": _fmt(b[col], 2),
            "currentShare": _fmt(c[col], 2),
            "diff": _fmt(execute("DIFF", {"a": c[col], "b": b[col]}).value, 2),
            "contribution": _fmt(Decimal(str(contrib)), 4),
        }
        for b, c, contrib in zip(base, cur, res.extra["contributions"])
    ]


def _label(ctx: EvalContext, text: str) -> str:
    """서식 표식([[ym:…]] · [[rule:…]])이 든 라벨 — 데이터 기간을 따른다 (Phase I)."""
    from nhdip.views.template import render_text

    return render_text(text, {}, ctx) if "[[" in (text or "") else text


@builder("psi_series", "등급별 구성비 — 기준시점 vs 비교시점 차트")
def b_psi_series(ctx: EvalContext, p: dict[str, Any]):
    base, cur, col, _ = _psi_parts(ctx, p)
    names = [_label(ctx, n) for n in (p.get("names") or ["기준", "비교"])]
    return [
        {"name": names[0], "points": [{"label": r["grade"], "value": float(r[col])} for r in base]},
        {"name": names[1], "points": [{"label": r["grade"], "value": float(r[col])} for r in cur]},
    ]


# ═════════════════════════ 포용금융 충당금 ═════════════════════════
def _inclusive(ctx: EvalContext, p: dict[str, Any]):
    master = {r["product_code"]: r for r in _rows(ctx, p["master"])}
    prov = _rows(ctx, p["dataset"])
    amt = p.get("amount_col", "provision")
    p = dict(p)
    for k in ("base_ym", "now_ym"):
        if isinstance(p[k], dict) and "ref" in p[k]:
            p[k] = resolve_ref(ctx, p[k]["ref"])[0]
        p[k] = resolve_token(prov, "ym", p[k])

    def by_ym(ym):
        return {r["product_code"]: r for r in prov if str(r.get("ym")) == str(ym) and not r.get("is_total")}

    base, now = by_ym(p["base_ym"]), by_ym(p["now_ym"])
    items = []
    for code, m in master.items():
        b = Decimal(str(base.get(code, {}).get(amt) or 0))
        n = Decimal(str(now.get(code, {}).get(amt) or 0))
        items.append({"code": code, "name": m.get("product_name"), "group": m.get("product_group"), "base": b, "now": n, "diff": execute("DIFF", {"a": n, "b": b}).value})
    total_diff = sum((i["diff"] for i in items), Decimal(0))
    for i in items:
        i["contribution"] = execute("SHARE", {"numerator": i["diff"], "denominator": total_diff}).value if total_diff else Decimal(0)
    items.sort(key=lambda i: i["diff"], reverse=True)
    totals = {}
    for ym in (p["base_ym"], p["now_ym"]):
        t = [r for r in prov if str(r.get("ym")) == str(ym) and r.get("is_total")]
        totals[str(ym)] = Decimal(str(t[0][amt])) if t else None
    unmatched = sorted(set(now) - set(master)) if p.get("report_unmatched") else []
    return items, totals, unmatched


@builder("inclusive_products", "포용금융 대상 상품별 충당금 증감·기여도 (InclusiveProductRow[])")
def b_inclusive_products(ctx: EvalContext, p: dict[str, Any]):
    items, _, _ = _inclusive(ctx, p)
    return [
        {
            "productCode": i["code"],
            "productName": i["name"],
            "productGroup": i["group"],
            "provisionBase": float(i["base"]),
            "provisionNow": float(i["now"]),
            "diff": float(i["diff"]),
            "contribution": float(_r(i["contribution"], 1)),
        }
        for i in items
    ]


@builder("inclusive_product_table", "상품별 충당금 증감 및 기여도 표 (보고서, 상위 N건)")
def b_inclusive_table(ctx: EvalContext, p: dict[str, Any]):
    items, _, _ = _inclusive(ctx, p)
    return [
        {
            "code": i["code"],
            "name": i["name"],
            "group": i["group"],
            "base": _fmt(i["base"]),
            "now": _fmt(i["now"]),
            "diff": _fmt(i["diff"], 0, sign=True),
            "contribution": _fmt(i["contribution"], 1),
        }
        for i in items[: int(p.get("limit", 10))]
    ]


@builder("inclusive_groups", "상품군별 요약 (코드 수 · 기준/비교 충당금 · 비중 증감 %p)")
def b_inclusive_groups(ctx: EvalContext, p: dict[str, Any]):
    items, totals, _ = _inclusive(ctx, p)
    groups: dict[str, dict[str, Any]] = {}
    for i in items:
        g = groups.setdefault(i["group"], {"group": i["group"], "codes": 0, "base": Decimal(0), "now": Decimal(0)})
        g["codes"] += 1
        g["base"] += i["base"]
        g["now"] += i["now"]
    tb, tn = totals.get(str(p["base_ym"])), totals.get(str(p["now_ym"]))
    out = []
    for g in groups.values():
        delta = None
        if tb and tn:
            s1 = execute("SHARE", {"numerator": g["now"], "denominator": tn}).value
            s0 = execute("SHARE", {"numerator": g["base"], "denominator": tb}).value
            delta = float(_r(execute("SHARE_DELTA_PP", {"share1": s1, "share0": s0}).value, 2))
        out.append({"group": g["group"], "codes": g["codes"], "base": float(g["base"]), "now": float(g["now"]), "deltaPP": delta})
    order = p.get("group_order")
    if order:
        out.sort(key=lambda g: order.index(g["group"]) if g["group"] in order else 99)
    return out


@builder("inclusive_group_table", "상품군별 요약 표 (보고서 — 상품코드 수 · 기준/비교 충당금 · 비중 증감 %p, 표시 문자열)")
def b_inclusive_group_table(ctx: EvalContext, p: dict[str, Any]):
    return [
        {"group": g["group"], "codes": g["codes"], "base": _fmt(g["base"]), "now": _fmt(g["now"]), "deltaPP": "-" if g["deltaPP"] is None else _fmt(g["deltaPP"], 2, sign=True)}
        for g in b_inclusive_groups(ctx, p)
    ]


@builder("inclusive_match_note", "대상 상품코드 매칭 결과 문장 (마스터 코드 중 최근 충당금 자료에 있는 코드 수)")
def b_inclusive_match_note(ctx: EvalContext, p: dict[str, Any]):
    master = {r["product_code"] for r in _rows(ctx, p["master"])}
    prov = _rows(ctx, p["dataset"])
    latest = max((str(r.get("ym")) for r in prov), default=None)
    have = {r["product_code"] for r in prov if str(r.get("ym")) == latest}
    miss = len(master - have)
    return f"상품코드 {len(master)}건 {'전건 매칭' if not miss else f'중 {len(master) - miss}건 매칭'}(미매칭 {miss}건)."


@builder("data_quality", "데이터 품질 요약 [{label, status, note}] — 데이터셋 최근 버전 품질 검사 · 마스터 매칭 · 미제공 자료")
def b_data_quality(ctx: EvalContext, p: dict[str, Any]):
    from nhdip.calc.metrics import ResolveError

    out = []
    for it in p.get("items") or []:
        # dataset = 이 바인딩의 워크플로가 맡은 자료(계보 대상), ref_dataset = 다른 워크플로 자료(표시만 — 계보로 이 워크플로를 깨우지 않음)
        ds_code = it.get("dataset") or it.get("ref_dataset")
        label = _label(ctx, it.get("label") or ds_code or "")
        kind = it.get("kind", "dataset")
        try:
            if kind == "missing":
                if ds_code:
                    ctx.dataset(ds_code)  # 정의 · 자료가 생기면 아래 dataset 판정으로 바뀐다
                    kind = "dataset"
                else:
                    raise ResolveError("미제공")
            if kind == "master_match":
                note = b_inclusive_match_note(ctx, {**it, "dataset": ds_code})
                out.append({"label": label, "status": "passed" if "전건 매칭" in note else "warning", "note": note.rstrip(".")})
                continue
            vs, rows, _ = ctx.dataset(ds_code)
            v = vs.versions[0]
            q = v.quality or {}
            bad = [c for c in q.get("checks") or [] if not c.get("passed")]
            note = " · ".join(c.get("detail") or c.get("rule") for c in bad[:2]) if bad else f"품질 검사 통과 · {v.row_count:,}행 · {v.file_name}"
            out.append({"label": label, "status": q.get("status") or "passed", "note": note[:200]})
        except ResolveError:
            out.append({"label": label, "status": "failed", "note": it.get("note") or "데이터 미제공 — 분석에서 제외"})
    return out


# ═════════════════════════ 부도율 추이 ═════════════════════════
@builder("series_points", "월별 시계열 포인트 [{label, value}] — 데이터셋 행에서 수식으로 계산 (latest_year: 최근 연도만 · label_fmt: month · scale: 단위 환산)")
def b_series_points(ctx: EvalContext, p: dict[str, Any]):
    rows = _rows(ctx, p["dataset"], p.get("where"), p.get("order_by", "ym"))
    lc = p.get("label_col", "ym")
    if p.get("latest_year") and rows:
        year = max(str(r.get(lc))[:4] for r in rows)
        rows = [r for r in rows if str(r.get(lc)).startswith(year)]
    out = []
    for r in rows:
        if p.get("formula"):
            args = {k: r.get(v) for k, v in p["args"].items()}
            val = execute(p["formula"], args).value
        else:
            val = Decimal(str(r.get(p["col"]))) if r.get(p["col"]) is not None else None
        if val is not None and p.get("scale"):
            val = val / Decimal(str(p["scale"]))
        ym = str(r.get(lc))
        if p.get("label_fmt") == "month" and len(ym) >= 6 and ym[:6].isdigit():
            label = f"{int(ym[4:6])}월"
        else:
            label = f"{ym[:4]}.{ym[4:6]}" if len(ym) == 6 and ym.isdigit() else ym
        out.append({"label": label, "value": None if val is None else float(_r(val, int(p.get("decimals", 3))))})
    return out


@builder("metric_series", "지표 결과로 만든 차트 시리즈 [{name, points}] — 시점 비교 막대(이름 · 라벨은 데이터 기간 표식)")
def b_metric_series(ctx: EvalContext, p: dict[str, Any]):
    return [{"name": _label(ctx, s.get("name") or ""), "points": b_metric_points(ctx, {"points": s.get("points") or []})} for s in p.get("series") or []]


@builder("metric_points", "지표 결과로 만든 점 [{label, value}] — 연도별 비교 차트(라벨은 데이터 기간 표식)")
def b_metric_points(ctx: EvalContext, p: dict[str, Any]):
    out = []
    for pt in p.get("points") or []:
        oc = ctx.outcomes.get(pt["metric"])
        val = None if oc is None or oc.error or oc.display is None else float(oc.display)
        out.append({"label": _label(ctx, pt.get("label") or pt["metric"]), "value": val})
    if all(x["value"] is None for x in out):
        from nhdip.calc.metrics import ResolveError

        raise ResolveError("지표 값 없음: " + ", ".join(pt["metric"] for pt in p.get("points") or []))
    return out


# ═════════════════════════ 범용 ═════════════════════════
@builder("template", "지표 표시값을 끼운 문장 (예: '합계 {total_obs}건') — 숫자는 지표 표시값만 사용")
def b_template(ctx: EvalContext, p: dict[str, Any]):
    vals = {}
    for code, oc in ctx.outcomes.items():
        if oc.display is not None:
            d = oc.decimals or 0
            vals[code] = f"{oc.display:,.{d}f}"
        for k, v in (oc.extra or {}).items():
            if isinstance(v, (str, int)):
                vals[f"{code}__{k}"] = v
    try:
        return p["template"].format_map(_SafeDict(vals))
    except (KeyError, ValueError):
        return p["template"]


class _SafeDict(dict):
    def __missing__(self, key):
        return "{" + key + "}"


# 영업점 시나리오 빌더 등록 (B.29) — 모듈 끝에서 가져와 순환 참조를 피한다
from nhdip.views import branch as _branch  # noqa: E402,F401
