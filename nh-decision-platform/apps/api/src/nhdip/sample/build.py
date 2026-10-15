"""시연 자료 패키지 조립 (Phase I · 설계 §25.2) — 시나리오 값 → 실제 업로드 파일(엑셀 · CSV · PDF) + 목록.

    from nhdip.sample.build import build
    pkg = build()            # 2026.08 기준 (기존 시나리오 값)
    pkg.write("sample-data/202608")
    bad = perturb(pkg)       # 교란 검사용 — 셀마다 다른 비율로 수치만 바꾼 같은 파일들

파일 이름 · 양식은 실무에서 받는 모양(원본 보고서 번호 · 시스템 테이블명 · 공문 붙임)을 따른다.
데이터셋 정의는 미리 없다 — 파일을 올리면 파일 모양에서 정의가 만들어지고, 제품의 기본 업무 구성(seed/business_pack.json)이
지표 산식 · 업무 흐름 · 화면 연결을 자료 이름 · 열 이름으로 그 자료에 잇는다. manifest 의 dataset 값은 시나리오 안의 자료 구분일 뿐 플랫폼 코드가 아니다.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import zlib
from dataclasses import dataclass, field
from typing import Any

from . import excel as X
from .docs import catalog, collect_snippets, pdf, upload_meta
from .scenario_branch import branch_versions
from .scenario_hq import versions as hq_and_risk_versions

SUPPORTED = ("202608",)
GENERATOR = "nhdip.sample.build v1"


@dataclass
class SampleFile:
    name: str
    kind: str  # dataset | document
    content: bytes
    dataset: str | None = None
    origin: str = "bank"
    data_origin: str = "simulated"
    note: str | None = None
    doc: dict[str, Any] | None = None  # 문서: docCode · docClass · title · issuer · publishedAt · meta
    rows: int | None = None

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content).hexdigest()


@dataclass
class Package:
    ym: str
    files: list[SampleFile] = field(default_factory=list)
    variant: str = "base"

    def manifest(self) -> dict[str, Any]:
        items = []
        for f in self.files:
            it: dict[str, Any] = {"name": f.name, "kind": f.kind, "origin": f.origin, "sha256": f.sha256, "bytes": len(f.content)}
            if f.kind == "dataset":
                it.update({"dataset": f.dataset, "dataOrigin": f.data_origin, "rows": f.rows, "note": f.note})
            elif f.kind == "config":
                it.update({"note": f.note})
            else:
                it.update(f.doc or {})
            items.append(it)
        return {"ym": self.ym, "variant": self.variant, "generatedBy": GENERATOR, "notice": X.NOTICE, "files": items}

    def write(self, out_dir: str) -> list[str]:
        os.makedirs(out_dir, exist_ok=True)
        paths = []
        for f in self.files:
            sub = os.path.join(out_dir, {"dataset": "datasets", "config": "업무구성"}.get(f.kind, "documents"))
            os.makedirs(sub, exist_ok=True)
            p = os.path.join(sub, f.name)
            with open(p, "wb") as fh:
                fh.write(f.content)
            paths.append(p)
        with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8", newline="\n") as fh:
            json.dump(self.manifest(), fh, ensure_ascii=False, indent=1)
            fh.write("\n")
        return paths


# 업로드 순서 — 마스터(다른 자료가 참조) → 사실 자료 → 문서
ORDER = ["INCLUSIVE_PRODUCTS", "PD_MASTER_SCALE", "RETAIL_POOL_MASTER", "BRANCH_OFFICE_MASTER", "BRANCH_KPI_SCHEME", "CORP_PROSPECT",
         "PL_PRODUCT_SEGMENT", "LOAN_BALANCE_MONTHLY", "PROVISION_BY_PRODUCT", "MODEL_MONITORING_GRADE", "DEFAULT_RATE_MONTHLY", "CAPITAL_CONSTRAINT",
         "PEER_BANK_STATS", "HQ_PLAN_KPI", "RETAIL_POOL_SUMMARY", "OBLG_GRD_DEF", "RETAIL_EXPOSURE", "BRANCH_KPI_SCORE", "BRANCH_BIZ_BALANCE"]
EXT = {"PEER_BANK_STATS"}


def _ym_dot(ym: str) -> str:
    return f"{ym[:4]}.{ym[4:6]}"


def _shift(ym: str, months: int) -> str:
    y, m = int(ym[:4]), int(ym[4:6])
    i = y * 12 + (m - 1) + months
    return f"{i // 12}{i % 12 + 1:02d}"


def _noise(key: str, amp: float) -> float:
    """결정적 작은 흔들림 (−amp ~ +amp)."""
    return ((zlib.crc32(key.encode()) % 2001) / 1000 - 1) * amp


# ═════════════════════════ 2633 손익 ═════════════════════════
def _pl_files(versions: list[dict[str, Any]]) -> list[SampleFile]:
    by = {v["rows"][0]["ym"]: {r["item_code"]: r["amount"] for r in v["rows"]} for v in versions}
    latest = max(by)
    out = []
    for ym in sorted(by):
        cur = dict(by[ym])
        ref = by[latest]
        # 원본 보고서에는 모든 연도에 같은 과목이 있다 — 시나리오에 없는 과목은 최근 연도 비중으로 채운다
        for code, base in (("HOUSE_INTEREST", "HH_INTEREST"), ("HH_ETC_INTEREST", "HH_INTEREST"), ("PUBLIC_INTEREST", "CORP_INTEREST")):
            if code not in cur:
                cur[code] = round(ref[code] * cur[base] / ref[base])
        prev = by.get(_shift(ym, -12))
        T, N, C, H, HO, HE, PU = (cur[k] for k in ("TOTAL_REVENUE", "LOAN_NIM", "CORP_INTEREST", "HH_INTEREST", "HOUSE_INTEREST", "HH_ETC_INTEREST", "PUBLIC_INTEREST"))
        won = C + H + PU
        loan_int = round(won * 1.06)
        sec, dep = round(T * 0.11), round(T * 0.02)
        interest = loan_int + sec + dep
        non = T - interest
        fee, fx = round(non * 0.38), round(non * 0.12)

        def pv(code: str) -> float | None:
            return None if prev is None else prev.get(code)

        items = [
            ("총수익", 0, T, pv("TOTAL_REVENUE")),
            ("이자수익", 1, interest, None),
            ("대출금이자수익", 2, loan_int, None),
            ("원화대출금이자수익", 3, won, None),
            ("기업자금대출금이자", 4, C, pv("CORP_INTEREST")),
            ("가계자금대출금이자", 4, H, pv("HH_INTEREST")),
            ("주택자금대출이자", 5, HO, None),
            ("기타가계자금대출이자", 5, HE, None),
            ("공공자금대출이자", 4, PU, None),
            ("외화대출금이자수익", 3, loan_int - won, None),
            ("유가증권이자수익", 2, sec, None),
            ("예치금이자수익", 2, dep, None),
            ("비이자수익", 1, non, None),
            ("수수료수익", 2, fee, None),
            ("외환매매익", 2, fx, None),
            ("기타영업수익", 2, non - fee - fx, None),
            ("여신(일반)부문 이자마진 수익", 0, N, pv("LOAN_NIM")),
            ("수신부문 이자마진 수익", 0, round(T * 0.21), None),
        ]
        out.append(SampleFile(f"({ym})2633_상품부문별손익계산서.xlsx", "dataset", X.report_2633(ym, items), "PL_PRODUCT_SEGMENT", note=f"2633 원본 양식 · {_ym_dot(ym)} 누계", rows=7))
    return out


# ═════════════════════════ 2020 월별 여신 ═════════════════════════
# 2026년 월별 잔액(조원) — 기업 · 가계 (여신 종합 화면의 월별 추이와 같은 시나리오)
MONTHLY_2026 = {
    "CORP": [111.24, 111.86, 112.54, 113.08, 113.62, 114.26, 114.82, 115.34],
    "HH": [93.88, 94.52, 95.24, 96.18, 97.02, 97.86, 98.54, 99.24],
}


def _lb_files(versions: list[dict[str, Any]]) -> list[SampleFile]:
    by = {v["rows"][0]["ym"]: {r["account_code"]: r["balance"] for r in v["rows"]} for v in versions}
    years = sorted(by)  # 202408 · 202508 · 202608
    latest = by[years[-1]]
    out = []
    for i, ym in enumerate(years):
        # 지난 연도는 연간 보고서(1~12월), 올해는 기준월까지 — 9~12월은 다음 해 같은 달 잔액으로 이어지게
        y, anchor_m = int(ym[:4]), int(ym[4:])
        nxt = by.get(years[i + 1]) if i + 1 < len(years) else None
        months = 12 if nxt else anchor_m
        aug = dict(by[ym])
        for code, base in (("HOUSE", "HH"), ("HH_ETC", "HH"), ("PUBLIC", "CORP")):
            if code not in aug:
                aug[code] = round(latest[code] * aug[base] / latest[base])
        prev_aug = by[years[i - 1]] if i else {k: v * by[years[0]][k] / by[years[1]][k] for k, v in by[years[0]].items() if k in by[years[1]]}

        def series(code: str) -> list[float]:
            if y == 2026 and code in MONTHLY_2026 and len(MONTHLY_2026[code]) == months:
                k = aug[code] / (MONTHLY_2026[code][-1] * 1_000_000)  # 8월 = 시나리오(교란 패키지면 바뀐 값) — 월별 모양은 그대로
                return [round(v * 1_000_000 * k) for v in MONTHLY_2026[code][:-1]] + [aug[code]]
            base_code = code if code in prev_aug else ("HH" if code in ("HOUSE", "HH_ETC") else "CORP")
            g = aug[base_code] / prev_aug[base_code]
            g_next = (nxt.get(base_code) or aug[base_code]) / aug[base_code] if nxt else g
            vals = []
            for m in range(1, months + 1):
                k = g ** ((m - anchor_m) / 12) if m <= anchor_m else g_next ** ((m - anchor_m) / 12)
                v = aug[code] * k * (1 + (0 if m == anchor_m else _noise(f"{ym}{code}{m}", 0.002)))
                vals.append(round(v))
            return vals

        corp, hh, house, etc, pub = (series(c) for c in ("CORP", "HH", "HOUSE", "HH_ETC", "PUBLIC"))
        work = [round(v * 0.63) for v in corp]
        general = [h - a - b for h, a, b in zip(hh, house, etc)]
        loans = [a + b + c for a, b, c in zip(corp, hh, pub)]
        guar = [round(v * 0.021) for v in loans]
        tree = [
            ("대출금", 0, loans),
            ("기업자금대출금", 1, corp),
            ("운전자금대출금", 2, work),
            ("시설자금대출금", 2, [c - w for c, w in zip(corp, work)]),
            ("가계자금대출금", 1, hh),
            ("주택자금대출", 2, house),
            ("기타가계자금대출", 2, etc),
            ("가계일반자금대출", 2, general),
            ("공공및기타자금대출금", 1, pub),
            ("지급보증", 0, guar),
            ("종합계", 0, [a + b for a, b in zip(loans, guar)]),
        ]
        base_date = f"{y}-{months:02d}-{X._last_day(y, months):02d}"
        out.append(SampleFile(f"({y}{months:02d})2020 과목별 월별 여신현황.xlsx", "dataset", X.report_2020(y, months, tree, base_date=base_date), "LOAN_BALANCE_MONTHLY", note=f"2020 원본 양식 · {y}년 1~{months}월", rows=len(tree) * months))
    return out


# ═════════════════════════ 7790 충당금 ═════════════════════════
OTHER_PRODUCTS = [
    ("2001101010001", "NH주택담보대출(변동)"), ("2001101010002", "NH주택담보대출(혼합)"), ("2001101020001", "NH전세자금대출"), ("2001101020003", "NH청년전세대출"),
    ("2001102010001", "NH직장인신용대출"), ("2001102010004", "NH공무원신용대출"), ("2001102030001", "NH마이너스통장"), ("2001103010001", "농업인정책자금대출"),
    ("2001103010002", "농축산경영자금대출"), ("2001103020001", "농업시설자금대출"), ("2001104010001", "기업운전자금대출"), ("2001104010002", "기업시설자금대출"),
    ("2001104020001", "중소기업정책자금대출"), ("2001104020003", "소상공인정책자금대출"), ("2001104030001", "외감기업일반대출"), ("2001104030002", "대기업일반대출"),
    ("2001105010001", "NH기업카드론"), ("2001105020001", "개인사업자운전자금"), ("2001105020002", "개인사업자시설자금"), ("2001106010001", "예적금담보대출"),
    ("2001106020001", "유가증권담보대출"), ("2001106030001", "NH자동차대출"), ("2001107010001", "공공기관대출"), ("2001107020001", "지방자치단체대출"),
    ("2001108010001", "외화대출(운전)"), ("2001108010002", "외화대출(시설)"), ("2001109010001", "PF대출(일반)"), ("2001109020001", "부동산임대업대출"),
]


def _prov_files(versions: list[dict[str, Any]]) -> list[SampleFile]:
    rng = random.Random(7790)
    weights = [rng.uniform(0.4, 3.0) for _ in OTHER_PRODUCTS]
    out = []
    for v in versions:
        ym = v["rows"][0]["ym"]
        total = next(r["provision"] for r in v["rows"] if r["is_total"])
        prods = [{"code": r["product_code"], "name": r["product_name"], "provision": r["provision"]} for r in v["rows"] if not r["is_total"] and r["product_code"] != "OTHERS"]
        others = next(r["provision"] for r in v["rows"] if r["product_code"] == "OTHERS")
        # 그 외 상품 합계를 실제 상품 행으로 나눈다 — 상세 합계 = 합계 행
        shares = [w / sum(weights) for w in weights]
        amounts = [round(others * s) for s in shares]
        amounts[-1] += others - sum(amounts)
        prods += [{"code": c, "name": n, "provision": a} for (c, n), a in zip(OTHER_PRODUCTS, amounts)]
        prods.sort(key=lambda p: p["code"])
        for p in prods:
            p["borrowers"] = max(3, int(p["provision"] / 7.5) + int(_noise(ym + p["code"], 40)))
        out.append(SampleFile(f"({ym})7790_상품별_충당금.xlsx", "dataset", X.report_7790(ym, prods, total), "PROVISION_BY_PRODUCT", note=f"7790 원본 양식 · {_ym_dot(ym)}", rows=len(prods) + 1))
    return out


# ═════════════════════════ 실무형 표 ═════════════════════════
C = X.Col


def _tidy_files(versions: list[dict[str, Any]]) -> list[SampleFile]:
    out: list[SampleFile] = []
    for v in versions:
        ds, name, rows = v["dataset"], v["file_name"], v["rows"]
        f: SampleFile | None = None
        if ds == "INCLUSIVE_PRODUCTS":
            cols = [C("상품코드", "product_code"), C("상품명", "product_name", width=34), C("상품군", "product_group")]
            content = X.table("포용금융 대상 상품 운영기준 — 대상 상품코드", ["근거 : 포용금융 대상 상품 운영기준(여신정책협의회 의결) · 대상 상품코드 일람", f"대상 : {len(rows)}건 · 작성 : 신용리스크관리부"], cols, rows, sheet="대상상품")
            f = SampleFile(name, "dataset", content, ds, note="마스터 · 대상 상품코드")
        elif ds == "MODEL_MONITORING_GRADE":
            as_of = rows[0]["as_of"]
            cols = [C("기준일", "as_of", "date"), C("모형코드", "model_code"), C("등급", "grade"), C("등급순서", "grade_seq", "int"), C("관측건수", "obs_count", "int"), C("부도건수", "default_count", "int"),
                    C("구성비(%)", "obs_share", "num2"), C("K-S(등급)", "ks", "num1"), C("SDR 순위", "sdr_rank", "int"), C("익스포저(억원)", "exposure_amt", "num0")]
            if name.endswith(".csv"):
                f = SampleFile(name, "dataset", X.csv_bytes(cols, rows), ds, note=f"모형 등급별 집계 · 기준분포 {as_of}")
            else:
                content = X.table("신용평가모형 등급별 모니터링 집계", [f"기준일 : {as_of} · 관찰기간 : 1년 · 작성 : 신용리스크관리부 모형검증팀", "구성비 = 등급 관측건수 ÷ 전체 관측건수 × 100"], cols, rows, sheet="등급별")
                f = SampleFile(name, "dataset", content, ds, note=f"모형 등급별 집계 · {as_of}")
        elif ds == "PD_MASTER_SCALE":
            cols = [C("모형코드", "model_code"), C("등급", "grade"), C("최소(%)", "pd_min", "num3"), C("대표값(%)", "pd_mid", "num3"), C("최대(%)", "pd_max", "num3")]
            content = X.table("PD Master Scale — 등급별 예측부도율", ["모형 : 일반기업 소기업 모형(CORP_MICRO) · 적용 : 2026년 · 단위 : %"], cols, rows, sheet="PD")
            f = SampleFile(name, "dataset", content, ds, note="마스터 · 예측부도율")
        elif ds == "DEFAULT_RATE_MONTHLY":
            cols = [C("기준년월", "ym"), C("구분코드", "segment_key"), C("구분명", "segment_label"), C("포트폴리오", "portfolio"), C("부도건수", "default_count", "int"), C("관측건수", "obs_count", "int")]
            f = SampleFile(name, "dataset", X.csv_bytes(cols, rows), ds, note="월별 부도율 집계(시스템 추출 CSV)")
        elif ds == "CAPITAL_CONSTRAINT":
            cols = [C("기준년월", "ym"), C("항목코드", "item_code"), C("항목명", "item_name", width=34), C("값", "value", "num2"), C("단위", "unit")]
            content = X.table("2026년 하반기 자본 · 한도 제약", ["근거 : 지주 RWA 한도 · 총자산 최대 성장률 통보, 하반기 부서별 신용RWA 한도 배분", f"기준년월 : {_ym_dot(rows[0]['ym'])} · 작성 : 종합기획부"], cols, rows, sheet="제약")
            f = SampleFile(name, "dataset", content, ds, note="자본 · 한도 제약")
        elif ds == "PEER_BANK_STATS":
            cols = [C("기준년월", "ym"), C("지표코드", "stat_code"), C("지표명", "stat_name"), C("값", "value", "num1"), C("출처", "issuer")]
            f = SampleFile(name, "dataset", X.csv_bytes(cols, rows), ds, origin="ext", note="외부 공시 통계")
        elif ds == "HQ_PLAN_KPI":
            cols = [C("기준년월", "ym"), C("항목코드", "item_code"), C("항목명", "item_name", width=36), C("값", "value", "num1"), C("단위", "unit"), C("조직코드", "org_code"), C("원천 문서", "source_doc", width=44), C("정의서 컬럼", "contract_column", width=34)]
            content = X.table("종합기획부 경영계획 · 보고서 KPI (컬럼정의서 v2)", [f"기준년월 : {_ym_dot(rows[0]['ym'])} · 작성 : 종합기획부 경영목표팀", "경영계획 승인 목표 · 모형 보고서 KPI · 지역본부 신규취급 실적"], cols, rows, sheet="KPI")
            f = SampleFile(name, "dataset", content, ds, note="경영계획 KPI")
        elif ds == "OBLG_GRD_DEF":
            cols = [C("std_ym", "std_ym"), C("brwr_no", "brwr_no"), C("brwr_nm", "brwr_nm"), C("SUVMN_BRC", "SUVMN_BRC"), C("Ls_nics_GRDC", "Ls_nics_GRDC", "int"), C("ln_bac", "ln_bac", "int"),
                    C("onlycard", "onlycard", "int"), C("STD_INDS_CFC", "STD_INDS_CFC"), C("crdevl_pttp_dsc_f", "crdevl_pttp_dsc_f"), C("default", "default", "int")]
            f = SampleFile(name, "dataset", X.csv_bytes(cols, rows), ds, note="기업 익스포저 차주별(시스템 테이블 추출)")
        elif ds == "CORP_PROSPECT":
            cols = [C("사업자등록번호", "biz_no"), C("법인등록번호", "corp_no"), C("기업명", "corp_nm", width=20), C("기업규모", "corp_scale"), C("설립일자", "estb_dt"), C("NICS모형", "nics_model"), C("예상재무등급", "exp_grade"),
                    C("산업코드", "ind_cd"), C("산업분류명", "ind_nm", width=28), C("지역", "region"), C("시군구", "sigungu", width=16), C("자산총계", "tot_asset", "num0"), C("부채총계", "tot_liab", "num0"),
                    C("자본총계", "tot_equity", "num0"), C("매출액", "sales", "num0"), C("영업이익", "op_income", "num0"), C("당기순이익", "net_income", "num0")]
            content = X.table("[붙임1] 여신가망 재무우량 기업명세", ["[외감기업 활성화] (필독) 여신가망 재무우량 기업명세 제공 안내 — 신용리스크관리부", "재무 기준 : 2025 회계연도 · 단위 : 백만원 · 당행 여신 미거래 기업"], cols, rows, sheet="기업명세")
            f = SampleFile(name, "dataset", content, ds, note="본부 추천 가망기업(공문 붙임)")
        elif ds == "RETAIL_EXPOSURE":
            cols = [C("기준년월", "std_ym"), C("차주식별번호", "brwr_id"), C("사무소코드", "office_cd"), C("해당상품Pool", "pool_id"), C("여신익스포져금액", "exp_amt", "int"), C("CB등급", "cb_grade", "int"), C("연체여부", "dlq_yn", "int")]
            f = SampleFile(name, "dataset", X.csv_bytes(cols, rows), ds, note="소매 익스포저(시스템 테이블 추출)")
        elif ds == "RETAIL_POOL_MASTER":
            cols = [C("Pool", "pool_id"), C("Pool 명", "pool_nm", width=26), C("상품군", "product_group"), C("저신용자 Pool", "low_credit", "bool"), C("업적평가 서민금융 인정", "seomin_eval", "bool"),
                    C("용도코드", "use_cd"), C("PD(%·가정)", "pd_pct", "num2"), C("LGD(%·가정)", "lgd_pct", "num1"), C("충당금률(%·가정)", "prov_rate_pct", "num4")]
            content = X.table("소매여신 상품 Pool 정의", ["Pool → 상품군 · 저신용자 Pool · 업적평가 서민금융 인정 · 용도코드 · 충당금률 가정(PD × LGD)", "작성 : 신용리스크관리부 · Y = 해당"], cols, rows, sheet="Pool")
            f = SampleFile(name, "dataset", content, ds, note="마스터 · Pool 정의")
        elif ds == "BRANCH_OFFICE_MASTER":
            cols = [C("사무소코드", "office_cd"), C("영업점명", "office_nm"), C("지역(시도)", "region"), C("시군구", "sigungu"), C("지역본부", "region_hq"), C("조직 코드", "org_code")]
            content = X.table("영업점(사무소) 마스터", ["작성 : 여신기획부 · 가망기업 지역 매칭용(시군구는 | 로 여러 개)"], cols, rows, sheet="사무소")
            f = SampleFile(name, "dataset", content, ds, note="마스터 · 영업점")
        elif ds == "BRANCH_KPI_SCHEME":
            cols = [C("평가기간", "period"), C("단계", "level", "int"), C("상위 항목", "group_cd"), C("항목 코드", "item_cd"), C("항목명", "item_nm", width=22), C("상위 코드", "parent_cd"), C("배점", "max_points", "num0"),
                    C("변경 구분", "change_type"), C("변경 내용", "change_summary", width=60), C("근거 면", "doc_page")]
            content = X.table("업적평가 배점표 (리테일 영업점) — 2026년 상 · 하반기", ["근거 : 26년(상) · 26년(하) 업적평가 세부기준 > 영업본부/영업점 평가기준 > 배점표 > 리테일", "작성 : 경영지원부 성과평가팀"], cols, rows, sheet="배점표")
            f = SampleFile(name, "dataset", content, ds, note="마스터 · 배점표")
        elif ds == "BRANCH_KPI_SCORE":
            cols = [C("사무소코드", "office_cd"), C("평가기간", "period"), C("기준일", "as_of", "date"), C("단계", "level", "int"), C("상위 항목", "group_cd"), C("항목 코드", "item_cd"), C("득점", "score", "num2"),
                    C("실적값", "actual_value", "num0"), C("목표값", "target_value", "num0"), C("실적 단위", "unit"), C("비고", "note")]
            content = X.table("영업점 업적평가 득점 현황", [f"사무소 : {rows[0]['office_cd']} · 평가기간 : {rows[0]['period']} · 기준일 : {rows[0]['as_of']}", "작성 : 경영지원부 성과평가팀(득점은 평가 중간 집계)"], cols, rows, sheet="득점")
            f = SampleFile(name, "dataset", content, ds, note="영업점 득점 현황")
        elif ds == "RETAIL_POOL_SUMMARY":
            ym = rows[0]["std_ym"]
            cols = [C("기준년월", "std_ym"), C("Pool", "pool_id"), C("익스포저 건수", "exposure_cnt", "int"), C("익스포저 금액(백만원)", "exposure_amt", "num0"), C("평균 CB 등급", "avg_cb_grade", "num1"), C("신규취급 누계(백만원)", "new_amt_ytd", "num0")]
            content = X.table("소매여신 Pool별 월별 집계 (TB_JC_PM_C_LA 집계)", [f"기준년월 : {_ym_dot(ym)} · 월말 · 전행 · 작성 : 신용리스크관리부", "신규취급 누계 = 해당 연도 1월 ~ 기준월 신규 취급액 합계 · 평균 CB 등급 = Pool 내 건수 가중"], cols, rows, sheet="Pool집계")
            f = SampleFile(name, "dataset", content, ds, note=f"소매 Pool 월별 집계 · {_ym_dot(ym)}")  # 합계 줄은 두지 않는다(행으로 읽히지 않게)
        elif ds == "BRANCH_BIZ_BALANCE":
            cols = [C("사무소코드", "office_cd"), C("기준년월", "ym"), C("부문 코드", "segment_cd"), C("부문명", "segment_nm"), C("금액(원)", "amount", "num0", width=20), C("기준", "measure")]
            content = X.table("영업점 사업부문별 잔액 · 실적", [f"사무소 : {rows[0]['office_cd']} · 기준년월 : {_ym_dot(rows[0]['ym'])} · 단위 : 원"], cols, rows, sheet="부문")
            f = SampleFile(name, "dataset", content, ds, note="영업점 사업부문")
        if f is None:
            raise ValueError(f"양식 없음: {ds}")
        f.rows = len(rows)
        out.append(f)
    return out


def _docs() -> list[SampleFile]:
    snips = collect_snippets()
    out = []
    for d in catalog():
        origin = "ext" if d["dbClass"] == "gov_policy" else "bank"
        name = d.get("fileName") or f"{d['title']}.pdf"
        content = pdf(d, snips.get(d["title"], []))
        out.append(SampleFile(name, "document", content, origin=origin, doc={"docCode": d["docId"], "docClass": d["dbClass"], "title": d["title"], "issuer": d.get("issuer"), "publishedAt": d.get("effectiveDate"), "meta": upload_meta(d)}))
    return out


# 교란 검사(Q139)에서 바꾸지 않는 열 — 범주 · 등급 · 순서 · 0/1 표시 (값이 아니라 분류)
KEEP_COLS = {"Ls_nics_GRDC", "onlycard", "default", "cb_grade", "dlq_yn", "grade_seq", "sdr_rank", "level"}


# 차주 단위 자료 — 구간 열 · 등급 열 · 등급 범위 (교란 검사에서 구간별 비율 · 등급 이동)
SEGMENT_COL = {"OBLG_GRD_DEF": "crdevl_pttp_dsc_f", "RETAIL_EXPOSURE": "pool_id"}
CAT_GRADE = {"OBLG_GRD_DEF": "Ls_nics_GRDC", "RETAIL_EXPOSURE": "cb_grade"}
CAT_RANGE = {"OBLG_GRD_DEF": (1, 16), "RETAIL_EXPOSURE": (1, 10)}
# 한 행 안에서 같은 비율로 바꾸는 열 — 서로 크기 순서가 정해진 값(최소 ≤ 대표 ≤ 최대)
SAME_ROW = {"PD_MASTER_SCALE": {"pd_min", "pd_mid", "pd_max"}}


def _factor(key: str) -> float:
    """0.72~1.40 (1 ± 4% 안은 피한다 — 우연히 같은 표시값이 되지 않게)."""
    u = (zlib.crc32(key.encode()) % 10_000) / 10_000
    f = 0.72 + 0.68 * u
    if abs(f - 1) < 0.04:
        f = 1.04 if f >= 1 else 0.96
    return f


def _specs() -> dict[str, Any]:
    with open(os.path.join(os.path.dirname(__file__), "scenario_specs.json"), encoding="utf-8") as fh:
        return json.load(fh)


def business_config() -> dict[str, Any]:
    """제품의 기본 업무 구성(seed/business_pack.json — 지표 산식 · 흐름 · 화면 연결 · 화면 · 조직, 값 없음). 시연 자료는 이 구성의 자료 이름 · 열에 맞춘다."""
    from nhdip.seed.pack import load_pack

    return load_pack()


def _perturb_rows(ds_code: str, rows: list[dict[str, Any]], seed: int) -> list[dict[str, Any]]:
    """수치 열을 셀마다 다른 결정적 비율(0.72~1.40)로 — 키 · 기준일 · 범주 열은 그대로. 균일 배율은 비율 · 증가율이 그대로라 쓰지 않는다."""
    # 시나리오 행의 키 · 수치 열(시연 자료 생성기 자신의 행 모양 — 플랫폼 정의가 아님, scenario_specs.json)
    spec = _specs()[ds_code]
    keys = set(spec.get("key_columns") or []) | {spec.get("as_of_column")} | KEEP_COLS
    num = {c: typ for c, typ in (spec.get("numeric") or {}).items() if c not in keys}
    seg_col = SEGMENT_COL.get(ds_code)
    out = []
    for r in rows:
        r = dict(r)
        rk = "|".join(str(r.get(k)) for k in (spec.get("key_columns") or [])) or json.dumps(r, sort_keys=True, ensure_ascii=False, default=str)
        if seg_col:
            # 차주 단위 자료 — 구간(규모 · Pool)마다 다른 비율 + 행 흔들림, 등급 · 연체 일부 이동, 일부 행 제외(건수 · 구성비도 바뀌게)
            u = (zlib.crc32(f"{seed}|{ds_code}|{rk}|cat".encode()) % 10_000) / 10_000
            # 구간마다 다른 제외 비율(3~25%) — 균일하게 빼면 건수 구성비가 그대로라 구간별로 다르게
            drop = 0.03 + 0.22 * ((zlib.crc32(f"{seed}|{ds_code}|{r.get(seg_col)}|drop".encode()) % 10_000) / 10_000)
            if (zlib.crc32(f"{seed}|{ds_code}|{rk}|drop".encode()) % 10_000) / 10_000 < drop:
                continue
            lo, hi = CAT_RANGE[ds_code]
            gcol = CAT_GRADE[ds_code]
            g = r.get(gcol)
            if isinstance(g, int) and lo <= g <= hi and u < 0.30:
                r[gcol] = max(lo, min(hi, g + (1 if u < 0.20 else -1)))
            if r.get("dlq_yn") is not None and u > 0.94:
                r["dlq_yn"] = 1 - int(r["dlq_yn"] or 0)
        for c, typ in num.items():
            v = r.get(c)
            if v is None or isinstance(v, bool) or not isinstance(v, (int, float)):
                continue
            col_key = "row" if c in SAME_ROW.get(ds_code, ()) else c
            f = _factor(f"{seed}|{ds_code}|{rk}|{col_key}")
            if seg_col:
                f = _factor(f"{seed}|{ds_code}|{r.get(seg_col)}|{c}") * (0.97 + 0.06 * f / 1.4)
            r[c] = int(round(v * f)) if typ in ("int", "integer") or (isinstance(v, int) and abs(v) >= 1000) else round(v * f, 6)
        out.append(r)
    return out


def build(ym: str = "202608", *, documents: bool = True, perturb_seed: int | None = None) -> Package:
    """시연 자료 패키지. perturb_seed 를 주면 같은 파일 · 같은 키에 수치만 셀마다 다르게 바꾼 교란 패키지(하드코딩 검출용)."""
    if ym not in SUPPORTED:
        raise ValueError(f"지원 기준월: {', '.join(SUPPORTED)} (시나리오 값이 있는 달)")
    versions = [*hq_and_risk_versions(), *branch_versions()]
    if perturb_seed is not None:
        versions = [{**v, "rows": _perturb_rows(v["dataset"], v["rows"], perturb_seed)} for v in versions]
    by: dict[str, list[dict[str, Any]]] = {}
    for v in versions:
        by.setdefault(v["dataset"], []).append(v)
    files: list[SampleFile] = []
    for ds in ORDER:
        vs = by.pop(ds, [])
        if ds == "PL_PRODUCT_SEGMENT":
            files += _pl_files(vs)
        elif ds == "LOAN_BALANCE_MONTHLY":
            files += _lb_files(vs)
        elif ds == "PROVISION_BY_PRODUCT":
            files += _prov_files(vs)
        else:
            files += _tidy_files(vs)
    if by:
        raise ValueError(f"순서에 없는 데이터셋: {sorted(by)}")
    for f in files:
        if f.dataset in EXT:
            f.origin = "ext"
    if documents:
        files += _docs()
    # 업무 구성(지표 산식 · 흐름 · 화면)은 제품에 들어 있다(seed/business_pack.json) — 패키지는 원천 자료 · 문서만
    return Package(ym, files, variant="base" if perturb_seed is None else f"perturb-{perturb_seed}")
