"""파일에서 데이터셋 정의 추론 (Phase J 후속 · DEF-01~05 · Q160~Q163) — DB 없는 단위 시험."""
from __future__ import annotations

import io

import pytest

from nhdip.data.infer import InferError, infer_definition, infer_new_columns, merge_columns, suggest_code, validate_definition


def _csv(header: str, rows: list[str]) -> bytes:
    return (header + "\n" + "\n".join(rows) + "\n").encode("utf-8")


PRODUCTS = [("A01", "새희망홀씨"), ("B02", "햇살론"), ("C03", "사잇돌")]
MONTHLY = _csv(
    "기준월,상품코드,상품명,잔액,부도율,등록일",
    [f"2026{m:02d},{p},{n},{1000 * i + m},{0.1 * i:.2f},2026-{m:02d}-01" for m in (6, 7, 8) for i, (p, n) in enumerate(PRODUCTS, start=1)],
)


def _by_label(d: dict) -> dict[str, dict]:
    return {c["label"]: c for c in d["columns"]}


def test_infer_types_keys_and_as_of():
    d = infer_definition(MONTHLY, "대출현황_202608.csv")
    cols = _by_label(d)
    assert [c["label"] for c in d["columns"]] == ["기준월", "상품코드", "상품명", "잔액", "부도율", "등록일"]
    assert cols["기준월"]["type"] == "str"  # YYYYMM 은 날짜가 아니라 연월 글자(기준일 열 후보)
    assert cols["상품코드"]["type"] == "str" and cols["상품명"]["type"] == "str"
    assert cols["잔액"]["type"] == "int" and cols["부도율"]["type"] == "num" and cols["등록일"]["type"] == "date"
    assert d["as_of_column"] == cols["기준월"]["name"]
    assert d["key_columns"] == [cols["기준월"]["name"], cols["상품코드"]["name"]]  # 행을 구분하는 가장 작은 조합 — 측정값은 키에서 뺀다
    # 키 · 기준일 열만 필수 — 나머지는 비어 있거나 빠져도 올라온다
    assert {c["label"] for c in d["columns"] if c["required"]} == {"기준월", "상품코드"}
    assert d["rows"] == 9 and d["origin"] == "bank" and d["parser"] == {}
    assert d["notes"] == []  # 문자 열마다 '숫자로 보이지만…' 안내가 잘못 붙지 않는다
    assert d["file_pattern"] and "\\d+" in d["file_pattern"]
    assert validate_definition(d) == []
    # 열별 예시값(검토용)
    assert d["samples"][cols["상품코드"]["name"]] == ["A01", "B02", "C03"]


def test_infer_skips_title_rows_and_records_parser():
    body = "대출 현황 보고서\n단위: 백만원\n기준월,항목,금액\n202606,가,1\n202606,나,2\n202607,가,3\n202607,나,4\n".encode("utf-8")
    d = infer_definition(body, "report.csv")
    assert d["parser"] == {"skip_rows": 2}  # 다음에 올리는 같은 모양 파일도 같게 읽는다
    assert [c["label"] for c in d["columns"]] == ["기준월", "항목", "금액"]
    assert d["as_of_column"] and d["key_columns"]


def test_infer_keeps_codes_with_leading_zero_as_text_and_mixed_numbers_as_text():
    d = infer_definition(_csv("코드,금액,비고", ["001,1000,가", "002,2000,나", "003,abc,다"]), "m.csv")
    cols = _by_label(d)
    assert cols["코드"]["type"] == "str"  # 앞자리 0 이 사라지면 안 된다
    assert cols["금액"]["type"] == "str" and any("금액" in n and "문자로" in n for n in d["notes"])  # 한 값이라도 다르면 올릴 때 막히지 않게 문자


def test_infer_reports_when_no_key_found():
    d = infer_definition(_csv("구분,값", ["가,x", "가,x", "나,x"]), "dup.csv")  # 어떤 열 조합으로도 행이 구분되지 않는다
    assert d["key_columns"] == [] and any("키" in n for n in d["notes"])
    # 한 열만으로 구분되면 그 열이 키
    assert infer_definition(_csv("구분,값", ["가,x", "나,y", "다,z"]), "uniq.csv")["key_columns"] == ["구분"]


def test_infer_empty_and_bad_inputs():
    with pytest.raises(InferError):
        infer_definition(b"", "e.csv")
    with pytest.raises(InferError):
        infer_definition(MONTHLY, "x.csv", origin="zzz")


def _report_files() -> dict[str, bytes]:
    """업무 보고서 양식 3종(다단 머리글 · 들여쓰기 계층 · 월 열) — 시연 자료 생성기와 같은 모양."""
    from nhdip.sample import excel as X

    tree = [("대출금", 0, [100.0, 110.0, 120.0]), ("기업자금대출금", 1, [60.0, 65.0, 70.0]), ("가계자금대출금", 1, [40.0, 45.0, 50.0]), ("종합계", 0, [100.0, 110.0, 120.0])]
    items = [("총수익", 0, 4800.0, 4600.0), ("이자수익", 1, 2800.0, None), ("대출금이자수익", 2, 2200.0, None), ("여신(일반)부문 이자마진 수익", 0, 2100.0, 2000.0)]
    prods = [{"code": "2001101010001", "name": "주택담보대출", "borrowers": 120, "provision": 105.0}, {"code": "2001109670002", "name": "햇살론", "borrowers": 40, "provision": 29.0}]
    return {
        "(202603)2020 과목별 월별 여신현황.xlsx": X.report_2020(2026, 3, tree, base_date="2026-03-31"),
        "(202608)2633_상품부문별손익계산서.xlsx": X.report_2633("202608", items),
        "(202608)7790_상품별_충당금.xlsx": X.report_7790("202608", prods, 134.0),
    }


def test_infer_report_forms_build_structure_from_the_file():
    """정해 둔 양식 · 데이터셋 코드 없이 — 보고서 양식 파일도 파일 모양에서 구조를 만든다(M.25 · DOB-19).
    예전에는 '원본 보고서 양식입니다 — 기존 데이터셋 LOAN_BALANCE_MONTHLY 에 올려 주세요' 로 막혔다."""
    f = _report_files()
    d20 = infer_definition(f["(202603)2020 과목별 월별 여신현황.xlsx"], "(202603)2020 과목별 월별 여신현황.xlsx")
    c20 = _by_label(d20)
    assert d20["parser"] == {"layout": "report"} and set(c20) == {"기준년월", "과목구분", "상위 항목", "수준", "계리잔액"}
    assert d20["as_of_column"] == c20["기준년월"]["name"] and c20["계리잔액"]["type"] in ("num", "int")
    assert d20["code"].startswith("DS_") and "LOAN_BALANCE" not in d20["code"] and any("보고서 양식" in n for n in d20["notes"])
    d33 = infer_definition(f["(202608)2633_상품부문별손익계산서.xlsx"], "(202608)2633_상품부문별손익계산서.xlsx")
    c33 = _by_label(d33)
    assert {"기준년월", "항목명", "상위 항목", "기준월 누계"} <= set(c33) and "8월 누계" not in c33  # 달마다 열 이름이 바뀌지 않게
    d79 = infer_definition(f["(202608)7790_상품별_충당금.xlsx"], "(202608)7790_상품별_충당금.xlsx")
    c79 = _by_label(d79)
    assert {"상품코드", "손실충당금 대출채권", "손실충당금 및 충당부채 총계", "합계 행"} <= set(c79)  # 다단 머리글을 합친 열 이름
    assert c79["상품코드"]["type"] == "str"  # 숫자로 된 코드는 코드(글자)로


def test_report_form_rows_store_through_generic_reader():
    """만든 정의로 같은 파일을 읽으면 행이 그대로 들어간다 — 원본 양식 어댑터(정해 둔 열)를 쓰지 않는다."""
    from types import SimpleNamespace

    from nhdip.data.datasets import _read_any, map_rows

    name, content = next(iter(_report_files().items()))
    d = infer_definition(content, name)
    ds = SimpleNamespace(**{**d, "mapping": {}})
    raw, src = _read_any(content, name, ds)
    rows, errors = map_rows(ds, raw)
    assert src["layout"] == "report" and not errors and len(rows) == 12  # 과목 4개 × 3개월
    by = {(r[_by_label(d)["기준년월"]["name"]], r[_by_label(d)["과목구분"]["name"]]): r for r in rows}
    assert by[("202602", "기업자금대출금")][_by_label(d)["계리잔액"]["name"]] == 65.0 and by[("202602", "기업자금대출금")][_by_label(d)["상위 항목"]["name"]] == "대출금"


def test_infer_xlsx_header_not_on_first_row():
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["월간 현황"])
    ws.append([])
    ws.append(["지점", "건수", "금액"])
    for i in range(5):
        ws.append([f"지점{i}", i + 1, 1000.5 * (i + 1)])
    buf = io.BytesIO()
    wb.save(buf)
    d = infer_definition(buf.getvalue(), "점포.xlsx")
    assert d["parser"] == {"header_row": 3}
    cols = _by_label(d)
    assert cols["건수"]["type"] == "int" and cols["금액"]["type"] == "num" and cols["지점"]["type"] == "str"
    assert d["key_columns"] == [cols["지점"]["name"]]


def test_infer_masks_pii_in_samples():
    d = infer_definition(_csv("이름,번호", ["가,900101-1234567", "나,900101-2234567"]), "pii.csv")
    shown = " ".join(v for vs in d["samples"].values() for v in vs)
    assert "1234567" not in shown and "2234567" not in shown


def test_suggest_code():
    assert suggest_code("loan_balance_202608.csv") == "LOAN_BALANCE"
    assert suggest_code("대출.csv").startswith("DS_") and suggest_code("대출.csv") == suggest_code("대출.csv")


def test_validate_definition_reports_every_problem():
    bad = {"code": "x", "name": "", "origin": "zz", "columns": [{"name": "a", "type": "str"}, {"name": "A", "type": "xx"}], "key_columns": ["q"], "as_of_column": "w"}
    errs = " | ".join(validate_definition(bad))
    for part in ("코드", "이름", "출처", "겹칩니다", "타입", "키 열", "기준일 열"):
        assert part in errs, part
    assert validate_definition({"code": "OK_1", "name": "n", "origin": "ext", "columns": []})  # 컬럼 없는 정의는 거절
    assert validate_definition({"code": "OK_1", "name": "n", "origin": "ext", "columns": [{"name": "a", "type": "str"}], "key_columns": ["a"], "as_of_column": "a"}) == []


def test_infer_new_columns_only_adds_unknown_columns():
    class DS:  # 기존 데이터셋 — 열 둘
        columns = [{"name": "ym", "label": "기준월", "type": "str", "required": True}, {"name": "item", "label": "항목", "type": "str", "required": True}]

    body = _csv("기준월,항목,신규지표,메모", ["202608,가,1.5,x", "202608,나,2.5,y"])
    r = infer_new_columns(DS, body, "n.csv")
    assert [c["label"] for c in r["newColumns"]] == ["신규지표", "메모"]
    assert {m["column"] for m in r["matched"]} == {"ym", "item"}
    assert all(c["required"] is False for c in r["newColumns"])  # 새 열은 선택 — 기존 업로드가 새로 막히지 않는다
    merged = r["columns"]
    assert [c["name"] for c in merged[:2]] == ["ym", "item"] and len(merged) == 4
    assert merge_columns(merged, r["newColumns"]) == merged  # 두 번 더해도 겹치지 않는다
