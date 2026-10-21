"""경영목표 처리 · 진행사업 상태 API (F.8 · F.15~17) — 프론트 Provider 동작과 동일한 규칙."""
from __future__ import annotations

import secrets
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from nhdip.db import get_session
from nhdip.events import audit, emit
from nhdip.models import AppUser, AuditLog, Rule, RuleVersion, Setting
from nhdip.views.goal_check import check_goal
from nhdip.ui_config import hq_org_name, value_of
from nhdip.views.store import get_current

from . import state_service as S
from .deps import client_ip, current_user, require_resource, user_resources

router = APIRouter(prefix="/state", tags=["state"])


# ═════════════════════════ 경영목표 ═════════════════════════
def _finite(v: float | None) -> float | None:
    import math

    if v is not None and not math.isfinite(v):
        raise ValueError("유한한 숫자여야 합니다")
    return v


class ApplyIn(BaseModel):
    proposalId: str = Field(max_length=120)
    mode: Literal["adopt", "manual_edit"]
    value: float | None = None
    reason: str | None = Field(None, max_length=1000)
    force: bool = False  # 정합성 경고(warn)를 확인하고 사유와 함께 확정

    @field_validator("value")
    @classmethod
    def _fin(cls, v):
        return _finite(v)


class CheckIn(BaseModel):
    proposalId: str = Field(max_length=120)
    mode: Literal["adopt", "manual_edit"] = "adopt"
    value: float | None = None

    @field_validator("value")
    @classmethod
    def _fin(cls, v):
        return _finite(v)


class ProposalIn(BaseModel):
    proposalId: str


class AddNewIn(BaseModel):
    proposalId: str
    targetLabel: str


class ManualGoalIn(BaseModel):
    title: str = Field(max_length=200)
    targetLabel: str = Field(max_length=200)
    periodLabel: str = Field(max_length=60)
    metricLabel: str | None = Field(None, max_length=200)
    ownerOrg: str | None = Field(None, max_length=60)


class ReviewItemIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class GoalRevertIn(BaseModel):
    goalId: str = Field(max_length=120)
    toVersion: int | None = Field(None, ge=0)  # 비우면 현재 바로 앞 버전
    reason: str | None = Field(None, max_length=1000)  # 필수 — 빈 값 · 짧은 값은 한국어 422 (_require_reason)


class GoalDeleteIn(BaseModel):
    goalId: str = Field(max_length=120)
    reason: str | None = Field(None, max_length=1000)


class GoalEditIn(BaseModel):
    goalId: str = Field(max_length=120)
    value: float
    reason: str | None = Field(None, max_length=1000)
    force: bool = False  # 정합성 경고(warn)를 확인하고 확정

    @field_validator("value")
    @classmethod
    def _fin(cls, v):
        return _finite(v)


def _require_admin_reset(user: AppUser) -> None:
    """전체 초기화는 모든 사용자의 처리 이력을 지우므로 관리자만 (B.32)."""
    if user.role != "admin":
        raise HTTPException(403, "전체 초기화는 관리자만 할 수 있습니다")


def _user_dept(session: Session, user: AppUser) -> str | None:
    """사용자 소속 부서명(부 · 지역본부 · 영업점 중 가장 가까운 단위) — 등록 부서는 화면 입력값이 아니라 소속으로 정한다."""
    from nhdip.orgs import org_chain

    for o in org_chain(session, user.org_code):
        if o.unit_type in ("DEPT", "REGION", "BRANCH"):
            return o.name
    return None


def _org_name(session: Session, code: str | None) -> str:
    from nhdip.models import OrgUnit

    o = session.get(OrgUnit, code) if code else None
    return o.name if o is not None else (code or "-")


def _proposal(session: Session, pid: str) -> dict[str, Any]:
    for p in get_current(session, "proposals") or []:
        if p["id"] == pid:
            return p
    raise HTTPException(404, "제안 없음")


def _find_goal(session: Session, goal_id: str) -> dict[str, Any] | None:
    for g in get_current(session, "goals") or []:
        if g.get("id") == goal_id:
            return g
    return None


def _reason_min(session: Session) -> int:
    """사유 최소 글자 수 = [화면 설정 › 기준값 › 제안 사유 최소 글자 수] — 강제 확정 · 되돌리기 · 다시 수정 공통 (화면과 같은 값)."""
    return max(1, int(value_of(session, "ui.thresholds").get("proposalReasonMin") or 1))


def _require_reason(session: Session, reason: str | None) -> str:
    min_len = _reason_min(session)
    text = (reason or "").strip()
    if len(text) < min_len:
        raise HTTPException(422, {"message": f"사유를 {min_len}자 이상 입력하세요", "minLength": min_len})
    return text


def _versions(goal: dict[str, Any], override: dict[str, Any] | None) -> list[dict[str, Any]]:
    """목표 버전 사슬 — [기준(산출물) 버전, 확정 버전 …]. 이력은 지우지 않고 뒤에 덧붙이기만 한다.
    사슬이 없는 예전 확정(값만 있는 override)은 '기준 + 1' 한 칸으로 본다 (화면 resolveGoal 과 같은 규칙)."""
    base = {"version": int(goal.get("version") or 1), "value": goal.get("targetValue"), "mode": "base", "creationMode": goal.get("creationMode") or "existing"}
    ov = override or {}
    if ov.get("versions"):
        return [base, *ov["versions"]]
    tv = ov.get("targetValue")
    if tv is not None and tv != base["value"]:
        return [base, {"version": base["version"] + 1, "value": tv, "at": ov.get("updatedAt"), "actor": ov.get("confirmedBy"), "mode": "legacy", "creationMode": ov.get("creationMode") or "user_manual"}]
    return [base]


def _next_version(chain: list[dict[str, Any]], value: float | None, mode: str, creation_mode: str, reason: str, user: AppUser, **extra: Any) -> tuple[int, list[dict[str, Any]]]:
    """새 버전 한 칸을 덧붙인 확정 버전 목록(기준 제외)과 새 버전 번호."""
    nv = int(chain[-1]["version"]) + 1
    entry = {"version": nv, "value": value, "at": S.today(), "actor": user.emp_no, "mode": mode, "creationMode": creation_mode, "reason": reason, **extra}
    return nv, [*chain[1:], entry]


def _update_goal_rule(session: Session, goal_id: str, value: float, actor: str) -> dict[str, Any] | None:
    """확정 목표 값을 연결된 규칙(GOAL_TARGETS 등)에 새 버전으로 반영 → rule.changed 이벤트."""
    links_s = session.get(Setting, "goal.rule_links")
    link = (links_s.value if links_s else {}).get(goal_id)
    if not link:
        return None
    from nhdip.locks import lock

    # 잠금을 먼저 잡고 활성 버전을 읽는다 — 같은 규칙의 다른 목표 확정과 겹쳐도 앞 확정값을 잃지 않는다 (B.33)
    lock(session, f"rule:{link['rule']}")
    rule = session.get(Rule, link["rule"])
    if not rule:
        return None
    session.refresh(rule)
    cur = session.execute(select(RuleVersion).where(RuleVersion.rule_code == rule.code, RuleVersion.version == rule.active_version)).scalar()
    body = dict(cur.body if cur else {})
    if body.get(link["path"]) == value:
        return None
    body[link["path"]] = value
    last = session.execute(select(RuleVersion.version).where(RuleVersion.rule_code == rule.code).order_by(RuleVersion.version.desc()).limit(1)).scalar() or 0
    session.add(RuleVersion(rule_code=rule.code, version=last + 1, body=body, note=f"경영목표 확정({goal_id})", created_by=actor))
    from .admin_core import _dual_control

    if _dual_control(session):
        # 이중 승인 — 규칙 반영은 관리자 [판정 규칙]에서 다른 관리자가 적용해야 활성화
        return {"rule": rule.code, "version": last + 1, link["path"]: value, "pendingApproval": True}
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
    # 버전 번호 — 새 기록은 detail.version, 예전 확정 기록은 기준 버전부터 차례로 센다 (초기화하면 기준으로 돌아감)
    goal = _find_goal(session, goal_id)
    base_v = int(goal.get("version") or 1) if goal else None
    counter = base_v
    versions: dict[int, int | None] = {}
    resets = sorted(session.execute(select(AuditLog.at).where(AuditLog.action == "goal.reset")).scalars().all())
    for r in reversed(rows):
        d = r.detail or {}
        ver = d.get("version")
        while resets and resets[0] < r.at:  # 전체 초기화(대상 없음 기록) 뒤의 확정은 기준 버전부터 다시 센다
            resets.pop(0)
            counter = base_v
        if r.action in VALUE_ACTIONS:
            if ver is None and counter is not None and (r.action != "goal.apply" or d.get("value") is not None):
                ver = counter + 1
            if ver is not None:
                counter = ver
        versions[r.id] = ver
    out = []
    for r in rows:
        d = r.detail or {}
        out.append({"at": r.at.astimezone(tz).isoformat(timespec="seconds"), "action": r.action, "actor": r.actor, "actorName": names.get(r.actor or ""), "value": d.get("value"), "fromValue": d.get("fromValue"), "version": versions.get(r.id), "restoredVersion": d.get("restoredVersion"), "mode": d.get("mode"), "reason": d.get("reason"), "forced": bool(d.get("forced")), "issues": d.get("issues") or [], "rule": d.get("rule")})
    return out


VALUE_ACTIONS = ("goal.apply", "goal.edit", "goal.revert", "goal.delete")  # 목표값 버전을 만드는 기록


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
        # 최소 글자 수 = [화면 설정 › 기준값 › 제안 사유 최소 글자 수] — 화면 버튼과 같은 값 (Phase K · HC-01)
        min_len = _reason_min(session)
        if len((body.reason or "").strip()) < min_len:
            raise HTTPException(422, {"message": f"강제 확정 사유를 {min_len}자 이상 입력하세요", "issues": chk["issues"]})
    S.lock_item(session, S.NS_GOAL_OVERRIDE, p["targetGoalId"])
    prev = S.get_ns(session, S.NS_GOAL_OVERRIDE).get(p["targetGoalId"])
    goal = _find_goal(session, p["targetGoalId"])
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
    version_detail: dict[str, Any] = {}
    if goal is not None:
        # 확정할 때마다 버전 사슬에 한 칸 — 되돌리기 · 다시 수정이 이 사슬을 기준으로 동작한다
        chain = _versions(goal, prev)
        nv, override["versions"] = _next_version(chain, resolved, body.mode, override["creationMode"], override["changeReason"], user)
        override["version"] = nv
        version_detail = {"version": nv, "fromValue": chain[-1]["value"]}
    S.put(session, S.NS_GOAL_OVERRIDE, p["targetGoalId"], override, user.emp_no)
    S.put(session, S.NS_PROPOSAL_ACTION, p["id"], {"action": body.mode}, user.emp_no)
    rule_change = _update_goal_rule(session, p["targetGoalId"], resolved, user.emp_no) if resolved is not None else None
    emit(session, "goal.confirmed", {"goal": p["targetGoalId"], "proposal": p["id"], "mode": body.mode, "value": resolved}, user.emp_no)
    audit(session, user.emp_no, "goal.apply", "goal", p["targetGoalId"], {"proposal": p["id"], "mode": body.mode, "value": resolved, "rule": rule_change, "reason": override["changeReason"], "forced": bool(chk["issues"] and body.force), "issues": chk["issues"], **version_detail}, client_ip(request))
    session.commit()
    return S.goal_state(session)


@router.post("/goals/keep")
def keep_goal(body: ProposalIn, request: Request, session: Session = Depends(get_session), user: AppUser = Depends(require_resource("goal_actions"))):
    p = _proposal(session, body.proposalId)
    if p.get("targetGoalId"):
        # 유지 결정은 예전과 같이 기록한다(확정 값 · 규칙 연결 동작을 바꾸지 않음 — 화면 시안 반영은 되돌리기 · 다시 수정 · 삭제 경로만 더함)
        S.put(session, S.NS_GOAL_OVERRIDE, p["targetGoalId"], {"status": "active", "updatedAt": S.today(), "changeReason": "기존 목표 유지 결정", "confirmedBy": user.emp_no}, user.emp_no)
    S.put(session, S.NS_PROPOSAL_ACTION, p["id"], {"action": "keep"}, user.emp_no)
    emit(session, "goal.confirmed", {"goal": p.get("targetGoalId"), "proposal": p["id"], "mode": "keep"}, user.emp_no)
    audit(session, user.emp_no, "goal.keep", "goal", p.get("targetGoalId"), {"proposal": p["id"]}, client_ip(request))
    session.commit()
    return S.goal_state(session)


REOPEN_ACTIONS = ("adopt", "manual_edit", "keep")


@router.post("/goals/revert")
def revert_goal(body: GoalRevertIn, request: Request, session: Session = Depends(get_session), user: AppUser = Depends(require_resource("goal_actions"))):
    """확정한 목표 변경 되돌리기 — 고른 이전 버전(기본: 바로 앞 버전)의 목표값을 **새 버전**으로 다시 기록한다.
    이력은 지우지 않는다. 기준(산출물) 버전으로 되돌리면 목표값이 기준값으로 돌아가지만 되돌린 기록은 새 버전으로 남는다.
    이 목표를 대상으로 한 AI 제안의 처리(반영 · 직접 수정 · 유지)는 지워 다시 검토할 수 있게 한다 (신규 목표 추가 'added' 는 그대로)."""
    goal = _find_goal(session, body.goalId)
    if goal is None:
        raise HTTPException(404, "목표 없음")
    reason = _require_reason(session, body.reason)
    S.lock_item(session, S.NS_GOAL_OVERRIDE, body.goalId)
    prev = S.get_ns(session, S.NS_GOAL_OVERRIDE).get(body.goalId)
    if not prev:
        raise HTTPException(422, "되돌릴 확정 변경이 없습니다")
    chain = _versions(goal, prev)
    cur = chain[-1]
    to_v = body.toVersion if body.toVersion is not None else int(chain[-2 if len(chain) > 1 else 0]["version"])
    target = next((v for v in chain if int(v["version"]) == to_v), None)
    if target is None:
        raise HTTPException(422, f"v{to_v} 버전이 없습니다")
    if len(chain) > 1 and target is cur:
        raise HTTPException(422, "현재 버전으로는 되돌릴 수 없습니다 — 이전 버전을 고르세요")
    restored = target.get("value")
    to_base = target is chain[0]
    creation = chain[0]["creationMode"] if to_base else (target.get("creationMode") or "user_manual")
    nv, versions = _next_version(chain, restored, "revert", creation, reason, user, restoredVersion=to_v)
    override: dict[str, Any] = {"status": "active", "updatedAt": S.today(), "changeReason": reason, "creationMode": creation, "confirmedBy": user.emp_no, "version": nv, "versions": versions, "revertedTo": to_v}
    if restored is not None:
        override["targetValue"] = restored
    S.put(session, S.NS_GOAL_OVERRIDE, body.goalId, override, user.emp_no)
    actions = S.get_ns(session, S.NS_PROPOSAL_ACTION)
    reopened = [p["id"] for p in get_current(session, "proposals") or [] if p.get("targetGoalId") == body.goalId and (actions.get(p["id"]) or {}).get("action") in REOPEN_ACTIONS]
    for pid in reopened:
        S.remove(session, S.NS_PROPOSAL_ACTION, pid)
    rule_change = _update_goal_rule(session, body.goalId, restored, user.emp_no) if restored is not None else None
    emit(session, "goal.confirmed", {"goal": body.goalId, "mode": "revert", "value": restored, "version": nv}, user.emp_no)
    audit(session, user.emp_no, "goal.revert", "goal", body.goalId, {"mode": "revert", "value": restored, "fromValue": cur.get("value"), "version": nv, "fromVersion": cur["version"], "restoredVersion": to_v, "toBase": to_base, "reason": reason, "rule": rule_change, "reopened": reopened}, client_ip(request))
    session.commit()
    return S.goal_state(session)


@router.post("/goals/delete")
def delete_goal(body: GoalDeleteIn, request: Request, session: Session = Depends(get_session), user: AppUser = Depends(require_resource("goal_actions"))):
    """목표 삭제(소프트) — 목표를 보관(archived) 상태로 바꾸는 새 버전을 쌓는다. 이력 · 버전 사슬은 지우지 않으며,
    이력의 [이 버전으로 복원](/goals/revert)으로 삭제 전 버전을 새 버전으로 되살릴 수 있다.
    직접 추가한 목표(goal.added)는 같은 항목에 보관 상태 · 사유 · 처리자를 덧붙인다."""
    reason = _require_reason(session, body.reason)
    goal = _find_goal(session, body.goalId)
    if goal is None:
        S.lock_item(session, S.NS_GOAL_ADDED, body.goalId)
        added = S.get_ns(session, S.NS_GOAL_ADDED).get(body.goalId)
        if not added:
            raise HTTPException(404, "목표 없음")
        if added.get("status") == "archived":
            raise HTTPException(422, "이미 삭제된 목표입니다")
        S.put(session, S.NS_GOAL_ADDED, body.goalId, {**added, "status": "archived", "archivedAt": S.today(), "archivedBy": user.emp_no, "archiveReason": reason, "prevStatus": added.get("status") or "active"}, user.emp_no)
        detail: dict[str, Any] = {"mode": "delete", "creationMode": "delete", "reason": reason, "added": True}
    else:
        S.lock_item(session, S.NS_GOAL_OVERRIDE, body.goalId)
        prev = S.get_ns(session, S.NS_GOAL_OVERRIDE).get(body.goalId) or {}
        if prev.get("status") == "archived":
            raise HTTPException(422, "이미 삭제된 목표입니다")
        chain = _versions(goal, prev)
        value = chain[-1].get("value")
        nv, versions = _next_version(chain, value, "delete", "delete", reason, user, status="archived")
        override: dict[str, Any] = {**prev, "status": "archived", "updatedAt": S.today(), "changeReason": reason, "creationMode": prev.get("creationMode") or chain[-1].get("creationMode") or "existing", "confirmedBy": user.emp_no, "version": nv, "versions": versions}
        if value is not None:
            override["targetValue"] = value
        S.put(session, S.NS_GOAL_OVERRIDE, body.goalId, override, user.emp_no)
        detail = {"mode": "delete", "creationMode": "delete", "value": value, "version": nv, "fromVersion": chain[-1]["version"], "reason": reason, "status": "archived"}
    emit(session, "goal.confirmed", {"goal": body.goalId, "mode": "delete"}, user.emp_no)
    audit(session, user.emp_no, "goal.delete", "goal", body.goalId, detail, client_ip(request))
    session.commit()
    return S.goal_state(session)


@router.post("/goals/edit")
def edit_goal(body: GoalEditIn, request: Request, session: Session = Depends(get_session), user: AppUser = Depends(require_resource("goal_actions"))):
    """확정된(또는 적용 중인) 목표값 다시 수정 — 담당자 입력값을 새 버전으로 기록. 정합성 검증 · 강제 확정 규칙은 /goals/apply 의 직접 수정과 같다."""
    goal = _find_goal(session, body.goalId)
    if goal is None:
        raise HTTPException(404, "목표 없음")
    reason = _require_reason(session, body.reason)
    S.lock_item(session, S.NS_GOAL_OVERRIDE, body.goalId)
    prev = S.get_ns(session, S.NS_GOAL_OVERRIDE).get(body.goalId)
    if (prev or {}).get("status") == "archived":
        raise HTTPException(422, "삭제된 목표입니다 — 변경 이력에서 먼저 복원하세요")
    chk = check_goal(session, body.goalId, body.value)
    if chk["blocked"]:
        raise HTTPException(422, {"message": "정합성 검증에서 확정할 수 없는 값입니다", "issues": chk["issues"]})
    if not chk["passed"] and not body.force:
        raise HTTPException(409, {"message": "정합성 경고가 있습니다 — 경고를 확인하고 확정하세요", "issues": chk["issues"]})
    chain = _versions(goal, prev)
    nv, versions = _next_version(chain, body.value, "edit", "user_manual", reason, user)
    override: dict[str, Any] = {"status": "active", "targetValue": body.value, "updatedAt": S.today(), "changeReason": reason, "creationMode": "user_manual", "confirmedBy": user.emp_no, "version": nv, "versions": versions}
    if chk["issues"]:
        override["consistency"] = {"forced": body.force, "issues": chk["issues"]}
    S.put(session, S.NS_GOAL_OVERRIDE, body.goalId, override, user.emp_no)
    rule_change = _update_goal_rule(session, body.goalId, body.value, user.emp_no)
    emit(session, "goal.confirmed", {"goal": body.goalId, "mode": "edit", "value": body.value, "version": nv}, user.emp_no)
    audit(session, user.emp_no, "goal.edit", "goal", body.goalId, {"mode": "edit", "value": body.value, "fromValue": chain[-1].get("value"), "version": nv, "fromVersion": chain[-1]["version"], "reason": reason, "rule": rule_change, "forced": bool(chk["issues"] and body.force), "issues": chk["issues"]}, client_ip(request))
    session.commit()
    return S.goal_state(session)


def _annual_label(session: Session) -> str | None:
    """'<기준 연도> 연간' — 기준일을 모르면 None(화면은 '–')."""
    from nhdip.data.datasets import display_as_of

    a = display_as_of(session)
    return f"{str(a)[:4]} 연간" if a else None


@router.post("/goals/add-new")
def add_new_goal(body: AddNewIn, request: Request, session: Session = Depends(get_session), user: AppUser = Depends(require_resource("goal_actions"))):
    p = _proposal(session, body.proposalId)
    gid = f"goal-new-{p['id']}"
    if not S.get_ns(session, S.NS_GOAL_ADDED).get(gid):
        # 기간 · 담당 조직은 제안 · 기준일 · 업무 영역 설정에서 (Phase K · HC-04 — 연도 · 부서 이름을 코드에 두지 않는다)
        S.put(session, S.NS_GOAL_ADDED, gid, {"id": gid, "title": p["title"].replace("신규 경영목표 제안 — ", ""), "targetLabel": body.targetLabel, "creationMode": "ai_proposed", "status": "active", "sourceProposalId": p["id"], "periodLabel": p.get("periodLabel") or _annual_label(session), "ownerOrg": p.get("ownerOrg") or hq_org_name(session), "addedAt": S.today()}, user.emp_no)
    S.put(session, S.NS_PROPOSAL_ACTION, p["id"], {"action": "added"}, user.emp_no)
    emit(session, "goal.confirmed", {"goal": gid, "proposal": p["id"], "mode": "added"}, user.emp_no)
    audit(session, user.emp_no, "goal.add_new", "goal", gid, {"proposal": p["id"], "target": body.targetLabel}, client_ip(request))
    session.commit()
    return S.goal_state(session)


@router.post("/goals/manual")
def add_manual_goal(body: ManualGoalIn, request: Request, session: Session = Depends(get_session), user: AppUser = Depends(require_resource("goal_actions"))):
    gid = f"goal-manual-{secrets.token_hex(4)}"
    S.put(session, S.NS_GOAL_ADDED, gid, {"id": gid, "title": body.title, "targetLabel": body.targetLabel, "creationMode": "user_manual", "status": "active", "periodLabel": body.periodLabel, "metricLabel": body.metricLabel, "ownerOrg": (body.ownerOrg if user.role == "admin" and body.ownerOrg else None) or _user_dept(session, user) or hq_org_name(session), "addedAt": S.today()}, user.emp_no)
    emit(session, "goal.confirmed", {"goal": gid, "mode": "manual"}, user.emp_no)
    audit(session, user.emp_no, "goal.add_manual", "goal", gid, body.model_dump(), client_ip(request))
    session.commit()
    return S.goal_state(session)


@router.post("/goals/review-items")
def register_review_item(body: ReviewItemIn, request: Request, session: Session = Depends(get_session), user: AppUser = Depends(require_resource("goal_actions"))):
    S.put(session, S.NS_REVIEW_ITEM, body.title[:120], {"title": body.title}, user.emp_no)
    audit(session, user.emp_no, "goal.review_item", "goal", None, {"title": body.title}, client_ip(request))
    session.commit()
    return S.goal_state(session)


@router.post("/goals/reset")
def reset_goals(request: Request, session: Session = Depends(get_session), user: AppUser = Depends(require_resource("goal_actions"))):
    _require_admin_reset(user)
    S.clear(session, "goal")
    audit(session, user.emp_no, "goal.reset", "goal", None, None, client_ip(request))
    session.commit()
    return S.goal_state(session)


# ═════════════════════════ 진행사업 ═════════════════════════
class PlanPatchIn(BaseModel):
    title: str | None = Field(None, max_length=200)
    body: str | None = Field(None, max_length=4000)
    monitoringMetrics: list[str] | None = Field(None, max_length=20)
    evidenceNote: str | None = Field(None, max_length=2000)
    reviewCycle: str | None = Field(None, max_length=40)
    linkedTabKey: str | None = Field(None, max_length=80)
    linkedAnalysisLabel: str | None = Field(None, max_length=200)


class NewPlanIn(BaseModel):
    id: str | None = Field(None, max_length=40)  # 클라이언트가 미리 만든 ID (plan-user-*) — 화면이 바로 시트를 열 수 있도록
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(max_length=4000)
    evidenceNote: str | None = Field(None, max_length=2000)
    monitoringMetrics: list[str] = Field(default_factory=list, max_length=20)
    reviewCycle: str | None = Field(None, max_length=40)
    ownerOrg: str | None = Field(None, max_length=60)
    linkedTabKey: str | None = Field(None, max_length=80)
    linkedAnalysisLabel: str | None = Field(None, max_length=200)


def _check_owner(session: Session, pid: str, user: AppUser) -> None:
    """직접 등록한 진행사업은 등록자 · 같은 부서 · 관리자만 고치거나 지울 수 있다 (Agent 제안 사업은 담당 부서 권한으로) — B.32."""
    p = S.get_ns(session, S.NS_PLAN_USER).get(pid)
    if not p or user.role == "admin" or p.get("createdBy") == user.emp_no:
        return
    if p.get("ownerOrg") and p.get("ownerOrg") == _user_dept(session, user):
        return
    raise HTTPException(403, "다른 부서가 등록한 진행사업은 수정할 수 없습니다")


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
    S.lock_item(session, S.NS_PLAN_RUNTIME, pid)
    rt = dict(S.get_ns(session, S.NS_PLAN_RUNTIME).get(pid) or {})
    for k, v in values.items():
        if v is None:
            rt.pop(k, None)
        else:
            rt[k] = v
    S.put(session, S.NS_PLAN_RUNTIME, pid, rt, user.emp_no)


def _shared(session: Session, pid: str | None = None) -> set[str]:
    """영업점 참고가 켜진 진행사업 id (pid 를 주면 그것만 확인)."""
    from nhdip.views.plan_share import shared_plans

    ids = {str(p.get("id")) for p in shared_plans(session)}
    return ids if pid is None else ids & {pid}


def _after_share(session: Session, user: AppUser, before: set[str], pid: str | None = None) -> None:
    """영업점 참고 수행방안이 바뀌었으면(켜기 · 끄기 · 참고 중인 사업의 수정 · 삭제) — 영업점 참고 산출물(수행방안 + 연결 분석)을 다시 게시해
    질문하기에 바로 반영하고, 이벤트로 영업점 흐름을 다시 돌려 영업점 서술 에이전트가 새 근거로 쓰게 한다(같은 트랜잭션, 호출자가 commit)."""
    from nhdip.views.plan_share import SHARE_EVENTS, republish

    session.flush()
    after = _shared(session, pid)
    touched = (before | after) if pid is None else (before | after) & {pid}
    if not touched:
        return
    republish(session, user.emp_no)
    titles = {str(p.get("id")): p.get("title") for p in S.merged_plans(session)}
    for i in sorted(touched):
        emit(session, SHARE_EVENTS[0] if i in after else SHARE_EVENTS[1], {"plan": i, "title": titles.get(i)}, user.emp_no)


@router.get("/plans")
def get_plan_state(session: Session = Depends(get_session), user: AppUser = Depends(require_resource("plan_state"))):
    allowed = user_resources(session, user)
    if allowed is not None and "plan_actions" not in allowed:
        return S.shared_plan_state(session)  # 영업점 등 — 영업점 참고가 켜진 진행사업만
    return S.plan_state(session)


@router.post("/plans/{pid}/register")
def register_plan(pid: str, request: Request, session: Session = Depends(get_session), user: AppUser = Depends(require_resource("plan_actions"))):
    # 영업점 참고가 미리 켜져 있던 수행방안(기본값 · 참고를 먼저 켬)은 등록하는 순간 영업점에 공유된다 —
    # 켜기 · 끄기와 같이 영업점 공통 요약을 다시 게시하고 영업점 흐름을 다시 돌린다(_after_share)
    before = _shared(session, pid)
    _runtime(session, pid, user, status="in_progress", registeredAt=S.today())
    audit(session, user.emp_no, "plan.register", "plan", pid, None, client_ip(request))
    _after_share(session, user, before, pid)
    session.commit()
    return S.plan_state(session)


@router.post("/plans/{pid}/unregister")
def unregister_plan(pid: str, request: Request, session: Session = Depends(get_session), user: AppUser = Depends(require_resource("plan_actions"))):
    before = _shared(session, pid)
    _runtime(session, pid, user, status="proposed", branchShared=False, registeredAt=None)
    audit(session, user.emp_no, "plan.unregister", "plan", pid, None, client_ip(request))
    _after_share(session, user, before, pid)
    session.commit()
    return S.plan_state(session)


@router.post("/plans/{pid}/toggle-share")
def toggle_share(pid: str, request: Request, session: Session = Depends(get_session), user: AppUser = Depends(require_resource("plan_actions"))):
    base = next((p for p in (get_current(session, "action_plans") or []) if p["id"] == pid), None) or S.get_ns(session, S.NS_PLAN_USER).get(pid)
    if not base:
        raise HTTPException(404, "수행방안 없음")
    _check_owner(session, pid, user)
    S.lock_item(session, S.NS_PLAN_RUNTIME, pid)
    before = _shared(session, pid)
    cur = (S.get_ns(session, S.NS_PLAN_RUNTIME).get(pid) or {}).get("branchShared", base.get("branchShared", False))
    _runtime(session, pid, user, branchShared=not cur)
    audit(session, user.emp_no, "plan.toggle_share", "plan", pid, {"branchShared": not cur}, client_ip(request))
    # 영업점 참고 — 수행방안과 연결 분석을 영업점 화면 · 질문하기 · 영업점 에이전트가 함께 쓴다(views.plan_share)
    _after_share(session, user, before, pid)
    session.commit()
    return S.plan_state(session)


@router.patch("/plans/{pid}")
def update_plan(pid: str, body: PlanPatchIn, request: Request, session: Session = Depends(get_session), user: AppUser = Depends(require_resource("plan_actions"))):
    patch = body.model_dump(exclude_none=True)
    _check_owner(session, pid, user)
    before = _shared(session, pid)
    S.lock_item(session, S.NS_PLAN_USER, pid)
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
    _after_share(session, user, before, pid)  # 영업점이 참고 중인 사업을 고치면(연결 분석 포함) 영업점에도 새 내용
    session.commit()
    return S.plan_state(session)


@router.delete("/plans/{pid}")
def delete_plan(pid: str, request: Request, session: Session = Depends(get_session), user: AppUser = Depends(require_resource("plan_actions"))):
    if not _plan_exists(session, pid):
        raise HTTPException(404, "수행방안 없음")
    _check_owner(session, pid, user)
    before = _shared(session, pid)
    S.put(session, S.NS_PLAN_DELETED, pid, {}, user.emp_no)
    S.remove(session, S.NS_PLAN_USER, pid)
    audit(session, user.emp_no, "plan.delete", "plan", pid, None, client_ip(request))
    _after_share(session, user, before, pid)
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
        # 등록 부서 = 소속(가장 가까운 부 · 지역본부 · 영업점), 없으면 소속 조직 이름 — 부서 이름을 코드에 두지 않는다
        "ownerOrg": (body.ownerOrg if user.role == "admin" and body.ownerOrg else None) or _user_dept(session, user) or _org_name(session, user.org_code),
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
    _require_admin_reset(user)
    before = _shared(session)
    S.clear(session, "plan")
    audit(session, user.emp_no, "plan.reset", "plan", None, None, client_ip(request))
    _after_share(session, user, before)
    session.commit()
    return S.plan_state(session)


# ═════════════════════════ 확인 · 보고 요청 (영업점 · 사업부서 → 본부) ═════════════════════════
REQUEST_TYPES_DEFAULT = {"direction_check": "경영방향 확인 요청", "perf_report": "사업 성과보고", "new_biz_check": "신규사업 확인 요청", "guide_check": "영업 가이드 확인 요청"}


class ReportRequestIn(BaseModel):
    reqType: str = Field(max_length=40)
    title: str = Field(min_length=2, max_length=200)
    body: str = Field(min_length=2, max_length=4000)
    dueDate: str | None = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    relatedGoalId: str | None = Field(None, max_length=120)


def _request_types(session: Session) -> dict[str, str]:
    st = session.get(Setting, "request.types")
    return {**REQUEST_TYPES_DEFAULT, **(st.value if st and isinstance(st.value, dict) else {})}


@router.get("/report-requests/types")
def report_request_types(session: Session = Depends(get_session), _: AppUser = Depends(current_user)):
    return [{"value": k, "label": v} for k, v in _request_types(session).items()]


@router.get("/report-requests/mine")
def my_report_requests(session: Session = Depends(get_session), user: AppUser = Depends(current_user)):
    rows = [r for r in S.get_ns(session, S.NS_REPORT_REQUEST).values() if r.get("createdBy") == user.emp_no]
    return sorted(rows, key=lambda r: r.get("createdAt", ""), reverse=True)


@router.post("/report-requests", status_code=201)
def create_report_request(body: ReportRequestIn, request: Request, session: Session = Depends(get_session), user: AppUser = Depends(current_user)):
    """확인 · 보고 요청 등록 (B.32) — 요청 부서는 소속에서 정하고, 받는 부서는 설정 request.to_org(기본 종합기획부)."""
    from nhdip import ratelimit

    ratelimit.check(session, "request_user", user.emp_no)
    types = _request_types(session)
    if body.reqType not in types:
        raise HTTPException(422, "알 수 없는 요청 유형입니다")
    to_s = session.get(Setting, "request.to_org")
    rid = f"req-user-{secrets.token_hex(4)}"
    item = {
        "id": rid,
        "fromOrg": _user_dept(session, user) or user.org_code,
        "toOrg": (to_s.value if to_s and to_s.value else "종합기획부"),
        "reqType": body.reqType,
        "reqTypeLabel": types[body.reqType],
        "title": body.title.strip(),
        "body": body.body.strip(),
        "dueDate": body.dueDate,
        "createdAt": S.today(),
        "status": "open",
        "relatedGoalId": body.relatedGoalId,
        "createdBy": user.emp_no,
        "origin": "user",
    }
    S.put(session, S.NS_REPORT_REQUEST, rid, item, user.emp_no)
    emit(session, "request.created", {"id": rid, "reqType": body.reqType, "fromOrg": item["fromOrg"]}, user.emp_no)
    audit(session, user.emp_no, "request.create", "report_request", rid, {"title": item["title"], "reqType": body.reqType}, client_ip(request))
    session.commit()
    return item
