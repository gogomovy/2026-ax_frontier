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


_BUSY: dict[str, float | int | None] = {"job": None, "since": None}  # 지금 실행 중인 작업 (감시 스레드가 본다)


def process_one(worker_id: str) -> bool:
    with SessionLocal() as s:
        job = claim_job(s, worker_id)
        if not job:
            return False
        job_id, wf, causes = job.id, job.workflow_code, job.causes
    _BUSY.update(job=job_id, since=time.monotonic())
    try:
        return _process(worker_id, job_id, wf, causes)
    finally:
        _BUSY.update(job=None, since=None)


def _process(worker_id: str, job_id: int, wf: str, causes: list) -> bool:
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
            if j.status in ("done", "failed"):
                from nhdip.workflow.orchestrator import release_downstream

                release_downstream(s, wf)
        log.info("job %s %s (db %d queries · %.0f ms)", job_id, status, db_stats["queries"], db_stats["ms"])
    return True


def max_run_minutes() -> float:
    """실행 시간 상한(분) — 설정 `workflow.max_run_minutes`(기본 120, 0 = 끔). 넘으면 워커가 스스로 재시작한다 (B.33)."""
    from nhdip.models import Setting

    try:
        with SessionLocal() as s:
            st = s.get(Setting, "workflow.max_run_minutes")
            return float(st.value) if st and st.value is not None else 120.0
    except Exception:  # noqa: BLE001
        return 120.0


class _Beat:
    """심장박동 · 감시 스레드 (B.32 · B.33).
    - 긴 워크플로우를 실행하는 동안에도 살아 있음을 알린다(멈춘 작업 복구 판단의 기준). 정보에 실행 중 작업 · 경과를 싣는다.
    - 한 작업이 실행 시간 상한을 넘으면(멈춘 외부 호출 · 무한 대기) 프로세스를 끝낸다 → 컨테이너가 다시 띄우고,
      새 워커가 기동 때 이 호스트의 고아 작업을 다시 대기열로 돌린다(recover_own_orphans)."""

    def __init__(self, worker_id: str, stats: dict, every: float = 5.0):
        import threading

        self.worker_id, self.stats, self.every = worker_id, stats, every
        self._ev = threading.Event()
        self._t = threading.Thread(target=self._run, name="heartbeat", daemon=True)
        self._limit_at = 0.0
        self._limit = 120.0

    def _run(self) -> None:
        while not self._ev.wait(self.every):
            now = time.monotonic()
            if now - self._limit_at > 60:
                self._limit, self._limit_at = max_run_minutes(), now
            since = _BUSY.get("since")
            busy_sec = int(now - since) if since else 0
            try:
                heartbeat(self.worker_id, {**self.stats, "busy_job": _BUSY.get("job"), "busy_sec": busy_sec})
            except Exception:  # noqa: BLE001
                log.warning("heartbeat failed", exc_info=True)
            if self._limit and busy_sec > self._limit * 60:
                log.critical("job %s 가 실행 시간 상한 %.0f분을 넘었습니다 — 워커를 재시작합니다", _BUSY.get("job"), self._limit)
                os._exit(3)

    def start(self) -> "_Beat":
        heartbeat(self.worker_id, dict(self.stats))
        self._t.start()
        return self

    def stop(self) -> None:
        self._ev.set()


def housekeeping(worker_id: str, stats: dict, last: dict[str, float]) -> None:
    """주기 작업 — 작업이 계속 있어도(바쁜 동안에도) 정해진 간격마다 돈다 (B.32).
    알림 검사 · 보관 정리 · 멈춘 작업 복구는 여러 워커 중 하나만 하도록 잠금을 잡는다."""
    from nhdip.locks import try_lock

    now = time.monotonic()

    def due(name: str, every: float) -> bool:
        if now - last.get(name, 0.0) >= every:
            last[name] = now
            return True
        return False

    if due("cron", 20):
        with SessionLocal() as s:
            stats["scheduled"] = stats.get("scheduled", 0) + schedule_due(s)
    if due("alert", 60):
        from nhdip.alerts import scan as scan_alerts

        with SessionLocal() as s:
            if try_lock(s, "housekeeping:alerts"):
                stats["alerts"] = stats.get("alerts", 0) + scan_alerts(s)
            else:
                s.rollback()
    if due("recover", 300):
        with SessionLocal() as s:
            if try_lock(s, "housekeeping:recover"):
                stats["recovered"] = stats.get("recovered", 0) + recover_stale(s)
            else:
                s.rollback()
    if due("purge", 86400):
        from nhdip.retention import purge

        with SessionLocal() as s:
            if try_lock(s, "housekeeping:purge"):
                stats["purged"] = stats.get("purged", 0) + purge_request_log(s)
                stats["retention"] = purge(s)
            else:
                s.rollback()


def main() -> None:
    obs.setup_logging()
    signal.signal(signal.SIGTERM, _sig)
    signal.signal(signal.SIGINT, _sig)
    import uuid

    # 기동마다 고유 — 컨테이너 재시작 때 hostname · PID(1)가 같아도 이전 기동의 작업과 구분된다 (B.33)
    worker_id = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
    poll = get_settings().worker_poll_sec
    log.info("worker %s started (poll %.1fs)", worker_id, poll)
    try:
        from nhdip.workflow.dispatcher import recover_own_orphans

        with SessionLocal() as s:
            n = recover_own_orphans(s, socket.gethostname(), worker_id)
        if n:
            log.warning("이전 기동이 남긴 실행 중 작업 %d건을 다시 대기열로 돌렸습니다", n)
    except Exception:  # noqa: BLE001
        log.exception("orphan recovery failed")
    stats = {"dispatched": 0, "jobs": 0, "started_at": utcnow().isoformat()}
    # 처음 기동 직후 바로 복구 · 정리하지 않도록 기준 시각을 지금으로 (cron · 알림은 곧바로)
    last: dict[str, float] = {"recover": time.monotonic() - 240, "purge": time.monotonic() - 86400 + 600}
    beat = _Beat(worker_id, stats).start()
    try:
        while not _stop:
            try:
                with SessionLocal() as s:
                    stats["dispatched"] += dispatch_once(s)
                housekeeping(worker_id, stats, last)
                if process_one(worker_id):
                    stats["jobs"] += 1
                    continue
            except Exception:  # noqa: BLE001 — 루프는 계속
                log.exception("worker loop error")
                time.sleep(3)
            time.sleep(poll)
    finally:
        beat.stop()
    log.info("worker stopped")


def health(max_age_sec: int = 60) -> int:
    """컨테이너 상태 검사 — 이 호스트 워커의 심장박동이 max_age_sec 안에 있으면 0 (B.32)."""
    from sqlalchemy import select

    try:
        with SessionLocal() as s:
            seen = s.execute(select(WorkerHeartbeat.seen_at).where(WorkerHeartbeat.worker_id.like(f"{socket.gethostname()}:%")).order_by(WorkerHeartbeat.seen_at.desc()).limit(1)).scalar()
        return 0 if seen and (utcnow() - seen).total_seconds() <= max_age_sec else 1
    except Exception:  # noqa: BLE001
        return 1


if __name__ == "__main__":
    import sys

    if sys.argv[1:2] == ["--health"]:
        sys.exit(health())
    main()
