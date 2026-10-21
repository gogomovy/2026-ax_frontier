"""영업본부(지역본부) 통합 업적평가 (요구사항 §37 RGN) — 지역본부 아래 영업점의 업적평가 산출물을 한 화면에 모은다.

계산은 영업점 흐름(wf_branch_kpi)의 지점별 범위 실행이 이미 한다(산출물 'branch_dashboard@<지점>'). 여기서는 읽어서 비교 · 순위만 만든다
(새 수치를 만들지 않는다 — 점수 · 만점은 그대로, 평균 · 순위만 이 자리에서 센다).

열람 범위
  관리자          모든 지역본부(주소 인자 region 으로 고름, 없으면 첫 지역본부)
  지역본부 직원    자기 지역본부 하나(다른 region 인자는 거절)
  영업점 직원      없음(화면 권한에서 빠진다 — 설정 screen.deny_unit_types)
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from nhdip.models import OrgUnit


class RegionDenied(PermissionError):
    pass


def regions(session: Session) -> list[OrgUnit]:
    return list(session.execute(select(OrgUnit).where(OrgUnit.unit_type == "REGION", OrgUnit.active).order_by(OrgUnit.sort, OrgUnit.code)).scalars())


def region_of_user(session: Session, user: Any, requested: str | None) -> OrgUnit | None:
    """볼 지역본부 — 관리자는 고른 것(없으면 첫 지역본부), 그 밖은 소속 경로의 지역본부. 영업점 직원 · 다른 지역 요청은 거절."""
    from nhdip.orgs import org_chain

    if getattr(user, "role", None) == "admin":
        all_ = regions(session)
        if requested:
            hit = next((r for r in all_ if r.code == requested), None)
            if hit is None:
                raise RegionDenied("없는 지역본부입니다")
            return hit
        return all_[0] if all_ else None
    chain = org_chain(session, user.org_code)
    if any(o.unit_type == "BRANCH" for o in chain):
        raise RegionDenied("영업점 직원은 자기 영업점 화면만 볼 수 있습니다")
    mine = next((o for o in chain if o.unit_type == "REGION"), None)
    if mine is None:
        raise RegionDenied("지역본부 소속이 아닙니다")
    if requested and requested != mine.code:
        raise RegionDenied("다른 지역본부의 영업점은 볼 수 없습니다")
    return mine


def branches_of(session: Session, region: OrgUnit) -> list[OrgUnit]:
    """지역본부 아래(하위 경로 전체)의 영업점."""
    out: list[OrgUnit] = []
    frontier = [region.code]
    seen = {region.code}
    while frontier:
        kids = list(session.execute(select(OrgUnit).where(OrgUnit.parent_code.in_(frontier), OrgUnit.active).order_by(OrgUnit.sort, OrgUnit.code)).scalars())
        frontier = []
        for k in kids:
            if k.code in seen:
                continue
            seen.add(k.code)
            frontier.append(k.code)
            if k.unit_type == "BRANCH":
                out.append(k)
    return out


def _val(x: Any) -> Decimal | None:
    v = x.get("value") if isinstance(x, dict) else x
    if v in (None, "", "–", "-"):
        return None
    try:
        return Decimal(str(v).replace(",", ""))
    except (InvalidOperation, ValueError):
        return None


def _num(d: Decimal | None) -> float | None:
    return None if d is None else float(d)


def _row(code: str, org: OrgUnit | None, payload: Any, has_data: bool = True) -> dict[str, Any]:
    from nhdip.views.template import strip_tpl

    # 그 지점 자료(사무소 마스터 · 득점 현황)가 없으면 산출물이 있어도 계산 전 — 기본 지점은 자료 없이도 기본 실행이 0점 틀을 만든다
    p = strip_tpl(payload) if isinstance(payload, dict) and has_data else None
    sc = (p or {}).get("scorecard") or {}
    total, mx = _val(sc.get("total")), _val(sc.get("max"))
    after, adj, up = _val(sc.get("totalAfter")), _val(sc.get("adjustments")), _val(sc.get("uplift"))
    computed = total is not None
    groups = []
    for g in sc.get("groups") or []:
        if not isinstance(g, dict):
            continue
        gs, gm = _val(g.get("score")), _val(g.get("max"))
        groups.append({"code": g.get("code"), "label": g.get("label"), "kind": g.get("kind"), "score": _num(gs), "max": _num(gm),
                       "rate": _num(round(gs / gm * 100, 1)) if gs is not None and gm else None})
    alerts = [a for a in (p or {}).get("alerts") or [] if isinstance(a, dict)]
    office = (p or {}).get("office") or {}
    figs = (p or {}).get("figures") or {}
    return {
        "code": code,
        "name": office.get("name") or (org.name if org else code),
        "orgCode": org.code if org else None,
        "available": computed,
        "total": _num(total), "max": _num(mx), "adjustments": _num(adj), "totalAfter": _num(after), "uplift": _num(up),
        "rate": _num(round(total / mx * 100, 1)) if computed and mx else None,
        "groups": groups,
        "avgGrade": _num(_val(figs.get("br_avg_grade"))),
        "alerts": [{"title": a.get("title"), "severity": a.get("severity"), "tabKey": a.get("tabKey")} for a in alerts[:3]],
        "alertCount": len(alerts),
        "periodLabel": (p or {}).get("periodLabel"),
        "asOfLabel": (p or {}).get("asOfLabel"),
    }


def region_kpi(session: Session, user: Any, requested: str | None = None) -> dict[str, Any]:
    """지역본부 통합 업적평가 — 지점별 총점 · 만점 · 득점률 · 그룹 점수 · 주의 알림, 지역 평균 · 순위."""
    from nhdip.orgs import can_view_office, office_code_of, org_of_office
    from nhdip.scopes import office_data, office_scope, scoped_key
    from nhdip.views.store import get_current

    region = region_of_user(session, user, requested)
    if region is None:
        return {"region": None, "regions": [], "branches": [], "summary": {"branches": 0, "computed": 0}}
    primary, offices = office_scope(session)
    orgs = branches_of(session, region)
    codes = [office_code_of(session, o.code) for o in orgs]
    # 지점 계산 대상(자료가 있는 지점) 가운데 조직표에서 이 지역본부 아래인 지점 — 조직표에 지점이 아직 없어도 산출물로 보이게
    for c in offices:
        if c in codes:
            continue
        o = org_of_office(session, c)
        if o is not None and o.code in {x.code for x in orgs}:
            codes.append(c)
    rows = []
    by_code = {office_code_of(session, o.code): o for o in orgs}
    with_data = office_data(session)
    for code in dict.fromkeys(codes):
        if not can_view_office(session, user, code):
            continue
        rows.append(_row(code, by_code.get(code), get_current(session, scoped_key("branch_dashboard", code, primary)), with_data is None or code in with_data))
    done = [r for r in rows if r["available"]]
    rank_key = lambda r: (-(r["totalAfter"] if r["totalAfter"] is not None else r["total"] or 0), r["code"])  # noqa: E731
    for i, r in enumerate(sorted(done, key=rank_key), start=1):
        r["rank"] = i
    rows.sort(key=lambda r: (r.get("rank") or 10**6, r["code"]))

    def avg(vals: list[float | None]) -> float | None:
        xs = [v for v in vals if v is not None]
        return round(sum(xs) / len(xs), 2) if xs else None

    group_avgs: dict[str, dict[str, Any]] = {}
    for r in done:
        for g in r["groups"]:
            ga = group_avgs.setdefault(str(g["code"]), {"code": g["code"], "label": g["label"], "kind": g["kind"], "scores": [], "max": g["max"]})
            ga["scores"].append(g["score"])
    groups = [{**{k: v for k, v in g.items() if k != "scores"}, "avg": avg(g["scores"])} for g in group_avgs.values()]
    top = done and min(done, key=rank_key)
    period = next((r["periodLabel"] for r in done if r.get("periodLabel")), None)
    return {
        "region": {"code": region.code, "name": region.name},
        "regions": [{"code": r.code, "name": r.name} for r in regions(session)] if getattr(user, "role", None) == "admin" else [{"code": region.code, "name": region.name}],
        "periodLabel": period,
        "asOfLabel": next((r["asOfLabel"] for r in done if r.get("asOfLabel")), None),
        "branches": rows,
        "groups": groups,
        "summary": {
            "branches": len(rows), "computed": len(done),
            "avgTotal": avg([r["total"] for r in done]), "avgRate": avg([r["rate"] for r in done]), "avgTotalAfter": avg([r["totalAfter"] for r in done]),
            "alerts": sum(r["alertCount"] for r in done),
            "top": {"code": top["code"], "name": top["name"]} if top else None,
        },
    }
