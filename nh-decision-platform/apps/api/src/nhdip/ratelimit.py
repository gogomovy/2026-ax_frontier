"""요청 속도 제한 (B.32) — 로그인 · 가입 · 질의 등 남용 방지.

슬라이딩 윈도(프로세스 메모리). 기준은 설정 `auth.rate_limits` 의 {이름: [허용 횟수, 초]} — 0 이면 끄기.
API 를 여러 프로세스로 띄우면 프로세스마다 따로 센다(운영에서는 앞단 게이트웨이 제한과 함께 쓴다).
"""
from __future__ import annotations

import threading
import time
from collections import deque

from fastapi import HTTPException
from sqlalchemy.orm import Session

from nhdip.models import Setting

DEFAULTS = {"login_ip": [30, 300], "login_emp": [10, 300], "signup_ip": [10, 3600], "assist_user": [30, 60], "stream_user": [10, 60], "request_user": [20, 86400]}
_hits: dict[str, deque[float]] = {}
_lock = threading.Lock()


def limits(session: Session) -> dict[str, list[int]]:
    s = session.get(Setting, "auth.rate_limits")
    return {**DEFAULTS, **(s.value if s and isinstance(s.value, dict) else {})}


def check(session: Session, name: str, key: str | None) -> None:
    """허용 횟수를 넘으면 429. key 가 없으면(IP 미상 등) 검사하지 않는다."""
    if not key:
        return
    n, window = (limits(session).get(name) or [0, 0])[:2]
    if not n:
        return
    now = time.monotonic()
    k = f"{name}:{key}"
    with _lock:
        q = _hits.setdefault(k, deque())
        while q and q[0] <= now - window:
            q.popleft()
        if len(q) >= n:
            retry = int(window - (now - q[0])) + 1
            raise HTTPException(429, f"요청이 너무 많습니다. {retry}초 후 다시 시도하세요", headers={"Retry-After": str(retry)})
        q.append(now)


def reset() -> None:
    with _lock:
        _hits.clear()
