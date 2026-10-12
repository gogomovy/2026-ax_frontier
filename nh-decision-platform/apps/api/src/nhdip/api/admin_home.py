"""관리자 홈 · 운영 개요 (Phase C · ADM-02 · MON-01 · Q104 · Q105).

- `GET /admin/overview` — 처리할 일(가입 · 자료 · 분석 · 실행 승인, 알림, 추출 검토) · 시스템 상태 · 최근 24시간 실행 추이
- `GET /admin/monitor/overview?hours=24|168` — 시간대별 실행 상태 · LLM 호출 · 이벤트, 워크플로별 성공률 · 소요, 느린 노드, 에이전트별 토큰, 최근 실패 · 알림
집계는 읽기 전용이며 시간대 라벨은 설정 `ui.timezone`(기본 Asia/Seoul).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from nhdip.db import get_session
from nhdip.models import (
    AnalysisAgentVersion,
    AppUser,
    ExtractionIssue,
    Job,
    LlmCall,
    LlmConnection,
    NodeRun,
    OutboxEvent,
    Setting,
    UploadRequest,
    WorkerHeartbeat,
    Workflow,
    WorkflowRun,
    utcnow,
)
from nhdip.models.runtime import Alert

from .deps import require_admin

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


def _tz(session: Session) -> ZoneInfo:
    s = session.get(Setting, "ui.timezone")
    try:
        return ZoneInfo(str(s.value)) if s is not None and s.value else ZoneInfo("Asia/Seoul")
    except Exception:  # noqa: BLE001
        return ZoneInfo("Asia/Seoul")


def _iso(v: datetime | None) -> str | None:
    return v.isoformat() if v else None


def _buckets(now: datetime, hours: int, tz: ZoneInfo) -> tuple[list[datetime], timedelta, list[str]]:
    """시간대 칸 — 24시간이면 1시간, 7일이면 6시간 칸. (칸 시작 시각들, 칸 길이, 라벨)"""
    step = timedelta(hours=1 if hours <= 48 else 6)
    end = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    n = max(1, int(timedelta(hours=hours) / step))
    starts = [end - step * (n - i) for i in range(n)]
    labels = [s.astimezone(tz).strftime("%H시" if step.total_seconds() <= 3600 else "%m.%d %H시") for s in starts]
    return starts, step, labels


def _slot(t: datetime, starts: list[datetime], step: timedelta) -> int | None:
    if not starts or t < starts[0]:
        return None
    i = int((t - starts[0]) / step)
    return i if 0 <= i < len(starts) else None


@router.get("/overview")
def overview(session: Session = Depends(get_session)):
    now = utcnow()
    tz = _tz(session)
    day = now - timedelta(hours=24)
    users = dict(session.execute(select(AppUser.status, func.count()).group_by(AppUser.status)).all())
    uploads = session.execute(select(func.count()).select_from(UploadRequest).where(UploadRequest.status == "pending")).scalar() or 0
    analyses = session.execute(select(func.count()).select_from(AnalysisAgentVersion).where(AnalysisAgentVersion.status == "pending")).scalar() or 0
    approvals = session.execute(select(func.count()).select_from(Job).where(Job.status == "approval")).scalar() or 0
    issues = session.execute(select(func.count()).select_from(ExtractionIssue).where(ExtractionIssue.status == "open")).scalar() or 0
    alerts = session.execute(select(func.count()).select_from(Alert).where(Alert.at >= day, Alert.severity.in_(["warning", "critical"]))).scalar() or 0
    tasks = [
        {"key": "users", "label": "가입 승인 대기", "count": int(users.get("pending", 0)), "href": "/admin/users", "tone": "attention"},
        {"key": "uploads", "label": "자료 승인 대기", "count": int(uploads), "href": "/admin/uploads", "tone": "attention"},
        {"key": "analyses", "label": "분석 에이전트 승인 대기", "count": int(analyses), "href": "/admin/analysis-agents", "tone": "attention"},
        {"key": "jobs", "label": "실행 승인 대기", "count": int(approvals), "href": "/admin/monitor/agents", "tone": "attention"},
        {"key": "alerts", "label": "최근 24시간 경고 · 위험 알림", "count": int(alerts), "href": "/admin/monitor/alerts", "tone": "critical"},
        {"key": "issues", "label": "온톨로지 추출 검토", "count": int(issues), "href": "/admin/ontology", "tone": "info"},
    ]
    # 상태
    workers = session.execute(select(WorkerHeartbeat)).scalars().all()
    alive = sum(1 for w in workers if (now - w.seen_at).total_seconds() < 30)
    conn = session.execute(select(LlmConnection).where(LlmConnection.active).order_by(LlmConnection.id)).scalars().first()
    from nhdip.graph.neo4j_client import health as graph_health

    graph = graph_health()
    pending_events = session.execute(select(func.count()).select_from(OutboxEvent).where(OutboxEvent.dispatched_at.is_(None))).scalar() or 0
    queued = session.execute(select(func.count()).select_from(Job).where(Job.status.in_(["queued", "running"]))).scalar() or 0
    status = [
        {"key": "db", "label": "데이터베이스", "ok": True, "detail": "PostgreSQL · pgvector"},
        {"key": "graph", "label": "온톨로지 그래프", "ok": bool(graph.get("ok")), "detail": f"노드 {graph.get('nodes', '-')}" if graph.get("ok") else "연결 안 됨 — 그래프 축소 동작"},
        {"key": "llm", "label": "LLM 게이트웨이", "ok": bool(conn and (conn.base_url or "").strip()), "detail": (conn.name if conn and conn.base_url else "주소 미입력 — 서술은 기존 문장 유지")},
        {"key": "workers", "label": "워커", "ok": alive > 0, "detail": f"{alive}개 동작 · 작업 {queued} · 대기 이벤트 {pending_events}"},
    ]
    # 최근 24시간 실행
    starts, step, labels = _buckets(now, 24, tz)
    runs = session.execute(select(WorkflowRun.status, WorkflowRun.started_at).where(WorkflowRun.started_at >= starts[0])).all()
    buckets = [{"label": lb, "values": {"succeeded": 0, "degraded": 0, "failed": 0, "running": 0}} for lb in labels]
    totals: dict[str, int] = defaultdict(int)
    for st, at in runs:
        i = _slot(at, starts, step)
        if i is not None:
            buckets[i]["values"][st if st in buckets[i]["values"] else "running"] += 1
        if at >= day:
            totals[st] += 1
    llm = session.execute(select(func.count(), func.coalesce(func.sum(LlmCall.prompt_tokens), 0), func.coalesce(func.sum(LlmCall.completion_tokens), 0)).where(LlmCall.created_at >= day)).one()
    recent = session.execute(select(WorkflowRun).order_by(WorkflowRun.started_at.desc()).limit(6)).scalars().all()
    return {
        "at": _iso(now),
        "tasks": tasks,
        "pendingTotal": sum(t["count"] for t in tasks if t["key"] != "issues"),
        "status": status,
        "runs24h": {"total": sum(totals.values()), **{k: int(v) for k, v in totals.items()}, "buckets": buckets},
        "llm24h": {"calls": int(llm[0]), "tokens": int(llm[1]) + int(llm[2])},
        "users": {k: int(v) for k, v in users.items()},
        "workflows": session.execute(select(func.count()).select_from(Workflow).where(Workflow.enabled)).scalar() or 0,
        "recentRuns": [{"id": r.id, "workflow": r.workflow_code, "status": r.status, "startedAt": _iso(r.started_at), "finishedAt": _iso(r.finished_at)} for r in recent],
    }


@router.get("/monitor/overview")
def monitor_overview(hours: int = Query(24, ge=1, le=24 * 31), session: Session = Depends(get_session)):
    now = utcnow()
    tz = _tz(session)
    starts, step, labels = _buckets(now, hours, tz)
    since = starts[0]
    # 실행
    runs = session.execute(select(WorkflowRun.id, WorkflowRun.workflow_code, WorkflowRun.status, WorkflowRun.started_at, WorkflowRun.finished_at).where(WorkflowRun.started_at >= since)).all()
    run_b = [{"label": lb, "values": {"succeeded": 0, "degraded": 0, "failed": 0, "running": 0}} for lb in labels]
    per_wf: dict[str, dict[str, Any]] = defaultdict(lambda: {"runs": 0, "succeeded": 0, "degraded": 0, "failed": 0, "ms": []})
    for _id, wf, st, a, b in runs:
        i = _slot(a, starts, step)
        if i is not None:
            run_b[i]["values"][st if st in run_b[i]["values"] else "running"] += 1
        w = per_wf[wf]
        w["runs"] += 1
        if st in ("succeeded", "degraded", "failed"):
            w[st] += 1
        if b:
            w["ms"].append(int((b - a).total_seconds() * 1000))
    workflows = []
    for wf, w in sorted(per_wf.items(), key=lambda kv: -kv[1]["runs"]):
        ms = sorted(w["ms"])
        workflows.append({"workflow": wf, "runs": w["runs"], "succeeded": w["succeeded"], "degraded": w["degraded"], "failed": w["failed"],
                          "successRate": round(100 * (w["succeeded"] + w["degraded"]) / w["runs"], 1) if w["runs"] else None,
                          "avgMs": int(sum(ms) / len(ms)) if ms else None, "p95Ms": ms[min(len(ms) - 1, int(len(ms) * 0.95))] if ms else None})
    # 느린 노드 (평균 소요)
    slow = session.execute(
        select(NodeRun.impl, func.count(), func.avg(NodeRun.duration_ms), func.count().filter(NodeRun.status == "failed"))
        .where(NodeRun.started_at >= since).group_by(NodeRun.impl).order_by(func.avg(NodeRun.duration_ms).desc()).limit(8)
    ).all() if runs else []
    # LLM
    calls = session.execute(select(LlmCall.agent_code, LlmCall.status, LlmCall.created_at, LlmCall.prompt_tokens, LlmCall.completion_tokens, LlmCall.latency_ms).where(LlmCall.created_at >= since)).all()
    llm_b = [{"label": lb, "values": {"ok": 0, "error": 0}} for lb in labels]
    by_agent: dict[str, dict[str, int]] = defaultdict(lambda: {"calls": 0, "tokens": 0, "errors": 0})
    tokens = 0
    lat: list[int] = []
    for agent, st, at, pt, ct, ms in calls:
        i = _slot(at, starts, step)
        if i is not None:
            llm_b[i]["values"]["error" if st == "error" else "ok"] += 1
        t = int(pt or 0) + int(ct or 0)
        tokens += t
        a = by_agent[agent or "-"]
        a["calls"] += 1
        a["tokens"] += t
        a["errors"] += 1 if st == "error" else 0
        if ms:
            lat.append(int(ms))
    from nhdip.llm.budget import status as budget_status

    try:
        budget = budget_status(session)
    except Exception:  # noqa: BLE001
        budget = {}
    # 이벤트
    evs = session.execute(select(OutboxEvent.type, OutboxEvent.created_at, OutboxEvent.dispatched_at).where(OutboxEvent.created_at >= since)).all()
    ev_b = [{"label": lb, "values": {"dispatched": 0, "pending": 0}} for lb in labels]
    ev_types: dict[str, int] = defaultdict(int)
    for typ, at, disp in evs:
        i = _slot(at, starts, step)
        if i is not None:
            ev_b[i]["values"]["dispatched" if disp else "pending"] += 1
        ev_types[typ] += 1
    failures = session.execute(select(WorkflowRun).where(WorkflowRun.started_at >= since, WorkflowRun.status.in_(["failed", "degraded"])).order_by(WorkflowRun.started_at.desc()).limit(8)).scalars().all()
    alerts = session.execute(select(Alert).where(Alert.at >= since).order_by(Alert.at.desc()).limit(8)).scalars().all()
    total = len(runs)
    ok = sum(1 for r in runs if r[2] in ("succeeded", "degraded"))
    durations = sorted(int((b - a).total_seconds() * 1000) for _i, _w, _s, a, b in runs if b)
    return {
        "hours": hours,
        "stepHours": int(step.total_seconds() // 3600),
        "kpi": {
            "runs": total,
            "successRate": round(100 * ok / total, 1) if total else None,
            "failed": sum(1 for r in runs if r[2] == "failed"),
            "degraded": sum(1 for r in runs if r[2] == "degraded"),
            "avgMs": int(sum(durations) / len(durations)) if durations else None,
            "p95Ms": durations[min(len(durations) - 1, int(len(durations) * 0.95))] if durations else None,
            "llmCalls": len(calls),
            "llmErrors": sum(1 for c in calls if c[1] == "error"),
            "tokens": tokens,
            "llmAvgMs": int(sum(lat) / len(lat)) if lat else None,
            "events": len(evs),
            "alerts": len(alerts),
        },
        "runs": run_b,
        "llm": llm_b,
        "events": ev_b,
        "eventTypes": sorted(({"type": k, "count": v} for k, v in ev_types.items()), key=lambda x: -x["count"])[:8],
        "workflows": workflows,
        "slowNodes": [{"impl": impl, "count": int(n), "avgMs": int(avg or 0), "failed": int(f or 0)} for impl, n, avg, f in slow],
        "agents": sorted(({"agent": k, **v} for k, v in by_agent.items()), key=lambda x: -x["tokens"])[:8],
        "budget": budget,
        "failures": [{"id": r.id, "workflow": r.workflow_code, "status": r.status, "startedAt": _iso(r.started_at), "error": (r.error or "")[:200]} for r in failures],
        "recentAlerts": [{"id": a.id, "at": _iso(a.at), "kind": a.kind, "severity": a.severity, "title": a.title, "status": a.status} for a in alerts],
    }
