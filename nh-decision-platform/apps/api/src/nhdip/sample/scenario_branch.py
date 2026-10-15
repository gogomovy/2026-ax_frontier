"""시연 시나리오 — 영업점(수원영통지점 001068) 원천 값 (Phase I · Q136, 예전 시드 B.29 시뮬레이션).

결정적 난수(seed 20260831)로 기업 · 소매 익스포저 · 가망기업 · 배점표 · 득점 · 사업부문 잔액을 만든다.
`nhdip.sample.build` 가 실제 업로드 파일로 바꾼다.
"""
from __future__ import annotations

import random
from functools import lru_cache
from typing import Any

# 시연 영업점 시나리오 값(예전 seed.defs_branch 상수 — Phase O 에서 시드를 빼며 시연 자료 생성기로 옮김)
OFFICE = "001068"
ORG_CODE = "001068"  # 조직 코드 = 사무소 코드
YM = "202608"
PERIOD, PREV_PERIOD = "2026H2", "2026H1"
GRADE_LABELS = ["1", "2A", "2B", "3A", "3B", "4A", "4B", "5A", "5B", "5C", "6A", "6B", "6C", "7A", "7B", "8"]

IND = {  # KSIC 11차 (중분류 대표 세분류 코드, 명칭)
    "C10": ("C10712", "떡 · 빵류 제조업"), "C20": ("C20499", "기타 화학제품 제조업"), "C21": ("C21210", "완제 의약품 제조업"), "C25": ("C25929", "기타 금속가공제품 제조업"),
    "C26": ("C26299", "기타 전자부품 제조업"), "C27": ("C27199", "기타 의료용 기기 제조업"), "C29": ("C29199", "기타 일반목적용 기계 제조업"), "C30": ("C30399", "기타 자동차 부품 제조업"),
    "D35": ("D35113", "태양력 발전업"), "F41": ("F41221", "토목 건설업"), "F42": ("F42411", "실내 건축 공사업"), "G46": ("G46510", "컴퓨터 및 주변장치 도매업"),
    "G47": ("G47190", "기타 종합 소매업"), "H49": ("H49301", "일반 화물자동차 운송업"), "H52": ("H52941", "물류 터미널 운영업"), "I56": ("I56111", "한식 일반 음식점업"),
    "J58": ("J58222", "응용 소프트웨어 개발 및 공급업"), "J62": ("J62010", "컴퓨터 프로그래밍 서비스업"), "L68": ("L68112", "비주거용 건물 임대업"), "M70": ("M70113", "기타 공학 연구개발업"),
    "Q86": ("Q86201", "일반 의원"),
}
BANK_IND_W = {k: 1.0 for k in IND} | {"L68": 2.2, "G46": 1.8, "G47": 1.5, "F42": 1.4, "I56": 1.6, "C25": 1.4, "C29": 1.3, "C26": 1.0, "C21": 0.5, "D35": 0.4}
BRANCH_IND_W = {"L68": 22, "I56": 16, "G46": 12, "G47": 10, "F42": 10, "C25": 8, "C29": 3, "H49": 5, "M70": 3, "Q86": 6, "C10": 5}
SIZE_SPEC = {  # 등급 평균 · 표준편차, 잔액 중앙값(억원) · 분산
    "11": (4.0, 1.5, 120.0, 0.55), "12": (6.0, 1.7, 25.0, 0.55), "13": (8.0, 1.9, 6.0, 0.6), "15": (9.8, 2.1, 1.2, 0.7), "16": (10.2, 2.1, 4.0, 0.7),
}
BANK_SIZE_W = {"11": 0.05, "12": 0.15, "13": 0.22, "15": 0.43, "16": 0.15}
BRANCH_SIZE_N = {"11": 1, "12": 8, "13": 22, "15": 112, "16": 37}
NAME_A = ["영통", "광교", "매탄", "망포", "원천", "신동", "이의", "하동", "태장", "권선", "세류", "인계", "한빛", "대성", "우성", "태광", "동양", "삼정", "신우", "세진", "금강", "청솔", "푸른", "새솔", "늘봄"]
NAME_B = ["정밀", "산업", "테크", "식품", "물산", "유통", "건설", "전자", "기계", "화학", "메디칼", "푸드", "로지스", "엔지니어링", "상사", "인테리어", "개발", "에프앤비"]
POOLS = [
    # pool, 이름, 상품군, 저신용, 서민금융 인정, 용도코드, PD, LGD, 전행 건 비중, 지점 건 비중, 중앙값(백만원), 상한(백만원), 연체확률
    ("P01", "주택담보대출(우량)", "주택담보", False, False, "", 0.25, 20, 0.14, 0.20, 180, None, 0.003),
    ("P02", "주택담보대출(일반)", "주택담보", False, False, "", 0.60, 25, 0.10, 0.12, 140, None, 0.006),
    ("P03", "전세자금대출", "전세", False, False, "", 0.40, 15, 0.12, 0.16, 160, None, 0.004),
    ("P04", "신용대출(우량 1~3등급)", "신용", False, False, "", 0.50, 45, 0.18, 0.20, 45, None, 0.005),
    ("P05", "신용대출(일반 4~6등급)", "신용", False, False, "", 1.80, 50, 0.16, 0.15, 30, None, 0.016),
    ("P06", "신용대출(저신용 7~10등급)", "신용", True, False, "", 6.50, 55, 0.07, 0.05, 15, None, 0.055),
    ("P07", "NH새희망홀씨대출", "서민금융", True, True, "1031|1032", 7.80, 60, 0.09, 0.03, 22, 35, 0.068),
    ("P08", "햇살론(보증부)", "서민금융", True, False, "1041", 3.00, 15, 0.06, 0.03, 14, 35, 0.032),
    ("P09", "사잇돌(보증부)", "서민금융", True, False, "1051", 4.00, 30, 0.04, 0.02, 16, 30, 0.038),
    ("P10", "기타 소매", "기타", False, False, "", 1.00, 40, 0.04, 0.04, 20, None, 0.012),
]
POOL_CB = {"P01": (1, 3), "P02": (3, 5), "P03": (2, 5), "P04": (1, 3), "P05": (4, 6), "P06": (7, 10), "P07": (6, 10), "P08": (6, 10), "P09": (5, 8), "P10": (3, 7)}

# 가망기업 — 수원시 후보(선정 · 제외 사유가 모두 나오도록 구성) + 타 지역
PROSPECTS_SUWON = [
    # 기업명, 규모, NICS, 예상재무등급, 업종, 시군구, 자산, 부채, 매출, 영업이익, 순이익, 설립
    ("신동에너지(주)", "대기업", "11", "2A", "D35", "수원시 영통구", 820_400, 342_100, 412_800, 58_300, 41_200, "2009-04-13"),
    ("광교바이오팜(주)", "중견기업", "12", "2B", "C21", "수원시 영통구", 182_400, 84_600, 141_300, 18_900, 13_700, "2011-09-02"),
    ("원천소프트(주)", "중소기업", "13", "2B", "J58", "수원시 영통구", 41_200, 15_400, 38_600, 6_100, 4_800, "2014-03-21"),
    ("영통세미텍(주)", "중견기업", "12", "3A", "C26", "수원시 영통구", 246_800, 129_200, 198_400, 21_600, 15_300, "2007-11-05"),
    ("매탄메디칼(주)", "중소기업", "13", "3A", "C27", "수원시 영통구", 68_300, 33_100, 57_200, 7_400, 5_200, "2012-06-18"),
    ("수원정밀화학(주)", "중견기업", "12", "3B", "C20", "수원시 권선구", 155_600, 90_800, 133_900, 11_200, 7_900, "2003-02-27"),
    ("망포푸드(주)", "중소기업", "13", "3B", "C10", "수원시 영통구", 52_900, 28_900, 61_400, 4_300, 3_100, "2015-08-11"),
    ("이의디스플레이(주)", "중소기업", "13", "3B", "C26", "수원시 영통구", 47_700, 26_100, 44_200, 3_900, 2_700, "2016-01-25"),
    ("광교로지스(주)", "중견기업", "12", "4A", "H52", "수원시 영통구", 133_500, 81_300, 96_800, 6_900, 4_600, "2010-05-30"),
    ("영통상사(주)", "중견기업", "12", "2B", "G46", "수원시 영통구", 118_900, 52_400, 287_300, 9_800, 7_200, "2005-10-14"),
    ("수원건설산업(주)", "중견기업", "12", "3A", "F41", "수원시 팔달구", 208_200, 153_400, 176_500, 12_300, 8_100, "2001-07-09"),
    ("동탄테크(주)", "중견기업", "12", "2B", "C29", "화성시", 164_300, 71_800, 152_600, 16_400, 11_900, "2008-03-17"),
]
OTHER_REGIONS = [("서울", "강남구"), ("서울", "영등포구"), ("인천", "연수구"), ("경기", "성남시 분당구"), ("경기", "용인시 기흥구"), ("경기", "안양시 동안구"), ("대전", "유성구"), ("충북", "청주시 흥덕구"), ("부산", "해운대구"), ("경기", "평택시")]


def _suffix(i: int) -> str:
    return f"{i:06d}"


@lru_cache(maxsize=1)
def _generate() -> dict[str, list[dict[str, Any]]]:
    rng = random.Random(20260831)
    offices = [OFFICE] + [f"00{n:04d}" for n in rng.sample(range(1001, 1999), 39) if f"00{n:04d}" != OFFICE][:39]

    def pick(weights: dict[str, float]) -> str:
        keys = list(weights)
        return rng.choices(keys, weights=[weights[k] for k in keys])[0]

    def corp_row(i: int, office: str, size: str, ind_w: dict[str, float], _named: bool) -> dict[str, Any]:
        mu, sd, med, s = SIZE_SPEC[size]
        seq = max(1, min(16, round(rng.gauss(mu, sd))))
        amt_eok = med * pow(2.718281828, rng.gauss(0, s))
        if size == "16":
            amt_eok += 10.0  # 기업형소호 = 거액(10억 이상) 개인사업자
        ind = pick(ind_w)
        pd = 0.0004 * (1.52 ** (seq - 1))
        nm = f"{rng.choice(NAME_A)}{rng.choice(NAME_B)}"
        if size != "16":
            nm = f"(주){nm}" if rng.random() < 0.5 else f"{nm}(주)"
        return {"std_ym": YM, "brwr_no": f"B{office[-4:]}{_suffix(i)}", "brwr_nm": nm, "SUVMN_BRC": office, "Ls_nics_GRDC": seq,
                "ln_bac": int(round(amt_eok * 1e8, -4)), "onlycard": 0, "STD_INDS_CFC": IND[ind][0], "crdevl_pttp_dsc_f": size, "default": 1 if rng.random() < pd else 0}

    corp: list[dict[str, Any]] = []
    i = 0
    for size, n in BRANCH_SIZE_N.items():
        for _ in range(n):
            i += 1
            corp.append(corp_row(i, OFFICE, size, BRANCH_IND_W, True))
    for _ in range(4):  # 카드 전용 차주 (분석 제외)
        i += 1
        corp.append({**corp_row(i, OFFICE, "15", BRANCH_IND_W, True), "onlycard": 1, "ln_bac": int(round(rng.uniform(2, 30) * 1e6, -4))})
    for g in (0, 99, 0):  # 등급 체계 밖 (분석 제외)
        i += 1
        corp.append({**corp_row(i, OFFICE, "15", BRANCH_IND_W, True), "Ls_nics_GRDC": g})
    for office in offices[1:]:
        for _ in range(rng.randint(78, 118)):
            i += 1
            r = corp_row(i, office, pick(BANK_SIZE_W), BANK_IND_W, False)
            u = rng.random()
            if u < 0.03:
                r["onlycard"], r["ln_bac"] = 1, int(round(rng.uniform(2, 30) * 1e6, -4))
            elif u < 0.05:
                r["Ls_nics_GRDC"] = rng.choice([0, 99])
            corp.append(r)

    retail: list[dict[str, Any]] = []
    j = 0
    bank_mix = {p[0]: p[8] for p in POOLS}
    branch_mix = {p[0]: p[9] for p in POOLS}
    spec = {p[0]: p for p in POOLS}

    def retail_row(office: str, pool: str) -> dict[str, Any]:
        nonlocal j
        j += 1
        p = spec[pool]
        amt = p[10] * pow(2.718281828, rng.gauss(0, 0.45))
        if p[11]:
            amt = min(amt, float(p[11]))
        lo, hi = POOL_CB[pool]
        return {"std_ym": YM, "brwr_id": f"R{office[-4:]}{j:06d}", "office_cd": office, "pool_id": pool, "exp_amt": int(round(amt * 1e6, -4)), "cb_grade": rng.randint(lo, hi), "dlq_yn": 1 if rng.random() < p[12] else 0}

    for _ in range(260):
        retail.append(retail_row(OFFICE, pick(branch_mix)))
    for office in offices[1:]:
        for _ in range(rng.randint(120, 175)):
            retail.append(retail_row(office, pick(bank_mix)))

    prospects: list[dict[str, Any]] = []
    for k, (nm, scale, model, grade, ind, sig, asset, liab, sales, op, net, est) in enumerate(PROSPECTS_SUWON):
        prospects.append({"biz_no": f"124-8{k % 7 + 1}-{30117 + k * 173:05d}", "corp_no": f"1358{k:02d}-0{rng.randint(100000, 999999)}", "corp_nm": nm, "corp_scale": scale, "estb_dt": est, "nics_model": model, "exp_grade": grade,
                          "ind_cd": IND[ind][0], "ind_nm": IND[ind][1], "region": "경기", "sigungu": sig, "tot_asset": asset, "tot_liab": liab, "tot_equity": asset - liab, "sales": sales, "op_income": op, "net_income": net})
    for k in range(60):
        region, sig = OTHER_REGIONS[k % len(OTHER_REGIONS)]
        model = rng.choice(["11", "12", "12", "13", "13"])
        asset = int(rng.uniform(40_000, 600_000) * (3 if model == "11" else 1))
        liab = int(asset * rng.uniform(0.25, 0.7))
        sales = int(asset * rng.uniform(0.6, 1.4))
        op = int(sales * rng.uniform(0.04, 0.13))
        ind = rng.choice(list(IND))
        prospects.append({"biz_no": f"{rng.randint(101, 899)}-8{rng.randint(1, 8)}-{rng.randint(10000, 99999):05d}", "corp_no": f"{rng.randint(110111, 285011)}-0{rng.randint(100000, 999999)}",
                          "corp_nm": f"{rng.choice(NAME_A)}{rng.choice(NAME_B)}(주)", "corp_scale": {"11": "대기업", "12": "중견기업", "13": "중소기업"}[model], "estb_dt": f"{rng.randint(1995, 2018)}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}",
                          "nics_model": model, "exp_grade": rng.choice(GRADE_LABELS[1:7]), "ind_cd": IND[ind][0], "ind_nm": IND[ind][1], "region": region, "sigungu": sig,
                          "tot_asset": asset, "tot_liab": liab, "tot_equity": asset - liab, "sales": sales, "op_income": op, "net_income": int(op * 0.74)})
    return {"corp": corp, "retail": retail, "prospects": prospects}


# 업적평가 배점표 (리테일) — 시뮬레이션 가정: 원본 세부기준 PDF 수령 시 배점표 데이터셋만 교체
_H2_CHANGES = {
    "CORE_PRIME": ("신설", "신규 · 증액 유치한 기업여신을 차주 신용등급 구간별 가중치(1~3B 150% … 7A 이하 50%)로 환산해 실적 인정 — 우량기업여신 유치 우대", "84~91"),
    "CORE_CORP_LOAN": ("변경", "배점 100 → 60 (40점을 우량기업여신으로 이관)", "84"),
    "INCL_SEOMIN": ("신설", "NH새희망홀씨대출(용도코드 1031 · 1032) 신규 유치 건수에 배점 부여, 해당 차주는 건전성평가 중 연체평가에서 제외", "126"),
    "BIZ_STRAT": ("변경", "배점 180 → 160 (20점을 생산적·포용금융으로 이관)", "15"),
    "BIZ_INCL": ("변경", "배점 100 → 120 (서민금융 20점 신설)", "15"),
}
SCHEME = [
    # 단계, 상위, 코드, 이름, 상위코드, 상반기 배점, 하반기 배점
    (1, "CUST", "CUST", "고객KPI", None, 200, 200),
    (2, "CUST", "CUST_BASE", "고객기반 확대", "CUST", 90, 90),
    (2, "CUST", "CUST_DIGITAL", "디지털 고객", "CUST", 60, 60),
    (2, "CUST", "CUST_CS", "고객만족 · 소비자보호", "CUST", 50, 50),
    (1, "BIZ", "BIZ", "사업KPI", None, 500, 500),
    (2, "BIZ", "BIZ_CORE", "핵심사업", "BIZ", 220, 220),
    (3, "BIZ", "CORE_CORP_LOAN", "기업여신 증대", "BIZ_CORE", 100, 60),
    (3, "BIZ", "CORE_PRIME", "우량기업여신", "BIZ_CORE", None, 40),
    (3, "BIZ", "CORE_DEPOSIT", "저원가성 예금", "BIZ_CORE", 120, 120),
    (2, "BIZ", "BIZ_STRAT", "전략사업", "BIZ", 180, 160),
    (2, "BIZ", "BIZ_INCL", "생산적·포용금융", "BIZ", 100, 120),
    (3, "BIZ", "INCL_PROD", "생산적금융", "BIZ_INCL", 60, 60),
    (3, "BIZ", "INCL_INCL", "포용금융", "BIZ_INCL", 40, 40),
    (3, "BIZ", "INCL_SEOMIN", "서민금융", "BIZ_INCL", None, 20),
    (1, "FIN", "FIN", "재무KPI", None, 300, 300),
    (2, "FIN", "FIN_PROFIT", "수익성(총이익)", "FIN", 180, 180),
    (2, "FIN", "FIN_SOUND", "건전성", "FIN", 120, 120),
    (1, "ADJ", "ADJ", "가 · 감점", None, None, None),
    (2, "ADJ", "ADJ_BONUS", "가점", "ADJ", None, None),
    (2, "ADJ", "ADJ_PENALTY", "감점", "ADJ", None, None),
]
# 하반기 진행 중(2026-08-31) 득점 — 시뮬레이션: 2개월 경과 시점의 적당한 수준
SCORES = {
    "CUST_BASE": (58.0, None, None, ""), "CUST_DIGITAL": (41.0, None, None, ""), "CUST_CS": (38.0, None, None, ""),
    "BIZ_CORE": (107.0, None, None, ""), "CORE_CORP_LOAN": (31.0, 4_820, 9_300, "백만원"), "CORE_PRIME": (4.0, 6_000, 60_000, "백만원(가중)"), "CORE_DEPOSIT": (72.0, None, None, ""),
    "BIZ_STRAT": (88.0, None, None, ""),
    "BIZ_INCL": (59.67, None, None, ""), "INCL_PROD": (33.0, None, None, ""), "INCL_INCL": (24.0, None, None, ""), "INCL_SEOMIN": (2.67, 4, 30, "건"),
    "FIN_PROFIT": (118.0, None, None, ""), "FIN_SOUND": (82.0, None, None, ""),
    "ADJ_BONUS": (5.0, None, None, "지역사회 공헌"), "ADJ_PENALTY": (-3.0, None, None, "민원 발생"),
}
BIZ_BALANCE = [("deposit", "수신", 142_060_000_000, "평잔"), ("fx", "외환", 3_840_000_000, "누적 실적"), ("pension", "퇴직연금", 21_030_000_000, "적립금"), ("card", "카드", 5_210_000_000, "누적 이용실적")]


def branch_versions() -> list[dict[str, Any]]:
    g = _generate()
    out: list[dict[str, Any]] = [
        {"dataset": "OBLG_GRD_DEF", "file_name": f"Oblg_grd_def_{YM}.csv", "rows": g["corp"]},
        {"dataset": "CORP_PROSPECT", "file_name": "붙임1) 여신가망 재무우량 기업명세(2026).xlsx", "rows": g["prospects"]},
        {"dataset": "RETAIL_EXPOSURE", "file_name": f"TB_JC_PM_C_LA_{YM}.csv", "rows": g["retail"]},
        {"dataset": "RETAIL_POOL_MASTER", "file_name": "소매여신 상품 Pool 정의.xlsx",
         "rows": [{"pool_id": p[0], "pool_nm": p[1], "product_group": p[2], "low_credit": p[3], "seomin_eval": p[4], "use_cd": p[5], "pd_pct": p[6], "lgd_pct": p[7], "prov_rate_pct": round(p[6] * p[7] / 100, 4)} for p in POOLS]},
        {"dataset": "BRANCH_OFFICE_MASTER", "file_name": "영업점 사무소 마스터.xlsx",
         "rows": [{"office_cd": OFFICE, "office_nm": "수원영통지점", "region": "경기", "sigungu": "수원시", "region_hq": "수도권1지역본부", "org_code": ORG_CODE}]},
    ]
    rows = []
    for period, idx in ((PREV_PERIOD, 5), (PERIOD, 6)):
        for s in SCHEME:
            pts = s[idx]
            if pts is None and s[1] != "ADJ":
                continue  # 해당 반기에 없는 항목
            ch = _H2_CHANGES.get(s[2]) if period == PERIOD else None
            rows.append({"period": period, "level": s[0], "group_cd": s[1], "item_cd": s[2], "item_nm": s[3], "parent_cd": s[4], "max_points": pts,
                         "change_type": ch[0] if ch else "", "change_summary": ch[1] if ch else "", "doc_page": ch[2] if ch else ""})
    out.append({"dataset": "BRANCH_KPI_SCHEME", "file_name": "업적평가 배점표(리테일) 2026 상·하반기.xlsx", "rows": rows})
    lv = {s[2]: (s[0], s[1]) for s in SCHEME}
    out.append({"dataset": "BRANCH_KPI_SCORE", "file_name": f"영업점 업적평가 득점 현황({YM}).xlsx",
                "rows": [{"office_cd": OFFICE, "period": PERIOD, "as_of": "2026-08-31", "level": lv[k][0], "group_cd": lv[k][1], "item_cd": k, "score": v[0], "actual_value": v[1], "target_value": v[2], "unit": v[3] if v[1] is not None else "", "note": v[3] if v[1] is None else ""} for k, v in SCORES.items()]})
    out.append({"dataset": "BRANCH_BIZ_BALANCE", "file_name": f"영업점 사업부문별 잔액({YM}).xlsx",
                "rows": [{"office_cd": OFFICE, "ym": YM, "segment_cd": c, "segment_nm": n, "amount": a, "measure": m} for c, n, a, m in BIZ_BALANCE]})
    return out
