"""범위 실행 · 범위 산출물 (B.47 · 다지점 영업점 — 요구사항 §19 BRM-01~08, 설계 §19.25, Q97).

설정 `workflow.scopes` = {워크플로우: {rule, key, list, name, requires[], max, shared_keys[], placeholder}}.
- 기본 범위 = 규칙 `rule` 본문의 `key` 값(예: BRANCH_SCOPE.office_code) — 기존 산출물 키 그대로.
- 추가 범위 = 규칙 본문 `list` 값(예: office_codes) 중 기본 범위를 뺀 것 — 산출물 '<키>@<값>', 지표 값 '<지표>@<값>'.
"""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from nhdip.models import Rule, RuleVersion, Setting

SCOPE_VALUE = re.compile(r"^[A-Za-z0-9_-]{1,20}$")  # 산출물 키에 붙는 값 — 사용자 입력(주소 인자)도 이 형식만


def scope_specs(session: Session) -> dict[str, dict[str, Any]]:
    s = session.get(Setting, "workflow.scopes")
    v = s.value if s is not None and isinstance(s.value, dict) else {}
    return {k: spec for k, spec in v.items() if isinstance(spec, dict) and spec.get("rule") and spec.get("key")}


def scope_spec(session: Session, workflow_code: str) -> dict[str, Any] | None:
    return scope_specs(session).get(workflow_code)


def scope_values(session: Session, spec: dict[str, Any], *, limit: bool = True) -> tuple[str | None, list[str]]:
    """(기본 범위 값, 추가 범위 값들) — 규칙 본문에서 읽는다. 목록이 없으면 추가 범위 없음. 형식이 맞지 않는 값은 뺀다.
    limit=True 면 상한(`max`, 기본 범위 포함)까지만 — 상한 밖 값은 limit=False 로 읽어 실행 요약 · 알림에 남긴다(BRM-07)."""
    rule = session.get(Rule, spec["rule"])
    rv = session.execute(select(RuleVersion).where(RuleVersion.rule_code == spec["rule"], RuleVersion.version == rule.active_version)).scalar() if rule else None
    body = rv.body if rv is not None and isinstance(rv.body, dict) else {}
    primary = body.get(spec["key"])
    primary = str(primary) if primary not in (None, "") else None
    values = [str(v) for v in (body.get(spec.get("list", "")) or []) if v not in (None, "") and SCOPE_VALUE.match(str(v))]
    if spec.get("name") == "office" and spec.get("from_owners", True):
        values += owner_offices(session)  # 관리자가 영업점을 골라 올린 자료가 있으면 그 영업점도 계산한다(§33 OWN — 규칙에 지점을 더하지 않아도)
    if spec.get("from_data", True) and spec.get("requires"):
        values += data_scopes(session, spec)  # 필요한 자료에 행이 있는 범위(예: 득점 현황 · 사무소 마스터에 다 있는 지점) — 지역 영업점 통합 화면이 지점을 하나씩 등록하지 않아도
    extras = [v for v in dict.fromkeys(values) if v != primary]
    return primary, (extras[: scope_cap(spec)] if limit else extras)


def data_scopes(session: Session, spec: dict[str, Any]) -> list[str]:
    """설정 requires(['자료 이름.열', ...])의 모든 자료에 값이 있는 범위 값 — 교집합, 자료 순서대로. 자료가 없으면 빈 목록."""
    from nhdip.data.datasets import current_rows
    from nhdip.data.sources import Resolver

    res = Resolver(session)
    common: list[str] | None = None
    for req in spec.get("requires") or []:
        name, _, col = str(req).rpartition(".")
        d = res.resolve(name) if name else None
        if d is None or not col:
            return []
        col = res.aliases(name, d).get(col, col)
        _, rows = current_rows(session, d)
        vals = [str(r.get(col)) for r in rows if r.get(col) not in (None, "") and SCOPE_VALUE.match(str(r.get(col)))]
        vals = list(dict.fromkeys(vals))
        common = vals if common is None else [v for v in common if v in set(vals)]
    return common or []


def owner_offices(session: Session) -> list[str]:
    """현재 판 자료(데이터셋 · 문서)를 가진 영업점의 사무소 코드 — 소유 조직이 영업점(BRANCH)인 것."""
    from nhdip.models import OrgUnit, source
    from nhdip.orgs import office_code_of

    codes: set[str] = set()
    for origin in ("bank", "ext"):
        t = source(origin)
        codes |= {c for c in session.execute(select(t.version.owner_org).where(t.version.is_current, t.version.owner_org.is_not(None)).distinct()).scalars()}
    if not codes:
        return []
    branches = session.execute(select(OrgUnit.code).where(OrgUnit.code.in_(codes), OrgUnit.unit_type == "BRANCH").order_by(OrgUnit.sort, OrgUnit.code)).scalars()
    return [o for o in (office_code_of(session, c) for c in branches) if SCOPE_VALUE.match(o)]


def llm_scopes(session: Session, workflow_code: str, values: list[str], limit: Any) -> list[str]:
    """이번 실행에서 LLM(변화 판단 · 플래너 · 서술)을 쓸 추가 범위 (BRM-07 · 지점 수에 따른 비용 한도).

    설정 `narrate_max` 곳까지 — 그 범위의 서술이 없거나 가장 오래된 범위부터 돌아가며 고른다(실행마다 다른 지점이 차례로 갱신).
    나머지 범위는 규칙 판단 · 기존 문장 유지. 음수 · 없음 = 제한 없음, 0 = 추가 범위는 LLM 을 쓰지 않음.
    """
    from sqlalchemy import func

    from nhdip.models import AgentDecision

    try:
        n = int(limit)
    except (TypeError, ValueError):
        return list(values)
    if n < 0:
        return list(values)
    if n == 0 or not values:
        return []
    ins = AgentDecision.detail["insight"].astext
    last: dict[str, Any] = {}
    for insight, at in session.execute(
        select(ins, func.max(AgentDecision.at)).where(AgentDecision.workflow_code == workflow_code, AgentDecision.decision == "narrated", ins.like("%@%")).group_by(ins)
    ).all():
        v = str(insight).rsplit("@", 1)[1]
        if v not in last or at > last[v]:
            last[v] = at
    order = sorted(range(len(values)), key=lambda i: (values[i] in last, last.get(values[i]) or 0, i))
    return [values[i] for i in order[:n]]


def scope_cap(spec: dict[str, Any]) -> int:
    """추가 범위 상한 — 설정 `max` 는 기본 범위를 포함한 수."""
    try:
        return max(0, int(spec.get("max", 20)) - 1)
    except (TypeError, ValueError):
        return 19


def office_scope(session: Session) -> tuple[str | None, list[str]]:
    """영업점 범위(name=office) — (기본 지점, 계산 대상 지점 전체). 설정이 없으면 (None, [])."""
    for spec in scope_specs(session).values():
        if spec.get("name") == "office":
            primary, extras = scope_values(session, spec)
            return primary, ([primary] if primary else []) + extras
    return None, []


def scoped_key(key: str, value: str | None, primary: str | None) -> str:
    """범위 산출물 키 — 기본 범위(또는 범위 없음)는 기존 키."""
    return key if not value or value == primary else f"{key}@{value}"


def resolve_office(session: Session, user: Any, office: str | None) -> str | None:
    """화면이 볼 지점 — 주소 인자 → 사용자 소속 영업점 → 기본 지점. 열람 가능 여부는 호출하는 쪽이 can_view_office 로 검사."""
    from nhdip.orgs import branch_of, office_code_of

    if office:
        return str(office)
    br = branch_of(session, user.org_code)
    if br is not None:
        return office_code_of(session, br.code)
    return office_scope(session)[0]
