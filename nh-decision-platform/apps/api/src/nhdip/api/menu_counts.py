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
    tabs = (get_current(session, "analysis_tabs") or {}).get("current", [])
    plans = merged_plans(session)
    return {
        "goalProposals": sum(1 for p in proposals if p["id"] not in acted),
        "analyses": len(tabs),
        "proposedPlans": sum(1 for p in plans if p.get("status") == "proposed"),
        # 클라이언트가 처리 직후 건수를 다시 계산할 때 쓰는 전체 건수
        "proposalsTotal": len(proposals),
        "analysesTotal": len(tabs),
    }
