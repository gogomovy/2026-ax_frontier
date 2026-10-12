"""사업부서 · 영업점 컬럼 정의서 기본 연결 (B.38).

정의서(TalkFile_사업부서/영업점_컬럼정의서_컬럼기준_v1.xlsx)의 T 시트는 다행 표 — 행 생성기(contracts/rows.py)가 행 값을 만들고,
에이전트 서술 컬럼은 Critic 을 통과한 인사이트 · 보고서 · 실행계획에 연결한다. S01~S03 은 원천 데이터셋 컬럼 존재만 검사하고,
S99 는 문서 DB 에서 적재한다. 원천이 없는 컬럼(전년말 · 연체원장 · 매핑 미확정)은 '미연결'로 남긴다 — 임의 수치를 만들지 않는다.
모든 연결은 관리자 화면(컬럼 정의서 › 연결 편집)에서 바꿀 수 있고, 행 생성기 · 파라미터는 설정 contracts.row_builders 에서 바꾼다.
"""
from __future__ import annotations

from typing import Any

SPEC_FILES = ("risk_column_def_v1.json", "branch_column_def_v1.json")
DEPT_PREFIX = {"사업부서": "risk"}  # 설정 contracts.dept_prefix 에 병합(기존 값 유지)

# 설정 contracts.row_builders — 표 코드 → 행 생성기 · 파라미터. 단위 환산 계수는 데이터셋 정의 단위(라벨) 기준.
ROW_BUILDERS: dict[str, dict[str, Any]] = {
    "RISK_T01": {"builder": "risk_model_rows", "params": {"model_code": "CORP_MICRO", "model_name": "소기업 신용평가모형", "segment": "15", "grade": "6B", "exposure_won_per_unit": 100000000,
                                                          "status_labels": {"over_max": "상한초과", "over_rep": "주의(상한내관리)", "normal": "일상"}}},
    "RISK_T02": {"builder": "risk_grade_rows", "params": {"model_code": "CORP_MICRO"}},
    "RISK_T03": {"builder": "risk_product_rows", "params": {"provision_won_per_unit": 1000000}},
    "RISK_S99": {"builder": "doc_meta_rows", "params": {}},
    "BRANCH_T01": {"builder": "branch_status_rows", "params": {}},
    "BRANCH_T02": {"builder": "branch_corp_rows", "params": {"micro_size": "15"}},
    "BRANCH_T03": {"builder": "branch_retail_rows", "params": {}},
    "BRANCH_S99": {"builder": "doc_meta_rows", "params": {"only_branch_visible": True}},
}

# 워크플로우별 적재 노드 — 해당 워크플로우가 계산한 지표 · 서술로 표를 채운다
WORKFLOW_TABLES: dict[str, list[str]] = {
    "wf_model_monitoring": ["RISK_T01", "RISK_T02", "RISK_S99"],
    "wf_inclusive_risk": ["RISK_T03"],
    "wf_branch_kpi": ["BRANCH_T01", "BRANCH_T02", "BRANCH_T03", "BRANCH_S01", "BRANCH_S02", "BRANCH_S03", "BRANCH_S99"],
}


def _agent(insight: str, report: str, rec: dict[str, Any], caution: str, anchor: str) -> dict[str, dict[str, Any]]:
    return {
        "ANALYSIS_ID": {"analysis": "id"},
        "ANALYSIS_DT": {"analysis": "dt"},
        "REPORT_HTML": {"report": report},
        "AGENT_SUMMARY": {"insight": insight},
        "AGENT_RECOMMENDATION": rec,
        "RISK_CAUTION_TXT": {"report": report, "section": caution},
        "EVIDENCE_DOC_IDS": {"evidence": insight},
        "REPORT_ANCHOR_ID": {"const": anchor},
        "TAB_TITLE": {"report": report, "field": "title"},
    }


def _um(reason: str, q: str | None = None) -> dict[str, Any]:
    return {"unmapped": reason, **({"question": q} if q else {})}


NO_SRC = "원천 추가 필요(정의서 '추가 필요') — 원천 확보 전 임의 수치를 만들지 않음"
METHOD = "판정 임계값 · 관찰창은 통계방법론 원문 확인 전 임의 확정 금지(정의서)"
MAPPING = "검증된 재무등급→신용등급 매핑 · 심사 등급 확보 전 산출불가(정의서)"


def _rows(cols: list[str]) -> dict[str, dict[str, Any]]:
    return {c: {"row": c.lower()} for c in cols}


RISK_T01 = {
    **_rows(["BASE_YM", "MODEL_ID", "MODEL_NM", "MODEL_SEGMENT_CD", "EXPOSURE_CNT", "EXPOSURE_AMT", "PSI", "AR_RT", "EXCEED_GRADE_CNT", "MONITOR_STATUS_CD", "INCLUSIVE_PROV_SHARE_DIFF_PP"]),
    "ACTUAL_DEFAULT_RT": {"row": "actual_default_rt", "check": {"model_id": "CORP_MICRO"}},
    "PRED_PD_RT": {"row": "pred_pd_rt", "check": {"model_id": "CORP_MICRO"}},
    "PRED_PD_MAX_RT": {"row": "pred_pd_max_rt", "check": {"model_id": "CORP_MICRO"}},
    **_agent("ins-model-6b", "report.model-monitoring", {"plan": "plan-micro-recalibration", "field": "body"}, "s5-findings", "s4-calibration"),
}
RISK_T02 = {
    **_rows(["BASE_YM", "MODEL_ID", "GRADE_CD", "REF_BASE_YM", "REFERENCE_CNT", "CURRENT_CNT", "DEFAULT_CNT", "NONDEFAULT_CNT", "REFERENCE_SHARE_RT", "CURRENT_SHARE_RT",
             "PSI_COMPONENT", "MODEL_PSI", "PRED_PD_MIN_RT", "EXCEED_REP_PD_YN", "EXCEED_MAX_PD_YN"]),
    "ACTUAL_DEFAULT_RT": {"row": "actual_default_rt", "check": {"grade_cd": "6B"}},
    "PRED_PD_RT": {"row": "pred_pd_rt", "check": {"grade_cd": "6B"}},
    "PRED_PD_MAX_RT": {"row": "pred_pd_max_rt", "check": {"grade_cd": "6B"}},
    "PD_GAP_PP": {"row": "pd_gap_pp", "check": {"grade_cd": "6B"}},
    "AR_RT": {"metric": "ar_micro"},
    "OBS_START_DT": _um(METHOD), "OBS_END_DT": _um(METHOD), "PSI_THRESHOLD": _um(METHOD), "AR_THRESHOLD_RT": _um(METHOD),
    "METRIC_HELP_TXT": _um("지표 도움말은 용어 사전(관리자 › 용어)에서 관리 — 통계방법론 원문 연결 후 바인딩"),
    **_agent("ins-model-6b", "report.model-monitoring", {"plan": "plan-micro-recalibration", "field": "body"}, "s5-findings", "s3-grade"),
}
RISK_T03 = {
    **_rows(["BASE_YM", "PRODUCT_CD", "PRODUCT_NM", "INCLUSIVE_YN", "COMPARISON_BASE_YM", "PROVISION_AMT", "JAN_PROVISION_AMT", "INCLUSIVE_PROVISION_AMT", "JAN_INCLUSIVE_PROVISION_AMT",
             "TOTAL_PROVISION_AMT", "JAN_TOTAL_PROVISION_AMT", "INCLUSIVE_PROV_SHARE_RT", "JAN_INCLUSIVE_PROV_SHARE_RT", "PROV_SHARE_DIFF_PP", "PROV_GROWTH_RT",
             "TOTAL_RETAIL_EXPOSURE_AMT", "TOTAL_WEIGHTED_PD_RT"]),
    **{c: _um(NO_SRC) for c in ("YEAR_END_BASE_YM", "YE_PROVISION_AMT", "YE_EXPOSURE_AMT", "OVERDUE_AMT", "YE_PROV_GROWTH_RT", "YE_TOTAL_WEIGHTED_PD_RT", "WEIGHTED_PD_DIFF_PP",
                                "OVERDUE_RT", "YE_EXPOSURE_CNT", "NEW_OVERDUE_CNT", "YE_INCLUSIVE_PROVISION_AMT", "YE_TOTAL_RETAIL_EXPOSURE_AMT", "EXPOSURE_COUNT_YE_GROWTH_RT", "EXPOSURE_AMOUNT_YE_GROWTH_RT")},
    **{c: _um("상품코드↔소매 Pool 매핑 미제공 — 상품별 익스포저 · PD 는 매핑 확보 후") for c in ("EXPOSURE_AMT", "EXPOSURE_CNT", "PRODUCT_PD_RT")},
    **_agent("ins-inclusive-provision", "report.inclusive-risk", {"plan": "plan-inclusive-risk", "field": "body"}, "i5-opinion", "i3-product"),
}
S99 = {
    **_rows(["DOC_ID", "DOC_VERSION", "DOC_TITLE", "DOC_TYPE_CD", "ISSUE_DT", "VALID_FROM_DT", "PAGE_NO", "ACCESS_SCOPE", "BRANCH_VISIBLE_YN", "DATA_ASOF_YM"]),
    # 시드 문서는 원본 파일 · 적용종료일 · 하단 표기 페이지가 없을 수 있다 — 업로드 문서에서 채워짐(값 없음은 오류가 아님)
    **{c: {"row": c.lower(), "optional": True} for c in ("ORIGINAL_FILE_URI", "VALID_TO_DT", "PRINTED_PAGE_NO")},
    "SECTION_ID": _um("근거 문단 단위는 보고서 근거(EVIDENCE_DOC_IDS)에 저장 — 문서 단위 표에는 비움"),
    "IS_INFERENCE_YN": _um("정책 연계 추론 여부는 온톨로지 관계(추론 표시) 기준 — 문서 단위 표에는 비움"),
    "EVIDENCE_QUOTE": _um("근거 발췌는 보고서 근거(EVIDENCE_DOC_IDS)에 저장 — 문서 단위 표에는 비움"),
}
BRANCH_T01 = {
    **_rows(["BASE_YM", "BRC", "ROW_KIND_CD", "ITEM_CD", "BRC_NM", "EVAL_HALF", "KPI_PARENT_CD", "KPI_ITEM_NM", "MAX_SCORE", "EARNED_SCORE", "RULE_CHANGED_YN", "RULE_CHANGE_SUMMARY",
             "BIZ_DIV_NM", "BIZ_SCALE_AMT", "BIZ_SCALE_BASIS_TXT"]),
    **{c: _um("가 · 감점 적용방식 · 상한 확인 필요(정의서) — 업적평가 실적 DB 의 가감점 컬럼 확보 후") for c in ("BONUS_SCORE", "PENALTY_SCORE", "TOTAL_SCORE")},
    **_agent("ins-br-prime-corp", "report.branch-prime-corp", {"report": "report.branch-prime-corp", "section": "bp-effect"}, "bp-caution", "bp-finding"),
}
_ALL = {"group_kind_cd": "ALL"}
BRANCH_T02 = {
    **_rows(["BASE_YM", "BRC", "GROUP_KIND_CD", "MODEL_SEGMENT_CD", "GRADE_CD", "SAMPLE_FILTER_TXT", "BRC_BORROWER_CNT", "BRC_EXPOSURE_AMT", "BRC_COUNT_SHARE_RT", "BRC_AMOUNT_SHARE_RT",
             "BRC_AVG_GRADE_ORD", "BRC_WEIGHTED_GRADE_ORD", "BANK_BORROWER_CNT", "BANK_EXPOSURE_AMT", "BANK_COUNT_SHARE_RT", "BANK_AMOUNT_SHARE_RT", "BANK_AVG_GRADE_ORD",
             "BANK_WEIGHTED_GRADE_ORD", "SMALL_CORP_SHARE_GAP_PP", "GRADE_GAP_ORD"]),
    # 제안 버전(B.46 · Q96) — 같은 기준월 · 지점의 이전 적재와 수치 · 코드 열이 같으면 유지, 다르면 +1 (서술 · 분석 ID 는 비교 제외)
    "PROPOSAL_VER_NO": {"version": True},
    "CANDIDATE_CNT": {"metric": "br_prospect_pick", "rows_where": _ALL},
    "PROPOSED_NEW_LOAN_AMT": {"metric": "br_prospect_amt", "rows_where": _ALL},
    "CANDIDATE_FIN_GRADE_AVG": {"metric": "br_prospect_avg_grade", "rows_where": _ALL},
    "EXPECTED_CREDIT_GRADE_ORD": _um(MAPPING, "Q81"), "POST_AVG_GRADE_ORD": _um(MAPPING, "Q81"), "POST_WEIGHTED_GRADE_ORD": _um(MAPPING, "Q81"),
    "GRADE_IMPROVEMENT_ORD": _um(MAPPING, "Q81"), "EXPECTED_SCORE_GAIN": _um(MAPPING, "Q81"),
    "EXPECTED_NET_INCOME_AMT": _um("금리 · 조달원가 · 비용 · 충당금 원천 추가 필요(정의서) — 정보 없으면 산출불가"),
    # 80여 집계 행마다 보고서 HTML 을 반복하지 않도록 서술 · 보고서는 전체(ALL) 행에만
    **{k: (v if k in ("ANALYSIS_ID", "ANALYSIS_DT") else {**v, "rows_where": _ALL})
       for k, v in _agent("ins-br-prime-corp", "report.branch-prime-corp", {"report": "report.branch-prime-corp", "section": "bp-prospect"}, "bp-caution", "bp-prospect").items()},
}
BRANCH_T03 = {
    **_rows(["BASE_YM", "BRC", "PRODUCT_POOL_ID", "PURPOSE_CD", "SCORE_ELIGIBLE_YN", "BRC_RETAIL_EXPOSURE_AMT", "BRC_INCLUSIVE_EXPOSURE_AMT", "BRC_INCLUSIVE_BORROWER_CNT",
             "BRC_INCLUSIVE_SHARE_RT", "BRC_WEIGHTED_PD_RT", "BRC_OVERDUE_RT", "BANK_RETAIL_EXPOSURE_AMT", "BANK_INCLUSIVE_EXPOSURE_AMT", "BANK_INCLUSIVE_BORROWER_CNT",
             "BANK_INCLUSIVE_SHARE_RT", "BANK_WEIGHTED_PD_RT", "BANK_OVERDUE_RT", "SHARE_GAP_PP", "INTERNAL_HQ_DOC_EXPOSE_YN"]),
    "ANNUAL_BORROWER_LIMIT_AMT": {"row": "annual_borrower_limit_amt", "check": {"product_pool_id": "P01"}},
    "PRODUCT_CD": _um("소매 Pool ↔ 상품코드 매핑 미제공(정의서 '실 컬럼명 추후 확인')"),
    "PROPOSED_NEW_BORROWER_CNT": {"metric": "br_seomin_rec_cnt"},
    "PROPOSED_LOAN_PER_BORROWER_AMT": {"metric": "br_seomin_ticket"},
    "PROPOSED_NEW_EXPOSURE_AMT": {"metric": "br_seomin_rec_amt"},
    "EXPECTED_SCORE_GAIN": {"metric": "br_seomin_uplift"},
    "EXPECTED_ADD_PROVISION_AMT": {"metric": "br_seomin_add_prov"},
    "POST_WEIGHTED_PD_RT": _um("신규 유치분 Pool PD 배분 기준 미정 — 유치 후 가중 PD 는 배분 규칙 확정 후"),
    "EXPECTED_NET_INCOME_AMT": _um("금리 · 비용 · 충당금 원천 추가 필요(정의서) — PD 만으로 산출불가"),
    "EVAL_OVERDUE_EXEMPT_YN": _um("평가 예외 적용 대상 원문 미첨부(정의서)"),
    "POLICY_BACKGROUND_TXT": {"report": "report.branch-seomin", "section": "bs-change"},
    **_agent("ins-br-seomin", "report.branch-seomin", {"report": "report.branch-seomin", "section": "bs-effect"}, "bs-caution", "bs-effect"),
}
_D = lambda ds, col=None: {"dataset": ds, **({"column": col} if col else {})}  # noqa: E731
BRANCH_S01 = {
    "BASE_YM": _D("OBLG_GRD_DEF", "std_ym"), "BRWR_NO": _D("OBLG_GRD_DEF", "brwr_no"), "SUVMN_BRC": _D("OBLG_GRD_DEF", "SUVMN_BRC"), "LS_NICS_GRDC": _D("OBLG_GRD_DEF", "Ls_nics_GRDC"),
    "LN_BAC": _D("OBLG_GRD_DEF", "ln_bac"), "BRWR_NM": _D("OBLG_GRD_DEF", "brwr_nm"), "ONLYCARD": _D("OBLG_GRD_DEF", "onlycard"), "STD_INDS_CFC": _D("OBLG_GRD_DEF", "STD_INDS_CFC"),
    "CRDEVL_PTTP_DSC_F": _D("OBLG_GRD_DEF", "crdevl_pttp_dsc_f"), "DEFAULT_YN": _D("OBLG_GRD_DEF", "default"),
    "GRADE_LABEL": {"dataset": "OBLG_GRD_DEF", "column": "Ls_nics_GRDC", "note": "등급명은 규칙 CORP_GRADE_SCALE.labels 로 변환"},
}
BRANCH_S02 = {
    "BASE_YM": _um("후보 명세에 기준년월 컬럼 없음 — 데이터셋 버전(업로드 시점)으로 관리"),
    **{k: _D("CORP_PROSPECT", v) for k, v in {"BIZ_REG_NO": "biz_no", "CORP_REG_NO": "corp_no", "CORP_NM": "corp_nm", "CORP_SIZE_NM": "corp_scale", "ESTABLISH_DT": "estb_dt",
                                              "NICS_MODEL_CD": "nics_model", "EXPECTED_FIN_GRADE": "exp_grade", "INDUSTRY_CD": "ind_cd", "INDUSTRY_NM": "ind_nm", "HQ_REGION": "region",
                                              "HQ_CITY_GUN_GU": "sigungu", "TOTAL_ASSET_AMT": "tot_asset", "TOTAL_LIABILITY_AMT": "tot_liab", "TOTAL_EQUITY_AMT": "tot_equity",
                                              "SALES_AMT": "sales", "OPERATING_INCOME_AMT": "op_income", "NET_INCOME_AMT": "net_income"}.items()},
    **{c: _um("후보 선정 결과(지표 br_prospect_pick)의 항목 — 원천이 아닌 산출물") for c in ("TARGET_BRC", "EXISTING_LOAN_CUSTOMER_YN", "INDUSTRY_OVERLAP_YN", "CANDIDATE_REASON", "PROPOSED_LOAN_AMT")},
}
BRANCH_S03 = {
    "BASE_YM": _D("RETAIL_EXPOSURE", "std_ym"), "BORROWER_ID": _D("RETAIL_EXPOSURE", "brwr_id"), "EXPOSURE_AMT": _D("RETAIL_EXPOSURE", "exp_amt"),
    "PRODUCT_POOL_ID": _D("RETAIL_EXPOSURE", "pool_id"), "OFFICE_CD": _D("RETAIL_EXPOSURE", "office_cd"), "POOL_PD_RT": _D("RETAIL_POOL_MASTER", "pd_pct"),
    **{c: _um(NO_SRC) for c in ("LOAN_ACCOUNT_ID", "PRODUCT_CD", "PURPOSE_CD", "OVERDUE_AMT", "PROVISION_AMT", "ANNUAL_MAX_LIMIT_AMT", "NEW_OR_INCREASE_DT")},
}

# 운영 DB 연결 갱신 — 현재 연결이 '이전 기본값' 과 같을 때만 새 기본값으로(관리자가 바꾼 연결은 유지)
BINDING_UPGRADES: dict[str, list[dict[str, Any]]] = {
    **{f"{t}.{c}": [{"row": c.lower()}] for t in ("RISK_S99", "BRANCH_S99") for c in ("ORIGINAL_FILE_URI", "VALID_TO_DT", "PRINTED_PAGE_NO")},
    **{f"BRANCH_T02.{k}": [{x: y for x, y in v.items() if x != "rows_where"}] for k, v in BRANCH_T02.items() if k.startswith(("REPORT_", "AGENT_", "RISK_", "EVIDENCE_", "TAB_"))},
    "BRANCH_T02.PROPOSAL_VER_NO": [_um("다행 표의 제안 버전은 분석결과 식별자(ANALYSIS_ID)로 대신 추적")],  # B.46 — 이전 기본값(미연결)일 때만 버전 연결로
}

BINDINGS: dict[str, dict[str, Any]] = {
    **{f"RISK_T01.{k}": v for k, v in RISK_T01.items()},
    **{f"RISK_T02.{k}": v for k, v in RISK_T02.items()},
    **{f"RISK_T03.{k}": v for k, v in RISK_T03.items()},
    **{f"RISK_S99.{k}": v for k, v in S99.items()},
    **{f"BRANCH_T01.{k}": v for k, v in BRANCH_T01.items()},
    **{f"BRANCH_T02.{k}": v for k, v in BRANCH_T02.items()},
    **{f"BRANCH_T03.{k}": v for k, v in BRANCH_T03.items()},
    **{f"BRANCH_S01.{k}": v for k, v in BRANCH_S01.items()},
    **{f"BRANCH_S02.{k}": v for k, v in BRANCH_S02.items()},
    **{f"BRANCH_S03.{k}": v for k, v in BRANCH_S03.items()},
    **{f"BRANCH_S99.{k}": v for k, v in S99.items()},
}
