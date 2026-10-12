"""보고서(ReportDoc) → 형식 중립 요소 목록 (F.17 · MDL-14).

HTML · PDF · HWPX · HWP 변환기는 모두 이 요소 목록만 읽는다 → 같은 보고서는 형식이 달라도 같은 내용.
수치는 계산 결과(Figure)를 포맷해 넣고, 마커가 해결되지 않으면 그 사실을 본문에 남긴다(PRIN-05).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

FIG_TOKEN = re.compile(r"\[\[fig:([a-zA-Z0-9_\-]+)\]\]")
TERM_TOKEN = re.compile(r"\{\{term:([A-Z_0-9]+)(?:\|([^}]+))?\}\}")

#: 프론트 `defaultDecimals` 와 같음
DEFAULT_DECIMALS = {"PCT": 1, "PP": 1, "KRW_TN": 1, "KRW_BN": 0, "RATIO": 3}
EVIDENCE_CATEGORY = {"bank_data": "당행 Data", "internal_direction": "내부 경영방향", "external_policy": "외부 정책·환경"}
ORIGIN_LABEL = {"simulated": "시뮬레이션", "mixed": "혼합"}


def number(value: float, decimals: int) -> str:
    """Intl.NumberFormat('ko-KR', 고정 소수) 와 같은 결과 — 이진값 기준 사사오입 + 천 단위 구분."""
    q = Decimal(1).scaleb(-decimals) if decimals > 0 else Decimal(1)
    return f"{Decimal(value).quantize(q, rounding=ROUND_HALF_UP):,}"


def format_figure(fig: dict[str, Any], units: dict[str, str]) -> str:
    if fig.get("value") is None:
        return fig.get("undefinedLabel") or "미제공"
    unit = fig.get("unit", "NONE")
    d = fig.get("decimals")
    d = DEFAULT_DECIMALS.get(unit, 0) if d is None else int(d)
    return f"{number(fig['value'], d)}{units.get(unit, '')}"


def resolve(text: str | None, figures: dict[str, Any] | None, units: dict[str, str]) -> str:
    """[[fig:ID]] → 계산 수치 표시, {{term:CODE|라벨}} → 라벨 (평문)."""
    figs = figures or {}

    def fig(m: re.Match) -> str:
        f = figs.get(m.group(1))
        return format_figure(f, units) if isinstance(f, dict) else f"[수치 참조 누락: {m.group(1)}]"

    return TERM_TOKEN.sub(lambda m: m.group(2) or m.group(1), FIG_TOKEN.sub(fig, text or ""))


def js_number(v: Any) -> str:
    """차트 포인트 원값 표시 — JS 문자열 변환과 같게(정수형 실수는 소수점 없이)."""
    if v is None:
        return "-"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def date_dot(iso: str | None) -> str:
    if not iso:
        return ""
    parts = iso[:10].split("-")
    return ".".join(parts) if len(parts) == 3 else iso


def date_time(iso: str | None) -> str:
    if not iso:
        return ""
    m = re.search(r"T(\d{2}):(\d{2})", iso)
    return f"{date_dot(iso)} {m.group(1)}:{m.group(2)}" if m else date_dot(iso)


# ── 요소 ─────────────────────────────────────────────────────
@dataclass
class Heading:
    level: int
    text: str


@dataclass
class Para:
    text: str
    style: str = "body"  # body · meta · muted · op_title


@dataclass
class Bullets:
    items: list[str]
    ordered: bool = False


@dataclass
class Callout:
    text: str
    tone: str = "info"


@dataclass
class Table:
    columns: list[str]
    rows: list[list[str]]
    aligns: list[str] = field(default_factory=list)
    caption: str | None = None
    note: str | None = None
    highlight: set[int] = field(default_factory=set)


@dataclass
class KeyValues:
    items: list[tuple[str, str]]


@dataclass
class EvidenceList:
    items: list[tuple[str, str, str, str]]  # (분류, 제목, 출처, 발췌)


Element = Heading | Para | Bullets | Callout | Table | KeyValues | EvidenceList


def _evidence(items: list[dict[str, Any]]) -> EvidenceList:
    out = []
    for e in items or []:
        doc = e.get("doc")
        if doc:
            src = doc.get("title", "") + (f" p.{doc['page']}" if doc.get("page") else "") + (f" · {doc['issuer']}" if doc.get("issuer") else "")
        else:
            src = e.get("tableRef") or "내부 집계"
        out.append((EVIDENCE_CATEGORY.get(e.get("category", ""), e.get("category", "")), e.get("label", ""), src, e.get("snippet") or ""))
    return EvidenceList(out)


def _block(b: dict[str, Any], figures: dict[str, Any], units: dict[str, str]) -> list[Element]:
    t = b.get("type")
    if t == "p":
        return [Para(resolve(b.get("text"), figures, units))]
    if t == "ul":
        return [Bullets([resolve(i, figures, units) for i in b.get("items") or []])]
    if t == "callout":
        return [Callout(resolve(b.get("text"), figures, units), b.get("tone") or "info")]
    if t == "kv":
        return [KeyValues([(i.get("label", ""), str(i.get("value", ""))) for i in b.get("kv") or []])]
    if t == "metrics":
        # 지표 묶음 (Phase C · 분석 에이전트 보고서) — 그림 ID 목록 → 이름 : 확정 수치
        return [KeyValues([((figures.get(f) or {}).get("label", f), resolve(f"[[fig:{f}]]", figures, units)) for f in b.get("figures") or []])]
    if t == "table" and b.get("table"):
        tb = b["table"]
        cols = tb.get("columns") or []
        hl_key, hl_val = tb.get("highlightRowKey"), tb.get("highlightRowValue")
        rows, hl = [], set()
        for i, r in enumerate(tb.get("rows") or []):
            if hl_key and str(r.get(hl_key)) == str(hl_val):
                hl.add(i)
            rows.append([str(r.get(c["key"])) if r.get(c["key"]) is not None else "-" for c in cols])
        return [Table([c.get("label", "") for c in cols], rows, [c.get("align") or "left" for c in cols], tb.get("caption"), tb.get("note"), hl)]
    if t == "chart" and b.get("chart"):
        # 차트는 같은 데이터를 표로 제공한다(그래픽 재현 의존 제거)
        c = b["chart"]
        series = c.get("series") or []
        cats = [p.get("label", "") for p in (series[0].get("points") if series else [])]
        rows = [[lab, *[js_number((s.get("points") or [])[i].get("value")) if i < len(s.get("points") or []) else "-" for s in series]] for i, lab in enumerate(cats)]
        return [Table(["구분", *[s.get("name", "") for s in series]], rows, ["left", *["right"] * len(series)], f"{c.get('title', '')} (데이터 표)")]
    return []


def build(report: dict[str, Any], units: dict[str, str]) -> list[Element]:
    origin = ORIGIN_LABEL.get(report.get("dataOrigin", ""), "실데이터")
    els: list[Element] = [
        Heading(1, report.get("title", "")),
        Para(f"{report.get('subtitle', '')}\n기준일 {report.get('asOf', '')} · 생성 {date_time(report.get('generatedAt'))} · 데이터 성격 {origin}", "meta"),
        Heading(2, "AGENT 의견"),
    ]
    for i, o in enumerate(report.get("opinions") or [], start=1):
        els.append(Para(f"{i}. {o.get('title', '')}", "op_title"))
        els.append(Para(resolve(o.get("statement"), o.get("figures"), units)))
        ev = _evidence(o.get("evidence") or [])
        if ev.items:
            els.append(ev)
    figures = report.get("figures") or {}
    for s in report.get("sections") or []:
        els.append(Heading(int(s.get("level") or 2), s.get("heading", "")))
        for b in s.get("blocks") or []:
            els.extend(_block(b, figures, units))
    els.append(Heading(2, "근거"))
    ev = _evidence(report.get("evidence") or [])
    els.append(ev if ev.items else Para("연결된 근거가 없습니다.", "muted"))
    if report.get("limitations"):
        els.append(Heading(2, "한계 · 유의사항"))
        els.append(Bullets([str(x) for x in report["limitations"]]))
    els.append(Para("본 문서는 AI 분석 결과를 보조 자료로 변환한 것입니다. 최종 판단과 책임은 담당자·의사결정권자에게 있습니다.", "muted"))
    els.append(Para(f"{report.get('id', '')} · {report.get('kind', '')}", "muted"))
    return els
