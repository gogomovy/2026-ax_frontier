"""LLM 문장의 '리터럴 숫자' 점검 — 수치는 계산 커널이 확정한 [[fig:ID]] 마커로만 쓴다 (서술 검증 · 판단 사유 · 묶음 이름 공용).

예전에는 검증 규칙(CRITIC_RULES)과 판단 사유 점검(LITERAL_NUM)이 서로 다른 정규식을 써서 '3개' '2위' '12％' 같은 표현이 통과했다.
여기서는 ① 전각 문자를 NFKC 로 정규화하고 ② 내장 패턴 + 규칙(DB)의 패턴을 함께 적용한다.
연도 · 월 · 분기 같은 기간 표현('2026년 3분기')은 데이터에서 온 라벨이라 막지 않는다.
"""
from __future__ import annotations

import re
import unicodedata

BUILTIN = re.compile(
    r"\d+(?:[.,]\d+)+\s*(?:%p?|bp|배)?"  # 소수 · 천단위
    r"|\d+\s*(?:%p?|bp|억|조|만|천|원|건|배|개|곳|명|위|점|퍼센트|포인트)"  # 단위가 붙은 정수
)
_FIG = re.compile(r"\[\[fig:[^\]]+\]\]")
_TERM_LABEL = re.compile(r"\{\{term:[^|}]*\|([^}]*)\}\}")
_TERM_BARE = re.compile(r"\{\{term:[^}]*\}\}")


def normalize(text: str | None) -> str:
    return unicodedata.normalize("NFKC", text or "")


def strip_markers(text: str | None) -> str:
    """수치 마커는 뺀다. 용어 마커 `{{term:CODE|라벨}}` 는 라벨이 화면에 그대로 보이므로 라벨 글자는 남겨 점검한다
    (예전에는 마커 전체를 지워 `{{term:PSI|연체율 12.5%}}` 로 숫자를 숨길 수 있었다)."""
    s = _FIG.sub(" ", text or "")
    s = _TERM_LABEL.sub(r" \1 ", s)
    return _TERM_BARE.sub(" ", s)


def literal_numbers(text: str | None, extra_pattern: str | None = None) -> list[str]:
    """마커를 뺀 문장에서 리터럴 숫자 표현을 찾는다. extra_pattern 은 규칙(CRITIC_RULES.literal_number_regex)의 패턴 — 내장 패턴과 합친다."""
    s = normalize(strip_markers(text))
    found = [m.group(0) for m in BUILTIN.finditer(s)]
    if extra_pattern:
        try:
            found += [m.group(0) for m in re.compile(extra_pattern).finditer(s)]
        except re.error:
            pass  # 잘못된 규칙 패턴이 검증을 끄지 않도록 내장 패턴만
    seen: list[str] = []
    for f in found:
        if f not in seen:
            seen.append(f)
    return seen


def has_literal_number(text: str | None, extra_pattern: str | None = None) -> bool:
    return bool(literal_numbers(text, extra_pattern))
