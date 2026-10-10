"""관측성 기본 배선 (작업 0.5 · NFR-09) — 단일 추적 ID 로 HTTP → 이벤트 → 워커 → 계산 · LLM · DB 구간을 잇는다.

- 추적 ID: W3C `traceparent`(00-<32hex>-<16hex>-<flags>) 또는 `X-Trace-Id` 를 이어받고, 없으면 새로 만든다.
- contextvar 로 요청/작업 범위에 보관 → 로그 레코드 · 새로 쓰는 이벤트 · 감사 · 실행 · LLM 호출 행에 자동 기록.
- DB 구간: SQLAlchemy 커서 실행 이벤트로 질의 수 · 소요(ms)를 범위별로 합산.
외부 수집기(OpenTelemetry · Langfuse)는 Q23 추천안에 따라 보류 — 같은 추적 ID 형식이라 나중에 내보내기만 붙이면 된다.
"""
from __future__ import annotations

import contextvars
import logging
import re
import secrets
import time
from contextlib import contextmanager
from typing import Any, Iterator

_trace: contextvars.ContextVar[str | None] = contextvars.ContextVar("nhdip_trace_id", default=None)
_db: contextvars.ContextVar[dict[str, float] | None] = contextvars.ContextVar("nhdip_db_stats", default=None)

_TRACEPARENT = re.compile(r"^[0-9a-f]{2}-([0-9a-f]{32})-[0-9a-f]{16}-[0-9a-f]{2}$")
_HEX32 = re.compile(r"^[0-9a-f]{32}$")


def new_trace_id() -> str:
    return secrets.token_hex(16)


def current() -> str | None:
    """현재 범위의 추적 ID (모델 컬럼 기본값으로도 쓴다)."""
    return _trace.get()


def current_or_new() -> str:
    """이벤트처럼 흐름의 시작점이 되는 행 — 범위 밖(정기 실행 등)이면 새 추적 ID 로 시작한다."""
    return _trace.get() or new_trace_id()


def from_headers(headers: Any) -> str:
    tp = (headers.get("traceparent") or "").strip().lower()
    m = _TRACEPARENT.match(tp)
    if m and m.group(1) != "0" * 32:
        return m.group(1)
    xt = (headers.get("x-trace-id") or "").strip().lower()
    return xt if _HEX32.match(xt) else new_trace_id()


def traceparent(trace_id: str) -> str:
    return f"00-{trace_id}-{secrets.token_hex(8)}-01"


@contextmanager
def scope(trace_id: str | None) -> Iterator[dict[str, float]]:
    """추적 ID · DB 통계 범위. 끝나면 이전 값으로 되돌린다."""
    stats = {"queries": 0, "ms": 0.0}
    t1 = _trace.set(trace_id or new_trace_id())
    t2 = _db.set(stats)
    try:
        yield stats
    finally:
        _trace.reset(t1)
        _db.reset(t2)


def db_stats() -> dict[str, float] | None:
    return _db.get()


def note(key: str, value: Any) -> None:
    """현재 범위 요약에 값 기록 (예: 요청 사용자 사번)."""
    st = _db.get()
    if st is not None:
        st[key] = value  # type: ignore[assignment]


# ── 로그 ─────────────────────────────────────────────────────
class TraceFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = _trace.get() or "-"
        return True


LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s [trace=%(trace_id)s] %(message)s"


def setup_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    if not any(isinstance(f, TraceFilter) for h in root.handlers for f in h.filters):
        logging.basicConfig(level=level, format=LOG_FORMAT, force=True)
        for h in logging.getLogger().handlers:
            h.addFilter(TraceFilter())


# ── DB 구간 ─────────────────────────────────────────────────
def instrument_engine(engine: Any) -> None:
    from sqlalchemy import event

    if getattr(engine, "_nhdip_obs", False):
        return

    @event.listens_for(engine, "before_cursor_execute")
    def _before(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        conn.info.setdefault("nhdip_t0", []).append(time.perf_counter())

    @event.listens_for(engine, "after_cursor_execute")
    def _after(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        stack = conn.info.get("nhdip_t0")
        if not stack:
            return
        dt = (time.perf_counter() - stack.pop()) * 1000
        st = _db.get()
        if st is not None:
            st["queries"] += 1
            st["ms"] += dt

    engine._nhdip_obs = True  # type: ignore[attr-defined]
