"""온디맨드 분석 (F.9 · UX-05) — 업무 화면에서 분석을 다시 실행하고 단계 진행을 SSE 로 받는다.

실행 권한: 그 워크플로우 결과 화면을 볼 수 있는 사용자(설정 `assist.workflow_resources` 의 화면 리소스).
남용 방지: 같은 워크플로우가 대기·실행 중이거나 `analysis.min_interval_sec` 안에 요청된 적이 있으면 기존 요청을 돌려준다.
"""
from __future__ import annotations

import asyncio
import json
import time
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from nhdip.db import SessionLocal, get_session
from nhdip.events import audit, emit
from nhdip.models import AppUser, Job, NodeRun, OutboxEvent, Setting, Workflow, WorkflowNode, WorkflowRun, utcnow

from .assist import DEFAULT_WF_RESOURCES
from .deps import client_ip, current_user, user_resources

router = APIRouter(prefix="/analysis", tags=["analysis"])


class RunIn(BaseModel):
    workflow: str


def _setting(session: Session, key: str, default: Any) -> Any:
    s = session.get(Setting, key)
    return s.value if s and s.value is not None else default


def _check(session: Session, user: AppUser, workflow: str) -> Workflow:
    wf = session.get(Workflow, workflow)
    if not wf or not wf.enabled:
        raise HTTPException(404, "분석 없음")
    res = _setting(session, "assist.workflow_resources", DEFAULT_WF_RESOURCES).get(workflow)
    allowed = user_resources(session, user)
    if res is None or (allowed is not None and res not in allowed):
        raise HTTPException(403, "이 분석을 실행할 권한이 없습니다")
    return wf


@router.post("/run")
def run_analysis(body: RunIn, request: Request, session: Session = Depends(get_session), user: AppUser = Depends(current_user)):
    wf = _check(session, user, body.workflow)
    gap = int(_setting(session, "analysis.min_interval_sec", 60))
    recent = session.execute(
        select(OutboxEvent)
        .where(OutboxEvent.type == "manual", OutboxEvent.payload["workflow"].astext == wf.code, OutboxEvent.created_at > utcnow() - timedelta(seconds=gap))
        .order_by(OutboxEvent.id.desc())
        .limit(1)
    ).scalar()
    if recent is not None:
        return {"event": recent.id, "traceId": recent.trace_id, "reused": True}
    ev = emit(session, "manual", {"workflow": wf.code, "reason": "업무 화면 온디맨드 분석"}, user.emp_no)
    audit(session, user.emp_no, "analysis.run", "workflow", wf.code, None, client_ip(request))
    session.commit()
    return {"event": ev.id, "traceId": ev.trace_id, "reused": False}


def _snapshot(event_id: int) -> dict[str, Any]:
    with SessionLocal() as s:
        ev = s.get(OutboxEvent, event_id)
        if ev is None:
            return {"phase": "missing"}
        wf_code = (ev.payload or {}).get("workflow")
        run = s.execute(select(WorkflowRun).where(WorkflowRun.causes.contains([{"event_id": event_id}])).order_by(WorkflowRun.started_at.desc()).limit(1)).scalar()
        defs = s.execute(select(WorkflowNode).where(WorkflowNode.workflow_code == (run.workflow_code if run else wf_code), WorkflowNode.enabled).order_by(WorkflowNode.seq)).scalars().all()
        done = {}
        if run:
            done = {n.node_key: n for n in s.execute(select(NodeRun).where(NodeRun.workflow_run_id == run.id)).scalars()}
        steps = []
        current_set = False
        for d in defs:
            nr = done.get(d.key)
            if nr:
                status = nr.status
            elif run and run.status == "running" and not current_set:
                status, current_set = "running", True
            else:
                status = "pending"
            steps.append({"key": d.key, "name": d.name, "status": status, "durationMs": nr.duration_ms if nr else None})
        if run is None:
            job = s.execute(select(Job).where(Job.causes.contains([{"event_id": event_id}])).order_by(Job.id.desc()).limit(1)).scalar()
            phase = "failed" if job and job.status == "failed" else "queued"
        else:
            phase = {"running": "running", "succeeded": "done", "degraded": "done", "failed": "failed"}.get(run.status, run.status)
        return {
            "phase": phase,
            "workflow": wf_code,
            "runId": run.id if run else None,
            "status": run.status if run else None,
            "published": ((run.summary or {}).get("published") if run else None) or [],
            "traceId": ev.trace_id,
            "steps": steps,
        }


@router.get("/stream")
async def stream(event: int = Query(..., ge=1), timeout: int = Query(180, ge=5, le=600), session: Session = Depends(get_session), user: AppUser = Depends(current_user)):
    ev = session.get(OutboxEvent, event)
    if ev is None or ev.type != "manual":
        raise HTTPException(404, "실행 요청 없음")
    _check(session, user, (ev.payload or {}).get("workflow", ""))
    session.close()

    async def gen():
        last, t0 = None, time.monotonic()
        yield "retry: 3000\n\n"
        while True:
            snap = await run_in_threadpool(_snapshot, event)
            body = json.dumps(snap, ensure_ascii=False)
            if body != last:
                yield f"event: progress\ndata: {body}\n\n"
                last = body
            if snap["phase"] in ("done", "failed", "missing"):
                yield f"event: end\ndata: {body}\n\n"
                return
            if time.monotonic() - t0 > timeout:
                yield f"event: end\ndata: {json.dumps({**snap, 'phase': 'timeout'}, ensure_ascii=False)}\n\n"
                return
            await asyncio.sleep(1)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"})
