"""조직 트리 — 유형(본부 · 부 · 국 · 팀 · 지역본부 · 영업점) · 허용 상위 유형 검증 · 깊이 재계산."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from nhdip.models import OrgUnit, Setting

DEFAULT_TYPES = [
    {"code": "HQ_DIV", "label": "본부", "parents": []},
    {"code": "DEPT", "label": "부", "parents": ["HQ_DIV"]},
    {"code": "BUREAU", "label": "국", "parents": ["DEPT", "REGION"]},
    {"code": "TEAM", "label": "팀", "parents": ["BUREAU", "DEPT"]},
    {"code": "REGION", "label": "지역본부", "parents": []},
    {"code": "BRANCH", "label": "영업점", "parents": ["REGION"]},
]


class OrgError(ValueError):
    pass


def unit_types(session: Session) -> list[dict[str, Any]]:
    s = session.get(Setting, "org.unit_types")
    return s.value if s and isinstance(s.value, list) else DEFAULT_TYPES


def type_labels(session: Session) -> dict[str, str]:
    return {t["code"]: t["label"] for t in unit_types(session)}


def validate_parent(session: Session, unit_type: str, parent_code: str | None, self_code: str | None = None) -> OrgUnit | None:
    types = {t["code"]: t for t in unit_types(session)}
    if unit_type not in types:
        raise OrgError(f"알 수 없는 조직 유형: {unit_type}")
    allowed = types[unit_type].get("parents") or []
    if not parent_code:
        if allowed and unit_type not in ("HQ_DIV", "REGION"):
            raise OrgError(f"{types[unit_type]['label']} 은(는) 상위 조직이 필요합니다 ({', '.join(types[p]['label'] for p in allowed if p in types)})")
        return None
    parent = session.get(OrgUnit, parent_code)
    if not parent:
        raise OrgError("상위 조직 없음")
    if self_code:
        cur: OrgUnit | None = parent
        while cur:
            if cur.code == self_code:
                raise OrgError("자기 자신이나 하위 조직을 상위로 지정할 수 없습니다")
            cur = session.get(OrgUnit, cur.parent_code) if cur.parent_code else None
    if parent.unit_type not in allowed:
        lbl = type_labels(session)
        raise OrgError(f"{lbl.get(unit_type, unit_type)} 의 상위는 {', '.join(lbl.get(p, p) for p in allowed) or '없음(최상위)'} 이어야 합니다")
    return parent


def recompute_levels(session: Session) -> int:
    """상위 조직 기준 깊이(1=최상위) 재계산. 바뀐 조직 수를 돌려준다."""
    rows = session.execute(select(OrgUnit)).scalars().all()
    by = {o.code: o for o in rows}
    changed = 0

    def depth(o: OrgUnit, seen: set[str]) -> int:
        if not o.parent_code or o.parent_code not in by or o.code in seen:
            return 1
        return depth(by[o.parent_code], seen | {o.code}) + 1

    for o in rows:
        d = depth(o, set())
        if o.level != d:
            o.level = d
            changed += 1
    return changed


def depth_labels(session: Session, orgs: list[OrgUnit]) -> list[str]:
    """가입 화면 단계별 선택 라벨 — 같은 깊이에 있는 유형 라벨을 모아 표시 (예: '본부·지역본부')."""
    lbl = type_labels(session)
    out: list[str] = []
    for d in range(1, max((o.level for o in orgs), default=0) + 1):
        names = list(dict.fromkeys(lbl.get(o.unit_type or "", "조직") for o in orgs if o.level == d))
        out.append("·".join(names) or "조직")
    return out


def org_chain(session: Session, org_code: str) -> list[OrgUnit]:
    """조직 → 상위 조직 순서의 경로 (권한 상속 · 문서 소유 부서 판정)."""
    chain: list[OrgUnit] = []
    seen: set[str] = set()
    cur = session.get(OrgUnit, org_code)
    while cur and cur.code not in seen:
        chain.append(cur)
        seen.add(cur.code)
        cur = session.get(OrgUnit, cur.parent_code) if cur.parent_code else None
    return chain


# ── 부서 데이터 책임자 범위 (UPL-04 · Q107) ─────────────────────
STEWARD_SCOPE_TYPES = ("DEPT", "REGION")


def steward_scope(session: Session, org_code: str) -> OrgUnit | None:
    """책임자가 맡는 부서 — 소속 경로에서 가장 가까운 부(DEPT) · 지역본부(REGION). 없으면 경로의 맨 위 조직."""
    chain = org_chain(session, org_code)
    return next((o for o in chain if o.unit_type in STEWARD_SCOPE_TYPES), chain[-1] if chain else None)


def in_steward_scope(session: Session, steward: Any, org_code: str | None) -> bool:
    """요청자 조직이 책임자 부서 아래(그 부서 포함)인지."""
    if not org_code or not getattr(steward, "data_steward", False):
        return False
    scope = steward_scope(session, steward.org_code)
    return scope is not None and scope.code in {o.code for o in org_chain(session, org_code)}


# ── 영업점 범위 (B.29 · Q43/Q44) ─────────────────────────────
def office_code_of(session: Session, org_code: str) -> str:
    """조직 코드 → 사무소 코드. 기본은 조직 코드 그대로, 다르면 설정 branch.office_codes 로 매핑."""
    s = session.get(Setting, "branch.office_codes")
    mapping = s.value if s and isinstance(s.value, dict) else {}
    return str(mapping.get(org_code, org_code))


def org_of_office(session: Session, office_code: str) -> OrgUnit | None:
    s = session.get(Setting, "branch.office_codes")
    mapping = s.value if s and isinstance(s.value, dict) else {}
    for org, off in mapping.items():
        if str(off) == str(office_code):
            return session.get(OrgUnit, org)
    return session.get(OrgUnit, office_code)


def branch_of(session: Session, org_code: str) -> OrgUnit | None:
    """사용자 조직 경로에서 영업점(BRANCH) 단위 — 없으면 None(지역본부 · 본부 · 관리자)."""
    return next((o for o in org_chain(session, org_code) if o.unit_type == "BRANCH"), None)


def can_view_office(session: Session, user: Any, office_code: str) -> bool:
    """영업점 산출물 열람 범위 — 관리자 전체, 영업점 직원은 자기 영업점만, 그 외(지역본부 등)는 상위 조직이 겹치는 영업점."""
    if getattr(user, "role", None) == "admin":
        return True
    chain = org_chain(session, user.org_code)
    br = next((o for o in chain if o.unit_type == "BRANCH"), None)
    if br is not None:
        return office_code_of(session, br.code) == str(office_code)
    target = org_of_office(session, office_code)
    if target is None:
        return False
    mine = {o.code for o in chain}
    return any(o.code in mine for o in org_chain(session, target.code)[1:])


# ═════════════════════════ 자료 소유 조직 (요구사항 §33 OWN) ═════════════════════════
class OwnerError(ValueError):
    pass


def resolve_owner(session: Session, user: Any, requested: str | None = None) -> str | None:
    """올린 자료의 소유 조직 — 관리자는 고른 팀 · 영업점(빈 값 = 전행 공통), 그 밖의 사용자는 자기 소속(회원가입 때 정한 팀).
    관리자가 아닌 사용자가 다른 조직을 고르면 거절한다."""
    want = (requested or "").strip() or None
    if user is None:
        return want
    if getattr(user, "role", None) != "admin":
        if want and want != user.org_code:
            raise OwnerError("자료 소유 조직은 관리자만 고를 수 있습니다 — 내 소속으로 올라갑니다")
        return user.org_code
    if want is None:
        return None
    org = session.get(OrgUnit, want)
    if org is None or not org.active:
        raise OwnerError(f"없는 조직이거나 쓰지 않는 조직입니다: {want}")
    return org.code


def is_branch(session: Session, org_code: str | None) -> bool:
    if not org_code:
        return False
    o = session.get(OrgUnit, org_code)
    return o is not None and o.unit_type == "BRANCH"


def owner_json(session: Session, org_code: str | None, cache: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """목록 표시용 — {code, name, unitType}. 없으면 None(전행 공통)."""
    if not org_code:
        return None
    if cache is not None and org_code in cache:
        return cache[org_code]
    o = session.get(OrgUnit, org_code)
    out = {"code": org_code, "name": o.name if o else org_code, "unitType": o.unit_type if o else None}
    if cache is not None:
        cache[org_code] = out
    return out
