"""영업점 시나리오 표 · 차트 빌더 (B.29) — 모든 집계는 커널 수식(SUM · SHARE · DIFF · KPI_PROPORTIONAL_SCORE)으로 계산."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from nhdip.calc import execute
from nhdip.calc.formulas import _grade_seq, grade_weight
from nhdip.calc.metrics import EvalContext, resolve_ref

from .builders import _fmt, _r, _rows, builder


def _val(ctx: EvalContext, v: Any) -> Any:
    if isinstance(v, dict) and "ref" in v:
        return resolve_ref(ctx, v["ref"])[0]
    return v


def _rule(ctx: EvalContext, code: str) -> dict[str, Any]:
    return resolve_ref(ctx, {"rule": code})[0] or {}


def _sum(vals: list[Any]) -> Decimal:
    return execute("SUM", {"values": [v for v in vals if v is not None]}).value or Decimal(0)


def _share(n: Any, d: Any) -> Decimal | None:
    return execute("SHARE", {"numerator": n, "denominator": d}).value if d else None


def _portfolio(ctx: EvalContext, p: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    office = _val(ctx, p["office"])
    where = dict(p.get("where") or {})
    bank = _rows(ctx, p["dataset"], where)
    br = [r for r in _rows(ctx, p["dataset"], {**where, p["office_col"]: office})]
    return br, bank, _rule(ctx, p.get("scale_rule", "CORP_GRADE_SCALE"))


# ═════════════════════════ 대시보드 ═════════════════════════
@builder("branch_office", "영업점 정보(사무소 마스터) — 코드 · 이름 · 지역 · 지역본부")
def b_branch_office(ctx: EvalContext, p: dict[str, Any]):
    office = _val(ctx, p["office"])
    rows = _rows(ctx, p.get("dataset", "BRANCH_OFFICE_MASTER"), {"office_cd": office})
    if not rows:
        raise KeyError(f"사무소 마스터에 없음: {office}")
    r = rows[0]
    return {"code": str(r["office_cd"]), "name": r.get("office_nm"), "region": r.get("region"), "sigungu": r.get("sigungu"), "regionHq": r.get("region_hq"), "orgCode": r.get("org_code") or str(r["office_cd"])}


@builder("branch_kpi_scorecard", "업적평가 평가항목별 득점 · 배점 · 상반기 대비 변경 (배점표 × 득점 현황)")
def b_kpi_scorecard(ctx: EvalContext, p: dict[str, Any]):
    office, period, prev = _val(ctx, p["office"]), _val(ctx, p["period"]), _val(ctx, p.get("prev_period"))
    scheme = _rows(ctx, p.get("scheme", "BRANCH_KPI_SCHEME"), {"period": period})
    prev_max = {r["item_cd"]: r.get("max_points") for r in _rows(ctx, p.get("scheme", "BRANCH_KPI_SCHEME"), {"period": prev})} if prev else {}
    scores = {r["item_cd"]: r for r in _rows(ctx, p.get("score", "BRANCH_KPI_SCORE"), {"office_cd": office, "period": period})}

    def item(r: dict[str, Any]) -> dict[str, Any]:
        sc = scores.get(r["item_cd"], {})
        out = {"code": r["item_cd"], "label": r["item_nm"], "score": None if sc.get("score") is None else float(_r(Decimal(str(sc["score"])), 2)), "max": r.get("max_points"),
               "prevMax": prev_max.get(r["item_cd"]), "changeType": r.get("change_type") or None, "changeSummary": r.get("change_summary") or None, "docPage": r.get("doc_page") or None}
        if sc.get("actual_value") is not None:
            out |= {"actual": float(sc["actual_value"]), "target": None if sc.get("target_value") is None else float(sc["target_value"]), "actualUnit": sc.get("unit")}
        if sc.get("note"):
            out["note"] = sc["note"]
        return out

    groups = []
    for g in [r for r in scheme if int(r["level"]) == 1]:
        items = []
        for it in [r for r in scheme if int(r["level"]) == 2 and r.get("parent_cd") == g["item_cd"]]:
            x = item(it)
            x["details"] = [item(d) for d in scheme if int(d["level"]) == 3 and d.get("parent_cd") == it["item_cd"]]
            items.append(x)
        total = _sum([x["score"] for x in items])
        groups.append({"code": g["item_cd"], "label": g["item_nm"], "kind": "adjustment" if g["group_cd"] == "ADJ" else "kpi", "score": float(_r(total, 1)), "max": g.get("max_points"), "prevMax": prev_max.get(g["item_cd"]), "items": items})
    return groups


# ═════════════════════════ 기업여신 포트폴리오 (2화면) ═════════════════════════
@builder("branch_size_table", "기업규모별 익스포저 — 지점 건수 · 금액 · 비중 vs 전행 비중")
def b_size_table(ctx: EvalContext, p: dict[str, Any]):
    br, bank, sc = _portfolio(ctx, p)
    col_s = p.get("size_col", "crdevl_pttp_dsc_f")
    bt_c, bt_a = len(br), _sum([r["ln_bac"] for r in br])
    kt_c, kt_a = len(bank), _sum([r["ln_bac"] for r in bank])
    rows = []
    for code in sc.get("size_order") or []:
        b = [r for r in br if str(r.get(col_s)) == code]
        k = [r for r in bank if str(r.get(col_s)) == code]
        b_a, k_a = _sum([r["ln_bac"] for r in b]), _sum([r["ln_bac"] for r in k])
        b_sh, k_sh = _share(b_a, bt_a), _share(k_a, kt_a)
        rows.append({"size": sc.get("size_labels", {}).get(code, code), "brCnt": _fmt(len(b)), "brCntShare": _fmt(_share(len(b), bt_c), 1), "brAmt": _fmt(b_a / Decimal(1e8), 1), "brAmtShare": _fmt(b_sh, 1),
                     "bankCntShare": _fmt(_share(len(k), kt_c), 1), "bankAmtShare": _fmt(k_sh, 1), "diffPp": _fmt(execute("DIFF", {"a": b_sh or 0, "b": k_sh or 0}).value, 1, sign=True)})
    rows.append({"size": "합계", "brCnt": _fmt(bt_c), "brCntShare": "100.0", "brAmt": _fmt(bt_a / Decimal(1e8), 1), "brAmtShare": "100.0", "bankCntShare": "100.0", "bankAmtShare": "100.0", "diffPp": "-"})
    return rows


@builder("branch_grade_table", "신용등급(16단계)별 익스포저 — 지점 건수 · 금액 · 비중 vs 전행 비중")
def b_grade_table(ctx: EvalContext, p: dict[str, Any]):
    br, bank, sc = _portfolio(ctx, p)
    g_col = p.get("grade_col", "Ls_nics_GRDC")
    bt_c, bt_a = len(br), _sum([r["ln_bac"] for r in br])
    kt_c, kt_a = len(bank), _sum([r["ln_bac"] for r in bank])
    rows = []
    for i, label in enumerate(sc.get("labels") or [], start=1):
        b = [r for r in br if int(r.get(g_col) or 0) == i]
        k = [r for r in bank if int(r.get(g_col) or 0) == i]
        b_a = _sum([r["ln_bac"] for r in b])
        rows.append({"grade": label, "brCnt": _fmt(len(b)), "brCntShare": _fmt(_share(len(b), bt_c), 1), "brAmt": _fmt(b_a / Decimal(1e8), 1), "brAmtShare": _fmt(_share(b_a, bt_a), 1),
                     "bankCntShare": _fmt(_share(len(k), kt_c), 1), "bankAmtShare": _fmt(_share(_sum([r["ln_bac"] for r in k]), kt_a), 1)})
    return rows


def _band_of(seq: int, sc: dict[str, Any]) -> int:
    labels = sc.get("labels") or []
    for i, b in enumerate(sc.get("bands") or []):
        mx = _grade_seq(b.get("max_grade"), labels)
        if mx is not None and seq <= mx:
            return i
    return len(sc.get("bands") or []) - 1


@builder("branch_size_grade_table", "기업규모 × 신용등급 구간 비중 — mode: count(건수) · amount(금액), 지점 전체 = 100%")
def b_size_grade_table(ctx: EvalContext, p: dict[str, Any]):
    br, _, sc = _portfolio(ctx, p)
    col_s, g_col = p.get("size_col", "crdevl_pttp_dsc_f"), p.get("grade_col", "Ls_nics_GRDC")
    amount = p.get("mode") == "amount"
    bands = sc.get("bands") or []
    w = (lambda r: r["ln_bac"]) if amount else (lambda r: 1)
    total = _sum([w(r) for r in br])
    rows = []
    for code in [*(sc.get("size_order") or []), None]:
        sel = br if code is None else [r for r in br if str(r.get(col_s)) == code]
        row: dict[str, Any] = {"size": "합계" if code is None else sc.get("size_labels", {}).get(code, code)}
        for i in range(len(bands)):
            row[f"b{i + 1}"] = _fmt(_share(_sum([w(r) for r in sel if _band_of(int(r[g_col]), sc) == i]), total), 1)
        row["total"] = _fmt(_share(_sum([w(r) for r in sel]), total), 1)
        rows.append(row)
    return rows


@builder("branch_grade_band_series", "신용등급 구간별 금액 비중 차트 — 지점 vs 전행")
def b_grade_band_series(ctx: EvalContext, p: dict[str, Any]):
    br, bank, sc = _portfolio(ctx, p)
    g_col = p.get("grade_col", "Ls_nics_GRDC")
    out = []
    for name, rows in (("지점", br), ("전행", bank)):
        tot = _sum([r["ln_bac"] for r in rows])
        out.append({"name": name, "points": [{"label": b["label"], "value": float(_r(_share(_sum([r["ln_bac"] for r in rows if _band_of(int(r[g_col]), sc) == i]), tot) or Decimal(0), 1))} for i, b in enumerate(sc.get("bands") or [])]})
    return out


@builder("branch_top_borrowers", "지점 기업여신 상위 차주 (대출잔액 순)")
def b_top_borrowers(ctx: EvalContext, p: dict[str, Any]):
    br, _, sc = _portfolio(ctx, p)
    from nhdip.privacy import mask_name, policy as privacy_policy

    masked = set(privacy_policy(ctx.session).get("display_mask_columns") or [])
    labels = sc.get("labels") or []
    tot = _sum([r["ln_bac"] for r in br])
    rows = []
    for i, r in enumerate(sorted(br, key=lambda x: -float(x["ln_bac"]))[: int(p.get("limit", 10))], start=1):
        seq = int(r["Ls_nics_GRDC"])
        name = r.get("brwr_nm") or r.get("brwr_no")
        if r.get("brwr_nm") and "brwr_nm" in masked:
            name = mask_name(r["brwr_nm"])  # 차주명 화면 가림 (설정 privacy.policy.display_mask_columns) — B.32
        rows.append({"rank": i, "name": name, "size": sc.get("size_labels", {}).get(str(r.get("crdevl_pttp_dsc_f")), "-"), "grade": labels[seq - 1] if 0 < seq <= len(labels) else "-",
                     "industry": r.get("STD_INDS_CFC") or "-", "amount": _fmt(Decimal(str(r["ln_bac"])) / Decimal(1e8), 1), "share": _fmt(_share(r["ln_bac"], tot), 1)})
    return rows


@builder("branch_prime_weights", "우량기업여신 신용등급 구간별 가중치 — 상반기(가중치 없음) vs 하반기")
def b_prime_weights(ctx: EvalContext, p: dict[str, Any]):
    pol = _rule(ctx, p.get("rule", "BRANCH_PRIME_CORP_POLICY"))
    labels = _rule(ctx, p.get("scale_rule", "CORP_GRADE_SCALE")).get("labels") or []
    rows, lo = [], 1
    for w in pol.get("weights") or []:
        hi = _grade_seq(w.get("max_grade"), labels) or len(labels)
        rows.append({"band": w.get("label"), "grades": f"{labels[lo - 1]} ~ {labels[hi - 1]}" if lo != hi else labels[lo - 1], "h1": _fmt(Decimal(str(pol.get("h1_weight", 1))) * 100, 0) + "%", "h2": _fmt(Decimal(str(w.get("weight", 1))) * 100, 0) + "%"})
        lo = hi + 1
    return rows


def _outcome(ctx: EvalContext, code: str):
    oc = ctx.outcomes.get(code)
    if oc is None or oc.error:
        raise KeyError(f"지표 결과 없음: {code}")
    return oc


@builder("branch_prospect_table", "마케팅 후보 기업 표 — 선정 지표(PROSPECT_SELECT) 결과")
def b_prospect_table(ctx: EvalContext, p: dict[str, Any]):
    oc = _outcome(ctx, p["metric"])
    sizes = _rule(ctx, "CORP_GRADE_SCALE").get("size_labels") or {}
    rows = []
    for i, s in enumerate(oc.extra.get("selected") or [], start=1):
        rows.append({"rank": i, "corp": s["corp_nm"], "industry": f"{s.get('ind_nm') or '-'} ({str(s.get('ind_cd') or '')[:3]})", "model": sizes.get(str(s.get("nics_model")), s.get("nics_model")), "grade": s["exp_grade"],
                     "asset": _fmt(Decimal(str(s["tot_asset"])) / 100, 0), "debt": _fmt(s["debt_ratio"], 0), "sales": _fmt(Decimal(str(s["sales"])) / 100, 0),
                     "loan": _fmt(Decimal(str(s["loan_mn"])) / 100, 0), "weight": _fmt(Decimal(str(s["weight"])) * 100, 0) + "%", "weighted": _fmt(Decimal(str(s["weighted_mn"])) / 100, 0)})
    return rows


@builder("branch_prospect_note", "마케팅 후보 선정 · 제외 사유 요약 문구")
def b_prospect_note(ctx: EvalContext, p: dict[str, Any]):
    oc = _outcome(ctx, p["metric"])
    pol = _rule(ctx, p.get("rule", "BRANCH_PROSPECT_POLICY"))
    ex = oc.extra.get("excluded") or {}
    ov = ", ".join(oc.extra.get("overlap_industries") or []) or "없음"
    return (f"본부 추천 기업 중 제외 — 지역 외 {ex.get('region', 0)}개 · 예상재무등급 {pol.get('max_grade')} 초과 {ex.get('grade', 0)}개 · 부채비율 {pol.get('max_debt_ratio_pct')}% 초과 {ex.get('debt', 0)}개 · "
            f"지점 집중 업종({ov}, 금액 비중 {pol.get('overlap_share_pct')}% 이상) {ex.get('overlap', 0)}개 · 업종 중복 {ex.get('duplicate', 0)}개 · 후보 상한({pol.get('max_candidates')}개) 초과 {ex.get('limit', 0)}개. "
            "신규 여신 가정액은 NICS 모형별 가정값(규칙 BRANCH_PROSPECT_POLICY · 시뮬레이션 가정), 금액 단위 억원.")


# ═════════════════════════ 소매여신 · 서민금융 (3화면) ═════════════════════════
def _retail(ctx: EvalContext, p: dict[str, Any]):
    office = _val(ctx, p["office"])
    where = dict(p.get("where") or {})
    bank = _rows(ctx, p["dataset"], where)
    br = _rows(ctx, p["dataset"], {**where, p["office_col"]: office})
    master = _rows(ctx, p["master"], {})
    return br, bank, master


@builder("branch_pool_table", "소매여신 Pool별 익스포저 — 지점 건수 · 금액 · 비중 · 연체율 vs 전행 비중")
def b_pool_table(ctx: EvalContext, p: dict[str, Any]):
    br, bank, master = _retail(ctx, p)
    bt, kt = _sum([r["exp_amt"] for r in br]), _sum([r["exp_amt"] for r in bank])
    rows = []
    for m in master:
        b = [r for r in br if r["pool_id"] == m["pool_id"]]
        k = [r for r in bank if r["pool_id"] == m["pool_id"]]
        b_a = _sum([r["exp_amt"] for r in b])
        dlq = _sum([r["exp_amt"] for r in b if int(r.get("dlq_yn") or 0) == 1])
        rows.append({"pool": m["pool_id"], "name": m["pool_nm"], "seomin": "인정" if m.get("seomin_eval") else "-", "lowCredit": "저신용" if m.get("low_credit") else "-", "brCnt": _fmt(len(b)),
                     "brAmt": _fmt(b_a / Decimal(1e6), 0), "brShare": _fmt(_share(b_a, bt), 2), "bankShare": _fmt(_share(_sum([r["exp_amt"] for r in k]), kt), 2),
                     "brDlq": _fmt(_share(dlq, b_a), 2) if b_a else "-", "provRate": _fmt(m.get("prov_rate_pct"), 2)})
    return rows


@builder("branch_pool_series", "상품군별 금액 비중 차트 — 지점 vs 전행")
def b_pool_series(ctx: EvalContext, p: dict[str, Any]):
    br, bank, master = _retail(ctx, p)
    groups = list(dict.fromkeys(m.get("product_group") or "기타" for m in master))
    grp = {m["pool_id"]: m.get("product_group") or "기타" for m in master}
    out = []
    for name, rows in (("지점", br), ("전행", bank)):
        tot = _sum([r["exp_amt"] for r in rows])
        out.append({"name": name, "points": [{"label": g, "value": float(_r(_share(_sum([r["exp_amt"] for r in rows if grp.get(r["pool_id"]) == g]), tot) or Decimal(0), 1))} for g in groups]})
    return out


@builder("branch_seomin_constraints", "서민금융 신규 유치 규모 — 한도별 최대 유치액 · 건수 · 적용 한도 표시")
def b_seomin_constraints(ctx: EvalContext, p: dict[str, Any]):
    m = p["metrics"]
    ticket = _outcome(ctx, m["ticket"]).value
    rec = _outcome(ctx, m["rec"])
    labels = [("gap", "전행 평균 비중 도달 필요액", "지점 서민금융 비중을 전행 평균 수준으로"), ("prov", "충당금 증가 허용 범위", "추가 충당금 ≤ 허용액 (충당금률 가정)"), ("cnt", "반기 신규 가능 건수", "신규 가능 건수 × 평균 취급액")]
    binding = {"a": "gap", "b": "prov", "c": "cnt"}.get(rec.extra.get("binding"))
    rows = []
    for key, label, basis in labels:
        v = _outcome(ctx, m[key]).value
        rows.append({"limit": label, "basis": basis, "amount": _fmt(v / Decimal(1e6), 0), "count": _fmt(execute("CEIL_DIV", {"a": v, "b": ticket}).value, 0), "applied": "적용(최소)" if key == binding else "-"})
    rows.append({"limit": "권고 규모", "basis": "세 한도 중 최소", "amount": _fmt(rec.value / Decimal(1e6), 0), "count": _fmt(execute("CEIL_DIV", {"a": rec.value, "b": ticket}).value, 0), "applied": "권고"})
    return rows


__all__ = ["grade_weight"]
