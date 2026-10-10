"""LiteLLM(OpenAI 호환) 클라이언트 — 에이전트별 연결 · 키 · 모델 · 파라미터 (LLM-01~06).

설정 해석 순서: 에이전트 override > 에이전트 프로필 > 기본 프로필(is_default).
모든 호출은 ops.llm_call 에 입력(messages) · 출력 · 파라미터 스냅샷 · 토큰 · 지연과 함께 기록된다.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from nhdip.models import Agent, LlmCall, LlmConnection, LlmProfile, Prompt
from nhdip.security import decrypt_secret

PARAM_KEYS = ("temperature", "top_p", "max_tokens")


class LlmUnavailable(RuntimeError):
    """설정 미완료(모델·연결 없음) 또는 에이전트 비활성 — 템플릿 폴백 대상."""


class LlmError(RuntimeError):
    """호출 실패(재시도 후) — 템플릿 폴백 대상."""


class LlmBudgetExceeded(LlmError):
    """월 예산 초과로 호출을 막음 — LlmError 로 처리되는 모든 경로(서술 · 구조화 · 질의)가 기존 폴백을 그대로 쓴다."""


@dataclass
class ResolvedLlm:
    agent_code: str | None
    connection_id: int | None
    connection_name: str | None
    base_url: str
    api_key: str
    model: str
    params: dict[str, Any]
    timeout: float
    retries: int
    tools_enabled: bool
    system_prompt: str = ""
    user_template: str = ""
    prompt_version: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def snapshot(self) -> dict[str, Any]:
        return {
            "connection": self.connection_name,
            "model": self.model,
            **self.params,
            "timeout": self.timeout,
            "retries": self.retries,
            "tools_enabled": self.tools_enabled,
            "prompt_version": self.prompt_version,
            **({"extra": self.extra} if self.extra else {}),
        }


def resolve(session: Session, agent_code: str | None) -> ResolvedLlm:
    agent = session.get(Agent, agent_code) if agent_code else None
    if agent_code and not agent:
        raise LlmUnavailable(f"에이전트 없음: {agent_code}")
    if agent and not agent.enabled:
        raise LlmUnavailable(f"에이전트 비활성: {agent_code}")
    profile = session.get(LlmProfile, agent.profile_id) if agent and agent.profile_id else None
    if not profile:
        profile = session.execute(select(LlmProfile).where(LlmProfile.is_default)).scalars().first()
    ov = dict(agent.override or {}) if agent else {}

    def pick(key, default=None):
        if ov.get(key) not in (None, ""):
            return ov[key]
        if profile is not None and getattr(profile, key, None) not in (None, ""):
            return getattr(profile, key)
        return default

    conn_id = pick("connection_id")
    conn = session.get(LlmConnection, int(conn_id)) if conn_id else None
    if not conn or not conn.active:
        raise LlmUnavailable("LLM 연결이 설정되지 않았거나 비활성입니다")
    model = pick("model", "")
    if not model:
        raise LlmUnavailable("모델명이 설정되지 않았습니다")
    params = {k: pick(k) for k in PARAM_KEYS if pick(k) is not None}
    extra = {**(profile.extra if profile else {}), **(ov.get("extra") or {})}
    prompt = None
    if agent:
        q = select(Prompt).where(Prompt.agent_code == agent.code)
        q = q.where(Prompt.version == agent.prompt_version) if agent.prompt_version else q.order_by(Prompt.version.desc())
        prompt = session.execute(q.limit(1)).scalar()
    return ResolvedLlm(
        agent_code=agent.code if agent else None,
        connection_id=conn.id,
        connection_name=conn.name,
        base_url=conn.base_url.rstrip("/"),
        api_key=decrypt_secret(conn.api_key_enc),
        model=model,
        params=params,
        timeout=float(pick("timeout_sec", 60.0)),
        retries=int(pick("retries", 2)),
        tools_enabled=bool(pick("tools_enabled", False)),
        system_prompt=prompt.system if prompt else "",
        user_template=prompt.user_template if prompt else "",
        prompt_version=prompt.version if prompt else None,
        extra=extra,
    )


def _headers(api_key: str) -> dict[str, str]:
    h = {"Content-Type": "application/json"}
    if api_key:
        h["Authorization"] = f"Bearer {api_key}"
    return h


def _url(base: str, path: str) -> str:
    # base_url 이 /v1 로 끝나도, 아니어도 동작 (LiteLLM 은 두 경로 모두 제공)
    return f"{base}{path}"


@dataclass
class ChatResult:
    text: str
    tool_calls: list[dict[str, Any]]
    raw: dict[str, Any]
    call_id: str
    message: dict[str, Any]


def chat(
    session: Session,
    cfg: ResolvedLlm,
    messages: list[dict[str, Any]],
    *,
    tools: list[dict[str, Any]] | None = None,
    json_mode: bool = False,
    node_run_id: str | None = None,
    workflow_run_id: str | None = None,
    purpose: str = "chat",
) -> ChatResult:
    from .budget import check as check_budget

    check_budget(session, cfg.agent_code)  # 월 예산 초과 + 차단 설정이면 LlmBudgetExceeded (4.7)
    body: dict[str, Any] = {"model": cfg.model, "messages": messages, **cfg.params, **cfg.extra}
    if tools and cfg.tools_enabled:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    if json_mode and not tools:
        body["response_format"] = {"type": "json_object"}
    call = LlmCall(
        node_run_id=node_run_id,
        workflow_run_id=workflow_run_id,
        agent_code=cfg.agent_code,
        purpose=purpose,
        connection_name=cfg.connection_name,
        base_url=cfg.base_url,
        model=cfg.model,
        params=cfg.snapshot(),
        messages=messages,
    )
    session.add(call)
    session.flush()
    t0 = time.monotonic()
    last_err = ""
    attempts = 0
    for attempt in range(cfg.retries + 1):
        attempts = attempt + 1
        try:
            resp = httpx.post(_url(cfg.base_url, "/chat/completions"), headers=_headers(cfg.api_key), json=body, timeout=cfg.timeout)
            if resp.status_code == 400 and "response_format" in body:
                # 일부 모델은 JSON 모드를 지원하지 않는다 → 끄고 재시도
                body.pop("response_format", None)
                continue
            if resp.status_code >= 500 or resp.status_code == 429:
                last_err = f"HTTP {resp.status_code}: {resp.text[:300]}"
                time.sleep(min(2**attempt, 8))
                continue
            if resp.status_code >= 400:
                last_err = f"HTTP {resp.status_code}: {resp.text[:500]}"
                break
            data = resp.json()
            msg = (data.get("choices") or [{}])[0].get("message") or {}
            usage = data.get("usage") or {}
            call.response = data
            call.output_text = msg.get("content") or ""
            call.prompt_tokens = usage.get("prompt_tokens")
            call.completion_tokens = usage.get("completion_tokens")
            call.latency_ms = int((time.monotonic() - t0) * 1000)
            call.status = "ok"
            call.params = {**call.params, "attempts": attempts}
            return ChatResult(call.output_text, msg.get("tool_calls") or [], data, call.id, msg)
        except (httpx.HTTPError, ValueError) as exc:
            last_err = f"{type(exc).__name__}: {exc}"
            time.sleep(min(2**attempt, 8))
    call.status = "error"
    call.error = last_err
    call.latency_ms = int((time.monotonic() - t0) * 1000)
    call.params = {**call.params, "attempts": attempts}
    raise LlmError(last_err)


def embed(session: Session, cfg: ResolvedLlm, texts: list[str], *, workflow_run_id: str | None = None, node_run_id: str | None = None) -> list[list[float]]:
    from .budget import check as check_budget

    check_budget(session, cfg.agent_code)
    call = LlmCall(
        node_run_id=node_run_id,
        workflow_run_id=workflow_run_id,
        agent_code=cfg.agent_code,
        purpose="embedding",
        connection_name=cfg.connection_name,
        base_url=cfg.base_url,
        model=cfg.model,
        params=cfg.snapshot(),
        messages={"inputs": len(texts), "sample": texts[0][:200] if texts else ""},
    )
    session.add(call)
    t0 = time.monotonic()
    try:
        resp = httpx.post(_url(cfg.base_url, "/embeddings"), headers=_headers(cfg.api_key), json={"model": cfg.model, "input": texts}, timeout=cfg.timeout)
        resp.raise_for_status()
        data = resp.json()
        vecs = [d["embedding"] for d in sorted(data["data"], key=lambda d: d.get("index", 0))]
        call.status = "ok"
        call.prompt_tokens = (data.get("usage") or {}).get("prompt_tokens")
        call.output_text = f"{len(vecs)} vectors × {len(vecs[0]) if vecs else 0} dim"
        return vecs
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        call.status = "error"
        call.error = str(exc)[:1000]
        raise LlmError(str(exc)) from exc
    finally:
        call.latency_ms = int((time.monotonic() - t0) * 1000)


def test_connection(base_url: str, api_key: str, model: str | None = None, timeout: float = 15.0) -> dict[str, Any]:
    """GET /models 로 키에 허용된 모델 목록·지연을 확인하고, 모델이 주어지면 1토큰 호출까지 확인."""
    out: dict[str, Any] = {"ok": False, "base_url": base_url}
    t0 = time.monotonic()
    try:
        r = httpx.get(_url(base_url.rstrip("/"), "/models"), headers=_headers(api_key), timeout=timeout)
        out["models_status"] = r.status_code
        out["latency_ms"] = int((time.monotonic() - t0) * 1000)
        if r.status_code == 200:
            out["models"] = [m.get("id") for m in (r.json().get("data") or [])][:200]
            out["ok"] = True
        else:
            out["error"] = r.text[:300]
        if model:
            t1 = time.monotonic()
            c = httpx.post(
                _url(base_url.rstrip("/"), "/chat/completions"),
                headers=_headers(api_key),
                json={"model": model, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 1},
                timeout=timeout * 2,
            )
            out["chat_status"] = c.status_code
            out["chat_latency_ms"] = int((time.monotonic() - t1) * 1000)
            out["chat_ok"] = c.status_code == 200
            if c.status_code != 200:
                out["chat_error"] = c.text[:300]
            out["ok"] = out["ok"] and out["chat_ok"]
    except httpx.HTTPError as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def parse_json(text: str) -> Any:
    """모델 출력에서 JSON 본문을 꺼낸다(코드펜스·앞뒤 설명 허용)."""
    s = text.strip()
    if s.startswith("```"):
        s = s.strip("`")
        s = s[s.find("\n") + 1 :] if "\n" in s else s
    start = min([i for i in (s.find("{"), s.find("[")) if i >= 0], default=-1)
    if start < 0:
        raise ValueError("JSON 없음")
    end = max(s.rfind("}"), s.rfind("]"))
    return json.loads(s[start : end + 1])
