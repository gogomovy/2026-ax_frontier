"""커널 도구 호출 루프 (CALC-10) — LLM 이 calc_* 도구를 부르면 서버가 커널로 계산해 돌려준다. LLM 은 직접 계산하지 않는다."""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from nhdip.calc import REGISTRY, execute, tool_schemas

from .client import ResolvedLlm, chat


def run_tool(name: str, arguments: str | None) -> dict[str, Any]:
    fid = (name or "").removeprefix("calc_").upper()
    if fid not in REGISTRY:
        return {"error": f"unknown tool {name}"}
    try:
        args = json.loads(arguments or "{}")
        r = execute(fid, args)
        return {"formula": fid, "value": None if r.value is None else str(r.value), **{k: v for k, v in r.extra.items()}}
    except Exception as exc:  # noqa: BLE001 — 도구 오류는 LLM 에 그대로 돌려준다
        return {"formula": fid, "error": str(exc)}


def chat_with_tools(
    session: Session,
    cfg: ResolvedLlm,
    messages: list[dict[str, Any]],
    *,
    use_tools: bool = True,
    max_rounds: int = 5,
    purpose: str = "chat",
    workflow_run_id: str | None = None,
) -> dict[str, Any]:
    """{answer, trace[], tool_results[], call_ids[]} — LlmError 는 호출자에게 전달."""
    tools = tool_schemas() if use_tools and cfg.tools_enabled else None
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
            out = run_tool(fn.get("name", ""), fn.get("arguments"))
            results.append({"tool": fn.get("name"), "args": fn.get("arguments"), "result": out})
            trace.append({"tool": fn.get("name"), "result": out})
            msgs.append({"role": "tool", "tool_call_id": tc.get("id"), "content": json.dumps(out, ensure_ascii=False, default=str)})
    return {"answer": None, "trace": trace, "tool_results": results, "call_ids": calls, "tools_used": bool(tools), "error": "도구 호출 반복 한도 초과"}
