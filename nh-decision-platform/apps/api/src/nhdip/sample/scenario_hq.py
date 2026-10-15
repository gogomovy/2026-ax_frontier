"""시연 시나리오 — 종합기획부 · 신용리스크관리부 원천 값 (Phase I · Q136).

예전에 시드가 행으로 바로 넣던 시뮬레이션 값(손익 · 잔액 · 충당금 · 모형 등급 · 부도율 · 자본 · 타행 · 경영계획 KPI)이다.
이 값은 `nhdip.sample.build` 가 실제 업로드 파일(원본 보고서 양식 엑셀 · 실무형 엑셀 · CSV)로 바꾸고,
플랫폼에는 업로드 경로로만 들어간다. 2026.08 값은 기존 시나리오와 같다(골든셋 · E2E 기준).
"""
from __future__ import annotations

import json
import os
from typing import Any

K = "HQ_PLAN_KPI"  # 시연 묶음 안의 자료 구분(manifest) — 플랫폼 데이터셋 코드가 아님

HERE = os.path.dirname(__file__)


def _raw() -> dict[str, Any]:
    with open(os.path.join(HERE, "scenario_raw.json"), encoding="utf-8") as fh:
        return json.load(fh)


RAW_FIN = {
    "TOTAL_REVENUE": ("전체 수익", "Sheet1!D12", {"202408": 4_371_940, "202508": 4_603_180, "202608": 4_812_360}),
    "LOAN_NIM": ("여신(일반)부문 이자마진 수익", "Sheet1!D118", {"202408": 2_034_120, "202508": 2_112_880, "202608": 2_186_540}),
    "CORP_INTEREST": ("기업자금대출금이자", "Sheet1!D131", {"202408": 1_003_560, "202508": 1_048_900, "202608": 1_089_820}),
    "HH_INTEREST": ("가계자금대출금이자", "Sheet1!D140", {"202408": 812_300, "202508": 852_110, "202608": 909_960}),
    "HH_ETC_INTEREST": ("기타가계자금대출이자", "Sheet1!D144", {"202608": 106_200}),
    "HOUSE_INTEREST": ("주택자금대출이자", "Sheet1!D146", {"202608": 486_000}),
    "PUBLIC_INTEREST": ("공공자금대출이자", "Sheet1!D150", {"202608": 114_000}),
}
RAW_BAL = {
    "CORP": ("기업자금대출금", "Sheet1!E21", {"202408": 106_240_000, "202508": 110_860_000, "202608": 115_340_000}),
    "HH": ("가계자금대출금", "Sheet1!E29", {"202408": 88_120_000, "202508": 93_180_000, "202608": 99_240_000}),
    "HH_ETC": ("기타가계자금대출금", "Sheet1!E33", {"202608": 12_340_000}),
    "HOUSE": ("주택자금대출금", "Sheet1!E31", {"202608": 62_480_000}),
    "PUBLIC": ("공공자금대출금", "Sheet1!E37", {"202608": 18_620_000}),
}
PROVISION_TOTAL = {"202601": (3_284_600, "X314"), "202608": (3_412_180, "X318")}
DR_MONTHS = ["202509", "202510", "202511", "202512", "202601", "202602", "202603", "202604", "202605", "202606", "202607", "202608"]
DR_SERIES = [
    ("corp_large", "대기업", "corp", [0.412, 0.408, 0.401, 0.396, 0.389, 0.392, 0.388, 0.381, 0.377, 0.374, 0.371, 0.368]),
    ("corp_audited", "외감", "corp", [0.884, 0.891, 0.902, 0.918, 0.931, 0.944, 0.958, 0.971, 0.986, 1.004, 1.021, 1.038]),
    ("corp_unaudited", "비외감", "corp", [1.642, 1.668, 1.701, 1.736, 1.772, 1.814, 1.858, 1.901, 1.947, 1.994, 2.041, 2.088]),
    ("corp_micro", "소기업", "corp", [2.481, 2.523, 2.571, 2.618, 2.664, 2.702, 2.738, 2.761, 2.774, 2.781, 2.766, 2.753]),
    ("corp_soho", "기업형소호", "corp", [3.128, 3.182, 3.246, 3.311, 3.384, 3.462, 3.541, 3.618, 3.694, 3.768, 3.841, 3.912]),
    ("pool_1", "풀 1 (임시)", "retail", [1.214, 1.228, 1.241, 1.259, 1.272, 1.288, 1.301, 1.318, 1.332, 1.347, 1.361, 1.374]),
    ("pool_2", "풀 2 (임시)", "retail", [0.682, 0.679, 0.674, 0.671, 0.668, 0.664, 0.661, 0.658, 0.654, 0.651, 0.648, 0.644]),
    ("pool_3", "풀 3 (임시)", "retail", [2.341, 2.388, 2.442, 2.501, 2.564, 2.628, 2.691, 2.758, 2.822, 2.889, 2.954, 3.018]),
    ("pool_4", "풀 4 (임시)", "retail", [1.882, 1.901, 1.918, 1.934, 1.951, 1.962, 1.974, 1.981, 1.988, 1.994, 1.998, 2.004]),
    ("pool_5", "풀 5 (임시)", "retail", [0.944, 0.951, 0.958, 0.962, 0.971, 0.978, 0.984, 0.991, 0.998, 1.004, 1.011, 1.018]),
]
CAPITAL_ITEMS = [
    ("ASSET_GROWTH_MAX", "총자산 최대 증가율(지주 한도)", 8.2, "%"),
    ("BANK_ASSET_TARGET", "은행 목표 총자산 증가율", 7.4, "%"),
    ("RWA_NET_LIMIT", "RWA 순증 한도", 12.4, "조원"),
    ("RWA_DEPT_TOTAL", "부서별 배분 합계", 8.6, "조원"),
    ("RWA_CORP_ALLOC", "기업 부문 신용RWA 배분", 4.9, "조원"),
    ("RWA_CORP_USED", "기업 부문 신용RWA 사용", 3.42, "조원"),
    ("RWA_HH_ALLOC", "가계 부문 신용RWA 배분", 3.1, "조원"),
    ("RWA_HH_USED", "가계 부문 신용RWA 사용", 2.86, "조원"),
    ("RWA_ETC_ALLOC", "기타 부문 신용RWA 배분", 0.6, "조원"),
    ("RWA_ETC_USED", "기타 부문 신용RWA 사용", 0.31, "조원"),
    ("BIS_TOTAL", "BIS 총자본비율", 14.8, "%"),
]
PD_MIN_6B = 6.412


def hq_versions() -> list[dict[str, Any]]:
    """[{dataset, file_name, as_of, rows}] — 파일 단위 버전 (화면 데이터 목록과 동일한 파일명)."""
    raw = _raw()
    out: list[dict[str, Any]] = []
    for ym in ("202408", "202508", "202608"):
        rows = [{"ym": ym, "item_code": code, "item_name": name, "amount": vals[ym], "src_ref": cell} for code, (name, cell, vals) in RAW_FIN.items() if ym in vals]
        out.append({"dataset": "PL_PRODUCT_SEGMENT", "file_name": f"({ym})2633_상품부문별손익계산서.xlsx", "rows": rows})
        rows = [{"ym": ym, "account_code": code, "account_name": name, "balance": vals[ym], "src_ref": cell} for code, (name, cell, vals) in RAW_BAL.items() if ym in vals]
        out.append({"dataset": "LOAN_BALANCE_MONTHLY", "file_name": f"({ym})2020 과목별 월별 여신현황.xlsx", "rows": rows})
    products = raw["inclusive_products"]
    out.append({"dataset": "INCLUSIVE_PRODUCTS", "file_name": "포용금융 대상 상품 운영기준(상품코드).xlsx", "rows": [{"product_code": p["productCode"], "product_name": p["productName"], "product_group": p["productGroup"]} for p in sorted(products, key=lambda x: x["productCode"])]})
    for ym, key in (("202601", "provisionBase"), ("202608", "provisionNow")):
        total, cell = PROVISION_TOTAL[ym]
        rows = [{"ym": ym, "product_code": p["productCode"], "product_name": p["productName"], "provision": p[key], "is_total": False, "src_ref": f"X{100 + i}"} for i, p in enumerate(sorted(products, key=lambda x: x["productCode"]))]
        # 포용금융 외 상품 합계(시뮬레이션) — 합계 행과 상세 합이 맞도록 구성
        others = total - sum(p[key] for p in products)
        rows.append({"ym": ym, "product_code": "OTHERS", "product_name": "그 외 상품 합계", "provision": others, "is_total": False, "src_ref": "X121:X313"})
        rows.append({"ym": ym, "product_code": "TOTAL", "product_name": "합계", "provision": total, "is_total": True, "src_ref": cell})
        out.append({"dataset": "PROVISION_BY_PRODUCT", "file_name": f"({ym})7790_상품별_충당금.xlsx", "rows": rows})
    grades = raw["micro_grades"]
    buckets = {b["bucket"]: b for b in raw["micro_psi_buckets"]}
    base_total = 41_200  # 기준시점 관측건수(시뮬레이션) — 구성비만 PSI 에 사용
    out.append({
        "dataset": "MODEL_MONITORING_GRADE", "file_name": "(20250831)소기업모형_등급별_집계(기준분포).csv",
        "rows": [{"as_of": "2025-08-31", "model_code": "CORP_MICRO", "grade": g["gradeCode"], "grade_seq": i + 1, "obs_count": round(base_total * buckets[g["gradeCode"]]["baseShare"] / 100), "default_count": None, "obs_share": buckets[g["gradeCode"]]["baseShare"]} for i, g in enumerate(grades)],
    })
    out.append({
        "dataset": "MODEL_MONITORING_GRADE", "file_name": "(20260831)소기업모형_등급별_집계.csv",
        "rows": [{"as_of": "2026-08-31", "model_code": "CORP_MICRO", "grade": g["gradeCode"], "grade_seq": i + 1, "obs_count": g["obsCount"], "default_count": g["defaultCount"], "obs_share": g["obsShare"], "ks": g.get("ks"), "sdr_rank": g.get("sdrRank"), "exposure_amt": 48_200 if g["gradeCode"] == "6B" else None} for i, g in enumerate(grades)],
    })
    out.append({
        "dataset": "PD_MASTER_SCALE", "file_name": "PD_Master_Scale_소기업모형.xlsx",
        "rows": [{"model_code": "CORP_MICRO", "grade": g["gradeCode"], "pd_min": PD_MIN_6B if g["gradeCode"] == "6B" else None, "pd_mid": g["pdMid"], "pd_max": g["pdMax"]} for g in grades],
    })
    rows = []
    for key, label, portfolio, values in DR_SERIES:
        for ym, rate in zip(DR_MONTHS, values):
            rows.append({"ym": ym, "segment_key": key, "segment_label": label, "portfolio": portfolio, "default_count": round(rate * 1000), "obs_count": 100_000})
    out.append({"dataset": "DEFAULT_RATE_MONTHLY", "file_name": "월별_부도율_집계(202509-202608).csv", "rows": rows})
    out.append({"dataset": "CAPITAL_CONSTRAINT", "file_name": "2026 하반기 자본·한도 제약.xlsx", "rows": [{"ym": "202608", "item_code": c, "item_name": n, "value": v, "unit": u} for c, n, v, u in CAPITAL_ITEMS]})
    out.append({"dataset": "PEER_BANK_STATS", "file_name": "타행_공시_비교(2026Q2).csv", "rows": [{"ym": "202606", "stat_code": "MID_LOW_CREDIT_SHARE", "stat_name": "개인여신 중 중·저신용자 비중(타행 평균)", "value": 17.2, "issuer": "은행연합회 공시"}]})
    return out


# (item_code, 이름, 값, 단위, 조직, 원천 문서, 정의서 컬럼)
ITEMS = [
    ("LOAN_NIM_ANNUAL_TARGET", "여신 이자마진 연간 승인 목표", 3_300_000, "백만원", None, "경영의사결정 DB/종합기획부 경영계획", "LOAN_NIM_ANNUAL_TARGET_AMT"),
    ("Q3_LOAN_INCOME_ACTUAL", "3분기 여신 수익 현재값(8월까지)", 1_210_000, "백만원", None, "2633 상품부문별 손익계산서 3분기 누계 (Q19: T03 은 2020 으로 표기)", "Q3_LOAN_INCOME_AMT"),
    ("Q3_LOAN_INCOME_TARGET", "3분기 여신 수익 목표", 1_750_000, "백만원", None, "경영의사결정 DB/종합기획부 경영계획", "Q3_LOAN_INCOME_TARGET_AMT"),
    ("HH_LOAN_BAL_LIMIT", "가계여신 잔액 관리 상한", 100_000_000, "백만원", None, "경영의사결정 DB/종합기획부 경영계획", "HH_LOAN_BAL_LIMIT_AMT"),
    ("GRADE_5C_PLUS_RT", "5C 이상 차주 비중", 61.4, "%", None, "2025_일반기업모형 모니터링 보고서_F", "GRADE_5C_PLUS_BORROWER_RT"),
    ("GRADE_5C_PLUS_TARGET", "5C 이상 차주 비중 목표(62%대 유지)", 62.0, "%", None, "2025_일반기업모형 모니터링 보고서_F", "GRADE_5C_PLUS_TARGET_RT"),
    ("D300_CORP_NEW_TARGET", "수도권지역본부 기업여신 신규취급 목표", 1_240_000, "백만원", "D300", "경영의사결정 DB/경영계획", "CAPITAL_CORP_NEW_LOAN_TARGET_AMT"),
    ("D300_CORP_NEW_ACTUAL", "수도권지역본부 기업여신 신규취급 실적", 780_000, "백만원", "D300", "지역본부 신규취급 집계 (Q18: 정의서 원천 7790 재확인)", "CAPITAL_CORP_NEW_LOAN_CURRENT_AMT"),
    ("D500_CORP_NEW_TARGET", "충북지역본부 기업여신 신규취급 목표", 620_000, "백만원", "D500", "경영의사결정 DB/경영계획", "CHUNGBUK_CORP_NEW_LOAN_TARGET_AMT"),
    ("D500_CORP_NEW_ACTUAL", "충북지역본부 기업여신 신규취급 실적", 410_000, "백만원", "D500", "지역본부 신규취급 집계 (Q18)", "CHUNGBUK_CORP_NEW_LOAN_CURRENT_AMT"),
    ("D300_HH_NEW_LIMIT", "수도권지역본부 가계여신 월 신규취급 한도", 240_000, "백만원", "D300", "경영의사결정 DB/경영계획", "CAPITAL_HH_NEW_LOAN_LIMIT_AMT"),
    ("D300_HH_NEW_ACTUAL", "수도권지역본부 가계여신 8월 신규취급", 228_600, "백만원", "D300", "지역본부 신규취급 집계 (Q18)", "CAPITAL_HH_NEW_LOAN_CURRENT_AMT"),
    ("INCLUSIVE_SUPPLY_PY", "포용금융(중·저신용) 공급 전년 실적", 2_950_000, "백만원", None, "2026년 생산적·포용적 금융 부문 성과평가 방안 기준 실적 (Q15 추천안 입력)", "INCLUSIVE_FIN_SUPPLY_PROPOSAL_AMT"),
]


def kpi_version() -> dict[str, Any]:
    return {
        "dataset": K,
        "file_name": "(202608)종기부_경영계획KPI(컬럼정의서v2_결정반영).xlsx",
        "rows": [{"ym": "202608", "item_code": c, "item_name": n, "value": v, "unit": u, "org_code": o, "source_doc": s, "contract_column": cc} for c, n, v, u, o, s, cc in ITEMS],
    }


# ═════════════════════════ Phase I — 원천이 없던 화면 수치의 시나리오 자료 ═════════════════════════
# 지역본부 가이드 이행률(영업점 전파 목표 3번째 — 포용금융 초기 연체 점검)
KPI_EXTRA = [
    ("D300_INC_DLQ_CHECK_RT", "수도권지역본부 포용금융 초기 연체 점검 이행률", 84.0, "%", "D300", "지역본부 월간 점검 보고(포용금융 취급 후 3·6개월 연체 점검)", "CAPITAL_INC_DLQ_CHECK_RT"),
    ("D300_INC_DLQ_CHECK_TARGET", "수도권지역본부 포용금융 초기 연체 점검 목표", 100.0, "%", "D300", "포용금융 확대에 따른 신용리스크 중점관리방안", "CAPITAL_INC_DLQ_CHECK_TARGET_RT"),
]

GRADES16 = ["1", "2A", "2B", "3A", "3B", "4A", "4B", "5A", "5B", "5C", "6A", "6B", "6C", "7A", "7B", "8"]
# 모형 — (코드, 등급, 관측(비교) · 관측(기준), 평균 부도율 %, 목표 AR %, 목표 PSI, 전기 AR 배율)
MODEL_SPECS = [
    ("CORP_LARGE", GRADES16[0:12], 3_240, 3_180, 0.45, 62.31, 0.024),
    ("CORP_MID", GRADES16[1:13], 8_460, 8_220, 0.95, 58.74, 0.038),
    ("CORP_SMALL", GRADES16[2:14], 21_640, 20_980, 1.85, 54.18, 0.061),
    ("RETAIL_AS", [str(i) for i in range(1, 11)], 182_400, 176_900, 6.40, 35.52, 0.031),
    ("RETAIL_BS", [str(i) for i in range(1, 11)], 1_246_000, 1_210_000, 0.62, 83.84, 0.012),
]


def _shares(n: int, mu: float, sd: float) -> list[float]:
    import math

    w = [math.exp(-((k - mu) ** 2) / (2 * sd * sd)) for k in range(n)]
    s = sum(w)
    return [x / s for x in w]


def _obs(shares: list[float], total: int) -> list[int]:
    out = [max(3, round(total * s)) for s in shares]
    out[len(out) // 2] += total - sum(out)
    return out


def _defaults(obs: list[int], b: float, avg_dr: float) -> list[int]:
    import math

    mid = (len(obs) - 1) / 2
    raw = [math.exp(b * (k - mid)) for k in range(len(obs))]
    c = avg_dr / 100 * sum(obs) / sum(o * r for o, r in zip(obs, raw))
    return [min(o - 1, max(0, round(o * min(0.65, c * r)))) for o, r in zip(obs, raw)]


def _ar(defaults: list[int], obs: list[int]) -> float:
    from nhdip.calc.formulas import f_auroc

    return (2 * float(f_auroc(defaults, obs)) - 1) * 100


def _bisect(fn, lo: float, hi: float, target: float, it: int = 60) -> float:
    for _ in range(it):
        m = (lo + hi) / 2
        if fn(m) < target:
            lo = m
        else:
            hi = m
    return (lo + hi) / 2


def _psi(base: list[float], cur: list[float]) -> float:
    from nhdip.calc.formulas import f_psi

    r = f_psi(base, cur)
    return float(r["value"] if isinstance(r, dict) else r)


MODEL_ROWS_JSON = os.path.join(HERE, "model_rows.json")


def model_rows() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(기준시점 2025-08-31 행, 비교시점 2026-08-31 행) — 보정 결과를 고정한 `model_rows.json` 을 읽는다.
    보정(지수 함수 · 이분법 → 반올림)은 부동소수 수학 라이브러리 차이로 운영체제마다 마지막 자리가 달라 건수가 1 바뀔 수 있다
    (CI 리눅스에서 저장소 사본과 어긋남을 확인). 값을 바꾸려면 `calibrate_model_rows()` 로 다시 만들어 JSON 을 고친다."""
    with open(MODEL_ROWS_JSON, encoding="utf-8") as fh:
        d = json.load(fh)
    return d["base"], d["cur"]


def calibrate_model_rows() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """소기업 모형(기존 시나리오) + 5개 모형(목표 AR · PSI 에 맞춘 결정적 생성) — `model_rows.json` 을 다시 만들 때만 쓴다."""
    raw = _raw()
    grades = raw["micro_grades"]
    buckets = {b["bucket"]: b for b in raw["micro_psi_buckets"]}
    base_total = 41_200
    base = [{"as_of": "2025-08-31", "model_code": "CORP_MICRO", "grade": g["gradeCode"], "grade_seq": i + 1, "obs_count": round(base_total * buckets[g["gradeCode"]]["baseShare"] / 100), "default_count": None, "obs_share": buckets[g["gradeCode"]]["baseShare"]} for i, g in enumerate(grades)]
    cur = [{"as_of": "2026-08-31", "model_code": "CORP_MICRO", "grade": g["gradeCode"], "grade_seq": i + 1, "obs_count": g["obsCount"], "default_count": g["defaultCount"], "obs_share": g["obsShare"], "ks": g.get("ks"), "sdr_rank": g.get("sdrRank"), "exposure_amt": 48_200 if g["gradeCode"] == "6B" else None} for i, g in enumerate(grades)]
    for code, labels, n_now, n_base, dr, ar, psi in MODEL_SPECS:
        G = len(labels)
        mu, sd = G * 0.47, G * 0.21
        s_now = _shares(G, mu, sd)
        o_now = _obs(s_now, n_now)
        b_now = _bisect(lambda b: _ar(_defaults(o_now, b, dr), o_now), 0.01, 3.0, ar)
        d_now = _defaults(o_now, b_now, dr)
        share_now = [round(o * 100 / sum(o_now), 2) for o in o_now]

        def psi_for(delta: float) -> float:
            sb = _shares(G, mu - delta, sd)
            ob = _obs(sb, n_base)
            return _psi([round(o * 100 / sum(ob), 2) for o in ob], share_now)

        delta = _bisect(psi_for, 0.0, G / 3, psi)
        o_base = _obs(_shares(G, mu - delta, sd), n_base)
        b_base = _bisect(lambda b: _ar(_defaults(o_base, b, dr * 0.92), o_base), 0.01, 3.0, ar * 1.035)  # 전기: 변별력이 조금 높았다
        d_base = _defaults(o_base, b_base, dr * 0.92)
        for k, g in enumerate(labels):
            base.append({"as_of": "2025-08-31", "model_code": code, "grade": g, "grade_seq": k + 1, "obs_count": o_base[k], "default_count": d_base[k], "obs_share": round(o_base[k] * 100 / sum(o_base), 2)})
            cur.append({"as_of": "2026-08-31", "model_code": code, "grade": g, "grade_seq": k + 1, "obs_count": o_now[k], "default_count": d_now[k], "obs_share": share_now[k]})
    return base, cur


# 소매여신 Pool 월별 집계 — (건수, 금액 백만원, 평균 CB 등급, 신규취급 누계 백만원) · 202508 · 202601 · 202608
POOL_SUMMARY = {
    "202608": {
        "P01": (210_000, 14_200_000, 2.7, 1_820_000), "P02": (120_000, 7_900_000, 4.6, 960_000), "P03": (160_000, 6_300_000, 4.2, 1_240_000),
        "P04": (380_000, 2_950_000, 3.3, 1_380_000), "P05": (300_000, 1_550_000, 5.9, 720_000), "P06": (140_000, 2_866_300, 8.4, 1_040_000),
        "P07": (96_420, 1_602_000, 7.3, 720_000), "P08": (71_340, 1_098_000, 6.6, 540_000), "P09": (45_720, 720_000, 6.0, 340_000), "P10": (60_000, 600_000, 5.4, 210_000),
    },
    "202601": {
        "P01": (206_400, 13_880_000, 2.7, 230_000), "P02": (118_900, 7_760_000, 4.6, 118_000), "P03": (157_200, 6_160_000, 4.2, 152_000),
        "P04": (372_800, 2_880_000, 3.3, 171_000), "P05": (294_100, 1_512_000, 5.9, 88_000), "P06": (136_200, 2_790_400, 8.3, 128_000),
        "P07": (83_360, 1_382_000, 7.2, 92_000), "P08": (61_560, 951_000, 6.5, 69_000), "P09": (39_340, 622_000, 5.9, 43_000), "P10": (59_100, 588_000, 5.4, 26_000),
    },
    "202508": {
        "P01": (198_300, 13_420_000, 2.8, 1_710_000), "P02": (115_700, 7_540_000, 4.7, 900_000), "P03": (151_900, 5_980_000, 4.3, 1_170_000),
        "P04": (361_200, 2_790_000, 3.4, 1_300_000), "P05": (286_800, 1_470_000, 6.0, 680_000), "P06": (131_400, 2_700_100, 8.3, 909_900),
        "P07": (78_900, 1_301_000, 7.2, 630_000), "P08": (58_200, 902_000, 6.5, 472_500), "P09": (36_800, 590_000, 5.9, 297_311), "P10": (57_800, 572_000, 5.5, 198_000),
    },
}


def pool_summary_versions() -> list[dict[str, Any]]:
    return [{"dataset": "RETAIL_POOL_SUMMARY", "file_name": f"TB_JC_PM_C_LA_POOL_{ym}.xlsx",
             "rows": [{"std_ym": ym, "pool_id": p, "exposure_cnt": c, "exposure_amt": a, "avg_cb_grade": g, "new_amt_ytd": n} for p, (c, a, g, n) in vals.items()]}
            for ym, vals in sorted(POOL_SUMMARY.items())]


def versions() -> list[dict[str, Any]]:
    """종합기획부 · 신용리스크 시나리오 전체 — 모형 등급 집계는 6개 모형, KPI 는 가이드 이행률 포함, 소매 Pool 월별 집계 추가."""
    out = [v for v in hq_versions() if v["dataset"] != "MODEL_MONITORING_GRADE"]
    base, cur = model_rows()
    out.append({"dataset": "MODEL_MONITORING_GRADE", "file_name": "(20250831)신용평가모형_등급별_집계(기준분포).csv", "rows": base})
    out.append({"dataset": "MODEL_MONITORING_GRADE", "file_name": "(20260831)신용평가모형_등급별_모니터링_집계.xlsx", "rows": cur})
    kpi = kpi_version()
    kpi["rows"] += [{"ym": "202608", "item_code": c, "item_name": n, "value": v, "unit": u, "org_code": o, "source_doc": s, "contract_column": cc} for c, n, v, u, o, s, cc in KPI_EXTRA]
    return [*out, kpi, *pool_summary_versions()]
