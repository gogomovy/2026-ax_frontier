"""FastAPI 앱 — 인증 · 화면 API · 상태 API · 관리자 API.

web(Next.js) 이 같은 출처의 `/backend/*` 를 이 서버로 프록시하므로 CORS 는 열지 않는다.
"""
from __future__ import annotations

import logging
import time

from fastapi import FastAPI, Request
from starlette.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from sqlalchemy import text

from nhdip.api import admin_core, admin_data, analysis, assist, auth, cascade, documents, oidc, reports, screens, state
from nhdip import obs
from nhdip.db import SessionLocal, engine

obs.setup_logging()
access_log = logging.getLogger("nhdip.http")

app = FastAPI(title="NHDIP API", version="0.3.0", docs_url="/docs", redoc_url=None)
app.include_router(auth.router)
app.include_router(oidc.router)
app.include_router(screens.router)
app.include_router(state.router)
app.include_router(cascade.router)
app.include_router(reports.router)
app.include_router(documents.router)
app.include_router(analysis.router)
app.include_router(assist.router)
app.include_router(admin_core.router)
app.include_router(admin_data.router)


_slow_cache: dict[str, float] = {"value": 1000.0, "at": 0.0}


def _slow_ms() -> int:
    """설정 `obs.slow_request_ms` (60초 캐시)."""
    from nhdip.models import Setting

    if time.monotonic() - _slow_cache["at"] > 60:
        try:
            with SessionLocal() as s:
                v = s.get(Setting, "obs.slow_request_ms")
                _slow_cache["value"] = float(v.value) if v and v.value is not None else 1000.0
        except Exception:  # noqa: BLE001
            pass
        _slow_cache["at"] = time.monotonic()
    return int(_slow_cache["value"])


def _record_request(row: dict) -> None:
    from nhdip.models import RequestLog

    try:
        with SessionLocal() as s:
            s.add(RequestLog(**row))
            s.commit()
    except Exception:  # noqa: BLE001 — 관측 기록 실패가 업무 응답을 막지 않는다
        logging.getLogger("nhdip.obs").warning("request_log 기록 실패", exc_info=True)


@app.middleware("http")
async def trace_and_security(request: Request, call_next):
    """추적 ID(작업 0.5): traceparent/X-Trace-Id 이어받기 → 응답 헤더 · 로그 · DB 기록(변경 · 오류 · 느린 요청)."""
    trace_id = obs.from_headers(request.headers)
    with obs.scope(trace_id) as stats:
        from nhdip.models import utcnow

        started = utcnow()  # 구간 시작 시각 (기록은 응답 후)
        t0 = time.perf_counter()
        status = 500
        try:
            resp = await call_next(request)
            status = resp.status_code
        except Exception:
            logging.getLogger("nhdip.http").exception("처리되지 않은 오류 %s %s", request.method, request.url.path)
            resp = JSONResponse({"detail": "내부 오류가 발생했습니다", "traceId": trace_id}, status_code=500)
        ms = round((time.perf_counter() - t0) * 1000)
        route = getattr(request.scope.get("route"), "path", None)
        access_log.info("%s %s %s %dms db=%d/%.0fms", request.method, request.url.path, status, ms, stats["queries"], stats["ms"])
        path = request.url.path
        if path != "/health" and (request.method not in ("GET", "HEAD", "OPTIONS") or status >= 500 or ms >= _slow_ms()):
            row = {"at": started, "trace_id": trace_id, "method": request.method, "path": path[:300], "route": route, "status": status, "duration_ms": ms, "db_queries": int(stats["queries"]), "db_ms": round(stats["ms"]), "actor": stats.get("actor")}
            await run_in_threadpool(_record_request, row)
    resp.headers["X-Trace-Id"] = trace_id
    resp.headers["traceparent"] = obs.traceparent(trace_id)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Cache-Control", "no-store")
    return resp


@app.get("/health")
def health():
    try:
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
        return {"ok": True}
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(exc)[:200]}, status_code=503)
