"""시험용 원본 보고서 양식 엑셀(2020 과목별 월별 여신현황 모양) — 정해 둔 어댑터 없이 파일 모양에서 읽히는지 시험한다(Phase O)."""
from __future__ import annotations

import io

from openpyxl import Workbook
from openpyxl.styles import Alignment


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
            ("  주택자금대출", 2, 62480000),
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
