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
