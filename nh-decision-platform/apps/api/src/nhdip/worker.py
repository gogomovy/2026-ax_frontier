"""워커 — 아웃박스 디스패치 + 작업 실행 루프.  `python -m nhdip.worker`"""
from __future__ import annotations

import logging
import os
import signal
import socket
import time
import traceback
from datetime import timedelta

from sqlalchemy.dialects.postgresql import insert

from nhdip.config import get_settings
from nhdip.db import SessionLocal
from nhdip import obs
from nhdip.models import Job, WorkerHeartbeat, WorkflowRun, utcnow
from nhdip.workflow.dispatcher import claim_job, dispatch_once, recover_stale
from nhdip.workflow.engine import run_workflow
from nhdip.workflow.scheduler import schedule_due

log = logging.getLogger("nhdip.worker")
_stop = False


def _sig(*_):
    global _stop
    _stop = True


def heartbeat(worker_id: str, info: dict) -> None:
    with SessionLocal() as s:
        stmt = insert(WorkerHeartbeat).values(worker_id=worker_id, seen_at=utcnow(), info=info)
        s.execute(stmt.on_conflict_do_update(index_elements=[WorkerHeartbeat.worker_id], set_={"seen_at": utcnow(), "info": info}))
        s.commit()


def purge_request_log(session) -> int:
    """요청 추적 기록 보관 기간 정리 (설정 `obs.request_log_days`, 기본 30일). 업무 데이터 · 감사 로그는 건드리지 않는다."""
    from sqlalchemy import delete

    from nhdip.models import RequestLog, Setting

    st = session.get(Setting, "obs.request_log_days")
    days = int(st.value) if st and st.value else 30
    if days <= 0:
        return 0
    n = session.execute(delete(RequestLog).where(RequestLog.at < utcnow() - timedelta(days=days))).rowcount or 0
    session.commit()
    if n:
        log.info("request_log %d건 정리 (%d일 경과)", n, days)
    return n


def job_trace_id(causes: list) -> str | None:
    """작업의 추적 ID — 원인 이벤트의 추적 ID(여러 건이 병합되면 첫 건). 없으면 새로 만든다."""
    for c in causes or []:
        if isinstance(c, dict) and c.get("trace_id"):
            return c["trace_id"]
    return None


def process_one(worker_id: str) -> bool:
    with SessionLocal() as s:
        job = claim_job(s, worker_id)
        if not job:
            return False
        job_id, wf, causes = job.id, job.workflow_code, job.causes
    with obs.scope(job_trace_id(causes)) as db_stats:
        log.info("job %s → %s (%d causes)", job_id, wf, len(causes))
        status, error, run_id = "done", None, None
        t0 = time.perf_counter()
        try:
            with SessionLocal() as s:
                run = run_workflow(s, wf, causes, job_id=job_id)
                run_id = run.id
                if run.status == "failed":
                    status, error = "failed", run.error
        except Exception as exc:  # noqa: BLE001
            status, error = "failed", f"{exc}\n{traceback.format_exc()[-2000:]}"
        with SessionLocal() as s:
            if run_id:
                # 실행 요약에 DB 구간(질의 수 · 소요) · 전체 소요를 남긴다
                r = s.get(WorkflowRun, run_id)
                if r is not None:
                    r.summary = {**(r.summary or {}), "obs": {"db_queries": int(db_stats["queries"]), "db_ms": round(db_stats["ms"]), "wall_ms": round((time.perf_counter() - t0) * 1000)}}
            j = s.get(Job, job_id)
            if status == "failed" and j.attempts < j.max_attempts:
                j.status = "queued"
                j.run_after = utcnow() + timedelta(seconds=30 * j.attempts)
            else:
                j.status = status
                j.finished_at = utcnow()
            j.error = error
            j.locked_by = None
            s.commit()
        log.info("job %s %s (db %d queries · %.0f ms)", job_id, status, db_stats["queries"], db_stats["ms"])
    return True


def main() -> None:
    obs.setup_logging()
    signal.signal(signal.SIGTERM, _sig)
    signal.signal(signal.SIGINT, _sig)
    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    poll = get_settings().worker_poll_sec
    log.info("worker %s started (poll %.1fs)", worker_id, poll)
    last_hb = 0.0
    last_recover = 0.0
    last_cron = 0.0
    last_purge = 0.0
    last_alert = 0.0
    stats = {"dispatched": 0, "jobs": 0, "started_at": utcnow().isoformat()}
    while not _stop:
        try:
            with SessionLocal() as s:
                stats["dispatched"] += dispatch_once(s)
            if process_one(worker_id):
                stats["jobs"] += 1
                continue
            now = time.monotonic()
            if now - last_hb > 5:
                heartbeat(worker_id, stats)
                last_hb = now
            if now - last_cron > 20:
                with SessionLocal() as s:
                    stats["scheduled"] = stats.get("scheduled", 0) + schedule_due(s)
                last_cron = now
            if now - last_alert > 60:
                from nhdip.alerts import scan as scan_alerts

                with SessionLocal() as s:
                    stats["alerts"] = stats.get("alerts", 0) + scan_alerts(s)
                last_alert = now
            if now - last_purge > 86400:
                with SessionLocal() as s:
                    stats["purged"] = stats.get("purged", 0) + purge_request_log(s)
                last_purge = now
            if now - last_recover > 300:
                with SessionLocal() as s:
                    recover_stale(s)
                last_recover = now
        except Exception:  # noqa: BLE001 — 루프는 계속
            log.exception("worker loop error")
            time.sleep(3)
        time.sleep(poll)
    log.info("worker stopped")


if __name__ == "__main__":
    main()
