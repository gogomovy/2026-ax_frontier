"""발표 흐름(NAVI) 점검에서 메운 빈 곳.

  경영목표 → 사업부서 · 영업점   종합기획부가 목표를 확정 · 수정 · 신설 · 삭제하면 수행방안을 내는 사업부서 흐름과 영업점 흐름도 다시 보고,
                                서술 에이전트는 확정 목표를 숫자 없이 공통 방향으로 읽는다
  문서(PDF · 워드)              워드(docx) 문서도 보안 검사 · 본문 추출
  영업점 범위                    필요한 자료 설정({"dataset", "column"})으로 지점을 찾는다 — 자료 없는 기본 지점은 계산된 지점이 아니다
"""
from __future__ import annotations

import io
import zipfile

import pytest
from sqlalchemy import select


def _ev(t: str, p: dict):
    from nhdip.models import OutboxEvent, utcnow

    return OutboxEvent(id=0, type=t, payload=p, created_at=utcnow())


def test_goal_event_wakes_business_and_branch_flows(db):
    from nhdip.models import Workflow
    from nhdip.workflow.dispatcher import match_event

    with db() as s:
        m = match_event(s, _ev("goal.confirmed", {"goal": "goal-q3-revenue", "mode": "edit"}))
        outs = {w.code: w.outputs or [] for w in s.execute(select(Workflow).where(Workflow.enabled)).scalars()}
    assert any(r.startswith("trigger:event") for r in m.get("wf_hq_goal_review", [])), m  # 목표를 만드는 흐름은 자기 조건으로
    assert not any(r.startswith("lineage:goal") for r in m.get("wf_hq_goal_review", []))
    woke = {wf for wf, rs in m.items() if any(r.startswith("lineage:goal") for r in rs)}
    assert {"wf_branch_kpi", "wf_model_monitoring", "wf_inclusive_risk"} <= woke, m
    assert all("goals" not in outs[wf] for wf in woke) and not woke & {"wf_graph_projection", "wf_ontology_build"}


def test_goal_lines_are_current_goals_without_numbers(db):
    from nhdip.views import user_state as S
    from nhdip.workflow import numguard

    with db() as s:
        try:
            S.put(s, S.NS_GOAL_ADDED, "goal-manual-navi1", {"id": "goal-manual-navi1", "title": "서민금융 공급 비중 5.5% 이상", "periodLabel": "2026년 하반기", "status": "active", "ownerOrg": "종합기획부"}, "t")
            S.put(s, S.NS_GOAL_ADDED, "goal-manual-navi2", {"id": "goal-manual-navi2", "title": "보관된 목표 1,200억원", "status": "archived"}, "t")
            s.flush()
            lines = S.goal_lines(s, limit=50)
            mine = [ln for ln in lines if "서민금융 공급 비중" in ln]
            assert mine == ["- [종합기획부 신설 목표] 서민금융 공급 비중 이상 · 2026년 하반기"], lines
            assert not any("보관된 목표" in ln for ln in lines)
            assert all(not numguard.literal_numbers(ln) for ln in lines), lines  # 서술 검증이 막는 숫자는 근거 줄에도 없다
        finally:
            s.rollback()


def _docx(paras: list[str], macro: bool = False) -> bytes:
    body = "".join(f"<w:p><w:pPr/><w:r><w:t xml:space=\"preserve\">{p}</w:t></w:r></w:p>" for p in paras)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", f'<?xml version="1.0"?><w:document xmlns:w="urn:w"><w:body>{body}'
                                        '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>표 칸</w:t></w:r><w:r><w:tab/><w:t>A&amp;B</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>')
        if macro:
            z.writestr("word/vbaProject.bin", b"x")
    return buf.getvalue()


def test_docx_document_is_checked_and_extracted():
    from nhdip.data.documents import extract_text
    from nhdip.data.filecheck import UploadRejected, check_upload

    data = _docx(["1. 추진 방향", "서민 대출 공급 목표를 상향한다."])
    assert check_upload("정책.docx", data, "document") == "정책.docx"
    text, pages = extract_text("정책.docx", data)
    assert text.split("\n\n") == ["1. 추진 방향", "서민 대출 공급 목표를 상향한다.", "표 칸\tA&B"] and pages == [(1, text)]
    with pytest.raises(UploadRejected, match="매크로"):
        check_upload("매크로.docx", _docx(["x"], macro=True), "document")
    with pytest.raises(UploadRejected, match="doc"):
        check_upload("예전.docx", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 64, "document")
    with pytest.raises(UploadRejected, match="워드"):
        check_upload("가짜.docx", b"%PDF-1.4", "document")
    with pytest.raises(UploadRejected, match="허용 형식"):
        check_upload("x.docx", data, "dataset")


def test_scope_requires_accept_config_and_legacy_forms():
    from nhdip.scopes import _req_pair

    assert _req_pair({"dataset": "영업점 업적평가 득점 현황", "column": "office_cd"}) == ("영업점 업적평가 득점 현황", "office_cd")
    assert _req_pair("영업점 사무소 마스터.office_cd") == ("영업점 사무소 마스터", "office_cd")


def test_aggregate_conditions_support_comparisons():
    """질의 패널 data_aggregate — 후속 질문으로 기준을 바꿔 집계(이상 · 미만 · 목록 · 제외)."""
    from nhdip.knowledge.assist_tools import _conditions

    rows = [{"g": "A", "v": "5"}, {"g": "B", "v": "7.5"}, {"g": "C", "v": None}, {"g": "D", "v": "12"}]

    def pick(f):
        conds, bad = _conditions(f)
        assert bad is None, bad
        return [r["g"] for r in rows if all(c(r.get(k)) for k, c in conds)]

    assert pick({"g": "A"}) == ["A"]
    assert pick({"v": {"gte": 7.5}}) == ["B", "D"]
    assert pick({"v": {"gt": 5, "lt": 12}}) == ["B"]
    assert pick({"g": {"in": ["A", "D"]}}) == ["A", "D"]
    assert pick({"g": {"ne": "A"}, "v": {"lte": "7.5"}}) == ["B"]
    assert _conditions({"v": {"like": "x"}})[1] and _conditions({"v": {"gt": "abc"}})[1]
