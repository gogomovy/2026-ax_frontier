"""전파 경로 API (F.16 · PROP-03) — 서버에서 계산한 현재 트리."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from nhdip.db import get_session
from nhdip.models import AppUser
from nhdip.views.cascade import current_tree, find_node

from .deps import require_resource

router = APIRouter(prefix="/cascade", tags=["cascade"])


@router.get("/tree")
def cascade_tree(session: Session = Depends(get_session), _: AppUser = Depends(require_resource("cascade"))):
    """기본 트리 + 경영목표 처리 + 진행사업 등록/전파 상태를 반영한 전체 트리."""
    return current_tree(session)


@router.get("/{goal_id}/impact")
def cascade_impact(goal_id: str, value: float | None = None, session: Session = Depends(get_session), _: AppUser = Depends(require_resource("cascade"))):
    """목표 변경 영향(6.6.3) — 다시 계산될 지표 · 화면, 재검토할 수행방안, 전파 노드, 새 값의 정합성."""
    from nhdip.views.goal_impact import impact

    return impact(session, goal_id, value)


@router.get("/{goal_id}")
def cascade_goal(goal_id: str, session: Session = Depends(get_session), _: AppUser = Depends(require_resource("cascade"))):
    """목표(또는 수행방안) 한 개의 하위 전파 경로."""
    node = find_node(current_tree(session), goal_id)
    if node is None:
        raise HTTPException(404, "전파 경로 없음")
    return node
