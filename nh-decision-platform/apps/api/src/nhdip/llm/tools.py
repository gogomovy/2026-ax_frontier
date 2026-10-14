"""커널 도구 호출 루프 (CALC-10) — LLM 이 calc_* 도구를 부르면 서버가 커널로 계산해 돌려준다. LLM 은 직접 계산하지 않는다.

Phase M(LLM-P06 · DOB-08) — 호출자가 `extra` 로 도구를 더할 수 있다(온톨로지 조회 · 반영된 자료 집계). LLM 계층은 그 도구의 내용을 모른다:
스키마 목록과 실행 함수만 받는다(계층 규칙 — llm 은 workflow · views 를 가져오지 않는다. 도구 구현은 knowledge.assist_tools).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator

from sqlalchemy.orm import Session

from nhdip.calc import REGISTRY, execute, tool_schemas

from .client import ChatResult, ResolvedLlm, chat, chat_stream


@dataclass
class ExtraTools:
    """호출자가 더하는 도구 — schemas(OpenAI tools 모양) · run(이름, 인자 dict) → 결과 dict. 이름은 calc_ 로 시작하지 않는다."""

    schemas: list[dict[str, Any]] = field(default_factory=list)
    run: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None

    def names(self) -> set[str]:
        return {s.get("function", {}).get("name") for s in self.schemas}


def run_tool(name: str, arguments: str | None, extra: ExtraTools | None = None) -> dict[str, Any]:
    if extra is not None and extra.run is not None and name in extra.names():
        try:
            args = json.loads(arguments or "{}")
            if not isinstance(args, dict):
                raise ValueError("인자는 JSON 객체여야 합니다")
            return extra.run(name, args)
        except Exception as exc:  # noqa: BLE001 — 도구 오류는 LLM 에 그대로 돌려준다
            return {"tool": name, "error": str(exc)[:300]}
    fid = (name or "").removeprefix("calc_").upper()
    if fid not in REGISTRY:
        return {"error": f"unknown tool {name}"}
    try:
        args = json.loads(arguments or "{}")
        r = execute(fid, args)
        return {"formula": fid, "value": None if r.value is None else str(r.value), **{k: v for k, v in r.extra.items()}}
    except Exception as exc:  # noqa: BLE001 — 도구 오류는 LLM 에 그대로 돌려준다
        return {"formula": fid, "error": str(exc)}


def _tools_for(cfg: ResolvedLlm, use_tools: bool, extra: ExtraTools | None) -> list[dict[str, Any]] | None:
    if not (use_tools and cfg.tools_enabled):
        return None
    return [*tool_schemas(), *((extra.schemas if extra is not None else []) or [])]


def chat_with_tools(
    session: Session,
    cfg: ResolvedLlm,
    messages: list[dict[str, Any]],
    *,
    use_tools: bool = True,
    max_rounds: int = 5,
    purpose: str = "chat",
    workflow_run_id: str | None = None,
    extra: ExtraTools | None = None,
) -> dict[str, Any]:
    """{answer, trace[], tool_results[], call_ids[]} — LlmError 는 호출자에게 전달."""
    tools = _tools_for(cfg, use_tools, extra)
    msgs = list(messages)
    trace: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    calls: list[str] = []
    for _ in range(max_rounds):
        res = chat(session, cfg, msgs, tools=tools, purpose=purpose, workflow_run_id=workflow_run_id)
        calls.append(res.call_id)
        trace.append({"llm_call_id": res.call_id, "tool_calls": res.tool_calls})
        if not res.tool_calls:
            return {"answer": res.text, "trace": trace, "tool_results": results, "call_ids": calls, "tools_used": bool(tools)}
        msgs.append({"role": "assistant", "content": res.message.get("content"), "tool_calls": res.tool_calls})
        for tc in res.tool_calls:
            fn = tc.get("function", {})
            out = run_tool(fn.get("name", ""), fn.get("arguments"), extra)
            results.append({"tool": fn.get("name"), "args": fn.get("arguments"), "result": out})
            trace.append({"tool": fn.get("name"), "result": out})
            msgs.append({"role": "tool", "tool_call_id": tc.get("id"), "content": json.dumps(out, ensure_ascii=False, default=str)})
    return {"answer": None, "trace": trace, "tool_results": results, "call_ids": calls, "tools_used": bool(tools), "error": "도구 호출 반복 한도 초과"}


def chat_with_tools_stream(
    session: Session,
    cfg: ResolvedLlm,
    messages: list[dict[str, Any]],
    *,
    use_tools: bool = True,
    max_rounds: int = 5,
    purpose: str = "chat",
    workflow_run_id: str | None = None,
    extra: ExtraTools | None = None,
) -> Iterator[tuple[str, Any]]:
    """`chat_with_tools` 의 스트리밍판 — ('delta', 글자 조각) · ('tool', 도구 이름) · ('reset', None)을 내고 마지막에 ('result', 결과 사전 — chat_with_tools 와 같은 모양).

    도구를 부르는 턴에 먼저 나온 글이 있으면 ('reset', None)으로 화면의 글을 비우게 한다(도구 결과를 받은 뒤 답이 처음부터 다시 나오므로).
    LlmError 는 호출자에게 전달한다 — 이미 내보낸 글이 있는지는 호출자가 안다."""
    tools = _tools_for(cfg, use_tools, extra)
    msgs = list(messages)
    trace: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    calls: list[str] = []
    for _ in range(max_rounds):
        res: ChatResult | None = None
        streamed = False
        for kind, val in chat_stream(session, cfg, msgs, tools=tools, purpose=purpose, workflow_run_id=workflow_run_id):
            if kind == "delta":
                streamed = True
                yield "delta", val
            else:
                res = val
        assert res is not None  # chat_stream 은 결과 없이 끝나지 않는다(오류는 LlmError)
        calls.append(res.call_id)
        trace.append({"llm_call_id": res.call_id, "tool_calls": res.tool_calls})
        if not res.tool_calls:
            yield "result", {"answer": res.text, "trace": trace, "tool_results": results, "call_ids": calls, "tools_used": bool(tools)}
            return
        if streamed:
            yield "reset", None
        msgs.append({"role": "assistant", "content": res.message.get("content"), "tool_calls": res.tool_calls})
        for tc in res.tool_calls:
            fn = tc.get("function", {})
            yield "tool", fn.get("name", "")
            out = run_tool(fn.get("name", ""), fn.get("arguments"), extra)
            results.append({"tool": fn.get("name"), "args": fn.get("arguments"), "result": out})
            trace.append({"tool": fn.get("name"), "result": out})
            msgs.append({"role": "tool", "tool_call_id": tc.get("id"), "content": json.dumps(out, ensure_ascii=False, default=str)})
    yield "result", {"answer": None, "trace": trace, "tool_results": results, "call_ids": calls, "tools_used": bool(tools), "error": "도구 호출 반복 한도 초과"}
