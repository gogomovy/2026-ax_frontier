"""경영목표 처리 · 진행사업 상태 API (F.8 · F.15~17) — 프론트 Provider 동작과 동일한 규칙."""
from __future__ import annotations

import secrets
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from nhdip.db import get_session
from nhdip.events import audit, emit
from nhdip.models import AppUser, AuditLog, Rule, RuleVersion, Setting
from nhdip.views.goal_check import check_goal
from nhdip.views.store import get_current

from . import state_service as S
from .deps import client_ip, require_resource

router = APIRouter(prefix="/state", tags=["state"])


# ═════════════════════════ 경영목표 ═════════════════════════
class ApplyIn(BaseModel):
    proposalId: str
    mode: Literal["adopt", "manual_edit"]
    value: float | None = None
    reason: str | None = None
    force: bool = False  # 정합성 경고(warn)를 확인하고 사유와 함께 확정


class CheckIn(BaseModel):
    proposalId: str
    mode: Literal["adopt", "manual_edit"] = "adopt"
    value: float | None = None


class ProposalIn(BaseModel):
    proposalId: str


class AddNewIn(BaseModel):
    proposalId: str
    targetLabel: str


class ManualGoalIn(BaseModel):
    title: str
    targetLabel: str
    periodLabel: str
    metricLabel: str | None = None
    ownerOrg: str | None = None


class ReviewItemIn(BaseModel):
    title: str


def _proposal(session: Session, pid: str) -> dict[str, Any]:
    for p in get_current(session, "proposals") or []:
        if p["id"] == pid:
            return p
    raise HTTPException(404, "제안 없음")


def _update_goal_rule(session: Session, goal_id: str, value: float, actor: str) -> dict[str, Any] | None:
    """확정 목표 값을 연결된 규칙(GOAL_TARGETS 등)에 새 버전으로 반영 → rule.changed 이벤트."""
    links_s = session.get(Setting, "goal.rule_links")
    link = (links_s.value if links_s else {}).get(goal_id)
    if not link:
        return None
    rule = session.get(Rule, link["rule"])
    if not rule:
        return None
    cur = session.execute(select(RuleVersion).where(RuleVersion.rule_code == rule.code, RuleVersion.version == rule.active_version)).scalar()
    body = dict(cur.body if cur else {})
    if body.get(link["path"]) == value:
        return None
    body[link["path"]] = value
    last = session.execute(select(RuleVersion.version).where(RuleVersion.rule_code == rule.code).order_by(RuleVersion.version.desc()).limit(1)).scalar() or 0
    session.add(RuleVersion(rule_code=rule.code, version=last + 1, body=body, note=f"경영목표 확정({goal_id})", created_by=actor))
    rule.active_version = last + 1
    emit(session, "rule.changed", {"rule": rule.code, "version": last + 1, "source": goal_id}, actor)
    return {"rule": rule.code, "version": last + 1, link["path"]: value}


@router.get("/goals")
def get_goal_state(session: Session = Depends(get_session), _: AppUser = Depends(require_resource("goal_state"))):
    return S.goal_state(session)


def _resolve_value(p: dict[str, Any], value: float | None) -> float | None:
    rec = p.get("recommendation") or {}
    resolved = value
    if resolved is None:
        resolved = rec.get("value")
    if resolved is None and rec.get("high") is not None and rec.get("low") is not None:
        resolved = round((rec["high"] + rec["low"]) / 2, 2)
    return resolved


@router.post("/goals/check")
def check_proposal(body: CheckIn, session: Session = Depends(get_session), _: AppUser = Depends(require_resource("goal_actions"))):
    """확정 전 정합성 검증(6.4.7) — 상위 제약 · 기조 방향 · 총자산 영향."""
    p = _proposal(session, body.proposalId)
    if not p.get("targetGoalId"):
        return {"goal": None, "passed": True, "issues": [], "checked": 0}
    value = _resolve_value(p, body.value if body.mode == "manual_edit" else None)
    return {**check_goal(session, p["targetGoalId"], value), "value": value}


@router.get("/goals/{goal_id}/history")
def goal_history(goal_id: str, session: Session = Depends(get_session), _: AppUser = Depends(require_resource("goal_state"))):
    """목표 변경 이력(6.4.8) — 감사 기록(goal.*) 기준, 처리자 이름 · 값 · 사유 · 강제 확정 여부."""
    rows = session.execute(select(AuditLog).where(AuditLog.target_kind == "goal", AuditLog.target_id == goal_id).order_by(AuditLog.at.desc()).limit(100)).scalars().all()
    names = {u.emp_no: u.name for u in session.execute(select(AppUser).where(AppUser.emp_no.in_({r.actor for r in rows if r.actor}))).scalars()}
    from zoneinfo import ZoneInfo

    tz_s = session.get(Setting, "ui.timezone")
    tz = ZoneInfo(tz_s.value if tz_s and tz_s.value else "Asia/Seoul")
    out = []
    for r in rows:
        d = r.detail or {}
        out.append({"at": r.at.astimezone(tz).isoformat(timespec="seconds"), "action": r.action, "actor": r.actor, "actorName": names.get(r.actor or ""), "value": d.get("value"), "mode": d.get("mode"), "reason": d.get("reason"), "forced": bool(d.get("forced")), "issues": d.get("issues") or [], "rule": d.get("rule")})
    return out


@router.post("/goals/apply")
def apply_proposal(body: ApplyIn, request: Request, session: Session = Depends(get_session), user: AppUser = Depends(require_resource("goal_actions"))):
    p = _proposal(session, body.proposalId)
    if not p.get("targetGoalId"):
        raise HTTPException(422, "기존 목표를 바꾸는 제안이 아닙니다")
    rec = p.get("recommendation") or {}
    resolved = _resolve_value(p, body.value)
    # 확정 전 정합성 검증 — block 은 거부, warn 은 사유를 적고 강제 확정할 때만 통과
    chk = check_goal(session, p["targetGoalId"], resolved)
    if chk["blocked"]:
        raise HTTPException(422, {"message": "정합성 검증에서 확정할 수 없는 값입니다", "issues": chk["issues"]})
    if not chk["passed"]:
        if not body.force:
            raise HTTPException(409, {"message": "정합성 경고가 있습니다 — 사유를 입력하고 확정하세요", "issues": chk["issues"]})
        if len((body.reason or "").strip()) < 5:
            raise HTTPException(422, {"message": "강제 확정 사유를 5자 이상 입력하세요", "issues": chk["issues"]})
    override = {
        "status": "active",
        "targetValue": resolved,
        "updatedAt": S.today(),
        "changeReason": body.reason or (f"AI 제안 반영 — {rec.get('text', '')}" if body.mode == "adopt" else "담당자 직접 수정"),
        "creationMode": "ai_proposed" if body.mode == "adopt" else "user_manual",
        "confirmedBy": user.emp_no,
    }
    if chk["issues"]:
        override["consistency"] = {"forced": body.force, "issues": chk["issues"]}
    S.put(session, S.NS_GOAL_OVERRIDE, p["targetGoalId"], override, user.emp_no)
    S.put(session, S.NS_PROPOSAL_ACTION, p["id"], {"action": body.mode}, user.emp_no)
    rule_change = _update_goal_rule(session, p["targetGoalId"], resolved, user.emp_no) if resolved is not None else None
    emit(session, "goal.confirmed", {"goal": p["targetGoalId"], "proposal": p["id"], "mode": body.mode, "value": resolved}, user.emp_no)
    audit(session, user.emp_no, "goal.apply", "goal", p["targetGoalId"], {"proposal": p["id"], "mode": body.mode, "value": resolved, "rule": rule_change, "reason": override["changeReason"], "forced": bool(chk["issues"] and body.force), "issues": chk["issues"]}, client_ip(request))
    session.commit()
    return S.goal_state(session)


@router.post("/goals/keep")
def keep_goal(body: ProposalIn, request: Request, session: Session = Depends(get_session), user: AppUser = Depends(require_resource("goal_actions"))):
    p = _proposal(session, body.proposalId)
    if p.get("targetGoalId"):
        S.put(session, S.NS_GOAL_OVERRIDE, p["targetGoalId"], {"status": "active", "updatedAt": S.today(), "changeReason": "기존 목표 유지 결정", "confirmedBy": user.emp_no}, user.emp_no)
    S.put(session, S.NS_PROPOSAL_ACTION, p["id"], {"action": "keep"}, user.emp_no)
    emit(session, "goal.confirmed", {"goal": p.get("targetGoalId"), "proposal": p["id"], "mode": "keep"}, user.emp_no)
    audit(session, user.emp_no, "goal.keep", "goal", p.get("targetGoalId"), {"proposal": p["id"]}, client_ip(request))
    session.commit()
    return S.goal_state(session)


@router.post("/goals/add-new")
def add_new_goal(body: AddNewIn, request: Request, session: Session = Depends(get_session), user: AppUser = Depends(require_resource("goal_actions"))):
    p = _proposal(session, body.proposalId)
    gid = f"goal-new-{p['id']}"
    if not S.get_ns(session, S.NS_GOAL_ADDED).get(gid):
        S.put(session, S.NS_GOAL_ADDED, gid, {"id": gid, "title": p["title"].replace("신규 경영목표 제안 — ", ""), "targetLabel": body.targetLabel, "creationMode": "ai_proposed", "status": "active", "sourceProposalId": p["id"], "periodLabel": "2026 연간", "ownerOrg": "종합기획부", "addedAt": S.today()}, user.emp_no)
    S.put(session, S.NS_PROPOSAL_ACTION, p["id"], {"action": "added"}, user.emp_no)
    emit(session, "goal.confirmed", {"goal": gid, "proposal": p["id"], "mode": "added"}, user.emp_no)
    audit(session, user.emp_no, "goal.add_new", "goal", gid, {"proposal": p["id"], "target": body.targetLabel}, client_ip(request))
    session.commit()
    return S.goal_state(session)


@router.post("/goals/manual")
def add_manual_goal(body: ManualGoalIn, request: Request, session: Session = Depends(get_session), user: AppUser = Depends(require_resource("goal_actions"))):
    gid = f"goal-manual-{secrets.token_hex(4)}"
    S.put(session, S.NS_GOAL_ADDED, gid, {"id": gid, "title": body.title, "targetLabel": body.targetLabel, "creationMode": "user_manual", "status": "active", "periodLabel": body.periodLabel, "metricLabel": body.metricLabel, "ownerOrg": body.ownerOrg or "종합기획부", "addedAt": S.today()}, user.emp_no)
    emit(session, "goal.confirmed", {"goal": gid, "mode": "manual"}, user.emp_no)
    audit(session, user.emp_no, "goal.add_manual", "goal", gid, body.model_dump(), client_ip(request))
    session.commit()
    return S.goal_state(session)


@router.post("/goals/review-items")
def register_review_item(body: ReviewItemIn, session: Session = Depends(get_session), user: AppUser = Depends(require_resource("goal_actions"))):
    S.put(session, S.NS_REVIEW_ITEM, body.title[:120], {"title": body.title}, user.emp_no)
    session.commit()
    return S.goal_state(session)


@router.post("/goals/reset")
def reset_goals(request: Request, session: Session = Depends(get_session), user: AppUser = Depends(require_resource("goal_actions"))):
    S.clear(session, "goal")
    audit(session, user.emp_no, "goal.reset", "goal", None, None, client_ip(request))
    session.commit()
    return S.goal_state(session)


# ═════════════════════════ 진행사업 ═════════════════════════
class PlanPatchIn(BaseModel):
    title: str | None = None
    body: str | None = None
    monitoringMetrics: list[str] | None = None
    evidenceNote: str | None = None
    reviewCycle: str | None = None
    linkedTabKey: str | None = None
    linkedAnalysisLabel: str | None = None


class NewPlanIn(BaseModel):
    id: str | None = None  # 클라이언트가 미리 만든 ID (plan-user-*) — 화면이 바로 시트를 열 수 있도록
    title: str
    body: str
    evidenceNote: str | None = None
    monitoringMetrics: list[str] = []
    reviewCycle: str | None = None
    ownerOrg: str | None = None
    linkedTabKey: str | None = None
    linkedAnalysisLabel: str | None = None


def _user_evidence(note: str | None) -> list[dict[str, Any]]:
    if not (note or "").strip():
        return []
    return [{"id": f"ev-user-{secrets.token_hex(3)}", "category": "internal_direction", "sourceKind": "none", "label": "담당자 입력 근거", "snippet": note.strip()}]


def _plan_exists(session: Session, pid: str) -> bool:
    base = {p["id"] for p in get_current(session, "action_plans") or []}
    return pid in base or pid in S.get_ns(session, S.NS_PLAN_USER)


def _runtime(session: Session, pid: str, user: AppUser, **values: Any) -> None:
    if not _plan_exists(session, pid):
        raise HTTPException(404, "수행방안 없음")
    rt = dict(S.get_ns(session, S.NS_PLAN_RUNTIME).get(pid) or {})
    for k, v in values.items():
        if v is None:
            rt.pop(k, None)
        else:
            rt[k] = v
    S.put(session, S.NS_PLAN_RUNTIME, pid, rt, user.emp_no)


@router.get("/plans")
def get_plan_state(session: Session = Depends(get_session), _: AppUser = Depends(require_resource("plan_state"))):
    return S.plan_state(session)


@router.post("/plans/{pid}/register")
def register_plan(pid: str, request: Request, session: Session = Depends(get_session), user: AppUser = Depends(require_resource("plan_actions"))):
    _runtime(session, pid, user, status="in_progress", registeredAt=S.today())
    audit(session, user.emp_no, "plan.register", "plan", pid, None, client_ip(request))
    session.commit()
    return S.plan_state(session)


@router.post("/plans/{pid}/unregister")
def unregister_plan(pid: str, request: Request, session: Session = Depends(get_session), user: AppUser = Depends(require_resource("plan_actions"))):
    _runtime(session, pid, user, status="proposed", branchShared=False, registeredAt=None)
    audit(session, user.emp_no, "plan.unregister", "plan", pid, None, client_ip(request))
    session.commit()
    return S.plan_state(session)


@router.post("/plans/{pid}/toggle-share")
def toggle_share(pid: str, request: Request, session: Session = Depends(get_session), user: AppUser = Depends(require_resource("plan_actions"))):
    base = next((p for p in (get_current(session, "action_plans") or []) if p["id"] == pid), None) or S.get_ns(session, S.NS_PLAN_USER).get(pid)
    if not base:
        raise HTTPException(404, "수행방안 없음")
    cur = (S.get_ns(session, S.NS_PLAN_RUNTIME).get(pid) or {}).get("branchShared", base.get("branchShared", False))
    _runtime(session, pid, user, branchShared=not cur)
    audit(session, user.emp_no, "plan.toggle_share", "plan", pid, {"branchShared": not cur}, client_ip(request))
    session.commit()
    return S.plan_state(session)


@router.patch("/plans/{pid}")
def update_plan(pid: str, body: PlanPatchIn, request: Request, session: Session = Depends(get_session), user: AppUser = Depends(require_resource("plan_actions"))):
    patch = body.model_dump(exclude_none=True)
    users = S.get_ns(session, S.NS_PLAN_USER)
    if pid in users:
        p = {**users[pid], **patch, "updatedAt": S.today()}
        if "evidenceNote" in patch:
            p["evidence"] = _user_evidence(patch["evidenceNote"])
        S.put(session, S.NS_PLAN_USER, pid, p, user.emp_no)
    else:
        rt = S.get_ns(session, S.NS_PLAN_RUNTIME).get(pid) or {}
        _runtime(session, pid, user, patch={**(rt.get("patch") or {}), **patch}, updatedAt=S.today())
    audit(session, user.emp_no, "plan.update", "plan", pid, patch, client_ip(request))
    session.commit()
    return S.plan_state(session)


@router.delete("/plans/{pid}")
def delete_plan(pid: str, request: Request, session: Session = Depends(get_session), user: AppUser = Depends(require_resource("plan_actions"))):
    if not _plan_exists(session, pid):
        raise HTTPException(404, "수행방안 없음")
    S.put(session, S.NS_PLAN_DELETED, pid, {}, user.emp_no)
    S.remove(session, S.NS_PLAN_USER, pid)
    audit(session, user.emp_no, "plan.delete", "plan", pid, None, client_ip(request))
    session.commit()
    return S.plan_state(session)


@router.post("/plans")
def add_plan(body: NewPlanIn, request: Request, session: Session = Depends(get_session), user: AppUser = Depends(require_resource("plan_actions"))):
    import re

    pid = body.id if body.id and re.fullmatch(r"plan-user-[0-9a-z]{4,20}", body.id) and not _plan_exists(session, body.id) else f"plan-user-{secrets.token_hex(4)}"
    plan = {
        "id": pid,
        "title": body.title,
        "body": body.body,
        "ownerOrg": body.ownerOrg or "신용리스크관리부",
        "monitoringMetrics": body.monitoringMetrics,
        "reviewCycle": body.reviewCycle or "월",
        "alignment": {"verdict": "unknown", "matched": [], "conflicts": []},
        "evidence": _user_evidence(body.evidenceNote),
        "evidenceNote": body.evidenceNote,
        "status": "proposed",
        "branchShared": False,
        "origin": "user",
        "linkedTabKey": body.linkedTabKey,
        "linkedAnalysisLabel": body.linkedAnalysisLabel,
        "updatedAt": S.today(),
        "guideRuleId": "USER_DEFINED",
        "createdBy": user.emp_no,
    }
    S.put(session, S.NS_PLAN_USER, pid, plan, user.emp_no)
    audit(session, user.emp_no, "plan.add", "plan", pid, {"title": body.title}, client_ip(request))
    session.commit()
    return {"id": pid, **S.plan_state(session)}


@router.post("/plans/reset")
def reset_plans(request: Request, session: Session = Depends(get_session), user: AppUser = Depends(require_resource("plan_actions"))):
    S.clear(session, "plan")
    audit(session, user.emp_no, "plan.reset", "plan", None, None, client_ip(request))
    session.commit()
    return S.plan_state(session)
