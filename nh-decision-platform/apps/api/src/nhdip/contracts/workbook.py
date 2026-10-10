"""컬럼 정의서(엑셀) 파서 — openpyxl 만 사용한다(로컬 스크립트에서도 import 가능).

시트 규칙: 시트명 `T01_종기부_현황` → 테이블 코드 T01 · 부서 종기부 · 이름 현황.
헤더 행은 첫 셀이 `컬럼명` 인 행. 헤더 이름으로 열을 찾으므로 열 순서가 바뀌어도 된다.
"""
from __future__ import annotations

import io
import re
from typing import Any

HEADER_KEYS = {
    "column_name": ["컬럼명"],
    "kor_name": ["한글컬럼명"],
    "pk": ["PK유무", "PK"],
    "data_type": ["TYPE", "타입"],
    "source_desc": ["원본데이터(파일명/DB)", "원본데이터"],
    "source_column": ["원천 컬럼", "원천컬럼"],
    "mock": ["목데이터 여부(확인필요)", "목데이터", "목데이터여부"],
    "expected": ["화면값", "목업값(검증용)", "목업값"],
}
SHEET_RE = re.compile(r"^(T\d{2,3})_([^_]+)_(.+)$")
COL_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,62}$")


def _norm(s: Any) -> str:
    return re.sub(r"\s+", "", str(s or ""))


def _cell(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def parse_workbook(content: bytes) -> list[dict[str, Any]]:
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=True)
    tables: list[dict[str, Any]] = []
    for ws in wb.worksheets:
        m = SHEET_RE.match(ws.title.strip())
        if not m:
            continue
        rows = list(ws.iter_rows(values_only=True))
        hdr_idx = next((i for i, r in enumerate(rows) if r and _norm(r[0]) == "컬럼명"), None)
        if hdr_idx is None:
            continue
        header = [_norm(h) for h in rows[hdr_idx]]
        pos: dict[str, int] = {}
        for key, names in HEADER_KEYS.items():
            for n in names:
                if _norm(n) in header:
                    pos[key] = header.index(_norm(n))
                    break
        if "column_name" not in pos:
            continue
        cols = []
        for seq, r in enumerate(rows[hdr_idx + 1 :], start=1):
            name = _cell(r[pos["column_name"]]) if pos["column_name"] < len(r) else None
            if not name:
                continue
            get = lambda k: _cell(r[pos[k]]) if k in pos and pos[k] < len(r) else None  # noqa: E731
            cols.append(
                {
                    "seq": seq,
                    "column_name": name.upper(),
                    "valid_name": bool(COL_RE.match(name.upper())),
                    "kor_name": get("kor_name") or name,
                    "is_pk": (get("pk") or "").upper() in ("Y", "O", "PK"),
                    "data_type": (get("data_type") or "").upper() or None,
                    "source_desc": get("source_desc"),
                    "source_column": get("source_column"),
                    "is_mock": (get("mock") or "").upper() in ("O", "Y"),
                    "expected_text": get("expected"),
                }
            )
        tables.append({"table_code": m.group(1), "dept": m.group(2), "name": m.group(3), "sheet": ws.title, "columns": cols})
    return tables
