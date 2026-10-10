"""원본 보고서 어댑터 (1.3.2 ~ 1.3.6) — 2020 · 2633 · 7790 양식을 사진 속 원본 배치대로 만든 픽스처로 검증. DB 불필요."""
from __future__ import annotations

import io

import pytest
from openpyxl import Workbook
from openpyxl.styles import Alignment

from nhdip.data.adapters import AdapterError, detect, load_sheets, parse_report
from nhdip.seed.defs_data import PARSERS


def _xlsx(build) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    build(ws)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _put(ws, r, c, v, indent=0):
    cell = ws.cell(row=r, column=c, value=v)
    if indent:
        cell.alignment = Alignment(indent=indent)


def wb_2020(year="2026", months=8, header_ym="2026-08-31"):
    def build(ws):
        ws["A1"] = "2020 과목별 월별 여신현황"
        ws["A2"] = "조회일자 : 2026-09-15 18:18:23"
        ws["A3"] = "조회사무소 : 00561(신용리스크관리부)"
        ws["A4"] = "조회자 : 99999999(홍길동)"  # 개인 정보 — 저장하지 않아야 함
        ws["A5"] = "조회구분 : [전국], 사무소 : [], 과목 : [여신대분류], 유형 : []"
        ws["A6"] = f"기 준 일 : [{header_ym}], 사무소명 : [], 구분 : [계리잔액], 조건 : [], 단위:명,좌, [1,000,000] 원"
        ws["A8"] = "담당부서 : 여신관리부 홍길동"
        ws["A10"] = "과목구분"
        for m in range(1, months + 1):
            ws.cell(row=10, column=1 + m, value=f"{m}월")
        tree = [
            ("대출금", 0, 214580000),
            ("기업자금대출금", 1, 115340000),
            ("금융운전자금대출금", 2, 70000000),
            ("가계자금대출금", 1, 99240000),
            ("가계일반자금대출", 2, 20000000),
            ("  주택자금대출", 2, 62480000),  # 앞 공백 들여쓰기 + 셀 들여쓰기 혼용
            ("기타가계자금대출", 2, 12340000),
            ("공공및기타자금대출금", 1, 18620000),
            ("지급보증", 0, 5000),
            ("종합계", 0, 230000000),
        ]
        for i, (name, ind, aug) in enumerate(tree):
            r = 11 + i
            _put(ws, r, 1, name, ind if not name.startswith(" ") else 1)
            for m in range(1, months + 1):
                ws.cell(row=r, column=1 + m, value=round(aug * (0.99 + m * 0.00125)) if m < months else aug)

    return _xlsx(build)


def test_2020_layout_meta_tree_units_and_lineage():
    content = wb_2020()
    sheets = load_sheets(content)
    a, score = detect(sheets, "(202608)2020 과목별 월별 여신현황.xlsx")
    assert a.code == "report_2020" and score >= 70
    p = parse_report(content, "(202608)2020 과목별 월별 여신현황.xlsx", "LOAN_BALANCE_MONTHLY", PARSERS["LOAN_BALANCE_MONTHLY"])
    aug = {r["account_code"]: r for r in p.rows if r["ym"] == "202608"}
    assert aug["CORP"]["balance"] == 115340000 and aug["HH"]["balance"] == 99240000 and aug["HOUSE"]["balance"] == 62480000
    assert aug["HH_ETC"]["parent_path"] == "대출금>가계자금대출금" and aug["LOAN_TOTAL"]["balance"] == 214580000
    assert aug["CORP"]["src_ref"] == "Sheet1!I12"  # 8월 열 · 기업자금대출금 행
    assert "PATH:대출금>기업자금대출금>금융운전자금대출금" in aug  # 매핑 없는 과목도 경로 코드로 보존
    assert {r["ym"] for r in p.rows} == {f"2026{m:02d}" for m in range(1, 9)}
    m = p.meta
    assert m["조회사무소"].startswith("00561") and m["구분"] == "계리잔액" and m["base_ym"] == "202608" and m["source_unit_multiplier"] == 1_000_000
    assert "조회자" not in m and "담당부서" not in m and "홍길동" not in str(m)  # DATA-06


def test_2020_only_mapped_accounts_when_keep_unmapped_off():
    p = parse_report(wb_2020(), "(202608)2020.xlsx", "LOAN_BALANCE_MONTHLY", {**PARSERS["LOAN_BALANCE_MONTHLY"], "account_codes": {"대출금>기업자금대출금": "CORP"}, "keep_unmapped": False})
    assert {r["account_code"] for r in p.rows} == {"CORP"}


def wb_2633():
    def build(ws):
        ws["A1"] = "2633 상품부문별 손익계산서"
        ws["A2"] = "(단위: 백만원)"
        ws["A4"], ws["B4"], ws["C4"], ws["D4"] = "항목명", "당월", "7월 누계", "8월 누계"
        items = [
            ("총수익", 0, 4812360), ("이자수익", 1, 3500000), ("대출금이자수익", 2, 2500000), ("원화대출금이자수익", 3, 2100000),
            ("기업자금대출금이자", 4, 1089820), ("가계자금대출금이자", 4, 909960), ("주택자금대출이자", 5, 486000),
            ("여신(일반)부문 이자마진 수익", 0, 2186540), ("기타", 0, None),
        ]
        for i, (name, ind, v) in enumerate(items):
            _put(ws, 5 + i, 1, name, ind)
            ws.cell(row=5 + i, column=2, value=None if v is None else v // 8)
            ws.cell(row=5 + i, column=3, value=None if v is None else round(v * 0.87))
            ws.cell(row=5 + i, column=4, value=v)

    return _xlsx(build)


def test_2633_picks_august_cumulative_and_required_items():
    p = parse_report(wb_2633(), "(202608)2633_상품부문별손익계산서.xlsx", "PL_PRODUCT_SEGMENT", PARSERS["PL_PRODUCT_SEGMENT"])
    by = {r["item_code"]: r for r in p.rows}
    assert by["TOTAL_REVENUE"]["amount"] == 4812360 and by["LOAN_NIM"]["amount"] == 2186540
    assert by["CORP_INTEREST"]["amount"] == 1089820 and by["CORP_INTEREST"]["src_ref"] == "Sheet1!D9"
    assert by["HH_INTEREST"]["parent_path"].endswith("원화대출금이자수익") and by["HOUSE_INTEREST"]["amount"] == 486000
    assert p.meta["amount_column"] == "8월 누계" and all(r["ym"] == "202608" for r in p.rows)
    with pytest.raises(AdapterError, match="필수 항목"):
        parse_report(wb_2633(), "(202608)2633.xlsx", "PL_PRODUCT_SEGMENT", {**PARSERS["PL_PRODUCT_SEGMENT"], "item_codes": {"총수익": "TOTAL_REVENUE"}})


def wb_7790(with_header=True):
    def build(ws):
        ws["A1"] = "7790 상품별 충당금 산출현황 요약"
        ws["A2"] = "기준년월 : [2026.08]"
        ws["A4"], ws["B4"], ws["C4"] = "상품코드", "상품명", "차주수"
        ws.merge_cells("D4:F4")
        ws["D4"] = "손실충당금"
        ws["D5"], ws["E5"], ws["F5"] = "대출채권", "미수이자", "가지급금"
        ws["X4"] = "손실충당금 및 충당부채 총계" if with_header else "기타"
        rows = [("2001107820007", "(개인)햇살론", 10, 1200.5), ("2001108220001", "(개인)새희망홀씨", 8, 800), ("", "", None, None), ("합계", "", 18, 3412180)]
        for i, (code, name, n, total) in enumerate(rows):
            r = 6 + i
            ws.cell(row=r, column=1, value=code or None)
            ws.cell(row=r, column=2, value=name or None)
            ws.cell(row=r, column=3, value=n)
            ws.cell(row=r, column=24, value=total)

    return _xlsx(build)


def test_7790_total_header_total_row_and_fallback_column():
    p = parse_report(wb_7790(), "(202608)7790_상품별_충당금.xlsx", "PROVISION_BY_PRODUCT", PARSERS["PROVISION_BY_PRODUCT"])
    assert [(r["product_code"], r["provision"], r["is_total"]) for r in p.rows] == [("2001107820007", 1200.5, False), ("2001108220001", 800, False), ("TOTAL", 3412180, True)]
    assert p.rows[-1]["src_ref"] == "Sheet1!X9" and not p.notes
    q = parse_report(wb_7790(with_header=False), "(202608)7790.xlsx", "PROVISION_BY_PRODUCT", PARSERS["PROVISION_BY_PRODUCT"])
    assert q.rows[-1]["provision"] == 3412180 and "열 위치(X)" in q.notes[0]


def test_detection_wrong_dataset_and_tidy_fallback():
    with pytest.raises(AdapterError, match="LOAN_BALANCE_MONTHLY"):
        parse_report(wb_2020(), "(202608)2020.xlsx", "PROVISION_BY_PRODUCT", {})

    def tidy(ws):
        ws.append(["ym", "account_code", "account_name", "balance"])
        ws.append(["202608", "CORP", "기업자금대출금", 115340000])

    assert parse_report(_xlsx(tidy), "(202608)2020 정리본.xlsx", "LOAN_BALANCE_MONTHLY", PARSERS["LOAN_BALANCE_MONTHLY"]) is None  # 정리된 표 → 일반 파서
    assert parse_report(wb_2020(), "x.xlsx", "LOAN_BALANCE_MONTHLY", {"adapter": "none"}) is None


def test_hwpx_document_text_and_upload_check():
    from hwpx import HwpxDocument

    from nhdip.data.documents import extract_text
    from nhdip.data.filecheck import UploadRejected, check_upload

    d = HwpxDocument.new()
    d.add_heading("포용금융 확대방안", level=1)
    d.add_paragraph("1. 추진 방향")
    d.add_paragraph("서민 대출 공급 목표를 상향한다.")
    for fmt, name in (("hwpx", "정책.hwpx"), ("hwp", "정책.hwp")):
        data = d.to_bytes(format=fmt)
        assert check_upload(name, data, "document") == name
        text, pages = extract_text(name, data)
        assert "서민 대출 공급 목표를 상향한다." in text and pages[0][0] == 1
    with pytest.raises(UploadRejected, match="HWPX"):
        check_upload("가짜.hwpx", b"%PDF-1.4", "document")
    with pytest.raises(UploadRejected, match="HWP"):
        check_upload("가짜.hwp", b"PK\x03\x04", "document")
