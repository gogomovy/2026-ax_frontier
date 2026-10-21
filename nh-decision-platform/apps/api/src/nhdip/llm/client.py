"""LiteLLM(OpenAI 호환) 클라이언트 — 에이전트별 연결 · 키 · 모델 · 파라미터 (LLM-01~06).

설정 해석 순서: 에이전트 override > 에이전트 프로필 > 기본 프로필(is_default).
모든 호출은 ops.llm_call 에 입력(messages) · 출력 · 파라미터 스냅샷 · 토큰 · 지연과 함께 기록된다.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Iterator

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from nhdip.models import Agent, LlmCall, LlmConnection, LlmProfile, Prompt, new_id
from nhdip.security import decrypt_secret

PARAM_KEYS = ("temperature", "top_p", "max_tokens")
# 게이트웨이가 '지원하지 않는 파라미터' 로 거절한 (모델, 파라미터) — 이후 호출에서는 보내지 않는다 (B.37)
_UNSUPPORTED: dict[str, set[str]] = {}
_DROPPABLE = ("temperature", "top_p", "max_tokens", "presence_penalty", "frequency_penalty", "seed", "stop")


def _unsupported_param(text: str, body: dict) -> str | None:
    """400 응답이 특정 파라미터 미지원이면 그 이름 (LiteLLM UnsupportedParamsError · OpenAI 'Unsupported parameter')."""
    import re

    t = text or ""
    if "nsupported" not in t and "does not support" not in t and "not supported" not in t:
        return None
    for k in _DROPPABLE:
        if k in body and re.search(rf"\b{k}\b", t):
            return k
    return None


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
    if not (conn.base_url or "").strip():
        raise LlmUnavailable("LLM 주소가 입력되지 않았습니다 — 관리자 [LLM 연동]")
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
    try:
        api_key = decrypt_secret(conn.api_key_enc)
        timeout_sec, retry_n = float(pick("timeout_sec", 60.0)), int(pick("retries", 2))
    except Exception as exc:  # noqa: BLE001 — 암호 해독 실패(키 교체) · 잘못된 설정값은 '쓸 수 없음'으로 알려 호출자가 규칙으로 대체하게
        raise LlmUnavailable(f"LLM 설정을 읽을 수 없습니다 — {type(exc).__name__}: {str(exc)[:120]}") from exc
    return ResolvedLlm(
        agent_code=agent.code if agent else None,
        connection_id=conn.id,
        connection_name=conn.name,
        base_url=conn.base_url.rstrip("/"),
        api_key=api_key,
        model=model,
        params=params,
        timeout=timeout_sec,
        retries=retry_n,
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


def _log_messages(session: Session, messages: Any) -> Any:
    """호출 기록에 남길 메시지 — 설정 privacy.policy.mask_llm_log 이면 개인정보 형식 값을 가린다 (B.32)."""
    from nhdip.privacy import mask_obj, policy

    try:
        return mask_obj(messages) if policy(session).get("mask_llm_log", True) else messages
    except Exception:  # noqa: BLE001
        return mask_obj(messages)


def _outgoing(session: Session, messages: Any) -> Any:
    """게이트웨이로 보낼 메시지 — 설정 privacy.policy.mask_llm_input(기본 켬)이면 개인정보 형식 값을 가린다 (Phase M · LLM-P04 · Q186).
    설정을 못 읽으면 가리는 쪽으로. 호출자가 가진 원본 목록은 바꾸지 않는다(복사본을 보낸다)."""
    from nhdip.privacy import mask_obj, policy

    try:
        on = bool(policy(session).get("mask_llm_input", True))
    except Exception:  # noqa: BLE001
        on = True
    return mask_obj(messages) if on else messages


def _breaker_open(session: Session, cfg: "ResolvedLlm", purpose: str, workflow_run_id: str | None, node_run_id: str | None = None) -> None:
    """차단기가 열려 있으면 보내지 않고 기록(skipped)만 남긴 뒤 LlmError(BreakerOpen) — 호출자는 규칙 대체로 (LLM-P03)."""
    from .breaker import BreakerOpen, before_call

    try:
        before_call(session, cfg)
    except BreakerOpen as exc:
        call = LlmCall(node_run_id=node_run_id, workflow_run_id=workflow_run_id, agent_code=cfg.agent_code, purpose=purpose, connection_name=cfg.connection_name,
                       base_url=cfg.base_url, model=cfg.model, params={**cfg.snapshot(), "breaker": "open"}, messages=None)
        call.id = new_id()
        call.status, call.error, call.latency_ms = "skipped", str(exc)[:1000], 0
        _save_call(call)
        raise


def _breaker_result(session: Session, cfg: "ResolvedLlm", ok: bool, error: str = "") -> None:
    from .breaker import record_failure, record_success

    try:
        record_success(cfg) if ok else record_failure(session, cfg, error)
    except Exception:  # noqa: BLE001 — 차단기 기록 실패가 호출을 막지 않는다
        logging.getLogger("nhdip.llm").warning("차단기 기록 실패", exc_info=True)


def _save_call(call: LlmCall) -> None:
    """호출 기록은 업무 트랜잭션과 따로 저장한다 — 노드가 실패해 롤백돼도 비용 · 오류 기록이 남는다 (B.32)."""
    from nhdip.db import SessionLocal

    try:
        with SessionLocal() as s2:
            s2.merge(call)
            s2.commit()
    except Exception:  # noqa: BLE001 — 기록 실패가 업무를 막지 않는다
        logging.getLogger("nhdip.llm").warning("llm_call 기록 실패", exc_info=True)


# 출력 상한(max_tokens)을 늘리면 응답 시간도 늘어난다 — 대기 시간은 최소 '상한 ÷ 초당 토큰' 으로 (2026-10-12 LLM 모드 업로드 시험:
# 판단 호출이 6000 토큰으로 늘어난 뒤 고정 30초에 두 번 끊겨 규칙으로 대체됨). 1500 토큰이면 30초 — 기존 판단 대기와 같다.
MIN_TOKENS_PER_SEC = 50


def _timeout_for(base: float, max_tokens: Any) -> float:
    return max(float(base), float(max_tokens) / MIN_TOKENS_PER_SEC) if isinstance(max_tokens, int) and max_tokens > 0 else float(base)


def _max_tokens_cap(session: Session) -> int:
    """출력 잘림 시 늘릴 수 있는 max_tokens 상한 — 설정 llm.max_tokens_cap (기본 8000, 0 = 늘리지 않음)."""
    try:
        from nhdip.models import Setting

        s = session.get(Setting, "llm.max_tokens_cap") if session is not None else None
        return int(s.value) if s is not None and s.value is not None else 8000
    except Exception:  # noqa: BLE001
        return 8000


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
    _breaker_open(session, cfg, purpose, workflow_run_id, node_run_id)  # 연결이 연속 실패 중이면 곧바로 LlmError (LLM-P03)
    body: dict[str, Any] = {"model": cfg.model, "messages": _outgoing(session, messages), **cfg.params, **cfg.extra}
    if tools and cfg.tools_enabled:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    if json_mode and not tools:
        body["response_format"] = {"type": "json_object"}
    for k in _UNSUPPORTED.get(cfg.model, set()):
        body.pop(k, None)
    call = LlmCall(
        node_run_id=node_run_id,
        workflow_run_id=workflow_run_id,
        agent_code=cfg.agent_code,
        purpose=purpose,
        connection_name=cfg.connection_name,
        base_url=cfg.base_url,
        model=cfg.model,
        params=cfg.snapshot(),
        messages=_log_messages(session, messages),
    )
    call.id = new_id()
    t0 = time.monotonic()
    last_err = ""
    attempts = 0
    dropped: list[str] = []
    expanded: list[int] = []
    cap = _max_tokens_cap(session)
    transient = False  # 연결 문제(네트워크 · 시간 초과 · 5xx · 429)로 끝났는지 — 차단기는 이것만 센다(400 같은 요청 문제는 연결 탓이 아님)
    for attempt in range(cfg.retries + 1 + len(_DROPPABLE) + 2):
        if attempts - len(dropped) - len(expanded) > cfg.retries:
            break
        attempts += 1
        try:
            resp = httpx.post(_url(cfg.base_url, "/chat/completions"), headers=_headers(cfg.api_key), json=body, timeout=_timeout_for(cfg.timeout, body.get("max_tokens")))
            bad = _unsupported_param(resp.text, body) if resp.status_code == 400 else None
            if bad:
                # 모델이 받지 않는 파라미터(예: temperature 고정 모델) — 빼고 다시 보낸다(재시도 횟수에 넣지 않음)
                body.pop(bad, None)
                _UNSUPPORTED.setdefault(cfg.model, set()).add(bad)
                dropped.append(bad)
                logging.getLogger("nhdip.llm").warning("model %s 가 %s 를 지원하지 않아 빼고 다시 호출", cfg.model, bad)
                continue
            if resp.status_code == 400 and "response_format" in body:
                # 일부 모델은 JSON 모드를 지원하지 않는다 → 끄고 재시도
                body.pop("response_format", None)
                continue
            if resp.status_code >= 500 or resp.status_code == 429:
                last_err = f"HTTP {resp.status_code}: {resp.text[:300]}"
                transient = True
                time.sleep(min(2**attempt, 8))
                continue
            if resp.status_code >= 400:
                last_err = f"HTTP {resp.status_code}: {resp.text[:500]}"
                transient = resp.status_code in (401, 408)  # 키가 틀렸거나(401) 게이트웨이 시간 초과 — 그 연결 전체의 문제. 모델별 거절(403 · 404)은 세지 않는다
                break
            data = resp.json()
            choice = (data.get("choices") or [{}])[0]
            msg = choice.get("message") or {}
            usage = data.get("usage") or {}
            cur = body.get("max_tokens")
            if choice.get("finish_reason") == "length" and not msg.get("tool_calls") and isinstance(cur, int) and cur < cap and len(expanded) < 2:
                # 출력 상한에 걸려 잘림(추론형 모델은 생각 토큰이 상한을 먼저 씀) — 상한을 늘려 다시 보낸다(설정 llm.max_tokens_cap · B.40)
                body["max_tokens"] = min(cap, cur * 2)
                expanded.append(body["max_tokens"])
                logging.getLogger("nhdip.llm").warning("model %s 출력이 max_tokens %s 에서 잘려 %s 로 다시 호출", cfg.model, cur, body["max_tokens"])
                continue
            call.response = _log_messages(session, data)  # 응답 · 출력도 입력(messages)과 같은 개인정보 가림 정책으로 기록
            call.output_text = _log_messages(session, msg.get("content") or "")
            call.prompt_tokens = usage.get("prompt_tokens")
            call.completion_tokens = usage.get("completion_tokens")
            call.latency_ms = int((time.monotonic() - t0) * 1000)
            call.status = "ok"
            call.params = {**call.params, "attempts": attempts, **({"dropped": dropped} if dropped else {}), **({"max_tokens_expanded": expanded} if expanded else {}),
                           **({"truncated": True} if choice.get("finish_reason") == "length" else {})}
            out = ChatResult(call.output_text, msg.get("tool_calls") or [], data, call.id, msg)
            _save_call(call)
            _breaker_result(session, cfg, True)
            return out
        except (httpx.HTTPError, ValueError, KeyError, TypeError, IndexError, AttributeError) as exc:
            # 게이트웨이가 약속과 다른 모양(choices 없음 등)으로 답해도 오류 기록(ops.llm_call)을 남기고 LlmError 로 알린다
            last_err = f"{type(exc).__name__}: {exc}"
            transient = isinstance(exc, httpx.HTTPError)
            time.sleep(min(2**attempt, 8))
    call.status = "error"
    call.error = last_err
    call.latency_ms = int((time.monotonic() - t0) * 1000)
    call.params = {**call.params, "attempts": attempts}
    _save_call(call)
    if transient:
        _breaker_result(session, cfg, False, last_err)
    raise LlmError(last_err)


def chat_stream(
    session: Session,
    cfg: ResolvedLlm,
    messages: list[dict[str, Any]],
    *,
    tools: list[dict[str, Any]] | None = None,
    purpose: str = "chat",
    workflow_run_id: str | None = None,
) -> Iterator[tuple[str, Any]]:
    """스트리밍 호출(OpenAI 호환 `stream=true`) — ('delta', 글자 조각)을 내다가 마지막에 ('result', ChatResult) 하나.

    `chat` 과 같은 기록(ops.llm_call) · 예산 점검 · 지원하지 않는 파라미터 빼고 다시 보내기를 지킨다. 다른 점:
    - 재시도는 **첫 글자를 내보내기 전**의 연결 오류 · 429 · 5xx 에만 한다. 이미 내보낸 글자가 있으면 되돌릴 수 없으므로 LlmError.
    - 호출자가 중간에 그만두면(사용자의 [중지]) 연결을 닫고 기록을 `cancelled` 로 남긴다.
    - 도구 호출(tool_calls)은 조각을 모아 `chat` 과 같은 모양으로 돌려준다. 출력 상한 확장(max_tokens 늘려 재호출)은 하지 않는다 — 잘리면 잘린 채 끝낸다."""
    from .budget import check as check_budget

    check_budget(session, cfg.agent_code)
    _breaker_open(session, cfg, purpose, workflow_run_id)
    body: dict[str, Any] = {"model": cfg.model, "messages": _outgoing(session, messages), **cfg.params, **cfg.extra, "stream": True, "stream_options": {"include_usage": True}}
    if tools and cfg.tools_enabled:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    for k in _UNSUPPORTED.get(cfg.model, set()):
        body.pop(k, None)
    call = LlmCall(
        workflow_run_id=workflow_run_id, agent_code=cfg.agent_code, purpose=purpose, connection_name=cfg.connection_name, base_url=cfg.base_url, model=cfg.model,
        params={**cfg.snapshot(), "stream": True}, messages=_log_messages(session, messages),
    )
    call.id = new_id()
    t0 = time.monotonic()
    last_err = ""
    attempts = 0
    dropped: list[str] = []
    emitted = False
    finished = False
    transient = False
    parts: list[str] = []
    timeout = httpx.Timeout(connect=15.0, read=_timeout_for(cfg.timeout, body.get("max_tokens")), write=15.0, pool=15.0)  # read = 조각 사이 최대 대기
    try:
        for attempt in range(cfg.retries + 1 + len(_DROPPABLE) + 2):
            if attempts - len(dropped) > cfg.retries:
                break
            attempts += 1
            try:
                with httpx.stream("POST", _url(cfg.base_url, "/chat/completions"), headers=_headers(cfg.api_key), json=body, timeout=timeout) as resp:
                    if resp.status_code >= 400:
                        err_text = resp.read().decode("utf-8", "replace")
                        bad = _unsupported_param(err_text, body) if resp.status_code == 400 else None
                        if bad:
                            body.pop(bad, None)
                            _UNSUPPORTED.setdefault(cfg.model, set()).add(bad)
                            dropped.append(bad)
                            continue
                        if resp.status_code == 400 and "stream_options" in body:
                            body.pop("stream_options", None)  # 사용량 옵션을 모르는 게이트웨이
                            dropped.append("stream_options")
                            continue
                        last_err = f"HTTP {resp.status_code}: {err_text[:300]}"
                        transient = resp.status_code >= 500 or resp.status_code in (401, 408, 429)
                        if resp.status_code >= 500 or resp.status_code == 429:
                            time.sleep(min(2**attempt, 8))
                            continue
                        break
                    parts.clear()
                    tool_acc: dict[int, dict[str, Any]] = {}
                    usage: dict[str, Any] = {}
                    finish: str | None = None
                    for line in resp.iter_lines():
                        if not line.startswith("data:"):
                            continue
                        payload = line[5:].strip()
                        if payload == "[DONE]":
                            break
                        try:
                            chunk = json.loads(payload)
                        except ValueError:
                            continue
                        usage = chunk.get("usage") or usage
                        choice = (chunk.get("choices") or [{}])[0]
                        delta = choice.get("delta") or {}
                        if delta.get("content"):
                            parts.append(delta["content"])
                            emitted = True
                            yield "delta", delta["content"]
                        for tc in delta.get("tool_calls") or []:
                            acc = tool_acc.setdefault(int(tc.get("index", 0)), {"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                            acc["id"] = tc.get("id") or acc["id"]
                            fn = tc.get("function") or {}
                            acc["function"]["name"] += fn.get("name") or ""
                            acc["function"]["arguments"] += fn.get("arguments") or ""
                        finish = choice.get("finish_reason") or finish
                    text = "".join(parts)
                    tool_calls = [tool_acc[i] for i in sorted(tool_acc)]
                    message = {"role": "assistant", "content": text or None, **({"tool_calls": tool_calls} if tool_calls else {})}
                    raw = {"stream": True, "usage": usage, "finish_reason": finish}
                    call.response = raw
                    call.output_text = text
                    call.prompt_tokens = usage.get("prompt_tokens")
                    call.completion_tokens = usage.get("completion_tokens")
                    call.latency_ms = int((time.monotonic() - t0) * 1000)
                    call.status = "ok"
                    call.params = {**call.params, "attempts": attempts, **({"dropped": dropped} if dropped else {}), **({"truncated": True} if finish == "length" else {})}
                    finished = True
                    _save_call(call)
                    _breaker_result(session, cfg, True)
                    yield "result", ChatResult(text, tool_calls, raw, call.id, message)
                    return
            except (httpx.HTTPError, ValueError) as exc:
                last_err = f"{type(exc).__name__}: {exc}"
                transient = isinstance(exc, httpx.HTTPError)
                if emitted:
                    break  # 이미 글자를 내보냈다 — 같은 요청을 다시 보내면 글이 겹친다
                time.sleep(min(2**attempt, 8))
        call.status = "error"
        call.error = last_err
        call.latency_ms = int((time.monotonic() - t0) * 1000)
        call.params = {**call.params, "attempts": attempts}
        finished = True
        _save_call(call)
        if transient:
            _breaker_result(session, cfg, False, last_err)
        raise LlmError(last_err)
    finally:
        if not finished:  # 호출자가 중간에 그만둠(GeneratorExit) — 비용 · 지연 기록은 남긴다
            call.status = "cancelled"
            call.latency_ms = int((time.monotonic() - t0) * 1000)
            call.output_text = "".join(parts)
            _save_call(call)


def embed(session: Session, cfg: ResolvedLlm, texts: list[str], *, workflow_run_id: str | None = None, node_run_id: str | None = None) -> list[list[float]]:
    from .budget import check as check_budget

    check_budget(session, cfg.agent_code)
    _breaker_open(session, cfg, "embedding", workflow_run_id, node_run_id)
    texts = _outgoing(session, list(texts))  # 임베딩 입력도 게이트웨이로 나간다 — 같은 가림 정책 (LLM-P04)
    call = LlmCall(
        node_run_id=node_run_id,
        workflow_run_id=workflow_run_id,
        agent_code=cfg.agent_code,
        purpose="embedding",
        connection_name=cfg.connection_name,
        base_url=cfg.base_url,
        model=cfg.model,
        params=cfg.snapshot(),
        messages=_log_messages(session, {"inputs": len(texts), "sample": texts[0][:200] if texts else ""}),
    )
    call.id = new_id()
    t0 = time.monotonic()
    try:
        resp = httpx.post(_url(cfg.base_url, "/embeddings"), headers=_headers(cfg.api_key), json={"model": cfg.model, "input": texts}, timeout=cfg.timeout)
        resp.raise_for_status()
        data = resp.json()
        vecs = [d["embedding"] for d in sorted(data["data"], key=lambda d: d.get("index", 0))]
        if len(vecs) != len(texts):
            # 게이트웨이가 일부만 돌려주면 zip 이 조용히 잘라 일부 청크가 임베딩 없이 '완료'로 보인다 — 오류로 알린다
            raise ValueError(f"임베딩 {len(texts)}건을 요청했으나 {len(vecs)}건만 받음")
        call.status = "ok"
        call.prompt_tokens = (data.get("usage") or {}).get("prompt_tokens")
        call.output_text = f"{len(vecs)} vectors × {len(vecs[0]) if vecs else 0} dim"
        _breaker_result(session, cfg, True)
        return vecs
    except (httpx.HTTPError, KeyError, ValueError, TypeError, IndexError, AttributeError) as exc:
        call.status = "error"
        call.error = str(exc)[:1000]
        bad = isinstance(exc, httpx.HTTPStatusError) and exc.response is not None and exc.response.status_code < 500 and exc.response.status_code not in (401, 408, 429)
        if isinstance(exc, httpx.HTTPError) and not bad:
            _breaker_result(session, cfg, False, str(exc))
        raise LlmError(str(exc)) from exc
    finally:
        call.latency_ms = int((time.monotonic() - t0) * 1000)
        _save_call(call)


def test_connection(base_url: str, api_key: str, model: str | None = None, timeout: float = 15.0,
                    embedding_model: str | None = None) -> dict[str, Any]:
    """연결 확인 — GET /models(모델 목록 · 지연) + 채팅 모델 1토큰 호출 + 임베딩 모델 1건 호출.

    임베딩은 채팅과 호출 규격이 달라(`/embeddings`) 채팅 시험만으로는 확인되지 않는다.
    모델 이름 오타 · 키 권한 부족 · 게이트웨이 미등록을 저장 시점에 바로 알 수 있게 함께 호출한다.
    """
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
        if embedding_model:
            out.update(_test_embedding(base_url, api_key, embedding_model, timeout))
            out["ok"] = out["ok"] and bool(out.get("embed_ok"))
    except httpx.HTTPError as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def _test_embedding(base_url: str, api_key: str, model: str, timeout: float) -> dict[str, Any]:
    """임베딩 모델 1건 호출 — 차원 · 지연을 돌려준다(검색 품질은 차원이 맞아야 유지된다)."""
    out: dict[str, Any] = {"embed_model": model, "embed_ok": False}
    t0 = time.monotonic()
    try:
        r = httpx.post(
            _url(base_url.rstrip("/"), "/embeddings"),
            headers=_headers(api_key),
            json={"model": model, "input": "연결 확인"},
            timeout=timeout * 2,
        )
    except httpx.HTTPError as exc:
        out["embed_error"] = f"{type(exc).__name__}: {exc}"
        return out
    out["embed_status"] = r.status_code
    out["embed_latency_ms"] = int((time.monotonic() - t0) * 1000)
    if r.status_code != 200:
        out["embed_error"] = r.text[:300]
        return out
    try:
        vec = ((r.json().get("data") or [{}])[0] or {}).get("embedding") or []
    except ValueError as exc:
        out["embed_error"] = f"응답을 읽을 수 없습니다: {exc}"
        return out
    if not isinstance(vec, list) or not vec:
        out["embed_error"] = "임베딩 벡터가 비어 있습니다 — 임베딩 모델이 아닐 수 있습니다"
        return out
    out["embed_dim"] = len(vec)
    out["embed_ok"] = True
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
