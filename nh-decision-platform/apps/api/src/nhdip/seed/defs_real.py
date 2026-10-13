"""Phase I 정의 보강 — 원천이 없던 화면 수치를 데이터셋 + 지표로 (요구사항 RD-07 · 결정 Q142).

- 모형 카드(6개 모형): 등급 집계(MODEL_MONITORING_GRADE, 정의 그대로 · 자료만 6개 모형) → AUROC · AR · K-S · PSI · AR 하락률 · 판정
- 포용금융 · 중·저신용 공급: 소매 Pool 월별 집계(RETAIL_POOL_SUMMARY 신설) × Pool 마스터(상품군 · 저신용 Pool)
- 여신 종합 · 비교표: 손익(2633) · 잔액(2020)의 당기 · 전년 · 전전년 · 증감 · 증감률
- 자본: 관리기준(규칙 CAPITAL_FLOORS) · BIS 여유
- 제안 제약: 가계 잔액 연말 추정 · 가계 RWA 소진율(제안 반영) · 한도 100%
- 지역본부 가이드 이행률(HQ_PLAN_KPI 항목)
판정 임계값 · 개발시점 AR · 가정 계수는 규칙(관리자 편집)에 둔다 — 화면에는 계산 근거 없는 숫자를 두지 않는다(PRIN-05).
"""
from __future__ import annotations

from typing import Any

from .defs_data import col, metric, mref, q

MM, IR, HQ = "wf_model_monitoring", "wf_inclusive_risk", "wf_hq_goal_review"
G = "MODEL_MONITORING_GRADE"
RS = "RETAIL_POOL_SUMMARY"
PM = "RETAIL_POOL_MASTER"
PL, LB, CC, K = "PL_PRODUCT_SEGMENT", "LOAN_BALANCE_MONTHLY", "CAPITAL_CONSTRAINT", "HQ_PLAN_KPI"

DATASETS = [
    dict(
        code=RS, name="소매여신 Pool별 월별 집계 (TB_JC_PM_C_LA 집계)", origin="bank", kind="fact",
        description="전행 소매여신 Pool별 익스포저 건수 · 금액 · 평균 CB 등급 · 신규취급 누계(월말). 포용금융 익스포저 · 중·저신용자 공급 · 소매 평균 등급의 원천 (정의서 RISK_T03 '원천 추가 필요' 항목)",
        file_pattern=r"TB_JC_PM_C_LA_POOL_(\d{6})\.(xlsx|csv|json)", refresh_cycle="월",
        columns=[
            col("std_ym", "기준년월", "str", True, ["기준월"]),
            col("pool_id", "Pool", "str", True, ["해당상품Pool", "Pool코드"]),
            col("exposure_cnt", "익스포저 건수", "int", True, ["건수", "계좌수"]),
            col("exposure_amt", "익스포저 금액(백만원)", "num", True, ["익스포저금액", "잔액(백만원)"]),
            col("avg_cb_grade", "평균 CB 등급", "num", False, ["평균CB등급", "평균등급"]),
            col("new_amt_ytd", "신규취급 누계(백만원)", "num", False, ["신규취급누계", "신규취급액누계"]),
        ],
        key_columns=["std_ym", "pool_id"], as_of_column="std_ym",
        mapping={"unit": "건·백만원", "used_by": ["포용금융 익스포저", "중·저신용자 공급", "소매 평균 등급"],
                 "concepts": [{"label": "PolicyTheme", "key": "포용금융", "about": True}, {"label": "BusinessDomain", "key": "가계여신", "about": True}]},
        quality_rules=[{"rule": "range", "column": "exposure_cnt", "min": 0}, {"rule": "range", "column": "exposure_amt", "min": 0},
                       {"rule": "range", "column": "avg_cb_grade", "min": 1, "max": 10, "severity": "warning"}],
    ),
]

# 모형 카드 — (그림 id 접미사, 모형 코드, PSI 판정 여부, AR 하락률 자릿수)
MODELS = [("large", "CORP_LARGE", True, 1), ("mid", "CORP_MID", True, 1), ("small", "CORP_SMALL", True, 1), ("micro", "CORP_MICRO", True, 1),
          ("as", "RETAIL_AS", False, 1), ("bs", "RETAIL_BS", False, 2)]
# 개발시점 AR(%) — 모형 개발 보고서 값으로 교체할 시뮬레이션 가정 (규칙 MDL_AR_BASELINE 에 키 추가)
AR_BASELINE = {"CORP_LARGE": 68.02, "CORP_MID": 67.21, "CORP_SMALL": 67.14, "RETAIL_AS": 54.39, "RETAIL_BS": 85.60}

RULES = [
    ("CAPITAL_FLOORS", "자본비율 관리기준", "threshold", "BIS 총자본비율 규제 최소 · 우량은행 기준 · 보통주자본비율 관리기준(%) — 행내 자본관리 기준으로 관리",
     {"bis_min": 8.0, "bis_prime": 10.0, "cet1_mgmt": 11.0}),
    ("MDL_MODEL_VERDICT", "모형 종합 판정 문구", "threshold", "PSI · AR 하락률 판정 중 가장 심각한 수준 → 모형 카드 판정 문구 (Phase I · 시뮬레이션 가정)",
     {"labels": {"info": "적정", "watch": "조건부 적정", "caution": "미흡 — 재개발 검토"}}),
]

# 기존 지표에 붙이는 화면 수치 id (같은 값을 여러 화면이 다른 id 로 쓰던 것)
EXTRA_FIGURES: dict[str, list[str]] = {
    "total_rev_2026": ["total_rev_cur"], "total_rev_2025": ["total_rev_prior"], "total_rev_growth": ["total_rev_rate"],
    "nim_2026": ["nim_cur"], "nim_2025": ["nim_prior"], "nim_growth": ["nim_rate"],
    "corp_int_rev": ["corp_int_cur", "cmp_corp_int_cur"], "hh_int_rev": ["hh_int_cur", "cmp_hh_int_cur"],
    "corp_bal": ["cmp_corp_bal_cur"], "hh_bal": ["cmp_hh_bal_cur"], "corp_growth": ["cmp_corp_bal_rate"], "hh_growth": ["cmp_hh_bal_rate"],
    "hh_bal_limit": ["hh_bal_limit", "cc_hh_ceiling"], "hh_bal_usage": ["hh_bal_usage"],
    "corp_rwa_usage_proposed": ["cc_rwa_corp_proposed"], "corp_rwa_margin_proposed": ["cc_rwa_corp_headroom"],
    "hh_rwa_usage_incl_inclusive": ["cc_inc_proposed"], "hh_rwa_margin_incl_inclusive": ["cc_inc_headroom"],
    "nim_share_2026": ["nim_share_2026"], "nim_share_2025": ["nim_share_2025"], "nim_share_2024": ["nim_share_2024"],
    "q3_loan_income_target": ["g1_target"], "loan_nim_target": ["g2_target"], "grade_5c_target": ["grade_5c_target"],
}


def extend(ms: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for m in ms:
        extra = [f for f in EXTRA_FIGURES.get(m["code"], []) if f not in m["figure_ids"]]
        if extra:
            m["figure_ids"] = [*m["figure_ids"], *extra]
    return ms


def _pl(item: str, ym: str, label: str):
    return q(PL, {"item_code": item, "ym": ym}, "amount", label=label, unit="백만원")


def _lb(acct: str, ym: str, label: str):
    return q(LB, {"account_code": acct, "ym": ym}, "balance", label=label, unit="백만원")


def _rule(code: str, path: str, label: str, unit: str = ""):
    r: dict[str, Any] = {"rule": code, "path": path, "label": label}
    if unit:
        r["unit"] = unit
    return r


def metrics() -> list[dict[str, Any]]:
    M: list[dict[str, Any]] = []
    L, Y1, Y2 = "$latest", "$latest-12", "$latest-24"
    # ── 여신 종합 · 비교표 (손익 · 잔액 3개년)
    for code, item, label, cur in (("total_rev", "TOTAL_REVENUE", "전체 수익", "total_rev_2026"), ("nim", "LOAN_NIM", "여신(일반)부문 이자마진 수익", "nim_2026"),
                                   ("corp_int", "CORP_INTEREST", "기업자금대출금이자", "corp_int_rev"), ("hh_int", "HH_INTEREST", "가계자금대출금이자", "hh_int_rev")):
        prior = {"total_rev": "total_rev_2025", "nim": "nim_2025"}.get(code)
        cmp = ["cmp_" + code] if code in ("corp_int", "hh_int") else []
        if prior is None:  # 전년 값 지표가 없던 이자수익
            prior = f"{code}_2025"
            M.append(metric(prior, f"{label}(전년 동기 누계)", "VALUE", {"value": _pl(item, Y1, label)}, wf=HQ, unit="KRW_BN", decimals=0, scale=100, figures=[f"{code}_prior", *[c + "_prior" for c in cmp]], sort=110))
            M.append(metric(f"{code}_growth", f"{label} 증감률", "GROWTH_RATE", {"v0": _pl(item, Y1, f"{label} (전년 동기)"), "v1": _pl(item, L, f"{label} (당기)")}, wf=HQ, unit="PCT", decimals=2,
                            figures=[f"{code}_rate", *[c + "_rate" for c in cmp]], sort=111))
        M.append(metric(f"{code}_2024", f"{label}(전전년 동기 누계)", "VALUE", {"value": _pl(item, Y2, label)}, wf=HQ, unit="KRW_BN", decimals=0, scale=100, figures=[f"{code}_prior2", *[c + "_prior2" for c in cmp]], sort=112))
        M.append(metric(f"{code}_diff", f"{label} 증감액", "DIFF", {"a": mref(cur, "당기", "백만원"), "b": mref(prior, "전기", "백만원")}, wf=HQ, unit="KRW_BN", decimals=0, scale=100, figures=[f"{code}_diff", *[c + "_diff" for c in cmp]], sort=113))
    for seg, acct, label in (("corp", "CORP", "기업자금대출금"), ("hh", "HH", "가계자금대출금")):
        M += [
            metric(f"{seg}_bal_2025", f"{label} 잔액(전년 동기)", "VALUE", {"value": _lb(acct, Y1, label)}, wf=HQ, unit="KRW_TN", decimals=2, scale=1_000_000, figures=[f"cmp_{seg}_bal_prior"], sort=114),
            metric(f"{seg}_bal_2024", f"{label} 잔액(전전년 동기)", "VALUE", {"value": _lb(acct, Y2, label)}, wf=HQ, unit="KRW_TN", decimals=2, scale=1_000_000, figures=[f"cmp_{seg}_bal_prior2"], sort=115),
            metric(f"{seg}_bal_diff", f"{label} 증감액", "DIFF", {"a": mref(f"{seg}_bal", "당기", "백만원"), "b": mref(f"{seg}_bal_2025", "전년 동기", "백만원")}, wf=HQ, unit="KRW_TN", decimals=2, scale=1_000_000, figures=[f"cmp_{seg}_bal_diff"], sort=116),
        ]
    tot = lambda ym: q(LB, {"account_code": {"in": ["CORP", "HH"]}, "ym": ym}, "balance", "sum", "기업+가계 잔액", "백만원")  # noqa: E731
    M += [
        metric("corp_share_2025", "기업여신 구성비(전년 동기)", "SHARE", {"numerator": _lb("CORP", Y1, "기업자금대출금"), "denominator": tot(Y1)}, wf=HQ, unit="PCT", decimals=2, figures=[], sort=117),
        metric("hh_share_2025", "가계여신 구성비(전년 동기)", "SHARE", {"numerator": _lb("HH", Y1, "가계자금대출금"), "denominator": tot(Y1)}, wf=HQ, unit="PCT", decimals=2, figures=[], sort=117),
        metric("hh_share_2024", "가계여신 구성비(2년 전)", "SHARE", {"numerator": _lb("HH", Y2, "가계자금대출금"), "denominator": tot(Y2)}, wf=HQ, unit="PCT", decimals=2, figures=[], sort=117),
    ]
    # 수익성(규모 대비 수익률) 3개년 — 부문별 이자수익 ÷ 잔액
    for seg, acct, item in (("corp", "CORP", "CORP_INTEREST"), ("hh", "HH", "HH_INTEREST"), ("etc_hh", "HH_ETC", "HH_ETC_INTEREST"), ("house", "HOUSE", "HOUSE_INTEREST"), ("public", "PUBLIC", "PUBLIC_INTEREST")):
        for yr, tok in (("2025", Y1), ("2024", Y2)):
            M.append(metric(f"ros_{seg}_{yr}", f"규모 대비 수익률({yr})", "SHARE", {"numerator": _pl(item, tok, "이자수익"), "denominator": _lb(acct, tok, "잔액")}, wf=HQ, unit="PCT", decimals=3, figures=[], sort=118))
    # ── 자본 관리기준 · 여유
    M += [
        metric("bis_floor", "BIS 우량은행 기준", "VALUE", {"value": _rule("CAPITAL_FLOORS", "bis_prime", "우량은행 기준", "%")}, wf=HQ, unit="PCT", decimals=1, sort=117),
        metric("bis_min", "BIS 규제 최소기준", "VALUE", {"value": _rule("CAPITAL_FLOORS", "bis_min", "규제 최소기준", "%")}, wf=HQ, unit="PCT", decimals=1, sort=118),
        metric("bis_margin", "우량은행 기준 대비 여유", "DIFF", {"a": mref("bis_total", "BIS 총자본비율", "%"), "b": mref("bis_floor", "우량은행 기준", "%")}, wf=HQ, unit="PP", decimals=1, sort=119),
        metric("cet1_floor", "보통주자본비율 관리기준", "VALUE", {"value": _rule("CAPITAL_FLOORS", "cet1_mgmt", "관리기준", "%")}, wf=HQ, unit="PCT", decimals=1, sort=120),
        # 보통주자본(CET1) 원천은 아직 없음 — 항목(CET1_RATIO)이 올라오면 계산, 없으면 '시산 불가'(추정치를 만들지 않음)
        metric("cet1", "보통주자본비율", "VALUE", {"value": q(CC, {"item_code": "CET1_RATIO", "ym": "$latest"}, "value", label="보통주자본비율", unit="%")}, wf=HQ, unit="PCT", decimals=1, sort=121),
    ]
    # ── 제안 제약 (가계 잔액 연말 추정 · 가계 RWA · 한도 100%)
    M += [
        metric("limit_100", "한도(100%)", "VALUE", {"value": {"const": 100, "label": "한도(100%)", "unit": "%"}}, wf=HQ, unit="PCT", decimals=1, figures=["cc_rwa_corp_ceiling", "cc_rwa_hh_ceiling", "cc_inc_ceiling"], sort=122),
        metric("hh_bal_prev_ye", "가계자금대출금 잔액(전년 말)", "VALUE", {"value": _lb("HH", "$prev_year_end", "가계자금대출금(전년 말)")}, wf=HQ, unit="KRW_TN", decimals=2, scale=1_000_000, figures=[], sort=123),
        metric("hh_ye_proposed", "제안 반영 시 가계여신 연말 추정 잔액", "GROWTH_APPLY", {"base": mref("hh_bal_prev_ye", "전년 말 잔액", "백만원"), "rate": mref("hh_growth_rec", "제안 관리목표(증가율)", "%")}, wf=HQ, unit="KRW_TN", decimals=2, scale=1_000_000,
               figures=["cc_hh_proposed"], sort=124, description="연말 추정 = 전년 말 잔액 × (1 + 제안 관리목표 증가율)"),
        metric("hh_ye_headroom", "가계여신 잔액 관리 한도 여유(제안 반영)", "DIFF", {"a": mref("hh_bal_limit", "관리 한도", "백만원"), "b": mref("hh_ye_proposed", "연말 추정 잔액", "백만원")}, wf=HQ, unit="KRW_TN", decimals=2, scale=1_000_000, figures=["cc_hh_headroom"], sort=125),
        metric("hh_ye_increment_tn", "제안 반영 가계여신 증가분(조원)", "PCT_AMOUNT", {"base": {"metric": "hh_ye_increment_mn", "label": "증가분(백만원)", "unit": "백만원"}, "rate": {"const": 100}, "divisor": {"const": 1_000_000, "label": "백만원→조원"}}, wf=HQ, unit="KRW_TN", decimals=2, figures=[], sort=127),
        metric("hh_ye_increment_mn", "제안 반영 가계여신 증가분(백만원)", "DIFF", {"a": mref("hh_ye_proposed", "연말 추정", "백만원"), "b": q(LB, {"account_code": "HH", "ym": L}, "balance", label="가계자금대출금(당기)", unit="백만원")}, wf=HQ, unit="KRW_MN", decimals=0, figures=[], sort=126),
        metric("hh_rwa_usage_proposed", "가계부문 신용RWA 소진율(제안 반영)", "PROPOSED_USAGE", {"used": q(CC, {"item_code": "RWA_HH_USED", "ym": L}, "value", label="가계 RWA 사용", unit="조원"), "increment": mref("hh_ye_increment_tn", "가계여신 증가분", "조원"),
               "factor": _rule("PROPOSAL_IMPACT", "hh_rwa_factor", "가계여신 RWA 환산계수(시뮬레이션 가정)"), "limit": q(CC, {"item_code": "RWA_HH_ALLOC", "ym": L}, "value", label="가계 RWA 배분", unit="조원")}, wf=HQ, unit="PCT", decimals=1, figures=["cc_rwa_hh_proposed"], sort=128),
        metric("hh_rwa_margin_proposed", "가계부문 신용RWA 한도 여유(제안 반영)", "DIFF", {"a": {"const": 100, "label": "한도(100%)", "unit": "%"}, "b": mref("hh_rwa_usage_proposed", "제안 반영 소진율", "%")}, wf=HQ, unit="PP", decimals=1, figures=["cc_rwa_hh_headroom"], sort=129),
    ]
    # ── 지역본부 가이드 이행률 (HQ_PLAN_KPI)
    kpi = lambda item, label: q(K, {"item_code": item, "ym": L}, "value", label=label, unit="%")  # noqa: E731
    M += [
        metric("d300_inc_check_rt", "수도권지역본부 포용금융 초기 연체 점검 이행률", "VALUE", {"value": kpi("D300_INC_DLQ_CHECK_RT", "이행률")}, wf=HQ, unit="PCT", decimals=0, figures=["bt3_actual"], sort=130),
        metric("d300_inc_check_target", "수도권지역본부 포용금융 초기 연체 점검 목표", "VALUE", {"value": kpi("D300_INC_DLQ_CHECK_TARGET", "목표")}, wf=HQ, unit="PCT", decimals=0, figures=["bt3_target"], sort=131),
        metric("d300_inc_check_progress", "초기 연체 점검 진행률", "SHARE", {"numerator": mref("d300_inc_check_rt", "이행률", "%"), "denominator": mref("d300_inc_check_target", "목표", "%")}, wf=HQ, unit="PCT", decimals=1, figures=[], sort=132),
    ]
    # ── 포용금융 · 중·저신용 (소매 Pool 월별 집계)
    incl = {"pool_id": {"in_dataset": {"dataset": PM, "col": "pool_id", "where": {"product_group": "서민금융"}}}}
    lowc = {"pool_id": {"in_dataset": {"dataset": PM, "col": "pool_id", "where": {"low_credit": True}}}}
    base_ym = {"ref": {"rule": "INC_PROVISION_SHARE_TREND", "path": "base_ym"}}

    def rs(where, column, label, agg="list"):
        return q(RS, where, column, agg, label, "건" if column == "exposure_cnt" else ("등급" if column == "avg_cb_grade" else "백만원"), "pool_id")

    M += [
        metric("inc_exposure_cnt_now", "포용금융 익스포저 건수(최근월)", "SUM", {"values": rs({**incl, "std_ym": L}, "exposure_cnt", "서민금융 Pool 건수")}, wf=IR, unit="CNT", decimals=0, sort=20),
        metric("inc_exposure_cnt_base", "포용금융 익스포저 건수(기준월)", "SUM", {"values": rs({**incl, "std_ym": base_ym}, "exposure_cnt", "서민금융 Pool 건수(기준월)")}, wf=IR, unit="CNT", decimals=0, figures=[], sort=21),
        metric("inc_exposure_cnt_growth", "익스포저 건수 증가율(기준월 대비)", "GROWTH_RATE", {"v0": mref("inc_exposure_cnt_base", "기준월 건수", "건"), "v1": mref("inc_exposure_cnt_now", "최근월 건수", "건")}, wf=IR, unit="PCT", decimals=1, sort=22),
        metric("inc_exposure_amt_now", "포용금융 익스포저 규모(최근월)", "SUM", {"values": rs({**incl, "std_ym": L}, "exposure_amt", "서민금융 Pool 금액")}, wf=IR, unit="KRW_TN", decimals=2, scale=1_000_000, sort=23),
        metric("inc_avg_grade", "해당 풀 평균 신용등급(건수 가중)", "WEIGHTED_AVG", {"values": rs({**incl, "std_ym": L}, "avg_cb_grade", "Pool 평균 CB 등급"), "weights": rs({**incl, "std_ym": L}, "exposure_cnt", "Pool 건수")}, wf=IR, unit="RATIO", decimals=1, sort=24),
        metric("retail_avg_grade", "소매 익스포저 전체 평균 신용등급(건수 가중)", "WEIGHTED_AVG", {"values": rs({"std_ym": L}, "avg_cb_grade", "Pool 평균 CB 등급"), "weights": rs({"std_ym": L}, "exposure_cnt", "Pool 건수")}, wf=IR, unit="RATIO", decimals=1, sort=25),
        metric("mid_low_supply", "중·저신용자 여신 공급액(누계)", "SUM", {"values": rs({**lowc, "std_ym": L}, "new_amt_ytd", "저신용 Pool 신규취급 누계")}, wf=HQ, unit="KRW_TN", decimals=2, scale=1_000_000, sort=140),
        metric("mid_low_supply_py", "중·저신용자 여신 공급액(전년 동기 누계)", "SUM", {"values": rs({**lowc, "std_ym": Y1}, "new_amt_ytd", "저신용 Pool 신규취급 누계(전년)")}, wf=HQ, unit="KRW_TN", decimals=2, scale=1_000_000, figures=[], sort=141),
        metric("mid_low_growth", "공급액 증가율(전년 동기 대비)", "GROWTH_RATE", {"v0": mref("mid_low_supply_py", "전년 동기", "백만원"), "v1": mref("mid_low_supply", "당기", "백만원")}, wf=HQ, unit="PCT", decimals=1, sort=142),
        metric("mid_low_bal", "중·저신용자 익스포저 금액", "SUM", {"values": rs({**lowc, "std_ym": L}, "exposure_amt", "저신용 Pool 금액")}, wf=HQ, unit="KRW_TN", decimals=2, scale=1_000_000, figures=[], sort=143),
        metric("retail_bal", "소매 익스포저 금액(전체)", "SUM", {"values": rs({"std_ym": L}, "exposure_amt", "전체 Pool 금액")}, wf=HQ, unit="KRW_TN", decimals=2, scale=1_000_000, figures=[], sort=144),
        metric("mid_low_share", "개인여신 중 중·저신용자 비중", "SHARE", {"numerator": mref("mid_low_bal", "중·저신용자 금액", "백만원"), "denominator": mref("retail_bal", "전체 금액", "백만원")}, wf=HQ, unit="PCT", decimals=1, sort=145),
    ]
    # ── 소기업 6B 근거 · 보고서 문단 수치
    g6b = {"model_code": "CORP_MICRO", "as_of": L, "grade": "6B"}
    M += [
        metric("obs_6b", "6B 등급 전체건수", "VALUE", {"value": q(G, g6b, "obs_count", label="관측건수", unit="건")}, wf=MM, unit="CNT", decimals=0, sort=70),
        metric("defaults_6b", "6B 등급 부도건수", "VALUE", {"value": q(G, g6b, "default_count", label="부도건수", unit="건")}, wf=MM, unit="CNT", decimals=0, sort=71),
        metric("pd_min_6b", "예측부도율 최소값", "VALUE", {"value": q("PD_MASTER_SCALE", {"model_code": "CORP_MICRO", "grade": "6B"}, "pd_min", label="최소값", unit="%")}, wf=MM, unit="PCT", decimals=3, sort=72),
        metric("share_6b_now", "6B 등급 구성비(비교시점)", "VALUE", {"value": q(G, g6b, "obs_share", label="구성비", unit="%")}, wf=MM, unit="PCT", decimals=2, sort=73),
        metric("share_6b_base", "6B 등급 구성비(기준시점)", "VALUE", {"value": q(G, {**g6b, "as_of": "$earliest"}, "obs_share", label="구성비", unit="%")}, wf=MM, unit="PCT", decimals=2, sort=74),
        metric("chi_df", "카이제곱 자유도", "VALUE", {"value": mref("chi_stat", "자유도", "", "df")}, wf=MM, unit="NONE", decimals=0, sort=75),
    ]
    for grade in ("7B", "8"):
        w = {"model_code": "CORP_MICRO", "as_of": L, "grade": grade}
        M.append(metric(f"obs_{grade.lower()}", f"소기업 {grade} 등급 관측건수", "VALUE", {"value": q(G, w, "obs_count", label="관측건수", unit="건")}, wf=MM, unit="CNT", decimals=0, sort=76))
        M.append(metric(f"dr_{grade.lower()}", f"소기업 {grade} 등급 실제부도율", "DEFAULT_RATE", {"default_count": q(G, w, "default_count", label="부도건수", unit="건"), "obs_count": q(G, w, "obs_count", label="관측건수", unit="건")}, wf=MM, unit="PCT", decimals=3, sort=76))
    # ── 포용금융 대상 상품 · 상품군별 비중 증감
    P = "PROVISION_BY_PRODUCT"
    M.append(metric("share_band", "포용금융 충당금 비중 판정", "BAND", {"value": mref("share_delta_pp", "비중 증감", "%p"), "bands": _rule("INC_PROVISION_SHARE_TREND", "bands", "비중 증감 구간")}, wf=IR, unit="PP", decimals=2, sort=29))
    M.append(metric("inc_product_cnt", "포용금융 대상 상품코드 수", "VALUE", {"value": q("INCLUSIVE_PRODUCTS", {}, "product_code", "count", "대상 상품코드", "건")}, wf=IR, unit="CNT", decimals=0, sort=30))
    for gid, gname in (("saehope", "새희망홀씨대출"), ("sunshine", "햇살론"), ("saitdol", "사잇돌")):
        grp = {"product_code": {"in_dataset": {"dataset": "INCLUSIVE_PRODUCTS", "col": "product_code", "where": {"product_group": gname}}}, "is_total": False}
        M += [
            metric(f"inc_grp_{gid}_now", f"{gname} 충당금(최근월)", "SUM", {"values": q(P, {**grp, "ym": L}, "provision", "list", f"{gname} 상품 충당금", "백만원")}, wf=IR, unit="KRW_MN", decimals=0, sort=31),
            metric(f"inc_grp_{gid}_base", f"{gname} 충당금(기준월)", "SUM", {"values": q(P, {**grp, "ym": base_ym}, "provision", "list", f"{gname} 상품 충당금", "백만원")}, wf=IR, unit="KRW_MN", decimals=0, sort=32),
            metric(f"inc_grp_{gid}_share_now", f"{gname} 충당금 비중(최근월)", "SHARE", {"numerator": mref(f"inc_grp_{gid}_now", "상품군 충당금", "백만원"), "denominator": mref("prov_total_now", "전체 충당금", "백만원")}, wf=IR, unit="PCT", decimals=2, figures=[], sort=33),
            metric(f"inc_grp_{gid}_share_base", f"{gname} 충당금 비중(기준월)", "SHARE", {"numerator": mref(f"inc_grp_{gid}_base", "상품군 충당금", "백만원"), "denominator": mref("prov_total_base", "전체 충당금", "백만원")}, wf=IR, unit="PCT", decimals=2, figures=[], sort=34),
            metric(f"inc_grp_{gid}_delta", f"{gname} 비중 증감", "SHARE_DELTA_PP", {"share1": mref(f"inc_grp_{gid}_share_now", "최근월 비중", "%"), "share0": mref(f"inc_grp_{gid}_share_base", "기준월 비중", "%")}, wf=IR, unit="PP", decimals=2, sort=35),
        ]
    # ── 모형 카드 (등급 집계 → 성능 · 안정성 · 판정)
    for sfx, code, has_psi, ard_dec in MODELS:
        cur = {"model_code": code, "as_of": "$latest"}
        base = {"model_code": code, "as_of": "$earliest"}
        if sfx != "micro":  # 소기업 모형은 기존 지표(auroc_micro · ar_micro · ks_micro · ard_micro · psi_micro)
            M += [
                metric(f"auroc_{sfx}", "AUROC", "AUROC_GRADED", {"defaults": q(G, cur, "default_count", "list", "등급별 부도건수", "건", "grade_seq"), "obs": q(G, cur, "obs_count", "list", "등급별 관측건수", "건", "grade_seq")}, wf=MM, unit="RATIO", decimals=3, sort=60),
                metric(f"ar_{sfx}", "AR", "AR_FROM_AUROC", {"auroc": mref(f"auroc_{sfx}", "AUROC")}, wf=MM, unit="PCT", decimals=2, sort=61),
                metric(f"ks_{sfx}", "K-S", "KS_GRADED", {"defaults": q(G, cur, "default_count", "list", "등급별 부도건수", "건", "grade_seq"), "obs": q(G, cur, "obs_count", "list", "등급별 관측건수", "건", "grade_seq")}, wf=MM, unit="PCT", decimals=1, sort=62),
                metric(f"ard_{sfx}", "AR 하락률", "AR_DECLINE", {"ar_dev": _rule("MDL_AR_BASELINE", code, "개발시점 AR(시뮬레이션 가정)"), "ar_now": mref(f"ar_{sfx}", "현재 AR", "%")}, wf=MM, unit="PCT", decimals=ard_dec, sort=63),
            ]
            if has_psi:
                M.append(metric(f"psi_{sfx}", "PSI", "PSI", {"base": q(G, base, "obs_share", "list", "기준시점 구성비", "%", "grade_seq"), "current": q(G, cur, "obs_share", "list", "비교시점 구성비", "%", "grade_seq")}, wf=MM, unit="RATIO", decimals=3, sort=64))
        M.append(metric(f"ard_band_{sfx}", "AR 하락률 판정", "BAND", {"value": mref(f"ard_{sfx}", "AR 하락률", "%"), "bands": _rule("MDL_AR_DECLINE_BANDS", "bands", "AR 하락률 구간")}, wf=MM, unit="PCT", decimals=ard_dec, sort=65))
        sev = {"sev_a": mref(f"ard_band_{sfx}", "AR 하락률 판정", field="severity")}
        if has_psi:
            M.append(metric(f"psi_band_{sfx}", "PSI 판정", "BAND", {"value": mref(f"psi_{sfx}", "PSI"), "bands": _rule("MDL_PSI_BANDS", "bands", "PSI 구간")}, wf=MM, unit="RATIO", decimals=3, sort=66))
            sev["sev_b"] = mref(f"psi_band_{sfx}", "PSI 판정", field="severity")
        M.append(metric(f"verdict_{sfx}", "모형 종합 판정", "VERDICT", {**sev, "labels": _rule("MDL_MODEL_VERDICT", "labels", "판정 문구")}, wf=MM, unit="NONE", decimals=0, sort=67))
    return M


def bindings() -> list[dict[str, Any]]:
    """연도별 · 월별 추이 점(차트) — 지표 결과 · 데이터셋 행에서."""
    ym = lambda tok: f"[[ym:{LB}:{tok}|dot]]"  # noqa: E731
    pl_ym = lambda tok: f"[[ym:{PL}:{tok}|dot]]"  # noqa: E731
    out = []
    for seg, acct in (("corporate", "CORP"), ("household", "HH")):
        s = "corp" if acct == "CORP" else "hh"
        out.append(dict(workflow_code=HQ, artifact_key="loan_overview", path=f"{seg}.yearly", builder="metric_points",
                        params={"points": [{"label": ym("$latest-24"), "metric": f"{s}_bal_2024"}, {"label": ym("$latest-12"), "metric": f"{s}_bal_2025"}, {"label": ym("$latest"), "metric": f"{s}_bal"}]}))
        out.append(dict(workflow_code=HQ, artifact_key="loan_overview", path=f"{seg}.monthly", builder="series_points",
                        params={"dataset": LB, "where": {"account_code": acct}, "order_by": "ym", "col": "balance", "scale": 1_000_000, "decimals": 2, "latest_year": True, "label_fmt": "month"}))
    inc_p = {"dataset": "PROVISION_BY_PRODUCT", "master": "INCLUSIVE_PRODUCTS", "base_ym": {"ref": {"rule": "INC_PROVISION_SHARE_TREND", "path": "base_ym"}}, "now_ym": "$latest", "group_order": ["새희망홀씨대출", "햇살론", "사잇돌"]}
    out.append(dict(workflow_code=IR, artifact_key="report.inclusive-risk", path="table:포용금융 대상 상품군", builder="inclusive_group_table", params=inc_p))
    base_l, now_l = "[[rule:INC_PROVISION_SHARE_TREND.base_ym|dot]]", "[[ym:PROVISION_BY_PRODUCT:$latest|dot]]"
    out.append(dict(workflow_code=IR, artifact_key="report.inclusive-risk", path="chart:포용금융 충당금 비중 — 2026.01 vs 2026.08", builder="metric_series",
                    params={"series": [{"name": "충당금 비중", "points": [{"label": base_l, "metric": "share_base"}, {"label": now_l, "metric": "share_now"}]}]}))
    groups = (("saehope", "새희망홀씨대출"), ("sunshine", "햇살론"), ("saitdol", "사잇돌"))
    out.append(dict(workflow_code=IR, artifact_key="report.inclusive-risk", path="chart:상품군별 충당금 — 2026.01 vs 2026.08 (백만원)", builder="metric_series",
                    params={"series": [{"name": lab, "points": [{"label": g, "metric": f"inc_grp_{gid}_{when}"} for gid, g in groups]} for lab, when in ((base_l, "base"), (now_l, "now"))]}))
    out.append(dict(workflow_code=IR, artifact_key="report.inclusive-risk", path="table_note:포용금융 대상 상품군", builder="inclusive_match_note", params={"master": "INCLUSIVE_PRODUCTS", "dataset": "PROVISION_BY_PRODUCT"}))
    P = "PROVISION_BY_PRODUCT"

    def dq(own: str) -> dict[str, Any]:
        # 두 워크플로가 같은 표를 쓴다 — 자기 자료만 'dataset'(계보: 그 자료가 바뀌면 이 워크플로가 돈다), 다른 쪽 자료는 'ref_dataset'(표시만)
        k = lambda ds: "dataset" if ds == own else "ref_dataset"  # noqa: E731
        return {"items": [
            {"label": "([[ym:PROVISION_BY_PRODUCT:$latest|ym]])7790_상품별_충당금", "kind": "dataset", k(P): P},
            {"label": "신용평가모형 등급별 집계", "kind": "dataset", k("MODEL_MONITORING_GRADE"): "MODEL_MONITORING_GRADE"},
            {"label": "포용금융 상품코드 매칭", "kind": "master_match", "master": "INCLUSIVE_PRODUCTS", k(P): P},
            {"label": "해당 풀 연체율", "kind": "missing", "note": "데이터 미제공 — 분석에서 제외하고 한계로 표기(소매 연체원장 원천 추가 필요)"},
        ]}

    for wf, own in ((MM, "MODEL_MONITORING_GRADE"), (IR, P)):
        out.append(dict(workflow_code=wf, artifact_key="risk_dashboard", path="dataQuality", builder="data_quality", params=dq(own)))
    for i, acct in enumerate(("CORP", "HH")):
        out.append(dict(workflow_code=HQ, artifact_key="comparison_view", path=f"balanceSeries.{i}.points", builder="series_points",
                        params={"dataset": LB, "where": {"account_code": acct}, "order_by": "ym", "col": "balance", "scale": 1_000_000, "decimals": 2, "latest_year": True, "label_fmt": "month"}))
    for i, s in enumerate(("corp", "hh")):
        out.append(dict(workflow_code=HQ, artifact_key="comparison_view", path=f"shareSeries.{i}.points", builder="metric_points",
                        params={"points": [{"label": ym("$latest-24"), "metric": f"{s}_share_2024"}, {"label": ym("$latest-12"), "metric": f"{s}_share_2025"}, {"label": ym("$latest"), "metric": f"{s}_share"}]}))
    for i, seg in enumerate(("corp", "hh", "etc_hh", "house", "public")):
        out.append(dict(workflow_code=HQ, artifact_key="profitability", path=f"{i}.trend", builder="metric_points",
                        params={"points": [{"label": ym("$latest-24"), "metric": f"ros_{seg}_2024"}, {"label": ym("$latest-12"), "metric": f"ros_{seg}_2025"}, {"label": ym("$latest"), "metric": f"ros_{seg}"}]}))
    out.append(dict(workflow_code=HQ, artifact_key="loan_overview", path="revenue.nimShareTrend", builder="metric_points",
                    params={"points": [{"label": pl_ym("$latest-24"), "metric": "nim_share_2024"}, {"label": pl_ym("$latest-12"), "metric": "nim_share_2025"}, {"label": pl_ym("$latest"), "metric": "nim_share_2026"}]}))
    return out
