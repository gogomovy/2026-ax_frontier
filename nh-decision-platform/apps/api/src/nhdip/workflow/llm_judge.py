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
DEFAULT_POLICY = {"enabled": True, "cooldown_sec": 300, "max_context_chars": 14000}
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


def ask_json(session: Session, agent_code: str, task: str, context: dict[str, Any], *, workflow_run_id: str | None = None, node_run_id: str | None = None, required: tuple[str, ...] = ()) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """(결정 JSON 또는 None, 메타{by, reason, llm_call_id, model})"""
    pol = policy(session)
    if not pol.get("enabled", True):
        return None, {"by": "rule", "reason": "LLM 판단 꺼짐(설정 agents.llm_judge)"}
    until = _COOL.get(agent_code, 0.0)
    if until > time.monotonic():
        return None, {"by": "rule", "reason": "최근 LLM 오류 — 대기 시간 동안 규칙으로 판단"}
    try:
        llm = resolve(session, agent_code)
    except LlmUnavailable as exc:
        return None, {"by": "rule", "reason": f"LLM 미연결 — {exc}"}
    ctx_text = json.dumps(context, ensure_ascii=False, default=str)[: int(pol.get("max_context_chars", 14000))]
    user = (llm.user_template or DEFAULT_USER).replace("{task}", task).replace("{context}", fence(ctx_text))
    messages = [{"role": "system", "content": (llm.system_prompt or "너는 은행 업무 판단 에이전트다. JSON 으로만 답한다.") + "\n\n" + GUARD}, {"role": "user", "content": user}]
    try:
        res = chat(session, llm, messages, json_mode=True, workflow_run_id=workflow_run_id, node_run_id=node_run_id, purpose=f"judge:{agent_code}")
        data = parse_json(res.text)
        if not isinstance(data, dict):
            raise ValueError("JSON 객체가 아님")
        missing = [k for k in required if not isinstance(data.get(k), list)]
        if missing:
            # 형식이 맞지 않으면 판단으로 쓰지 않는다(쉬지는 않음 — 모델 오류가 아닌 출력 형식 문제)
            return None, {"by": "rule", "reason": f"LLM 출력 형식 오류(필수 목록 {', '.join(missing)} 없음) — 규칙으로 대체", "llm_call_id": res.call_id, "model": llm.model}
    except (LlmError, ValueError, AttributeError) as exc:
        _COOL[agent_code] = time.monotonic() + float(pol.get("cooldown_sec", 300))
        return None, {"by": "rule", "reason": f"LLM 판단 실패 — 규칙으로 대체: {str(exc)[:200]}"}
    _COOL.pop(agent_code, None)
    return data, {"by": "llm", "llm_call_id": res.call_id, "model": llm.model, "prompt_version": llm.prompt_version}


def reset_cooldown() -> None:
    """테스트 · 연결 변경 직후 — 대기 상태를 비운다."""
    _COOL.clear()
