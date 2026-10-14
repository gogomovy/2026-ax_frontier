"""LLM 비용 · 예산 관리 (작업 4.7) — 월 사용량(토큰 · 금액) 집계와 예산 초과 시 경고/차단.

설정(관리자 편집)
  llm.pricing : {"모델명" | "*": {"prompt_per_1k": 원, "completion_per_1k": 원}} — 비우면 금액 0(사내 게이트웨이)
  llm.budget  : {"monthly_tokens": 0, "monthly_cost": 0, "per_agent_tokens": {}, "on_exceed": "warn" | "block", "warn_pct": 80}
               0 은 한도 없음. block 이면 초과 후 호출을 막고(LlmUnavailable) 서술은 기존 문장 유지(축소 실행)
               cache_sec(기본 30) — 호출 전 검사가 쓰는 집계 보관 시간(Phase M · LLM-P09). 0 이면 호출마다 집계
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from nhdip.models import LlmCall, Setting

DEFAULT_BUDGET = {"monthly_tokens": 0, "monthly_cost": 0, "per_agent_tokens": {}, "on_exceed": "warn", "warn_pct": 80}


def _setting(session: Session, key: str, default: Any) -> Any:
    s = session.get(Setting, key)
    return s.value if s and s.value is not None else default


def month_start(now: datetime | None = None) -> datetime:
    n = now or datetime.now(timezone.utc)
    return n.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _price(pricing: dict[str, Any], model: str | None) -> dict[str, float]:
    p = pricing.get(model or "") or pricing.get("*") or {}
    return {"prompt": float(p.get("prompt_per_1k", 0) or 0), "completion": float(p.get("completion_per_1k", 0) or 0)}


def usage(session: Session, since: datetime | None = None) -> dict[str, Any]:
    since = since or month_start()
    pricing = _setting(session, "llm.pricing", {}) or {}
    rows = session.execute(
        select(LlmCall.agent_code, LlmCall.model, func.count(), func.coalesce(func.sum(LlmCall.prompt_tokens), 0), func.coalesce(func.sum(LlmCall.completion_tokens), 0))
        .where(LlmCall.created_at >= since, LlmCall.status == "ok")
        .group_by(LlmCall.agent_code, LlmCall.model)
    ).all()
    items, tokens, cost = [], 0, 0.0
    for agent, model, calls, pt, ct in rows:
        p = _price(pricing, model)
        c = pt / 1000 * p["prompt"] + ct / 1000 * p["completion"]
        items.append({"agent": agent, "model": model, "calls": calls, "promptTokens": int(pt), "completionTokens": int(ct), "tokens": int(pt + ct), "cost": round(c, 2)})
        tokens += int(pt + ct)
        cost += c
    return {"since": since.isoformat(), "tokens": tokens, "cost": round(cost, 2), "items": sorted(items, key=lambda x: x["tokens"], reverse=True)}


def status(session: Session) -> dict[str, Any]:
    b = {**DEFAULT_BUDGET, **(_setting(session, "llm.budget", {}) or {})}
    u = usage(session)
    def pct(used: float, limit: float) -> float | None:
        return round(used / limit * 100, 1) if limit else None
    per_agent = {}
    for code, lim in (b.get("per_agent_tokens") or {}).items():
        used = sum(i["tokens"] for i in u["items"] if i["agent"] == code)
        per_agent[code] = {"used": used, "limit": lim, "pct": pct(used, lim)}
    out = {
        "budget": b,
        "usage": u,
        "tokensPct": pct(u["tokens"], float(b["monthly_tokens"] or 0)),
        "costPct": pct(u["cost"], float(b["monthly_cost"] or 0)),
        "perAgent": per_agent,
    }
    levels = [x for x in (out["tokensPct"], out["costPct"], *[a["pct"] for a in per_agent.values()]) if x is not None]
    out["maxPct"] = max(levels) if levels else None
    return out


_CACHE: dict[str, Any] = {}  # 호출 전 검사용 집계 보관 {"key": 예산 설정 지문, "at": monotonic, "status": ...} (Phase M · LLM-P09)
_CACHE_LOCK = threading.Lock()


def _cached_status(session: Session, b: dict[str, Any]) -> dict[str, Any]:
    """월 사용량 집계를 cache_sec(기본 30초) 동안 보관한다 — 호출마다 ops.llm_call 전체 집계를 돌지 않게.
    예산 설정이 바뀌면(지문 다름) 바로 다시 집계한다. 관리자 화면(status)은 보관 없이 늘 새로 집계."""
    ttl = float(b.get("cache_sec", 30) or 0)
    key = json.dumps(b, sort_keys=True, default=str)
    now = time.monotonic()
    with _CACHE_LOCK:
        if ttl > 0 and _CACHE.get("key") == key and now - float(_CACHE.get("at", 0)) < ttl:
            return _CACHE["status"]
    st = status(session)
    with _CACHE_LOCK:
        _CACHE.update(key=key, at=now, status=st)
    return st


def clear_cache() -> None:
    with _CACHE_LOCK:
        _CACHE.clear()


def check(session: Session, agent_code: str | None) -> None:
    """호출 전 예산 검사 — on_exceed=block 이고 한도를 넘었으면 LlmBudgetExceeded(LlmError)."""
    b = {**DEFAULT_BUDGET, **(_setting(session, "llm.budget", {}) or {})}
    if b.get("on_exceed") != "block" or not (b.get("monthly_tokens") or b.get("monthly_cost") or b.get("per_agent_tokens")):
        return
    st = _cached_status(session, b)
    over = (st["tokensPct"] or 0) >= 100 or (st["costPct"] or 0) >= 100
    if agent_code and agent_code in st["perAgent"]:
        over = over or (st["perAgent"][agent_code]["pct"] or 0) >= 100
    if over:
        from .client import LlmBudgetExceeded

        raise LlmBudgetExceeded("이번 달 LLM 예산을 넘었습니다 — 관리자 [운영 알림 · 비용]에서 예산을 확인하세요")
