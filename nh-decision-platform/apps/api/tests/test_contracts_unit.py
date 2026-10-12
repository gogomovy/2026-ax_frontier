"""컬럼 정의서 파서 · 다행 적재 단위 시험 (B.38) — DB 없이."""
from __future__ import annotations

import io

import openpyxl

from nhdip.contracts.workbook import parse_workbook, table_code

HDR = ["컬럼명", "한글컬럼명", "PK유무", "TYPE", "원본데이터(파일명/DB)", "원천 컬럼", "목데이터 여부(확인필요)", "목업값(검증용)"]


def _wb(sheets: dict[str, list[list]]) -> bytes:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, rows in sheets.items():
        ws = wb.create_sheet(name)
        ws.append(HDR)
        for r in rows:
            ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_table_code_prefix_per_dept():
    p = {"종기부": "hq", "사업부서": "risk", "영업점": "branch"}
    assert table_code("T01", "종기부", p) == "T01"  # 기준 부서는 그대로 (기존 계약 호환)
    assert table_code("T02", "사업부서", p) == "RISK_T02"
    assert table_code("S99", "영업점", p) == "BRANCH_S99"
    assert table_code("T01", "모름", p) == "T01"  # 접두 없는 부서 — 업로드 API 가 422 로 막는다


def test_source_sheets_follow_workbook_dept():
    content = _wb({
        "T01_영업점_현황": [["BASE_YM", "기준년월", "Y", "CHAR(6)", "식별", None, None, "202608"], ["BRC", "사무소코드", "Y", "CHAR(6)", None, None, None, "001068"]],
        "S01_기업여신_원천": [["BRWR_NO", "차주번호", "Y", "VARCHAR(40)", "Oblg_grd_def", "brwr_no", None, None]],
        "S99_문서근거_메타데이터": [["DOC_ID", "문서식별자", "Y", "VARCHAR(40)", None, None, None, None]],
        "정의기준_확인사항": [["구분", "정의"]],
    })
    t = {x["table_code"]: x for x in parse_workbook(content, {"영업점": "branch"})}
    assert set(t) == {"BRANCH_T01", "BRANCH_S01", "BRANCH_S99"}
    assert t["BRANCH_S01"]["dept"] == "영업점" and t["BRANCH_S01"]["name"] == "기업여신_원천" and t["BRANCH_S01"]["kind"] == "source"
    assert t["BRANCH_T01"]["kind"] == "screen" and [c["is_pk"] for c in t["BRANCH_T01"]["columns"]] == [True, True]


def test_report_section_text_includes_kv_blocks():
    from types import SimpleNamespace

    from nhdip.contracts.materialize import resolve_binding

    rep = {"title": "서민금융", "figures": {"x": {"value": 3, "unit": "CNT", "decimals": 0}}, "sections": [{"id": "s1", "blocks": [{"type": "kv", "kv": [{"label": "권고", "value": "[[fig:x]]"}]}]}]}
    c = SimpleNamespace(binding={"report": "report.a", "section": "s1"})
    assert resolve_binding(None, c, {"report.a": rep})["value"] == "권고: 3건."
    c = SimpleNamespace(binding={"report": "report.a", "field": "title"})
    assert resolve_binding(None, c, {"report.a": rep})["value"] == "서민금융"


def test_dept_default_bindings_are_valid_kinds():
    from nhdip.api.admin_data import BINDING_KINDS
    from nhdip.seed.defs_dept_contracts import BINDING_UPGRADES, BINDINGS, ROW_BUILDERS, WORKFLOW_TABLES
    from nhdip.contracts.rows import ROW_BUILDERS as IMPLS

    assert all(any(k in b for k in BINDING_KINDS) for b in BINDINGS.values())
    assert all(v["builder"] in IMPLS for v in ROW_BUILDERS.values())
    assert set(ROW_BUILDERS) <= {t for ts in WORKFLOW_TABLES.values() for t in ts}
    assert all(k in BINDINGS for k in BINDING_UPGRADES)


def test_rows_version_multi_row_proposal():
    """B.46 — 다행 표 제안 버전: 처음 1, 행 집합이 같으면(순서 · 소수 표기 무관) 유지, 값이 바뀌거나 행이 늘면 +1. 서술 등 비교 제외 열은 무시."""
    from decimal import Decimal

    from nhdip.contracts.materialize import rows_version

    cols = ["base_ym", "brc", "grade_cd", "brc_borrower_cnt", "brc_exposure_amt"]
    a = [{"base_ym": "202608", "brc": "001068", "grade_cd": "2A", "brc_borrower_cnt": 3, "brc_exposure_amt": Decimal("1500.000000"), "agent_summary": "문장 A", "proposal_ver_no": 2},
         {"base_ym": "202608", "brc": "001068", "grade_cd": "3B", "brc_borrower_cnt": 1, "brc_exposure_amt": Decimal("200"), "agent_summary": "문장 A", "proposal_ver_no": 2}]
    same = [{**a[1], "brc_exposure_amt": Decimal("200.00"), "agent_summary": "문장 B", "proposal_ver_no": None},
            {**a[0], "brc_exposure_amt": Decimal("1500"), "agent_summary": "문장 B", "proposal_ver_no": None}]
    assert rows_version([], same, cols, "proposal_ver_no") == 1  # 이전 적재 없음
    assert rows_version([{**r, "proposal_ver_no": None} for r in a], same, cols, "proposal_ver_no") == 1  # 이전 적재에 버전이 비어 있음(기존 DB)
    assert rows_version(a, same, cols, "proposal_ver_no") == 2  # 수치 같음 → 유지 (서술 변경 · 행 순서 · 소수 표기 무시)
    changed = [same[0], {**same[1], "brc_borrower_cnt": 4}]
    assert rows_version(a, changed, cols, "proposal_ver_no") == 3
    assert rows_version(a, [*same, {**same[0], "grade_cd": "4A"}], cols, "proposal_ver_no") == 3  # 행 추가
