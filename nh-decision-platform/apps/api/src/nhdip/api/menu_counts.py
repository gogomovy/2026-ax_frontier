"""사이드바 건수 (countKey) — 서버 상태 기준."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from nhdip.models import AppUser
from nhdip.views.readiness import gate, session_lookup
from nhdip.views.store import get_current

from .state_service import NS_PROPOSAL_ACTION, get_ns, merged_plans


def menu_counts(session: Session, user: AppUser) -> dict[str, Any]:
    # 자료가 올라오기 전의 빈 제안 · 시연 탭은 '검토 필요' · 분석 건수에 세지 않는다 (views.readiness — M.19 · Q204)
    look = session_lookup(session)
    proposals = [p for p in (gate("proposals", get_current(session, "proposals")) or []) if isinstance(p, dict)]
    acted = get_ns(session, NS_PROPOSAL_ACTION)
    from nhdip.analysis_registry import dynamic_tabs

    # 신용리스크 분석 탭 = 기존 탭 + 그 공간의 분석 에이전트 탭 (Phase C · DAG-07)
    tabs = list((gate("analysis_tabs", get_current(session, "analysis_tabs"), look) or {}).get("current", [])) + dynamic_tabs(session, "risk")
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
    # 데이터 책임자 승인함(§40 STW) — 에이전트 제안 · 부서 분석 요청 중 내가 처리할 것(책임자는 부서 범위, 관리자는 전체)
    if user.role == "admin" or getattr(user, "data_steward", False):
        from nhdip.stewardship import pending_total

        try:
            out["stewardTodo"] = pending_total(session, user)
        except Exception:  # noqa: BLE001 — 건수 계산 실패가 메뉴를 막지 않는다(승인함 화면이 직접 다시 센다)
            import logging

            logging.getLogger(__name__).exception("데이터 책임자 승인함 건수 계산 실패")
            session.rollback()
            out["stewardTodo"] = 0
    if user.role == "admin":
        out.update(admin_counts(session))
    return out


def admin_counts(session: Session) -> dict[str, int]:
    """관리자 처리 대기 건수 (NAV-04 · Q122) — 가입 승인 · 자료 요청 · 분석 에이전트 승인."""
    from sqlalchemy import func, select

    from nhdip.models import AnalysisAgentVersion, UploadRequest

    def n(model: Any, *where: Any) -> int:
        return int(session.scalar(select(func.count()).select_from(model).where(*where)) or 0)

    from sqlalchemy import or_

    # 가입 승인 대기 + 인사 동기화 사번의 비밀번호 로그인 신청(Phase R · auth.PW_REQUEST)
    users = n(AppUser, or_(AppUser.status == "pending", AppUser.hr.has_key("pwRequest")))
    uploads = n(UploadRequest, UploadRequest.status == "pending")
    analyses = n(AnalysisAgentVersion, AnalysisAgentVersion.status == "pending")
    return {"adminUsers": users, "adminUploads": uploads, "adminAnalyses": analyses, "adminTodo": users + uploads + analyses}
