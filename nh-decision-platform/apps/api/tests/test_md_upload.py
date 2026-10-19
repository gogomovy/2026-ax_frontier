"""마크다운(.md) 표 업로드 (Phase Q · MD-01~06) — DRM 엑셀을 .md 로 바꿔 올린 파일이 정형 자료로 들어가는지."""
from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

ADMIN = ("00000001", "Admin1234!")

# 엑셀 → md 변환기(markitdown 계열) 모양 — 시트 제목 · 제목 줄이 머리글로 잡힌 표 · NaN · Unnamed · 굵게 · 쉼표 숫자 · 이스케이프된 |
MD = """# 마크다운시험 상품 잔액

기준일: 2026-08-31 (단위: 백만원)

## 요약
| 구분 | 값 |
|---|---|
| 상품 수 | 3 |

## 상품잔액
| 마크다운시험 상품 잔액 현황 | Unnamed: 1 | Unnamed: 2 |
|---|---|---|
| 기준월 | 상품명 | 마크다운시험잔액 |
| 202608 | **가계 \\| 신용** | 1,234 |
| 202608 | 기업&nbsp;운전 | 5,678.5 |
| 202608 | 기타 | NaN |
| ※ 출처: 여신부 | | |
"""


def _client() -> TestClient:
    from nhdip.main import app

    return TestClient(app)


def _login(c: TestClient, emp: str, pw: str) -> None:
    from nhdip import ratelimit

    ratelimit.reset()
    assert c.post("/auth/login", json={"emp_no": emp, "password": pw}).status_code == 200


def test_md_tables_and_cells():
    from nhdip.data.mdtable import decode, is_md_table, tables

    ts = tables(MD)
    assert [t.title for t in ts] == ["요약", "상품잔액"]
    t = ts[1]
    assert t.rows[0] == ["마크다운시험 상품 잔액 현황", "", ""]  # Unnamed → 빈 머리글
    assert t.rows[2] == ["202608", "가계 | 신용", "1,234"]  # 굵게 · 이스케이프된 | 정리
    assert t.rows[3][1] == "기업 운전" and t.rows[4][2] == ""  # &nbsp; · NaN
    assert is_md_table(MD.encode("utf-8")) and not is_md_table("# 제목\n\n본문만 있는 글".encode("utf-8"))
    assert not is_md_table(b"| a | b |\n|---|---|\n")  # 데이터 행 없음
    assert decode(MD.encode("cp949")) == MD  # 내부망 변환기 CP949
    # 자료 등록 도우미(정형/비정형 판별) — 표가 든 .md 는 정형, 글만 있으면 문서
    from nhdip.data.onboarding import is_structured

    assert is_structured("a.md", MD.encode("utf-8")) and not is_structured("b.md", "글만".encode("utf-8")) and not is_structured("c.md")


def test_md_filecheck_and_infer():
    from nhdip.data.filecheck import UploadRejected, check_upload
    from nhdip.data.infer import infer_definition

    assert check_upload("상품잔액_202608.md", MD.encode("cp949"), "dataset") == "상품잔액_202608.md"
    assert check_upload("메모.md", "본문".encode("utf-8"), "document") == "메모.md"
    with pytest.raises(UploadRejected):
        check_upload("x.md", b"\x00\x01binary", "dataset")
    d = infer_definition(MD.encode("utf-8"), "마크다운시험_상품잔액_202608.md")
    labels = [c["label"] for c in d["columns"]]
    # 큰 표(상품잔액)를 고르고, 제목 줄 아래 실제 머리글 줄을 찾는다 — 다음 달 파일도 같은 표 · 같은 줄
    assert labels == ["기준월", "상품명", "마크다운시험잔액"], labels
    assert d["parser"].get("sheet") == "상품잔액" and d["parser"].get("header_row") == 2, d["parser"]
    assert d["as_of_column"] == next(c["name"] for c in d["columns"] if c["label"] == "기준월")
    with pytest.raises(Exception):
        infer_definition("# 표 없음\n\n글만".encode("utf-8"), "글.md")


def test_md_upload_same_as_csv(db):
    """같은 자료를 .md 로 올리면 .csv 로 올린 것과 같은 행이 된다(새 정의 자동 · 같은 자료의 다음 판 · 숫자 변환)."""
    from nhdip.data.datasets import current_rows
    from nhdip.models import Dataset

    admin = _client()
    _login(admin, *ADMIN)
    form = {"origin": "bank", "data_origin": "simulated"}
    r = admin.post("/admin/datasets/auto-upload", data=form, files={"file": ("마크다운시험_상품잔액_202608.md", io.BytesIO(MD.encode("cp949")), "text/markdown")})
    assert r.status_code == 201, r.text
    code = r.json()["dataset"]
    with db() as s:
        ds = s.get(Dataset, code)
        _, rows = current_rows(s, ds)
        names = {c["label"]: c["name"] for c in ds.columns}
        got = sorted((r[names["상품명"]], r[names["마크다운시험잔액"]]) for r in rows)
    assert got == [("가계 | 신용", 1234), ("기업 운전", 5678.5), ("기타", None)], got  # 주석 줄(※ 출처)은 행이 아니다
    # 다음 달 — 같은 파일 이름 규칙 · 같은 표(여러 표 중 상품잔액) → 같은 자료의 새 판(기준월이 달라 함께 보관)
    nxt = MD.replace("202608", "202609").replace("1,234", "2,000")
    r2 = admin.post("/admin/datasets/auto-upload", data=form, files={"file": ("마크다운시험_상품잔액_202609.md", io.BytesIO(nxt.encode("utf-8")), "text/markdown")})
    assert r2.status_code == 201 and r2.json()["dataset"] == code, r2.text
    # 같은 내용의 CSV 와 같은 행
    csv = "기준월,상품명,마크다운시험잔액\n202609,가계 | 신용,\"2,000\"\n202609,기업 운전,5678.5\n202609,기타,\n"
    from nhdip.data.datasets import preview_file

    with db() as s:
        ds = s.get(Dataset, code)
        a = preview_file(ds, "x.csv", csv.encode("utf-8"), s)["rows"]
        b = preview_file(ds, "x.md", nxt.encode("utf-8"), s)["rows"]
        assert a == b, (a, b)
        _, rows = current_rows(s, ds)
        assert len(rows) == 6
    # 표가 없는 .md 를 정형 자료로 올리면 이유를 알려 준다
    bad = admin.post(f"/admin/datasets/{code}/upload", data=form, files={"file": ("글.md", io.BytesIO("# 표 없음\n\n글만".encode("utf-8")), "text/markdown")})
    assert bad.status_code == 422 and "표를 찾지 못했습니다" in bad.text, bad.text
