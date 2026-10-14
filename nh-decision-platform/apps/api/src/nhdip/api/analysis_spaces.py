"""부서 분석 공간 화면 API (Phase C · DAG-07 · Q101) — 분석 목록 · 보고서를 레지스트리에서.

- `GET /screens/analysis/spaces` — 볼 수 있는 분석 공간(이름 · 경로 · 탭 수 · 분석 에이전트 만들기 가능 여부)
- `GET /screens/analysis/{space}/tabs?office=` — 기존 탭 + 분석 에이전트 탭 (공간 탭 리소스)
- `GET /screens/analysis/{space}/reports/{tab}?office=` — 보고서 (공간 보고서 리소스). 범위 공간(영업점)은 지점 산출물
기존 경로(`/screens/analysis-tabs` · `/screens/reports/*` · `/screens/branch/*`)는 그대로 둔다.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from nhdip.analysis_registry import agent_for_tab, report_key, space, space_tabs, spaces
from nhdip.db import get_session
from nhdip.models import AppUser
from nhdip.views.store import get_current_row

from .deps import current_user, user_resources
from .screens import OFFICE_Q, _producer, branch_artifact

router = APIRouter(prefix="/screens/analysis", tags=["screens"])


def _can(allowed: set[str] | None, res: str | None) -> bool:
    return allowed is None or (bool(res) and res in allowed)


def _space_or_404(session: Session, key: str, user: AppUser, resource_key: str) -> tuple[dict[str, Any], set[str] | None]:
    sp = space(session, key)
    allowed = user_resources(session, user)
    if sp is None:
        raise HTTPException(404, "분석 공간 없음")
    if not _can(allowed, sp.get(resource_key) or sp.get("resource")):
        raise HTTPException(403, f"이 화면에 대한 권한이 없습니다 ({sp.get(resource_key) or sp.get('resource')})")
    return sp, allowed


def _builtin(session: Session, user: AppUser, sp: dict[str, Any], office: str | None) -> dict[str, Any] | None:
    if not sp.get("tabs"):
        return {"current": [], "previous": []}
    if sp.get("scoped") == "office":
        return branch_artifact(session, user, sp["tabs"], office) or {"current": [], "previous": []}
    return None  # space_tabs 가 산출물을 읽음


@router.get("/spaces")
def list_spaces(session: Session = Depends(get_session), user: AppUser = Depends(current_user)):
    allowed = user_resources(session, user)
    out = []
    for k, sp in spaces(session).items():
        if not _can(allowed, sp.get("tabsResource") or sp.get("resource")):
            continue
        tabs = space_tabs(session, sp, _builtin(session, user, sp, None))
        out.append({"key": k, "label": sp.get("label"), "path": sp.get("path") or f"/analysis/{k}", "tabs": len(tabs["current"]),
                    "dynamic": sum(1 for t in tabs["current"] if t.get("dynamic")), "builder": bool(sp.get("builder")) and _can(allowed, "analysis_builder")})
    return out


@router.get("/{space_key}/tabs")
def tabs(space_key: str, office: str | None = OFFICE_Q, session: Session = Depends(get_session), user: AppUser = Depends(current_user)):
    sp, allowed = _space_or_404(session, space_key, user, "tabsResource")
    out = space_tabs(session, sp, _builtin(session, user, sp, office))
    return {**out, "space": {"key": sp["key"], "label": sp.get("label"), "path": sp.get("path") or f"/analysis/{sp['key']}", "scoped": sp.get("scoped")},
            "builder": {"allowed": bool(sp.get("builder")) and _can(allowed, "analysis_builder")}}


@router.get("/{space_key}/reports/{tab_key}")
def report(space_key: str, tab_key: str, office: str | None = OFFICE_Q, session: Session = Depends(get_session), user: AppUser = Depends(current_user)):
    sp, _ = _space_or_404(session, space_key, user, "resource")
    key = report_key(sp, tab_key)
    if tab_key.startswith("an-"):
        a = agent_for_tab(session, tab_key)
        if a is None or a.space != sp["key"]:
            raise HTTPException(404, "보고서 없음")
        row = get_current_row(session, key)
        payload = row.payload if row is not None else None
        extra = {"analysisAgent": {"code": a.code, "status": a.status, "version": a.version}}
    elif sp.get("scoped") == "office":
        payload = branch_artifact(session, user, key, office)
        extra = {}
    else:
        row = get_current_row(session, key)
        payload = row.payload if row is not None else None
        extra = {}
    if payload is None:
        raise HTTPException(404, "보고서 없음")
    return {**payload, **extra, "workflow": _producer(session, key)}
