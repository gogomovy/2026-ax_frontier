"""부서 데이터 책임자 승인함 API (요구사항 §40 STW) — 에이전트 제안(분석 화면 · 추적 지표 · 개념 연결 · 온톨로지 변경)과 부서 사용자 분석 요청.

관리자는 전체, 부서 데이터 책임자는 자기 부서가 소유한 자료 · 자기 부서 사용자의 요청만 본다(다른 부서 것은 없는 것처럼 404).
판정 · 반영은 핵심 계층 `nhdip.stewardship` 이 하고, 여기서는 권한 · 감사 · 커밋만 한다.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from nhdip.db import get_session
from nhdip.events import audit
from nhdip.models import AppUser
from nhdip.stewardship import StewardError, Viewer, approve_analysis, inbox, reject_analysis, review_concept, review_metric, review_ontology, viewer_of

from .deps import client_ip, current_user

router = APIRouter(prefix="/db/steward/proposals", tags=["db"])


def _viewer(session: Session = Depends(get_session), user: AppUser = Depends(current_user)) -> Viewer:
    v = viewer_of(session, user)
    if v is None:
        raise HTTPException(403, "부서 데이터 책임자 · 관리자만 볼 수 있습니다 — 관리자 [사용자]에서 데이터 책임자로 지정")
    return v


def _via(v: Viewer) -> str:
    return "admin" if v.admin else "steward"


def _http(exc: StewardError) -> HTTPException:
    return HTTPException(exc.status, str(exc))


class NoteIn(BaseModel):
    note: str | None = Field(default=None, max_length=1000)


class AnalysisApproveIn(NoteIn):
    """승인 기준 — 비우면 요청 명세 그대로. space 는 아직 한 번도 승인되지 않은 분석만 바꿀 수 있다."""

    cron: str | None = None
    on_data_change: bool | None = None
    llm: bool | None = None
    space: str | None = None


class ConceptIn(NoteIn):
    label: str = Field(min_length=1, max_length=60)
    key: str = Field(min_length=1, max_length=200)


@router.get("")
def proposals(status: str = "pending", kind: str | None = None, session: Session = Depends(get_session), v: Viewer = Depends(_viewer)) -> dict[str, Any]:
    return inbox(session, v, status, kind)


@router.post("/analysis/{code}/{version}/approve")
def analysis_approve(code: str, version: int, body: AnalysisApproveIn, request: Request, session: Session = Depends(get_session), v: Viewer = Depends(_viewer)):
    options = {k: val for k, val in body.model_dump(exclude_unset=True).items() if k in ("cron", "on_data_change", "llm")}
    try:
        out = approve_analysis(session, v, code, version, note=body.note, options=options, space=body.space)
    except StewardError as exc:
        session.rollback()
        raise _http(exc) from exc
    audit(session, v.emp_no, "steward.analysis.approve", "analysis_agent", code, {"version": version, "via": _via(v), "space": body.space, "workflow": out.get("workflow")}, client_ip(request))
    session.commit()
    return out


@router.post("/analysis/{code}/{version}/reject")
def analysis_reject(code: str, version: int, body: NoteIn, request: Request, session: Session = Depends(get_session), v: Viewer = Depends(_viewer)):
    try:
        reject_analysis(session, v, code, version, body.note or "")
    except StewardError as exc:
        session.rollback()
        raise _http(exc) from exc
    audit(session, v.emp_no, "steward.analysis.reject", "analysis_agent", code, {"version": version, "via": _via(v)}, client_ip(request))
    session.commit()
    return {"ok": True}


@router.post("/metric/{code}/{action}")
def metric_decide(code: str, action: str, body: NoteIn, request: Request, session: Session = Depends(get_session), v: Viewer = Depends(_viewer)):
    if action not in ("approve", "reject"):
        raise HTTPException(404, "알 수 없는 동작")
    try:
        review_metric(session, v, code, approve=action == "approve", note=body.note)
    except StewardError as exc:
        session.rollback()
        raise _http(exc) from exc
    audit(session, v.emp_no, f"steward.metric.{action}", "metric", code, {"via": _via(v), "note": body.note}, client_ip(request))
    session.commit()
    return {"ok": True}


@router.post("/concept/{dataset}/{action}")
def concept_decide(dataset: str, action: str, body: ConceptIn, request: Request, session: Session = Depends(get_session), v: Viewer = Depends(_viewer)):
    if action not in ("approve", "reject"):
        raise HTTPException(404, "알 수 없는 동작")
    try:
        review_concept(session, v, dataset, body.label, body.key, approve=action == "approve", note=body.note)
    except StewardError as exc:
        session.rollback()
        raise _http(exc) from exc
    audit(session, v.emp_no, f"steward.concept.{action}", "dataset", dataset, {"label": body.label, "key": body.key, "via": _via(v), "note": body.note}, client_ip(request))
    session.commit()
    if action == "approve":
        # 설명 카드(질문하기 · Elasticsearch)의 개념 태그를 바로 맞춘다 — 실패해도 워커 주기 작업이 다시 맞춘다
        try:
            from nhdip.data.catalog import index_dataset_cards

            index_dataset_cards(session, [dataset])
            session.commit()
        except Exception:  # noqa: BLE001
            session.rollback()
    return {"ok": True}


@router.post("/ontology/{pid}/{action}")
def ontology_decide(pid: int, action: str, body: NoteIn, request: Request, session: Session = Depends(get_session), v: Viewer = Depends(_viewer)):
    """온톨로지 변경 제안 승인(적용 → 새 판) · 반려(사유 필수 — 같은 연산을 다시 제안하지 않음). 적용 검증 실패는 failed 로 남기고 422."""
    if action not in ("approve", "reject"):
        raise HTTPException(404, "알 수 없는 동작")
    try:
        p, res = review_ontology(session, v, pid, approve=action == "approve", note=body.note)
    except StewardError as exc:
        session.rollback()
        raise _http(exc) from exc
    audit(session, v.emp_no, f"steward.ontology.{action}", "ontology_proposal", str(pid),
          {"via": _via(v), "result": res.get("status"), "version": res.get("version"), "datasets": [d.get("code") for d in (p.evidence or {}).get("datasets") or [] if isinstance(d, dict)], "note": body.note},
          client_ip(request))
    session.commit()
    if not res.get("ok"):
        raise HTTPException(422, res.get("error") or "적용하지 못했습니다")
    return {"ok": True, "status": res.get("status"), "version": res.get("version"), "warnings": res.get("warnings") or []}
