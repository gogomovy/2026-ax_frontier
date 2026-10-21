"""업무 소속 — 가입 승인 때 관리자가 정하는 '플랫폼 화면이 붙는 조직 단위' (사용자 · 조직 관리).

인사 조직(.dat)의 사무소 · 팀은 수천 곳이지만 화면 권한은 몇몇 단위에만 붙는다. 영역은 네 가지다.
  hq     — 종합기획부: 설정 ui.scopes.hq 의 단위 조직
  dept   — 사업부서:   설정 ui.scopes.dept 의 단위 조직
  region — 영업본부:   조직 유형 REGION(지역본부)
  branch — 영업점:     조직 유형 BRANCH(영업점) — 계산 대상 지점(ui.scopes.branch)을 먼저, 나머지는 검색
이름은 설정(ui.scopes 의 label)에서 오고 비었을 때만 기본 이름을 쓴다.

관리자가 정한 소속은 사용자 hr.orgAssigned 에 남겨 인사 동기화가 사무소 기준으로 되돌리지 않는다(orgsync).
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from nhdip.models import AppUser, utcnow
from nhdip.orgs import OrgIndex, OrgNode, type_labels

GROUP_ORDER = ("hq", "dept", "region", "branch")
DEFAULT_LABEL = {"hq": "종합기획부", "dept": "사업부서", "region": "영업본부", "branch": "영업점"}
GROUP_TYPES = {"region": ("REGION",), "branch": ("BRANCH",)}
ASSIGNED = "orgAssigned"  # app_user.hr 안 — {code, by, at, from}
REGION_LIST_MAX = 200  # 넘으면 목록 대신 검색


class Affiliation:
    """영역별 단위 — 요청 하나 동안 조직 전체 · 설정을 한 번만 읽는다."""

    def __init__(self, session: Session) -> None:
        from nhdip.ui_config import value_of

        self.idx = OrgIndex.load(session)
        self.lbl = type_labels(session)
        scopes = value_of(session, "ui.scopes") or {}
        self.labels = {k: str((scopes.get(k) or {}).get("label") or DEFAULT_LABEL[k]) for k in GROUP_ORDER}
        self.units: dict[str, list[str]] = {}
        for k in ("hq", "dept", "branch"):
            codes = [u.get("org") for u in (scopes.get(k) or {}).get("units") or [] if isinstance(u, dict) and u.get("org")]
            self.units[k] = [c for c in dict.fromkeys(codes) if c in self.idx.by]
        self.units["region"] = sorted((r.code for r in self.idx.by.values() if r.unit_type == "REGION" and r.active), key=lambda c: self.idx.order[c])

    def option(self, code: str) -> dict[str, Any] | None:
        r = self.idx.by.get(code)
        if r is None:
            return None
        return {"code": r.code, "name": r.name, "unitType": r.unit_type, "unitLabel": self.lbl.get(r.unit_type or "", "조직"), "active": r.active,
                "path": [x.name for x in self.idx.path(r.code)[:-1]]}

    def groups(self) -> list[dict[str, Any]]:
        out = []
        for k in GROUP_ORDER:
            codes = self.units[k]
            search = {"types": list(GROUP_TYPES[k])} if k == "branch" or (k == "region" and len(codes) > REGION_LIST_MAX) else None
            shown = codes[:REGION_LIST_MAX] if k == "region" else codes
            out.append({"key": k, "label": self.labels[k], "options": [o for o in (self.option(c) for c in shown) if o and o["active"]], "search": search})
        return out

    def classify(self, code: str | None) -> dict[str, Any] | None:
        """그 조직이 속한 영역과 단위 — 경로(자기 → 위)에서 처음 맞는 것. 종기부 · 사업부서 단위 아래 팀은 그 단위로,
        영업점 · 지역본부는 유형으로. 어디에도 없으면 None(화면이 붙지 않는 인사 조직일 수 있다)."""
        if not code or code not in self.idx.by:
            return None
        chain: list[OrgNode] = self.idx.path(code)[::-1]
        for r in chain:
            for k in ("hq", "dept"):
                if r.code in self.units[k]:
                    return {"group": k, "label": self.labels[k], "code": r.code}
        for k in ("branch", "region"):
            hit = next((r for r in chain if (r.unit_type or "") in GROUP_TYPES[k]), None)
            if hit is not None:
                return {"group": k, "label": self.labels[k], "code": hit.code}
        return None


def assigned_of(user: AppUser) -> dict[str, Any] | None:
    v = (user.hr or {}).get(ASSIGNED)
    return v if isinstance(v, dict) else None


def assign(user: AppUser, code: str, actor: str) -> dict[str, Any]:
    """관리자가 정한 소속 — 소속을 바꾸고 표지를 남긴다(인사 동기화가 되돌리지 않음). 감사 기록용 {from, to} 를 돌려준다."""
    prev = user.org_code
    user.org_code = code
    user.hr = {**(user.hr or {}), ASSIGNED: {"code": code, "by": actor, "at": utcnow().isoformat(), "from": prev}}
    return {"from": prev, "to": code}


def hr_office(user: AppUser, idx: OrgIndex) -> str | None:
    """인사 동기화 기준 소속 — 사무소, 없으면 상위(1 → 2 → 3) 중 조직에 있는 첫 코드."""
    hr = user.hr or {}
    return next((c for c in (hr.get("officeCode"), hr.get("parent1Code"), hr.get("parent2Code"), hr.get("parent3Code")) if c and c in idx.by), None)


def follow_hr(user: AppUser, idx: OrgIndex) -> dict[str, Any] | None:
    """관리자 지정을 풀고 인사 기준 소속으로 되돌린다. 인사 소속을 모르면(가입 신청 사용자) 표지만 지운다."""
    hr = {k: v for k, v in (user.hr or {}).items() if k != ASSIGNED}
    prev, office = user.org_code, hr_office(user, idx)
    user.hr = hr
    if office and office != prev:
        user.org_code = office
        return {"from": prev, "to": office}
    return None
