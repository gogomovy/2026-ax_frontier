"""컬럼 정의서(TalkFile_종기부_컬럼정의서(컬럼기준)_v2) 연결 정의.

- HQ_PLAN_KPI: 정의서에서 '목데이터 O' 이거나 경영계획·보고서·지역본부 실적이 원천인 값(시뮬레이션). 실데이터는 같은 정의로 업로드.
- METRICS: 정의서 컬럼을 계산하기 위해 추가한 지표(커널 수식). 산식은 정의서 '원천 컬럼' 열을 그대로 옮겼다.
- BINDINGS: 컬럼 → 지표 · 서술 · 기준년월 · 고정값. 산식이 정의되지 않은 컬럼은 unmapped + 미결 질문 번호.
"""
from __future__ import annotations

from typing import Any

from .defs_data import col, metric, mref, q

HQ = "wf_hq_goal_review"
K = "HQ_PLAN_KPI"

DATASET = dict(
    code=K, name="경영계획 · 보고서 KPI (종기부 컬럼정의서)", origin="bank", kind="fact",
    description="경영계획 승인 목표 · 모형 보고서 KPI · 지역본부 신규취급 실적 — 컬럼정의서에서 '목데이터 O' 또는 원천이 문서인 값",
    refresh_cycle="월",
    columns=[col("ym", "기준년월", "str", True), col("item_code", "항목코드", "str", True), col("item_name", "항목명", "str"), col("value", "값", "num", True),
             col("unit", "단위", "str"), col("org_code", "조직코드", "str"), col("source_doc", "원천 문서", "str"), col("contract_column", "정의서 컬럼", "str")],
    key_columns=["ym", "item_code"], as_of_column="ym",
    mapping={"unit": "백만원·%", "used_by": ["T01 현황", "T03 목표설정"], "concepts": [{"label": "BusinessDomain", "key": "기업여신", "about": True}, {"label": "BusinessDomain", "key": "가계여신", "about": True}]},
    quality_rules=[{"rule": "min_rows", "value": 1}],
)

def kpi(item: str, label: str, unit: str = "백만원"):
    return q(K, {"item_code": item, "ym": "$latest"}, "value", label=label, unit=unit)


CC = "CAPITAL_CONSTRAINT"
PL = "PL_PRODUCT_SEGMENT"
LB = "LOAN_BALANCE_MONTHLY"


def metrics() -> list[dict[str, Any]]:
    from .defs_real import extend

    return extend(_metrics())


def _metrics() -> list[dict[str, Any]]:
    cc = lambda item, label: q(CC, {"item_code": item, "ym": "$latest"}, "value", label=label, unit="조원")  # noqa: E731
    return [
        # T01 — RWA
        metric("loan_rwa_used", "여신 신용RWA 소진액", "SUM", {"values": q(CC, {"item_code": {"in": ["RWA_CORP_USED", "RWA_HH_USED", "RWA_ETC_USED"]}, "ym": "$latest"}, "value", "list", "부문별 신용RWA 사용", "조원")}, wf=HQ, unit="KRW_TN", decimals=2, figures=[], sort=60),
        metric("loan_rwa_limit", "여신 신용RWA 배분한도", "VALUE", {"value": cc("RWA_DEPT_TOTAL", "부서별 배분 합계")}, wf=HQ, unit="KRW_TN", decimals=2, figures=[], sort=61),
        metric("loan_rwa_usage", "여신 신용RWA 소진율", "USAGE_RATE", {"used": mref("loan_rwa_used", "소진액", "조원"), "limit": mref("loan_rwa_limit", "배분한도", "조원")}, wf=HQ, unit="PCT", decimals=1, figures=[], sort=62),
        # T01/T03 — 이자마진 연간 목표 진행률 (화면 g2_* 수치를 커널 계산으로 대체)
        metric("nim_current_tn", "여신 이자마진 현재 수익(조원)", "VALUE", {"value": q(PL, {"item_code": "LOAN_NIM", "ym": "$latest"}, "amount", label="여신 이자마진", unit="백만원")}, wf=HQ, unit="KRW_TN", decimals=2, scale=1_000_000, figures=["g2_actual"], sort=63),
        metric("loan_nim_target", "여신 이자마진 연간 목표", "VALUE", {"value": kpi("LOAN_NIM_ANNUAL_TARGET", "연간 승인 목표")}, wf=HQ, unit="KRW_TN", decimals=2, scale=1_000_000, figures=[], sort=64),
        metric("loan_nim_progress", "여신 이자마진 목표 진행률", "SHARE", {"numerator": mref("nim_current_tn", "현재 수익", "백만원"), "denominator": mref("loan_nim_target", "연간 목표", "백만원")}, wf=HQ, unit="PCT", decimals=1, figures=["g2_gap"], sort=65),
        # 3분기 여신 수익
        metric("q3_loan_income", "3분기 여신 수익 현재값", "VALUE", {"value": kpi("Q3_LOAN_INCOME_ACTUAL", "3분기 누계")}, wf=HQ, unit="KRW_TN", decimals=2, scale=1_000_000, figures=["g1_actual"], sort=66),
        metric("q3_loan_income_target", "3분기 여신 수익 목표", "VALUE", {"value": kpi("Q3_LOAN_INCOME_TARGET", "3분기 목표")}, wf=HQ, unit="KRW_TN", decimals=2, scale=1_000_000, figures=[], sort=67),
        metric("q3_loan_income_gap", "3분기 여신 수익 목표 대비 차이", "DIFF", {"a": mref("q3_loan_income", "현재값", "백만원"), "b": mref("q3_loan_income_target", "목표", "백만원")}, wf=HQ, unit="KRW_TN", decimals=2, scale=1_000_000, figures=["g1_gap"], sort=68),
        # 가계여신 잔액 한도
        metric("hh_bal_limit", "가계여신 잔액 관리목표", "VALUE", {"value": kpi("HH_LOAN_BAL_LIMIT", "잔액 관리 상한")}, wf=HQ, unit="KRW_TN", decimals=2, scale=1_000_000, figures=[], sort=69),
        metric("hh_bal_remain", "가계여신 잔액 한도 여유", "DIFF", {"a": mref("hh_bal_limit", "관리목표", "백만원"), "b": q(LB, {"account_code": "HH", "ym": "$latest"}, "balance", label="가계자금대출금", unit="백만원")}, wf=HQ, unit="KRW_TN", decimals=2, scale=1_000_000, figures=["g5_gap"], sort=70),
        # 5C 이상 차주 비중
        metric("grade_5c_rt", "5C 이상 차주 비중", "VALUE", {"value": kpi("GRADE_5C_PLUS_RT", "5C 이상 차주 비중", "%")}, wf=HQ, unit="PCT", decimals=1, figures=["g6_actual"], sort=71),
        metric("grade_5c_target", "5C 이상 차주 비중 목표", "VALUE", {"value": kpi("GRADE_5C_PLUS_TARGET", "목표", "%")}, wf=HQ, unit="PCT", decimals=1, figures=[], sort=72),
        metric("grade_5c_gap", "5C 이상 차주 비중 목표 대비", "DIFF", {"a": mref("grade_5c_rt", "현재", "%"), "b": mref("grade_5c_target", "목표", "%")}, wf=HQ, unit="PP", decimals=1, figures=["g6_gap"], sort=73),
        # T02 — 3개년 여신 비중 1년차
        metric("nim_share_2024", "여신 이자마진 비중(2년 전)", "SHARE", {"numerator": q(PL, {"item_code": "LOAN_NIM", "ym": "$latest-24"}, "amount", label="여신 이자마진", unit="백만원"), "denominator": q(PL, {"item_code": "TOTAL_REVENUE", "ym": "$latest-24"}, "amount", label="전체 수익", unit="백만원")}, wf=HQ, unit="PCT", decimals=2, figures=[], sort=74),
        # T03 — 목표 추천 (규칙 기반, Phase 2.6)
        # Phase 2.6 목표 추천 엔진 — 제약 상한(지주 한도 − 안전 마진) · 기조 · 추세 · 폭(규칙 GOAL_REC_POLICY)
        metric("corp_rec_ceiling", "기업여신 목표 환산 상한(지주 한도 − 안전 마진)", "DIFF", {"a": mref("cap_asset_growth", "지주 총자산 최대 증가율", "%"), "b": {"rule": "GOAL_REC_POLICY", "path": "corp_loan_growth.safety_margin", "label": "안전 마진", "unit": "%p"}}, wf=HQ, unit="PCT", decimals=1, figures=["cc_corp_ceiling"], sort=74),
        metric("corp_growth_rec", "기업여신 확대 제안 목표(범위 중앙)", "GOAL_RANGE_REC", {"base": mref("corp_goal", "현재 목표", "%"), "stance": {"rule": "GOAL_REC_POLICY", "path": "corp_loan_growth.stance", "label": "기조(+1 확대)"}, "low_delta": {"rule": "GOAL_REC_POLICY", "path": "corp_loan_growth.low_delta", "label": "폭 하한"}, "high_delta": {"rule": "GOAL_REC_POLICY", "path": "corp_loan_growth.high_delta", "label": "폭 상한"}, "trend": mref("corp_cagr", "3개년 추세(CAGR)", "%"), "trend_weight": {"rule": "GOAL_REC_POLICY", "path": "corp_loan_growth.trend_weight", "label": "추세 가중치"}, "ceiling": mref("corp_rec_ceiling", "환산 상한", "%")}, wf=HQ, unit="PCT", decimals=2, figures=[], sort=75,
               description="Phase 2.6 — 현재 목표를 기준으로 기조 방향 폭을 더하고 지주 한도 환산 상한으로 제한"),
        metric("corp_rec_high", "기업여신 추천 상한", "VALUE", {"value": mref("corp_growth_rec", "추천 범위 상한", "%", "high")}, wf=HQ, unit="PCT", decimals=1, figures=["cc_corp_proposed"], sort=76),
        metric("corp_rec_headroom", "환산 상한 대비 여유", "DIFF", {"a": mref("corp_rec_ceiling", "환산 상한", "%"), "b": mref("corp_rec_high", "추천 상한", "%")}, wf=HQ, unit="PP", decimals=1, figures=["cc_corp_headroom"], sort=77),
        metric("hh_growth_rec", "가계여신 관리 제안 목표(범위 중앙)", "GOAL_RANGE_REC", {"base": mref("hh_goal", "현재 관리목표", "%"), "stance": {"rule": "GOAL_REC_POLICY", "path": "hh_loan_growth.stance", "label": "기조(−1 관리)"}, "low_delta": {"rule": "GOAL_REC_POLICY", "path": "hh_loan_growth.low_delta", "label": "폭 하한"}, "high_delta": {"rule": "GOAL_REC_POLICY", "path": "hh_loan_growth.high_delta", "label": "폭 상한"}, "trend": mref("hh_cagr", "3개년 추세(CAGR)", "%"), "trend_weight": {"rule": "GOAL_REC_POLICY", "path": "hh_loan_growth.trend_weight", "label": "추세 가중치"}, "floor": {"rule": "GOAL_REC_POLICY", "path": "hh_loan_growth.floor", "label": "하한"}}, wf=HQ, unit="PCT", decimals=2, figures=[], sort=78,
               description="Phase 2.6.6 — limit형 목표: 관리 기조(−1)로 현재 관리목표보다 낮은 범위"),
        metric("hh_bal_usage", "가계여신 잔액 관리 한도 소진율", "USAGE_RATE", {"used": mref("hh_bal", "현재 잔액", "조원"), "limit": mref("hh_bal_limit", "관리 한도", "조원")}, wf=HQ, unit="PCT", decimals=1, figures=[], sort=79),
        # Q15 · Q17 추천안 — 제안 반영 후 지표 (가정은 규칙 PROPOSAL_IMPACT)
        metric("corp_rec_delta", "기업여신 제안 대비 현재 증가율 차이", "DIFF", {"a": mref("corp_growth_rec", "제안 목표", "%"), "b": mref("corp_growth", "현재 증가율", "%")}, wf=HQ, unit="PP", decimals=2, figures=[], sort=90),
        metric("corp_rec_increment", "제안 반영 기업여신 증가분", "PCT_AMOUNT", {"base": q(LB, {"account_code": "CORP", "ym": "$latest"}, "balance", label="기업자금대출금", unit="백만원"), "rate": mref("corp_rec_delta", "증가율 차이", "%p"), "divisor": {"const": 1_000_000, "label": "백만원→조원"}}, wf=HQ, unit="KRW_TN", decimals=2, figures=[], sort=91),
        metric("corp_rwa_usage_proposed", "기업부문 신용RWA 소진율(제안 반영)", "PROPOSED_USAGE", {"used": q(CC, {"item_code": "RWA_CORP_USED", "ym": "$latest"}, "value", label="기업 RWA 사용", unit="조원"), "increment": mref("corp_rec_increment", "기업여신 증가분", "조원"), "factor": {"rule": "PROPOSAL_IMPACT", "path": "corp_rwa_factor", "label": "기업여신 RWA 환산계수(시뮬레이션 가정)"}, "limit": q(CC, {"item_code": "RWA_CORP_ALLOC", "ym": "$latest"}, "value", label="기업 RWA 배분", unit="조원")}, wf=HQ, unit="PCT", decimals=1, figures=[], sort=92),
        metric("corp_rwa_increment", "제안 반영 기업 신용RWA 증가분", "LINEAR", {"a": {"const": 0, "label": "기준"}, "b": mref("corp_rec_increment", "기업여신 증가분", "조원"), "c": {"rule": "PROPOSAL_IMPACT", "path": "corp_rwa_factor", "label": "RWA 환산계수(시뮬레이션 가정)"}}, wf=HQ, unit="KRW_TN", decimals=2, figures=[], sort=100),
        # Phase 6.2.4 — BIS 시산: 총 RWA 항목(CAPITAL_CONSTRAINT.RWA_TOTAL)이 없으면 '시산 불가'. 수령 후 관리자 화면에서 사용으로 바꾸고 관리기준을 확인
        metric("bis_after_proposal", "BIS 총자본비율 시산(제안 반영)", "BIS_RATIO_SIM", {"bis_now": mref("bis_total", "현재 BIS 총자본비율", "%"), "rwa_now": cc("RWA_TOTAL", "총 RWA"), "rwa_increment": mref("corp_rwa_increment", "RWA 증가분", "조원"), "min_ratio": {"const": 13.0, "label": "관리기준(시뮬레이션 가정)", "unit": "%"}}, wf=HQ, unit="PCT", decimals=2, figures=[], sort=101, enabled=False,
               description="시산 불가 — 총 RWA(RWA_TOTAL) 데이터 수령 시 사용. 자본 불변 가정"),
        metric("corp_rwa_margin_proposed", "기업부문 신용RWA 한도 여유(제안 반영)", "DIFF", {"a": {"const": 100, "label": "한도(100%)", "unit": "%"}, "b": mref("corp_rwa_usage_proposed", "제안 반영 소진율", "%")}, wf=HQ, unit="PP", decimals=1, figures=[], sort=93),
        metric("corp_rec_goal_delta", "기업여신 제안 목표 − 현재 목표", "DIFF", {"a": mref("corp_growth_rec", "제안 목표", "%"), "b": mref("corp_goal", "현재 목표", "%")}, wf=HQ, unit="PP", decimals=2, figures=[], sort=94),
        metric("total_asset_expected", "제안 반영 총자산 예상 증가율", "LINEAR", {"a": mref("bank_asset_target", "은행 목표 총자산증가율", "%"), "b": mref("corp_rec_goal_delta", "기업여신 목표 변화", "%p"), "c": {"rule": "PROPOSAL_IMPACT", "path": "corp_loan_asset_weight", "label": "기업여신의 총자산 기여 비중(시뮬레이션 가정)"}}, wf=HQ, unit="PCT", decimals=1, figures=[], sort=95),
        metric("total_asset_margin_proposed", "총자산 증가율 한도 여유(제안 반영)", "DIFF", {"a": mref("cap_asset_growth", "지주 한도", "%"), "b": mref("total_asset_expected", "제안 반영 예상", "%")}, wf=HQ, unit="PP", decimals=1, figures=[], sort=96),
        metric("inclusive_supply_py", "포용금융 공급 전년 실적", "VALUE", {"value": kpi("INCLUSIVE_SUPPLY_PY", "전년 실적")}, wf=HQ, unit="KRW_TN", decimals=2, scale=1_000_000, figures=[], sort=97),
        metric("inclusive_supply_rec", "포용금융 공급 확대 제안(범위 중앙)", "GROWTH_RANGE_REC", {"base": mref("inclusive_supply_py", "전년 실적", "백만원"), "low_rt": {"rule": "PROPOSAL_IMPACT", "path": "inclusive_supply_growth.low", "label": "공급 증가율 하한"}, "high_rt": {"rule": "PROPOSAL_IMPACT", "path": "inclusive_supply_growth.high", "label": "공급 증가율 상한"}}, wf=HQ, unit="KRW_TN", decimals=2, scale=1_000_000, figures=[], sort=98),
        metric("hh_rwa_usage_incl_inclusive", "가계부문 신용RWA 소진율(포용금융 제안 포함)", "PROPOSED_USAGE", {"used": q(CC, {"item_code": "RWA_HH_USED", "ym": "$latest"}, "value", label="가계 RWA 사용", unit="조원"), "increment": mref("inclusive_net_tn", "포용금융 순증", "조원"), "factor": {"rule": "PROPOSAL_IMPACT", "path": "inclusive_rwa_factor", "label": "포용금융 RWA 환산계수(시뮬레이션 가정)"}, "limit": q(CC, {"item_code": "RWA_HH_ALLOC", "ym": "$latest"}, "value", label="가계 RWA 배분", unit="조원")}, wf=HQ, unit="PCT", decimals=1, figures=[], sort=102),
        metric("hh_rwa_margin_incl_inclusive", "가계부문 신용RWA 한도 여유(포용금융 포함)", "DIFF", {"a": {"const": 100, "label": "한도(100%)", "unit": "%"}, "b": mref("hh_rwa_usage_incl_inclusive", "소진율", "%")}, wf=HQ, unit="PP", decimals=1, figures=[], sort=103),
        metric("inclusive_net_tn", "포용금융 공급 순증(조원)", "PCT_AMOUNT", {"base": mref("inclusive_supply_net", "순증(백만원)", "백만원"), "rate": {"const": 100}, "divisor": {"const": 1_000_000, "label": "백만원→조원"}}, wf=HQ, unit="KRW_TN", decimals=2, figures=[], sort=101),
        metric("inclusive_supply_net", "포용금융 공급 순증(백만원)", "DIFF", {"a": mref("inclusive_supply_rec", "제안", "백만원"), "b": mref("inclusive_supply_py", "전년 실적", "백만원")}, wf=HQ, unit="KRW_MN", decimals=0, figures=[], sort=100),
        metric("rwa_corp_margin", "기업부문 신용RWA 한도 여유", "DIFF", {"a": {"const": 100, "label": "한도(100%)", "unit": "%"}, "b": mref("rwa_corp_usage", "소진율", "%")}, wf=HQ, unit="PP", decimals=1, figures=[], sort=76),
        # T03 — 지역본부 신규취급 (영업점 화면 bt* 수치)
        metric("d300_corp_new_target", "수도권지역본부 기업여신 신규취급 목표", "VALUE", {"value": kpi("D300_CORP_NEW_TARGET", "목표")}, wf=HQ, unit="KRW_TN", decimals=2, scale=1_000_000, figures=["bt1_target"], sort=80),
        metric("d300_corp_new_actual", "수도권지역본부 기업여신 신규취급 실적", "VALUE", {"value": kpi("D300_CORP_NEW_ACTUAL", "실적")}, wf=HQ, unit="KRW_TN", decimals=2, scale=1_000_000, figures=["bt1_actual"], sort=81),
        metric("d300_corp_new_progress", "수도권지역본부 기업여신 신규취급 진행률", "SHARE", {"numerator": mref("d300_corp_new_actual", "실적", "백만원"), "denominator": mref("d300_corp_new_target", "목표", "백만원")}, wf=HQ, unit="PCT", decimals=1, figures=[], sort=82),
        metric("d500_corp_new_target", "충북지역본부 기업여신 신규취급 목표", "VALUE", {"value": kpi("D500_CORP_NEW_TARGET", "목표")}, wf=HQ, unit="KRW_TN", decimals=2, scale=1_000_000, figures=[], sort=83),
        metric("d500_corp_new_actual", "충북지역본부 기업여신 신규취급 실적", "VALUE", {"value": kpi("D500_CORP_NEW_ACTUAL", "실적")}, wf=HQ, unit="KRW_TN", decimals=2, scale=1_000_000, figures=[], sort=84),
        metric("d500_corp_new_progress", "충북지역본부 기업여신 신규취급 진행률", "SHARE", {"numerator": mref("d500_corp_new_actual", "실적", "백만원"), "denominator": mref("d500_corp_new_target", "목표", "백만원")}, wf=HQ, unit="PCT", decimals=1, figures=[], sort=85),
        metric("d300_hh_new_limit", "수도권지역본부 가계여신 월 신규취급 한도", "VALUE", {"value": kpi("D300_HH_NEW_LIMIT", "월 한도")}, wf=HQ, unit="KRW_BN", decimals=0, scale=100, figures=["bt2_target"], sort=86),
        metric("d300_hh_new_actual", "수도권지역본부 가계여신 8월 신규취급", "VALUE", {"value": kpi("D300_HH_NEW_ACTUAL", "8월 취급")}, wf=HQ, unit="KRW_BN", decimals=0, scale=100, figures=["bt2_actual"], sort=87),
        metric("d300_hh_new_usage", "수도권지역본부 가계여신 신규취급 한도 소진율", "USAGE_RATE", {"used": mref("d300_hh_new_actual", "취급", "백만원"), "limit": mref("d300_hh_new_limit", "한도", "백만원")}, wf=HQ, unit="PCT", decimals=1, figures=[], sort=88),
    ]


RULE_IMPACT = ("PROPOSAL_IMPACT", "제안 반영 영향 가정 (시뮬레이션 가정 · Q15/Q17 추천안)", "threshold",
               "제안 목표를 반영했을 때 RWA·총자산 영향을 계산하는 환산계수. 실측 계수(신규 취급의 평균 위험가중치, 총자산 구성비)로 교체",
               {"corp_rwa_factor": 0.19, "inclusive_rwa_factor": 0.49, "hh_rwa_factor": 0.35, "corp_loan_asset_weight": 0.3, "inclusive_supply_growth": {"low": 5, "high": 12},
                "note": "corp_rwa_factor 0.19 · inclusive_rwa_factor 0.49 는 정의서 목업값(86.4% · 96.2%)을 재현하도록 맞춘 가정값"})

RULE_BODY_V1 = {"corp_loan_growth": {"low_delta": 0.5, "high_delta": 1.0, "ceiling": 8.0}, "hh_loan_growth": {"low_delta": -1.0, "high_delta": -0.5, "floor": 0}}
RULE_BODY_V2 = {
    # stance: +1 확대 · −1 관리 · 0 유지 (정책 · 경영 의사결정 기조) / 폭은 양수 크기 / trend_weight 0 = 현재 목표 기준(추세는 근거로만 표시)
    "corp_loan_growth": {"stance": 1, "low_delta": 0.5, "high_delta": 1.0, "safety_margin": 0.2, "trend_weight": 0},
    "hh_loan_growth": {"stance": -1, "low_delta": 0.5, "high_delta": 1.0, "floor": 0, "trend_weight": 0},
    "note": "Q28 추천안: 기조 · 폭 · 안전 마진은 정책 결정 값(관리자 편집). 상한 = 지주 총자산 최대 증가율 − 안전 마진",
}
RULE = ("GOAL_REC_POLICY", "경영목표 추천 정책(기조 · 폭 · 추세 · 제약)", "threshold", "GOAL_RANGE_REC 입력 — 기조(+1/−1/0) · 폭 · 추세 가중치 · 안전 마진/하한", RULE_BODY_V2)

Q16 = "Q16 추천안: 정의서 화면값은 1년 밀린 값(45.90%=2025.08, 46.53%=2024.08) → 계산값 기준으로 대조"
U15 = {"unmapped": "산식 미정의 — 'AI Agent 산출' 수치는 커널 수식이 정해져야 계산(LLM 은 수치를 만들지 않음)", "question": "Q15"}
T = lambda m: {"metric": m}  # noqa: E731

# 컬럼명 → 바인딩 (표 공통). 표마다 다르면 'T03.컬럼' 키로 덮어쓴다.
BINDINGS: dict[str, dict[str, Any]] = {
    "BASE_YM": {"base_ym": LB},
    "BIZ_DIV_CD": {"const": "LOAN"},
    "BIZ_DIV_NM": {"const": "여신"},
    "PROPOSAL_VER_NO": {"version": True},
    "TOTAL_ASSET_GROWTH_TARGET_RT": T("bank_asset_target"),
    "TOTAL_ASSET_GROWTH_LIMIT_RT": T("cap_asset_growth"),
    "TOTAL_ASSET_GROWTH_MARGIN_RT": T("bank_asset_headroom"),
    "LOAN_CREDIT_RWA_USED_AMT": T("loan_rwa_used"),
    "LOAN_CREDIT_RWA_LIMIT_AMT": T("loan_rwa_limit"),
    "LOAN_CREDIT_RWA_USAGE_RT": T("loan_rwa_usage"),
    "LOAN_NIM_CURRENT_AMT": T("nim_current_tn"),
    "LOAN_NIM_ANNUAL_TARGET_AMT": T("loan_nim_target"),
    "LOAN_NIM_TARGET_AMT": T("loan_nim_target"),
    "LOAN_NIM_PROGRESS_RT": T("loan_nim_progress"),
    "LOAN_NIM_INCOME_AMT": T("nim_2026"),
    "PY_LOAN_NIM_INCOME_AMT": T("nim_2025"),
    "LOAN_NIM_YOY_RT": T("nim_growth"),
    "LOAN_INCOME_SHARE_RT": {"metric": "nim_share_2026", "expected": "45.44%", "expected_note": Q16},
    "PY_LOAN_INCOME_SHARE_RT": {"metric": "nim_share_2025", "expected": "45.90%", "expected_note": Q16},
    "LOAN_INCOME_SHARE_YOY_DIFF": T("nim_share_delta"),
    "LOAN_INCOME_SHARE_DIFF_RT": T("nim_share_delta"),
    "TOTAL_INCOME_AMT": T("total_rev_2026"),
    "PY_TOTAL_INCOME_AMT": T("total_rev_2025"),
    "TOTAL_INCOME_YOY_RT": T("total_rev_growth"),
    "CORP_INTEREST_INCOME_AMT": T("corp_int_rev"),
    "HH_INTEREST_INCOME_AMT": T("hh_int_rev"),
    "LOAN_SHARE_Y1_RT": T("nim_share_2024"),
    "LOAN_SHARE_Y2_RT": T("nim_share_2025"),
    "LOAN_SHARE_Y3_RT": T("nim_share_2026"),
    "CORP_LOAN_BAL_AMT": T("corp_bal"),
    "HH_LOAN_BAL_AMT": T("hh_bal"),
    "HH_LOAN_BAL_CURRENT_AMT": T("hh_bal"),
    "CORP_LOAN_SHARE_RT": T("corp_share"),
    "HH_LOAN_SHARE_RT": T("hh_share"),
    "CORP_LOAN_YOY_RT": T("corp_growth"),
    "HH_LOAN_YOY_RT": T("hh_growth"),
    "CORP_LOAN_GROWTH_RT": T("corp_growth"),
    "CORP_LOAN_GROWTH_CURRENT_RT": T("corp_growth"),
    "HH_LOAN_GROWTH_RT": T("hh_growth"),
    "HH_LOAN_GROWTH_CURRENT_RT": T("hh_growth"),
    "CORP_LOAN_GROWTH_TARGET_RT": T("corp_goal"),
    "CORP_LOAN_GROWTH_GAP_RT": T("corp_gap"),
    "HH_LOAN_GROWTH_LIMIT_RT": T("hh_goal"),
    "HH_LOAN_GROWTH_EXCESS_RT": T("hh_gap"),
    "HH_LOAN_BAL_LIMIT_AMT": T("hh_bal_limit"),
    "HH_LOAN_BAL_REMAIN_AMT": T("hh_bal_remain"),
    "Q3_LOAN_INCOME_AMT": T("q3_loan_income"),
    "Q3_LOAN_INCOME_CURRENT_AMT": T("q3_loan_income"),
    "Q3_LOAN_INCOME_TARGET_AMT": T("q3_loan_income_target"),
    "Q3_LOAN_INCOME_GAP_AMT": T("q3_loan_income_gap"),
    "GRADE_5C_PLUS_BORROWER_RT": T("grade_5c_rt"),
    "GRADE_5C_PLUS_CURRENT_RT": T("grade_5c_rt"),
    "GRADE_5C_PLUS_TARGET_RT": T("grade_5c_target"),
    "GRADE_5C_PLUS_GAP_RT": T("grade_5c_gap"),
    "CORP_INTEREST_YIELD_RT": T("ros_corp"),
    "HH_INTEREST_YIELD_RT": T("ros_hh"),
    "INTEREST_YIELD_DIFF_RT": T("ros_gap"),
    "AGENT_SUMMARY_TEXT": {"insight": "att-corp-gap"},
    "AGENT_ANALYSIS_TEXT": {"insight": "ins-divergence"},
    "AGENT_TARGET_COMMENT_TEXT": {"proposal": "prop-corp-growth", "field": "judgement"},
    "AGENT_CORP_GROWTH_PROPOSAL_RT": T("corp_growth_rec"),
    "AGENT_CORP_PROPOSAL_REASON_TEXT": {"proposal": "prop-corp-growth", "field": "judgement"},
    # Q17 추천안: T03(목표설정) 의 RWA 소진율·여유는 '제안 반영 후' 기준
    "CORP_RWA_USAGE_RT": T("corp_rwa_usage_proposed"),
    "CORP_RWA_MARGIN_RT": T("corp_rwa_margin_proposed"),
    # Q15 추천안: Agent 산출 수치를 규칙 기반 커널 산식으로 정의
    "TOTAL_ASSET_EXPECTED_GROWTH_RT": T("total_asset_expected"),
    "TOTAL_ASSET_LIMIT_MARGIN_RT": T("total_asset_margin_proposed"),
    "INCLUSIVE_FIN_SUPPLY_PROPOSAL_AMT": T("inclusive_supply_rec"),
    "HH_RWA_USAGE_INCL_INCLUSIVE_RT": T("hh_rwa_usage_incl_inclusive"),
    "HH_RWA_MARGIN_INCL_INCLUSIVE_RT": T("hh_rwa_margin_incl_inclusive"),
    "CAPITAL_CORP_NEW_LOAN_TARGET_AMT": T("d300_corp_new_target"),
    "CAPITAL_CORP_NEW_LOAN_CURRENT_AMT": T("d300_corp_new_actual"),
    "CAPITAL_CORP_NEW_LOAN_PROGRESS_RT": T("d300_corp_new_progress"),
    "CHUNGBUK_CORP_NEW_LOAN_TARGET_AMT": T("d500_corp_new_target"),
    "CHUNGBUK_CORP_NEW_LOAN_CURRENT_AMT": T("d500_corp_new_actual"),
    "CHUNGBUK_CORP_NEW_LOAN_PROGRESS_RT": T("d500_corp_new_progress"),
    "CAPITAL_HH_NEW_LOAN_LIMIT_AMT": T("d300_hh_new_limit"),
    "CAPITAL_HH_NEW_LOAN_CURRENT_AMT": T("d300_hh_new_actual"),
    "CAPITAL_HH_NEW_LOAN_USAGE_RT": T("d300_hh_new_usage"),
}


# 운영 DB 연결 갱신 — 현재 연결이 아래 '이전 기본값' 과 같을 때만 새 기본값으로 바꾼다(관리자가 바꾼 연결은 유지)
BINDING_UPGRADES: dict[str, list[dict[str, Any]]] = {
    "LOAN_INCOME_SHARE_RT": [{"metric": "nim_share_2026"}],
    "PY_LOAN_INCOME_SHARE_RT": [{"metric": "nim_share_2025"}],
    "CORP_RWA_USAGE_RT": [{"metric": "rwa_corp_usage"}],
    "CORP_RWA_MARGIN_RT": [{"metric": "rwa_corp_margin"}],
    **{c: [U15] for c in ("TOTAL_ASSET_EXPECTED_GROWTH_RT", "TOTAL_ASSET_LIMIT_MARGIN_RT", "INCLUSIVE_FIN_SUPPLY_PROPOSAL_AMT", "HH_RWA_USAGE_INCL_INCLUSIVE_RT", "HH_RWA_MARGIN_INCL_INCLUSIVE_RT")},
}
