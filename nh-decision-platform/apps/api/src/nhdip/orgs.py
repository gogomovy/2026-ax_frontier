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
