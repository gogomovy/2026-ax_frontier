"""보고서 양식 표 읽기 (M.25 · DOB-19 · Q213) — 미리 정해 둔 양식 · 데이터셋 코드 · 열 이름 없이, 파일 모양에서 구조를 만든다.

일반 표(머리글 1줄 + 행)는 `datasets._read_table` 이 읽는다. 여기서는 일반 표로는 읽히지 않는 업무 보고서 엑셀을 같은 모양의 행 목록으로 바꾼다.
  머리글 찾기   제목 · '키 : 값' 안내 줄 아래, 글자 칸이 둘 이상이고 바로 아래에 숫자 행이 오는 첫 줄. 숫자 없는 줄이 이어지면 다단 머리글로 합친다
                (병합된 위 칸은 아래 칸이 있는 오른쪽 열까지 이어 붙임 — 예: '손실충당금' + '대출채권' → '손실충당금 대출채권')
  열 역할       값이 대부분 숫자면 값 열, 아니면 항목(이름 · 코드) 열
  계층          항목 열의 들여쓰기(셀 들여쓰기 · 앞 공백)가 있으면 '상위 항목' · '수준' 열을 만든다(같은 이름의 항목도 구분)
  기간 열       머리글이 '1월 · 2월 …' 처럼 기간이 둘 이상(또는 값 열이 모두 기간)이면 행으로 펼친다('기준년월' + 측정 열 하나). 측정 이름은 안내 줄의 '구분' 값, 없으면 '값'
  기준년월      파일 이름의 (YYYYMM) 또는 안내 줄의 기준일 · 기준년월 — 표에 기간 열이 없으면 '기준년월' 열로 붙인다
  합계 행       항목이 '합계 · 총계 · 소계 · Total' 이면 '합계 행' 열(참)
  머리글 이름   기준월과 같은 'N월'(예: 8월 누계)은 '기준월 누계' 로 — 달마다 열 이름이 바뀌지 않게
안내 줄의 조회자 · 담당자 같은 개인 이름은 저장하지 않는다(sheets._header_meta).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .sheets import MONTH_RE, Sheet, _header_meta, _level, _num, file_info, load_sheets

MAX_SCAN = 40  # 머리글을 찾는 앞부분 줄 수
MAX_HEADER_ROWS = 3
PERIOD_MIN = 3  # 기간 열 기준 — 둘 이상(또는 값 열이 모두 기간)이면 행으로 펼친다
TOTAL_RE = re.compile(r"^\s*(합\s*계|총\s*계|소\s*계|total|grand\s*total)\s*$", re.I)
NOTE_RE = re.compile(r"^\s*(?:※|주\s*\)|\*|출처\s*[:：]|자료\s*[:：]|비고\s*[:：])")
YM_RE = re.compile(r"((?:19|20)\d{2})\s*[.\-/년]?\s*(\d{1,2})(?!\d)")
YM_HEAD = re.compile(r"^\s*((?:19|20)\d{2})\s*[.\-/년]\s*(\d{1,2})\s*월?\s*$")
PARENT_COL, LEVEL_COL, TOTAL_COL, YM_COL = "상위 항목", "수준", "합계 행", "기준년월"


@dataclass
class Report:
    rows: list[dict[str, Any]]
    info: dict[str, Any] = field(default_factory=dict)


def _is_text(v: Any) -> bool:
    return v is not None and str(v).strip() != "" and not _is_num(v)


def _is_num(v: Any) -> bool:
    """숫자 칸 — 엑셀 숫자 셀, 또는 '1,234' · '-3.5' · '(12)' 같은 숫자 글자. 숫자만으로 된 글자 셀(상품코드 · 사무소 코드)은 코드로 본다."""
    if v is None or isinstance(v, bool):
        return False
    if isinstance(v, (int, float)):
        return True
    s = str(v).strip()
    if not s or s == "-" or re.fullmatch(r"\d+", s):
        return False
    return _num(s) is not None


def _nonempty(row: list[Any]) -> list[int]:
    return [c for c, v in enumerate(row) if v is not None and str(v).strip() != ""]


def _numeric_row(row: list[Any]) -> bool:
    return any(_is_num(v) for v in row)


def _header_start(cells: list[list[Any]]) -> int | None:
    for r in range(min(MAX_SCAN, len(cells))):
        row = cells[r]
        texts = [c for c in _nonempty(row) if _is_text(row[c])]
        if len(texts) < 2 or len(texts) < 0.6 * len(_nonempty(row)):
            continue
        for k in range(1, MAX_HEADER_ROWS + 2):
            if r + k < len(cells) and _numeric_row(cells[r + k]):
                return r
    return None


def _header_rows(cells: list[list[Any]], start: int) -> list[int]:
    rows = [start]
    r = start + 1
    while r < len(cells) and len(rows) < MAX_HEADER_ROWS and not _numeric_row(cells[r]):
        if len([c for c in _nonempty(cells[r]) if _is_text(cells[r][c])]) >= 1:
            rows.append(r)
        r += 1
    return rows


def _labels(cells: list[list[Any]], hrows: list[int], width: int) -> dict[int, str]:
    """다단 머리글 → 열 이름. 위 칸이 비었고 아래 칸이 있으면 바로 왼쪽 열의 위 칸을 이어 받는다(병합 칸)."""
    grid = [[(str(cells[r][c]).strip() if c < len(cells[r]) and cells[r][c] is not None else "") for c in range(width)] for r in hrows]
    for i in range(len(grid) - 1):
        for c in range(1, width):
            below = any(grid[j][c] for j in range(i + 1, len(grid)))
            if not grid[i][c] and below and grid[i][c - 1] and any(grid[j][c - 1] for j in range(i + 1, len(grid))):
                grid[i][c] = grid[i][c - 1]
    out: dict[int, str] = {}
    for c in range(width):
        parts: list[str] = []
        for i in range(len(grid)):
            p = re.sub(r"\s+", " ", grid[i][c])
            if p and p not in parts:
                parts.append(p)
        if parts:
            out[c] = " ".join(parts)[:120]
    return out


def _base_ym(filename: str, meta: dict[str, Any], lines: list[str]) -> str | None:
    ym = file_info(filename).get("ym")
    if ym:
        return ym
    if meta.get("base_ym"):
        return str(meta["base_ym"])
    m = re.search(r"\((\d{6})\)", filename or "")
    if m:
        return m.group(1)
    for key in ("기준일", "기준년월", "기준월", "기준일자", "기준"):
        v = meta.get(key)
        if v:
            mm = YM_RE.search(str(v))
            if mm and 1 <= int(mm.group(2)) <= 12:
                return f"{mm.group(1)}{int(mm.group(2)):02d}"
    for line in lines:
        if "기준" in line:
            mm = YM_RE.search(line)
            if mm and 1 <= int(mm.group(2)) <= 12:
                return f"{mm.group(1)}{int(mm.group(2)):02d}"
    return None


def _period(label: str) -> tuple[int | None, int] | None:
    """기간 머리글 → (연도 또는 None, 월). '1월' · '2026.01' · '2026-01' · '202601'."""
    m = MONTH_RE.match(label)
    if m and 1 <= int(m.group(1)) <= 12:
        return None, int(m.group(1))
    m = YM_HEAD.match(label)
    if m and 1 <= int(m.group(2)) <= 12:
        return int(m.group(1)), int(m.group(2))
    t = re.sub(r"\D", "", label)
    if len(t) == 6 and label.strip().isdigit() and 1 <= int(t[4:]) <= 12 and t[:2] in ("19", "20"):
        return int(t[:4]), int(t[4:])
    return None


def read_report(content: bytes, filename: str) -> Report | None:
    """보고서 양식이면 행 목록, 일반 표(머리글 1줄 · 들여쓰기 없음 · 기간 열 없음)면 None — 일반 표 파서가 읽는다."""
    if not (filename or "").lower().endswith((".xlsx", ".xlsm")):
        return None
    try:
        sheets = load_sheets(content)
    except Exception:  # noqa: BLE001 — 엑셀이 아니거나 깨진 파일은 일반 파서가 오류를 낸다
        return None
    sheet = next((s for s in sheets if any(_nonempty(r) for r in s.cells)), None)
    if sheet is None:
        return None
    return _read_sheet(sheet, filename)


def _read_sheet(sheet: Sheet, filename: str) -> Report | None:
    cells = sheet.cells
    start = _header_start(cells)
    if start is None:
        return None
    hrows = _header_rows(cells, start)
    width = max((len(r) for r in cells[start : start + 200]), default=0)
    labels = _labels(cells, hrows, width)
    data_start = hrows[-1] + 1
    body = [r for r in range(data_start, len(cells)) if _nonempty(cells[r]) and not _note(cells[r])]
    if not body or len(labels) < 2:
        return None
    # 열 역할 — 값이 대부분 숫자면 값 열
    numeric: dict[int, bool] = {}
    for c in labels:
        vals = [cells[r][c] for r in body if c < len(cells[r]) and cells[r][c] is not None and str(cells[r][c]).strip() != ""]
        nums = sum(1 for v in vals if _is_num(v))
        numeric[c] = bool(vals) and nums >= 0.8 * len(vals)
    item_cols = [c for c in sorted(labels) if not numeric[c]]
    value_cols = [c for c in sorted(labels) if numeric[c]]
    if not value_cols:
        return None
    meta_lines = [" ".join(str(v) for v in cells[r] if v is not None and str(v).strip()) for r in range(start)]
    meta = _header_meta(sheet, start)
    base = _base_ym(filename, meta, meta_lines)
    periods = {c: p for c in value_cols if (p := _period(labels[c])) is not None}
    # 기간 열이 둘 이상이거나 값 열이 모두 기간이면 펼친다 — 1월 파일(열 1개)과 8월 파일(열 8개)이 같은 구조가 되게
    unpivot = bool(periods) and (len(periods) >= PERIOD_MIN - 1 or len(periods) == len(value_cols))
    # 계층 — 들여쓰기가 있는 첫 항목 열
    hier = next((c for c in item_cols if len({_level(sheet, r, c) for r in body if str(sheet.text(r, c)).strip()}) > 1), None)
    multi = len(hrows) > 1
    if not (multi or hier is not None or unpivot):
        return None  # 일반 표 — 기존 파서로
    # 머리글 이름 다듬기: 기준월과 같은 'N월'은 '기준월'로(달마다 열 이름이 바뀌지 않게)
    names: dict[int, str] = {}
    used: set[str] = set()
    base_m = int(base[4:]) if base else None
    for c in sorted(labels):
        n = labels[c]
        if base_m and not (unpivot and c in periods):
            n = re.sub(rf"(?<!\d){base_m}\s*월", "기준월", n)
        k, i = n, 2
        while k in used:
            k, i = f"{n} {i}", i + 1
        used.add(k)
        names[c] = k
    measure = str(meta.get("구분") or "").strip() or "값"
    has_ym_col = any(re.search(r"기준\s*(년월|월|일)|^ym$|연월|년월", names[c], re.I) for c in item_cols)
    rows: list[dict[str, Any]] = []
    stack: list[tuple[int, str]] = []
    totals = 0
    year = int(base[:4]) if base else None
    for r in body:
        item: dict[str, Any] = {}
        for c in item_cols:
            v = cells[r][c] if c < len(cells[r]) else None
            item[names[c]] = None if v is None or str(v).strip() == "" else (str(v).strip() if not isinstance(v, (int, float)) or isinstance(v, bool) else _code_text(v))
        if hier is not None:
            name = str(sheet.text(r, hier)).strip()
            if name:
                lv = _level(sheet, r, hier)
                while stack and stack[-1][0] >= lv:
                    stack.pop()
                parent = ">".join(n for _, n in stack)
                stack.append((lv, name))
                item[PARENT_COL], item[LEVEL_COL] = parent or None, lv
        is_total = any(isinstance(item.get(names[c]), str) and TOTAL_RE.match(item[names[c]]) for c in item_cols)
        if is_total:
            totals += 1
        vals = {c: (_num(cells[r][c]) if c < len(cells[r]) and _is_num(cells[r][c]) else None) for c in value_cols}
        if all(v is None for v in vals.values()):
            continue  # 값이 없는 줄(상위 항목 제목 · 빈 줄)은 계층만 기억
        if unpivot:
            rest = {names[c]: vals[c] for c in value_cols if c not in periods}
            for c, (py, pm) in periods.items():
                if vals[c] is None:
                    continue
                yy = py or year
                rows.append({YM_COL: f"{yy}{pm:02d}" if yy else f"{pm:02d}", **item, **rest, measure: vals[c], TOTAL_COL: is_total})
        else:
            rows.append({**({YM_COL: base} if base and not has_ym_col else {}), **item, **{names[c]: vals[c] for c in value_cols}, TOTAL_COL: is_total})
    if not rows:
        return None
    keys: list[str] = []
    for row in rows:
        for k in row:
            if k not in keys:
                keys.append(k)
    if not totals:
        keys = [k for k in keys if k != TOTAL_COL]
    if hier is None:
        keys = [k for k in keys if k not in (PARENT_COL, LEVEL_COL)]
    rows = [{k: row.get(k) for k in keys} for row in rows]
    unit = meta.get("unit_multiplier")
    notes = [f"보고서 양식으로 읽었습니다 — 머리글 {len(hrows)}줄" + (" · 들여쓰기 계층" if hier is not None else "") + (f" · 기간 열 {len(periods)}개를 행으로 펼침" if unpivot else "")]
    if unit:
        notes.append(f"원본 단위: {unit:,}원 — 값은 원본 그대로 저장합니다")
    return Report(rows, {"layout": "report", "sheet": sheet.name, "headerRows": [r + 1 for r in hrows], "baseYm": base, "unitMultiplier": unit, "unpivot": unpivot, "hierarchy": hier is not None,
                         "meta": {k: v for k, v in meta.items() if k not in ("unit_multiplier",)}, "notes": notes})


def _note(row: list[Any]) -> bool:
    cells = _nonempty(row)
    return len(cells) == 1 and bool(NOTE_RE.match(str(row[cells[0]])))


def _code_text(v: Any) -> Any:
    """항목 열의 숫자(코드 · 연월) — 정수면 글자로(앞자리 0 은 이미 글자 셀이면 보존)."""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    if isinstance(v, int):
        return str(v)
    return v
