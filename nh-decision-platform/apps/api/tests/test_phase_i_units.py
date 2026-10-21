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
    # 전년 동기(202508)가 없으면 최신보다 앞선 가장 가까운 보관 기간(202512 — 4개월 차이)으로 대체 · strict 면 그대로
    assert resolve_token(rows, "ym", "$latest-12") == "202512"
    assert resolve_token(rows, "ym", "$latest-12", fallback=False) == "202508"
    assert resolve_token(rows, "ym", "$earliest") == "202512"
    days = [{"d": "2026-03-31"}, {"d": "2026-08-31"}]
    assert resolve_token(days, "d", "$prev_year_end", fallback=False) == "2025-12-31"
    assert resolve_token(days, "d", "$prev_year_end") == "2026-03-31"  # 전년 말이 없으면 가장 가까운 앞선 기준일(3개월 차이)
    assert resolve_token(rows, "ym", "plain") == "plain" and resolve_token(rows, "ym", 7) == 7
    with pytest.raises(ResolveError):
        resolve_token([], "ym", "$latest")


# ── 보관 기간 기반 토큰 — 올린 기준일이 띄어 있어도 비교가 되게 ──
def test_prev_token_picks_stored_period_not_calendar_month():
    from nhdip.calc.metrics import resolve_token

    # 1월 · 8월만 올린 경우 — 달력상 전월(202607)은 없지만 '직전 보관 기간'은 202601
    jan_aug = [{"ym": "202601"}, {"ym": "202608"}]
    assert resolve_token(jan_aug, "ym", "$latest") == "202608"
    assert resolve_token(jan_aug, "ym", "$prev") == "202601"
    assert resolve_token(jan_aug, "ym", "$prev-1") == "202601"
    # 달 수로 세는 토큰은 그 달이 없으면 가장 가까운 앞선 보관 기간으로 대체한다(설정 calc.period_fallback=nearest) — strict 면 그 달 그대로(값 없음 오류)
    assert resolve_token(jan_aug, "ym", "$latest-1") == "202601"
    assert resolve_token(jan_aug, "ym", "$latest-12") == "202601"
    assert resolve_token(jan_aug, "ym", "$latest-1", fallback=False) == "202607"
    assert resolve_token(jan_aug, "ym", "$latest-12", fallback=False) == "202508"


def test_month_tokens_fall_back_to_nearest_earlier_period_and_report_it():
    from nhdip.calc.metrics import fallback_note, resolve_token_info, token_name

    jan_aug = [{"ym": "202601"}, {"ym": "202608"}]
    assert resolve_token_info(jan_aug, "ym", "$latest-12") == ("202601", "202508")
    # 정확한 달이 있으면 대체가 아니다
    full = [{"ym": "202508"}, {"ym": "202601"}, {"ym": "202608"}]
    assert resolve_token_info(full, "ym", "$latest-12") == ("202508", None)
    # 거리가 같으면 앞선 기간 — 202508 기준 ±2개월(202506 · 202510)
    tie = [{"ym": "202506"}, {"ym": "202510"}, {"ym": "202608"}]
    assert resolve_token_info(tie, "ym", "$latest-12") == ("202506", "202508")
    # 대신할 기간은 최신보다 그 달에 더 가까워야 한다 — 1월 · 8월이면 2년 전(202408) 자리에 1월(최신에서 7개월)은 안 된다
    assert resolve_token_info(jan_aug, "ym", "$latest-24") == ("202408", None)
    assert resolve_token_info([{"ym": "202606"}, {"ym": "202608"}], "ym", "$latest-12") == ("202508", None)
    # 최신 하나뿐이면 자기 자신과 견주지 않는다 — 대체 없이 그 달(값 없음 오류로 '갱신 실패')
    assert resolve_token_info([{"ym": "202608"}], "ym", "$latest-12") == ("202508", None)
    # 전년 말(202512)이 없으면 가장 가까운 앞선 기간
    assert resolve_token_info([{"ym": "202601"}, {"ym": "202608"}], "ym", "$prev_year_end") == ("202601", "202512")
    # 날짜 기준일 — 같은 달의 다른 날(영업일 말일)은 같은 기간
    days = [{"d": "2025-08-29"}, {"d": "2026-08-31"}]
    assert resolve_token_info(days, "d", "$latest-12") == ("2025-08-29", None)
    # 보관 기간 토큰($prev · $nearest-N)은 대체 개념이 없다
    assert resolve_token_info(jan_aug, "ym", "$prev")[1] is None and resolve_token_info(jan_aug, "ym", "$nearest-12")[1] is None
    assert token_name("$latest-12") == "전년 동기" and token_name("$prev_year_end") == "전년 말" and token_name("$latest-3") == "3개월 전"
    assert fallback_note({"token": "$latest-12", "wanted": "202508", "used": "202601"}) == "전년 동기(2025.08) 자료가 없어 가장 가까운 기준일 2026.01 과 비교"


def test_period_basis_relabels_figure_and_restores_when_exact_period_arrives():
    from nhdip.views.period_words import relabel
    from nhdip.views.store import patch_figures
    from nhdip.views.template import render_templates, strip_figure

    yoy = [{"col": "ym", "token": "$latest-12", "wanted": "202508", "used": "202601"}]
    assert relabel("전년 동기 대비 증가율", yoy) == "2026.01 대비 증가율"
    assert relabel("전년동기 잔액", yoy) == "2026.01 잔액"
    assert relabel("전년 말 잔액", yoy) == "전년 말 잔액"  # 대체되지 않은 토큰의 낱말은 그대로
    assert relabel("전년말 대비", [{"token": "$prev_year_end", "used": "202601"}]) == "2026.01 대비"
    assert relabel("2년 전 동기 잔액", [{"token": "$latest-24", "used": "202501"}]) == "2025.01 잔액"
    fig = {"id": "g", "label": "전년 동기 대비 증가율", "unit": "PCT", "value": None}
    art = {"figures": [fig], "statementTpl": "증가율은 전년 동기 대비 [[fig:g]] 입니다", "titleTpl": "전년 동기 대비 [[if:g>0|늘었다|줄었다]]"}
    changes: list = []
    patch_figures(art, {"g": {"value": 3.2, "basis": yoy}}, changes, "a")
    assert fig["label"] == "2026.01 대비 증가율" and fig["labelBase"] == "전년 동기 대비 증가율" and fig["basis"] == yoy
    from nhdip.views.template import figure_index

    render_templates(art, figure_index({"a": art}))
    assert art["statement"] == "증가율은 2026.01 대비 [[fig:g]] 입니다" and art["title"] == "2026.01 대비 늘었다"
    # 정확한 달이 올라와 대체가 풀리면 원래 라벨 · 문구로
    patch_figures(art, {"g": {"value": 2.0, "basis": []}}, changes, "a")
    assert fig["label"] == "전년 동기 대비 증가율" and "labelBase" not in fig and "basis" not in fig
    render_templates(art, figure_index({"a": art}))
    assert art["statement"] == "증가율은 전년 동기 대비 [[fig:g]] 입니다"
    # 화면 틀로 되돌릴 때도 원래 라벨
    f2 = {"id": "h", "label": "2026.01 잔액", "labelBase": "전년 동기 잔액", "unit": "KRW_TN", "value": 1.0, "basis": yoy}
    strip_figure(f2)
    assert f2 == {"id": "h", "label": "전년 동기 잔액", "unit": "KRW_TN", "value": None}


def test_prev_token_steps_back_and_clamps():
    from nhdip.calc.metrics import resolve_token

    rows = [{"ym": "202601"}, {"ym": "202604"}, {"ym": "202608"}]
    assert resolve_token(rows, "ym", "$prev") == "202604"
    assert resolve_token(rows, "ym", "$prev-2") == "202601"
    assert resolve_token(rows, "ym", "$prev-9") == "202601"  # 더 과거가 없으면 가장 이른 기간


def test_prev_token_collapses_to_latest_for_single_period():
    from nhdip.calc.metrics import resolve_token

    # 첫 업로드(기간 하나) — '갱신 실패'로 화면을 덮지 않도록 $latest 와 같게 떨어진다(증감 0)
    one = [{"ym": "202608"}]
    assert resolve_token(one, "ym", "$prev") == "202608" == resolve_token(one, "ym", "$latest")


def test_nearest_token_picks_closest_stored_period():
    from nhdip.calc.metrics import ResolveError, resolve_token

    rows = [{"ym": "202502"}, {"ym": "202510"}, {"ym": "202601"}, {"ym": "202608"}]
    # 12개월 전 = 202508 → 그 달은 없고 그보다 이전 중 가장 늦은 202502
    assert resolve_token(rows, "ym", "$nearest-12") == "202502"
    assert resolve_token(rows, "ym", "$nearest-10") == "202510"  # 목표와 정확히 같은 기간이 있으면 그것
    assert resolve_token(rows, "ym", "$nearest-0") == "202608"
    # 목표가 보관 기간보다 더 과거면 가장 가까운 기간
    assert resolve_token(rows, "ym", "$nearest-120") == "202502"
    assert resolve_token([{"d": "2026-01-31"}, {"d": "2026-08-31"}], "d", "$nearest-7") == "2026-01-31"
    with pytest.raises(ResolveError):  # 개월 수가 없으면 뜻이 정해지지 않는다
        resolve_token(rows, "ym", "$nearest")


def test_resolve_period_uses_anchor_dataset():
    from nhdip.calc.metrics import resolve_period

    prov = [{"기준년월": "202601"}, {"기준년월": "202608"}]
    pool = [{"기준년월": "202603"}, {"기준년월": "202609"}]
    ctx = SimpleNamespace(dataset=lambda ref: (None, prov, SimpleNamespace(as_of_column="기준년월")))
    # 규칙이 기준 자료를 정해 두면 이 질의의 행이 아니라 그 자료의 보관 기간에서 고른다
    # (분석 하나의 기준시점은 하나 — 라벨이 말하는 기간과 실제 견준 기간이 어긋나지 않게)
    assert resolve_period(ctx, "$prev", anchor="상품별 충당금(7790)", rows=pool, col="기준년월") == "202601"
    # 기준 자료가 없으면 이 질의의 행에서 고른다(예전 동작)
    assert resolve_period(ctx, "$prev", anchor=None, rows=pool, col="기준년월") == "202603"
    # 토큰이 아니면 그대로 — 고정 연월을 적은 구성은 그대로 동작한다
    assert resolve_period(ctx, "202605", anchor=None, rows=pool, col="기준년월") == "202605"
    assert resolve_period(ctx, "202605", anchor="상품별 충당금(7790)", rows=pool, col="기준년월") == "202605"


def test_analysis_spec_allows_stored_period_tokens():
    from nhdip.analysis_agents.spec import TOKEN_RE

    for ok in ("$latest", "$prev", "$prev-2", "$earliest", "$latest-12", "$nearest-12"):
        assert TOKEN_RE.match(ok), ok
    for bad in ("$nearest", "$prev_year_end", "$next", "$latest-", "latest"):
        assert not TOKEN_RE.match(bad), bad


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
