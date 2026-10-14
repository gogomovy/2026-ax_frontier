"""계산 커널 수식 레지스트리 (CALC-01, CALC-09).

원칙
- 모든 수치는 여기서 계산한다. LLM 은 계산하지 않는다(서술만).
- 스칼라 산술은 decimal(28자리), 통계는 numpy · scipy · scikit-learn.
- 반올림은 표시 단계에서만(kernel.round_display) — 내부 값은 보존한다.
- 수식은 버전을 가진다. 수식을 바꾸면 version 을 올리고 과거 calc_run 은 당시 버전으로 남는다.

새 수식은 @formula 로 등록하면 관리자 화면 · 지표 정의 · LLM 도구(CALC-10) 에 자동 노출된다.
"""
from __future__ import annotations

import re

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, getcontext
from typing import Any, Callable

import numpy as np
from scipy import stats
from sklearn.metrics import roc_auc_score

getcontext().prec = 28


class FormulaError(ValueError):
    pass


@dataclass
class FormulaSpec:
    id: str
    version: int
    expression: str
    description: str
    params: dict[str, str]  # 이름 → 설명 (타입 힌트 포함)
    fn: Callable[..., Any]
    library: str = "decimal"
    tool_enabled: bool = True
    returns: str = "scalar"  # scalar | object | list
    examples: list[dict[str, Any]] = field(default_factory=list)


REGISTRY: dict[str, FormulaSpec] = {}


def formula(id: str, *, version: int = 1, expression: str, description: str, params: dict[str, str], library: str = "decimal", returns: str = "scalar", tool_enabled: bool = True):
    def deco(fn):
        REGISTRY[id] = FormulaSpec(id, version, expression, description, params, fn, library, tool_enabled, returns)
        return fn

    return deco


# ── 형 변환 ───────────────────────────────────────────────────
def D(v: Any) -> Decimal:
    if v is None or v == "":
        raise FormulaError("값이 비어 있습니다")
    if isinstance(v, Decimal):
        return v
    if isinstance(v, float):
        return Decimal(repr(v))
    if isinstance(v, str):
        v = v.replace(",", "").strip()
    try:
        return Decimal(str(v))
    except Exception as exc:  # noqa: BLE001
        raise FormulaError(f"숫자로 변환할 수 없습니다: {v!r}") from exc


def arr(v: Any) -> np.ndarray:
    if not isinstance(v, (list, tuple, np.ndarray)):
        raise FormulaError("목록 값이 필요합니다")
    try:
        return np.asarray([float(str(x).replace(",", "")) for x in v], dtype=float)
    except ValueError as exc:
        raise FormulaError(f"숫자 목록으로 변환할 수 없습니다: {exc}") from exc


# ═════════════════════════ 기본 산술 ═════════════════════════
@formula("VALUE", expression="값 그대로", description="원천 값을 그대로 사용(단위 환산은 지표 scale)", params={"value": "number"})
def f_value(value):
    return D(value)


@formula("SUM", expression="Σ 값", description="합계", params={"values": "number[]"})
def f_sum(values):
    if not isinstance(values, (list, tuple)):
        return D(values)
    return sum((D(v) for v in values), Decimal(0))


@formula("DIFF", expression="a − b", description="차이(증감, 목표 대비 이탈 등)", params={"a": "number", "b": "number"})
def f_diff(a, b):
    return D(a) - D(b)


@formula("SHARE_DELTA_PP", expression="비교시점 비중 − 기준시점 비중", description="비중 증감(%p)", params={"share1": "number(%)", "share0": "number(%)"})
def f_share_delta(share1, share0):
    return D(share1) - D(share0)


@formula("SHARE", expression="분자 ÷ 분모 × 100", description="구성비·비중(%)", params={"numerator": "number", "denominator": "number"})
def f_share(numerator, denominator):
    den = D(denominator)
    if den == 0:
        raise FormulaError("분모가 0 입니다")
    return D(numerator) / den * 100


@formula("RATIO", expression="a ÷ b", description="비율", params={"a": "number", "b": "number"})
def f_ratio(a, b):
    den = D(b)
    if den == 0:
        raise FormulaError("분모가 0 입니다")
    return D(a) / den


@formula("GROWTH_RATE", expression="(당기 − 전기) ÷ |전기| × 100", description="증가율(%)", params={"v0": "number(전기)", "v1": "number(당기)"})
def f_growth(v0, v1):
    base = D(v0)
    if base == 0:
        raise FormulaError("전기 값이 0 입니다")
    return (D(v1) - base) / abs(base) * 100


@formula("USAGE_RATE", expression="사용 ÷ 한도 × 100", description="소진율(%)", params={"used": "number", "limit": "number"})
def f_usage(used, limit):
    return f_share(used, limit)


# ═════════════════════════ 신용리스크 ═════════════════════════
@formula("DEFAULT_RATE", expression="부도건수 ÷ 관측건수 × 100", description="실제부도율(%)", params={"default_count": "number", "obs_count": "number"})
def f_default_rate(default_count, obs_count):
    return f_share(default_count, obs_count)


@formula(
    "PD_BREACH_CHECK",
    expression="실제부도율 − 예측부도율 대표값 (판정: within_mid / above_mid_within_max / above_max)",
    description="등급별 예측부도율 대비 판정 — 값은 대표값 초과 폭(%p)",
    params={"actual_dr": "number(%)", "pd_mid": "number(%)", "pd_max": "number(%)"},
    returns="object",
)
def f_pd_breach(actual_dr, pd_mid, pd_max):
    a, mid, mx = D(actual_dr), D(pd_mid), D(pd_max)
    verdict = "within_mid" if a <= mid else ("above_mid_within_max" if a <= mx else "above_max")
    return {"value": a - mid, "verdict": verdict}


@formula(
    "MONOTONIC_BREAKS",
    expression="등급 k 의 부도율 < 등급 k−1 의 부도율 인 k",
    description="서열화(단조성) 위반 등급 목록",
    params={"labels": "string[]", "rates": "number[]"},
    library="numpy",
    returns="object",
)
def f_monotonic(labels, rates):
    r = arr(rates)
    if len(labels) != len(r):
        raise FormulaError("등급 수와 부도율 수가 다릅니다")
    breaks = [labels[k] for k in range(1, len(r)) if r[k] < r[k - 1]]
    return {"value": Decimal(len(breaks)), "breaks": breaks}


@formula(
    "PSI",
    expression="Σ (실제비중 − 기준비중) · ln(실제비중 ÷ 기준비중)",
    description="모집단 안정성 지수 — 비중은 % 입력, 0 비중은 ε 보정",
    params={"base": "number[](%)", "current": "number[](%)", "eps": "number(기본 1e-6)"},
    library="numpy",
    returns="object",
)
def f_psi(base, current, eps=1e-6):
    b, c = arr(base) / 100.0, arr(current) / 100.0
    if len(b) != len(c):
        raise FormulaError("구간 수가 다릅니다")
    e = float(eps or 1e-6)
    contrib = (c - b) * np.log(np.clip(c, e, None) / np.clip(b, e, None))
    return {"value": D(float(contrib.sum())), "contributions": [float(x) for x in contrib]}


@formula(
    "CHI_SQUARE_PD",
    expression="χ² = Σ (rᵢ − nᵢ·pᵢ)² ÷ (nᵢ·pᵢ·(1 − pᵢ))",
    description="등급계량화 검정 통계량(Hosmer-Lemeshow 형) — pd 는 % 입력",
    params={"obs": "number[]", "defaults": "number[]", "pd": "number[](%)"},
    library="numpy",
    returns="object",
)
def f_chi_square(obs, defaults, pd):
    n, r, p = arr(obs), arr(defaults), arr(pd) / 100.0
    if not (len(n) == len(r) == len(p)):
        raise FormulaError("등급 수가 다릅니다")
    expected = n * p
    with np.errstate(divide="ignore", invalid="ignore"):
        terms = np.where(expected * (1 - p) > 0, (r - expected) ** 2 / (expected * (1 - p)), 0.0)
    return {"value": D(float(terms.sum())), "df": int(len(n)), "terms": [float(x) for x in terms]}


@formula(
    "CHI2_CRITICAL",
    expression="χ²⁻¹(신뢰수준; 자유도)",
    description="카이제곱 임계값 (scipy.stats.chi2.ppf)",
    params={"df": "integer", "confidence": "number(0~1)"},
    library="scipy",
)
def f_chi_critical(df, confidence=0.95):
    return D(float(stats.chi2.ppf(float(confidence), int(df))))


@formula(
    "CHI2_TEST",
    expression="χ² ≤ 임계값 → 귀무가설 채택",
    description="카이제곱 검정 판정 — 값은 1(채택)/0(기각)",
    params={"stat": "number", "critical": "number"},
    returns="object",
)
def f_chi_test(stat, critical):
    accepted = D(stat) <= D(critical)
    return {"value": Decimal(1 if accepted else 0), "verdict": "accepted" if accepted else "rejected"}


def _graded(defaults, obs):
    dft, n = arr(defaults), arr(obs)
    if len(dft) == 0 or len(n) == 0:
        raise FormulaError("등급 자료가 없습니다 — 이 구분(모형)의 행이 올라오지 않았습니다")
    if len(dft) != len(n):
        raise FormulaError("부도건수 · 관측건수 등급 수가 다릅니다")
    good = n - dft
    if (good < 0).any():
        raise FormulaError("부도건수가 관측건수보다 큽니다")
    return dft, good


@formula(
    "AUROC_GRADED",
    expression="ROC 곡선 아래 면적 (등급 서열을 점수로, 등급별 부도·정상 건수를 가중치로)",
    description="집계 등급 자료 기준 AUROC (sklearn.metrics.roc_auc_score)",
    params={"defaults": "number[](우량→불량 등급순)", "obs": "number[]"},
    library="scikit-learn",
)
def f_auroc(defaults, obs):
    dft, good = _graded(defaults, obs)
    k = len(dft)
    score = np.repeat(np.arange(k), 2)
    label = np.tile([1, 0], k)
    weight = np.column_stack([dft, good]).ravel()
    return D(float(roc_auc_score(label, score, sample_weight=weight)))


@formula("AR_FROM_AUROC", expression="(2 · AUROC − 1) × 100", description="Accuracy Ratio(%)", params={"auroc": "number"})
def f_ar(auroc):
    return (2 * D(auroc) - 1) * 100


@formula(
    "KS_GRADED",
    expression="max |F_부도(k) − F_정상(k)| × 100",
    description="K-S 통계량(%) — 등급 누적분포 기준",
    params={"defaults": "number[]", "obs": "number[]"},
    library="numpy",
)
def f_ks(defaults, obs):
    dft, good = _graded(defaults, obs)
    cb, cg = np.cumsum(dft) / dft.sum(), np.cumsum(good) / good.sum()
    return D(float(np.max(np.abs(cb - cg)) * 100))


@formula(
    "AR_DECLINE",
    expression="(개발시점 AR − 현재 AR) ÷ 개발시점 AR × 100",
    description="AR 하락률(%)",
    params={"ar_dev": "number", "ar_now": "number"},
)
def f_ar_decline(ar_dev, ar_now):
    dev = D(ar_dev)
    if dev == 0:
        raise FormulaError("개발시점 AR 이 0 입니다")
    return (dev - D(ar_now)) / dev * 100


@formula(
    "BAND",
    expression="값이 속하는 구간 (규칙의 bands: [{max, label, severity}])",
    description="임계값 구간 판정 — 규칙(rule)으로 구간을 관리",
    params={"value": "number", "bands": "object[]"},
    returns="object",
)
def f_band(value, bands):
    v = D(value)
    for band in bands or []:
        mx = band.get("max")
        if mx is None or v <= D(mx):
            return {"value": v, "verdict": band.get("label"), "severity": band.get("severity")}
    return {"value": v, "verdict": None, "severity": None}


@formula(
    "RANGE_REC",
    expression="[기준 + 하한폭, 기준 + 상한폭] 을 [하한, 상한] 으로 clamp → 값 = 범위 중앙",
    description="목표 추천 범위(규칙 기반, Phase 2.6) — 폭·상한은 규칙에서 관리",
    params={"base": "number", "low_delta": "number", "high_delta": "number", "ceiling": "number(기본 없음)", "floor": "number(기본 없음)"},
    returns="object",
)
def f_range_rec(base, low_delta, high_delta, ceiling=None, floor=None):
    b = D(base)
    lo, hi = b + D(low_delta), b + D(high_delta)
    if lo > hi:
        lo, hi = hi, lo
    clamped = False
    if ceiling not in (None, ""):
        c = D(ceiling)
        if hi > c:
            hi, clamped = c, True
        if lo > c:
            lo, clamped = c, True
    if floor not in (None, ""):
        f = D(floor)
        if lo < f:
            lo, clamped = f, True
        if hi < f:
            hi, clamped = f, True
    return {"value": (lo + hi) / 2, "low": lo, "high": hi, "clamped": clamped}


@formula(
    "GROWTH_RANGE_REC",
    expression="[기준 × (1 + 하한율/100), 기준 × (1 + 상한율/100)] → 값 = 범위 중앙",
    description="증가율 범위로 금액 목표 추천(예: 전년 공급 실적 × 성장 범위)",
    params={"base": "number", "low_rt": "number(%)", "high_rt": "number(%)"},
    returns="object",
)
def f_growth_range_rec(base, low_rt, high_rt):
    b = D(base)
    lo, hi = b * (1 + D(low_rt) / 100), b * (1 + D(high_rt) / 100)
    if lo > hi:
        lo, hi = hi, lo
    return {"value": (lo + hi) / 2, "low": lo, "high": hi}


@formula(
    "PROPOSED_USAGE",
    expression="(현재 사용 + 증가분 × 환산계수) ÷ 한도 × 100",
    description="제안 반영 후 한도 소진율(%) — 예: 기업여신 증가분 × RWA 환산계수",
    params={"used": "number", "increment": "number", "factor": "number", "limit": "number"},
)
def f_proposed_usage(used, increment, factor, limit):
    lim = D(limit)
    if lim == 0:
        raise FormulaError("한도가 0 입니다")
    return (D(used) + D(increment) * D(factor)) / lim * 100


@formula(
    "PCT_AMOUNT",
    expression="기준 × 비율(%) ÷ 100 ÷ 단위",
    description="비율만큼의 금액(예: 기업여신 잔액 × 증가율 차이 → 증가분, 단위 환산)",
    params={"base": "number", "rate": "number(%)", "divisor": "number(기본 1)"},
)
def f_pct_amount(base, rate, divisor=1):
    d = D(divisor or 1)
    if d == 0:
        raise FormulaError("단위가 0 입니다")
    return D(base) * D(rate) / 100 / d


@formula(
    "LINEAR",
    expression="a + b × c",
    description="가산 산식(예: 목표 총자산증가율 + 기업여신 목표 변화 × 자산 비중)",
    params={"a": "number", "b": "number", "c": "number"},
)
def f_linear(a, b, c):
    return D(a) + D(b) * D(c)


@formula(
    "CAGR",
    expression="((종료값 ÷ 시작값)^(1 ÷ 기간) − 1) × 100",
    description="연평균 성장률(%) — 3개년 추세 밴드의 기준(Phase 2.6.4)",
    params={"v_start": "number", "v_end": "number", "years": "number"},
)
def f_cagr(v_start, v_end, years):
    a, b, n = D(v_start), D(v_end), D(years)
    if a <= 0 or b <= 0:
        raise FormulaError("시작값 · 종료값은 0 보다 커야 합니다")
    if n <= 0:
        raise FormulaError("기간은 0 보다 커야 합니다")
    return (Decimal(str((float(b) / float(a)) ** (1.0 / float(n)))) - 1) * 100


@formula(
    "GOAL_RANGE_REC",
    expression="기준점 = 현재 목표 + w × (추세 − 현재 목표) → 기조 방향으로 [기준점 ± 폭] → [하한, 상한] clamp → 값 = 범위 중앙",
    description="경영목표 추천 범위(Phase 2.6) — 기조(stance: +1 확대 · −1 관리 · 0 유지) · 추세 가중치 · 폭 · 제약 상하한은 규칙/지표로 관리",
    params={
        "base": "number(현재 목표)",
        "stance": "number(+1 · −1 · 0)",
        "low_delta": "number(폭 하한, 양수)",
        "high_delta": "number(폭 상한, 양수)",
        "trend": "number(추세, 예: CAGR · 선택)",
        "trend_weight": "number(0~1, 기본 0)",
        "ceiling": "number(제약 상한 · 선택)",
        "floor": "number(제약 하한 · 선택)",
    },
    returns="object",
)
def f_goal_range_rec(base, stance, low_delta, high_delta, trend=None, trend_weight=0, ceiling=None, floor=None):
    b = D(base)
    w = D(trend_weight or 0)
    if w < 0 or w > 1:
        raise FormulaError("추세 가중치는 0~1 입니다")
    anchor = b + w * (D(trend) - b) if trend not in (None, "") and w else b
    lo_d, hi_d = abs(D(low_delta)), abs(D(high_delta))
    if lo_d > hi_d:
        lo_d, hi_d = hi_d, lo_d
    st = D(stance)
    if st > 0:
        lo, hi, direction = anchor + lo_d, anchor + hi_d, "expand"
    elif st < 0:
        lo, hi, direction = anchor - hi_d, anchor - lo_d, "control"
    else:
        lo, hi, direction = anchor - lo_d, anchor + lo_d, "maintain"
    clamped = []
    if ceiling not in (None, ""):
        c = D(ceiling)
        if hi > c:
            hi = c
            clamped.append("ceiling")
        if lo > c:
            lo = c
    if floor not in (None, ""):
        f = D(floor)
        if lo < f:
            lo = f
            clamped.append("floor")
        if hi < f:
            hi = f
    return {"value": (lo + hi) / 2, "low": lo, "high": hi, "anchor": anchor, "direction": direction, "clamped": clamped}


@formula(
    "BIS_RATIO_SIM",
    expression="현재 BIS 비율 × 현재 RWA ÷ (현재 RWA + RWA 증가분) → 관리기준 대비 여유(bp)",
    description="BIS 총자본비율 시산(Phase 6.2.4) — 자본 불변 가정. RWA 총량이 없으면 시산 불가",
    params={"bis_now": "number(%)", "rwa_now": "number", "rwa_increment": "number", "min_ratio": "number(%)"},
    returns="object",
)
def f_bis_sim(bis_now, rwa_now, rwa_increment, min_ratio):
    rwa = D(rwa_now)
    total = rwa + D(rwa_increment)
    if rwa <= 0 or total <= 0:
        raise FormulaError("RWA 는 0 보다 커야 합니다")
    ratio = D(bis_now) * rwa / total
    return {"value": ratio, "margin_bp": (ratio - D(min_ratio)) * 100}


@formula(
    "ATTENTION_SCORE",
    expression="Σ 항목 점수 — 수치 항목 = min(|값| × 단위당 점수, 상한), 정성 항목 = 규칙의 고정 점수",
    description="AI Attention 우선순위 점수(Phase 2.5.4) — 항목 · 가중치는 규칙 ATTENTION_SCORE 에서 관리",
    params={"components": "object[]"},
    returns="object",
)
def f_attention_score(components):
    if not isinstance(components, (list, tuple)) or not components:
        raise FormulaError("점수 항목이 필요합니다")
    parts, total = [], Decimal(0)
    for c in components:
        if not isinstance(c, dict):
            raise FormulaError("점수 항목 형식이 올바르지 않습니다")
        if c.get("points") is not None:
            pts = D(c["points"])
        else:
            v = abs(D(c.get("value")))
            pts = v * D(c.get("per_unit", 1))
            if c.get("max") is not None:
                pts = min(pts, D(c["max"]))
        pts = pts.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)  # Q9 사사오입
        total += pts
        parts.append({"label": c.get("label", ""), "points": pts, "value": c.get("value"), "text": c.get("text")})
    return {"value": total, "parts": parts}


# ═════════════════════════ 영업점 업적평가 · 포트폴리오 (B.29) ═════════════════════════
SEVERITY_ORDER = ["info", "watch", "caution", "critical"]


@formula(
    "VERDICT",
    expression="판정들 중 가장 심각한 수준 → 규칙의 판정 문구 (info < watch < caution < critical)",
    description="종합 판정 — 여러 구간 판정(BAND)의 심각도 중 가장 높은 것을 고르고 규칙의 문구로 표시. 값은 심각도 순번(0~3)",
    params={"sev_a": "string(심각도)", "sev_b": "string(기본 없음)", "sev_c": "string(기본 없음)", "labels": "object(심각도 → 문구)"},
    returns="object",
)
def f_verdict(sev_a, sev_b=None, sev_c=None, labels=None):
    sevs = [s for s in (sev_a, sev_b, sev_c) if s]
    bad = [s for s in sevs if s not in SEVERITY_ORDER]
    if bad:
        raise FormulaError(f"알 수 없는 심각도: {bad}")
    if not sevs:
        raise FormulaError("판정 입력이 없습니다")
    worst = max(sevs, key=SEVERITY_ORDER.index)
    return {"value": Decimal(SEVERITY_ORDER.index(worst)), "verdict": (labels or {}).get(worst, worst), "severity": worst}


@formula("GROWTH_APPLY", expression="기준 × (1 + 증가율 ÷ 100)", description="증가율 적용 추정(예: 전년 말 잔액 × (1 + 제안 증가율) = 연말 추정 잔액)", params={"base": "number", "rate": "number(%)"})
def f_growth_apply(base, rate):
    return D(base) * (1 + D(rate) / 100)


@formula("MEAN", expression="Σ 값 ÷ 개수", description="단순 평균(예: 차주 수 기준 평균 신용등급)", params={"values": "number[]"})
def f_mean(values):
    vals = [D(v) for v in (values or []) if v not in (None, "")]
    if not vals:
        raise FormulaError("평균할 값이 없습니다")
    return sum(vals, Decimal(0)) / len(vals)


@formula("WEIGHTED_AVG", expression="Σ(값 × 가중치) ÷ Σ 가중치", description="가중평균(예: 대출잔액 가중 평균 신용등급)", params={"values": "number[]", "weights": "number[]"})
def f_weighted_avg(values, weights):
    if not isinstance(values, (list, tuple)) or not isinstance(weights, (list, tuple)) or len(values) != len(weights):
        raise FormulaError("값과 가중치 목록의 길이가 같아야 합니다")
    num, den = Decimal(0), Decimal(0)
    for v, w in zip(values, weights):
        if v in (None, "") or w in (None, ""):
            continue
        num += D(v) * D(w)
        den += D(w)
    if den == 0:
        raise FormulaError("가중치 합이 0 입니다")
    return num / den


@formula("BLEND_AVG", expression="(평균a × 가중a + 평균b × 가중b) ÷ (가중a + 가중b)", description="두 집단을 합친 가중평균(예: 신규 유치 후 포트폴리오 평균 등급)", params={"avg_a": "number", "w_a": "number", "avg_b": "number", "w_b": "number"})
def f_blend_avg(avg_a, w_a, avg_b, w_b):
    wa, wb = D(w_a), D(w_b)
    if wa + wb == 0:
        raise FormulaError("가중치 합이 0 입니다")
    return (D(avg_a) * wa + D(avg_b) * wb) / (wa + wb)


@formula("MIN_OF", expression="min(a, b, c)", description="여러 한도 중 가장 작은 값(예: 권고 유치 규모 = 비중 · 충당금 · 건수 한도 중 최소)", params={"a": "number", "b": "number", "c": "number(기본 없음)"}, returns="object")
def f_min_of(a, b, c=None):
    cands = [("a", D(a)), ("b", D(b))] + ([("c", D(c))] if c not in (None, "") else [])
    key, val = min(cands, key=lambda x: x[1])
    return {"value": val, "binding": key}


@formula("CEIL_DIV", expression="⌈a ÷ b⌉", description="올림 나눗셈(예: 권고 금액 ÷ 평균 취급액 → 필요 건수)", params={"a": "number", "b": "number"})
def f_ceil_div(a, b):
    den = D(b)
    if den == 0:
        raise FormulaError("분모가 0 입니다")
    return (D(a) / den).to_integral_value(rounding="ROUND_CEILING")


@formula(
    "SHARE_GAP_AMOUNT",
    expression="x = max(0, (t·T − c) ÷ (1 − t)),  t = 목표 비중 × 배수 ÷ 100",
    description="목표 비중에 도달하려면 추가로 늘려야 할 금액 — (c + x) ÷ (T + x) = t 의 해",
    params={"current": "number", "total": "number", "target_share": "number(%)", "factor": "number(기본 1)"},
)
def f_share_gap_amount(current, total, target_share, factor=1):
    t = D(target_share) * D(factor if factor not in (None, "") else 1) / 100
    if t >= 1 or t < 0:
        raise FormulaError("목표 비중은 0% 이상 100% 미만이어야 합니다")
    x = (t * D(total) - D(current)) / (1 - t)
    return max(Decimal(0), x)


@formula(
    "KPI_PROPORTIONAL_SCORE",
    expression="min(배점, 배점 × (실적 + 추가 실적) ÷ 목표)",
    description="업적평가 달성률 비례 득점 — 목표 · 배점은 배점표 · 규칙에서 관리",
    params={"actual": "number", "target": "number", "points": "number", "add": "number(기본 0)"},
)
def f_kpi_proportional(actual, target, points, add=0):
    tgt = D(target)
    if tgt <= 0:
        raise FormulaError("목표가 0 이하입니다")
    pts = D(points)
    return min(pts, pts * (D(actual) + D(add or 0)) / tgt)


def _grade_seq(label: Any, scale: list[str]) -> int | None:
    """등급 표기(1 · 2A · 3B …) 또는 순번(1~16) → 순번. 체계 밖 값은 None."""
    s = str(label).strip().upper() if label is not None else ""
    if s in [x.upper() for x in scale]:
        return [x.upper() for x in scale].index(s) + 1
    try:
        n = int(float(s))
    except ValueError:
        return None
    return n if 1 <= n <= len(scale) else None


def grade_weight(seq: int, weights: list[dict[str, Any]], scale: list[str]) -> tuple[Decimal, str]:
    """등급 순번 → (가중치, 구간 라벨). 구간은 max_grade(이 등급까지) 오름차순."""
    for w in weights or []:
        mx = _grade_seq(w.get("max_grade"), scale)
        if mx is not None and seq <= mx:
            return D(w.get("weight", 1)), str(w.get("label", ""))
    return Decimal(1), ""


def _corp_key(name: Any) -> str:
    """기업명 비교 키 — 공백 · (주) · 주식회사 표기 차이를 무시."""
    s = re.sub(r"\s+", "", str(name or ""))
    return re.sub(r"\(주\)|㈜|주식회사|\(유\)|유한회사", "", s)


@formula(
    "PROSPECT_SELECT",
    expression="지역 일치 → 예상재무등급 ≤ 기준 → 부채비율 ≤ 기준 → 지점 집중 업종 제외 → 업종당 1개 → 등급 · 자산 순 상위 N",
    description="여신가망 재무우량 기업 중 영업점 마케팅 후보 선정 — 값 = 후보 수, 신규 여신 가정액 · 평균 등급 · 등급 가중 실적은 부가 결과",
    params={"prospects": "object[]", "branch_rows": "object[]", "office": "object", "policy": "object", "weights": "object[]", "grade_scale": "string[]", "existing": "string[](선택 · 당행 기존 차주명)"},
    returns="object",
    tool_enabled=False,
)
def f_prospect_select(prospects, branch_rows, office, policy, weights, grade_scale, existing=None):
    if not isinstance(policy, dict) or not isinstance(office, dict):
        raise FormulaError("선정 기준 · 영업점 정보가 필요합니다")
    scale = list(grade_scale or [])
    if not scale:
        raise FormulaError("신용등급 체계가 필요합니다")
    lvl = int(policy.get("industry_level", 3))
    amt_col, ind_col = policy.get("branch_amount_col", "ln_bac"), policy.get("branch_industry_col", "STD_INDS_CFC")
    # 지점 업종 집중도(금액 비중) — 기준 이상 업종은 포트폴리오 분산을 위해 제외
    by_ind: dict[str, Decimal] = {}
    tot = Decimal(0)
    for r in branch_rows or []:
        if r.get(amt_col) in (None, "") or not r.get(ind_col):
            continue
        a = D(r[amt_col])
        by_ind[str(r[ind_col])[:lvl]] = by_ind.get(str(r[ind_col])[:lvl], Decimal(0)) + a
        tot += a
    thr = D(policy.get("overlap_share_pct", 5))
    overlap = sorted(k for k, v in by_ind.items() if tot and v / tot * 100 >= thr)
    max_seq = _grade_seq(policy.get("max_grade", "3B"), scale) or len(scale)
    max_debt = D(policy.get("max_debt_ratio_pct", 200))
    region, sigungu = str(office.get("region") or ""), str(office.get("sigungu") or "")
    sig_list = [x.strip() for x in sigungu.split("|") if x.strip()]
    loan_by_model = {str(k): D(v) for k, v in (policy.get("loan_mn_by_model") or {}).items()}
    default_loan = D(policy.get("default_loan_mn", 1000))
    excluded = {"existing": 0, "region": 0, "grade": 0, "debt": 0, "overlap": 0, "duplicate": 0, "limit": 0}
    # 이미 당행 여신 거래 중인 기업(최근 기준월 차주 명세)은 '미거래 기업' 후보에서 뺀다 (B.40 — 유치 후에도 계속 추천되던 문제)
    known = {_corp_key(n) for n in (existing or []) if n}
    pool = []
    for p in prospects or []:
        if str(p.get("region") or "") != region or not any(str(p.get("sigungu") or "").startswith(s) for s in sig_list):
            excluded["region"] += 1
            continue
        if known and _corp_key(p.get("corp_nm")) in known:
            excluded["existing"] += 1
            continue
        seq = _grade_seq(p.get("exp_grade"), scale)
        if seq is None or seq > max_seq:
            excluded["grade"] += 1
            continue
        eq = D(p.get("tot_equity") or 0)
        debt = D(p.get("tot_liab") or 0) / eq * 100 if eq > 0 else None
        if debt is None or debt > max_debt:
            excluded["debt"] += 1
            continue
        ind = str(p.get("ind_cd") or "")[:lvl]
        if ind in overlap:
            excluded["overlap"] += 1
            continue
        pool.append((seq, -D(p.get("tot_asset") or 0), p, debt, ind))
    pool.sort(key=lambda x: (x[0], x[1], str(x[2].get("corp_nm"))))
    seen: set[str] = set()
    selected = []
    for seq, _, p, debt, ind in pool:
        if policy.get("one_per_industry", True) and ind in seen:
            excluded["duplicate"] += 1
            continue
        if len(selected) >= int(policy.get("max_candidates", 5)):
            excluded["limit"] += 1
            continue
        seen.add(ind)
        loan = loan_by_model.get(str(p.get("nics_model")), default_loan)
        w, band = grade_weight(seq, weights, scale)
        selected.append({"corp_nm": p.get("corp_nm"), "biz_no": p.get("biz_no"), "ind_cd": p.get("ind_cd"), "ind_nm": p.get("ind_nm"), "nics_model": p.get("nics_model"), "corp_scale": p.get("corp_scale"),
                         "sigungu": p.get("sigungu"), "exp_grade": scale[seq - 1], "grade_seq": seq, "tot_asset": D(p.get("tot_asset") or 0), "sales": D(p.get("sales") or 0), "op_income": D(p.get("op_income") or 0),
                         "debt_ratio": debt, "loan_mn": loan, "weight": w, "weight_band": band, "weighted_mn": loan * w})
    if not selected:
        return {"value": Decimal(0), "selected": [], "excluded": excluded, "overlap_industries": overlap, "amount_won": Decimal(0), "weighted_mn": Decimal(0), "avg_grade": None}
    amount = sum((s["loan_mn"] for s in selected), Decimal(0))
    avg = sum((s["loan_mn"] * s["grade_seq"] for s in selected), Decimal(0)) / amount
    return {"value": Decimal(len(selected)), "selected": selected, "excluded": excluded, "overlap_industries": overlap,
            "amount_mn": amount, "amount_won": amount * 1_000_000, "weighted_mn": sum((s["weighted_mn"] for s in selected), Decimal(0)), "avg_grade": avg}


def get(formula_id: str) -> FormulaSpec:
    spec = REGISTRY.get(formula_id)
    if not spec:
        raise FormulaError(f"등록되지 않은 수식: {formula_id}")
    return spec


def catalog() -> list[dict[str, Any]]:
    return [
        {
            "id": s.id,
            "version": s.version,
            "expression": s.expression,
            "description": s.description,
            "params": s.params,
            "library": s.library,
            "returns": s.returns,
            "toolEnabled": s.tool_enabled,
        }
        for s in REGISTRY.values()
    ]


def tool_schemas() -> list[dict[str, Any]]:
    """OpenAI 호환 tools 스키마 (CALC-10 질의 모드)."""

    def ptype(desc: str) -> dict[str, Any]:
        if desc.startswith("number[]") or desc.startswith("string[]") or desc.startswith("object[]"):
            item = {"number[]": "number", "string[]": "string", "object[]": "object"}[desc.split("(")[0]]
            return {"type": "array", "items": {"type": item}, "description": desc}
        if desc.startswith("integer"):
            return {"type": "integer", "description": desc}
        if desc.startswith("string"):
            return {"type": "string", "description": desc}
        return {"type": "number", "description": desc}

    tools = []
    for s in REGISTRY.values():
        if not s.tool_enabled:
            continue
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": f"calc_{s.id.lower()}",
                    "description": f"{s.description} — {s.expression}",
                    "parameters": {
                        "type": "object",
                        "properties": {k: ptype(v) for k, v in s.params.items()},
                        "required": [k for k, v in s.params.items() if "기본" not in v],
                    },
                },
            }
        )
    return tools
