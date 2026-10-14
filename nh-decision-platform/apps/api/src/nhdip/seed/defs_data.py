"""데이터셋 정의 · 지표 · 바인딩 · 워크플로우 시드 (정의만 — Phase I · Q135).

업무 수치는 시드가 넣지 않는다. 시연 자료는 `nhdip.sample` 이 실제 파일(엑셀 · PDF)로 만들어 업로드 경로로 올린다.
실데이터가 오면 같은 데이터셋 정의로 파일만 업로드하면 된다(정의가 다르면 관리자 화면에서 컬럼·별칭 수정).
"""
from __future__ import annotations

from typing import Any


def col(name, label, type_="str", required=False, aliases=None):
    return {"name": name, "label": label, "type": type_, "required": required, "aliases": aliases or []}


# ═════════════════════════ 데이터셋 정의 ═════════════════════════
DATASETS = [
    dict(
        code="PL_PRODUCT_SEGMENT", name="2633 상품부문별 손익계산서", origin="bank", kind="fact",
        description="상품부문별 손익 — 전체 수익 · 여신 이자마진 · 기업/가계 이자수익 (8월 누계)",
        file_pattern=r"\((\d{6})\)2633_상품부문별손익계산서\.(xlsx|csv|json)", refresh_cycle="월",
        columns=[col("ym", "기준년월", "str", True, ["기준월", "YYYYMM"]), col("item_code", "과목코드", "str", True, ["과목", "코드"]), col("item_name", "과목명", "str", False, ["계정명"]), col("amount", "금액(백만원)", "num", True, ["금액", "누계"]), col("src_ref", "원천 셀", "str", False, ["셀"])],
        key_columns=["ym", "item_code"], as_of_column="ym",
        mapping={"report_code": "2633", "unit": "백만원", "used_by": ["여신 종합수익", "수익성 트래킹", "기업·가계 이자수익 비교"],
                 "concepts": [{"label": "BusinessDomain", "key": "기업여신", "about": True}, {"label": "BusinessDomain", "key": "가계여신", "about": True}]},
        quality_rules=[{"rule": "range", "column": "amount", "min": 0}, {"rule": "allowed", "column": "item_code", "values": ["TOTAL_REVENUE", "LOAN_NIM", "CORP_INTEREST", "HH_INTEREST", "HH_ETC_INTEREST", "HOUSE_INTEREST", "PUBLIC_INTEREST"], "severity": "warning"}],
    ),
    dict(
        code="LOAN_BALANCE_MONTHLY", name="2020 과목별 월별 여신현황", origin="bank", kind="fact",
        description="과목별 여신 잔액 (월말)", file_pattern=r"\((\d{6})\)2020 과목별 월별 여신현황\.(xlsx|csv|json)", refresh_cycle="월",
        columns=[col("ym", "기준년월", "str", True, ["기준월"]), col("account_code", "과목코드", "str", True, ["과목"]), col("account_name", "과목명", "str"), col("balance", "잔액(백만원)", "num", True, ["잔액", "월말잔액"]), col("src_ref", "원천 셀", "str")],
        key_columns=["ym", "account_code"], as_of_column="ym",
        mapping={"report_code": "2020", "unit": "백만원", "used_by": ["기업여신", "가계여신", "규모·비중·추이 비교"],
                 "concepts": [{"label": "BusinessDomain", "key": "기업여신", "about": True}, {"label": "BusinessDomain", "key": "가계여신", "about": True}]},
        quality_rules=[{"rule": "range", "column": "balance", "min": 0}],
    ),
    dict(
        code="PROVISION_BY_PRODUCT", name="7790 상품별 충당금", origin="bank", kind="fact",
        description="상품코드별 손실충당금 및 충당부채 총계 (합계 row 포함)", file_pattern=r"\((\d{6})\)7790_상품별_충당금\.(xlsx|csv|json)", refresh_cycle="월",
        columns=[col("ym", "기준년월", "str", True), col("product_code", "상품코드", "str", True, ["상품 코드"]), col("product_name", "상품명", "str"), col("provision", "충당금(백만원)", "num", True, ["손실충당금 및 충당부채 총계", "X"]), col("is_total", "합계 행", "bool", False, ["합계"]), col("src_ref", "원천 셀", "str")],
        key_columns=["ym", "product_code"], as_of_column="ym",
        mapping={"report_code": "7790", "unit": "백만원", "used_by": ["포용금융 충당금 비중"], "concepts": [{"label": "PolicyTheme", "key": "포용금융", "about": True}]},
        quality_rules=[{"rule": "sum_equals", "column": "provision", "total_flag": "is_total", "group": "ym", "tolerance_pct": 100, "severity": "warning"}, {"rule": "max_change", "column": "provision", "pct": 50, "severity": "warning"}],
    ),
    dict(
        code="INCLUSIVE_PRODUCTS", name="포용금융 대상 상품 마스터", origin="bank", kind="master",
        description="포용금융 대상 상품코드 21건 (여신정책협의회 운영기준)", refresh_cycle="수시",
        columns=[col("product_code", "상품코드", "str", True), col("product_name", "상품명", "str", True), col("product_group", "상품군", "str", True)],
        key_columns=["product_code"],
        mapping={"unit": "-", "used_by": ["포용금융 충당금 비중", "상품군별 기여도"],
                 "nodes": [{"label": "Product", "key_col": "product_code", "name_col": "product_name"}, {"label": "ProductGroup", "key_col": "product_group"}],
                 "edges": [{"type": "IN_GROUP", "from": {"label": "Product", "col": "product_code"}, "to": {"label": "ProductGroup", "col": "product_group"}}],
                 "concepts": [{"label": "PolicyTheme", "key": "포용금융", "edges": [], "about": True}] + [{"label": "ProductGroup", "key": g, "edges": [{"type": "PART_OF_THEME", "to_label": "PolicyTheme", "to": "포용금융"}]} for g in ("새희망홀씨대출", "햇살론", "사잇돌")]},
    ),
    dict(
        code="MODEL_MONITORING_GRADE", name="신용평가모형 등급별 모니터링 집계", origin="bank", kind="fact",
        description="모형·등급별 관측건수 · 부도건수 · 구성비 (기준시점 분포 포함)", refresh_cycle="분기",
        columns=[col("as_of", "기준일", "date", True), col("model_code", "모형코드", "str", True), col("grade", "등급", "str", True), col("grade_seq", "등급순서", "int", True), col("obs_count", "관측건수", "int", False), col("default_count", "부도건수", "int", False), col("obs_share", "구성비(%)", "num", True), col("ks", "K-S(등급)", "num"), col("sdr_rank", "SDR 순위", "int"), col("exposure_amt", "익스포저(억원)", "num")],
        key_columns=["as_of", "model_code", "grade"], as_of_column="as_of",
        mapping={"unit": "건", "used_by": ["모형 모니터링", "6B 등급 특이사항", "PSI"],
                 "concepts": [{"label": "RatingModel", "key": "CORP_MICRO", "props": {"name": "일반기업 소기업 모형"}, "edges": [{"type": "APPLIES_TO", "to_label": "Segment", "to": "소기업"}], "about": True}, {"label": "Segment", "key": "소기업", "props": {"name": "소기업", "portfolio": "corp"}, "edges": [{"type": "BELONGS_TO", "to_label": "BusinessDomain", "to": "기업여신"}]}, {"label": "BusinessDomain", "key": "기업여신"}]},
        quality_rules=[{"rule": "le_column", "column": "default_count", "other": "obs_count"}, {"rule": "range", "column": "obs_share", "min": 0, "max": 100}],
    ),
    dict(
        code="PD_MASTER_SCALE", name="PD Master Scale", origin="bank", kind="master",
        description="모형·등급별 예측부도율(최소·대표·최대)", refresh_cycle="연",
        columns=[col("model_code", "모형코드", "str", True), col("grade", "등급", "str", True), col("pd_min", "최소(%)", "num"), col("pd_mid", "대표값(%)", "num", True), col("pd_max", "최대(%)", "num", True)],
        key_columns=["model_code", "grade"],
        mapping={"unit": "%", "used_by": ["등급계량화 검증"]},
        quality_rules=[{"rule": "le_column", "column": "pd_mid", "other": "pd_max"}],
    ),
    dict(
        code="DEFAULT_RATE_MONTHLY", name="월별 부도율 집계", origin="bank", kind="fact",
        description="기업 규모별 · 개인 풀별 월별 신규 부도 발생 (부도건수 · 관측건수)", refresh_cycle="월",
        columns=[col("ym", "기준년월", "str", True), col("segment_key", "구분코드", "str", True), col("segment_label", "구분명", "str"), col("portfolio", "포트폴리오", "str", True), col("default_count", "부도건수", "int", True), col("obs_count", "관측건수", "int", True)],
        key_columns=["ym", "segment_key"], as_of_column="ym",
        mapping={"unit": "건", "used_by": ["월별 부도율 추이"],
                 "concepts": [{"label": "Segment", "key": k, "props": {"name": k, "portfolio": "corp"}, "edges": [{"type": "BELONGS_TO", "to_label": "BusinessDomain", "to": "기업여신"}]} for k in ("대기업", "외감", "비외감", "소기업", "기업형소호")]},
        quality_rules=[{"rule": "le_column", "column": "default_count", "other": "obs_count"}, {"rule": "period_continuity", "column": "ym", "group": "segment_key", "severity": "warning"}],
    ),
    dict(
        code="CAPITAL_CONSTRAINT", name="자본·한도 제약 (지주 한도 · RWA 배분)", origin="bank", kind="fact",
        description="총자산 최대 증가율 · RWA 순증 한도 · 부서별 신용RWA 배분/사용", refresh_cycle="반기",
        columns=[col("ym", "기준년월", "str", True), col("item_code", "항목코드", "str", True), col("item_name", "항목명", "str"), col("value", "값", "num", True), col("unit", "단위", "str")],
        key_columns=["ym", "item_code"], as_of_column="ym",
        mapping={"unit": "%·조원", "used_by": ["총자산·RWA 제약", "제약 검증"], "concepts": [{"label": "CapitalConstraint", "key": "RWA 순증 한도", "about": True}, {"label": "CapitalConstraint", "key": "총자산 증가율 한도", "about": True}]},
    ),
    dict(
        code="PEER_BANK_STATS", name="타행 비교 통계 (외부)", origin="ext", kind="fact",
        description="외부 공시 기반 타행 평균 지표", refresh_cycle="분기",
        columns=[col("ym", "기준년월", "str", True), col("stat_code", "지표코드", "str", True), col("stat_name", "지표명", "str"), col("value", "값", "num", True), col("issuer", "출처", "str")],
        key_columns=["ym", "stat_code"], as_of_column="ym",
        mapping={"unit": "%", "used_by": ["중·저신용자 비중 비교"]},
    ),
]


# 월별 부도율 구분 (키 · 라벨 · 포트폴리오) — 값은 업로드 자료(DEFAULT_RATE_MONTHLY)
DR_SEGMENTS = [
    ("corp_large", "대기업", "corp"),
    ("corp_audited", "외감", "corp"),
    ("corp_unaudited", "비외감", "corp"),
    ("corp_micro", "소기업", "corp"),
    ("corp_soho", "기업형소호", "corp"),
    ("pool_1", "풀 1 (임시)", "retail"),
    ("pool_2", "풀 2 (임시)", "retail"),
    ("pool_3", "풀 3 (임시)", "retail"),
    ("pool_4", "풀 4 (임시)", "retail"),
    ("pool_5", "풀 5 (임시)", "retail"),
]


# ═════════════════════════ 지표 정의 ═════════════════════════
def q(dataset, where, col_, agg="first", label=None, unit="", order_by=None):
    ref: dict[str, Any] = {"q": {"dataset": dataset, "where": where, "col": col_, "agg": agg}}
    if order_by:
        ref["q"]["order_by"] = order_by
    if label:
        ref["label"] = label
    if unit:
        ref["unit"] = unit
    return ref


def mref(code, label=None, unit="", field="value"):
    r: dict[str, Any] = {"metric": code, "label": label or code, "unit": unit}
    if field != "value":
        r["field"] = field
    return r


def metric(code, label, formula, args, *, wf, unit="", decimals=None, scale=None, figures=None, sort=0, enabled=True, description=""):
    return dict(code=code, label=label, formula=formula, args=args, workflow_code=wf, unit=unit, decimals=decimals, scale=scale, figure_ids=figures or [code], sort=sort, enabled=enabled, description=description)


def metrics() -> list[dict[str, Any]]:
    M: list[dict[str, Any]] = []
    MM = "wf_model_monitoring"
    G = "MODEL_MONITORING_GRADE"
    cur = {"model_code": "CORP_MICRO", "as_of": "$latest"}
    base = {"model_code": "CORP_MICRO", "as_of": "$earliest"}
    g6b = {**cur, "grade": "6B"}
    M += [
        metric("dr_6b", "소기업 6B 등급 실제부도율", "DEFAULT_RATE", {"default_count": q(G, g6b, "default_count", label="부도건수", unit="건"), "obs_count": q(G, g6b, "obs_count", label="전체건수", unit="건")}, wf=MM, unit="PCT", decimals=3, sort=1),
        metric("pd_mid_6b", "예측부도율 대표값", "VALUE", {"value": q("PD_MASTER_SCALE", {"model_code": "CORP_MICRO", "grade": "6B"}, "pd_mid", label="대표값", unit="%")}, wf=MM, unit="PCT", decimals=3, sort=2),
        metric("pd_max_6b", "예측부도율 최대값", "VALUE", {"value": q("PD_MASTER_SCALE", {"model_code": "CORP_MICRO", "grade": "6B"}, "pd_max", label="최대값", unit="%")}, wf=MM, unit="PCT", decimals=3, sort=3),
        metric("breach_gap_6b", "대표값 초과 폭", "PD_BREACH_CHECK", {"actual_dr": mref("dr_6b", "실제부도율", "%"), "pd_mid": mref("pd_mid_6b", "예측부도율 대표값", "%"), "pd_max": mref("pd_max_6b", "예측부도율 최대값", "%")}, wf=MM, unit="PP", decimals=3, sort=4),
        metric("exposure_6b", "6B 등급 익스포저 금액", "VALUE", {"value": q(G, g6b, "exposure_amt", label="익스포저", unit="억원")}, wf=MM, unit="KRW_TN", decimals=2, scale=10_000, sort=5),
        metric("total_obs", "소기업 모형 전체 익스포저 건수", "SUM", {"values": q(G, cur, "obs_count", "list", "등급별 관측건수", "건", "grade_seq")}, wf=MM, unit="CNT", decimals=0, sort=6),
        metric("total_defaults", "소기업 모형 전체 부도건수", "SUM", {"values": q(G, cur, "default_count", "list", "등급별 부도건수", "건", "grade_seq")}, wf=MM, unit="CNT", decimals=0, sort=7),
        metric("total_dr", "소기업 모형 전체 실제부도율", "DEFAULT_RATE", {"default_count": mref("total_defaults", "전체 부도건수", "건"), "obs_count": mref("total_obs", "전체 관측건수", "건")}, wf=MM, unit="PCT", decimals=3, sort=8),
        metric("psi_micro", "PSI", "PSI", {"base": q(G, base, "obs_share", "list", "기준시점 구성비", "%", "grade_seq"), "current": q(G, cur, "obs_share", "list", "비교시점 구성비", "%", "grade_seq")}, wf=MM, unit="RATIO", decimals=3, sort=9),
        metric("chi_stat", "카이제곱 통계량", "CHI_SQUARE_PD", {"obs": q(G, cur, "obs_count", "list", "등급별 관측건수(nᵢ)", "건", "grade_seq"), "defaults": q(G, cur, "default_count", "list", "등급별 부도건수(rᵢ)", "건", "grade_seq"), "pd": q("PD_MASTER_SCALE", {"model_code": "CORP_MICRO"}, "pd_mid", "list", "예측부도율 대표값(pᵢ)", "%")}, wf=MM, unit="RATIO", decimals=2, sort=10,
               description="목데이터 수기값 18.42 → 계산값으로 대체됨(분모 nᵢ·pᵢ·(1−pᵢ))"),
        metric("chi_critical", "임계값(자유도 12, 95%)", "CHI2_CRITICAL", {"df": mref("chi_stat", "자유도", "", "df"), "confidence": {"rule": "MDL_CHI_TEST", "path": "confidence", "label": "신뢰수준"}}, wf=MM, unit="RATIO", decimals=2, sort=11),
        metric("chi_test", "카이제곱 검정 판정", "CHI2_TEST", {"stat": mref("chi_stat", "χ²"), "critical": mref("chi_critical", "임계값")}, wf=MM, unit="", decimals=0, sort=12, figures=["chi_test"]),
        metric("monotonic_breaks", "서열화 위반 등급 수", "MONOTONIC_BREAKS", {"labels": q(G, cur, "grade", "list", "등급", "", "grade_seq"), "rates": q(G, cur, "obs_count", "list", "관측건수", "건", "grade_seq")}, wf=MM, decimals=0, sort=13, enabled=False,
               description="실제 판정은 등급별 부도율로 — grade_table 빌더가 수행. 지표로 쓰려면 부도율 목록 지표를 추가"),
        metric("auroc_micro", "AUROC", "AUROC_GRADED", {"defaults": q(G, cur, "default_count", "list", "등급별 부도건수", "건", "grade_seq"), "obs": q(G, cur, "obs_count", "list", "등급별 관측건수", "건", "grade_seq")}, wf=MM, unit="RATIO", decimals=3, sort=14,
               description="Q10 추천안 적용 — 등급 집계 기준(현재 확보 데이터) AUROC. 차주 단위 점수 수령 시 원자료 기준 수식으로 교체"),
        metric("ar_micro", "AR", "AR_FROM_AUROC", {"auroc": mref("auroc_micro", "AUROC")}, wf=MM, unit="PCT", decimals=2, sort=15, description="Q10 추천안 적용 — AR = (2·AUROC − 1) × 100"),
        metric("ks_micro", "K-S", "KS_GRADED", {"defaults": q(G, cur, "default_count", "list", "등급별 부도건수", "건", "grade_seq"), "obs": q(G, cur, "obs_count", "list", "등급별 관측건수", "건", "grade_seq")}, wf=MM, unit="PCT", decimals=1, sort=16, description="Q10 추천안 적용 — 등급 누적분포 기준 K-S"),
        metric("ard_micro", "AR 하락률", "AR_DECLINE", {"ar_dev": {"rule": "MDL_AR_BASELINE", "path": "CORP_MICRO", "label": "개발시점 AR(시뮬레이션 가정)"}, "ar_now": mref("ar_micro", "현재 AR", "%")}, wf=MM, unit="PCT", decimals=1, sort=17,
               description="Q22 추천안 적용 — 계산 AR 과 같은 기준의 하락률. 개발시점 AR 은 규칙 MDL_AR_BASELINE(시뮬레이션 가정)"),
    ]
    # 월별 부도율 추이 (10개 구분 × 최신·기준·증감)
    for key, label, _ in DR_SEGMENTS:
        w_last = {"segment_key": key, "ym": "$latest"}
        w_first = {"segment_key": key, "ym": "$earliest"}
        M += [
            metric(f"dr_{key}_latest", f"{label} 부도율(최근월)", "DEFAULT_RATE", {"default_count": q("DEFAULT_RATE_MONTHLY", w_last, "default_count", label="부도건수", unit="건"), "obs_count": q("DEFAULT_RATE_MONTHLY", w_last, "obs_count", label="관측건수", unit="건")}, wf=MM, unit="PCT", decimals=3, sort=40),
            metric(f"dr_{key}_first", f"{label} 부도율(기준월)", "DEFAULT_RATE", {"default_count": q("DEFAULT_RATE_MONTHLY", w_first, "default_count", label="부도건수", unit="건"), "obs_count": q("DEFAULT_RATE_MONTHLY", w_first, "obs_count", label="관측건수", unit="건")}, wf=MM, unit="PCT", decimals=3, sort=41, figures=[]),
            metric(f"dr_{key}_delta", f"{label} 부도율 증감(기준월 대비)", "DIFF", {"a": mref(f"dr_{key}_latest", "당월 부도율", "%"), "b": mref(f"dr_{key}_first", "기준월 부도율", "%")}, wf=MM, unit="PP", decimals=3, sort=42),
        ]

    # 포용금융 충당금
    IR = "wf_inclusive_risk"
    P = "PROVISION_BY_PRODUCT"
    inc = {"product_code": {"in_dataset": {"dataset": "INCLUSIVE_PRODUCTS", "col": "product_code"}}, "is_total": False}
    base_ym = {"ref": {"rule": "INC_PROVISION_SHARE_TREND", "path": "base_ym"}}
    M += [
        metric("prov_inclusive_now", "포용금융 상품 충당금(최근월)", "SUM", {"values": q(P, {**inc, "ym": "$latest"}, "provision", "list", "포용금융 상품코드별 충당금", "백만원")}, wf=IR, unit="KRW_MN", decimals=0, sort=1),
        metric("prov_total_now", "전체 충당금(최근월)", "VALUE", {"value": q(P, {"is_total": True, "ym": "$latest"}, "provision", label="합계 row", unit="백만원")}, wf=IR, unit="KRW_MN", decimals=0, sort=2),
        metric("prov_inclusive_base", "포용금융 상품 충당금(기준월)", "SUM", {"values": q(P, {**inc, "ym": base_ym}, "provision", "list", "포용금융 상품코드별 충당금", "백만원")}, wf=IR, unit="KRW_MN", decimals=0, sort=3),
        metric("prov_total_base", "전체 충당금(기준월)", "VALUE", {"value": q(P, {"is_total": True, "ym": base_ym}, "provision", label="합계 row", unit="백만원")}, wf=IR, unit="KRW_MN", decimals=0, sort=4),
        metric("share_now", "포용금융 충당금 비중(최근월)", "SHARE", {"numerator": mref("prov_inclusive_now", "포용금융 상품 충당금 합계", "백만원"), "denominator": mref("prov_total_now", "전체 충당금(합계 row)", "백만원")}, wf=IR, unit="PCT", decimals=2, sort=5),
        metric("share_base", "포용금융 충당금 비중(기준월)", "SHARE", {"numerator": mref("prov_inclusive_base", "포용금융 상품 충당금 합계", "백만원"), "denominator": mref("prov_total_base", "전체 충당금(합계 row)", "백만원")}, wf=IR, unit="PCT", decimals=2, sort=6),
        metric("share_delta_pp", "비중 증감", "SHARE_DELTA_PP", {"share1": mref("share_now", "비교시점 비중", "%"), "share0": mref("share_base", "기준시점 비중", "%")}, wf=IR, unit="PP", decimals=2, sort=7),
        metric("share_delta_pct", "비중 증가율", "GROWTH_RATE", {"v0": mref("share_base", "기준시점 비중", "%"), "v1": mref("share_now", "비교시점 비중", "%")}, wf=IR, unit="PCT", decimals=1, sort=8),
    ]

    # 종합기획부 — 여신 · 수익 · 자본
    HQ = "wf_hq_goal_review"
    PL, LB, CC = "PL_PRODUCT_SEGMENT", "LOAN_BALANCE_MONTHLY", "CAPITAL_CONSTRAINT"

    def pl(item, ym, label):
        return q(PL, {"item_code": item, "ym": ym}, "amount", label=label, unit="백만원")

    def lb(acct, ym, label):
        return q(LB, {"account_code": acct, "ym": ym}, "balance", label=label, unit="백만원")

    def cc(item, label, unit=""):
        return q(CC, {"item_code": item, "ym": "$latest"}, "value", label=label, unit=unit)

    L, Y1, Y2 = "$latest", "$latest-12", "$latest-24"
    M += [
        metric("total_rev_2026", "전체 수익(당기 누계)", "VALUE", {"value": pl("TOTAL_REVENUE", L, "전체 수익")}, wf=HQ, unit="KRW_BN", decimals=0, scale=100, sort=1),
        metric("total_rev_2025", "전체 수익(전년 동기 누계)", "VALUE", {"value": pl("TOTAL_REVENUE", Y1, "전체 수익")}, wf=HQ, unit="KRW_BN", decimals=0, scale=100, sort=2),
        metric("total_rev_growth", "전체 수익 증가율", "GROWTH_RATE", {"v0": pl("TOTAL_REVENUE", Y1, "전체 수익 (전년 동기)"), "v1": pl("TOTAL_REVENUE", L, "전체 수익 (당기)")}, wf=HQ, unit="PCT", decimals=2, sort=3),
        metric("nim_2026", "여신(일반)부문 이자마진 수익(당기 누계)", "VALUE", {"value": pl("LOAN_NIM", L, "여신 이자마진")}, wf=HQ, unit="KRW_BN", decimals=0, scale=100, sort=4),
        metric("nim_2025", "여신(일반)부문 이자마진 수익(전년 동기)", "VALUE", {"value": pl("LOAN_NIM", Y1, "여신 이자마진")}, wf=HQ, unit="KRW_BN", decimals=0, scale=100, sort=5),
        metric("nim_growth", "여신 이자마진 수익 증가율", "GROWTH_RATE", {"v0": pl("LOAN_NIM", Y1, "여신(일반)부문 이자마진 수익 (전년 동기)"), "v1": pl("LOAN_NIM", L, "여신(일반)부문 이자마진 수익 (당기)")}, wf=HQ, unit="PCT", decimals=2, sort=6),
        metric("nim_share_2026", "전체 수익 중 여신 이자마진 비중", "SHARE", {"numerator": pl("LOAN_NIM", L, "여신(일반)부문 이자마진 수익"), "denominator": pl("TOTAL_REVENUE", L, "전체 수익")}, wf=HQ, unit="PCT", decimals=2, sort=7),
        metric("nim_share_2025", "전년 동기 비중", "SHARE", {"numerator": pl("LOAN_NIM", Y1, "여신(일반)부문 이자마진 수익"), "denominator": pl("TOTAL_REVENUE", Y1, "전체 수익")}, wf=HQ, unit="PCT", decimals=2, sort=8),
        metric("nim_share_delta", "비중 증감", "SHARE_DELTA_PP", {"share1": mref("nim_share_2026", "당기 비중", "%"), "share0": mref("nim_share_2025", "전기 비중", "%")}, wf=HQ, unit="PP", decimals=2, sort=9),
        metric("corp_bal", "기업자금대출금 잔액", "VALUE", {"value": lb("CORP", L, "기업자금대출금")}, wf=HQ, unit="KRW_TN", decimals=2, scale=1_000_000, figures=["corp_bal", "prof_corp_bal"], sort=10),
        metric("hh_bal", "가계자금대출금 잔액", "VALUE", {"value": lb("HH", L, "가계자금대출금")}, wf=HQ, unit="KRW_TN", decimals=2, scale=1_000_000, figures=["hh_bal", "prof_hh_bal"], sort=11),
        metric("loan_total", "여신 잔액(기업+가계)", "SUM", {"values": q(LB, {"account_code": {"in": ["CORP", "HH"]}, "ym": L}, "balance", "list", "기업·가계 잔액", "백만원")}, wf=HQ, unit="KRW_TN", decimals=2, scale=1_000_000, figures=["dom_loan_head"], sort=12),
        metric("corp_growth", "기업여신 증가율(전년 동기 대비)", "GROWTH_RATE", {"v0": lb("CORP", Y1, "기업자금대출금 (전년 동기)"), "v1": lb("CORP", L, "기업자금대출금 (당기)")}, wf=HQ, unit="PCT", decimals=2, sort=13),
        metric("hh_growth", "가계여신 증가율(전년 동기 대비)", "GROWTH_RATE", {"v0": lb("HH", Y1, "가계자금대출금 (전년 동기)"), "v1": lb("HH", L, "가계자금대출금 (당기)")}, wf=HQ, unit="PCT", decimals=2, sort=14),
        metric("corp_share", "기업여신 구성비", "SHARE", {"numerator": lb("CORP", L, "기업자금대출금"), "denominator": q(LB, {"account_code": {"in": ["CORP", "HH"]}, "ym": L}, "balance", "sum", "기업+가계 잔액", "백만원")}, wf=HQ, unit="PCT", decimals=2, figures=["corp_share", "corp_share_2026"], sort=15),
        metric("hh_share", "가계여신 구성비", "SHARE", {"numerator": lb("HH", L, "가계자금대출금"), "denominator": q(LB, {"account_code": {"in": ["CORP", "HH"]}, "ym": L}, "balance", "sum", "기업+가계 잔액", "백만원")}, wf=HQ, unit="PCT", decimals=2, sort=16),
        metric("corp_share_2024", "기업여신 구성비(2년 전)", "SHARE", {"numerator": lb("CORP", Y2, "기업자금대출금"), "denominator": q(LB, {"account_code": {"in": ["CORP", "HH"]}, "ym": Y2}, "balance", "sum", "기업+가계 잔액", "백만원")}, wf=HQ, unit="PCT", decimals=2, sort=17),
        metric("corp_share_delta", "기업여신 구성비 증감(2년)", "SHARE_DELTA_PP", {"share1": mref("corp_share", "당기 구성비", "%"), "share0": mref("corp_share_2024", "2년 전 구성비", "%")}, wf=HQ, unit="PP", decimals=2, sort=18),
        metric("corp_goal", "현재 경영목표", "VALUE", {"value": {"rule": "GOAL_TARGETS", "path": "corp_loan_growth", "label": "확정 목표", "unit": "%"}}, wf=HQ, unit="PCT", decimals=1, sort=19),
        metric("hh_goal", "현재 관리목표", "VALUE", {"value": {"rule": "GOAL_TARGETS", "path": "hh_loan_growth", "label": "확정 목표", "unit": "%"}}, wf=HQ, unit="PCT", decimals=1, sort=20),
        metric("corp_gap", "목표 대비 이탈", "DIFF", {"a": mref("corp_growth", "기업여신 증가율", "%"), "b": mref("corp_goal", "경영목표", "%")}, wf=HQ, unit="PP", decimals=2, sort=21),
        metric("hh_gap", "관리목표 대비 초과", "DIFF", {"a": mref("hh_growth", "가계여신 증가율", "%"), "b": mref("hh_goal", "관리목표", "%")}, wf=HQ, unit="PP", decimals=2, sort=22),
        # Phase 2.6.4 — 3개년(2년 구간) 추세: 목표 추천의 추세 밴드 기준
        metric("corp_cagr", "기업여신 잔액 연평균 성장률(3개년)", "CAGR", {"v_start": lb("CORP", Y2, "기업자금대출금(2년 전)"), "v_end": lb("CORP", L, "기업자금대출금(당기)"), "years": {"const": 2, "label": "기간(년)"}}, wf=HQ, unit="PCT", decimals=2, figures=[], sort=23),
        metric("hh_cagr", "가계여신 잔액 연평균 성장률(3개년)", "CAGR", {"v_start": lb("HH", Y2, "가계자금대출금(2년 전)"), "v_end": lb("HH", L, "가계자금대출금(당기)"), "years": {"const": 2, "label": "기간(년)"}}, wf=HQ, unit="PCT", decimals=2, figures=[], sort=24),
        metric("corp_int_rev", "기업자금대출금이자(당기 누계)", "VALUE", {"value": pl("CORP_INTEREST", L, "기업자금대출금이자")}, wf=HQ, unit="KRW_BN", decimals=0, scale=100, figures=["corp_int_rev", "prof_corp_rev"], sort=23),
        metric("hh_int_rev", "가계자금대출금이자(당기 누계)", "VALUE", {"value": pl("HH_INTEREST", L, "가계자금대출금이자")}, wf=HQ, unit="KRW_BN", decimals=0, scale=100, figures=["hh_int_rev", "prof_hh_rev"], sort=24),
        metric("ros_corp", "기업여신 규모 대비 수익률", "SHARE", {"numerator": pl("CORP_INTEREST", L, "기업자금대출금이자"), "denominator": lb("CORP", L, "기업자금대출금 잔액")}, wf=HQ, unit="PCT", decimals=3, sort=25),
        metric("ros_hh", "가계여신 규모 대비 수익률", "SHARE", {"numerator": pl("HH_INTEREST", L, "가계자금대출금이자"), "denominator": lb("HH", L, "가계자금대출금 잔액")}, wf=HQ, unit="PCT", decimals=3, sort=26),
        metric("ros_gap", "수익률 격차(기업−가계)", "DIFF", {"a": mref("ros_corp", "기업 수익률", "%"), "b": mref("ros_hh", "가계 수익률", "%")}, wf=HQ, unit="PP", decimals=3, sort=27),
        metric("prof_etc_hh_bal", "기타가계 잔액", "VALUE", {"value": lb("HH_ETC", L, "기타가계자금대출금")}, wf=HQ, unit="KRW_TN", decimals=2, scale=1_000_000, sort=28),
        metric("prof_etc_hh_rev", "기타가계 이자수익", "VALUE", {"value": pl("HH_ETC_INTEREST", L, "기타가계자금대출이자")}, wf=HQ, unit="KRW_BN", decimals=0, scale=100, sort=29),
        metric("ros_etc_hh", "기타가계 규모 대비 수익률", "SHARE", {"numerator": pl("HH_ETC_INTEREST", L, "이자"), "denominator": lb("HH_ETC", L, "잔액")}, wf=HQ, unit="PCT", decimals=3, sort=30),
        metric("prof_house_bal", "주택자금 잔액", "VALUE", {"value": lb("HOUSE", L, "주택자금대출금")}, wf=HQ, unit="KRW_TN", decimals=2, scale=1_000_000, sort=31),
        metric("prof_house_rev", "주택자금 이자수익", "VALUE", {"value": pl("HOUSE_INTEREST", L, "주택자금대출이자")}, wf=HQ, unit="KRW_BN", decimals=0, scale=100, sort=32),
        metric("ros_house", "주택자금 규모 대비 수익률", "SHARE", {"numerator": pl("HOUSE_INTEREST", L, "이자"), "denominator": lb("HOUSE", L, "잔액")}, wf=HQ, unit="PCT", decimals=3, sort=33),
        metric("prof_public_bal", "공공자금 잔액", "VALUE", {"value": lb("PUBLIC", L, "공공자금대출금")}, wf=HQ, unit="KRW_TN", decimals=2, scale=1_000_000, sort=34),
        metric("prof_public_rev", "공공자금 이자수익", "VALUE", {"value": pl("PUBLIC_INTEREST", L, "공공자금대출이자")}, wf=HQ, unit="KRW_BN", decimals=0, scale=100, sort=35),
        metric("ros_public", "공공자금 규모 대비 수익률", "SHARE", {"numerator": pl("PUBLIC_INTEREST", L, "이자"), "denominator": lb("PUBLIC", L, "잔액")}, wf=HQ, unit="PCT", decimals=3, sort=36),
        metric("cap_asset_growth", "총자산 최대 증가율", "VALUE", {"value": cc("ASSET_GROWTH_MAX", "지주 한도", "%")}, wf=HQ, unit="PCT", decimals=1, figures=["cap_asset_growth", "bank_asset_ceiling"], sort=40),
        metric("bank_asset_target", "은행 목표 총자산 증가율", "VALUE", {"value": cc("BANK_ASSET_TARGET", "은행 목표", "%")}, wf=HQ, unit="PCT", decimals=1, sort=41),
        metric("bank_asset_headroom", "한도 여유", "DIFF", {"a": mref("cap_asset_growth", "지주 한도", "%"), "b": mref("bank_asset_target", "은행 목표", "%")}, wf=HQ, unit="PP", decimals=1, sort=42),
        metric("cap_rwa_net", "RWA 순증 한도", "VALUE", {"value": cc("RWA_NET_LIMIT", "RWA 순증 한도", "조원")}, wf=HQ, unit="KRW_TN", decimals=1, sort=43),
        metric("cap_rwa_dept", "배분 합계", "VALUE", {"value": cc("RWA_DEPT_TOTAL", "부서별 배분 합계", "조원")}, wf=HQ, unit="KRW_TN", decimals=1, sort=44),
    ]
    for seg in ("corp", "hh", "etc"):
        S = seg.upper()
        M += [
            metric(f"rwa_{seg}_alloc", "배분", "VALUE", {"value": cc(f"RWA_{S}_ALLOC", "배분", "조원")}, wf=HQ, unit="KRW_TN", decimals=2 if seg != "corp" else 1, sort=45),
            metric(f"rwa_{seg}_used", "사용", "VALUE", {"value": cc(f"RWA_{S}_USED", "사용", "조원")}, wf=HQ, unit="KRW_TN", decimals=2, sort=46),
            metric(f"rwa_{seg}_usage", "소진율", "USAGE_RATE", {"used": cc(f"RWA_{S}_USED", "사용", "조원"), "limit": cc(f"RWA_{S}_ALLOC", "배분", "조원")}, wf=HQ, unit="PCT", decimals=1, sort=47),
        ]
    M += [
        metric("bis_total", "BIS 총자본비율", "VALUE", {"value": cc("BIS_TOTAL", "BIS 총자본비율", "%")}, wf=HQ, unit="PCT", decimals=1, sort=50),
        metric("peer_share", "타행 평균 비중(참고, 외부)", "VALUE", {"value": q("PEER_BANK_STATS", {"stat_code": "MID_LOW_CREDIT_SHARE", "ym": "$latest"}, "value", label="타행 평균(외부 공시)", unit="%")}, wf=HQ, unit="PCT", decimals=1, sort=51),
    ]
    from .defs_real import extend, metrics as real_metrics  # Phase I — 원천 없던 화면 수치(모형 카드 · 포용금융 · 비교표 · 제약)

    return extend(M + real_metrics())


# ═════════════════════════ 표·차트 바인딩 ═════════════════════════
GRADE_P = {"dataset": "MODEL_MONITORING_GRADE", "where": {"model_code": "CORP_MICRO", "as_of": "$latest"}, "master": "PD_MASTER_SCALE", "master_where": {"model_code": "CORP_MICRO"}, "verdict_labels": {"above_mid_within_max": "대표값 초과 · 최대값 이내", "above_max": "최대값 초과", "monotonic_break": "서열화 균열", "within_mid": "예측 범위 내"}}
PSI_P = {"dataset": "MODEL_MONITORING_GRADE", "base_where": {"model_code": "CORP_MICRO", "as_of": "$earliest"}, "current_where": {"model_code": "CORP_MICRO", "as_of": "$latest"},
         "names": ["[[ym:MODEL_MONITORING_GRADE:$earliest|dot]](기준)", "[[ym:MODEL_MONITORING_GRADE:$latest|dot]](비교)"]}
INC_P = {"dataset": "PROVISION_BY_PRODUCT", "master": "INCLUSIVE_PRODUCTS", "base_ym": {"ref": {"rule": "INC_PROVISION_SHARE_TREND", "path": "base_ym"}}, "now_ym": "$latest", "group_order": ["새희망홀씨대출", "햇살론", "사잇돌"]}


def bindings() -> list[dict[str, Any]]:
    MM, IR = "wf_model_monitoring", "wf_inclusive_risk"
    B = [
        dict(workflow_code=MM, artifact_key="report.model-monitoring", path="table:소기업 모형 등급별 모니터링 결과 (2026.08.31)", builder="grade_table", params=GRADE_P),
        dict(workflow_code=MM, artifact_key="report.model-monitoring", path="table_note:소기업 모형 등급별 모니터링 결과 (2026.08.31)", builder="template", params={"template": "합계 {total_obs}건 / 부도 {total_defaults}건 / 전체 실제부도율 {total_dr}%"}),
        dict(workflow_code=MM, artifact_key="report.model-monitoring", path="chart:등급별 실제부도율 vs 예측부도율 대표값·최대값", builder="grade_series", params=GRADE_P),
        dict(workflow_code=MM, artifact_key="report.model-monitoring", path="table:등급별 분포 비교 및 PSI 기여도", builder="psi_table", params=PSI_P),
        dict(workflow_code=MM, artifact_key="report.model-monitoring", path="table_note:등급별 분포 비교 및 PSI 기여도", builder="template", params={"template": "PSI {psi_micro} (표시 3자리, 기여도 합계 기준). 비중 0 구간은 ε 보정 규칙 적용 대상."}),
        dict(workflow_code=MM, artifact_key="report.model-monitoring", path="chart:등급별 구성비 — 기준시점 vs 비교시점", builder="psi_series", params=PSI_P),
        dict(workflow_code=IR, artifact_key="inclusive", path="products", builder="inclusive_products", params=INC_P),
        dict(workflow_code=IR, artifact_key="inclusive", path="groupSummary", builder="inclusive_groups", params=INC_P),
        dict(workflow_code=IR, artifact_key="report.inclusive-risk", path="table:상품별 충당금 증감 및 기여도 (상위 10건)", builder="inclusive_product_table", params={**INC_P, "limit": 10}),
    ]
    for key, _, _ in DR_SEGMENTS:
        B.append(dict(workflow_code=MM, artifact_key="default_rate_trend", path=f"series:{key}", builder="series_points", params={"dataset": "DEFAULT_RATE_MONTHLY", "where": {"segment_key": key}, "order_by": "ym", "formula": "DEFAULT_RATE", "args": {"default_count": "default_count", "obs_count": "obs_count"}, "decimals": 3}))
    from .defs_real import bindings as real_bindings

    return B + real_bindings()


# ═════════════════════════ 워크플로우 ═════════════════════════
def _std_nodes(narrator: str, targets: list[dict[str, Any]], evidence_cfg: dict[str, Any], judge: list[dict[str, Any]] | None = None, after_views: list[tuple] | None = None):
    nodes = [
        ("load_inputs", "입력 데이터 고정", "load_inputs", None, {}),
        ("compute", "지표 계산(커널)", "compute_metrics", None, {}),
    ]
    if judge:
        nodes.append(("judge", "규칙 판정", "judge", None, {"items": judge}))
    nodes += [
        # 판단 에이전트 (B.30) — 변화 감지 → (화면 갱신) → 실행 계획 → 근거 · 서술은 계획을 따른다
        ("detect", "변화 감지(에이전트)", "detect_changes", "change_detector", {"rule": "CHANGE_SIGNIFICANCE", "optional": True}),
        ("views", "화면 수치·표 갱신", "build_views", None, {}),
        *(after_views or []),
        ("plan", "실행 계획(플래너)", "plan_run", "planner", {"rule": "PLANNER_POLICY", "optional": True}),
        ("evidence", "근거 검색(그래프→하이브리드)", "retrieve_evidence", None, {**evidence_cfg, "optional": True}),
        ("narrate", "의견 서술(LLM)", "narrate", narrator, {"targets": targets, "optional": True}),
        ("critic", "서술 검증", "critic", "critic", {"rule": "CRITIC_RULES"}),
        ("publish", "산출물 게시", "publish", None, {}),
    ]
    return nodes


REC_ITEMS = [
    {"proposal": "prop-corp-growth", "metric": "corp_growth_rec", "current": "corp_goal", "trend": "corp_cagr", "unit": "PCT", "decimals": 1, "sign": True,
     "text": "기존 {current} 대비 상향 검토. 추천범위 {low} ~ {high}"},
    {"proposal": "prop-hh-control", "metric": "hh_growth_rec", "current": "hh_goal", "trend": "hh_cagr", "unit": "PCT", "decimals": 1, "sign": True,
     "text": "기존 {current} 이하 대비 하향 검토. 추천범위 {low} ~ {high} 이하"},
    {"proposal": "prop-inclusive-new", "metric": "inclusive_supply_rec", "unit": "KRW_TN", "decimals": 1,
     "text": "중·저신용자 여신 공급액 2026년 {low} ~ {high} 이상 (병행 지표: 개인여신 중 중·저신용자 비중 18.0% 이상)"},
]


def _hq_nodes(*a, **kw):
    """종합기획부: 표준 노드 + 목표 추천 · Attention 순위(화면 갱신 직후) + 컬럼 정의서 적재(Critic 이후, 게시 전)."""
    nodes = _std_nodes(*a, **kw)
    at = next(i for i, n in enumerate(nodes) if n[0] == "views") + 1
    nodes[at:at] = [
        ("recommend", "경영목표 추천 범위(커널)", "recommend_goals", None, {"items": REC_ITEMS}),
        ("rank", "AI Attention 우선순위(규칙)", "rank_attentions", None, {"rule": "ATTENTION_SCORE"}),
        # Phase M · LLM-P08 — 순위는 규칙 그대로, 항목마다 숫자 없는 해설(rankReason). LLM 없음 · 실패면 점수 구성으로 만든 규칙 문장
        ("curate", "AI 주목 사항 해설(에이전트)", "curate_attentions", "attention_curator", {"optional": True}),
    ]
    nodes.insert(len(nodes) - 1, ("contracts", "컬럼 정의서 테이블 적재·대조", "materialize_contracts", None, {"tables": ["T01", "T02", "T03"], "optional": True}))
    return nodes


WORKFLOWS = [
    dict(
        code="wf_model_monitoring", name="신용평가모형 모니터링", sort=1,
        description="모형 등급별 집계 · PD Master · 월별 부도율이 바뀌면 부도율·PSI·χ²·6B 판정을 다시 계산하고 보고서·의견을 갱신",
        outputs=["report.model-monitoring", "risk_dashboard", "default_rate_trend", "insights", "analysis_tabs", "action_plans"],
        nodes=_std_nodes(
            "narrator_model",
            [{"insight_id": "ins-model-6b", "instruction": "6B 등급의 대표값 초과·최대값 이내 여부와 카이제곱 검정 결과를 포함한다."}],
            {"query": "소기업 모형 등급계량화 예측부도율 최대값 이내 관리 판정 기준", "concepts": ["CORP_MICRO", "소기업"], "doc_classes": ["model_method"], "k": 4},
            judge=[{"metric": "psi_micro", "rule": "MDL_PSI_BANDS"}],
            after_views=[
                ("labels", "구분 표시명(설정 · 데이터)", "apply_segment_labels", None, {"artifact": "default_rate_trend"}),
                ("tabs", "분석 탭 동기화", "sync_analysis_tabs", None, {"reports": ["model_monitoring"]}),
                ("guides", "수행방안 가이드 선택(규칙)", "select_guides", None, {"rule": "GUIDE_CATALOG", "plans": ["plan-micro-recalibration"]}),
            ],
        ),
        triggers=[("cron", "0 6 * * *"), ("dataset", "MODEL_MONITORING_GRADE"), ("dataset", "PD_MASTER_SCALE"), ("dataset", "DEFAULT_RATE_MONTHLY"), ("doc_class", "model_method"), ("rule", "MDL_PSI_BANDS"), ("rule", "MDL_CHI_TEST"), ("rule", "MDL_AR_DECLINE_BANDS"), ("rule", "MDL_AR_BASELINE"), ("rule", "MDL_MODEL_VERDICT"), ("setting", "risk.segment_labels"), ("setting", "risk.retail_pool_note"), ("rule", "GUIDE_CATALOG")],
    ),
    dict(
        code="wf_inclusive_risk", name="포용금융 신용리스크", sort=2,
        description="상품별 충당금(7790) · 포용금융 대상 상품 마스터 · 정부정책/경영의사결정 문서가 바뀌면 충당금 비중과 기여도를 다시 계산",
        outputs=["inclusive", "report.inclusive-risk", "risk_dashboard", "attentions", "insights", "analysis_tabs", "action_plans"],
        nodes=_std_nodes(
            "narrator_inclusive",
            [{"insight_id": "ins-inclusive-provision", "instruction": "충당금 비중 변화, 익스포저 건수 증가, 평균 신용등급 비교를 포함하고 모니터링 필요성을 제시한다."}],
            {"query": "포용금융 확대 서민 취약계층 금융공급 대상 상품 실적 인정", "concepts": ["포용금융", "햇살론", "새희망홀씨대출", "사잇돌"], "doc_classes": ["gov_policy", "mgmt_decision"], "k": 4},
            judge=[{"metric": "share_delta_pp", "rule": "INC_PROVISION_SHARE_TREND", "insight": "ins-inclusive-provision"}],
            after_views=[
                ("tabs", "분석 탭 동기화", "sync_analysis_tabs", None, {"reports": ["inclusive_risk"]}),
                ("guides", "수행방안 가이드 선택(규칙)", "select_guides", None, {"rule": "GUIDE_CATALOG", "plans": ["plan-inclusive-risk"]}),
            ],
        ),
        triggers=[("cron", "10 6 * * *"), ("dataset", "PROVISION_BY_PRODUCT"), ("master", "INCLUSIVE_PRODUCTS"), ("dataset", "RETAIL_POOL_SUMMARY"), ("master", "RETAIL_POOL_MASTER"), ("doc_class", "gov_policy"), ("doc_class", "mgmt_decision"), ("rule", "INC_PROVISION_SHARE_TREND"), ("rule", "GUIDE_CATALOG")],
    ),
    dict(
        code="wf_hq_goal_review", name="종합기획부 경영목표 검토", sort=3,
        description="손익(2633) · 여신(2020) · 자본 제약 · 정책/의사결정 문서 · 목표 확정이 바뀌면 여신 현황·이탈·수익성·제약 수치를 다시 계산",
        outputs=["hq_dashboard", "loan_overview", "comparison_view", "capital_view", "profitability", "goals", "proposals", "attentions"],
        nodes=_hq_nodes(
            "narrator_hq",
            [{"insight_id": "ins-divergence", "instruction": "기업여신과 가계여신의 목표 대비 이탈 방향 차이를 서술한다."}],
            {"query": "기업여신 확대 가계부채 관리 경영목표 RWA 한도", "concepts": ["기업여신 확대", "가계부채 관리", "RWA 순증 한도"], "doc_classes": ["gov_policy", "mgmt_decision"], "k": 4},
        ),
        triggers=[("cron", "20 6 * * *"), ("event", "contract.changed"), ("dataset", "HQ_PLAN_KPI"), ("dataset", "PL_PRODUCT_SEGMENT"), ("dataset", "LOAN_BALANCE_MONTHLY"), ("dataset", "CAPITAL_CONSTRAINT"), ("dataset", "PEER_BANK_STATS"), ("dataset", "RETAIL_POOL_SUMMARY"), ("master", "RETAIL_POOL_MASTER"), ("rule", "CAPITAL_FLOORS"), ("rule", "PROPOSAL_IMPACT"), ("doc_class", "gov_policy"), ("doc_class", "mgmt_decision"), ("event", "goal.confirmed"), ("rule", "GOAL_TARGETS"), ("rule", "GOAL_REC_POLICY"), ("rule", "ATTENTION_SCORE")],
    ),
    dict(
        code="wf_graph_projection", name="그래프 투영 · 문서 구조화", sort=9,
        description="모든 데이터셋·문서·설정 변경 및 분석 결과 색인 갱신(kb.indexed) 시 임베딩 → 문서 구조화 → Neo4j 투영 (가벼운 작업)",
        outputs=[],
        nodes=[
            ("embed", "청크 임베딩", "embed_chunks", "embedder", {"optional": True}),
            ("extract", "문서 구조화", "extract_documents", "ontology_extractor", {"optional": True}),
            ("project", "그래프 투영", "project_graph", None, {}),
        ],
        triggers=[("any", "dataset"), ("any", "document"), ("any", "ontology"), ("any", "config"), ("event", "kb.indexed")],
        debounce=5,
    ),
]

# 화면 목데이터 문구 중 고정 숫자를 수치 마커로 바꾸는 교정 (계산값 갱신 시 문구가 따라가도록)
TEXT_FIXES = [
    # kv 값은 프론트에서 수치 마커를 렌더링한다 (ReportView kv → renderRich)
    ("report.model-monitoring", "χ² = 18.42 < 임계값 21.03", "χ² = [[fig:chi_stat]] < 임계값 [[fig:chi_critical]]"),
]

# 이미 운영 중인 DB 의 현재 산출물에도 적용하는 문구 교정 (멱등 — 옛 문구가 있을 때만 새 세대 게시)
# Q9 확정: 반올림은 사사오입(HALF_UP) → 9.1575% 는 9.16%
LIVE_TEXT_FIXES = [
    ("= 9.15% (1월 7.97%)", "= 9.16% (1월 7.97%)"),
    ("8월 9.15%로 상승", "8월 9.16%로 상승"),
    ("χ² = 18.42 < 임계값 21.03", "χ² = [[fig:chi_stat]] < 임계값 [[fig:chi_critical]]"),
    # Q22: 판정 근거 문구의 PSI · AR 하락률도 계산 수치 마커로 (ModelMonitoringPanel → renderRich)
    ("PSI 0.082(관찰 상단) · AR 하락률 23.8%(하락 주의)", "PSI [[fig:psi_micro]](관찰 상단) · AR 하락률 [[fig:ard_micro]](하락 주의)"),
    # B.29: 영업점 기준일 표기 (8월 말 = 하반기 2개월 경과)
    ("2026.08.31 (하반기 3개월차)", "2026.08.31 (하반기 2개월 경과)"),
]


# 원본 보고서 어댑터 설정 (1.3.3 ~ 1.3.5) — 이름 → 코드 매핑은 관리자 화면(데이터셋 parser)에서 편집
# 키: '항목명' 또는 '상위>항목명'(경로 끝부분 일치, 공백 · 괄호 무시). 매핑에 없는 과목은 PATH: 경로 코드로 보존
PARSERS = {
    "PL_PRODUCT_SEGMENT": {
        "adapter": "auto",
        "item_codes": {
            "총수익": "TOTAL_REVENUE", "전체 수익": "TOTAL_REVENUE",
            "여신(일반)부문 이자마진 수익": "LOAN_NIM",
            "원화대출금이자수익>기업자금대출금이자": "CORP_INTEREST", "원화대출금이자수익>가계자금대출금이자": "HH_INTEREST",
            "기타가계자금대출이자": "HH_ETC_INTEREST", "주택자금대출이자": "HOUSE_INTEREST", "공공자금대출이자": "PUBLIC_INTEREST",
        },
        "required_items": ["TOTAL_REVENUE", "LOAN_NIM", "CORP_INTEREST", "HH_INTEREST"],
    },
    "LOAN_BALANCE_MONTHLY": {
        "adapter": "auto",
        "unit_multiplier": 1_000_000,
        "account_codes": {
            "대출금": "LOAN_TOTAL", "종합계": "GRAND_TOTAL",
            "대출금>기업자금대출금": "CORP", "대출금>가계자금대출금": "HH",
            "주택자금대출": "HOUSE", "기타가계자금대출": "HH_ETC", "대출금>공공및기타자금대출금": "PUBLIC",
        },
        "keep_unmapped": True,
    },
    "PROVISION_BY_PRODUCT": {"adapter": "auto", "total_header": "손실충당금 및 충당부채 총계", "total_col": "X"},
}
from .defs_real import DATASETS as _REAL_DATASETS  # noqa: E402 — Phase I 신설 데이터셋(소매 Pool 월별 집계)

DATASETS += [d for d in _REAL_DATASETS if d["code"] not in {x["code"] for x in DATASETS}]
for _d in DATASETS:
    if _d["code"] in PARSERS:
        _d["parser"] = {**(_d.get("parser") or {}), **PARSERS[_d["code"]]}

# 운영 DB 데이터셋 품질 규칙 보강 — 업그레이드 이름별 1회만 적용(관리자가 이후 지운 규칙은 다시 넣지 않음)
QUALITY_UPGRADES = {
    "quality-v2-continuity-change": {
        "PROVISION_BY_PRODUCT": [{"rule": "max_change", "column": "provision", "pct": 50, "severity": "warning"}],
        "DEFAULT_RATE_MONTHLY": [{"rule": "period_continuity", "column": "ym", "group": "segment_key", "severity": "warning"}],
    },
}


# 서술 속 고정 숫자 → 계산 수치 마커 (골든셋 서술 검사에서 발견 · 1회 보강)
MARKER_FIXES = [
    {
        "keys": ["attentions", "hq_dashboard", "proposals"],
        "id": ["att-hh-limit", "prop-hh-control"],
        "fields": ["statement", "judgement"],
        "replace": [
            ("관리 한도 100.00조원의 99.2%를 소진했습니다", "관리 한도 [[fig:hh_bal_limit]]의 [[fig:hh_bal_usage]]를 소진했습니다"),
            ("가계 부문 신용RWA 소진율은 92.3%로", "가계 부문 신용RWA 소진율은 [[fig:rwa_hh_usage]]로"),
        ],
        "figures": {
            "hh_bal_limit": {"id": "hh_bal_limit", "label": "가계여신 잔액 관리 한도", "value": 100.0, "unit": "KRW_TN", "decimals": 2, "dataOrigin": "simulated"},
            "hh_bal_usage": {"id": "hh_bal_usage", "label": "가계여신 잔액 관리 한도 소진율", "value": 99.2, "unit": "PCT", "decimals": 1, "dataOrigin": "simulated"},
            "rwa_hh_usage": {"id": "rwa_hh_usage", "label": "가계 부문 신용RWA 소진율", "value": 92.3, "unit": "PCT", "decimals": 1, "dataOrigin": "simulated"},
        },
    }
]
