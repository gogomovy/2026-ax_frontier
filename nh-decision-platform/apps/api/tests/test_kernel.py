"""계산 커널 재현 테스트 — B.0 에서 검증한 값을 커널 수식으로 그대로 재현해야 한다 (DB 불필요)."""
from decimal import Decimal

import pytest

from nhdip.calc import FormulaError, execute, round_display, tool_schemas

GRADES = ["3A", "3B", "4A", "4B", "5A", "5B", "5C", "6A", "6B", "7A", "7B", "8"]
OBS = [1842, 3104, 5271, 6940, 7382, 6517, 4983, 3468, 2472, 1286, 624, 178]
DFT = [3, 9, 27, 62, 118, 171, 196, 199, 196, 132, 79, 21]
PD_MID = [0.24, 0.41, 0.68, 1.12, 1.84, 2.91, 4.22, 5.96, 7.733, 10.98, 14.22, 18.9]
BASE = [7.8, 10.4, 14.6, 17.2, 17.0, 12.6, 8.4, 5.2, 3.4, 2.0, 1.0, 0.4]
CUR = [4.18, 7.04, 11.96, 15.75, 16.75, 14.79, 11.31, 7.87, 5.61, 2.92, 1.42, 0.4]


def disp(formula, inputs, d, rounding="HALF_UP"):
    return round_display(execute(formula, inputs).value, d, rounding)


def test_default_rate_6b_and_total():
    assert disp("DEFAULT_RATE", {"default_count": 196, "obs_count": 2472}, 3) == Decimal("7.929")
    assert disp("DEFAULT_RATE", {"default_count": sum(DFT), "obs_count": sum(OBS)}, 3) == Decimal("2.753")
    assert sum(OBS) == 44067 and sum(DFT) == 1213


def test_pd_breach_6b():
    dr = execute("DEFAULT_RATE", {"default_count": 196, "obs_count": 2472}).value
    r = execute("PD_BREACH_CHECK", {"actual_dr": dr, "pd_mid": 7.733, "pd_max": 8.933})
    assert r.extra["verdict"] == "above_mid_within_max"
    assert round_display(r.value, 3) == Decimal("0.196")


def test_monotonic_break_at_grade_8():
    rates = [execute("DEFAULT_RATE", {"default_count": d, "obs_count": o}).value for d, o in zip(DFT, OBS)]
    assert execute("MONOTONIC_BREAKS", {"labels": GRADES, "rates": rates}).extra["breaks"] == ["8"]


def test_psi():
    r = execute("PSI", {"base": BASE, "current": CUR})
    assert round_display(r.value, 3) == Decimal("0.082")
    assert abs(r.extra["contributions"][0] - 0.0226) < 1e-4
    assert abs(r.extra["contributions"][8] - 0.0111) < 1e-4


def test_chi_square_accepted():
    stat = execute("CHI_SQUARE_PD", {"obs": OBS, "defaults": DFT, "pd": PD_MID})
    crit = execute("CHI2_CRITICAL", {"df": stat.extra["df"], "confidence": 0.95})
    assert round_display(stat.value, 2) == Decimal("20.47")
    assert round_display(crit.value, 2) == Decimal("21.03")
    assert execute("CHI2_TEST", {"stat": stat.value, "critical": crit.value}).extra["verdict"] == "accepted"


def test_inclusive_share_rounding():
    v = execute("SHARE", {"numerator": 312470, "denominator": 3412180}).value
    assert round_display(v, 2, "HALF_UP") == Decimal("9.16")
    assert round_display(v, 4) == Decimal("9.1575")
    # 기준 반올림 정책이 바뀌어도 내부 값은 그대로 (Q9)
    assert round_display(v, 2, "DOWN") == Decimal("9.15")


def test_auroc_ks_from_graded_counts():
    auc = execute("AUROC_GRADED", {"defaults": DFT, "obs": OBS}).value
    assert round_display(auc, 4) == Decimal("0.7625")
    assert round_display(execute("AR_FROM_AUROC", {"auroc": auc}).value, 2) == Decimal("52.49")
    assert round_display(execute("KS_GRADED", {"defaults": DFT, "obs": OBS}).value, 2) == Decimal("39.41")


def test_growth_and_scale():
    g = execute("GROWTH_RATE", {"v0": 110_860_000, "v1": 115_340_000}).value
    assert round_display(g, 2) == Decimal("4.04")
    assert round_display(Decimal(115_340_000), 2, scale=1_000_000) == Decimal("115.34")


def test_band_and_errors():
    r = execute("BAND", {"value": 0.082, "bands": [{"max": 0.1, "label": "안정", "severity": "info"}, {"max": None, "label": "불안정"}]})
    assert r.extra["verdict"] == "안정"
    with pytest.raises(FormulaError):
        execute("SHARE", {"numerator": 1, "denominator": 0})
    with pytest.raises(FormulaError):
        execute("NOPE", {})


def test_tool_schemas_cover_registry():
    names = {t["function"]["name"] for t in tool_schemas()}
    assert "calc_default_rate" in names and "calc_psi" in names


def test_range_rec_clamps_to_ceiling():
    r = execute("RANGE_REC", {"base": 7.0, "low_delta": 0.5, "high_delta": 1.0, "ceiling": 8.0})
    assert (r.value, r.extra["low"], r.extra["high"], r.extra["clamped"]) == (Decimal("7.75"), Decimal("7.5"), Decimal("8.0"), False)
    r = execute("RANGE_REC", {"base": 8.0, "low_delta": 0.5, "high_delta": 1.0, "ceiling": 8.0})
    assert r.value == Decimal("8.0") and r.extra["clamped"] is True
    r = execute("RANGE_REC", {"base": 4.0, "low_delta": -1.0, "high_delta": -0.5, "floor": 0})
    assert (r.extra["low"], r.extra["high"]) == (Decimal("3.0"), Decimal("3.5"))


def test_proposal_impact_formulas():
    """Q15 · Q17 추천안 수식 — 정의서 목업값 재현 (기업 RWA 86.4% · 가계 RWA 96.2% · 포용금융 3.1~3.3조)."""
    rec = execute("RANGE_REC", {"base": 7.0, "low_delta": 0.5, "high_delta": 1.0, "ceiling": 8.0}).value
    growth = execute("GROWTH_RATE", {"v0": 110_860_000, "v1": 115_340_000}).value
    inc = execute("PCT_AMOUNT", {"base": 115_340_000, "rate": rec - growth, "divisor": 1_000_000}).value
    assert round_display(execute("PROPOSED_USAGE", {"used": 3.42, "increment": inc, "factor": 0.19, "limit": 4.9}).value, 1) == Decimal("86.4")
    sup = execute("GROWTH_RANGE_REC", {"base": 2_950_000, "low_rt": 5, "high_rt": 12})
    assert (round_display(sup.extra["low"], 2, scale=1_000_000), round_display(sup.extra["high"], 2, scale=1_000_000)) == (Decimal("3.10"), Decimal("3.30"))
    net = execute("PCT_AMOUNT", {"base": sup.value - 2_950_000, "rate": 100, "divisor": 1_000_000}).value
    assert round_display(execute("PROPOSED_USAGE", {"used": 2.86, "increment": net, "factor": 0.49, "limit": 3.1}).value, 1) == Decimal("96.2")
    assert round_display(execute("LINEAR", {"a": 7.4, "b": 0.75, "c": 0.3}).value, 1) == Decimal("7.6")


# ── 영업점 시나리오 수식 (B.29) ──────────────────────────────
def test_branch_portfolio_formulas():
    assert disp("MEAN", {"values": [1, 2, 6]}, 2) == Decimal("3.00")
    assert disp("WEIGHTED_AVG", {"values": [2, 10], "weights": [300, 100]}, 2) == Decimal("4.00")
    assert disp("BLEND_AVG", {"avg_a": 8, "w_a": 900, "avg_b": 3, "w_b": 100}, 2) == Decimal("7.50")
    r = execute("MIN_OF", {"a": 490, "b": 427, "c": 687})
    assert r.value == Decimal(427) and r.extra["binding"] == "b"
    assert disp("CEIL_DIV", {"a": 427, "b": 22.9}, 0) == Decimal(19)
    # (c + x) / (T + x) = t → x = (t·T − c)/(1 − t): T=1000, c=5, t=2% → 15.306…
    assert disp("SHARE_GAP_AMOUNT", {"current": 5, "total": 1000, "target_share": 2}, 3) == Decimal("15.306")
    assert disp("SHARE_GAP_AMOUNT", {"current": 50, "total": 1000, "target_share": 2}, 0) == Decimal(0)  # 이미 목표 이상
    assert disp("KPI_PROPORTIONAL_SCORE", {"actual": 6000, "target": 60000, "points": 40}, 1) == Decimal("4.0")
    assert disp("KPI_PROPORTIONAL_SCORE", {"actual": 6000, "target": 60000, "points": 40, "add": 99000}, 1) == Decimal("40.0")  # 배점 상한


def test_prospect_select_filters_and_weights():
    from nhdip.seed.defs_branch import GRADE_LABELS, RULES

    pol = {r[0]: r[4] for r in RULES}
    office = {"region": "경기", "sigungu": "수원시"}
    branch_rows = [{"ln_bac": 90, "STD_INDS_CFC": "G46510"}, {"ln_bac": 10, "STD_INDS_CFC": "C29199"}]

    def p(nm, grade, ind, sig="수원시 영통구", liab=50, eq=100, model="12", asset=1000):
        return {"corp_nm": nm, "exp_grade": grade, "ind_cd": ind, "region": "경기", "sigungu": sig, "tot_liab": liab, "tot_equity": eq, "nics_model": model, "tot_asset": asset}

    rows = [p("A", "2B", "C21210"), p("B", "4A", "C26299"), p("C", "2A", "G46520"), p("D", "3A", "C21999"), p("E", "3B", "J58222", liab=300), p("F", "1", "C27199", sig="화성시"), p("G", "3B", "C29199", model="13")]
    r = execute("PROSPECT_SELECT", {"prospects": rows, "branch_rows": branch_rows, "office": office, "policy": pol["BRANCH_PROSPECT_POLICY"], "weights": pol["BRANCH_PRIME_CORP_POLICY"]["weights"], "grade_scale": GRADE_LABELS})
    names = [s["corp_nm"] for s in r.extra["selected"]]
    # B 등급 초과 · C 지점 집중 업종(G46) · D 업종 중복(C21) · E 부채비율 · F 지역 외 → A, G (C29 는 10% → 집중 업종이라 제외)
    assert "G46" in r.extra["overlap_industries"] and "C29" in r.extra["overlap_industries"]
    assert names == ["A"] and r.value == Decimal(1)
    assert r.extra["excluded"] == {"existing": 0, "region": 1, "grade": 1, "debt": 1, "overlap": 2, "duplicate": 1, "limit": 0}
    assert r.extra["weighted_mn"] == Decimal(3000) * Decimal("1.5")
