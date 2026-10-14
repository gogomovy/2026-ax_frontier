"""LLM 연결 차단기 (Phase M · 요구사항 LLM-P03 · Q187).

게이트웨이가 죽었을 때 에이전트마다 재시도 · 대기(최대 수십 초)를 되풀이하면 워크플로 전체가 늘어진다.
연결(LlmConnection)마다 연속 실패를 세다가 기준(설정 `llm.breaker.failures`, 기본 3)에 닿으면 `open_sec`(기본 120초) 동안
그 연결로 보내지 않고 곧바로 LlmError 를 낸다 — 호출자는 이미 있는 규칙 대체로 넘어간다. 시간이 지나면 한 번 보내 보고(반열림),
성공하면 닫고 실패하면 다시 연다.

상태는 프로세스 메모리(API · 워커 각각)다 — 공유 저장소 없이도 한 프로세스 안의 연쇄 대기를 끊는 것이 목적이다.
설정 `failures` 를 0 으로 하면 끈다.
"""
from __future__ import annotations

import threading
import time
from typing import Any

from sqlalchemy.orm import Session

from .client import LlmError

DEFAULT = {"failures": 3, "open_sec": 120}
_LOCK = threading.Lock()
_STATE: dict[str, dict[str, Any]] = {}  # 연결 키 → {fails, open_until, last_error, opened_at}


def _key(cfg: Any) -> str:
    return f"conn:{cfg.connection_id}" if getattr(cfg, "connection_id", None) is not None else f"url:{getattr(cfg, 'base_url', '')}"


def policy(session: Session | None) -> dict[str, int]:
    try:
        from nhdip.models import Setting

        st = session.get(Setting, "llm.breaker") if session is not None else None
        raw = st.value if st is not None and isinstance(st.value, dict) else {}
    except Exception:  # noqa: BLE001 — 설정을 못 읽으면 기본값
        raw = {}
    out = dict(DEFAULT)
    for k in DEFAULT:
        try:
            if raw.get(k) is not None:
                out[k] = max(0, int(raw[k]))
        except (TypeError, ValueError):
            pass
    return out


class BreakerOpen(LlmError):
    """LlmError 라서 호출자의 기존 대체 경로(규칙 · 템플릿)를 그대로 탄다."""

    def __init__(self, name: str, remaining: int, last_error: str):
        super().__init__(f"LLM 연결 '{name}' 차단 중 — 연속 실패로 {remaining}초 동안 보내지 않습니다(마지막 오류: {last_error[:120]})")
        self.remaining = remaining


def before_call(session: Session | None, cfg: Any) -> None:
    """열려 있으면 BreakerOpen. 열림 시간이 지났으면 한 번 보내게 둔다(반열림)."""
    pol = policy(session)
    if pol["failures"] <= 0:
        return
    with _LOCK:
        st = _STATE.get(_key(cfg))
        if not st or not st.get("open_until"):
            return
        now = time.monotonic()
        if now < st["open_until"]:
            raise BreakerOpen(getattr(cfg, "connection_name", None) or getattr(cfg, "base_url", "?"), int(st["open_until"] - now) + 1, st.get("last_error") or "")
        st["open_until"] = None  # 반열림 — 이번 호출 결과로 닫거나 다시 연다
        st["half_open"] = True


def record_success(cfg: Any) -> None:
    with _LOCK:
        _STATE.pop(_key(cfg), None)


def record_failure(session: Session | None, cfg: Any, error: str) -> None:
    pol = policy(session)
    if pol["failures"] <= 0:
        return
    with _LOCK:
        st = _STATE.setdefault(_key(cfg), {"fails": 0, "open_until": None})
        st["fails"] = int(st.get("fails") or 0) + 1
        st["last_error"] = (error or "")[:300]
        st["name"] = getattr(cfg, "connection_name", None)
        if st.pop("half_open", False) or st["fails"] >= pol["failures"]:
            st["open_until"] = time.monotonic() + pol["open_sec"]
            st["opened_at"] = time.time()


def snapshot() -> list[dict[str, Any]]:
    """관리자 표시용 — 열려 있거나 실패가 쌓인 연결."""
    now = time.monotonic()
    with _LOCK:
        return [{"key": k, "name": v.get("name"), "fails": v.get("fails", 0), "open": bool(v.get("open_until") and v["open_until"] > now),
                 "remainingSec": max(0, int((v.get("open_until") or now) - now)), "lastError": v.get("last_error")} for k, v in _STATE.items()]


def reset(key: str | None = None) -> None:
    with _LOCK:
        if key is None:
            _STATE.clear()
        else:
            _STATE.pop(key, None)
