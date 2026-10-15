"""Phase I 단위 시험 — 판정 · 증가율 적용 수식, 기간 토큰, 머리글 자동 탐지 · 주석 건너뜀, 문서 메타, 서식 문구, 저장소 사본 비교. DB 불필요."""
from __future__ import annotations

import io
from decimal import Decimal
from types import SimpleNamespace

import pytest

from nhdip.calc import FormulaError, execute


# ── 수식 (계산 커널 커버리지 게이트) ──
def test_verdict_picks_worst_severity_and_label():
    r = execute("VERDICT", {"sev_a": "info", "sev_b": "caution", "sev_c": "watch", "labels": {"caution": "주의", "info": "양호"}})
    assert r.value == Decimal(2) and r.extra["verdict"] == "주의" and r.extra["severity"] == "caution"
    r = execute("VERDICT", {"sev_a": "watch"})
    assert r.extra["verdict"] == "watch"  # 문구가 없으면 심각도 코드 그대로


@pytest.mark.parametrize("inputs", [{"sev_a": "bad"}, {"sev_a": None}])
def test_verdict_errors(inputs):
    with pytest.raises(FormulaError):
        execute("VERDICT", inputs)


def test_growth_apply():
    assert execute("GROWTH_APPLY", {"base": 200, "rate": 5}).value == Decimal(210)
    assert execute("GROWTH_APPLY", {"base": "1,000", "rate": -2.5}).value == Decimal("975.0")


# ── 기간 토큰 ──
def test_prev_year_end_token():
    from nhdip.calc.metrics import ResolveError, resolve_token

    rows = [{"ym": "202512"}, {"ym": "202607"}, {"ym": "202608"}]
    assert resolve_token(rows, "ym", "$prev_year_end") == "202512"
    assert resolve_token(rows, "ym", "$latest") == "202608"
    assert resolve_token(rows, "ym", "$latest-12") == "202508"
    assert resolve_token(rows, "ym", "$earliest") == "202512"
    days = [{"d": "2026-03-31"}, {"d": "2026-08-31"}]
    assert resolve_token(days, "d", "$prev_year_end") == "2025-12-31"
    assert resolve_token(rows, "ym", "plain") == "plain" and resolve_token(rows, "ym", 7) == 7
    with pytest.raises(ResolveError):
        resolve_token([], "ym", "$latest")


# ── 일반 표 파서: 머리글 자동 탐지 · 주석 건너뜀 (RD-09) ──
def test_read_table_csv_detects_header_and_skips_notes():
    from nhdip.data.datasets import _read_table

    text = "부서별 잔액 현황,,\n기준: 2026.08 · 단위: 백만원,,\n,,\n기준년월,계정코드,잔액\n202608,A1,\"1,234\"\n202608,A2,50\n,,\n※ 시연용 가상 자료,,\n"
    rows = _read_table(text.encode("utf-8"), "x.csv", {}, {"기준년월", "계정코드", "잔액"})
    assert rows == [{"기준년월": "202608", "계정코드": "A1", "잔액": "1,234"}, {"기준년월": "202608", "계정코드": "A2", "잔액": "50"}]
    # 후보가 없으면 첫 줄이 머리글(이전 동작)
    assert list(_read_table(b"a,b\n1,2\n", "y.csv", {}, None)[0]) == ["a", "b"]


def test_read_table_xlsx_detects_header():
    import openpyxl

    from nhdip.data.datasets import _read_table

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["상품부문별 손익"])
    ws.append(["기준: 2026.08"])
    ws.append([])
    ws.append(["기준년월", "상품코드", "금액"])
    ws.append(["202608", "P1", 10])
    ws.append(["주) 단위 백만원"])
    buf = io.BytesIO()
    wb.save(buf)
    rows = _read_table(buf.getvalue(), "z.xlsx", {}, {"기준년월", "상품코드", "금액"})
    assert rows == [{"기준년월": "202608", "상품코드": "P1", "금액": 10}]


def test_header_candidates_normalized():
    from nhdip.data.datasets import _norm, header_candidates

    ds = SimpleNamespace(columns=[{"name": "ym", "label": "기준 년월", "aliases": ["STD_YM"]}, {"name": "amt"}])
    c = header_candidates(ds)
    assert {_norm("ym"), _norm("기준 년월"), _norm("STD_YM"), _norm("amt")} <= c


# ── 문서 메타(RD-08) ──
def test_clean_doc_meta():
    from nhdip.data.documents import DocumentError, clean_doc_meta

    m = clean_doc_meta({"accessClass": "internal", "tags": [" 포용금융 ", ""], "isOfficial": False, "pageCount": 12, "unknown": "x"}, "ext")
    assert m["accessClass"] == "internal" and m["tags"] == ["포용금융"] and m["isOfficial"] is False and m["pageCount"] == 12 and "unknown" not in m
    assert clean_doc_meta(None, "bank") == {"docType": "업로드 문서", "isOfficial": False}
    for bad in ({"tags": "x"}, {"isOfficial": "yes"}, {"pageCount": 0}, {"pageCount": True}):
        with pytest.raises(DocumentError):
            clean_doc_meta(bad, "ext")
    with pytest.raises(DocumentError):
        clean_doc_meta(["x"], "ext")  # type: ignore[arg-type]


# ── 서식 문구(Tpl) ──
def test_render_text_figure_modes():
    from nhdip.views.template import DASH, render_text

    idx = {
        "g": {"id": "g", "value": 1.234, "unit": "PCT", "decimals": 2, "verdict": "주의", "severity": "caution"},
        "n": {"id": "n", "value": -3.5, "unit": "PP", "decimals": 1},
        "none": {"id": "none", "value": None, "unit": "PCT"},
    }
    units = {"PCT": "%", "PP": "%p"}
    assert render_text("증가율 [[fig:g]]", idx, units=units) == "증가율 1.23%"
    assert render_text("[[fig:g|signed]] · [[fig:g|num]] · [[fig:g|verdict]] · [[fig:g|severity]] · [[fig:g|unit]]", idx, units=units) == "+1.23% · 1.23 · 주의 · caution · %"
    assert render_text("[[fig:n|abs]] [[fig:n|signed]]", idx, units=units) == "3.5%p -3.5%p"
    assert render_text("[[fig:none]] [[fig:missing]]", idx, units=units) == f"{DASH} {DASH}"
    # 문맥(ctx)이 없으면 기간 · 규칙 표식은 대시
    assert render_text("[[ym:LOAN_BALANCE_MONTHLY|kor]] [[rule:X.a|d1]]", idx, units=units) == f"{DASH} {DASH}"


def test_fmt_period_modes():
    from nhdip.views.template import DASH, fmt_period

    assert fmt_period("202608", None) == "2026.08"
    assert fmt_period("2026-08-31", "kor") == "2026년 8월"
    assert fmt_period("202608", "month") == "8월" and fmt_period("202608", "year") == "2026" and fmt_period("2026-08", "ym") == "202608"
    assert fmt_period("202602", "date") == "2026.02.28"
    assert fmt_period("", None) == DASH


# ── 저장소 사본 비교 ──
def test_compare_dir_detects_missing_and_changed(tmp_path):
    import json

    from nhdip.sample.build import Package, SampleFile
    from nhdip.sample.check import compare_dir

    pkg = Package(files=[SampleFile("a.csv", "dataset", b"x,y\n1,2\n", "DS_A")], ym="202608")
    assert compare_dir(pkg, str(tmp_path)) == [f"manifest.json 없음: {tmp_path}"]
    (tmp_path / "datasets").mkdir()
    (tmp_path / "manifest.json").write_text(json.dumps({"files": [{"name": "a.csv"}, {"name": "b.csv"}]}), encoding="utf-8")
    (tmp_path / "datasets" / "a.csv").write_bytes(b"x,y\n1,3\n")
    diffs = compare_dir(pkg, str(tmp_path))
    assert "사본에만 있음: b.csv" in diffs and "내용 다름: a.csv" in diffs
    (tmp_path / "datasets" / "a.csv").write_bytes(b"x,y\n1,2\n")
    assert compare_dir(pkg, str(tmp_path)) == ["사본에만 있음: b.csv"]


def test_no_sample_data_in_repository_or_startup():
    """저장소 · 기동에 시연 자료가 없다 (M.20 · Q206) — 자료 사본 폴더, 기동 자동 업로드(LOAD_SAMPLE_ON_START), CLI load-sample 이 없다."""
    import os

    root = os.path.join(os.path.dirname(__file__), "..", "..", "..")
    assert not os.path.isdir(os.path.join(root, "sample-data"))
    with open(os.path.join(os.path.dirname(__file__), "..", "docker-entrypoint.sh"), encoding="utf-8") as fh:
        entry = fh.read()
    assert "load-sample" not in entry and 'LOAD_SAMPLE_ON_START:-' not in entry
    compose = os.path.join(root, "docker-compose.yml")
    if os.path.exists(compose):
        with open(compose, encoding="utf-8") as fh:
            assert "LOAD_SAMPLE_ON_START: ${" not in fh.read()
    from nhdip.cli import main

    with pytest.raises(SystemExit):
        main(["load-sample"])  # 없는 명령


def test_sample_upload_cli_refuses_outside_tests(monkeypatch, capsys):
    """시연 자료를 DB 에 올리는 명령은 시험 스택(NHDIP_SAMPLE_UPLOAD=1)에서만 돈다."""
    from nhdip.sample.__main__ import main

    monkeypatch.delenv("NHDIP_SAMPLE_UPLOAD", raising=False)
    assert main(["upload", "--base-url", "http://127.0.0.1:9"]) == 2
    assert main(["selftest"]) == 2
    assert "시험 환경 전용" in capsys.readouterr().err
