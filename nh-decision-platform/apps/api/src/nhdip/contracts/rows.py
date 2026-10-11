"""컬럼 정의서 다행 테이블 — 행 생성기 (B.38).

종기부 T01~T03 은 한 기준월 한 행이지만, 사업부서 · 영업점 정의서는 등급 · 상품 · Pool · 집계그룹마다 행이 있다.
행 생성기는 확정 데이터셋 버전에서 행 단위 값을 모으고, 파생 값(비율 · 차이 · PSI 기여도 · 가중평균)은 모두 계산 커널(execute)로 구한다.
반환: [{정의서 컬럼명(소문자): 값}] — 정의서 바인딩 {"row": "<컬럼>"} 이 이 값을 쓴다.
원천이 없는 컬럼(전년말 · 연체 원장 등 '추가 필요')은 행에 넣지 않아 '미연결'로 남는다(임의 수치를 만들지 않음).
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Callable

from nhdip.calc import execute
from nhdip.calc.metrics import EvalContext, resolve_token

ROW_BUILDERS: dict[str, Callable[[EvalContext, dict[str, Any]], list[dict[str, Any]]]] = {}
DESCRIPTIONS: dict[str, str] = {}


def row_builder(name: str, description: str):
    def deco(fn):
        ROW_BUILDERS[name] = fn
        DESCRIPTIONS[name] = description
        return fn

    return deco


def _D(v: Any) -> Decimal | None:
    if v is None or v == "":
        return None
    return Decimal(str(v))


def _k(formula: str, **inputs: Any) -> Decimal | None:
    """커널 실행 — 입력이 비거나 계산할 수 없으면 None(산출불가)."""
    if any(v is None for v in inputs.values()):
        return None
    try:
        return execute(formula, inputs).value
    except Exception:  # noqa: BLE001 — 0 분모 등은 산출불가
        return None


def _q(v: Decimal | None, places: int = 4) -> Decimal | None:
    return None if v is None else v.quantize(Decimal(1).scaleb(-places))


def _ym(v: Any) -> str:
    s = str(v or "")
    return s.replace("-", "")[:6]


def _asof(ctx: EvalContext) -> str:
    from nhdip.models import Setting

    s = ctx.session.get(Setting, "ui.as_of")
    return str(s.value) if s is not None and s.value else ""


def _rows(ctx: EvalContext, code: str) -> list[dict[str, Any]]:
    _, rows, _ = ctx.dataset(code)
    return rows


def _rule(ctx: EvalContext, code: str) -> dict[str, Any]:
    from nhdip.calc.metrics import resolve_ref

    try:
        return resolve_ref(ctx, {"rule": code})[0] or {}
    except Exception:  # noqa: BLE001
        return {}


# ═════════════════════════ 사업부서 (신용리스크관리부) ═════════════════════════
@row_builder("risk_grade_rows", "사업부서 T02 — 모형 · 등급별 관측 · 부도 · 비중 · PSI 기여도 · 실제부도율 · PD 비교")
def risk_grade_rows(ctx: EvalContext, p: dict[str, Any]) -> list[dict[str, Any]]:
    model = p.get("model_code", "CORP_MICRO")
    g = [r for r in _rows(ctx, "MODEL_MONITORING_GRADE") if r.get("model_code") == model]
    if not g:
        return []
    dates = sorted({str(r.get("as_of")) for r in g})
    cur_d, base_d = dates[-1], dates[0]
    cur = {r["grade"]: r for r in g if str(r.get("as_of")) == cur_d}
    base = {r["grade"]: r for r in g if str(r.get("as_of")) == base_d}
    pd_ = {r["grade"]: r for r in _rows(ctx, "PD_MASTER_SCALE") if r.get("model_code") == model}
    order = sorted(cur, key=lambda k: cur[k].get("grade_seq") or 0)
    tot_cur = sum(_D(cur[k].get("obs_count")) or 0 for k in order)
    tot_base = sum(_D(base[k].get("obs_count")) or 0 for k in order if k in base)
    # 비중 원천: 기본은 데이터셋의 비중 컬럼(obs_share) — 화면 · 지표 psi_micro 와 같은 입력이라 PSI 가 일치한다.
    # params.share_col 을 비우면 정의서 산식(등급건수 ÷ 전체건수 × 100)으로 계산한다.
    share_col = p.get("share_col", "obs_share")

    def share(row: dict[str, Any], tot: Decimal) -> Decimal | None:
        if share_col and row.get(share_col) is not None:
            return _D(row.get(share_col))
        return _k("SHARE", numerator=_D(row.get("obs_count")), denominator=tot)

    psi_res = execute("PSI", {"base": [share(base.get(k, {}), tot_base) or 0 for k in order], "current": [share(cur[k], tot_cur) or 0 for k in order]})
    contrib = psi_res.extra.get("contributions") or []
    psi = psi_res.value
    out = []
    for i, k in enumerate(order):
        c, b, m = cur[k], base.get(k, {}), pd_.get(k, {})
        n, d = _D(c.get("obs_count")), _D(c.get("default_count"))
        dr = _k("DEFAULT_RATE", default_count=d, obs_count=n)
        mid, mx, mn = _D(m.get("pd_mid")), _D(m.get("pd_max")), _D(m.get("pd_min"))
        gap = _k("DIFF", a=dr, b=mid)
        out.append({
            "base_ym": _ym(cur_d), "model_id": model, "grade_cd": k,
            "ref_base_ym": _ym(base_d), "reference_cnt": _D(b.get("obs_count")), "current_cnt": n, "default_cnt": d,
            "nondefault_cnt": _k("DIFF", a=n, b=d),
            "reference_share_rt": _q(share(b, tot_base)) if b else None,
            "current_share_rt": _q(share(c, tot_cur)),
            "psi_component": _q(Decimal(str(contrib[i])), 6) if i < len(contrib) else None,
            "model_psi": _q(psi, 6),
            "actual_default_rt": _q(dr), "pred_pd_rt": mid, "pred_pd_min_rt": mn, "pred_pd_max_rt": mx, "pd_gap_pp": _q(gap),
            "exceed_rep_pd_yn": None if dr is None or mid is None else ("Y" if dr > mid else "N"),
            "exceed_max_pd_yn": None if dr is None or mx is None else ("Y" if dr > mx else "N"),
        })
    return out


@row_builder("risk_model_rows", "사업부서 T01 — 모형별 현황(익스포저 · PSI · AR · 대표 등급 실제부도율 · PD) — 지표는 이 실행 또는 최근 확정값")
def risk_model_rows(ctx: EvalContext, p: dict[str, Any]) -> list[dict[str, Any]]:
    from nhdip.calc.metrics import ResolveError, resolve_ref

    def m(code: str) -> Decimal | None:
        try:
            v = resolve_ref(ctx, {"metric": code})[0]
        except ResolveError:
            return None
        return None if v is None else Decimal(str(v))

    model = p.get("model_code", "CORP_MICRO")
    grades = risk_grade_rows(ctx, {"model_code": model})
    meta = {r.get("model_code"): r for r in _rows(ctx, "MODEL_MONITORING_GRADE")}
    labels = _rule(ctx, "MODEL_LABELS") or {}
    g = p.get("grade", "6B")
    mm = [r for r in _rows(ctx, "MODEL_MONITORING_GRADE") if r.get("model_code") == model]
    last = max((str(r.get("as_of")) for r in mm), default=None)
    exp = _k("SUM", values=[_D(r.get("exposure_amt")) or 0 for r in mm if str(r.get("as_of")) == last])
    won = _D(p.get("exposure_won_per_unit"))  # 데이터셋 단위(억원) → 정의서 단위(원)
    if exp is not None and won is not None:
        exp = _k("LINEAR", a=0, b=exp, c=won)
    dr, mid, mx = m(p.get("dr_metric", "dr_6b")), m(p.get("pd_mid_metric", "pd_mid_6b")), m(p.get("pd_max_metric", "pd_max_6b"))
    labels_st = p.get("status_labels") or {}
    status = None
    if dr is not None and mid is not None and mx is not None:
        status = labels_st.get("over_max", "상한초과") if dr > mx else (labels_st.get("over_rep", "주의") if dr > mid else labels_st.get("normal", "일상"))
    return [{
        "base_ym": _ym(last), "monitor_status_cd": status,
        "model_id": model, "model_nm": p.get("model_name") or labels.get(model) or model, "model_segment_cd": p.get("segment", model),
        "exposure_cnt": m(p.get("obs_metric", "total_obs")), "exposure_amt": exp,
        "psi": m(p.get("psi_metric", "psi_micro")), "ar_rt": m(p.get("ar_metric", "ar_micro")),
        "actual_default_rt": dr, "pred_pd_rt": mid, "pred_pd_max_rt": mx,
        "exceed_grade_cnt": Decimal(sum(1 for r in grades if r.get("exceed_rep_pd_yn") == "Y")),
        # 정의서: 'T03 의 8월 비중 − 1월 비중' — T03 행 생성기와 같은 계산(실행 순서와 무관)
        "inclusive_prov_share_diff_pp": _inclusive_diff(ctx, p),
        "_grade": g, "_model_known": model in meta,
    }]


def _inclusive_diff(ctx: EvalContext, p: dict[str, Any]) -> Decimal | None:
    try:
        rows = risk_product_rows(ctx, {"with_retail": False, **(p.get("inclusive_params") or {})})
    except Exception:  # noqa: BLE001 — 충당금 데이터셋이 없으면 산출불가
        return None
    return rows[0].get("prov_share_diff_pp") if rows else None


@row_builder("risk_product_rows", "사업부서 T03 — 포용금융 상품별 당기 · 기준월 충당금, 비중 · 증가율 (7790 X컬럼)")
def risk_product_rows(ctx: EvalContext, p: dict[str, Any]) -> list[dict[str, Any]]:
    prov = _rows(ctx, "PROVISION_BY_PRODUCT")
    master = {r["product_code"]: r for r in _rows(ctx, "INCLUSIVE_PRODUCTS")}
    yms = sorted({str(r.get("ym")) for r in prov})
    if not yms:
        return []
    base_ym = str(p.get("base_ym") or (_rule(ctx, "INC_PROVISION_SHARE_TREND").get("base_ym")) or yms[0])
    now_ym = resolve_token(prov, "ym", "$latest")
    now = {r["product_code"]: r for r in prov if str(r["ym"]) == now_ym and not r.get("is_total")}
    jan = {r["product_code"]: r for r in prov if str(r["ym"]) == base_ym and not r.get("is_total")}
    tot_now = next((_D(r["provision"]) for r in prov if str(r["ym"]) == now_ym and r.get("is_total")), None)
    tot_jan = next((_D(r["provision"]) for r in prov if str(r["ym"]) == base_ym and r.get("is_total")), None)
    inc_now = _k("SUM", values=[_D(now[c]["provision"]) or 0 for c in master if c in now])
    inc_jan = _k("SUM", values=[_D(jan[c]["provision"]) or 0 for c in master if c in jan])
    share_now, share_jan = _k("SHARE", numerator=inc_now, denominator=tot_now), _k("SHARE", numerator=inc_jan, denominator=tot_jan)
    won = _D(p.get("provision_won_per_unit"))  # 7790 충당금 단위(백만원) → 정의서 단위(원)
    to_won = (lambda v: v if v is None or won is None else _k("LINEAR", a=0, b=v, c=won))  # noqa: E731
    retail = _rows(ctx, "RETAIL_EXPOSURE") if p.get("with_retail", True) else []
    if retail:
        r_ym = max(str(r.get("std_ym")) for r in retail)
        retail = [r for r in retail if str(r.get("std_ym")) == r_ym]
    pools = {r["pool_id"]: r for r in _rows(ctx, "RETAIL_POOL_MASTER")} if retail else {}
    ret_tot = _k("SUM", values=[_D(r["exp_amt"]) or 0 for r in retail]) if retail else None
    ret_wpd = _q(_k("WEIGHTED_AVG", values=[_D((pools.get(r["pool_id"]) or {}).get("pd_pct")) or 0 for r in retail], weights=[_D(r["exp_amt"]) or 0 for r in retail])) if retail else None
    common = {
        "base_ym": now_ym, "total_retail_exposure_amt": ret_tot, "total_weighted_pd_rt": ret_wpd,
        "comparison_base_ym": base_ym, "inclusive_provision_amt": to_won(inc_now), "jan_inclusive_provision_amt": to_won(inc_jan),
        "total_provision_amt": to_won(tot_now), "jan_total_provision_amt": to_won(tot_jan),
        "inclusive_prov_share_rt": _q(share_now), "jan_inclusive_prov_share_rt": _q(share_jan),
        "prov_share_diff_pp": _q(_k("SHARE_DELTA_PP", share1=share_now, share0=share_jan)),
        "prov_growth_rt": _q(_k("GROWTH_RATE", v0=inc_jan, v1=inc_now)),
    }
    out = []
    for code, m in sorted(master.items()):
        r_now, r_jan = now.get(code), jan.get(code)
        out.append({**common, "product_cd": code, "product_nm": (r_now or r_jan or {}).get("product_name") or m.get("product_name"), "inclusive_yn": "Y",
                    "provision_amt": to_won(_D((r_now or {}).get("provision"))), "jan_provision_amt": to_won(_D((r_jan or {}).get("provision")))})
    return out


# ═════════════════════════ 영업점 ═════════════════════════
def _office(ctx: EvalContext, p: dict[str, Any]) -> str:
    return str(p.get("office_cd") or _rule(ctx, "BRANCH_SCOPE").get("office_code") or "001068")


@row_builder("branch_status_rows", "영업점 T01 — 업적평가 항목(KPI) 행 + 사업부문(BIZ) 행")
def branch_status_rows(ctx: EvalContext, p: dict[str, Any]) -> list[dict[str, Any]]:
    office = _office(ctx, p)
    scope = _rule(ctx, "BRANCH_SCOPE")
    period = scope.get("period", "2026H2")
    scheme = {r["item_cd"]: r for r in _rows(ctx, "BRANCH_KPI_SCHEME") if r.get("period") == period}
    sc_rows = [r for r in _rows(ctx, "BRANCH_KPI_SCORE") if r.get("office_cd") == office and r.get("period") == period]
    last = max((str(r.get("as_of")) for r in sc_rows), default=None)
    scores = {r["item_cd"]: r for r in sc_rows if str(r.get("as_of")) == last}  # 최근 기준일 스냅숏만
    off = next((r for r in _rows(ctx, "BRANCH_OFFICE_MASTER") if r.get("office_cd") == office), {})
    base_ym = _ym(max((str(r.get("as_of")) for r in scores.values() if r.get("as_of")), default="")) or _ym(_asof(ctx))
    out = []
    for code, s in sorted(scheme.items(), key=lambda kv: (kv[1].get("level") or 0, kv[0])):
        sc = scores.get(code, {})
        out.append({"base_ym": base_ym, "brc": office, "row_kind_cd": "KPI", "item_cd": code, "brc_nm": off.get("office_nm"), "eval_half": period[-2:],
                    "kpi_parent_cd": s.get("parent_cd") or s.get("group_cd"), "kpi_item_nm": s.get("item_nm"), "max_score": _D(s.get("max_points")),
                    "earned_score": _D(sc.get("score")), "rule_changed_yn": "Y" if s.get("change_type") else "N", "rule_change_summary": s.get("change_summary") or None})
    for r in _rows(ctx, "BRANCH_BIZ_BALANCE"):
        if r.get("office_cd") != office:
            continue
        out.append({"base_ym": base_ym, "brc": office, "row_kind_cd": "BIZ", "item_cd": str(r.get("segment_cd")).upper(), "brc_nm": off.get("office_nm"), "eval_half": period[-2:],
                    "biz_div_nm": r.get("segment_nm"), "biz_scale_amt": _D(r.get("amount")), "biz_scale_basis_txt": r.get("measure")})
    return out


@row_builder("branch_corp_rows", "영업점 T02 — 기업여신 규모 · 등급 · 규모×등급 · 전체 집계(지점 vs 전행), 평균 등급서열")
def branch_corp_rows(ctx: EvalContext, p: dict[str, Any]) -> list[dict[str, Any]]:
    office = _office(ctx, p)
    labels = _rule(ctx, "CORP_GRADE_SCALE").get("labels") or []
    all_rows = _rows(ctx, "OBLG_GRD_DEF")
    ym = max((str(r.get("std_ym")) for r in all_rows), default=None)  # 최근 기준월만 (월별 구획이 쌓여도 중복 집계하지 않음)
    rows = [r for r in all_rows if str(r.get("std_ym")) == ym and not r.get("onlycard") and 1 <= int(r.get("Ls_nics_GRDC") or 0) <= 16]
    br = [r for r in rows if r.get("SUVMN_BRC") == office]

    def agg(sel: list[dict[str, Any]], scope: list[dict[str, Any]]) -> dict[str, Any]:
        n, amt = Decimal(len({r["brwr_no"] for r in sel})), _k("SUM", values=[_D(r["ln_bac"]) or 0 for r in sel]) or Decimal(0)
        n_all, amt_all = Decimal(len({r["brwr_no"] for r in scope})), _k("SUM", values=[_D(r["ln_bac"]) or 0 for r in scope]) or Decimal(0)
        g = [Decimal(int(r["Ls_nics_GRDC"])) for r in sel]
        return {"cnt": n, "amt": amt, "cnt_share": _q(_k("SHARE", numerator=n, denominator=n_all)), "amt_share": _q(_k("SHARE", numerator=amt, denominator=amt_all)),
                "avg": _q(_k("MEAN", values=g)) if g else None, "wavg": _q(_k("WEIGHTED_AVG", values=g, weights=[_D(r["ln_bac"]) or 0 for r in sel])) if g else None}

    groups: list[tuple[str, str, str, Callable[[dict[str, Any]], bool]]] = [("ALL", "ALL", "ALL", lambda r: True)]
    sizes = sorted({str(r.get("crdevl_pttp_dsc_f")) for r in rows})
    groups += [("SIZE", s, "ALL", (lambda s: lambda r: str(r.get("crdevl_pttp_dsc_f")) == s)(s)) for s in sizes]
    groups += [("GRADE", "ALL", labels[g - 1] if 0 < g <= len(labels) else str(g), (lambda g: lambda r: int(r["Ls_nics_GRDC"]) == g)(g)) for g in range(1, 17)]
    groups += [("SIZE_GRADE", s, labels[g - 1] if 0 < g <= len(labels) else str(g), (lambda s, g: lambda r: str(r.get("crdevl_pttp_dsc_f")) == s and int(r["Ls_nics_GRDC"]) == g)(s, g)) for s in sizes for g in range(1, 17)]
    out = []
    b_all, k_all = agg(br, br), agg(rows, rows)
    micro = p.get("micro_size", "15")
    b_micro, k_micro = agg([r for r in br if str(r.get("crdevl_pttp_dsc_f")) == micro], br), agg([r for r in rows if str(r.get("crdevl_pttp_dsc_f")) == micro], rows)
    for kind, size, grade, f in groups:
        bs, ks = [r for r in br if f(r)], [r for r in rows if f(r)]
        if not bs and not ks:
            continue
        b, k = agg(bs, br), agg(ks, rows)
        out.append({"base_ym": _ym(max((str(r.get("std_ym")) for r in rows), default="")), "brc": office, "group_kind_cd": kind, "model_segment_cd": size, "grade_cd": grade,
                    "sample_filter_txt": f"SUVMN_BRC={office}; onlycard=1 제외; Ls_nics_GRDC 1~16 외 제외 (전행 동일 필터)",
                    "brc_borrower_cnt": b["cnt"], "brc_exposure_amt": b["amt"], "brc_count_share_rt": b["cnt_share"], "brc_amount_share_rt": b["amt_share"],
                    "brc_avg_grade_ord": b["avg"], "brc_weighted_grade_ord": b["wavg"],
                    "bank_borrower_cnt": k["cnt"], "bank_exposure_amt": k["amt"], "bank_count_share_rt": k["cnt_share"], "bank_amount_share_rt": k["amt_share"],
                    "bank_avg_grade_ord": k["avg"], "bank_weighted_grade_ord": k["wavg"],
                    "small_corp_share_gap_pp": _q(_k("DIFF", a=b_micro["amt_share"], b=k_micro["amt_share"])) if kind == "ALL" else None,
                    "grade_gap_ord": _q(_k("DIFF", a=b_all["avg"], b=k_all["avg"])) if kind == "ALL" else None})
    return out


@row_builder("branch_retail_rows", "영업점 T03 — 소매여신 상품 Pool 별 지점 · 전행 익스포저 · 서민금융 비중 · 연체율 · 금액가중 PD")
def branch_retail_rows(ctx: EvalContext, p: dict[str, Any]) -> list[dict[str, Any]]:
    office = _office(ctx, p)
    pools = {r["pool_id"]: r for r in _rows(ctx, "RETAIL_POOL_MASTER")}
    all_rows = _rows(ctx, "RETAIL_EXPOSURE")
    ym = max((str(r.get("std_ym")) for r in all_rows), default=None)
    rows = [r for r in all_rows if str(r.get("std_ym")) == ym]
    br = [r for r in rows if r.get("office_cd") == office]
    limit_mn = _D((_rule(ctx, "BRANCH_SEOMIN_POLICY") or {}).get("per_borrower_max_mn"))

    def side(sel: list[dict[str, Any]]) -> dict[str, Any]:
        tot = _k("SUM", values=[_D(r["exp_amt"]) or 0 for r in sel]) or Decimal(0)
        seo = [r for r in sel if (pools.get(r["pool_id"]) or {}).get("seomin_eval")]
        seo_amt = _k("SUM", values=[_D(r["exp_amt"]) or 0 for r in seo]) or Decimal(0)
        dlq = _k("SUM", values=[_D(r["exp_amt"]) or 0 for r in sel if r.get("dlq_yn")]) or Decimal(0)
        wpd = _k("WEIGHTED_AVG", values=[_D((pools.get(r["pool_id"]) or {}).get("pd_pct")) or 0 for r in sel], weights=[_D(r["exp_amt"]) or 0 for r in sel]) if sel else None
        return {"tot": tot, "seo_amt": seo_amt, "seo_cnt": Decimal(len({r["brwr_id"] for r in seo})), "share": _q(_k("SHARE", numerator=seo_amt, denominator=tot)),
                "wpd": _q(wpd), "dlq": _q(_k("SHARE", numerator=dlq, denominator=tot))}

    b, k = side(br), side(rows)
    common = {"base_ym": _ym(max((str(r.get("std_ym")) for r in rows), default="")), "brc": office, "brc_retail_exposure_amt": b["tot"], "brc_inclusive_exposure_amt": b["seo_amt"], "brc_inclusive_borrower_cnt": b["seo_cnt"],
              "brc_inclusive_share_rt": b["share"], "brc_weighted_pd_rt": b["wpd"], "brc_overdue_rt": b["dlq"],
              "bank_retail_exposure_amt": k["tot"], "bank_inclusive_exposure_amt": k["seo_amt"], "bank_inclusive_borrower_cnt": k["seo_cnt"],
              "bank_inclusive_share_rt": k["share"], "bank_weighted_pd_rt": k["wpd"], "bank_overdue_rt": k["dlq"],
              "share_gap_pp": _q(_k("DIFF", a=b["share"], b=k["share"])),
              "annual_borrower_limit_amt": None if limit_mn is None else limit_mn * Decimal(1_000_000),
              "internal_hq_doc_expose_yn": "N"}
    out = []
    for pid, pm in sorted(pools.items()):
        out.append({**common, "product_pool_id": pid, "purpose_cd": pm.get("use_cd") or None, "score_eligible_yn": "Y" if pm.get("seomin_eval") else "N"})
    return out


@row_builder("doc_meta_rows", "S99 문서 근거 메타데이터 — 현재 문서 버전 · 원본 위치 · 발행일 · 열람 범위 · 영업점 노출 여부")
def doc_meta_rows(ctx: EvalContext, p: dict[str, Any]) -> list[dict[str, Any]]:
    from sqlalchemy import select

    from nhdip.models import Setting, source

    session = ctx.session
    visible = set(p.get("branch_visible_classes") or ["branch_ref", "gov_policy"])
    labels = (session.get(Setting, "doc_class.labels").value if session.get(Setting, "doc_class.labels") else {}) or {}
    owners = (session.get(Setting, "docs.owner_orgs").value if session.get(Setting, "docs.owner_orgs") else {}) or {}
    classes = set(p.get("doc_classes") or [])
    only_visible = bool(p.get("only_branch_visible"))
    out = []
    for origin in ("bank", "ext"):
        t = source(origin)
        for d in session.execute(select(t.document).where(t.document.is_current)).scalars():
            if (classes and d.doc_class not in classes) or (only_visible and d.doc_class not in visible):
                continue
            meta = d.meta or {}
            out.append({"doc_id": d.doc_code, "doc_version": str(d.version), "doc_title": d.title, "doc_type_cd": labels.get(d.doc_class, d.doc_class),
                        "original_file_uri": d.file_path or (f"{origin}://{d.file_name}" if d.file_name else None), "issue_dt": d.published_at,
                        "valid_from_dt": meta.get("effectiveDate") or d.published_at, "page_no": meta.get("pageCount"),
                        "access_scope": ",".join(owners.get(d.doc_code, [])) or ("전체" if origin == "ext" else "본부"),
                        "branch_visible_yn": "Y" if d.doc_class in visible else "N", "data_asof_ym": _ym(_asof(ctx)),
                        "valid_to_dt": meta.get("expiryDate"), "printed_page_no": meta.get("printedPage"), "is_inference_yn": None})
    return out
