"""사이드바 건수 (countKey) — 서버 상태 기준."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from nhdip.models import AppUser
from nhdip.views.store import get_current

from .state_service import NS_PROPOSAL_ACTION, get_ns, merged_plans


def menu_counts(session: Session, user: AppUser) -> dict[str, Any]:
    proposals = get_current(session, "proposals") or []
    acted = get_ns(session, NS_PROPOSAL_ACTION)
    from nhdip.analysis_registry import dynamic_tabs

    # 신용리스크 분석 탭 = 기존 탭 + 그 공간의 분석 에이전트 탭 (Phase C · DAG-07)
    tabs = list((get_current(session, "analysis_tabs") or {}).get("current", [])) + dynamic_tabs(session, "risk")
    plans = merged_plans(session)
    # 영업점 분석 탭 — 사용자 영업점 산출물일 때만 센다 (Q44)
    from nhdip.orgs import can_view_office
    from nhdip.scopes import office_scope, resolve_office, scoped_key

    # 다지점(B.47) — 사용자 소속 영업점(없으면 기본 지점)의 분석 탭
    target = resolve_office(session, user, None)
    btabs = get_current(session, scoped_key("branch_tabs", target, office_scope(session)[0])) or {}
    code = (btabs.get("office") or {}).get("code")
    branch_n = len(btabs.get("current") or []) if code and (not target or str(code) == str(target)) and can_view_office(session, user, code) else 0
    # 볼 수 있는 화면의 건수만 (B.32 — 다른 부서 업무량 비노출)
    from .deps import user_resources

    allowed = user_resources(session, user)
    can = (lambda r: allowed is None or r in allowed)
    out = {
        "branchAnalyses": branch_n,
        "branchAnalysesTotal": branch_n,
        "goalProposals": sum(1 for p in proposals if p["id"] not in acted),
        "analyses": len(tabs),
        "proposedPlans": sum(1 for p in plans if p.get("status") == "proposed"),
        # 클라이언트가 처리 직후 건수를 다시 계산할 때 쓰는 전체 건수
        "proposalsTotal": len(proposals),
        "analysesTotal": len(tabs),
    }
    for keys, res in ((("goalProposals", "proposalsTotal"), "proposals"), (("analyses", "analysesTotal"), "analysis_tabs"), (("proposedPlans",), "plan_actions")):
        if not can(res):
            for k in keys:
                out[k] = 0
    if user.role == "admin":
        out.update(admin_counts(session))
    return out


def admin_counts(session: Session) -> dict[str, int]:
    """관리자 처리 대기 건수 (NAV-04 · Q122) — 가입 승인 · 자료 요청 · 분석 에이전트 승인."""
    from sqlalchemy import func, select

    from nhdip.models import AnalysisAgentVersion, UploadRequest

    def n(model: Any, *where: Any) -> int:
        return int(session.scalar(select(func.count()).select_from(model).where(*where)) or 0)

    users = n(AppUser, AppUser.status == "pending")
    uploads = n(UploadRequest, UploadRequest.status == "pending")
    analyses = n(AnalysisAgentVersion, AnalysisAgentVersion.status == "pending")
    return {"adminUsers": users, "adminUploads": uploads, "adminAnalyses": analyses, "adminTodo": users + uploads + analyses}
