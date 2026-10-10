"""커널 경계 · 오류 경로 (CI 커버리지 게이트 — 계산 커널 90%, 작업 0.4). DB 불필요."""
from decimal import Decimal

import pytest

from nhdip.calc import FormulaError, execute, round_display
from nhdip.calc.formulas import D, arr, catalog, get


@pytest.mark.parametrize("bad", [None, "", "abc"])
def test_decimal_conversion_errors(bad):
    with pytest.raises(FormulaError):
        D(bad)


def test_decimal_conversion_variants():
    assert D(Decimal("1.5")) == Decimal("1.5")
    assert D(0.1) == Decimal("0.1")  # float 는 repr 기준(이진 오차 제거)
    assert D(" 1,234.5 ") == Decimal("1234.5")


def test_array_conversion_errors():
    with pytest.raises(FormulaError):
        arr(3)
    with pytest.raises(FormulaError):
        arr(["1", "x"])
    assert list(arr(["1,000", 2])) == [1000.0, 2.0]


@pytest.mark.parametrize(
    "formula,inputs",
    [
        ("SHARE", {"numerator": 1, "denominator": 0}),
        ("RATIO", {"a": 1, "b": 0}),
        ("GROWTH_RATE", {"v0": 0, "v1": 1}),
        ("USAGE_RATE", {"used": 1, "limit": 0}),
        ("AR_DECLINE", {"ar_dev": 0, "ar_now": 1}),
        ("PROPOSED_USAGE", {"used": 1, "increment": 1, "factor": 1, "limit": 0}),
        ("PCT_AMOUNT", {"base": 1, "rate": 1, "divisor": "0"}),
        ("PSI", {"base": [50, 50], "current": [100]}),
        ("CHI_SQUARE_PD", {"obs": [1, 2], "defaults": [0], "pd": [1, 2]}),
        ("MONOTONIC_BREAKS", {"labels": ["A"], "rates": [1, 2]}),
        ("AUROC_GRADED", {"defaults": [5], "obs": [3]}),
    ],
)
def test_formula_error_paths(formula, inputs):
    with pytest.raises(FormulaError):
        execute(formula, inputs)


def test_unknown_formula_and_input():
    with pytest.raises(FormulaError):
        get("NOPE")
    with pytest.raises(FormulaError):
        execute("SUM", {"values": [1], "extra": 1})


def test_simple_formulas():
    assert execute("VALUE", {"value": "7.5"}).value == Decimal("7.5")
    assert execute("SUM", {"values": 3}).value == Decimal(3)
    assert execute("DIFF", {"a": 5, "b": 2}).value == Decimal(3)
    assert execute("SHARE_DELTA_PP", {"share1": 9.16, "share0": 7.97}).value == Decimal("1.19")
    assert execute("RATIO", {"a": 1, "b": 4}).value == Decimal("0.25")
    assert execute("LINEAR", {"a": 7.4, "b": 0.5, "c": 0.3}).value == Decimal("7.55")
    assert execute("PCT_AMOUNT", {"base": 200, "rate": 5}).value == Decimal(10)


def test_band_no_match_and_range_floor():
    r = execute("BAND", {"value": 5, "bands": [{"max": 1, "label": "a", "severity": "info"}]})
    assert r.value == Decimal(5) and r.extra["verdict"] is None
    r = execute("RANGE_REC", {"base": 1, "low_delta": 1, "high_delta": -1, "floor": 1.5})
    assert r.extra["low"] == Decimal("1.5") and r.extra["clamped"]
    r = execute("RANGE_REC", {"base": 10, "low_delta": 1, "high_delta": 2, "ceiling": 9})
    assert r.extra["high"] == Decimal(9) and r.extra["low"] == Decimal(9)
    r = execute("GROWTH_RANGE_REC", {"base": 100, "low_rt": 12, "high_rt": 5})
    assert r.extra["low"] == Decimal(105)


def test_round_display_modes():
    assert round_display(None, 2) is None
    assert round_display(Decimal("1.2345"), None) == Decimal("1.2345")
    assert round_display(Decimal("12345"), 2, scale=10000) == Decimal("1.23")
    assert round_display(Decimal("2.5"), 0, "HALF_EVEN") == Decimal(2)
    assert round_display(Decimal("2.5"), 0, "HALF_UP") == Decimal(3)


def test_catalog_lists_every_formula():
    ids = {c["id"] for c in catalog()}
    assert {"SUM", "PSI", "CHI_SQUARE_PD", "AR_DECLINE", "RANGE_REC"} <= ids


def test_cagr():
    r = execute("CAGR", {"v_start": 106_240_000, "v_end": 115_340_000, "years": 2})
    assert round_display(r.value, 2) == Decimal("4.19")
    for bad in ({"v_start": 0, "v_end": 1, "years": 1}, {"v_start": 1, "v_end": 1, "years": 0}):
        with pytest.raises(FormulaError):
            execute("CAGR", bad)


def test_goal_range_rec_stance_trend_and_clamps():
    up = execute("GOAL_RANGE_REC", {"base": 7, "stance": 1, "low_delta": 0.5, "high_delta": 1.0, "ceiling": 8.0})
    assert (up.extra["low"], up.extra["high"], up.value) == (Decimal("7.5"), Decimal("8.0"), Decimal("7.75")) and up.extra["direction"] == "expand"
    down = execute("GOAL_RANGE_REC", {"base": 4, "stance": -1, "low_delta": 0.5, "high_delta": 1.0, "floor": 0})
    assert (down.extra["low"], down.extra["high"]) == (Decimal("3.0"), Decimal("3.5")) and down.extra["direction"] == "control"
    keep = execute("GOAL_RANGE_REC", {"base": 5, "stance": 0, "low_delta": 1.0, "high_delta": 0.5})
    assert (keep.extra["low"], keep.extra["high"]) == (Decimal("4.5"), Decimal("5.5"))
    blend = execute("GOAL_RANGE_REC", {"base": 7, "stance": 1, "low_delta": 0.5, "high_delta": 1.0, "trend": 4, "trend_weight": 0.5, "ceiling": 6})
    assert blend.extra["anchor"] == Decimal("5.5") and blend.extra["high"] == Decimal(6) and blend.extra["clamped"] == ["ceiling"]
    low = execute("GOAL_RANGE_REC", {"base": 0.3, "stance": -1, "low_delta": 0.5, "high_delta": 1.0, "floor": 0})
    assert low.extra["low"] == Decimal(0) and low.extra["high"] == Decimal(0) and low.extra["clamped"] == ["floor"]
    with pytest.raises(FormulaError):
        execute("GOAL_RANGE_REC", {"base": 1, "stance": 1, "low_delta": 1, "high_delta": 1, "trend": 1, "trend_weight": 2})


def test_bis_sim_and_attention_score():
    r = execute("BIS_RATIO_SIM", {"bis_now": 14.8, "rwa_now": 100, "rwa_increment": 1.0, "min_ratio": 13})
    assert round_display(r.value, 2) == Decimal("14.65") and round_display(r.extra["margin_bp"], 0) == Decimal(165)
    with pytest.raises(FormulaError):
        execute("BIS_RATIO_SIM", {"bis_now": 1, "rwa_now": 0, "rwa_increment": 0, "min_ratio": 1})
    s = execute("ATTENTION_SCORE", {"components": [{"label": "이탈", "value": -2.96, "per_unit": 11.55, "max": 40}, {"label": "중요도", "points": 25}, {"label": "상한", "value": 10, "per_unit": 10, "max": 40}]})
    assert s.value == Decimal("99.2") and [p["points"] for p in s.extra["parts"]] == [Decimal("34.2"), Decimal("25.0"), Decimal("40")]
    for bad in ([], [1]):
        with pytest.raises(FormulaError):
            execute("ATTENTION_SCORE", {"components": bad})
