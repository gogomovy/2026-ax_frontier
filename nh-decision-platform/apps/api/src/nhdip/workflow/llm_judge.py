"""LLM 판단 공통 (B.31) — 판단 에이전트(변화 감지 · 플래너 · 오케스트레이터)가 LLM 에 구조화된 결정을 요청한다.

원칙
- LLM 은 '무엇을 · 왜' 를 판단하고, 수치는 커널 결과만 입력으로 받는다(새 숫자를 만들지 않는다).
- 입력은 JSON 자료로 구분자 안에 넣고(프롬프트 인젝션 방어), 출력은 JSON 하나 — 호출자가 허용 목록 · 스키마로 검증한다.
- LLM 미연결 · 오류 · 형식 오류면 None 을 돌려주고 호출자는 규칙 판단으로 대체한다(실행은 멈추지 않음).
- 같은 에이전트가 연속 실패하면 설정 `agents.llm_judge.cooldown_sec` 동안 호출을 쉬어 대기 시간 · 비용을 막는다.
- 프롬프트(system · user_template)는 관리자 [에이전트]에서 버전 관리한다. user_template 의 {task} · {context} 자리에 값이 들어간다.
"""
from __future__ import annotations

import json
import re
import time
from typing import Any

from sqlalchemy.orm import Session

from nhdip.llm import LlmError, LlmUnavailable, chat, parse_json, resolve
from nhdip.llm.guard import GUARD, fence
from nhdip.models import Setting

_COOL: dict[str, float] = {}
_RESET: dict[str, Any] = {"at": None}  # reset_cooldown 시각 — 이전 DB 오류 기록은 쉬는 시간 판단에서 뺀다
DEFAULT_POLICY = {"enabled": True, "cooldown_sec": 300, "max_context_chars": 14000, "timeout_sec": 30, "retries": 1, "format_retries": 1}
DEFAULT_USER = "과제:\n{task}\n\n입력 자료(JSON):\n{context}\n\n출력은 JSON 객체 하나만."
LITERAL_NUM = re.compile(r"\d+(?:[.,]\d+)+|\d+\s*(?:%p?|bp|억|조|만|천|원|건|배|점)")


def policy(session: Session) -> dict[str, Any]:
    s = session.get(Setting, "agents.llm_judge")
    return {**DEFAULT_POLICY, **(s.value if s and isinstance(s.value, dict) else {})}


def clean_reason(text: Any, limit: int = 200) -> tuple[str, bool]:
    """판단 사유 문장 — 숫자를 직접 쓰면(LLM 이 만든 수치일 수 있음) 버린다. (문장, 버렸는지)"""
    s = str(text or "").strip()[:limit]
    if LITERAL_NUM.search(s):
        return "", True
    return s, False


def _dump(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, default=str)


def fit_context(context: dict[str, Any], max_chars: int, shrink: tuple[str, ...] = ()) -> tuple[str | None, dict[str, int]]:
    """입력 자료를 글자 상한 안으로 — JSON 을 중간에서 자르지 않고 목록 뒤쪽 항목을 덜어 낸다(B.43).

    목록은 호출자가 중요한 순서로 넣는다고 본다(예: 변화 후보는 주요 · 변화율 큰 순). `shrink` 에 적은 키를 먼저,
    그다음 다른 최상위 목록을 큰 것부터 줄인다. 덜어 낸 수는 자료의 `_omitted` 에 적어 LLM 이 알게 한다.
    모든 목록을 1개까지 줄여도 넘으면 (None, 덜어 낸 수) — 호출자는 규칙 판단으로 대체한다(잘린 JSON 을 보내지 않음).
    """
    text = _dump(context)
    if max_chars <= 0 or len(text) <= max_chars:
        return text, {}
    ctx = {k: (list(v) if isinstance(v, list) else v) for k, v in context.items()}
    omitted: dict[str, int] = {}

    def size() -> int:
        return len(_dump({**ctx, "_omitted": omitted})) if omitted else len(_dump(ctx))

    while size() > max_chars:
        lists = [k for k, v in ctx.items() if isinstance(v, list) and len(v) > 1]
        if not lists:
            return None, omitted
        first = [k for k in shrink if k in lists]
        key = first[0] if first else max(lists, key=lambda k: len(_dump(ctx[k])))
        items = ctx[key]
        # 넘친 비율만큼 한 번에 덜어 낸다(최소 1개) — 항목 수가 많아도 반복이 짧다
        over = size() - max_chars
        per = max(1, len(_dump(items)) // max(1, len(items)))
        n = min(len(items) - 1, max(1, -(-over // per)))
        ctx[key] = items[: len(items) - n]
        omitted[key] = omitted.get(key, 0) + n
    return _dump({**ctx, "_omitted": omitted}), omitted


def _cooling(session: Session, agent_code: str, sec: float) -> bool:
    """연속 실패 쉬는 시간 — 프로세스 메모리 + DB(최근 판단 호출이 오류였는지) 둘 다 본다.
    DB 기준이라 워커가 여러 개이거나 재시작해도 같은 판단을 한다 (B.32)."""
    if _COOL.get(agent_code, 0.0) > time.monotonic():
        return True
    if sec <= 0:
        return False
    from datetime import timedelta

    from sqlalchemy import select

    from nhdip.models import LlmCall, utcnow

    cut = utcnow() - timedelta(seconds=sec)
    if _RESET["at"] is not None and _RESET["at"] > cut:
        cut = _RESET["at"]
    last = session.execute(
        select(LlmCall.status).where(LlmCall.purpose == f"judge:{agent_code}", LlmCall.created_at > cut).order_by(LlmCall.created_at.desc()).limit(1)
    ).scalar()
    return last == "error"


def ask_json(session: Session, agent_code: str, task: str, context: dict[str, Any], *, workflow_run_id: str | None = None, node_run_id: str | None = None, required: tuple[str, ...] = (), shrink: tuple[str, ...] = ()) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """(결정 JSON 또는 None, 메타{by, reason, llm_call_id, model, contextTrimmed?})

    입력 자료가 `max_context_chars` 를 넘으면 목록 뒤쪽을 덜어 낸다(`fit_context`, 우선 줄일 키 = `shrink`).
    덜어 낸 항목 수는 메타 `contextTrimmed` — 호출자는 그 항목을 규칙으로 판단한다."""
    pol = policy(session)
    if not pol.get("enabled", True):
        return None, {"by": "rule", "reason": "LLM 판단 꺼짐(설정 agents.llm_judge)"}
    if _cooling(session, agent_code, float(pol.get("cooldown_sec", 300))):
        return None, {"by": "rule", "reason": "최근 LLM 오류 — 대기 시간 동안 규칙으로 판단"}
    try:
        llm = resolve(session, agent_code)
    except LlmUnavailable as exc:
        return None, {"by": "rule", "reason": f"LLM 미연결 — {exc}"}
    # 판단 호출은 실행 경로 위에 있으므로 대기 · 재시도 상한을 둔다 (설정 agents.llm_judge.timeout_sec · retries) — B.32
    import dataclasses

    llm = dataclasses.replace(llm, timeout=min(llm.timeout, float(pol.get("timeout_sec", 30))), retries=min(llm.retries, int(pol.get("retries", 1))))
    # 상한을 넘으면 JSON 을 중간에서 자르지 않고(이전 동작: 잘린 JSON 이 들어가 판단이 흔들림) 목록 항목을 덜어 낸다 — B.43
    ctx_text, trimmed = fit_context(context, int(pol.get("max_context_chars", 14000)), shrink)
    trim_meta = {"contextTrimmed": trimmed} if trimmed else {}
    if ctx_text is None:
        return None, {"by": "rule", "reason": "입력 자료가 글자 상한(agents.llm_judge.max_context_chars)을 넘음 — 규칙으로 판단", **trim_meta}
    if trimmed:
        task = task + "\n(입력 자료의 _omitted 는 글자 상한 때문에 뺀 목록 항목 수다. 뺀 항목은 판단하지 않는다 — 규칙으로 판단된다.)"
    user = (llm.user_template or DEFAULT_USER).replace("{task}", task).replace("{context}", fence(ctx_text))
    messages = [{"role": "system", "content": (llm.system_prompt or "너는 은행 업무 판단 에이전트다. JSON 으로만 답한다.") + "\n\n" + GUARD}, {"role": "user", "content": user}]
    try:
        res = chat(session, llm, messages, json_mode=True, workflow_run_id=workflow_run_id, node_run_id=node_run_id, purpose=f"judge:{agent_code}")
        try:
            data = parse_json(res.text)
        except ValueError as exc:
            # 출력 형식 오류(쉼표 누락 · 잘림 등)는 모델 장애가 아니다 — 오류를 알려 주고 같은 내용을 JSON 으로 다시 받는다(B.40, 설정 format_retries)
            data = None
            for _ in range(int(pol.get("format_retries", 1))):
                fix = messages + [{"role": "assistant", "content": res.text[:6000]},
                                  {"role": "user", "content": f"앞 응답은 JSON 형식 오류({str(exc)[:120]})로 읽을 수 없다. 같은 판단을 올바른 JSON 객체 하나로만 다시 출력하라. 설명 · 코드펜스 금지."}]
                res = chat(session, llm, fix, json_mode=True, workflow_run_id=workflow_run_id, node_run_id=node_run_id, purpose=f"judge:{agent_code}")
                try:
                    data = parse_json(res.text)
                    break
                except ValueError as again:
                    exc = again
            if data is None:
                return None, {"by": "rule", "reason": f"LLM 출력 형식 오류(재요청 후에도 JSON 아님: {str(exc)[:120]}) — 규칙으로 대체", "llm_call_id": res.call_id, "model": llm.model, **trim_meta}
        if not isinstance(data, dict):
            return None, {"by": "rule", "reason": "LLM 출력 형식 오류(JSON 객체가 아님) — 규칙으로 대체", "llm_call_id": res.call_id, "model": llm.model, **trim_meta}
        missing = [k for k in required if not isinstance(data.get(k), list)]
        if missing:
            # 형식이 맞지 않으면 판단으로 쓰지 않는다(쉬지는 않음 — 모델 오류가 아닌 출력 형식 문제)
            return None, {"by": "rule", "reason": f"LLM 출력 형식 오류(필수 목록 {', '.join(missing)} 없음) — 규칙으로 대체", "llm_call_id": res.call_id, "model": llm.model, **trim_meta}
    except (LlmError, ValueError, AttributeError) as exc:
        _COOL[agent_code] = time.monotonic() + float(pol.get("cooldown_sec", 300))
        return None, {"by": "rule", "reason": f"LLM 판단 실패 — 규칙으로 대체: {str(exc)[:200]}", **trim_meta}
    _COOL.pop(agent_code, None)
    return data, {"by": "llm", "llm_call_id": res.call_id, "model": llm.model, "prompt_version": llm.prompt_version, **trim_meta}


def reset_cooldown() -> None:
    """테스트 · 연결 변경 직후 — 대기 상태를 비운다."""
    from nhdip.models import utcnow

    _COOL.clear()
    _RESET["at"] = utcnow()
