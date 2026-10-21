"""기간 대체를 화면 글에 드러내기 — 계산 커널이 '전년 동기' 같은 달 수 토큰을 가장 가까운 보관 기준일로 대체했을 때
(calc.metrics.resolve_token · 설정 calc.period_fallback), 그 수치의 라벨 · 그 수치를 쓰는 서식 문구가 여전히 '전년 동기'라고 말하지 않게
실제로 견준 기간(2026.01)으로 바꾼다. 대체가 풀리면(그 달이 올라오면) 원래 라벨로 돌아간다.

토큰마다 그 기간을 가리키는 업무 낱말 — 라벨 · 문구에 그 낱말이 없으면 글은 그대로 두고, 화면은 Figure.basis 로 안내한다.
"""
from __future__ import annotations

import re
from typing import Any

from nhdip.calc.metrics import TOKEN_RE, fallback_note, period_dot, span_of


def _phrases(token: str) -> re.Pattern[str] | None:
    m = TOKEN_RE.match(token or "")
    if not m:
        return None
    kind, n = m.group(1), int(m.group(2)) if m.group(2) else 0
    if kind == "prev_year_end":
        return re.compile(r"전년\s?말")
    if kind != "latest" or not n:
        return None
    if n == 12:
        return re.compile(r"전년\s?동기|1년\s?전")
    if n == 24:
        return re.compile(r"전전년\s?동기|2년\s?전(?:\s?동기)?")
    if n == 1:
        return re.compile(r"전월")
    if n % 12 == 0:
        return re.compile(rf"{n // 12}년\s?전(?:\s?동기)?")
    return re.compile(rf"{n}\s?개월\s?전")


def basis_list(value: Any) -> list[dict[str, Any]]:
    return [b for b in value if isinstance(b, dict) and b.get("token") and b.get("used")] if isinstance(value, list) else []


def relabel(text: str, basis: list[dict[str, Any]]) -> str:
    """'전년 동기 대비 증가율' + [{token: $latest-12, used: 202601}] → '2026.01 대비 증가율'. 대체가 없거나 낱말이 없으면 그대로."""
    if not isinstance(text, str) or not text:
        return text
    out = text
    for b in basis_list(basis):
        pat = _phrases(str(b["token"]))
        if pat is not None:
            out = pat.sub(period_dot(b["used"]), out)
    return out


def figures_span(figs: Any) -> dict[str, Any] | None:
    """수치들 가운데 원래와 다른 비교 기간으로 계산된 실적의 비교 기간(이미 맞춘 값은 빼고) — 경영목표를 그 기간으로 환산할 때."""
    vals = figs.values() if isinstance(figs, dict) else figs or []
    return span_of([b for f in vals if isinstance(f, dict) for b in basis_list(f.get("basis"))])


def figure_note(f: dict[str, Any], span: dict[str, Any] | None = None) -> str:
    """에이전트 입력 · 안내용 한 줄 — 이 수치의 비교 기준(기간 대체 · 비교 기간 맞춤)과, 경영목표면 이번 비교 기간 환산 값. 없으면 빈 글자."""
    parts: list[str] = []
    for b in basis_list(f.get("basis")):
        months = f" · 비교 기간 {b['months']}개월" if isinstance(b.get("months"), int) and b.get("months") != b.get("wantedMonths") else ""
        parts.append(fallback_note(b) + months)
    al = f.get("align") if isinstance(f.get("align"), dict) else None
    if al and al.get("goal"):
        parts.append(f"경영목표를 비교 기간 {al['months']}개월로 환산(× {al['months']}/{al['wantedMonths']})해 견준 값")
    if al and al.get("params"):
        parts.append(f"기간을 실제 비교 기간 {al['months']}개월로 맞춰 계산한 값")
    v = f.get("value")
    if f.get("goal") and span and isinstance(v, (int, float)) and not isinstance(v, bool):
        parts.append(f"연 목표 — 이번 비교 기간 {span['months']}개월로 환산하면 {round(v * span['months'] / span['wantedMonths'], 2)}")
    return "; ".join(dict.fromkeys(parts))


PERIOD_GUIDE = ("비교 기준이 적힌 수치는 그 기간 기준으로 서술한다 — '전년 동기' · '전년 말'이라고 쓰지 않고 적힌 기간(예: 2026.01 대비)을 쓴다. "
                "경영목표와 견줄 때는 비교 기간으로 환산한 목표 기준임을 밝힌다.")


def basis_short(basis: Any, align: dict[str, Any] | None = None) -> str:
    """짧은 비교 기준 — '2026.01 대비 · 목표 7개월 환산'. 대체가 없으면 빈 글자."""
    used = list(dict.fromkeys(period_dot(b["used"]) for b in basis_list(basis)))
    parts = [f"{' · '.join(used)} 대비"] if used else []
    if isinstance(align, dict) and align.get("goal"):
        parts.append(f"목표 {align['months']}개월 환산")
    return " · ".join(parts)


def basis_range(basis: Any) -> str | None:
    """대체된 비교 구간 '2025.01~2026.08' — 대체가 없으면 None."""
    b = next(iter(basis_list(basis)), None)
    return f"{period_dot(b['used'])}~{period_dot(b['latest'])}" if b and b.get("latest") else None
