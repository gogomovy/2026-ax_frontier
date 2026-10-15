"""업무 자료 비우기 (M.19 · DEL-13 · Q203) — 시연 자료가 올라간 시험 DB 에서 비운 뒤 '정의만 있는 새 DB' 와 같은지 본다.

비우는 시험은 한 트랜잭션 안에서 하고 끝에 되돌린다(뒤 시험은 시연 자료 위에서 돈다).
"""
from __future__ import annotations

import io
import json
from contextlib import redirect_stdout

from sqlalchemy import func, select, text


def _count(s, model) -> int:
    return int(s.execute(select(func.count()).select_from(model)).scalar() or 0)


def test_reset_tables_are_classified(db):
    """DB 의 모든 표는 '지움' 또는 '남김' 중 하나 — 새 표가 생기면 여기서 분류를 강제한다(mart 는 동적 표라 행만 지운다)."""
    from nhdip.data.reset import CLEAR_TABLES, KEEP_TABLES, MART_SCHEMA

    assert not CLEAR_TABLES & KEEP_TABLES
    with db() as s:
        tables = {f"{a}.{b}" for a, b in s.execute(text("SELECT table_schema, table_name FROM information_schema.tables WHERE table_type = 'BASE TABLE' AND table_schema NOT IN ('pg_catalog', 'information_schema')"))}
    unclassified = sorted(t for t in tables if not t.startswith(MART_SCHEMA + ".") and t not in CLEAR_TABLES | KEEP_TABLES)
    assert unclassified == [], f"reset.CLEAR_TABLES 또는 KEEP_TABLES 에 넣으세요: {unclassified}"
    assert CLEAR_TABLES <= tables  # 이름이 틀린 항목이 없다


def test_reset_data_returns_to_definitions_only(db):
    from nhdip.data import reset as R
    from nhdip.models import (
        AppUser, AuditLog, CalcRun, Dataset, KbChunk, Metric, OutboxEvent, Rule, UploadRequest, ViewArtifact, ViewBinding, Workflow, WorkflowRun, source,
    )
    from nhdip.seed.run import has_business_data

    with db() as s:
        assert has_business_data(s)
        pv = R.preview(s)
        assert pv["rows"] > 0 and pv["currentDatasetVersions"]["bank"] > 0 and sum(pv["currentDocuments"].values()) > 0
        keep = {m.__name__: _count(s, m) for m in (AppUser, Dataset, Metric, Workflow, ViewBinding, Rule)}
        audits = _count(s, AuditLog)
        try:
            rep = R.reset_business_data(s, "test", external=False)
            s.flush()
            # 업무 자료 · 파생물이 없다
            for o in ("bank", "ext"):
                t = source(o)
                assert _count(s, t.version) == _count(s, t.row) == _count(s, t.document) == _count(s, t.chunk) == 0
            assert _count(s, CalcRun) == 0 and _count(s, WorkflowRun) == 0 and _count(s, UploadRequest) == 0
            for name in R.mart_tables(s):
                assert s.execute(text(f'SELECT count(*) FROM mart."{name}"')).scalar() == 0
            assert not has_business_data(s)
            # 화면 산출물은 값 없는 틀(0세대)만 — 업무 구성 반영 때 게시한 것과 같다(Phase O)
            arts = s.execute(select(ViewArtifact.key, ViewArtifact.generation, ViewArtifact.produced_by)).all()
            assert arts and len(arts) == rep.artifacts and {p for _, _, p in arts} == {"business_config"}
            assert all(g == 1 or g == 0 for _, g, _ in arts) and len({k for k, _, _ in arts}) == len(arts)
            assert _count(s, KbChunk) == 0  # 자료가 없으면 분석 결과 색인(벡터)도 비어 있다(M.21 · Q207)
            from nhdip.graph.projection import has_uploaded_data

            assert not has_uploaded_data(s)
            # 정의 · 사용자 · 설정은 그대로, 감사 기록은 하나 더, 그래프 재투영 이벤트만 남는다
            assert {m.__name__: _count(s, m) for m in (AppUser, Dataset, Metric, Workflow, ViewBinding, Rule)} == keep
            assert _count(s, AuditLog) == audits + 1
            evs = s.execute(select(OutboxEvent.type, OutboxEvent.payload)).all()
            assert [(t, p.get("workflow")) for t, p in evs] == [("manual", "wf_graph_projection")]
            d = rep.as_dict()
            assert d["rowsRemoved"] >= pv["rows"] and d["files"] >= 0 and "bank.row_store" in d["tables"]
        finally:
            s.rollback()
        assert has_business_data(s)  # 되돌림 — 뒤 시험은 시연 자료 위에서


def test_reset_data_refuses_while_jobs_run(db):
    import pytest

    from nhdip.data import reset as R
    from nhdip.models import Job

    with db() as s:
        try:
            s.add(Job(kind="workflow", workflow_code="wf_graph_projection", causes=[], status="running"))
            s.flush()
            assert R.busy(s)["runningJobs"] >= 1
            with pytest.raises(R.ResetBusy):
                R.reset_business_data(s, "test", external=False)
        finally:
            s.rollback()


def test_reset_data_cli_previews_without_yes(db):
    from nhdip.cli import main
    from nhdip.seed.run import has_business_data

    buf = io.StringIO()
    with redirect_stdout(buf):
        code = main(["reset-data"])
    assert code == 2
    out = json.loads(buf.getvalue())
    assert out["preview"] is True and out["rows"] > 0 and "bank.row_store" in out["tables"] and "cfg.dataset" in out["kept"]
    with db() as s:
        assert has_business_data(s)  # 미리보기는 아무것도 지우지 않는다


def test_reset_clear_external_tolerates_stores_down(monkeypatch):
    """ES 미구성 · Neo4j 장애여도 실패하지 않고 '다음 동기화 · 재투영이 정리' 로 남긴다."""
    from nhdip.data import reset as R
    from nhdip.graph import neo4j_client
    from nhdip.knowledge import elastic

    monkeypatch.setattr(elastic, "configured", lambda: False)

    def down(*_a, **_k):
        raise neo4j_client.GraphUnavailable("down")

    monkeypatch.setattr(neo4j_client, "run", down)
    out = R.clear_external()
    assert out["es"]["status"] == "skipped" and out["neo4j"]["status"] == "pending"


# ═════════════════════════ 자료 전 화면 거르기 (M.19 · DEL-14 · Q204) ═════════════════════════
def _templates() -> dict:
    """시연 업무 구성 파일의 화면 틀 — 반영 때 게시하는 값 없는 틀과 같다(Phase O)."""
    import copy

    from nhdip.sample.build import business_config
    from nhdip.views.template import to_template

    b = business_config()
    return {a["key"]: to_template(a["key"], copy.deepcopy(a["payload"]), [bd for bd in b["bindings"] if bd.get("artifact_key") == a["key"]]) for a in b["artifacts"]}


def _statements(o) -> int:
    from nhdip.views.readiness import is_statement

    n, stack = 0, [o]
    while stack:
        x = stack.pop()
        if isinstance(x, dict):
            n += is_statement(x)
            stack.extend(x.values())
        elif isinstance(x, list):
            stack.extend(x)
    return n


def test_gate_hides_template_narratives():
    """값 없는 틀(빈 DB)에서는 시연 서술 · 보고서 · 제안 · 수행방안 · 분석 탭 · 전파 목표가 화면에 나가지 않는다."""
    from nhdip.views.readiness import gate

    tpl = _templates()
    look = tpl.get
    assert sum(_statements(v) for v in tpl.values()) > 0  # 틀에는 서술이 있다(워크플로가 채운다)
    shown = {k: gate(k, v, look) for k, v in tpl.items()}
    assert all(v is None for k, v in shown.items() if k.startswith("report."))
    assert sum(_statements(v) for v in shown.values() if v is not None) == 0
    assert shown["proposals"] == [] and shown["action_plans"] == [] and shown["branch_targets"] == [] and shown["cascade"] == []
    assert shown["analysis_tabs"]["current"] == [] and shown["analysis_tabs"]["previous"] == []
    for k in ("risk_dashboard", "hq_dashboard", "capital_view", "loan_overview", "default_rate_trend", "comparison_view"):
        assert shown[k]["computed"] is False, k
    assert shown["capital_view"]["evidence"] == [] and shown["loan_overview"]["revenue"]["narrative"] == ""
    assert shown["comparison_view"]["divergence"] is None and shown["risk_dashboard"]["opinions"] == []
    # 수치가 없는 행의 시연 판정 · 한도 판정 · 출처 문서, 목록 항목의 시연 상태
    assert all(r["verdict"] == "" for r in shown["profitability"]) and all(r["verdict"] for r in tpl["profitability"])
    assert shown["capital_view"]["bankTarget"]["passed"] is None and all(c["doc"] is None for c in shown["capital_view"]["constraints"])
    assert all(x["severity"] is None for x in shown["default_rate_trend"]["corpSegments"])
    # 원본(틀)은 바뀌지 않는다 — 워크플로가 같은 틀을 채운다
    assert _statements(tpl["insights"]) > 0 and tpl["proposals"]


def test_gate_keeps_everything_once_data_is_loaded(db, computed):
    """시연 자료가 올라가 워크플로가 돈 DB 에서는 거르는 것이 없다 — 업로드 뒤 화면이 그대로다."""
    from nhdip.views.readiness import gate, session_lookup
    from nhdip.views.store import all_current

    with db() as s:
        arts = all_current(s)
        look = session_lookup(s)
        diffs = []
        for k, v in sorted(arts.items()):
            if k.startswith("eval.") or k in ("change_feed",):
                continue
            g = gate(k, v, look, flag=False)
            if g != v:
                diffs.append(k)
        assert diffs == [], f"자료가 있는데 거른 산출물: {diffs}"


def test_screens_hide_template_narratives_on_empty_db(db):
    """화면 API — 산출물이 틀뿐이면 분석 결과 · 보고서 · 수행방안 · 건수가 비어 있다.
    바깥 트랜잭션 안에서 비우고(핸들러의 commit 은 저장점만 닫는다) 끝에 되돌린다 — 뒤 시험은 시연 자료 위에서."""
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

    from nhdip.data import reset as R
    from nhdip.db import engine, get_session
    from nhdip.main import app
    from nhdip.seed.run import has_business_data

    conn = engine.connect()
    outer = conn.begin()
    s = Session(bind=conn, join_transaction_mode="create_savepoint", autoflush=False, expire_on_commit=False)
    try:
        R.reset_business_data(s, "test", external=False)
        s.commit()  # 저장점만 — 바깥 트랜잭션은 열려 있다

        def _same():
            yield s

        app.dependency_overrides[get_session] = _same
        c = TestClient(app)
        assert c.post("/auth/login", json={"emp_no": "00000001", "password": "Admin1234!"}).status_code == 200
        rd = c.get("/screens/risk-dashboard").json()
        assert rd["computed"] is False and rd["opinions"] == []
        hq = c.get("/screens/hq-dashboard").json()
        assert hq["computed"] is False and hq["attentions"] == []
        assert c.get("/screens/attentions").json() == []
        assert c.get("/screens/analysis/risk/tabs").json()["current"] == []
        assert c.get("/screens/reports/model-monitoring").status_code == 404
        assert c.get("/screens/analysis/risk/reports/model-monitoring").status_code == 404
        assert c.get("/screens/insights/ins-model-6b").status_code == 404
        assert c.get("/screens/action-plans").json() == [] and c.get("/screens/proposals").json() == []
        assert c.get("/screens/branch-targets").json() == [] and c.get("/screens/cascade").json() == []
        counts = c.get("/me/menu").json()["counts"]
        assert counts["analyses"] == 0 and counts["goalProposals"] == 0 and counts["proposedPlans"] == 0
    finally:
        app.dependency_overrides.pop(get_session, None)
        s.close()
        outer.rollback()
        conn.close()
    with db() as s2:
        assert has_business_data(s2)  # 되돌림 확인


def test_gate_keeps_text_only_artifacts():
    """수치 자리가 없는 산출물(글만 있는 보고서 등)은 판단할 근거가 없어 그대로 둔다."""
    from nhdip.views.readiness import gate

    text_only = {"title": "놓친 게시", "sections": [{"heading": "x", "blocks": [{"type": "p", "text": "글만 있는 보고서"}]}]}
    assert gate("report.text-only", text_only) == text_only
    blank = {"title": "틀", "asOf": None, "figures": {"a": {"id": "a", "label": "A", "unit": "PCT", "value": None}}}
    assert gate("report.blank", blank) is None


def test_empty_platform_projects_empty_graph(monkeypatch):
    """올린 자료가 없으면 그래프 투영은 정의도 넣지 않고 관리 노드를 모두 지운다(M.21 · Q207)."""
    from types import SimpleNamespace

    from nhdip.graph import projection as P

    calls: list[str] = []
    monkeypatch.setattr(P, "run", lambda cypher, **kw: calls.append(cypher) or [])
    monkeypatch.setattr(P, "active_schema", lambda s: SimpleNamespace(version=9, classes=[{"label": "Dataset"}, {"label": "Metric"}], relations=[{"type": "FEEDS"}]))
    monkeypatch.setattr(P, "has_uploaded_data", lambda s: False)
    monkeypatch.setattr(P, "collect_graph", lambda *a, **k: (_ for _ in ()).throw(AssertionError("자료가 없으면 수집하지 않는다")))
    out = P.project_all(object())
    assert out["nodes"] == 0 and out["relationships"] == 0 and "skipped" in out
    assert not any("MERGE" in c for c in calls)
    assert any("DETACH DELETE n" in c for c in calls) and any("DELETE r" in c for c in calls)
