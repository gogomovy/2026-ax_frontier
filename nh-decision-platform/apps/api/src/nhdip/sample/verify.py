"""시연 자료 검증 (Phase I · RD-04 · RD-05).

expected(pkg)   패키지 파일(엑셀 · CSV)을 직접 읽어 화면 핵심 수치의 기대값을 계산한다 — 플랫폼 적재 · 계산 코드를 쓰지 않는다.
compare(...)    기대값 ↔ 화면 산출물의 수치(Figure id 별)
static_spots()  교란 검사 — 수치를 셀마다 바꾼 패키지를 올린 뒤에도 그대로인 데이터 자리(숫자 · 숫자가 든 문구) = 하드코딩 후보
selftest()      빈 DB(정의 시드만) → 패키지 업로드 → 교란 패키지 업로드 → 두 검사 (CI · 로컬)
"""
from __future__ import annotations

import csv
import io
import json
import math
import re
import time
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from .build import Package, SampleFile


# ═════════════════════════ 파일 직접 읽기 (플랫폼 파서 미사용) ═════════════════════════
def _sheet(content: bytes) -> list[list[Any]]:
    import openpyxl

    ws = openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=True).worksheets[0]
    return [list(r) for r in ws.iter_rows(values_only=True)]


def _txt(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _table(f: SampleFile) -> list[dict[str, Any]]:
    """실무형 표 · CSV — 머리글 줄(첫 칸이 비어 있지 않고 다음 줄부터 값)을 찾아 dict 로."""
    if f.name.lower().endswith(".csv"):
        return list(csv.DictReader(io.StringIO(f.content.decode("utf-8-sig"))))
    rows = _sheet(f.content)
    for i, r in enumerate(rows):
        filled = [c for c in r if _txt(c)]
        if len(filled) >= 3 and i + 1 < len(rows) and all(isinstance(c, str) for c in filled):
            head = [_txt(c) for c in r]
            out = []
            for rr in rows[i + 1:]:
                vals = [c for c in rr if _txt(c)]
                if not vals or (len(vals) == 1 and _txt(vals[0]).startswith("※")):
                    continue
                out.append({head[k]: rr[k] for k in range(min(len(head), len(rr))) if head[k]})
            return out
    return []


def _num(v: Any) -> Decimal:
    return Decimal(str(v).replace(",", ""))


def _files(pkg: Package, needle: str) -> list[SampleFile]:
    return sorted((f for f in pkg.files if needle in f.name), key=lambda f: f.name)


def _pl(f: SampleFile) -> dict[str, Decimal]:
    rows = _sheet(f.content)
    m = int(re.search(r"\((\d{6})\)", f.name).group(1)[4:])
    hr = next(i for i, r in enumerate(rows) if any(_txt(c) == f"{m}월 누계" for c in r))
    col = next(j for j, c in enumerate(rows[hr]) if _txt(c) == f"{m}월 누계")
    return {_txt(r[0]): _num(r[col]) for r in rows[hr + 1:] if r and _txt(r[0]) and r[col] is not None}


def _lb(f: SampleFile) -> dict[str, dict[int, Decimal]]:
    rows = _sheet(f.content)
    hr = next(i for i, r in enumerate(rows) if r and _txt(r[0]) == "과목구분")
    cols = {j: int(_txt(c)[:-1]) for j, c in enumerate(rows[hr]) if re.fullmatch(r"\d{1,2}월", _txt(c))}
    return {_txt(r[0]): {m: _num(r[j]) for j, m in cols.items() if r[j] is not None} for r in rows[hr + 1:] if r and _txt(r[0])}


def _prov(f: SampleFile) -> tuple[dict[str, Decimal], Decimal]:
    rows = _sheet(f.content)
    hr = next(i for i, r in enumerate(rows) if r and _txt(r[0]) == "상품코드")
    xcol = next(j for j, c in enumerate(rows[hr]) if _txt(c) == "손실충당금 및 충당부채 총계")
    out, total = {}, None
    for r in rows[hr + 1:]:
        if not r or r[xcol] is None:
            continue
        if _txt(r[0]) == "합계":
            total = _num(r[xcol])
        elif _txt(r[0]):
            out[_txt(r[0])] = _num(r[xcol])
    return out, total


def _r(v: Decimal, d: int) -> float:
    return float(v.quantize(Decimal(1).scaleb(-d), rounding=ROUND_HALF_UP))


def _growth(v0: Decimal, v1: Decimal) -> Decimal:
    return (v1 - v0) / abs(v0) * 100


def expected(pkg: Package) -> dict[str, float]:
    """화면 수치 id → 기대값(표시 자릿수 반올림)."""
    E: dict[str, float] = {}
    # 손익(2633) — 최근 · 전년 동기
    pl = [(_pl(f), f) for f in _files(pkg, "2633_상품부문별손익계산서")]
    (now, _), (prev, _) = pl[-1], pl[-2]
    T1, T0, N1, C1, H1, H0 = now["총수익"], prev["총수익"], now["여신(일반)부문 이자마진 수익"], now["기업자금대출금이자"], now["가계자금대출금이자"], prev["가계자금대출금이자"]
    E |= {"total_rev_cur": _r(T1 / 100, 0), "total_rev_rate": _r(_growth(T0, T1), 2), "nim_share_2026": _r(N1 / T1 * 100, 2), "corp_int_cur": _r(C1 / 100, 0), "hh_int_rate": _r(_growth(H0, H1), 2)}
    # 잔액(2020) — 최근 파일의 마지막 달 · 전년 같은 달
    lbs = [_lb(f) for f in _files(pkg, "2020 과목별 월별 여신현황")]
    cur = lbs[-1]
    m = max(cur["기업자금대출금"])
    c1, h1 = cur["기업자금대출금"][m], cur["가계자금대출금"][m]
    c0, h0 = lbs[-2]["기업자금대출금"][m], lbs[-2]["가계자금대출금"][m]
    E |= {"corp_bal": _r(c1 / 1_000_000, 2), "hh_bal": _r(h1 / 1_000_000, 2), "corp_growth": _r(_growth(c0, c1), 2), "hh_growth": _r(_growth(h0, h1), 2), "corp_share": _r(c1 / (c1 + h1) * 100, 2)}
    # 충당금(7790) × 포용금융 대상 상품 마스터
    master = {_txt(r.get("상품코드")) for r in _table(_files(pkg, "포용금융 대상 상품 운영기준")[0])}
    (pb, tb), (pn, tn) = (_prov(f) for f in _files(pkg, "7790_상품별_충당금"))
    sb = sum((v for k, v in pb.items() if k in master), Decimal(0)) / tb * 100
    sn = sum((v for k, v in pn.items() if k in master), Decimal(0)) / tn * 100
    E |= {"share_base": _r(sb, 2), "share_now": _r(sn, 2), "share_delta_pp": _r(sn - sb, 2)}
    # 모형 등급 집계 — 소기업 6B · 전체 부도율 · PSI
    mm = [_table(f) for f in _files(pkg, "신용평가모형_등급별")]
    base = [r for r in mm[0] if r["모형코드"] == "CORP_MICRO"]
    curr = [r for r in mm[1] if r["모형코드"] == "CORP_MICRO"]
    g6 = next(r for r in curr if _txt(r["등급"]) == "6B")
    E["dr_6b"] = _r(_num(g6["부도건수"]) / _num(g6["관측건수"]) * 100, 3)
    E["total_dr"] = _r(sum(_num(r["부도건수"]) for r in curr) / sum(_num(r["관측건수"]) for r in curr) * 100, 3)
    order = lambda rows: sorted(rows, key=lambda r: int(_num(r["등급순서"])))  # noqa: E731
    p = [float(_num(r["구성비(%)"])) / 100 for r in order(base)]
    q = [float(_num(r["구성비(%)"])) / 100 for r in order(curr)]
    E["psi_micro"] = _r(Decimal(str(sum((b - a) * math.log(b / a) for a, b in zip(p, q)))), 3)
    # 월별 부도율 — 대기업 최근월
    dr = [r for r in _table(_files(pkg, "월별_부도율_집계")[0]) if r["구분코드"] == "corp_large"]
    last = max(dr, key=lambda r: r["기준년월"])
    E["dr_corp_large_latest"] = _r(_num(last["부도건수"]) / _num(last["관측건수"]) * 100, 3)
    # 소매 Pool 월별 집계 × Pool 정의
    pools = {_txt(r["Pool"]): r for r in _table(_files(pkg, "소매여신 상품 Pool 정의")[0])}
    ps = {f.name: _table(f) for f in _files(pkg, "TB_JC_PM_C_LA_POOL_")}
    names = sorted(ps)
    latest, base_m, py = ps[names[-1]], ps[next(n for n in names if "202601" in n)], ps[names[0]]
    incl = {k for k, r in pools.items() if _txt(r["상품군"]) == "서민금융"}
    low = {k for k, r in pools.items() if _txt(r["저신용자 Pool"]) == "Y"}
    s = lambda rows, keys, col: sum((_num(r[col]) for r in rows if _txt(r["Pool"]) in keys), Decimal(0))  # noqa: E731
    cnt1, cnt0 = s(latest, incl, "익스포저 건수"), s(base_m, incl, "익스포저 건수")
    E |= {"inc_exposure_cnt_now": float(cnt1), "inc_exposure_cnt_growth": _r(_growth(cnt0, cnt1), 1), "inc_exposure_amt_now": _r(s(latest, incl, "익스포저 금액(백만원)") / 1_000_000, 2),
          "mid_low_supply": _r(s(latest, low, "신규취급 누계(백만원)") / 1_000_000, 2),
          "mid_low_growth": _r(_growth(s(py, low, "신규취급 누계(백만원)"), s(latest, low, "신규취급 누계(백만원)")), 1),
          "mid_low_share": _r(s(latest, low, "익스포저 금액(백만원)") / s(latest, set(pools), "익스포저 금액(백만원)") * 100, 1)}
    # 영업점 업적평가 총득점(2단계 항목 합)
    sc = [r for r in _table(_files(pkg, "영업점 업적평가 득점 현황")[0]) if _txt(r["단계"]) in ("2", "2.0")]
    E["br_kpi_total"] = _r(sum((_num(r["득점"]) for r in sc if _txt(r["득점"])), Decimal(0)), 1)
    return E


def figure_values(artifacts: dict[str, Any]) -> dict[str, Any]:
    from nhdip.views.template import figure_index

    return {k: v.get("value") for k, v in figure_index(artifacts).items()}


def compare(exp: dict[str, float], figs: dict[str, Any]) -> list[dict[str, Any]]:
    bad = []
    for k, v in exp.items():
        got = figs.get(k)
        if got is None or abs(float(got) - v) > 1e-9:
            bad.append({"figure": k, "expected": v, "actual": got})
    return bad


# ═════════════════════════ 교란 검사 ═════════════════════════
SKIP_KEYS = {"id", "code", "generation", "page", "seq", "rank", "order", "level", "decimals", "calcId", "executedAt", "version", "step", "tab", "href", "docId", "icon", "fileName",
             "sourceRef", "source", "productCode", "tableRef", "expression", "calc", "inputs", "generatedAt", "updatedAt", "createdAt", "registeredAt", "dueDate", "effectiveDate",
             "bindKey", "codes", "no", "rankScore", "rankCalcId", "relevance", "sectionPath", "persona", "reportAnchor", "key", "orgCode", "orgName", "regionHq", "docPage",
             "changeSummary", "metric", "productName", "verifications", "doc", "basisDoc", "office", "batchLabel", "retailNote"}
MARKER = re.compile(r"\[\[[^\]]+\]\]|\{\{[^}]+\}\}")
DATA_TOKEN = re.compile(r"\d[\d,]*\.\d+|\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?\s?(?:%p|%|조원|조|억원|억|백만원|건|원|점|bp)")
SKIP_ARTIFACTS = re.compile(r"^(terms|meta|change_feed|contract\.|report\.an-)")
DATE = re.compile(r"20\d\d[.\-/]\d\d(?:[.\-/]\d\d)?|20\d\d년|\d{1,2}월|\d+분기|제\d+조|v\d+|\d+개년|\d+개월|\d+등급|\d+[A-C]\b|\b\d+\.\d+\s(?=[가-힣])|[Ⅰ-Ⅹ]\.")
NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
# 바뀌지 않아도 되는 자리 — (경로 정규식, 이유). 경로 = '산출물:점.경로'
EXEMPT: list[tuple[str, str]] = [
    (r":.*\.(caption|title|label|heading|name)$", "구조 라벨(기간은 서식 문구, 숫자 없는 표 · 차트 제목)"),
    (r"^cascade:", "목표 전파 경로(기획 입력 — 경영목표 · 지역본부 배분, 사람이 확정)"),
    (r"^goals:.*\.(targetValue|title|detail)$|^goals:.*\.history", "확정 경영목표 · 이력(기획 입력)"),
    (r"^proposals:.*\.ruleInputs\.", "제안 근거(규칙 · 문서 인용 입력)"),
    (r"\.evidence\.\d+\.(snippet|label)$", "문서 인용 근거(문서 글 그대로) — 데이터 근거는 서식 문구"),
    (r"^(action_plans|branch_targets):.*\.(guideline|body|text|title)$", "수행방안 · 가이드 문구(사람이 쓴 계획)"),
    (r"^dataset_meta:", "데이터 목록(적재 이력)"),
    (r"\.(asOf|periodLabel|asOfLabel)$", "기준일 · 평가 기간(교란 패키지는 같은 기간)"),
    (r"\.recommendation\.", "목표 추천 범위(규칙 · 기조 기반 — 데이터 제약에 닿지 않으면 같은 값)"),
    (r"\.rows\.\d+\.weight$", "등급 구간 가중치(규칙 — 등급 범주가 같으면 같은 값)"),
    (r"\.rows\.\d+\.sdrRank$", "SDR 순위(원천 범주 열 sdr_rank 그대로 — 교란하지 않는 순위 · 범주)"),
]
# 값 자체로 그대로여도 정상인 자리 — 0(해당 칸 자료 없음: 곱셈 교란에도 0), 구성비 합계 100%
ZERO = re.compile(r"^[+\-]?0(?:\.0+)?%?$")
FULL_SHARE = re.compile(r"^100(?:\.0+)?%?$")
SHARE_KEY = re.compile(r"(?i)share|total|pct|ratio")
# 수치 id 별 예외 — (이유). 제약이 걸려 규칙값이 그대로 결과가 되는 자리
EXEMPT_FIGS: dict[str, str] = {
    "br_seomin_add_prov": "충당금 허용 범위가 권고 규모를 정하면 추가 충당금 = 허용액(규칙값 · BRANCH_SEOMIN_POLICY.max_add_provision_mn)",
}


TINY_CELL = re.compile(r"^0\.\d%?$")


def invariant_value(x: Any, key: str, path: str = "") -> bool:
    """0 · 구성비 합계(100%) · 표 칸의 1% 미만 구성비(소수 1자리 — 차주 1명 ≈ 0.6%, 교란 폭이 표시 단위보다 작음)."""
    s = str(x).strip().replace(",", "")
    if ZERO.match(s):
        return True
    if TINY_CELL.match(s) and ".table.rows." in path:
        return True
    return bool(FULL_SHARE.match(s) and SHARE_KEY.search(key or ""))
TPL_FIG = re.compile(r"\[\[fig:([a-zA-Z0-9_\-]+)")


def _config_figs(session: Any) -> dict[str, str]:
    """값이 데이터로 바뀌지 않는 수치 id → 이유 — 규칙 · 상수만 쓰는 지표, 건수 세기(키 · 범주는 교란하지 않음), 판정(구간이 같으면 같음)."""
    from sqlalchemy import select

    from nhdip.models import Metric

    ms = {m.code: m for m in session.execute(select(Metric)).scalars()}
    memo: dict[str, str | None] = {}

    def kind(code: str, seen: frozenset = frozenset()) -> str | None:
        if code in memo:
            return memo[code]
        m = ms.get(code)
        if m is None or code in seen:
            return None
        if m.formula in ("BAND", "VERDICT", "CHI2_TEST", "MONOTONIC_BREAKS", "PROSPECT_SELECT", "CHI2_CRITICAL", "GOAL_RANGE_REC", "RANGE_REC", "GROWTH_RANGE_REC", "MIN_OF", "CEIL_DIV"):
            memo[code] = "판정 · 선정 · 임계 · 추천 범위(구간 · 기준 · 한도가 같으면 같은 값)"
            return memo[code]
        if any(isinstance(v, dict) and v.get("field") not in (None, "value") for v in (m.args or {}).values()):
            memo[code] = "계산 부가값(자유도 · 범위 끝 등 — 구조가 같으면 같은 값)"
            return memo[code]
        refs: list[dict[str, Any]] = []

        def collect(o: Any) -> None:
            if isinstance(o, dict):
                if any(k in o for k in ("q", "metric", "rule", "const", "setting")):
                    refs.append(o)
                else:
                    for v in o.values():
                        collect(v)
            elif isinstance(o, list):
                for v in o:
                    collect(v)

        collect(m.args or {})
        sub = []
        for r in refs:
            if "q" in r:
                sub.append("count" if (r["q"].get("agg") == "count") else "data")
            elif "metric" in r:
                sub.append(kind(r["metric"], seen | {code}) or "data")
            else:
                sub.append("config")
        if sub and all(s != "data" for s in sub):
            memo[code] = "규칙 · 상수 · 건수(교란하지 않는 키 · 범주)"
        else:
            memo[code] = None
        return memo[code]

    out: dict[str, str] = {}
    for code, m in ms.items():
        why = kind(code)
        if why:
            for fid in m.figure_ids or []:
                out[fid] = why
    return out


# 규칙 · 건수 · 매칭만 쓰는 표 빌더 — 교란(같은 키 · 같은 범주)에도 같은 결과가 정상
CONFIG_BUILDERS = {"branch_prime_weights", "inclusive_match_note", "data_quality", "branch_office"}


def config_paths(session: Any, artifacts: dict[str, Any]) -> set[str]:
    from sqlalchemy import select

    from nhdip.models import ViewBinding
    from nhdip.views.template import binding_targets

    out: set[str] = set()
    for b in session.execute(select(ViewBinding).where(ViewBinding.builder.in_(CONFIG_BUILDERS))).scalars():
        p = artifacts.get(b.artifact_key)
        if p is None:
            continue
        for parent, fld in binding_targets(p, b.path):
            out.add(f"{b.artifact_key}:{parent + '.' if parent else ''}{fld}")
    return out


def static_spots(a: dict[str, Any], b: dict[str, Any], config_figs: dict[str, str], skip_paths: set[str] | None = None) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """A(기본 패키지) · B(교란 패키지) 같은 경로 비교 — 그대로인 숫자 · 숫자 문구."""
    from nhdip.views.template import is_figure

    spots: list[dict[str, Any]] = []
    exempt = {"config": 0, "rule": 0}
    pats = [(re.compile(p), why) for p, why in EXEMPT]
    skip_paths = skip_paths or set()

    def config_tpl(tpl: str) -> bool:
        figs = TPL_FIG.findall(tpl)
        return not figs or all(f in config_figs or f in EXEMPT_FIGS for f in figs)

    def walk(x: Any, y: Any, path: str, key: str) -> None:
        if path.replace(":.", ":") in skip_paths:
            exempt["config"] += 1
            return
        if isinstance(x, dict) and isinstance(y, dict):
            if is_figure(x):
                if x.get("value") is not None and x.get("value") == y.get("value"):
                    if x["id"] in config_figs or x["id"] in EXEMPT_FIGS:
                        exempt["config"] += 1
                    elif x.get("value") == 0:
                        exempt["rule"] += 1
                    else:
                        spots.append({"path": path, "figure": x["id"], "value": x["value"], "kind": "figure"})
                for k in ("label",):
                    if k in x:
                        walk(x[k], y.get(k), f"{path}.{k}", k)
                return
            for k in x:
                if k in y and k not in SKIP_KEYS and not k.endswith(("Tpl", "Id", "Metric")):
                    tpl = x.get(k + "Tpl")
                    if isinstance(tpl, str) and x[k] == y[k]:
                        # 서식 문구 — 규칙 · 상수 · 건수 수치만 쓰면 그대로여도 정상, 데이터 수치가 있으면 하드코딩 후보
                        if config_tpl(tpl):
                            exempt["config"] += 1
                            continue
                    if isinstance(tpl, list) and isinstance(x[k], list) and isinstance(y[k], list):
                        # 문구 목록 서식 — 항목마다 같은 판단
                        for i, (xx, yy) in enumerate(zip(x[k], y[k])):
                            t = tpl[i] if i < len(tpl) else None
                            if isinstance(t, str) and xx == yy and config_tpl(t):
                                exempt["config"] += 1
                                continue
                            walk(xx, yy, f"{path}.{k}.{i}", k)
                        continue
                    walk(x[k], y[k], f"{path}.{k}", k)
        elif isinstance(x, list) and isinstance(y, list):
            for i, (xx, yy) in enumerate(zip(x, y)):
                walk(xx, yy, f"{path}.{i}", key)
        elif x == y and x is not None:
            if isinstance(x, (int, float)) and not isinstance(x, bool):
                if isinstance(x, int) and x in (0, 1):
                    return
            elif isinstance(x, str):
                if not DATA_TOKEN.search(DATE.sub("", MARKER.sub("", x))) or x.strip() in ("–", "-"):
                    return
            else:
                return
            if invariant_value(x, key, path):
                exempt["rule"] += 1
                return
            for pat, _why in pats:
                if pat.search(path):
                    exempt["rule"] += 1
                    return
            spots.append({"path": path, "value": x if not isinstance(x, str) else x[:140], "kind": "text" if isinstance(x, str) else "number"})

    for k in sorted(a):
        if SKIP_ARTIFACTS.match(k) or k not in b:
            continue
        walk(a[k], b[k], f"{k}:", "")
    for s in spots:
        s["path"] = s["path"].replace(":.", ":")
    return spots, exempt


# ═════════════════════════ 자체 시험 (빈 DB → 업로드 → 교란 업로드) ═════════════════════════
def drain(session_factory: Any, rounds: int = 60) -> float:
    from sqlalchemy import func, select

    from nhdip.models import Job, OutboxEvent, utcnow
    from nhdip.worker import process_one
    from nhdip.workflow.dispatcher import dispatch_once

    t0 = time.monotonic()
    for _ in range(rounds):
        with session_factory() as s:
            dispatch_once(s)
            for j in s.execute(select(Job).where(Job.status == "queued")).scalars():
                j.run_after = utcnow()
            s.commit()
        n = 0
        while process_one("sample-selftest"):
            n += 1
        with session_factory() as s:
            ev = s.execute(select(func.count()).select_from(OutboxEvent).where(OutboxEvent.dispatched_at.is_(None))).scalar()
            jobs = s.execute(select(func.count()).select_from(Job).where(Job.status.in_(["queued", "running"]))).scalar()
        if not n and not ev and not jobs:
            break
    return time.monotonic() - t0


def selftest(emp_no: str, password: str, *, perturb_seeds: tuple[int, int] = (7, 11)) -> dict[str, Any]:
    """현재 DATABASE_URL 의 DB(정의 시드만, 업무 자료 없음)에서 — 업로드 · 엑셀 대조 · 교란 검사. 문제가 있으면 ok=False."""
    from fastapi.testclient import TestClient

    from nhdip.db import SessionLocal
    from nhdip.main import app
    from nhdip.seed.run import has_business_data
    from nhdip.views.store import all_current

    from .build import build
    from .load import upload_http

    with SessionLocal() as s:
        if has_business_data(s):
            raise RuntimeError("업무 자료가 이미 있는 DB 입니다 — 새 DB(정의 시드만)에서 실행하세요")
    rep: dict[str, Any] = {"perturb_seeds": list(perturb_seeds)}
    base = build()
    snaps: list[dict[str, Any]] = []
    ok = True
    with TestClient(app) as c:
        up = upload_http("http://testserver", emp_no, password, base, client=c)
        rep["upload"] = {k: v for k, v in up.as_dict().items() if k != "files"}
        ok &= up.ok
        rep["drain_sec"] = round(drain(SessionLocal), 1)
        with SessionLocal() as s:
            a = all_current(s)
            cfg = _config_figs(s)
            skip = config_paths(s, a)
        rep["verify_base"] = compare(expected(base), figure_values(a))
        ok &= not rep["verify_base"]
        # 교란 패키지 두 벌 — 우연히 같은 표시값이 된 자리를 빼려고 두 번 모두 그대로인 자리만 하드코딩 후보로 본다
        for seed in perturb_seeds:
            bad = build(perturb_seed=seed)
            up2 = upload_http("http://testserver", emp_no, password, bad, client=c, force=True)
            rep[f"upload_perturbed_{seed}"] = {k: v for k, v in up2.as_dict().items() if k != "files"}
            ok &= up2.ok
            rep[f"drain_{seed}_sec"] = round(drain(SessionLocal), 1)
            with SessionLocal() as s:
                b = all_current(s)
            rep[f"verify_perturbed_{seed}"] = compare(expected(bad), figure_values(b))
            ok &= not rep[f"verify_perturbed_{seed}"]
            snaps.append(b)
    runs = [static_spots(a, b, cfg, skip) for b in snaps]
    common = set.intersection(*({s["path"] for s in spots} for spots, _ in runs))
    rep["static"] = [s for s in runs[0][0] if s["path"] in common]
    rep["exempt"] = runs[0][1]
    rep["ok"] = bool(ok) and not rep["static"]
    return rep


def verify_http(base_url: str, emp_no: str, password: str, pkg: Package | None = None) -> dict[str, Any]:
    """원격 스택(HTTP) — 화면 API 의 산출물 수치를 패키지 기대값과 비교."""
    from .build import build
    from .load import HttpUploader

    pkg = pkg or build()
    up = HttpUploader(base_url, emp_no, password)
    arts: dict[str, Any] = {}
    for path in ("/screens/hq-dashboard", "/screens/loan-overview", "/screens/comparison-view", "/screens/inclusive", "/screens/risk-dashboard", "/screens/reports/model-monitoring",
                 "/screens/default-rate-trend", "/screens/proposals", "/screens/branch/dashboard"):
        r = up.c.get(path)
        if r.status_code == 200:
            arts[path] = r.json()
    exp = expected(pkg)
    bad = compare(exp, figure_values(arts))
    return {"ok": not bad, "checked": len(exp), "mismatch": bad, "screens": len(arts)}


def to_json(rep: dict[str, Any]) -> str:
    return json.dumps(rep, ensure_ascii=False, indent=1, default=str)
