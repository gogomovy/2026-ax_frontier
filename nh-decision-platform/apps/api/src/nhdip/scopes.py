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
    extras = [v for v in dict.fromkeys(values) if v != primary]
    return primary, (extras[: scope_cap(spec)] if limit else extras)


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
