"""원본 보고서 엑셀 어댑터 (작업 1.3.2 ~ 1.3.6 · DATA-01) — 2633 · 2020 · 7790 원본 양식을 데이터셋 행으로 바꾼다.

- 자동 선택: 파일명 규약 `(YYYYMM)코드_명칭.xlsx` + 시트 내용(머리글 · 헤더 단어)으로 점수를 매겨 가장 맞는 어댑터를 고른다.
- 계층 복원: 과목 · 항목 이름의 들여쓰기(셀 들여쓰기 · 앞 공백)로 parent_path 를 만든다.
- 셀 계보: 모든 값에 `Sheet!A1` 형식의 원천 셀(src_ref)을 남긴다.
- 메타: 조회일자 · 조회사무소 · 기준일 · 구분 · 단위를 보존한다. 조회자 · 담당자 이름 같은 개인 정보는 저장하지 않는다(DATA-06).
- 이름 → 코드 매핑은 데이터셋 parser 설정(관리자 편집)에 둔다. 매핑에 없는 과목도 경로 코드로 보존한다(추이 · 구성비 보조).
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from typing import Any, Callable

FILE_RE = re.compile(r"\((\d{6})\)\s*(\d{4})")
MONTH_RE = re.compile(r"^\s*(\d{1,2})\s*월\s*$")
UNIT_RE = re.compile(r"\[\s*([\d,]+)\s*\]\s*원")
UNIT_WORDS = {"원": 1, "천원": 1_000, "백만원": 1_000_000, "억원": 100_000_000, "조원": 1_000_000_000_000}


class AdapterError(ValueError):
    pass


@dataclass
class Parsed:
    adapter: str
    rows: list[dict[str, Any]]
    meta: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


@dataclass
class Sheet:
    name: str
    cells: list[list[Any]]  # 값
    indents: list[list[int]]  # 들여쓰기 수준(셀 서식)

    def text(self, r: int, c: int) -> str:
        v = self.cells[r][c] if r < len(self.cells) and c < len(self.cells[r]) else None
        return "" if v is None else str(v)

    def ref(self, r: int, c: int) -> str:
        from openpyxl.utils import get_column_letter

        return f"{self.name}!{get_column_letter(c + 1)}{r + 1}"


def load_sheets(content: bytes) -> list[Sheet]:
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)  # 들여쓰기 서식을 읽기 위해 일반 모드
    out = []
    for ws in wb.worksheets:
        cells, indents = [], []
        for row in ws.iter_rows():
            cells.append([c.value for c in row])
            indents.append([int(getattr(c.alignment, "indent", 0) or 0) for c in row])
        out.append(Sheet(ws.title, cells, indents))
    return out


def file_info(filename: str) -> dict[str, str]:
    m = FILE_RE.search(filename or "")
    return {"ym": m.group(1), "report_code": m.group(2)} if m else {}


def _norm(s: Any) -> str:
    return re.sub(r"[\s_\-()·./\[\]]+", "", str(s or "")).lower()


def _level(sheet: Sheet, r: int, c: int) -> int:
    """들여쓰기 수준 = 셀 들여쓰기 + 앞 공백(반각 2칸 · 전각 1칸 = 1단계)."""
    raw = sheet.text(r, c)
    lead = len(raw) - len(raw.lstrip(" \u3000\t"))
    spaces = raw[:lead]
    return sheet.indents[r][c] + spaces.count("\u3000") + spaces.count("\t") + spaces.count(" ") // 2


def _num(v: Any) -> float | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", "")
    if s in ("", "-"):
        return None
    neg = s.startswith("(") and s.endswith(")")
    try:
        f = float(s.strip("()"))
    except ValueError:
        return None
    return -f if neg else f


def _header_meta(sheet: Sheet, upto: int) -> dict[str, Any]:
    """머리글 블록(헤더 행 위) — '키 : 값' · '키 : [값]' 조각을 모은다. 개인 이름 항목은 버린다."""
    meta: dict[str, Any] = {}
    skip = {"조회자", "담당자", "담당부서", "작성자"}
    for r in range(min(upto, len(sheet.cells))):
        line = " ".join(sheet.text(r, c) for c in range(len(sheet.cells[r])) if sheet.text(r, c).strip())
        if not line:
            continue
        um = UNIT_RE.search(line)
        if um:
            meta["unit_multiplier"] = int(um.group(1).replace(",", ""))
        else:
            uw = re.search(r"단위\s*[:：]?\s*(조원|억원|백만원|천원|원)", line)
            if uw:
                meta["unit_multiplier"] = UNIT_WORDS[uw.group(1)]
        for k, v in re.findall(r"([가-힣A-Za-z ]{2,10}?)\s*:\s*(\[[^\]]*\]|[^,:\[]+?)(?=,|\s+[가-힣A-Za-z ]{2,10}\s*:|$)", line):
            key = k.replace(" ", "")
            if key in skip or key.startswith("단위"):
                continue
            meta[key] = v.strip().strip("[]").strip()
        if "title" not in meta and r == 0 and ":" not in line:
            meta["title"] = line.strip()
    if "기준일" in meta:
        m = re.search(r"(\d{4})[-.](\d{2})", meta["기준일"])
        if m:
            meta["base_ym"] = m.group(1) + m.group(2)
    return meta


def _find(sheet: Sheet, pred: Callable[[str], bool], max_rows: int = 30) -> tuple[int, int] | None:
    for r in range(min(max_rows, len(sheet.cells))):
        for c in range(len(sheet.cells[r])):
            if pred(sheet.text(r, c)):
                return r, c
    return None


def _code_for(path: list[str], mapping: dict[str, str]) -> str | None:
    """매핑 키: '이름' 또는 '상위>이름'(경로 끝부분 일치). 더 긴(구체적) 키를 우선."""
    names = [_norm(p) for p in path]
    best, best_len = None, -1
    for key, code in mapping.items():
        parts = [_norm(x) for x in key.split(">")]
        if len(parts) <= len(names) and names[-len(parts):] == parts and len(parts) > best_len:
            best, best_len = code, len(parts)
    return best



TIDY_HEADS = {"ym", "기준년월", "기준월", "기준년월가정", "yyyymm", "accountcode", "itemcode", "productcode", "stdym"}


def _tidy(sheet: Sheet, max_rows: int = 20) -> bool:
    """정리된 표인지 — 앞 20줄 안에 정리표 머리글 칸(기준년월 · ym · 코드 컬럼)이 있으면. 제목 · 기준 · 단위 줄이 위에 있는 실무형 표도 포함(RD-09)."""
    for r in range(min(max_rows, len(sheet.cells))):
        if {_norm(sheet.text(r, c)) for c in range(len(sheet.cells[r]))} & TIDY_HEADS:
            return True
    return False

# ═════════════════════════ 어댑터 ═════════════════════════
class Adapter:
    code = ""
    report_code = ""
    dataset = ""
    title_words: tuple[str, ...] = ()

    def structure(self, sheet: Sheet) -> bool:
        """원본 양식 구조(헤더 단어 · 배치)가 있는지 — 정리된 표(기준년월 · 코드 컬럼)는 일반 파서가 처리."""
        return False

    def sniff(self, sheets: list[Sheet], filename: str) -> int:
        if not sheets or not self.structure(sheets[0]):
            return 0
        score = 0
        if file_info(filename).get("report_code") == self.report_code:
            score += 50
        if self.report_code and self.report_code in (filename or ""):
            score += 10
        head = " ".join(_norm(sheets[0].text(r, c)) for r in range(min(12, len(sheets[0].cells))) for c in range(min(40, len(sheets[0].cells[r])))) if sheets else ""
        score += sum(20 for w in self.title_words if _norm(w) in head)
        return score

    def parse(self, sheets: list[Sheet], filename: str, parser: dict[str, Any]) -> Parsed:  # pragma: no cover - 하위 구현
        raise NotImplementedError


class Report2020(Adapter):
    """과목별 월별 여신현황 — 머리글(조회일자 · 조회사무소 · 기준일 · 구분 · 단위) + '과목구분 | 1월 … 12월' + 들여쓰기 과목 트리."""

    code, report_code, dataset = "report_2020", "2020", "LOAN_BALANCE_MONTHLY"
    title_words = ("과목별 월별 여신현황", "과목구분", "계리잔액")

    def structure(self, sheet):
        hit = _find(sheet, lambda t: _norm(t) == "과목구분")
        return bool(hit) and any(MONTH_RE.match(sheet.text(hit[0], c)) for c in range(len(sheet.cells[hit[0]])))

    def parse(self, sheets, filename, parser):
        sh = sheets[0]
        hit = _find(sh, lambda t: _norm(t) == "과목구분")
        if not hit:
            raise AdapterError("2020 양식: '과목구분' 헤더를 찾지 못했습니다")
        hr, name_c = hit
        months = {c: int(MONTH_RE.match(sh.text(hr, c)).group(1)) for c in range(len(sh.cells[hr])) if MONTH_RE.match(sh.text(hr, c))}
        if not months:
            raise AdapterError("2020 양식: 월 컬럼(1월 ~ 12월)을 찾지 못했습니다")
        meta = _header_meta(sh, hr)
        year = (meta.get("base_ym") or file_info(filename).get("ym") or "")[:4]
        if not year:
            raise AdapterError("2020 양식: 기준일(연도)을 머리글 또는 파일명에서 찾지 못했습니다")
        mult = int(meta.get("unit_multiplier") or parser.get("unit_multiplier") or 1_000_000)
        to_mn = mult / 1_000_000  # 데이터셋 단위 백만원(KRW_MN)
        mapping = parser.get("account_codes") or {}
        stack: list[tuple[int, str]] = []
        rows, unmapped = [], []
        for r in range(hr + 1, len(sh.cells)):
            name = sh.text(r, name_c).strip()
            if not name:
                continue
            lv = _level(sh, r, name_c)
            while stack and stack[-1][0] >= lv:
                stack.pop()
            stack.append((lv, name))
            path = [n for _, n in stack]
            code = _code_for(path, mapping)
            if code is None:
                unmapped.append(">".join(path))
                if not parser.get("keep_unmapped", True):
                    continue
                code = "PATH:" + ">".join(path)
            for c, m in months.items():
                v = _num(sh.cells[r][c] if c < len(sh.cells[r]) else None)
                if v is None:
                    continue
                rows.append({"ym": f"{year}{m:02d}", "account_code": code, "account_name": name, "balance": round(v * to_mn, 6), "src_ref": sh.ref(r, c), "parent_path": ">".join(path[:-1])})
        meta.update({"unit": "KRW_MN", "source_unit_multiplier": mult, "months": sorted(months.values())})
        notes = [f"매핑 없는 과목 {len(unmapped)}개는 경로 코드(PATH:)로 보존"] if unmapped else []
        return Parsed(self.code, rows, meta, notes)


class Report2633(Adapter):
    """상품부문별 손익계산서 — 계층 항목명 + 'N월 누계'(또는 '누계') 금액 컬럼. 필수 4항목을 코드로 추출."""

    code, report_code, dataset = "report_2633", "2633", "PL_PRODUCT_SEGMENT"
    title_words = ("상품부문별", "손익계산서", "누계")

    def structure(self, sheet):
        return not _tidy(sheet) and _find(sheet, lambda t: "누계" in t) is not None

    def parse(self, sheets, filename, parser):
        sh = sheets[0]
        want_month = parser.get("cumulative_month")
        info = file_info(filename)
        ym = info.get("ym")
        hit = None
        for r in range(min(30, len(sh.cells))):
            cols = [c for c in range(len(sh.cells[r])) if "누계" in sh.text(r, c)]
            if cols:
                pick = cols[0]
                target = want_month or (int(ym[4:]) if ym else None)
                for c in cols:
                    m = re.search(r"(\d{1,2})\s*월", sh.text(r, c))
                    if target and m and int(m.group(1)) == int(target):
                        pick = c
                hit = (r, pick)
                break
        if not hit:
            raise AdapterError("2633 양식: '누계' 금액 컬럼을 찾지 못했습니다")
        hr, amt_c = hit
        name_c = next((c for c in range(len(sh.cells[hr])) if _norm(sh.text(hr, c)) in ("항목", "항목명", "과목", "과목명", "계정과목", "구분")), 0)
        meta = _header_meta(sh, hr)
        ym = ym or meta.get("base_ym")
        if not ym:
            raise AdapterError("2633 양식: 기준년월을 파일명 또는 머리글에서 찾지 못했습니다")
        mult = int(meta.get("unit_multiplier") or UNIT_WORDS.get(parser.get("unit", ""), 0) or 1_000_000)
        to_mn = mult / 1_000_000
        mapping = parser.get("item_codes") or {}
        stack: list[tuple[int, str]] = []
        rows, found = [], set()
        for r in range(hr + 1, len(sh.cells)):
            name = sh.text(r, name_c).strip()
            if not name:
                continue
            lv = _level(sh, r, name_c)
            while stack and stack[-1][0] >= lv:
                stack.pop()
            stack.append((lv, name))
            path = [n for _, n in stack]
            code = _code_for(path, mapping)
            v = _num(sh.cells[r][amt_c] if amt_c < len(sh.cells[r]) else None)
            if v is None or (code is None and not parser.get("keep_unmapped", False)):
                continue
            found.add(code)
            rows.append({"ym": ym, "item_code": code or "PATH:" + ">".join(path), "item_name": name, "amount": round(v * to_mn, 6), "src_ref": sh.ref(r, amt_c), "parent_path": ">".join(path[:-1])})
        missing = [c for c in parser.get("required_items", []) if c not in found]
        if missing:
            raise AdapterError(f"2633 양식: 필수 항목을 찾지 못했습니다 — {', '.join(missing)} (데이터셋 parser.item_codes 매핑 확인)")
        meta.update({"unit": "KRW_MN", "source_unit_multiplier": mult, "amount_column": sh.text(hr, amt_c)})
        return Parsed(self.code, rows, meta)


class Report7790(Adapter):
    """상품별 충당금 산출현황 — 다단 헤더, 상품코드 · 상품명 · … · '손실충당금 및 충당부채 총계'(헤더명 우선, 열 위치 폴백), 합계 행 감지."""

    code, report_code, dataset = "report_7790", "7790", "PROVISION_BY_PRODUCT"
    title_words = ("충당금", "상품코드", "손실충당금및충당부채총계")

    def structure(self, sheet):
        return not _tidy(sheet) and _find(sheet, lambda t: _norm(t) == "상품코드", 40) is not None

    def parse(self, sheets, filename, parser):
        sh = sheets[0]
        hit = _find(sh, lambda t: _norm(t) == "상품코드", 40)
        if not hit:
            raise AdapterError("7790 양식: '상품코드' 헤더를 찾지 못했습니다")
        hr, code_c = hit
        name_c = next((c for c in range(len(sh.cells[hr])) if _norm(sh.text(hr, c)) == "상품명"), code_c + 1)
        total_name = _norm(parser.get("total_header", "손실충당금 및 충당부채 총계"))
        total_c = None
        for r in range(max(0, hr - 3), min(hr + 4, len(sh.cells))):  # 병합 다단 헤더(위 · 아래 3행)
            for c in range(len(sh.cells[r])):
                if _norm(sh.text(r, c)) == total_name:
                    total_c = c
        notes = []
        if total_c is None:
            from openpyxl.utils import column_index_from_string

            col = parser.get("total_col", "X")
            total_c = column_index_from_string(col) - 1
            notes.append(f"'{parser.get('total_header', '손실충당금 및 충당부채 총계')}' 헤더를 찾지 못해 열 위치({col})를 사용")
        meta = _header_meta(sh, max(0, hr - 3))
        ym = file_info(filename).get("ym") or meta.get("base_ym")
        if not ym:
            for r in range(min(hr, len(sh.cells))):
                m = re.search(r"(\d{4})[.\-]?(\d{2})", " ".join(sh.text(r, c) for c in range(len(sh.cells[r]))))
                if m:
                    ym = m.group(1) + m.group(2)
                    break
        if not ym:
            raise AdapterError("7790 양식: 기준년월을 파일명 또는 머리글에서 찾지 못했습니다")
        start = hr + 1
        while start < len(sh.cells) and not sh.text(start, code_c).strip() and not re.search(r"합계|total", sh.text(start, name_c) + sh.text(start, code_c), re.I) and _num(sh.cells[start][total_c] if total_c < len(sh.cells[start]) else None) is None:
            start += 1  # 다단 헤더의 아래 행 건너뜀
        rows = []
        for r in range(start, len(sh.cells)):
            code = sh.text(r, code_c).strip()
            name = sh.text(r, name_c).strip()
            v = _num(sh.cells[r][total_c] if total_c < len(sh.cells[r]) else None)
            is_total = bool(re.search(r"^\s*(합\s*계|총\s*계|total)\s*$", code or name, re.I))
            if v is None or (not code and not is_total):
                continue
            rows.append({"ym": ym, "product_code": "TOTAL" if is_total else re.sub(r"\.0$", "", code), "product_name": name or ("합계" if is_total else ""), "provision": v, "is_total": is_total, "src_ref": sh.ref(r, total_c)})
        if not any(r["is_total"] for r in rows):
            notes.append("합계(Total) 행을 찾지 못했습니다 — 합계 일치 검증이 경고로 표시됩니다")
        meta.update({"total_column": sh.ref(hr, total_c).split("!")[1].rstrip("0123456789")})
        return Parsed(self.code, rows, meta, notes)


ADAPTERS: list[Adapter] = [Report2020(), Report2633(), Report7790()]
MIN_SCORE = 40


def detect(sheets: list[Sheet], filename: str) -> tuple[Adapter | None, int]:
    best, score = None, 0
    for a in ADAPTERS:
        s = a.sniff(sheets, filename)
        if s > score:
            best, score = a, s
    return (best, score) if score >= MIN_SCORE else (None, score)


def parse_report(content: bytes, filename: str, dataset_code: str, parser: dict[str, Any]) -> Parsed | None:
    """정의가 원본 양식 어댑터를 명시했을 때만(parser.adapter = 어댑터 코드 · auto) 변환, 아니면 None.
    명시하지 않은 정의(파일에서 만든 정의)는 쓰지 않는다 — 보고서 양식은 data/layout.py 가 파일 모양에서 구조를 만든다 (M.25 · Q213)."""
    mode = (parser or {}).get("adapter") or "none"
    if mode == "none":
        return None
    sheets = load_sheets(content)
    if not sheets or not sheets[0].cells:
        return None
    if mode != "auto":
        a = next((x for x in ADAPTERS if x.code == mode), None)
        if a is None:
            raise AdapterError(f"알 수 없는 어댑터: {mode}")
        return a.parse(sheets, filename, parser or {})
    a, score = detect(sheets, filename)
    if a is None:
        return None
    if a.dataset != dataset_code:
        # 이 정의의 양식이 아니다 — 다른 자료를 고르라고 특정 데이터셋을 가리키지 않는다(정의는 올린 파일로 만든다)
        raise AdapterError(f"이 파일은 다른 원본 양식({a.report_code})입니다 — 이 자료의 양식과 다릅니다. 맞는 자료를 고르거나 대상 없이 올려 새 자료로 만드세요")
    return a.parse(sheets, filename, parser or {})
