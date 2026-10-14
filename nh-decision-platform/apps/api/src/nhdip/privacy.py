"""개인정보 보호 (B.32) — 적재 전 개인정보 검사 · 화면 표시 가림 · LLM 호출 기록 가림.

기준은 설정 `privacy.policy` (관리자 편집):
  pii_scan            적재할 데이터에 주민등록번호 · 휴대전화 · 이메일 · 카드번호 형식 값이 있으면 품질 검증 실패(적재 거부)
  pii_allow_columns   검사에서 뺄 열(예: 공개 대표번호 열)
  display_mask_columns 화면 · 내보내기에서 가릴 열(예: 차주명 brwr_nm → 김*수)
  mask_llm_log        ops.llm_call 에 남기는 메시지의 개인정보 형식 값을 가림(전송 내용은 그대로)
  mask_assist_audit   질문하기 감사 기록(질문 · 피드백 · 진단 검색)에 남기는 질문의 개인정보 형식 값을 가림 — 사용자가 질문에 주민번호 등을 붙여 넣어도 감사 로그에 원문이 남지 않는다
  mask_llm_input      게이트웨이로 **보내는** 메시지의 개인정보 형식 값을 가림(Phase M · LLM-P04 · Q186) — 외부 모델에 원문이 나가지 않게. 끄면 원문 그대로 보낸다
패턴은 형식 기반이라 실제 개인정보 여부를 보증하지 않는다(오탐 시 pii_allow_columns 로 제외).
"""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

DEFAULTS: dict[str, Any] = {"pii_scan": True, "pii_allow_columns": [], "display_mask_columns": ["brwr_nm"], "mask_llm_log": True, "mask_assist_audit": True, "mask_llm_input": True}

PATTERNS: dict[str, re.Pattern[str]] = {
    "rrn": re.compile(r"(?<!\d)\d{6}\s?-\s?[1-8]\d{6}(?!\d)"),
    "phone": re.compile(r"(?<!\d)01[016789][-\s.]?\d{3,4}[-\s.]?\d{4}(?!\d)"),
    "email": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "card": re.compile(r"(?<!\d)\d{4}[-\s]\d{4}[-\s]\d{4}[-\s]\d{4}(?!\d)"),
}
LABELS = {"rrn": "주민등록번호", "phone": "휴대전화", "email": "이메일", "card": "카드번호"}


def policy(session: Session | None) -> dict[str, Any]:
    if session is None:
        return dict(DEFAULTS)
    from nhdip.models import Setting

    s = session.get(Setting, "privacy.policy")
    return {**DEFAULTS, **(s.value if s and isinstance(s.value, dict) else {})}


def scan_rows(rows: list[dict[str, Any]], allow: set[str] | None = None, limit: int = 20) -> dict[str, Any]:
    """{found: {종류: 건수}, samples: [{row, column, kind}]} — 값 자체는 돌려주지 않는다."""
    allow = allow or set()
    found: dict[str, int] = {}
    samples: list[dict[str, Any]] = []
    for i, r in enumerate(rows, start=1):
        for col, v in r.items():
            if col in allow or not isinstance(v, str) or len(v) < 6:
                continue
            for kind, pat in PATTERNS.items():
                if pat.search(v):
                    found[kind] = found.get(kind, 0) + 1
                    if len(samples) < limit:
                        samples.append({"row": i, "column": col, "kind": LABELS[kind]})
    return {"found": found, "samples": samples}


def mask_text(s: str) -> str:
    for kind, pat in PATTERNS.items():
        s = pat.sub(f"[{LABELS[kind]} 가림]", s)
    return s


def mask_obj(obj: Any) -> Any:
    if isinstance(obj, str):
        return mask_text(obj)
    if isinstance(obj, list):
        return [mask_obj(x) for x in obj]
    if isinstance(obj, dict):
        return {k: mask_obj(v) for k, v in obj.items()}
    return obj


def audit_text(session: Session | None, s: str, limit: int = 200) -> str:
    """감사 기록에 남길 질문 글 — 설정 mask_assist_audit 이면 개인정보 형식 값을 가린 뒤 자른다(자르기 전에 가려야 경계에 걸친 값이 남지 않는다)."""
    try:
        on = bool(policy(session).get("mask_assist_audit", True))
    except Exception:  # noqa: BLE001 — 설정을 못 읽어도 가리는 쪽으로
        on = True
    return (mask_text(s) if on else s)[:limit]


def mask_name(v: Any) -> Any:
    """이름 가림 — 김철수 → 김*수, 홍길 → 홍*, 법인명 등 긴 값은 앞 2글자 + * ."""
    if not isinstance(v, str) or not v.strip():
        return v
    s = v.strip()
    if len(s) <= 2:
        return s[0] + "*"
    if len(s) <= 4:
        return s[0] + "*" * (len(s) - 2) + s[-1]
    return s[:2] + "*" * (len(s) - 2)
