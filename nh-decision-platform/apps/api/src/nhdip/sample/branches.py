"""영업점 3곳 시험 자료 — 영업점별로 가입한 직원이 자기 지점 자료를 올리고, 영업본부(지역본부) 통합 업적평가에 모이는지 확인하는 묶음.

지점(기본 업무 구성의 조직표에 있는 수도권1지역본부 아래 영업점):
  BR301 강남금융센터 · BR302 서초지점 · BR303 역삼역지점  — 사무소 코드 = 조직 코드
파일은 기존 시연 자료(sample.build)와 같은 양식 · 같은 열이라 같은 자료 정의에 그대로 이어진다.

  공통(관리자, 소유 = 전행 공통)  영업점 사무소 마스터(3곳) · 업적평가 배점표 · 소매여신 상품 Pool 정의 · 여신가망 재무우량 기업명세
  지점별(소유 = 그 영업점)        기업여신 차주 등급 · 소매여신 차주 익스포저 · 업적평가 득점 현황 · 사업부문별 잔액

  python -m nhdip.sample branches --out test-data/branches
"""
from __future__ import annotations

import json
import os
import random
import zlib
from dataclasses import dataclass
from typing import Any

from . import scenario_branch as S
from .build import SampleFile, _tidy_files


@dataclass(frozen=True)
class Branch:
    code: str  # 조직 코드 = 사무소 코드
    name: str
    region: str
    sigungu: str
    profile: float  # 득점 수준(1 = 기준) — 지점마다 순위 · 득점률이 갈리게


REGION_CODE, REGION_NAME = "D300", "수도권1지역본부"
BRANCHES = (
    Branch("BR301", "강남금융센터", "서울", "강남구", 1.08),
    Branch("BR302", "서초지점", "서울", "서초구", 0.94),
    Branch("BR303", "역삼역지점", "서울", "강남구", 0.86),
)
# 가입 · 승인 예시 — 영업점 직원 3명 + 영업본부(지역본부 영업점지원팀) 1명. 사번은 시험용
ACCOUNTS = (
    ("20269301", "강남시험", "BR301"),
    ("20269302", "서초시험", "BR302"),
    ("20269303", "역삼시험", "BR303"),
    ("20269300", "본부시험", "T311"),
)
PROSPECT_NAMES = ["테헤란", "선릉", "삼성", "서초", "반포", "양재", "역삼", "논현", "청담", "도곡", "방배", "잠원"]


def _rng(*keys: Any) -> random.Random:
    return random.Random(zlib.crc32("|".join(map(str, keys)).encode()))


def _corp(b: Branch) -> list[dict[str, Any]]:
    rng = _rng("corp", b.code)
    rows: list[dict[str, Any]] = []
    i = 0
    for size, n in S.BRANCH_SIZE_N.items():
        for _ in range(max(1, round(n * rng.uniform(0.7, 1.3)))):
            i += 1
            mu, sd, med, s = S.SIZE_SPEC[size]
            seq = max(1, min(16, round(rng.gauss(mu - (b.profile - 1) * 4, sd))))  # 득점이 높은 지점은 등급도 조금 더 좋게
            amt = med * pow(2.718281828, rng.gauss(0, s)) + (10.0 if size == "16" else 0.0)
            ind = rng.choices(list(S.BRANCH_IND_W), weights=list(S.BRANCH_IND_W.values()))[0]
            nm = f"{rng.choice(S.NAME_A)}{rng.choice(S.NAME_B)}"
            if size != "16":
                nm = f"(주){nm}" if rng.random() < 0.5 else f"{nm}(주)"
            rows.append({"std_ym": S.YM, "brwr_no": f"B{b.code}{i:06d}", "brwr_nm": nm, "SUVMN_BRC": b.code, "Ls_nics_GRDC": seq, "ln_bac": int(round(amt * 1e8, -4)), "onlycard": 0,
                         "STD_INDS_CFC": S.IND[ind][0], "crdevl_pttp_dsc_f": size, "default": 1 if rng.random() < 0.0004 * (1.52 ** (seq - 1)) else 0})
    return rows


def _retail(b: Branch) -> list[dict[str, Any]]:
    rng = _rng("retail", b.code)
    spec = {p[0]: p for p in S.POOLS}
    mix = {p[0]: p[9] * (1.6 if p[4] and b.profile > 1 else 1.0) for p in S.POOLS}  # 서민금융 비중도 지점마다 다르게
    rows = []
    for j in range(1, rng.randint(220, 300) + 1):
        pool = rng.choices(list(mix), weights=list(mix.values()))[0]
        p = spec[pool]
        amt = p[10] * pow(2.718281828, rng.gauss(0, 0.45))
        if p[11]:
            amt = min(amt, float(p[11]))
        lo, hi = S.POOL_CB[pool]
        rows.append({"std_ym": S.YM, "brwr_id": f"R{b.code}{j:06d}", "office_cd": b.code, "pool_id": pool, "exp_amt": int(round(amt * 1e6, -4)), "cb_grade": rng.randint(lo, hi),
                     "dlq_yn": 1 if rng.random() < p[12] else 0})
    return rows


def _scores(b: Branch) -> list[dict[str, Any]]:
    rng = _rng("score", b.code)
    lv = {s[2]: (s[0], s[1]) for s in S.SCHEME}
    out = []
    for k, (score, actual, target, unit) in S.SCORES.items():
        f = b.profile * rng.uniform(0.95, 1.05)
        sc = round(score * f, 2) if score >= 0 else score
        act = int(round(actual * f)) if actual is not None else None
        out.append({"office_cd": b.code, "period": S.PERIOD, "as_of": "2026-08-31", "level": lv[k][0], "group_cd": lv[k][1], "item_cd": k, "score": sc, "actual_value": act, "target_value": target,
                    "unit": unit if actual is not None else "", "note": unit if actual is None else ""})
    return out


def _balance(b: Branch) -> list[dict[str, Any]]:
    rng = _rng("bal", b.code)
    return [{"office_cd": b.code, "ym": S.YM, "segment_cd": c, "segment_nm": n, "amount": int(round(a * b.profile * rng.uniform(0.8, 1.2), -6)), "measure": m} for c, n, a, m in S.BIZ_BALANCE]


def _prospects() -> list[dict[str, Any]]:
    """지점 영업구역(강남구 · 서초구) 후보 + 다른 지역 — 지점마다 추천 후보가 나오게."""
    rng = _rng("prospect")
    out = []
    for k in range(36):
        sig = ("강남구", "서초구", "송파구")[k % 3]
        model = rng.choice(["11", "12", "12", "13", "13", "13"])
        asset = int(rng.uniform(40_000, 600_000) * (3 if model == "11" else 1))
        liab = int(asset * rng.uniform(0.25, 0.7))
        sales = int(asset * rng.uniform(0.6, 1.4))
        op = int(sales * rng.uniform(0.04, 0.13))
        ind = rng.choice(list(S.IND))
        out.append({"biz_no": f"{rng.randint(101, 899)}-8{rng.randint(1, 8)}-{rng.randint(10000, 99999):05d}", "corp_no": f"{rng.randint(110111, 285011)}-0{rng.randint(100000, 999999)}",
                    "corp_nm": f"{PROSPECT_NAMES[k % len(PROSPECT_NAMES)]}{rng.choice(S.NAME_B)}(주)", "corp_scale": {"11": "대기업", "12": "중견기업", "13": "중소기업"}[model],
                    "estb_dt": f"{rng.randint(1995, 2018)}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}", "nics_model": model, "exp_grade": rng.choice(S.GRADE_LABELS[1:7]),
                    "ind_cd": S.IND[ind][0], "ind_nm": S.IND[ind][1], "region": "서울", "sigungu": sig, "tot_asset": asset, "tot_liab": liab, "tot_equity": asset - liab, "sales": sales,
                    "op_income": op, "net_income": int(op * 0.74)})
    return out


def common_versions() -> list[dict[str, Any]]:
    """공통 자료(관리자가 전행 공통으로 한 번) — 배점표 · Pool 정의는 기존 시연 자료와 같다."""
    base = {v["dataset"]: v for v in S.branch_versions()}
    return [
        {"dataset": "BRANCH_OFFICE_MASTER", "file_name": "영업점 사무소 마스터.xlsx",
         "rows": [{"office_cd": b.code, "office_nm": b.name, "region": b.region, "sigungu": b.sigungu, "region_hq": REGION_NAME, "org_code": b.code} for b in BRANCHES]},
        base["BRANCH_KPI_SCHEME"],
        base["RETAIL_POOL_MASTER"],
        {"dataset": "CORP_PROSPECT", "file_name": "붙임1) 여신가망 재무우량 기업명세(2026).xlsx", "rows": _prospects()},
    ]


def branch_files(b: Branch) -> list[dict[str, Any]]:
    return [
        {"dataset": "OBLG_GRD_DEF", "file_name": f"Oblg_grd_def_{S.YM}_{b.code}.csv", "rows": _corp(b)},
        {"dataset": "RETAIL_EXPOSURE", "file_name": f"TB_JC_PM_C_LA_{S.YM}_{b.code}.csv", "rows": _retail(b)},
        {"dataset": "BRANCH_KPI_SCORE", "file_name": f"영업점 업적평가 득점 현황({S.YM})_{b.name}.xlsx", "rows": _scores(b)},
        {"dataset": "BRANCH_BIZ_BALANCE", "file_name": f"영업점 사업부문별 잔액({S.YM})_{b.name}.xlsx", "rows": _balance(b)},
    ]


def build_branches() -> dict[str, list[SampleFile]]:
    """{'공통': [...], 'BR301 강남금융센터': [...], ...} — 업로드 순서대로."""
    out = {"00_공통(관리자 · 전행 공통)": _tidy_files(common_versions())}
    for n, b in enumerate(BRANCHES, start=1):
        out[f"{n:02d}_{b.code} {b.name}(소유 {b.code})"] = _tidy_files(branch_files(b))
    return out


GUIDE = """영업점 3곳 시험 자료 (시뮬레이션 · 실제 고객 정보 아님)

1) 가입 · 승인 — 각 사번으로 가입하고, 관리자 [사용자]에서 승인할 때 업무 소속을 고릅니다.
{accounts}
2) 공통 자료 — 관리자가 [데이터셋·문서]에서 '00_공통' 폴더 파일을 소유 '전행 공통'(빈 값)으로 올립니다.
   영업점 사무소 마스터에 세 지점이 있어야 지점마다 계산됩니다.
3) 지점 자료 — 지점 폴더의 파일을 그 지점 소유로 올립니다. 둘 중 하나:
   - 관리자 [데이터셋·문서]에서 '자료를 둘 팀 · 영업점'을 그 지점으로 고르고 올림
   - 지점 직원이 [자료 올리기]로 올리고 관리자가 [자료 승인] (영업점에 '자료 올리기' 화면 권한이 있어야 합니다)
4) 확인 — 지점 직원: 영업점 현황 · 분석 결과에 자기 지점 / 본부시험(영업점지원팀): [영업점 업적평가 통합]에 세 지점 순위 · 득점률
   다 올린 뒤 계산이 끝날 때까지 잠시(워커) — 관리자 [실행 현황]에서 wf_branch_kpi 가 성공인지 봅니다.
"""


def write(out_dir: str) -> dict[str, Any]:
    groups = build_branches()
    manifest: dict[str, Any] = {"region": {"code": REGION_CODE, "name": REGION_NAME}, "branches": [b.__dict__ for b in BRANCHES], "folders": {}}
    for folder, files in groups.items():
        d = os.path.join(out_dir, folder)
        os.makedirs(d, exist_ok=True)
        for f in files:
            with open(os.path.join(d, f.name), "wb") as fh:
                fh.write(f.content)
        manifest["folders"][folder] = [{"name": f.name, "rows": f.rows, "note": f.note} for f in files]
    accounts = "\n".join(f"   - 사번 {e} · 이름 {n} · 소속 {o} ({next((b.name for b in BRANCHES if b.code == o), '영업점지원팀 — 수도권1지역본부')})" for e, n, o in ACCOUNTS)
    with open(os.path.join(out_dir, "안내.txt"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(GUIDE.format(accounts=accounts))
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    return {"out": out_dir, "folders": {k: len(v) for k, v in groups.items()}}
