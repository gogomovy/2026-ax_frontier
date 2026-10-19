"""요청 속도 제한 (B.32 · B.33) — 로그인 · 가입 · 질의 등 남용 방지.

기준은 설정 `auth.rate_limits` 의 {이름: [허용 횟수, 초]} — 0 이면 끄기.
저장 위치는 설정 `auth.rate_limit_backend`:
  db      (기본) PostgreSQL `ops.rate_limit` 고정 창 카운터 — API 프로세스 · 컨테이너가 여러 개여도 함께 센다.
          업무 트랜잭션과 따로 바로 기록한다(요청이 거부 · 롤백돼도 시도 횟수는 남는다).
  memory  프로세스 메모리 슬라이딩 창 — DB 를 쓰지 않는다(프로세스마다 따로 셈).
DB 기록이 실패하면 메모리 방식으로 대신 센다(속도 제한 장애가 로그인을 막지 않도록).
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from nhdip.models import Setting

DEFAULTS = {"login_ip": [30, 300], "login_emp": [10, 300], "signup_ip": [10, 3600], "signup_lookup_ip": [30, 300], "assist_user": [30, 60], "assist_feedback": [30, 60], "assist_scope": [60, 60], "stream_user": [10, 60], "request_user": [20, 86400]}
_hits: dict[str, deque[float]] = {}
_lock = threading.Lock()
log = logging.getLogger("nhdip.ratelimit")

_UPSERT = text(
    "INSERT INTO ops.rate_limit (key, window_start, count) VALUES (:k, now(), 1) "
    "ON CONFLICT (key) DO UPDATE SET "
    " count = CASE WHEN ops.rate_limit.window_start <= now() - make_interval(secs => :w) THEN 1 ELSE ops.rate_limit.count + 1 END, "
    " window_start = CASE WHEN ops.rate_limit.window_start <= now() - make_interval(secs => :w) THEN now() ELSE ops.rate_limit.window_start END "
    "RETURNING count, EXTRACT(EPOCH FROM (now() - window_start))"
)


def limits(session: Session) -> dict[str, list[int]]:
    s = session.get(Setting, "auth.rate_limits")
    return {**DEFAULTS, **(s.value if s and isinstance(s.value, dict) else {})}


def backend(session: Session) -> str:
    s = session.get(Setting, "auth.rate_limit_backend")
    return str(s.value) if s and s.value in ("db", "memory") else "db"


def _deny(retry: int) -> None:
    retry = max(int(retry), 1)
    raise HTTPException(429, f"요청이 너무 많습니다. {retry}초 후 다시 시도하세요", headers={"Retry-After": str(retry)})


def _memory(k: str, n: int, window: int) -> None:
    now = time.monotonic()
    with _lock:
        q = _hits.setdefault(k, deque())
        while q and q[0] <= now - window:
            q.popleft()
        if len(q) >= n:
            _deny(window - (now - q[0]) + 1)
        q.append(now)


def _db(k: str, n: int, window: int) -> None:
    from nhdip.db import engine

    with engine.begin() as c:  # 업무 트랜잭션과 따로 즉시 커밋
        count, age = c.execute(_UPSERT, {"k": k[:200], "w": window}).one()
    if count > n:
        _deny(window - float(age) + 1)


def check(session: Session, name: str, key: str | None) -> None:
    """허용 횟수를 넘으면 429. key 가 없으면(IP 미상 등) 검사하지 않는다."""
    if not key:
        return
    n, window = (limits(session).get(name) or [0, 0])[:2]
    if not n:
        return
    k = f"{name}:{key}"
    if backend(session) == "db":
        try:
            _db(k, int(n), int(window))
            return
        except HTTPException:
            raise
        except Exception:  # noqa: BLE001 — DB 카운터 장애 시 메모리로 대신
            log.warning("rate_limit DB 기록 실패 — 메모리 방식으로 대신", exc_info=True)
    _memory(k, int(n), int(window))


def reset() -> None:
    """테스트 · 운영 점검용 — 메모리 · DB 카운터를 비운다."""
    with _lock:
        _hits.clear()
    try:
        from nhdip.db import engine

        with engine.begin() as c:
            c.execute(text("DELETE FROM ops.rate_limit"))
    except Exception:  # noqa: BLE001
        pass


def purge(session: Session, older_than_sec: int = 86400) -> int:
    """창이 지난 카운터 정리(보관 정리에서 호출)."""
    res = session.execute(text("DELETE FROM ops.rate_limit WHERE window_start < now() - make_interval(secs => :s)"), {"s": older_than_sec})
    return res.rowcount or 0
