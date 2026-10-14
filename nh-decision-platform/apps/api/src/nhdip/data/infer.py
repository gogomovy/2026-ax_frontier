"""파일에서 데이터셋 정의 추론 (Phase J 후속 · DEF-01~05 · Q160~Q163).

데이터셋은 처음부터 정해 둔 목록이 아니다 — 정의(`cfg.dataset`: 컬럼 · 타입 · 키 · 기준일 열 · 파서)가 곧 데이터 모양이다.
정의가 없는 새 종류의 파일을 올릴 때, 파일의 머리글 · 값으로 정의 초안을 만들어 사람이 확인 · 고쳐 저장하게 한다.
- `infer_definition`   새 파일 → 새 데이터셋 정의 초안 (머리글 줄 찾기 · 열 이름 · 타입 · 필수 · 키 조합 · 기준일 열 · 파일 이름 규칙)
- `infer_new_columns`  기존 데이터셋 + 새 파일 → 정의에 없는 열(조용히 버려지던 열)을 새 열 후보로
- `validate_definition` 저장 전 정의 점검 (코드 형식 · 열 이름 중복 · 타입 · 키/기준일 열이 정의 안에 있는지)

추론은 제안일 뿐 저장하지 않는다. 확정한 정의로 올린 파일은 기존 업로드와 같은 품질 · 개인정보 검사를 거친다.
원본 보고서 양식(2633 · 2020 · 7790)은 전용 어댑터가 있어 새 데이터셋으로 만들지 않고 기존 데이터셋에 올리게 안내한다.
"""
from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime
from itertools import combinations
from typing import Any

from nhdip.data.datasets import IngestError, _norm, _read_table, header_map
from nhdip.privacy import mask_text

TYPES = ("str", "int", "num", "date", "bool")
CODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-]{1,59}$")
MAX_COLUMNS = 200
SCAN_ROWS = 20000  # 타입 · 키 판단에 읽는 최대 행 — 더 큰 파일은 앞부분으로 판단하고 올릴 때 전체를 검사한다
KEY_POOL = 8  # 키 조합을 찾아볼 후보 열 수
KEY_MAX = 3  # 키 조합 최대 열 수

_YM = re.compile(r"^(19|20)\d{2}[./]?(0[1-9]|1[0-2])$")
_INT = re.compile(r"^-?(\d{1,3}(,\d{3})+|\d+)$")
_NUM = re.compile(r"^-?(\d{1,3}(,\d{3})+|\d+)(\.\d+)?$")
_LEAD0 = re.compile(r"^-?0\d+$")  # 0 으로 시작하는 숫자 글자(코드 · 번호) — 숫자로 바꾸면 0 이 사라진다
_DATE_FMTS = ("%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d")
_DATE_HEADER = re.compile(r"(일자|날짜|기준일|일시|date|dt\b|as_?of)", re.I)
_YM_HEADER = re.compile(r"(기준월|기준년월|연월|년월|ym|yyyymm|period|기간)", re.I)
_ID_HEADER = re.compile(r"(코드|번호|code|id\b|no\b|num\b|구분|종류|명\b)", re.I)


class InferError(IngestError):
    """정의를 추론할 수 없는 파일 (원본 보고서 양식 · 빈 파일 · 읽을 수 없음)."""


# ═════════════════════════ 값 분류 ═════════════════════════
def _empty(v: Any) -> bool:
    return v is None or (isinstance(v, str) and v.strip() in ("", "-"))


def _is_date_text(s: str, header: str) -> bool:
    for fmt in _DATE_FMTS:
        try:
            d = datetime.strptime(s, fmt)
        except ValueError:
            continue
        return 1990 <= d.year <= 2100
    if len(s) == 8 and s.isdigit() and _DATE_HEADER.search(header):  # 20260831 은 머리글이 날짜를 말할 때만 (일반 번호와 구분)
        try:
            return 1990 <= datetime.strptime(s, "%Y%m%d").year <= 2100
        except ValueError:
            return False
    return False


def _tag(v: Any, header: str) -> str:
    """값 하나 → empty | bool | date | ym | int | num | str"""
    if _empty(v):
        return "empty"
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, (date, datetime)):
        return "date"
    if isinstance(v, int):
        return "ym" if _YM.match(str(v)) else "int"
    if isinstance(v, float):
        if v.is_integer():
            return "ym" if _YM.match(str(int(v))) else "int"
        return "num"
    s = str(v).strip()
    if _YM.match(s):
        return "ym"
    if _is_date_text(s, header):
        return "date"
    if _LEAD0.match(s) or len(re.sub(r"\D", "", s)) > 15 and s.replace(",", "").lstrip("-").isdigit():
        return "str"
    if _INT.match(s):
        return "int"
    if _NUM.match(s):
        return "num"
    return "str"


def _column_type(header: str, values: list[Any]) -> tuple[str, bool, str | None]:
    """(타입, 연월(YYYYMM) 글자 열인가, 설명). 값이 하나라도 달리 읽히면 문자로 둔다 — 올릴 때 형 변환 오류로 막히지 않게."""
    tags = {_tag(v, header) for v in values} - {"empty"}
    if not tags:
        return "str", False, "값이 비어 있어 문자로 정했습니다"
    if tags == {"ym"}:
        return "str", True, None
    if tags == {"date"}:
        return "date", False, None
    if tags == {"bool"}:
        return "bool", False, None
    if tags <= {"int", "num", "ym"}:  # 연월처럼 보이는 숫자가 다른 숫자와 섞이면 그냥 숫자
        return ("int" if tags <= {"int", "ym"} else "num"), False, None
    if tags & {"int", "num"} and "str" in tags:
        return "str", False, "숫자로 보이지만 일부 값이 달라 문자로 정했습니다"
    return "str", False, None


def _slug(header: str, used: set[str], idx: int) -> str:
    s = re.sub(r"[^0-9A-Za-z가-힣]+", "_", str(header).strip()).strip("_").lower()[:50]
    if not s:
        s = f"col_{idx + 1:02d}"
    if s[0].isdigit():
        s = f"c_{s}"
    base, n = s, 2
    while s in used:
        s, n = f"{base}_{n}", n + 1
    used.add(s)
    return s


# ═════════════════════════ 머리글 줄 · 읽기 ═════════════════════════
def _textual(c: Any) -> bool:
    return isinstance(c, str) and c.strip() != "" and _tag(c, "") in ("str",)


def _header_row(rows: list[list[Any]]) -> int:
    """제목 · 기준 · 단위 줄 아래의 머리글 줄 — 글자 칸이 여럿이고 그 줄 이후부터 값이 나오는 첫 줄. 못 찾으면 첫 줄."""
    head = rows[:30]
    width = max((sum(1 for c in r if not _empty(c)) for r in head), default=0)
    for i, r in enumerate(head):
        cells = [c for c in r if not _empty(c)]
        if len(cells) >= 2 and len(cells) >= 0.6 * width and all(_textual(c) for c in cells) and any(not _empty(c) for c in (rows[i + 1] if i + 1 < len(rows) else [])):
            return i
    return 0


def _read(content: bytes, filename: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """(원본 행, 파서 설정). 머리글이 첫 줄이 아니면 parser 에 header_row / skip_rows 를 담아 다음 업로드도 같게 읽는다."""
    name = filename.lower()
    parser: dict[str, Any] = {}
    if name.endswith((".xlsx", ".xlsm")):
        try:
            import openpyxl

            wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=True)
            ws = wb.worksheets[0]
            grid = [list(r) for _, r in zip(range(40), ws.iter_rows(values_only=True))]
        except Exception as exc:  # noqa: BLE001 — 파일 형식 오류는 사용자에게
            raise InferError(f"엑셀을 읽을 수 없습니다 — {exc}") from exc
        idx = _header_row(grid)
        if idx:
            parser["header_row"] = idx + 1
        if wb.worksheets[0].title and len(wb.worksheets) > 1:
            parser["sheet"] = wb.worksheets[0].title
    elif name.endswith((".csv", ".txt", ".tsv")):
        text = content.decode("utf-8-sig", errors="replace")
        delim = "\t" if name.endswith(".tsv") else ","
        grid = [r for _, r in zip(range(40), csv.reader(text.splitlines(), delimiter=delim))]
        idx = _header_row(grid)
        if idx:
            parser["skip_rows"] = idx
    else:
        idx = 0
    try:
        rows = _read_table(content, filename, parser, None)
    except IngestError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise InferError(f"파일을 읽을 수 없습니다 — {exc}") from exc
    return rows, parser


def _reject_report_form(content: bytes, filename: str) -> None:
    """원본 보고서 양식은 어댑터가 읽는다 — 새 데이터셋이 아니라 기존 데이터셋에 올리게 안내."""
    if not filename.lower().endswith(".xlsx"):
        return
    try:
        from nhdip.data.adapters import detect, load_sheets

        adapter, _ = detect(load_sheets(content), filename)
    except Exception:  # noqa: BLE001 — 판별 실패는 일반 표로 읽는다
        return
    if adapter is not None:
        raise InferError(f"이 파일은 원본 보고서 양식({adapter.report_code})입니다 — 새 데이터셋을 만들지 말고 기존 데이터셋 {adapter.dataset} 에 올려 주세요")


# ═════════════════════════ 정의 추론 ═════════════════════════
def _stem_pattern(filename: str) -> str | None:
    stem = re.sub(r"\.[A-Za-z0-9]+$", "", filename.rsplit("/", 1)[-1]).strip()
    if not stem:
        return None
    parts = re.split(r"(\d+)", stem)
    return "".join(r"\d+" if p.isdigit() else re.escape(p) for p in parts)


def suggest_code(filename: str) -> str:
    stem = re.sub(r"\.[A-Za-z0-9]+$", "", filename.rsplit("/", 1)[-1])
    ascii_part = re.sub(r"[^A-Za-z0-9]+", "_", stem).strip("_").upper()
    ascii_part = re.sub(r"_?\d{4,}$", "", ascii_part).strip("_")  # 끝의 날짜 · 일련번호는 코드에서 뺀다
    if len(ascii_part) >= 3 and ascii_part[0].isalpha():
        return ascii_part[:40]
    import hashlib

    return "DS_" + hashlib.sha1(stem.encode("utf-8")).hexdigest()[:8].upper()


def _find_key(cols: list[dict[str, Any]], data: list[list[Any]], as_of_idx: int | None) -> list[str]:
    """행을 구분하는 가장 작은 열 조합 — 값이 다 있고(결측 없음) 서로 겹치지 않는 조합. 측정값(소수 · 금액)은 후보에서 뺀다."""
    pool: list[int] = []
    for i, c in enumerate(cols):
        if c["type"] in ("num", "bool"):
            continue
        if c["type"] == "int" and not _ID_HEADER.search(c["label"]):
            continue
        if any(_empty(r[i]) for r in data):
            continue
        pool.append(i)
    pool = pool[:KEY_POOL]
    if len(data) < 2 or not pool:
        return []
    for size in range(1, min(KEY_MAX, len(pool)) + 1):
        combos = list(combinations(pool, size))
        if as_of_idx is not None:  # 기준일 열이 든 조합을 먼저 — 월별 자료는 (기준월, 항목) 이 키
            combos.sort(key=lambda t: as_of_idx not in t)
        for combo in combos:
            seen = {tuple(str(r[i]) for i in combo) for r in data}
            if len(seen) == len(data):
                return [cols[i]["name"] for i in combo]
    return []


def infer_definition(content: bytes, filename: str, *, code: str | None = None, name: str | None = None, origin: str = "bank") -> dict[str, Any]:
    """새 파일 → 데이터셋 정의 초안(`DatasetIn` 모양) + 사람이 확인할 안내(notes) + 열별 예시값(samples). 저장하지 않는다."""
    if origin not in ("bank", "ext"):
        raise InferError("origin 은 bank(당행) | ext(외부)")
    _reject_report_form(content, filename)
    raw, parser = _read(content, filename)
    if not raw:
        raise InferError("읽을 행이 없습니다 — 첫 줄(또는 제목 줄 아래)에 머리글이 있는 표인지 확인하세요")
    raw = raw[:SCAN_ROWS]
    headers = [str(h) for h in raw[0].keys() if not _empty(h)]
    if not headers:
        raise InferError("머리글을 찾지 못했습니다")
    if len(headers) > MAX_COLUMNS:
        raise InferError(f"열이 너무 많습니다({len(headers)}개, 최대 {MAX_COLUMNS}개)")
    used: set[str] = set()
    cols: list[dict[str, Any]] = []
    notes: list[str] = []
    ym_idx: list[int] = []
    date_idx: list[int] = []
    for i, h in enumerate(headers):
        vals = [r.get(h) for r in raw]
        typ, is_ym, note = _column_type(h, vals)
        cols.append({"name": _slug(h, used, i), "label": h, "type": typ, "required": False, "aliases": []})
        if note:
            notes.append(f"{h}: {note}")
        if is_ym:
            ym_idx.append(i)
        if typ == "date":
            date_idx.append(i)
    if any(h.strip() == "" or re.match(r"^col\d+$", h) for h in map(str, raw[0].keys())):
        notes.append("머리글이 비어 있는 열은 건너뛰었습니다")
    # 기준일 열 — 연월(YYYYMM) 또는 날짜 열 중 머리글이 말하는 것, 하나뿐이면 그것
    cand = ym_idx + date_idx
    hint = [i for i in cand if _YM_HEADER.search(cols[i]["label"]) or _DATE_HEADER.search(cols[i]["label"])]
    as_of_idx = (hint or cand or [None])[0] if (hint or len(cand) == 1) else None
    if cand and as_of_idx is None:
        as_of_idx = cand[0]
        notes.append(f"기준일로 쓸 수 있는 열이 여럿이라 '{cols[as_of_idx]['label']}' 를 골랐습니다 — 다르면 바꾸세요")
    data = [[r.get(h) for h in headers] for r in raw]
    keys = _find_key(cols, data, as_of_idx)
    if not keys:
        notes.append("행을 구분하는 열 조합을 찾지 못했습니다 — 키 없이 저장됩니다(같은 행이 겹쳐도 막지 않음). 필요하면 키 열을 직접 고르세요")
    key_set = set(keys)
    for i, c in enumerate(cols):
        if c["name"] in key_set or i == as_of_idx:
            c["required"] = True  # 키 · 기준일 열만 필수 — 나머지는 비어 있거나 빠져도 올라온다(자료 형식이 고정되지 않게)
    rules: list[dict[str, Any]] = [{"rule": "min_rows", "value": 1, "severity": "error"}]
    out_name = (name or "").strip() or re.sub(r"\.[A-Za-z0-9]+$", "", filename.rsplit("/", 1)[-1]).strip() or "새 자료"
    samples = {
        c["name"]: [mask_text(str(v))[:40] for v in (r[i] for r in data[:200]) if not _empty(v)][:3]
        for i, c in enumerate(cols)
    }
    return {
        "code": (code or "").strip() or suggest_code(filename),
        "name": out_name[:150],
        "origin": origin,
        "kind": "fact",
        "description": f"파일 '{filename}' 에서 추론한 정의입니다. 열 이름 · 타입 · 키를 확인하세요.",
        "file_pattern": _stem_pattern(filename),
        "refresh_cycle": None,
        "columns": cols,
        "key_columns": keys,
        "as_of_column": cols[as_of_idx]["name"] if as_of_idx is not None else None,
        "mapping": {},
        "quality_rules": rules,
        "parser": parser,
        "active": True,
        "notes": notes,
        "samples": samples,
        "rows": len(raw),
    }


# ═════════════════════════ 기존 데이터셋에 새 열 ═════════════════════════
def infer_new_columns(ds: Any, content: bytes, filename: str) -> dict[str, Any]:
    """기존 데이터셋 + 새 파일 → 정의에 없어 저장되지 않던 열을 새 열 후보로. 기존 열은 그대로 두고 새 열은 선택(필수 아님)으로만 더한다."""
    _reject_report_form(content, filename)
    raw, _ = _read(content, filename)
    if not raw:
        raise InferError("읽을 행이 없습니다")
    raw = raw[:SCAN_ROWS]
    headers = [str(h) for h in raw[0].keys() if not _empty(h) and not re.match(r"^col\d+$", str(h))]
    hmap, _ = header_map(ds, headers)
    matched = set(hmap.values())
    used = {c["name"].lower() for c in ds.columns}
    new_cols: list[dict[str, Any]] = []
    for i, h in enumerate(headers):
        if h in matched:
            continue
        typ, _is_ym, _note = _column_type(h, [r.get(h) for r in raw])
        new_cols.append({"name": _slug(h, used, len(ds.columns) + i), "label": h, "type": typ, "required": False, "aliases": []})
    return {
        "matched": [{"column": c, "header": h} for c, h in hmap.items()],
        "newColumns": new_cols,
        "columns": merge_columns(ds.columns, new_cols),
        "samples": {c["name"]: [mask_text(str(r.get(c["label"])))[:40] for r in raw[:200] if not _empty(r.get(c["label"]))][:3] for c in new_cols},
    }


def merge_columns(existing: list[dict[str, Any]], new: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """기존 열은 그대로 두고 이름이 겹치지 않는 새 열만 뒤에 더한다(새 열은 필수가 아님)."""
    have = {str(c.get("name")).lower() for c in existing}
    return [*existing, *({**c, "required": False} for c in new if str(c.get("name")).lower() not in have)]


# ═════════════════════════ 정의 점검 ═════════════════════════
def validate_definition(d: dict[str, Any]) -> list[str]:
    """저장 전 정의 점검 — 문제 목록(비면 통과). 코드 형식 · 열 이름 중복 · 타입 · 키 · 기준일 열 · 별칭 형식."""
    errs: list[str] = []
    code = str(d.get("code") or "")
    if not CODE_RE.match(code):
        errs.append("데이터셋 코드는 영문 · 숫자로 시작하고 영문 · 숫자 · _ - 만 쓰는 2~60자입니다")
    if not str(d.get("name") or "").strip():
        errs.append("데이터셋 이름이 비어 있습니다")
    if d.get("origin") not in ("bank", "ext"):
        errs.append("출처 구분은 bank(당행) | ext(외부) 입니다")
    cols = d.get("columns")
    if not isinstance(cols, list) or not cols:
        errs.append("컬럼이 하나도 없습니다 — 컬럼 정의 없이는 파일을 읽을 수 없습니다")
        return errs
    if len(cols) > MAX_COLUMNS:
        errs.append(f"열은 최대 {MAX_COLUMNS}개입니다")
    names: set[str] = set()
    for i, c in enumerate(cols, start=1):
        if not isinstance(c, dict) or not str(c.get("name") or "").strip():
            errs.append(f"{i}번째 열의 이름이 비어 있습니다")
            continue
        n = str(c["name"]).strip()
        if len(n) > 60:
            errs.append(f"열 이름이 너무 깁니다(60자 이하): {n[:20]}…")
        if _norm(n) in names:
            errs.append(f"열 이름이 겹칩니다: {n}")
        names.add(_norm(n))
        if c.get("type", "str") not in (*TYPES, "integer", "number", "decimal", "float"):
            errs.append(f"열 '{n}' 의 타입은 {' | '.join(TYPES)} 중 하나입니다")
        if not isinstance(c.get("aliases", []), list):
            errs.append(f"열 '{n}' 의 별칭은 목록이어야 합니다")
    by = {_norm(str(c.get("name"))) for c in cols if isinstance(c, dict)}
    for k in d.get("key_columns") or []:
        if _norm(str(k)) not in by:
            errs.append(f"키 열 '{k}' 이(가) 컬럼에 없습니다")
    if d.get("as_of_column") and _norm(str(d["as_of_column"])) not in by:
        errs.append(f"기준일 열 '{d['as_of_column']}' 이(가) 컬럼에 없습니다")
    return errs
