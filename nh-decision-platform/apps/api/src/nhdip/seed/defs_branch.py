"""영업점 시나리오 (B.29) — 업적평가 기반 영업 가이드 · 수원영통지점(사무소 001068).

근거: data/사나리오 정의/TalkFile_(영업점)데이터활용계획 및 Agent시나리오_.txt
  1화면  업적평가 평가항목별 득점 · 가/감점 요약 + 기준 변경 알림(의견 요약) + 사업부문(종기부 화면과 같은 형태, 영업점 값)
  2화면  사업KPI > 핵심사업 > 우량기업여신 — 지점 기업 익스포저(규모 · 등급 · 규모×등급) → 본부 추천 가망기업 중 마케팅 후보
  3화면  사업KPI > 생산적·포용금융 > 서민금융 — 소매 익스포저 Pool 분석 → 신규 유치 적정 규모 (충당금 · 동일차주 한도 고려)

원칙
- 원천 컬럼명은 시나리오 정의서 기준(Oblg_grd_def · TB_JC_PM_C_LA). 정의서에 없는 컬럼은 '가정' 으로 표시하고 별칭으로 받는다.
- 실제 파일 · 배점표 PDF 를 받기 전까지 모든 행은 결정적 난수로 만든 시뮬레이션 버전이다(data_origin=simulated).
- 배점 · 가중치 · 선정 기준 · 한도는 규칙(cfg.rule) 또는 데이터셋(배점표)에 두고 "시뮬레이션 가정" 으로 표시한다.
- 수치는 모두 커널 수식으로 계산한다(지표 · 빌더). 서술은 [[fig:ID]] 마커로만 수치를 참조한다.
"""
from __future__ import annotations

from typing import Any

from .defs_data import _std_nodes, col, metric, mref, q

WF = "wf_branch_kpi"
OFFICE = "001068"
ORG_CODE = "001068"  # 조직 코드 = 사무소 코드 (설정 branch.office_codes 로 다르게 매핑 가능)
YM = "202608"
PERIOD, PREV_PERIOD = "2026H2", "2026H1"

GRADE_LABELS = ["1", "2A", "2B", "3A", "3B", "4A", "4B", "5A", "5B", "5C", "6A", "6B", "6C", "7A", "7B", "8"]
SIZE_LABELS = {"11": "대기업", "12": "외감", "13": "비외감", "15": "소기업", "16": "기업형소호"}

# ═════════════════════════ 데이터셋 정의 ═════════════════════════
DATASETS = [
    dict(
        code="OBLG_GRD_DEF", name="기업 익스포저 차주별 현황 (Oblg_grd_def)", origin="bank", kind="fact",
        description="당행 기업차주 익스포저 전체(차주 단위). 조사자사무소코드로 영업점 보유분을 식별하고 최종NICS신용등급(1~16 = 1~8등급)으로 건전성을 본다. 카드차주(onlycard=1) · 등급 체계 밖 값은 분석 제외",
        file_pattern=r"Oblg_grd_def_(\d{6})\.(xlsx|csv|json)", refresh_cycle="월",
        columns=[
            col("std_ym", "기준년월(가정)", "str", True, ["기준년월", "기준월"]),
            col("brwr_no", "차주번호", "str", True, ["차주번호", "BRWR_NO"]),
            col("brwr_nm", "차주명", "str", False, ["차주명", "BRWR_NM"]),
            col("SUVMN_BRC", "조사자사무소코드", "str", True, ["조사자사무소코드", "suvmn_brc"]),
            col("Ls_nics_GRDC", "최종NICS신용등급", "int", False, ["최종NICS신용등급", "LS_NICS_GRDC", "ls_nics_grdc"]),
            col("ln_bac", "대출잔액(원)", "num", True, ["대출잔액", "LN_BAC"]),
            col("onlycard", "카드차주여부", "int", False, ["카드차주여부", "ONLYCARD"]),
            col("STD_INDS_CFC", "표준산업분류코드(11차)", "str", False, ["표준산업분류코드", "std_inds_cfc"]),
            col("crdevl_pttp_dsc_f", "최종신용평가모형구분코드", "str", False, ["최종신용평가모형구분코드", "CRDEVL_PTTP_DSC_F"]),
            col("default", "부도여부", "int", False, ["부도여부", "DEFAULT"]),
        ],
        key_columns=["std_ym", "brwr_no"], as_of_column="std_ym",
        mapping={"unit": "원", "used_by": ["영업점 기업여신 포트폴리오", "우량기업여신 업적평가", "평균 신용등급 비교"],
                 "concepts": [{"label": "BusinessDomain", "key": "기업여신", "about": True}] + [{"label": "Segment", "key": v} for v in SIZE_LABELS.values()]},
        quality_rules=[{"rule": "range", "column": "ln_bac", "min": 0}, {"rule": "allowed", "column": "crdevl_pttp_dsc_f", "values": list(SIZE_LABELS), "severity": "warning"}, {"rule": "allowed", "column": "onlycard", "values": [0, 1], "severity": "warning"}],
    ),
    dict(
        code="CORP_PROSPECT", name="여신가망 재무우량 기업명세 (본부 추천)", origin="bank", kind="fact",
        description="신용리스크관리부 [외감기업 활성화] 공문 붙임1 — 당행 여신 미거래 기업 중 재무등급 시산 결과가 우수한 상위규모 기업 (재무 단위 백만원)",
        file_pattern=r"붙임1\) 여신가망 재무우량 기업명세\((\d{4})\)\.(xlsx|csv|json)", refresh_cycle="수시",
        columns=[
            col("biz_no", "사업자등록번호", "str", True, ["사업자등록번호"]), col("corp_no", "법인등록번호", "str", False, ["법인등록번호"]),
            col("corp_nm", "기업명", "str", True, ["기업명"]), col("corp_scale", "기업규모", "str", False, ["기업규모"]), col("estb_dt", "설립일자", "str", False, ["설립일자"]),
            col("nics_model", "NICS모형", "str", False, ["NICS모형"]), col("exp_grade", "예상재무등급", "str", True, ["예상재무등급"]),
            col("ind_cd", "산업코드", "str", False, ["산업코드", "표준산업분류코드"]), col("ind_nm", "산업분류명", "str", False, ["산업분류명", "표준산업분류명"]),
            col("region", "지역", "str", True, ["지역"]), col("sigungu", "시군구", "str", True, ["시군구"]),
            col("tot_asset", "자산총계(백만원)", "num", False, ["자산총계"]), col("tot_liab", "부채총계(백만원)", "num", False, ["부채총계"]), col("tot_equity", "자본총계(백만원)", "num", False, ["자본총계"]),
            col("sales", "매출액(백만원)", "num", False, ["매출액"]), col("op_income", "영업이익(백만원)", "num", False, ["영업이익"]), col("net_income", "당기순이익(백만원)", "num", False, ["당기순이익"]),
        ],
        key_columns=["biz_no"],
        mapping={"unit": "백만원", "used_by": ["우량기업여신 마케팅 후보"], "concepts": [{"label": "BusinessDomain", "key": "기업여신", "about": True}]},
    ),
    dict(
        code="RETAIL_EXPOSURE", name="소매여신 익스포저 월별 현황 (TB_JC_PM_C_LA)", origin="bank", kind="fact",
        description="당행 소매(개인)여신 익스포저 월별 조사 테이블. 상세 컬럼명은 추후 확정 — 현재 컬럼명은 가정이며 한글 별칭으로도 받는다",
        file_pattern=r"TB_JC_PM_C_LA_(\d{6})\.(xlsx|csv|json)", refresh_cycle="월",
        columns=[
            col("std_ym", "기준년월(가정)", "str", True, ["기준년월"]), col("brwr_id", "차주식별번호", "str", True, ["차주식별번호"]),
            col("office_cd", "사무소코드", "str", True, ["사무소코드"]), col("pool_id", "해당상품Pool", "str", True, ["해당상품Pool", "Pool"]),
            col("exp_amt", "여신익스포져금액(원)", "num", True, ["여신익스포져금액", "익스포져금액"]),
            col("cb_grade", "CB등급(가정)", "int", False, ["CB등급"]), col("dlq_yn", "30일 이상 연체여부(가정)", "int", False, ["연체여부"]),
        ],
        key_columns=["std_ym", "brwr_id", "pool_id"], as_of_column="std_ym",
        mapping={"unit": "원", "used_by": ["영업점 소매여신 포트폴리오", "서민금융 업적평가"], "concepts": [{"label": "BusinessDomain", "key": "가계여신", "about": True}, {"label": "PolicyTheme", "key": "포용금융"}]},
        quality_rules=[{"rule": "range", "column": "exp_amt", "min": 0}],
    ),
    dict(
        code="RETAIL_POOL_MASTER", name="소매여신 상품 Pool 정의", origin="bank", kind="master",
        description="Pool 식별번호 → 상품군 · 저신용자 Pool 여부 · 업적평가 서민금융 인정 여부 · 용도코드 · 충당금률 가정(PD × LGD)",
        refresh_cycle="수시",
        columns=[
            col("pool_id", "Pool", "str", True), col("pool_nm", "Pool 명", "str", True), col("product_group", "상품군", "str"),
            col("low_credit", "저신용자 Pool", "bool"), col("seomin_eval", "업적평가 서민금융 인정", "bool"), col("use_cd", "용도코드", "str"),
            col("pd_pct", "PD(%·가정)", "num"), col("lgd_pct", "LGD(%·가정)", "num"), col("prov_rate_pct", "충당금률(%·가정)", "num"),
        ],
        key_columns=["pool_id"],
        mapping={"unit": "-", "used_by": ["서민금융 익스포저 식별", "충당금 영향"], "nodes": [{"label": "Product", "key_col": "pool_id", "name_col": "pool_nm"}]},
    ),
    dict(
        code="BRANCH_OFFICE_MASTER", name="영업점(사무소) 마스터", origin="bank", kind="master",
        description="사무소 코드 · 영업점명 · 소재 지역(시도 · 시군구, 시군구는 | 로 여러 개) · 지역본부 — 가망기업 지역 매칭에 사용",
        refresh_cycle="수시",
        columns=[col("office_cd", "사무소코드", "str", True), col("office_nm", "영업점명", "str", True), col("region", "지역(시도)", "str", True), col("sigungu", "시군구", "str", True), col("region_hq", "지역본부", "str"), col("org_code", "조직 코드", "str")],
        key_columns=["office_cd"],
        mapping={"unit": "-", "used_by": ["영업점 지역 매칭"]},
    ),
    dict(
        code="BRANCH_KPI_SCHEME", name="업적평가 배점표 (리테일 영업점)", origin="bank", kind="master",
        description="업적평가 세부기준의 영업본부/영업점 평가기준 > 배점표 > 리테일 — 반기별 평가항목 · 배점 · 상반기 대비 변경 (원본 PDF 수령 전 시뮬레이션 가정)",
        refresh_cycle="반기",
        columns=[col("period", "평가기간", "str", True), col("level", "단계", "int", True), col("group_cd", "상위 항목", "str", True), col("item_cd", "항목 코드", "str", True), col("item_nm", "항목명", "str", True),
                 col("parent_cd", "상위 코드", "str"), col("max_points", "배점", "num"), col("change_type", "변경 구분", "str"), col("change_summary", "변경 내용", "str"), col("doc_page", "근거 면", "str")],
        key_columns=["period", "item_cd"],
        mapping={"unit": "점", "used_by": ["업적평가 대시보드", "업적 점수 상향 산정"], "concepts": [{"label": "PolicyTheme", "key": "업적평가", "about": True}]},
    ),
    dict(
        code="BRANCH_KPI_SCORE", name="영업점 업적평가 득점 현황", origin="bank", kind="fact",
        description="영업점별 평가항목 득점 · 세부 실적(실적값 · 목표값) — 하반기 진행 중 시점 기준 (시뮬레이션)",
        refresh_cycle="월",
        columns=[col("office_cd", "사무소코드", "str", True), col("period", "평가기간", "str", True), col("as_of", "기준일", "date", True), col("level", "단계", "int", True), col("group_cd", "상위 항목", "str", True),
                 col("item_cd", "항목 코드", "str", True), col("score", "득점", "num"), col("actual_value", "실적값", "num"), col("target_value", "목표값", "num"), col("unit", "실적 단위", "str"), col("note", "비고", "str")],
        key_columns=["office_cd", "period", "item_cd"], as_of_column="as_of",
        mapping={"unit": "점", "used_by": ["업적평가 대시보드"]},
    ),
    dict(
        code="BRANCH_BIZ_BALANCE", name="영업점 사업부문별 잔액 · 실적", origin="bank", kind="fact",
        description="영업점 기준 수신 · 외환 · 퇴직연금 · 카드 부문 잔액(실적). 여신은 기업 · 소매 익스포저에서 계산",
        refresh_cycle="월",
        columns=[col("office_cd", "사무소코드", "str", True), col("ym", "기준년월", "str", True), col("segment_cd", "부문 코드", "str", True), col("segment_nm", "부문명", "str"), col("amount", "금액(원)", "num", True), col("measure", "기준", "str")],
        key_columns=["office_cd", "ym", "segment_cd"], as_of_column="ym",
        mapping={"unit": "원", "used_by": ["영업점 사업부문 현황"]},
    ),
]

# ═════════════════════════ 규칙 (시뮬레이션 가정) ═════════════════════════
RULES = [
    ("BRANCH_SCOPE", "영업점 분석 대상 · 평가 기간", "threshold",
     "Q44 추천안 — 영업점 워크플로우가 계산할 사무소 · 업적평가 기간. office_code 는 기본 지점(기존 산출물 키), office_codes 에 지점을 더하면 "
     "같은 정의로 지점마다 계산해 '<산출물>@<지점>' 으로 게시한다(B.47 · 설정 workflow.scopes — 그 지점의 사무소 · 득점 자료가 있어야 계산)",
     {"office_code": OFFICE, "office_codes": [OFFICE], "period": PERIOD, "prev_period": PREV_PERIOD, "period_label": "2026년 하반기", "as_of_label": "2026.08.31 (하반기 2개월 경과)"}),
    ("CORP_GRADE_SCALE", "기업 신용등급 체계 · 규모 구분", "threshold",
     "기업 신용등급 16단계(1~8등급) — 데이터 값 1~16 을 순서대로 매핑, 그 외 값은 분석 제외. 신용평가모형구분코드 → 규모 라벨",
     {"labels": GRADE_LABELS,
      "bands": [{"label": "1~3B", "max_grade": "3B"}, {"label": "4A~4B", "max_grade": "4B"}, {"label": "5A~5C", "max_grade": "5C"}, {"label": "6A~6C", "max_grade": "6C"}, {"label": "7A~8", "max_grade": "8"}],
      "size_labels": SIZE_LABELS, "size_order": list(SIZE_LABELS), "upper_sizes": ["11", "12", "13"], "micro_sizes": ["15"]}),
    ("BRANCH_PRIME_CORP_POLICY", "우량기업여신 등급별 가중치 · 목표 (시뮬레이션 가정 · Q46 추천안)", "threshold",
     "2026년 하반기 업적평가 세부기준 핵심사업 > 우량기업여신(84~91p) — 신규 · 증액 여신을 차주 등급 구간 가중치로 환산. 원본 PDF 수령 시 가중치 · 목표를 교체",
     {"weights": [{"max_grade": "3B", "weight": 1.5, "label": "1~3B"}, {"max_grade": "4B", "weight": 1.2, "label": "4A~4B"}, {"max_grade": "5C", "weight": 1.0, "label": "5A~5C"}, {"max_grade": "6C", "weight": 0.7, "label": "6A~6C"}, {"max_grade": "8", "weight": 0.5, "label": "7A~8"}],
      "h1_weight": 1.0, "target_weighted_mn": 60_000, "note": "가중치 · 목표(가중 실적 600억원)는 시뮬레이션 가정"}),
    ("BRANCH_PROSPECT_POLICY", "우량기업 마케팅 후보 선정 기준 (시뮬레이션 가정 · Q47 추천안)", "threshold",
     "본부 추천 여신가망 재무우량 기업 중 — 영업점 소재 지역(시도 · 시군구 앞부분) 일치, 예상재무등급 상한, 부채비율 상한, 지점 집중 업종(중분류 금액 비중 ≥ 기준) 제외, 업종당 1개, 등급 · 자산 순 상위 N. 기업당 신규 여신 가정액은 NICS 모형별",
     {"max_grade": "3B", "max_debt_ratio_pct": 200, "industry_level": 3, "overlap_share_pct": 5.0, "one_per_industry": True, "max_candidates": 5,
      "loan_mn_by_model": {"11": 5_000, "12": 3_000, "13": 1_500}, "default_loan_mn": 1_000, "note": "기업당 신규 여신 가정액(대기업 50억 · 외감 30억 · 비외감 15억)은 시뮬레이션 가정"}),
    ("BRANCH_SEOMIN_POLICY", "서민금융 신규 유치 권고 기준 (시뮬레이션 가정 · Q48 추천안)", "threshold",
     "권고 금액 = min(전행 평균 비중 도달 필요액, 충당금 증가 허용액 ÷ 서민금융 충당금률, 반기 신규 가능 건수 × 평균 취급액). 평균 취급액은 동일차주 연간 최고 한도 이내",
     {"per_borrower_max_mn": 35, "target_factor": 1.0, "max_add_provision_mn": 20, "max_new_cnt": 30, "target_cnt": 30,
      "note": "충당금 증가 허용액(2천만원) · 반기 신규 가능 건수(30건) · 목표 건수(30건)는 시뮬레이션 가정. 동일차주 최고 한도 35백만원은 시나리오 정의서 기준"}),
]

# ═════════════════════════ 지표 ═════════════════════════
OFF = {"ref": {"rule": "BRANCH_SCOPE", "path": "office_code"}}
PER = {"ref": {"rule": "BRANCH_SCOPE", "path": "period"}}
VALID = {"std_ym": "$latest", "onlycard": 0, "Ls_nics_GRDC": {"in": list(range(1, 17))}}
OB, RT, PM = "OBLG_GRD_DEF", "RETAIL_EXPOSURE", "RETAIL_POOL_MASTER"
SEO = {"pool_id": {"in_dataset": {"dataset": PM, "col": "pool_id", "where": {"seomin_eval": True}}}}
LOWC = {"pool_id": {"in_dataset": {"dataset": PM, "col": "pool_id", "where": {"low_credit": True}}}}
RT_ALL = {"std_ym": "$latest"}


# 마케팅 후보의 '미거래' 조건 — 최근 기준월 이 지점 기업 차주명(B.40 · Q85). 차주 명세에 사업자번호가 없어 이름으로 맞추므로
# 전행 기준이면 동명 기업이 많아(시뮬레이션 이름 포함) 지점 기준으로 둔다 — 사업자번호 원천이 생기면 where 를 전행으로 넓힌다
PROSPECT_EXISTING = {"q": {"dataset": "OBLG_GRD_DEF", "where": {"std_ym": "$latest", "SUVMN_BRC": {"ref": {"rule": "BRANCH_SCOPE", "path": "office_code"}}}, "col": "brwr_nm", "agg": "list"},
                     "label": "지점 기존 여신 차주(미거래 조건)", "unit": ""}


def _scope(where: dict[str, Any], branch: bool, key: str = "SUVMN_BRC") -> dict[str, Any]:
    return {**where, key: OFF} if branch else dict(where)


def metrics() -> list[dict[str, Any]]:
    M: list[dict[str, Any]] = []
    for pre, br in (("br", True), ("bank", False)):
        who = "지점" if br else "전행"
        w = _scope(VALID, br)
        M += [
            metric(f"{pre}_corp_cnt", f"{who} 기업여신 차주 수", "VALUE", {"value": q(OB, w, None, "count", "차주 수(카드전용 · 등급 체계 밖 제외)", "건")}, wf=WF, unit="CNT", decimals=0, sort=1),
            metric(f"{pre}_corp_amt", f"{who} 기업여신 대출잔액", "SUM", {"values": q(OB, w, "ln_bac", "list", "차주별 대출잔액", "원")}, wf=WF, unit="KRW_BN", decimals=1, scale=1e8, sort=2),
            metric(f"{pre}_micro_amt", f"{who} 소기업 대출잔액", "SUM", {"values": q(OB, {**w, "crdevl_pttp_dsc_f": "15"}, "ln_bac", "list", "소기업(15) 대출잔액", "원")}, wf=WF, unit="KRW_BN", decimals=1, scale=1e8, sort=3),
            metric(f"{pre}_micro_cnt", f"{who} 소기업 차주 수", "VALUE", {"value": q(OB, {**w, "crdevl_pttp_dsc_f": "15"}, None, "count", "소기업(15) 차주 수", "건")}, wf=WF, unit="CNT", decimals=0, sort=3),
            metric(f"{pre}_upper_amt", f"{who} 대기업 · 외감 · 비외감 대출잔액", "SUM", {"values": q(OB, {**w, "crdevl_pttp_dsc_f": {"in": ["11", "12", "13"]}}, "ln_bac", "list", "11 · 12 · 13 대출잔액", "원")}, wf=WF, unit="KRW_BN", decimals=1, scale=1e8, sort=3),
            metric(f"{pre}_upper_cnt", f"{who} 대기업 · 외감 · 비외감 차주 수", "VALUE", {"value": q(OB, {**w, "crdevl_pttp_dsc_f": {"in": ["11", "12", "13"]}}, None, "count", "11 · 12 · 13 차주 수", "건")}, wf=WF, unit="CNT", decimals=0, sort=3),
            metric(f"{pre}_micro_amt_share", f"{who} 소기업 비중(금액)", "SHARE", {"numerator": mref(f"{pre}_micro_amt", "소기업 대출잔액", "원"), "denominator": mref(f"{pre}_corp_amt", "전체 대출잔액", "원")}, wf=WF, unit="PCT", decimals=1, sort=4),
            metric(f"{pre}_micro_cnt_share", f"{who} 소기업 비중(건수)", "SHARE", {"numerator": mref(f"{pre}_micro_cnt", "소기업 차주 수", "건"), "denominator": mref(f"{pre}_corp_cnt", "전체 차주 수", "건")}, wf=WF, unit="PCT", decimals=1, sort=4),
            metric(f"{pre}_upper_amt_share", f"{who} 대기업 · 외감 · 비외감 비중(금액)", "SHARE", {"numerator": mref(f"{pre}_upper_amt", "11~13 대출잔액", "원"), "denominator": mref(f"{pre}_corp_amt", "전체 대출잔액", "원")}, wf=WF, unit="PCT", decimals=1, sort=4),
            metric(f"{pre}_upper_cnt_share", f"{who} 대기업 · 외감 · 비외감 비중(건수)", "SHARE", {"numerator": mref(f"{pre}_upper_cnt", "11~13 차주 수", "건"), "denominator": mref(f"{pre}_corp_cnt", "전체 차주 수", "건")}, wf=WF, unit="PCT", decimals=1, sort=4),
            metric(f"{pre}_avg_grade", f"{who} 평균 신용등급(대출잔액 가중, 1~16)", "WEIGHTED_AVG", {"values": q(OB, w, "Ls_nics_GRDC", "list", "차주별 등급(1~16)"), "weights": q(OB, w, "ln_bac", "list", "차주별 대출잔액", "원")}, wf=WF, unit="NONE", decimals=2, sort=5,
                   description="등급 순번(1=1등급 … 16=8등급)의 대출잔액 가중평균 — 값이 클수록 위험"),
            metric(f"{pre}_avg_grade_cnt", f"{who} 평균 신용등급(차주 수 기준, 1~16)", "MEAN", {"values": q(OB, w, "Ls_nics_GRDC", "list", "차주별 등급(1~16)")}, wf=WF, unit="NONE", decimals=2, sort=5),
        ]
        rw = _scope(RT_ALL, br, "office_cd")
        M += [
            metric(f"{pre}_retail_amt", f"{who} 소매여신 익스포저", "SUM", {"values": q(RT, rw, "exp_amt", "list", "차주별 익스포저", "원")}, wf=WF, unit="KRW_BN", decimals=1, scale=1e8, sort=20),
            metric(f"{pre}_retail_cnt", f"{who} 소매여신 차주 수", "VALUE", {"value": q(RT, rw, None, "count", "익스포저 건수", "건")}, wf=WF, unit="CNT", decimals=0, sort=20),
            metric(f"{pre}_seomin_amt", f"{who} 서민금융(업적평가 인정 Pool) 익스포저", "SUM", {"values": q(RT, {**rw, **SEO}, "exp_amt", "list", "서민금융 인정 Pool 익스포저", "원")}, wf=WF, unit="KRW_MN" if br else "KRW_BN", decimals=0 if br else 1, scale=1e6 if br else 1e8, sort=21),
            metric(f"{pre}_seomin_cnt", f"{who} 서민금융 차주 수", "VALUE", {"value": q(RT, {**rw, **SEO}, None, "count", "서민금융 인정 Pool 건수", "건")}, wf=WF, unit="CNT", decimals=0, sort=21),
            metric(f"{pre}_seomin_share", f"{who} 서민금융 비중(금액)", "SHARE", {"numerator": mref(f"{pre}_seomin_amt", "서민금융 익스포저", "원"), "denominator": mref(f"{pre}_retail_amt", "소매여신 익스포저", "원")}, wf=WF, unit="PCT", decimals=2, sort=22),
            metric(f"{pre}_seomin_cnt_share", f"{who} 서민금융 비중(건수)", "SHARE", {"numerator": mref(f"{pre}_seomin_cnt", "서민금융 건수", "건"), "denominator": mref(f"{pre}_retail_cnt", "소매여신 건수", "건")}, wf=WF, unit="PCT", decimals=1, sort=22),
            metric(f"{pre}_lowcredit_amt", f"{who} 저신용자 Pool 익스포저", "SUM", {"values": q(RT, {**rw, **LOWC}, "exp_amt", "list", "저신용자 Pool 익스포저", "원")}, wf=WF, unit="KRW_BN", decimals=1, scale=1e8, sort=22),
            metric(f"{pre}_lowcredit_share", f"{who} 저신용자 Pool 비중(금액)", "SHARE", {"numerator": mref(f"{pre}_lowcredit_amt", "저신용자 Pool 익스포저", "원"), "denominator": mref(f"{pre}_retail_amt", "소매여신 익스포저", "원")}, wf=WF, unit="PCT", decimals=1, sort=22),
            metric(f"{pre}_retail_dlq_amt", f"{who} 소매여신 연체 익스포저", "SUM", {"values": q(RT, {**rw, "dlq_yn": 1}, "exp_amt", "list", "30일 이상 연체 익스포저", "원")}, wf=WF, unit="KRW_MN", decimals=0, scale=1e6, sort=23, figures=[]),
            metric(f"{pre}_retail_dlq_rate", f"{who} 소매여신 연체율(금액)", "SHARE", {"numerator": mref(f"{pre}_retail_dlq_amt", "연체 익스포저", "원"), "denominator": mref(f"{pre}_retail_amt", "소매여신 익스포저", "원")}, wf=WF, unit="PCT", decimals=2, sort=23),
        ]
    M += [
        metric("br_avg_grade_gap", "평균 신용등급 차이(지점 − 전행)", "DIFF", {"a": mref("br_avg_grade", "지점 평균 등급"), "b": mref("bank_avg_grade", "전행 평균 등급")}, wf=WF, unit="NONE", decimals=2, sort=6, description="양수 = 지점이 전행보다 위험 쪽"),
        metric("bank_micro_avg_grade", "전행 소기업 평균 신용등급(차주 수 기준)", "MEAN", {"values": q(OB, {**VALID, "crdevl_pttp_dsc_f": "15"}, "Ls_nics_GRDC", "list", "소기업 등급(1~16)")}, wf=WF, unit="NONE", decimals=2, sort=6),
        metric("bank_upper_avg_grade", "전행 대기업 · 외감 · 비외감 평균 신용등급(차주 수 기준)", "MEAN", {"values": q(OB, {**VALID, "crdevl_pttp_dsc_f": {"in": ["11", "12", "13"]}}, "Ls_nics_GRDC", "list", "11~13 등급(1~16)")}, wf=WF, unit="NONE", decimals=2, sort=6),
        metric("br_micro_share_gap", "소기업 비중 차이(지점 − 전행, 금액)", "DIFF", {"a": mref("br_micro_amt_share", "지점 소기업 비중", "%"), "b": mref("bank_micro_amt_share", "전행 소기업 비중", "%")}, wf=WF, unit="PP", decimals=1, sort=6),
        # 우량기업 마케팅 후보
        metric("br_prospect_pick", "우량기업 마케팅 후보 수", "PROSPECT_SELECT",
               {"prospects": q("CORP_PROSPECT", {}, None, "list", "본부 추천 여신가망 재무우량 기업"), "branch_rows": q(OB, _scope(VALID, True), None, "list", "지점 기업 익스포저(업종 집중도)"),
                "office": q("BRANCH_OFFICE_MASTER", {"office_cd": OFF}, None, "first", "영업점 소재 지역"), "policy": {"rule": "BRANCH_PROSPECT_POLICY", "label": "선정 기준(시뮬레이션 가정)"},
                "weights": {"rule": "BRANCH_PRIME_CORP_POLICY", "path": "weights", "label": "등급 구간 가중치"}, "grade_scale": {"rule": "CORP_GRADE_SCALE", "path": "labels", "label": "등급 체계"},
                "existing": PROSPECT_EXISTING},
               wf=WF, unit="NONE", decimals=0, sort=30, figures=["br_prospect_cnt"]),
        metric("br_prospect_amt", "후보 신규 여신 가정액", "VALUE", {"value": mref("br_prospect_pick", "후보 신규 여신 합계", "원", "amount_won")}, wf=WF, unit="KRW_BN", decimals=0, scale=1e8, sort=31),
        metric("br_prospect_avg_grade", "후보 평균 예상재무등급(금액 가중, 1~16)", "VALUE", {"value": mref("br_prospect_pick", "후보 평균 등급", "", "avg_grade")}, wf=WF, unit="NONE", decimals=2, sort=31),
        metric("br_prospect_weighted", "후보 유치 시 등급 가중 실적", "VALUE", {"value": mref("br_prospect_pick", "가중 실적", "백만원", "weighted_mn")}, wf=WF, unit="KRW_BN", decimals=0, scale=100, sort=31),
        metric("br_avg_grade_after", "후보 유치 후 지점 평균 신용등급", "BLEND_AVG", {"avg_a": mref("br_avg_grade", "현재 지점 평균 등급"), "w_a": mref("br_corp_amt", "현재 대출잔액", "원"), "avg_b": mref("br_prospect_avg_grade", "후보 평균 등급"), "w_b": mref("br_prospect_amt", "후보 신규 여신", "원")}, wf=WF, unit="NONE", decimals=2, sort=32),
        metric("br_avg_grade_improve", "평균 신용등급 개선 폭(단계)", "DIFF", {"a": mref("br_avg_grade", "유치 전"), "b": mref("br_avg_grade_after", "유치 후")}, wf=WF, unit="NONE", decimals=2, sort=33),
        metric("br_prime_actual", "우량기업여신 현재 실적(등급 가중)", "VALUE", {"value": q("BRANCH_KPI_SCORE", {"office_cd": OFF, "period": PER, "item_cd": "CORE_PRIME", "as_of": "$latest"}, "actual_value", label="하반기 누적 가중 실적", unit="백만원")}, wf=WF, unit="KRW_BN", decimals=0, scale=100, sort=34),
        metric("br_prime_target", "우량기업여신 만점 목표(등급 가중)", "VALUE", {"value": {"rule": "BRANCH_PRIME_CORP_POLICY", "path": "target_weighted_mn", "label": "목표(시뮬레이션 가정)", "unit": "백만원"}}, wf=WF, unit="KRW_BN", decimals=0, scale=100, sort=34),
        metric("br_prime_points", "우량기업여신 배점", "VALUE", {"value": q("BRANCH_KPI_SCHEME", {"period": PER, "item_cd": "CORE_PRIME"}, "max_points", label="배점표(하반기)", unit="점")}, wf=WF, unit="NONE", decimals=0, sort=34),
        metric("br_prime_score_now", "우량기업여신 현재 득점", "KPI_PROPORTIONAL_SCORE", {"actual": mref("br_prime_actual", "현재 실적", "백만원"), "target": mref("br_prime_target", "목표", "백만원"), "points": mref("br_prime_points", "배점", "점")}, wf=WF, unit="NONE", decimals=1, sort=35),
        metric("br_prime_score_after", "후보 유치 시 우량기업여신 득점", "KPI_PROPORTIONAL_SCORE", {"actual": mref("br_prime_actual", "현재 실적", "백만원"), "target": mref("br_prime_target", "목표", "백만원"), "points": mref("br_prime_points", "배점", "점"), "add": mref("br_prospect_weighted", "후보 가중 실적", "백만원")}, wf=WF, unit="NONE", decimals=1, sort=36),
        metric("br_prime_uplift", "예상 업적 점수 상향(우량기업여신)", "DIFF", {"a": mref("br_prime_score_after", "유치 후 득점"), "b": mref("br_prime_score_now", "현재 득점")}, wf=WF, unit="NONE", decimals=1, sort=37),
        # 서민금융
        metric("br_seomin_share_gap", "서민금융 비중 차이(전행 − 지점)", "DIFF", {"a": mref("bank_seomin_share", "전행 비중", "%"), "b": mref("br_seomin_share", "지점 비중", "%")}, wf=WF, unit="PP", decimals=2, sort=40),
        metric("br_seomin_prov_rate", "서민금융 충당금률(가정)", "VALUE", {"value": q(PM, {"seomin_eval": True}, "prov_rate_pct", label="Pool 충당금률(PD × LGD, 가정)", unit="%")}, wf=WF, unit="PCT", decimals=2, sort=40),
        metric("bank_seomin_dlq_rate", "전행 서민금융 연체율(금액)", "SHARE", {"numerator": q(RT, {**RT_ALL, **SEO, "dlq_yn": 1}, "exp_amt", "sum", "서민금융 연체 익스포저", "원"), "denominator": mref("bank_seomin_amt", "전행 서민금융 익스포저", "원")}, wf=WF, unit="PCT", decimals=2, sort=40),
        metric("br_seomin_ticket_avg", "전행 서민금융 차주당 평균 익스포저", "RATIO", {"a": mref("bank_seomin_amt", "전행 서민금융 익스포저", "원"), "b": mref("bank_seomin_cnt", "전행 서민금융 건수", "건")}, wf=WF, unit="KRW_MN", decimals=1, scale=1e6, sort=41),
        metric("br_seomin_limit", "동일차주 연간 최고 대출한도", "VALUE", {"value": {"rule": "BRANCH_SEOMIN_POLICY", "path": "per_borrower_max_mn", "label": "동일차주 최고 한도", "unit": "백만원"}}, wf=WF, unit="KRW_MN", decimals=0, sort=41),
        metric("br_seomin_limit_won", "동일차주 최고 한도(원)", "LINEAR", {"a": {"const": 0}, "b": mref("br_seomin_limit", "최고 한도", "백만원"), "c": {"const": 1_000_000, "label": "백만원 → 원"}}, wf=WF, unit="KRW_MN", decimals=0, scale=1e6, sort=42, figures=[]),
        metric("br_seomin_ticket", "권고 산정 평균 취급액(한도 이내)", "MIN_OF", {"a": mref("br_seomin_ticket_avg", "전행 평균 익스포저", "원"), "b": mref("br_seomin_limit_won", "동일차주 최고 한도", "원")}, wf=WF, unit="KRW_MN", decimals=1, scale=1e6, sort=43),
        metric("br_seomin_gap_amt", "전행 평균 비중 도달 필요액", "SHARE_GAP_AMOUNT", {"current": mref("br_seomin_amt", "지점 서민금융", "원"), "total": mref("br_retail_amt", "지점 소매여신", "원"), "target_share": mref("bank_seomin_share", "전행 평균 비중", "%"), "factor": {"rule": "BRANCH_SEOMIN_POLICY", "path": "target_factor", "label": "목표 배수"}}, wf=WF, unit="KRW_MN", decimals=0, scale=1e6, sort=44),
        metric("br_seomin_prov_limit", "충당금 증가 허용액", "LINEAR", {"a": {"const": 0}, "b": {"rule": "BRANCH_SEOMIN_POLICY", "path": "max_add_provision_mn", "label": "허용액(시뮬레이션 가정)", "unit": "백만원"}, "c": {"const": 1_000_000, "label": "백만원 → 원"}}, wf=WF, unit="KRW_MN", decimals=0, scale=1e6, sort=44),
        metric("br_seomin_prov_cap", "충당금 허용 범위 내 최대 유치액", "SHARE", {"numerator": mref("br_seomin_prov_limit", "충당금 증가 허용액", "원"), "denominator": mref("br_seomin_prov_rate", "충당금률", "%")}, wf=WF, unit="KRW_MN", decimals=0, scale=1e6, sort=45),
        metric("br_seomin_max_cnt", "반기 신규 가능 건수", "VALUE", {"value": {"rule": "BRANCH_SEOMIN_POLICY", "path": "max_new_cnt", "label": "신규 가능 건수(시뮬레이션 가정)", "unit": "건"}}, wf=WF, unit="CNT", decimals=0, sort=45),
        metric("br_seomin_cnt_cap", "신규 가능 건수 기준 최대 유치액", "LINEAR", {"a": {"const": 0}, "b": mref("br_seomin_max_cnt", "신규 가능 건수", "건"), "c": mref("br_seomin_ticket", "평균 취급액", "원")}, wf=WF, unit="KRW_MN", decimals=0, scale=1e6, sort=45),
        metric("br_seomin_rec_amt", "권고 신규 유치 규모", "MIN_OF", {"a": mref("br_seomin_gap_amt", "비중 도달 필요액", "원"), "b": mref("br_seomin_prov_cap", "충당금 허용 범위", "원"), "c": mref("br_seomin_cnt_cap", "건수 기준", "원")}, wf=WF, unit="KRW_MN", decimals=0, scale=1e6, sort=46),
        metric("br_seomin_rec_cnt", "권고 신규 유치 건수", "CEIL_DIV", {"a": mref("br_seomin_rec_amt", "권고 규모", "원"), "b": mref("br_seomin_ticket", "평균 취급액", "원")}, wf=WF, unit="CNT", decimals=0, sort=47),
        metric("br_seomin_add_prov", "권고 규모 유치 시 예상 추가 충당금", "PCT_AMOUNT", {"base": mref("br_seomin_rec_amt", "권고 규모", "원"), "rate": mref("br_seomin_prov_rate", "충당금률", "%")}, wf=WF, unit="KRW_MN", decimals=1, scale=1e6, sort=47),
        metric("br_seomin_amt_after", "유치 후 지점 서민금융 익스포저", "LINEAR", {"a": mref("br_seomin_amt", "현재", "원"), "b": mref("br_seomin_rec_amt", "권고 규모", "원"), "c": {"const": 1}}, wf=WF, unit="KRW_MN", decimals=0, scale=1e6, sort=48, figures=[]),
        metric("br_retail_amt_after", "유치 후 지점 소매여신 익스포저", "LINEAR", {"a": mref("br_retail_amt", "현재", "원"), "b": mref("br_seomin_rec_amt", "권고 규모", "원"), "c": {"const": 1}}, wf=WF, unit="KRW_BN", decimals=1, scale=1e8, sort=48, figures=[]),
        metric("br_seomin_share_after", "유치 후 지점 서민금융 비중", "SHARE", {"numerator": mref("br_seomin_amt_after", "유치 후 서민금융", "원"), "denominator": mref("br_retail_amt_after", "유치 후 소매여신", "원")}, wf=WF, unit="PCT", decimals=2, sort=49),
        metric("br_seomin_actual", "서민금융 하반기 신규 실적", "VALUE", {"value": q("BRANCH_KPI_SCORE", {"office_cd": OFF, "period": PER, "item_cd": "INCL_SEOMIN", "as_of": "$latest"}, "actual_value", label="하반기 누적 신규 건수", unit="건")}, wf=WF, unit="CNT", decimals=0, sort=50),
        metric("br_seomin_target", "서민금융 만점 목표 건수", "VALUE", {"value": {"rule": "BRANCH_SEOMIN_POLICY", "path": "target_cnt", "label": "목표(시뮬레이션 가정)", "unit": "건"}}, wf=WF, unit="CNT", decimals=0, sort=50),
        metric("br_seomin_points", "서민금융 배점", "VALUE", {"value": q("BRANCH_KPI_SCHEME", {"period": PER, "item_cd": "INCL_SEOMIN"}, "max_points", label="배점표(하반기)", unit="점")}, wf=WF, unit="NONE", decimals=0, sort=50),
        metric("br_seomin_score_now", "서민금융 현재 득점", "KPI_PROPORTIONAL_SCORE", {"actual": mref("br_seomin_actual", "현재 실적", "건"), "target": mref("br_seomin_target", "목표", "건"), "points": mref("br_seomin_points", "배점", "점")}, wf=WF, unit="NONE", decimals=1, sort=51),
        metric("br_seomin_score_after", "권고 규모 유치 시 서민금융 득점", "KPI_PROPORTIONAL_SCORE", {"actual": mref("br_seomin_actual", "현재 실적", "건"), "target": mref("br_seomin_target", "목표", "건"), "points": mref("br_seomin_points", "배점", "점"), "add": mref("br_seomin_rec_cnt", "권고 건수", "건")}, wf=WF, unit="NONE", decimals=1, sort=52),
        metric("br_seomin_uplift", "예상 업적 점수 상향(서민금융)", "DIFF", {"a": mref("br_seomin_score_after", "유치 후 득점"), "b": mref("br_seomin_score_now", "현재 득점")}, wf=WF, unit="NONE", decimals=1, sort=53),
    ]
    # 업적평가 합계
    SC = "BRANCH_KPI_SCORE"
    base = {"office_cd": OFF, "period": PER, "level": 2, "as_of": "$latest"}  # 득점 현황은 기준일 스냅숏 — 새 기준일을 올려도 중복 합산하지 않음
    M += [
        metric("br_kpi_total", "업적평가 총득점(가 · 감점 포함)", "SUM", {"values": q(SC, base, "score", "list", "평가항목 득점", "점")}, wf=WF, unit="NONE", decimals=1, sort=60),
        metric("br_kpi_max", "업적평가 총배점", "SUM", {"values": q("BRANCH_KPI_SCHEME", {"period": PER, "level": 2, "group_cd": {"ne": "ADJ"}}, "max_points", "list", "평가항목 배점", "점")}, wf=WF, unit="NONE", decimals=0, sort=60),
        metric("br_kpi_cust", "고객KPI 득점", "SUM", {"values": q(SC, {**base, "group_cd": "CUST"}, "score", "list", "고객KPI 항목 득점", "점")}, wf=WF, unit="NONE", decimals=1, sort=61),
        metric("br_kpi_biz", "사업KPI 득점", "SUM", {"values": q(SC, {**base, "group_cd": "BIZ"}, "score", "list", "사업KPI 항목 득점", "점")}, wf=WF, unit="NONE", decimals=1, sort=61),
        metric("br_kpi_fin", "재무KPI 득점", "SUM", {"values": q(SC, {**base, "group_cd": "FIN"}, "score", "list", "재무KPI 항목 득점", "점")}, wf=WF, unit="NONE", decimals=1, sort=61),
        metric("br_kpi_adj", "가 · 감점 합계", "SUM", {"values": q(SC, {**base, "group_cd": "ADJ"}, "score", "list", "가점 · 감점", "점")}, wf=WF, unit="NONE", decimals=1, sort=61),
        metric("br_kpi_uplift", "예상 업적 점수 상향 합계", "LINEAR", {"a": mref("br_prime_uplift", "우량기업여신"), "b": mref("br_seomin_uplift", "서민금융"), "c": {"const": 1}}, wf=WF, unit="NONE", decimals=1, sort=62),
        metric("br_kpi_total_after", "의견 반영 시 예상 총득점", "LINEAR", {"a": mref("br_kpi_total", "현재 총득점"), "b": mref("br_kpi_uplift", "예상 상향"), "c": {"const": 1}}, wf=WF, unit="NONE", decimals=1, sort=63),
        # 사업부문 (영업점 기준)
        metric("br_loan_total", "여신 잔액(기업 + 소매)", "LINEAR", {"a": mref("br_corp_amt", "기업여신 대출잔액", "원"), "b": mref("br_retail_amt", "소매여신 익스포저", "원"), "c": {"const": 1}}, wf=WF, unit="KRW_BN", decimals=1, scale=1e8, sort=70),
    ]
    for seg, label in (("deposit", "수신 평잔"), ("fx", "외환 누적 실적"), ("pension", "퇴직연금 적립금"), ("card", "카드 누적 이용실적")):
        M.append(metric(f"br_seg_{seg}", label, "VALUE", {"value": q("BRANCH_BIZ_BALANCE", {"office_cd": OFF, "ym": "$latest", "segment_cd": seg}, "amount", label=label, unit="원")}, wf=WF, unit="KRW_BN", decimals=1, scale=1e8, sort=71))
    return M


# ═════════════════════════ 표 · 차트 바인딩 ═════════════════════════
PF = {"dataset": OB, "where": VALID, "office": OFF, "office_col": "SUVMN_BRC", "scale_rule": "CORP_GRADE_SCALE"}
RP = {"dataset": RT, "where": RT_ALL, "office": OFF, "office_col": "office_cd", "master": PM}
CAP_SIZE = "기업규모별 익스포저 현황 — 지점 vs 전행"
CAP_GRADE = "신용등급별 익스포저 현황 — 지점 vs 전행"
CAP_XC = "기업규모 × 신용등급 구간 — 건수 기준 비중(지점 전체 = 100%)"
CAP_XA = "기업규모 × 신용등급 구간 — 금액 기준 비중(지점 전체 = 100%)"
CAP_WEIGHTS = "우량기업여신 신용등급 구간별 가중치 (2026년 하반기 신설)"
CAP_PROSPECT = "마케팅 후보 기업 — 본부 추천 여신가망 재무우량 기업 중 선정"
CAP_TOP = "지점 기업여신 상위 차주 (대출잔액 순)"
CAP_POOL = "소매여신 Pool별 익스포저 — 지점 vs 전행"
CAP_SEOMIN = "신규 유치 규모 산정 — 한도별 비교"
CHART_BAND = "신용등급 구간별 금액 비중 — 지점 vs 전행"
CHART_POOL = "상품군별 금액 비중 — 지점 vs 전행"
R1, R2, DASH = "report.branch-prime-corp", "report.branch-seomin", "branch_dashboard"


def bindings() -> list[dict[str, Any]]:
    return [
        *[dict(workflow_code=WF, artifact_key=k, path="office", builder="branch_office", params={"office": OFF}) for k in (DASH, "branch_tabs", R1, R2)],
        dict(workflow_code=WF, artifact_key=DASH, path="scorecard.groups", builder="branch_kpi_scorecard", params={"office": OFF, "period": PER, "prev_period": {"ref": {"rule": "BRANCH_SCOPE", "path": "prev_period"}}}),
        dict(workflow_code=WF, artifact_key=R1, path=f"table:{CAP_SIZE}", builder="branch_size_table", params=PF),
        dict(workflow_code=WF, artifact_key=R1, path=f"table:{CAP_GRADE}", builder="branch_grade_table", params=PF),
        dict(workflow_code=WF, artifact_key=R1, path=f"table:{CAP_XC}", builder="branch_size_grade_table", params={**PF, "mode": "count"}),
        dict(workflow_code=WF, artifact_key=R1, path=f"table:{CAP_XA}", builder="branch_size_grade_table", params={**PF, "mode": "amount"}),
        dict(workflow_code=WF, artifact_key=R1, path=f"chart:{CHART_BAND}", builder="branch_grade_band_series", params=PF),
        dict(workflow_code=WF, artifact_key=R1, path=f"table:{CAP_WEIGHTS}", builder="branch_prime_weights", params={"rule": "BRANCH_PRIME_CORP_POLICY", "scale_rule": "CORP_GRADE_SCALE"}),
        dict(workflow_code=WF, artifact_key=R1, path=f"table:{CAP_PROSPECT}", builder="branch_prospect_table", params={"metric": "br_prospect_pick"}),
        dict(workflow_code=WF, artifact_key=R1, path=f"table_note:{CAP_PROSPECT}", builder="branch_prospect_note", params={"metric": "br_prospect_pick", "rule": "BRANCH_PROSPECT_POLICY"}),
        dict(workflow_code=WF, artifact_key=R1, path=f"table:{CAP_TOP}", builder="branch_top_borrowers", params={**PF, "limit": 10}),
        dict(workflow_code=WF, artifact_key=R2, path=f"table:{CAP_POOL}", builder="branch_pool_table", params=RP),
        dict(workflow_code=WF, artifact_key=R2, path=f"chart:{CHART_POOL}", builder="branch_pool_series", params=RP),
        dict(workflow_code=WF, artifact_key=R2, path=f"table:{CAP_SEOMIN}", builder="branch_seomin_constraints", params={"metrics": {"gap": "br_seomin_gap_amt", "prov": "br_seomin_prov_cap", "cnt": "br_seomin_cnt_cap", "rec": "br_seomin_rec_amt", "ticket": "br_seomin_ticket"}}),
    ]


# ═════════════════════════ 워크플로우 ═════════════════════════
WORKFLOWS = [
    dict(
        code=WF, name="영업점 업적평가 영업 가이드", sort=4,
        description="업적평가 배점표 · 득점 · 기업/소매 익스포저 · 본부 추천 가망기업 · 업적평가 기준 문서가 바뀌면 지점 포트폴리오와 업적 점수 상향 규모를 다시 계산하고 영업 가이드(의견 탭)를 갱신",
        outputs=[DASH, "branch_tabs", R1, R2],
        nodes=_std_nodes(
            "narrator_branch",
            [
                {"insight_id": "ins-br-prime-corp", "instruction": "업적평가 기준(핵심사업 > 우량기업여신 신설), 지점의 소기업 비중 · 평균 등급이 전행보다 낮은 점, 후보 수 · 금액 · 평균 등급 개선 · 예상 점수 상향, 건전성 감점 방지(우량기업 중심) 주의점을 포함한다."},
                {"insight_id": "ins-br-seomin", "instruction": "업적평가 기준(생산적·포용금융 > 서민금융 신설), 지점 서민금융 비중의 전행 대비 수준, 권고 건수 · 규모와 그 근거가 된 한도, 동일차주 최고 한도, 연체평가 예외와 별개로 실제 충당금 영향이 있다는 점을 포함한다. 본부 내부 문서는 인용하지 않는다."},
            ],
            {"query": "업적평가 세부기준 우량기업여신 신용등급 가중치 서민금융 새희망홀씨 신규 유치 배점 연체평가 예외 생산적 포용금융 정책", "concepts": ["업적평가", "포용금융", "기업여신"], "doc_classes": ["branch_ref", "gov_policy"], "k": 4},
            after_views=[("tabs", "분석 탭 동기화", "sync_analysis_tabs", None, {"artifact": "branch_tabs", "reports": ["branch_prime_corp", "branch_seomin"]})],
        ),
        triggers=[("cron", "30 6 * * *"), ("dataset", "OBLG_GRD_DEF"), ("dataset", "CORP_PROSPECT"), ("dataset", "RETAIL_EXPOSURE"), ("master", "RETAIL_POOL_MASTER"), ("master", "BRANCH_OFFICE_MASTER"),
                  ("master", "BRANCH_KPI_SCHEME"), ("dataset", "BRANCH_KPI_SCORE"), ("dataset", "BRANCH_BIZ_BALANCE"), ("doc_class", "branch_ref"), ("doc_class", "gov_policy"),
                  ("rule", "BRANCH_SCOPE"), ("rule", "CORP_GRADE_SCALE"), ("rule", "BRANCH_PRIME_CORP_POLICY"), ("rule", "BRANCH_PROSPECT_POLICY"), ("rule", "BRANCH_SEOMIN_POLICY")],
    ),
]

# 이 시나리오로 추가되는 시드 문서 (운영 DB 에는 1회 보강으로 적재)
DOC_IDS = ["doc-perf-2026h1", "doc-perf-2026h2", "doc-risk-prospect-notice"]
ARTIFACT_KEYS = [DASH, "branch_tabs", R1, R2]
