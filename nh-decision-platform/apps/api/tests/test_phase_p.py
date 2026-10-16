"""Phase P — 분석 에이전트 팀 DB(TDB) · 변경 감지 전파(AGW) · 업로드 기준일 · 메모(UPV) · 관리자 메뉴(ADM2)."""
from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import select

ADMIN = ("00000001", "Admin1234!")
Q_OK = {"status": "passed", "checks": []}


def _client() -> TestClient:
    from nhdip.main import app

    return TestClient(app)


def _login(c: TestClient, emp: str, pw: str) -> None:
    from nhdip import ratelimit

    ratelimit.reset()
    assert c.post("/auth/login", json={"emp_no": emp, "password": pw}).status_code == 200


# ═════════════════════════ TDB — 팀 데이터 ═════════════════════════
def test_team_scope_and_context(db):
    from nhdip.analysis_agents.render import team_section
    from nhdip.analysis_agents.team import build_context, dataset_scopes, team_of

    with db() as s:
        team = team_of(s, "T211")
        assert team.code and "T211" in team.orgs and team.code in team.orgs
        scopes = dataset_scopes(s, team.orgs)
        assert scopes, "올린 자료가 있어야 한다(시험 DB 시드)"
        code = next(iter(scopes))
        spec = {"title": "시험 분석", "purpose": "팀 자료 확인", "metrics": [{"key": "n", "label": "건수", "formula": "VALUE", "args": {"value": {"q": {"dataset": code, "agg": "count"}}}}], "tables": []}
        tc = build_context(s, spec, team, inputs=[code])
        first = tc["datasets"][0]
        assert first["code"] == code and first["use"] == "input" and first["periodText"]
        assert set(tc) >= {"team", "datasets", "kpis", "graph", "concepts", "counts"} and "available" in tc["graph"]
        # 입력 밖 자료는 팀 · 공통 · 온톨로지 연관만(다른 부서 자료가 섞이지 않게)
        assert all(d["use"] == "input" or d["scope"] in ("team", "common") or d["useLabel"] == "온톨로지 연관" for d in tc["datasets"])
        sec = team_section(tc, [], {"engine": "pg"})
        assert sec and sec["id"] == "sec-team" and any(b["type"] == "table" for b in sec["blocks"])


# ═════════════════════════ AGW — 디스패처 전파 ═════════════════════════
def test_dispatch_team_common_upstream_unchanged(db):
    from nhdip.analysis_agents.team import team_of
    from nhdip.models import Metric, OutboxEvent, Workflow, WorkflowRun, WorkflowTrigger, new_id, utcnow
    from nhdip.workflow.dispatcher import match_event, unchanged_reason
    from nhdip.workflow.engine import changed_upstream_metrics

    with db() as s:
        team = team_of(s, "T211")
        s.add_all([Workflow(code="wf_p_up", name="상위 시험", description="", outputs=[], sort=990, enabled=True),
                   Workflow(code="wf_p_down", name="하위 시험", description="", outputs=[], sort=991, enabled=True)])
        s.flush()
        s.add_all([WorkflowTrigger(workflow_code="wf_p_down", kind="team", target=team.code, enabled=True), WorkflowTrigger(workflow_code="wf_p_down", kind="common", target="*", enabled=True),
                   Metric(code="p_up_kpi", label="상위 KPI", formula="VALUE", args={"value": {"const": 1}}, workflow_code="wf_p_up", unit="NONE", enabled=True),
                   Metric(code="p_down_ratio", label="하위", formula="RATIO", args={"a": {"metric": "p_up_kpi"}, "b": {"const": 2}}, workflow_code="wf_p_down", unit="NONE", enabled=True)])
        s.flush()

        def ev(t, p):
            return OutboxEvent(id=0, type=t, payload=p, created_at=utcnow())

        m = match_event(s, ev("dataset.committed", {"dataset": "NOPE_P", "owner_org": "T211"}))
        assert any(r.startswith("trigger:team") for r in m.get("wf_p_down", [])), m
        m = match_event(s, ev("dataset.committed", {"dataset": "NOPE_P", "owner_org": "001068"}))  # 다른 팀(영업점) 자료
        assert "wf_p_down" not in m, m
        m = match_event(s, ev("dataset.committed", {"dataset": "NOPE_P", "common": True}))
        assert any(r.startswith("trigger:common") for r in m.get("wf_p_down", [])), m
        # 상위 흐름 결과 변화 → 그 지표를 쓰는 하위 흐름(AGW-03)
        fin = utcnow()
        m = match_event(s, ev("metrics.changed", {"workflow": "wf_p_up", "metrics": ["p_up_kpi"], "finished_at": fin.isoformat()}))
        assert any(r.startswith("lineage:upstream") for r in m.get("wf_p_down", [])), m
        s.add(WorkflowRun(id=new_id(), workflow_code="wf_p_down", status="succeeded", causes=[], summary={}, started_at=fin + timedelta(seconds=1)))
        s.flush()
        m = match_event(s, ev("metrics.changed", {"workflow": "wf_p_up", "metrics": ["p_up_kpi"], "finished_at": fin.isoformat()}))
        assert "wf_p_down" not in m, m  # 그 뒤 이미 시작한 하위 실행 — 다시 넣지 않는다
        # 엔진 — 바뀐 지표 중 다른 흐름이 참조하는 것만
        outs = {"p_up_kpi": SimpleNamespace(display=3, previous=1, error=None), "p_other": SimpleNamespace(display=1, previous=0, error=None)}
        assert changed_upstream_metrics(s, "wf_p_up", outs) == ["p_up_kpi"]
        assert changed_upstream_metrics(s, "wf_p_up", {"p_up_kpi": SimpleNamespace(display=1, previous=1, error=None)}) == []
        assert unchanged_reason(ev("dataset.committed", {"dataset": "X", "unchanged": True, "same_as": 3})) and not unchanged_reason(ev("dataset.committed", {"dataset": "X"}))
        s.rollback()


# ═════════════════════════ UPV — 기준일 · 메모 · 중복 ═════════════════════════
def test_period_partition_normalization_and_placement(db):
    from nhdip.data.datasets import current_rows, ingest_rows
    from nhdip.data.placement import placement
    from nhdip.models import Dataset, OutboxEvent

    with db() as s:
        ds = Dataset(code="P_TEST_PERIOD", name="기간 시험", origin="bank", kind="fact", description="", columns=[{"name": "ym", "type": "str"}, {"name": "v", "type": "num"}],
                     key_columns=["ym"], as_of_column="ym", mapping={}, quality_rules=[], parser={}, active=True)
        s.add(ds)
        s.flush()
        ingest_rows(s, ds, [{"ym": "202607", "v": 1}], quality=Q_OK, file_name="a.csv", file_sha="a" * 64, memo="7월 원본", requested_by="20250001")
        v2 = ingest_rows(s, ds, [{"ym": "2026-07-31", "v": 2}, {"ym": "202608", "v": 3}], quality=Q_OK, file_name="b.csv", file_sha="b" * 64)
        s.flush()
        _, rows = current_rows(s, ds)
        assert sorted(r["v"] for r in rows) == [2, 3], rows  # 202607 과 2026-07-31 은 같은 기간 — 최근 반영 판(UPV-08)
        first = s.execute(select(type(v2)).where(type(v2).dataset_code == ds.code, type(v2).version == 1)).scalar()
        assert first.memo == "7월 원본" and first.requested_by == "20250001"
        # 같은 파일 다시 반영 — 재계산하지 않도록 이벤트에 표시(UPV-05)
        ingest_rows(s, ds, [{"ym": "2026-07-31", "v": 2}, {"ym": "202608", "v": 3}], quality=Q_OK, file_name="b.csv", file_sha="b" * 64)
        s.flush()
        evs = s.execute(select(OutboxEvent).where(OutboxEvent.type == "dataset.committed").order_by(OutboxEvent.id.desc()).limit(1)).scalars().all()
        assert evs[0].payload.get("dataset") == ds.code and evs[0].payload.get("unchanged") and evs[0].payload.get("same_as") == 2, evs[0].payload
        # 반영 미리보기 — 입력 기준일 불일치 · 새 기준일 추가 · 같은 기준일 교체 · 같은 파일
        bad = placement(s, ds, [{"ym": "202608", "v": 1}], as_of="2026-05-31", owner_org=None)
        assert bad["error"] and "파일 기간" in bad["error"]
        add = placement(s, ds, [{"ym": "202609", "v": 1}], as_of=None, owner_org=None)
        assert add["action"] == "add" and add["versionAsOf"] == "2026-09-30" and not add["error"]
        rep = placement(s, ds, [{"ym": "2026-07-31", "v": 2}, {"ym": "202608", "v": 3}], as_of=None, owner_org=None, file_sha="b" * 64)
        assert rep["action"] == "replace" and rep["replaces"]["version"] == 3 and rep["duplicateOf"] == {"version": 3}
        # 기준일 열이 없는 자료 — 날짜별 판이 쌓여도 계산은 가장 늦은 기준일 판만(UPV-04)
        nc = Dataset(code="P_TEST_NOCOL", name="열 없음 시험", origin="bank", kind="fact", description="", columns=[{"name": "v", "type": "num"}], key_columns=[], as_of_column=None,
                     mapping={}, quality_rules=[], parser={}, active=True)
        s.add(nc)
        s.flush()
        ingest_rows(s, nc, [{"v": 10}], quality=Q_OK, file_name="x.csv", as_of="2026-08-31")
        ingest_rows(s, nc, [{"v": 20}], quality=Q_OK, file_name="y.csv", as_of="2026-07-31")
        s.flush()
        _, rows = current_rows(s, nc)
        assert [r["v"] for r in rows] == [10], rows
        assert placement(s, nc, [{"v": 1}], as_of="2026-09-30", owner_org=None)["noAsOfColumn"]
        s.rollback()


# ═════════════════════════ AGW-09 · ADM2 — 관리자 ═════════════════════════
def test_admin_automation_and_menu(db):
    admin = _client()
    _login(admin, *ADMIN)
    r = admin.get("/admin/automation")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["workflows"] and {"policy", "decisions", "counts"} <= set(body)
    wf = body["workflows"][0]
    assert {"state", "triggers", "lastRun"} <= set(wf) and {"cron", "data", "upstream"} <= set(wf["triggers"])
    assert any(c["label"].startswith(("매일", "평일")) for w in body["workflows"] for c in w["triggers"]["cron"]), "업무 흐름 정기 실행(매일 06:00~)"
    secs = {sc["section"]: [i["href"] for i in sc["flow"] + sc["reference"]] for sc in admin.get("/me/menu").json()["sections"] if sc["admin"]}
    assert "/admin/automation" in secs.get("에이전트 · 자동화", []), secs
    assert {"관리자 홈", "데이터 반영", "에이전트 · 자동화", "운영 현황", "실행 기록 · 품질", "계산 · 설정", "사용자 · 권한"} <= set(secs), sorted(secs)
    p = admin.get("/db/datasets/NOPE/periods")
    assert p.status_code in (403, 404)
