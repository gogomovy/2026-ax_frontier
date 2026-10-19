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

from nhdip.api import admin_agentic, admin_bizconfig, admin_core, admin_data, admin_home, admin_knowledge, admin_sync, analysis, analysis_agents, analysis_spaces, assist, auth, cascade, db_uploads, documents, nc_sso, oidc, reports, screens, state
from nhdip import obs
from nhdip.config import check_runtime, docs_enabled, get_settings
from nhdip.db import SessionLocal, engine

obs.setup_logging()
access_log = logging.getLogger("nhdip.http")
_st = get_settings()
check_runtime(_st)  # 운영에서 기본 비밀값이면 기동 거부 (B.32)
_DOCS = docs_enabled(_st)

app = FastAPI(
    title="NHDIP API",
    version="0.3.0",
    docs_url="/docs" if _DOCS else None,
    openapi_url="/openapi.json" if _DOCS else None,
    redoc_url=None,
)
app.include_router(auth.router)
app.include_router(oidc.router)
app.include_router(nc_sso.router)
app.include_router(admin_sync.router)
app.include_router(screens.router)
app.include_router(state.router)
app.include_router(cascade.router)
app.include_router(reports.router)
app.include_router(documents.router)
app.include_router(analysis.router)
app.include_router(analysis_spaces.router)
app.include_router(analysis_agents.router)
app.include_router(analysis_agents.admin_router)
app.include_router(assist.router)
app.include_router(admin_core.router)
app.include_router(admin_agentic.router)
app.include_router(admin_bizconfig.router)  # /admin/datasets/auto-upload 이 /admin/datasets/{code} 보다 먼저
app.include_router(admin_data.router)
app.include_router(admin_home.router)
app.include_router(admin_knowledge.router)
app.include_router(db_uploads.router)
app.include_router(db_uploads.admin_router)


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


_SAFE_METHODS = ("GET", "HEAD", "OPTIONS")


def _origin_ok(request: Request) -> bool:
    """CSRF 방어 (B.32) — 변경 요청의 Origin 이 같은 출처(Host · X-Forwarded-Host)거나 허용 목록에 있어야 한다.

    Origin 이 없으면(서버 간 호출 · 내부 도구) 통과 — 세션 쿠키가 SameSite=Lax 라 교차 사이트 폼 전송은 쿠키가 실리지 않는다.
    """
    origin = request.headers.get("origin")
    if not origin or request.method in _SAFE_METHODS:
        return True
    if origin == "null":
        return False
    trusted = {o.strip().rstrip("/") for o in _st.trusted_origins.split(",") if o.strip()}
    if origin.rstrip("/") in trusted:
        return True
    host = origin.split("://", 1)[-1].split("/", 1)[0].lower()
    hosts = {h.strip().lower() for h in (request.headers.get("x-forwarded-host") or "").split(",") if h.strip()}
    hosts.add((request.headers.get("host") or "").lower())
    return host in hosts


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
            if _origin_ok(request):
                resp = await call_next(request)
            else:
                access_log.warning("교차 출처 변경 요청 차단 %s %s origin=%s", request.method, request.url.path, request.headers.get("origin"))
                resp = JSONResponse({"detail": "허용되지 않은 출처의 요청입니다"}, status_code=403)
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
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    if _st.cookie_secure:
        resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return resp


@app.get("/health")
def health():
    try:
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
        return {"ok": True}
    except Exception:  # noqa: BLE001 — 내부 오류 문구는 로그에만 (B.32)
        logging.getLogger("nhdip.http").warning("health: DB 연결 실패", exc_info=True)
        return JSONResponse({"ok": False, "error": "db unavailable"}, status_code=503)
