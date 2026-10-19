"""마크다운(.md) 표 읽기 — DRM 때문에 엑셀을 .md 로 바꿔 올리는 경우 (Phase Q · MD-01~06).

엑셀 → md 변환 도구(pandoc · markitdown · 사내 변환기 등)가 만드는 GFM 파이프 표를 정형 자료 행으로 읽는다.

    ## 시트1            ← 시트 · 표 이름(가장 가까운 앞 제목)
    | 상품명 | 잔액 |    ← 머리글
    |---|---:|          ← 구분 줄(이 줄이 있어야 표로 본다)
    | A | 1,234 |

- 한 파일에 표가 여럿(시트 여러 개)이면 정의의 parser.sheet(표 제목)와 맞는 표 → 정의 열과 머리글이 가장 많이 맞는 표 → 가장 큰 표
- 셀 정리: 굵게 · 기울임 · 코드 표시, <br> · &nbsp; 같은 HTML, 이스케이프된 \\|, 변환기가 빈 셀에 넣는 NaN · None · nan
- 변환기가 빈 머리글에 넣는 'Unnamed: 3' 은 빈 머리글로 — 제목 줄이 머리글로 잡힌 표는 기존 머리글 찾기(_header_index · _header_row)가 실제 머리글 줄을 찾는다
- 인코딩: UTF-8(BOM 포함) → CP949(내부망 변환기 기본값) 순으로 읽는다
표가 없는 .md 는 문서(비정형)로 처리한다(is_md_table).
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from typing import Any

_SEP = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$")
_BR = re.compile(r"<br\s*/?>", re.I)
_TAG = re.compile(r"</?[a-zA-Z][^>]*>")
_EMPH = re.compile(r"(\*\*|__)(.+?)\1|(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])|`([^`]*)`")
_UNNAMED = re.compile(r"^Unnamed:\s*\d+(_level_\d+)?$", re.I)
_NULLS = {"nan", "none", "null", "nat", "<na>"}


@dataclass
class MdTable:
    title: str | None
    rows: list[list[str]] = field(default_factory=list)  # 첫 줄 = 머리글

    @property
    def size(self) -> int:
        return max(0, len(self.rows) - 1) * max((len(r) for r in self.rows), default=0)


def decode(content: bytes) -> str:
    """UTF-8(BOM) → CP949 → UTF-8(대체 문자) 순."""
    for enc in ("utf-8-sig", "cp949"):
        try:
            return content.decode(enc)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def _split(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|") and not s.endswith("\\|"):
        s = s[:-1]
    cells, cur, i = [], [], 0
    while i < len(s):
        ch = s[i]
        if ch == "\\" and i + 1 < len(s) and s[i + 1] == "|":
            cur.append("|")
            i += 2
            continue
        if ch == "|":
            cells.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
        i += 1
    cells.append("".join(cur))
    return cells


def clean_cell(v: str, header: bool = False) -> str:
    t = _BR.sub(" ", v)
    t = _TAG.sub("", t)
    t = html.unescape(t).replace("\xa0", " ")
    t = _EMPH.sub(lambda m: m.group(2) or m.group(3) or m.group(4) or "", t)
    t = re.sub(r"\s+", " ", t).strip()
    if t.lower() in _NULLS:
        return ""
    if header and _UNNAMED.match(t):
        return ""
    return t


def tables(text: str) -> list[MdTable]:
    """파일 안의 파이프 표 — 구분 줄이 있는 것만, 나온 순서대로. 표 제목은 가장 가까운 앞 제목(#)."""
    lines = text.splitlines()
    out: list[MdTable] = []
    title: str | None = None
    i = 0
    while i < len(lines):
        ln = lines[i]
        h = _HEADING.match(ln)
        if h:
            title = clean_cell(h.group(1))
            i += 1
            continue
        if "|" in ln and i + 1 < len(lines) and _SEP.match(lines[i + 1]) and not _SEP.match(ln):
            head = [clean_cell(c, header=True) for c in _split(ln)]
            width = len(head)
            rows = [head]
            j = i + 2
            while j < len(lines) and "|" in lines[j] and lines[j].strip():
                if _SEP.match(lines[j]):  # 표 중간 구분 줄(변환기가 넣는 경우) — 건너뛴다
                    j += 1
                    continue
                cells = [clean_cell(c) for c in _split(lines[j])]
                cells = (cells + [""] * width)[:width] if len(cells) <= width else cells[:width]
                rows.append(cells)
                j += 1
            out.append(MdTable(title, rows))
            i = j
            continue
        i += 1
    return out


def is_md_table(content: bytes) -> bool:
    """정형 자료로 볼 .md 인가 — 데이터 행이 있는 파이프 표가 하나라도 있으면."""
    return any(len(t.rows) >= 2 for t in tables(decode(content)))


def _norm(s: Any) -> str:
    return re.sub(r"[\s_\-()·./]+", "", str(s or "")).lower()


def pick(ts: list[MdTable], parser: dict[str, Any] | None = None, cands: set[str] | None = None) -> MdTable:
    """읽을 표 — 정의의 표 제목(parser.sheet) → 정의 열과 맞는 머리글이 많은 표(앞 5줄 중 가장 많이 맞는 줄) → 가장 큰 표."""
    from .datasets import IngestError

    ts = [t for t in ts if len(t.rows) >= 2]
    if not ts:
        raise IngestError("마크다운 파일에서 표를 찾지 못했습니다 — '| 열1 | 열2 |' 머리글 아래 '|---|---|' 구분 줄이 있는 표여야 합니다(표가 없는 글은 문서로 올리세요)")
    sheet = (parser or {}).get("sheet")
    if sheet:
        hit = next((t for t in ts if t.title and _norm(t.title) == _norm(sheet)), None)
        if hit is not None:
            return hit
    if cands:
        def score(t: MdTable) -> int:
            return max((sum(1 for c in r if c and _norm(c) in cands) for r in t.rows[:5]), default=0)

        best = max(ts, key=score)
        if score(best) >= 2:
            return best
    return max(ts, key=lambda t: t.size)


def grid(content: bytes, parser: dict[str, Any] | None = None, cands: set[str] | None = None) -> tuple[list[list[Any]], MdTable, int]:
    """(표 칸 격자 — 빈 칸은 None, 고른 표, 표 수)."""
    ts = tables(decode(content))
    t = pick(ts, parser, cands)
    g = [[c if c != "" else None for c in r] for r in t.rows]
    return g, t, len([x for x in ts if len(x.rows) >= 2])
