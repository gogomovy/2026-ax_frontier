"""자료가 바뀌면 그 자료로 정해지는 것이 따라 바뀐다 — 소유 변경 · 삭제 전파.

  소유 변경   다른 팀이 다시 올림 · 되돌리기 · 삭제로 다른 판이 현재가 됨 · 공통 통합 DB 전환 · 관리자 소유 변경 · 조직 이동
              → 이벤트에 이전 · 새 소유를 싣고, 이전 소유 팀과 새 소유 팀의 팀 범위 흐름이 모두 다시 돈다
  삭제        지운 자료로 낸 수치 · 표 · 경영목표 추천은 '갱신 실패' 로 남기지 않고 비운다(남은 자료로 다시 계산되는 것만 남는다)
              자료가 하나도 남지 않아 화면을 값 없는 틀로 두면 그 위의 사용자 결정(확정 · 신설 목표, 제안 처리, 수행방안 상태)도 처음 상태로
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import select


def _last(s, etype: str, key: str, value):
    from nhdip.models import OutboxEvent

    for e in s.execute(select(OutboxEvent).where(OutboxEvent.type == etype).order_by(OutboxEvent.id.desc())).scalars():
        if (e.payload or {}).get(key) == value:
            return e.payload
    return None


def _ev(t: str, p: dict):
    from nhdip.models import OutboxEvent, utcnow

    return OutboxEvent(id=0, type=t, payload=p, created_at=utcnow())


def test_owner_change_wakes_old_and_new_team(db):
    from nhdip.analysis_agents.team import team_of
    from nhdip.models import Workflow, WorkflowTrigger
    from nhdip.workflow.dispatcher import event_owners, match_event

    with db() as s:
        team = team_of(s, "T211")
        s.add(Workflow(code="wf_own_team", name="팀 범위 시험", description="", outputs=[], sort=995, enabled=True))
        s.flush()
        s.add(WorkflowTrigger(workflow_code="wf_own_team", kind="team", target=team.code, enabled=True))
        s.flush()
        try:
            assert event_owners({"owner_org": "001068", "owner_orgs": ["T211", None]}) == {"001068", "T211"}
            # 새 소유는 다른 곳(영업점)이지만 이전 소유가 이 팀 — 이 팀 흐름도 다시 돈다(이 팀 범위에서 자료가 빠진다)
            m = match_event(s, _ev("dataset.committed", {"dataset": "NOPE_OWN", "owner_org": "001068", "owner_orgs": ["T211"]}))
            assert any(r.startswith("trigger:team") for r in m.get("wf_own_team", [])), m
            assert "wf_own_team" not in match_event(s, _ev("dataset.committed", {"dataset": "NOPE_OWN", "owner_org": "001068"}))
            # 소유만 바꾼 이벤트 · 삭제 · 문서 소유 변경도 같은 규칙
            for t in ("dataset.owner_changed", "dataset.deleted", "document.owner_changed"):
                assert "wf_own_team" in match_event(s, _ev(t, {"dataset": "NOPE_OWN", "doc_class": "x", "owner_orgs": ["T211"]})), t
            # 공통 통합 DB 에서 뺀 자료 — 공통 조건 흐름도 다시 본다
            s.add(WorkflowTrigger(workflow_code="wf_own_team", kind="common", target="*", enabled=True))
            s.flush()
            m = match_event(s, _ev("dataset.owner_changed", {"dataset": "NOPE_OWN", "common": False, "was_common": True}))
            assert any(r.startswith("trigger:common") for r in m.get("wf_own_team", [])), m
            # 조직 이동 — 이 팀 아래에 있던 조직을 다른 곳으로 옮기면 이 팀 범위가 바뀐다
            m = match_event(s, _ev("org.moved", {"code": "X_MOVED", "parent_before": team.code, "parent_after": None}))
            assert any(r.startswith("lineage:org_moved") for r in m.get("wf_own_team", [])), m
        finally:
            s.rollback()


def test_owner_change_events_carry_previous_owner(db):
    from nhdip.api.admin_data import OWNER_BEFORE_COMMON, _common_switch
    from nhdip.data.datasets import IngestError, change_version_owner, ingest_rows, rollback
    from nhdip.data.deletion import delete_dataset_version
    from nhdip.data.documents import change_document_owner, ingest_document
    from nhdip.models import Dataset, source

    code = "P_OWN_CHANGE"
    q = {"status": "passed", "checks": []}
    rows = [{"k": "a", "v": 1}]
    with db() as s:
        try:
            ds = Dataset(code=code, name="소유 변경 시험", origin="bank", kind="fact", description="", columns=[{"name": "k", "type": "str"}, {"name": "v", "type": "num"}],
                         key_columns=["k"], quality_rules=[], mapping={}, parser={}, active=True)
            s.add(ds)
            s.flush()
            v1 = ingest_rows(s, ds, rows, quality=q, file_name="a.csv", file_sha="sha-a", actor="t", owner_org="T211")
            s.flush()
            # 같은 파일을 다른 팀 소유로 — '변경 없음' 이 아니다(팀 범위 결과가 바뀐다), 이전 소유가 실린다
            v2 = ingest_rows(s, ds, rows, quality=q, file_name="a.csv", file_sha="sha-a", actor="t", owner_org="T212")
            s.flush()
            p = _last(s, "dataset.committed", "version_id", v2.id)
            assert p["owner_org"] == "T212" and p["owner_orgs"] == ["T211"] and p["owner_changed"] and not p.get("unchanged"), p
            # 같은 파일 · 같은 소유는 그대로 '변경 없음'
            v3 = ingest_rows(s, ds, rows, quality=q, file_name="a.csv", file_sha="sha-a", actor="t", owner_org="T212")
            s.flush()
            assert _last(s, "dataset.committed", "version_id", v3.id).get("unchanged") is True
            # 관리자 소유 변경 — 현재 판이면 이벤트(이전 소유)
            out = change_version_owner(s, ds, v3.id, None, "admin")
            s.flush()
            assert out == {"from": "T212", "to": None, "event": True}
            p = _last(s, "dataset.owner_changed", "version_id", v3.id)
            assert p["owner_orgs"] == ["T212"] and "owner_org" not in p
            assert change_version_owner(s, ds, v3.id, None, "admin") is None  # 바뀐 것 없음
            # 되돌리기 — 되돌린 판의 소유 + 밀려난 판의 소유
            rollback(s, ds, v1.id, "admin")
            s.flush()
            p = _last(s, "dataset.committed", "version_id", v1.id)
            assert p.get("rollback") and p["owner_org"] == "T211" and p.get("owner_changed"), p
            # 영업점 판 — 영업점 구획은 따로, 소유를 전행으로 바꾸면 같은 기준일 현재 판이 둘이 되므로 거절
            vb = ingest_rows(s, ds, rows, quality=q, file_name="b.csv", file_sha="sha-b", actor="t", owner_org="001068")
            s.flush()
            with pytest.raises(IngestError):
                change_version_owner(s, ds, vb.id, None, "admin")
            # 공통 통합 DB — 켜면 소유를 비우고 남겨 두며, 끄면 되돌린다 · 자료 이벤트로 이전 소유 팀 흐름이 다시 돈다
            t = source("bank")
            ds.common = True
            _common_switch(s, ds, True, "admin")
            s.flush()
            owners = {x.id: x.owner_org for x in s.execute(select(t.version).where(t.version.dataset_code == code)).scalars()}
            assert set(owners.values()) == {None}
            p = _last(s, "dataset.owner_changed", "reason", "common_on")
            assert p["dataset"] == code and set(p["owner_orgs"]) == {"T211", "T212", "001068"} and p["common"] is True
            with pytest.raises(IngestError):
                change_version_owner(s, ds, v1.id, "T211", "admin")  # 공통 자료는 소유 팀이 없다
            ds.common = False
            _common_switch(s, ds, False, "admin")
            s.flush()
            back = {x.id: (x.owner_org, OWNER_BEFORE_COMMON in (x.quality or {})) for x in s.execute(select(t.version).where(t.version.dataset_code == code)).scalars()}
            assert back[v1.id] == ("T211", False) and back[v2.id] == ("T212", False) and back[vb.id] == ("001068", False)
            assert _last(s, "dataset.owner_changed", "reason", "common_off")["was_common"] is True
            # 삭제 — 지운 판의 소유 팀
            delete_dataset_version(s, ds, v1.id, "admin", "시험 삭제")
            s.flush()
            p = _last(s, "dataset.deleted", "version_id", v1.id)
            assert "T211" in p["owner_orgs"], p
            # 문서 — 다른 팀이 같은 문서를 다시 올림 · 관리자 소유 변경
            d1 = ingest_document(s, origin="bank", doc_code="P-OWN-DOC", title="소유 시험 문서", doc_class="reference", text="소유 시험 본문입니다.", actor="t", owner_org="T211")
            s.flush()
            d2 = ingest_document(s, origin="bank", doc_code="P-OWN-DOC", title="소유 시험 문서", doc_class="reference", text="소유 시험 본문입니다.", actor="t", owner_org="T212")
            s.flush()
            p = _last(s, "document.ingested", "document_id", d2.id)
            assert p["owner_org"] == "T212" and p["owner_orgs"] == ["T211"], p
            assert d1.id != d2.id
            out = change_document_owner(s, "bank", d2.id, "001068", "admin")
            s.flush()
            p = _last(s, "document.owner_changed", "document_id", d2.id)
            assert out["event"] and p["owner_org"] == "001068" and p["owner_orgs"] == ["T212"], p
        finally:
            s.rollback()


def test_deleted_input_clears_instead_of_stale(db):
    from nhdip.models import Metric, ViewBinding, Workflow
    from nhdip.views.store import patch_figures
    from nhdip.workflow.nodes import _binding_gone, gone_metrics

    # 수치 — 지운 자료의 옛 값 · 계산 근거를 남기지 않는다(계산 실패는 지금처럼 '갱신 실패' 표시)
    payload = {"a": {"id": "f1", "label": "지운 자료 수치", "value": 9.5, "unit": "PCT", "calc": {"formulaId": "RATIO"}, "sourceRef": "x"},
               "b": {"id": "f2", "label": "계산 실패", "value": 3.0, "unit": "PCT"}}
    changes: list = []
    patch_figures(payload, {"f1": {"cleared": True, "reason": "입력 자료 삭제"}, "f2": {"stale": True, "staleReason": "오류"}}, changes, "k")
    assert payload["a"]["value"] is None and "calc" not in payload["a"] and "sourceRef" not in payload["a"]
    assert payload["b"]["value"] == 3.0 and payload["b"]["stale"] is True
    assert any(c.get("cleared") for c in changes)
    # 어떤 지표가 '지운 자료' 지표인지 — 그 자료를 읽는 지표 + 그 지표를 참조하는 지표
    with db() as s:
        try:
            s.add(Workflow(code="wf_gone_t", name="삭제 시험", description="", outputs=[], sort=996, enabled=True))
            s.flush()
            s.add_all([Metric(code="g_base", label="기본", formula="VALUE", args={"value": {"q": {"dataset": "GONE_DS", "field": "v"}}}, workflow_code="wf_gone_t", unit="NONE", enabled=True),
                       Metric(code="g_derived", label="파생", formula="RATIO", args={"a": {"metric": "g_base"}, "b": {"const": 2}}, workflow_code="wf_gone_t", unit="NONE", enabled=True),
                       Metric(code="g_other", label="남은 자료", formula="VALUE", args={"value": {"q": {"dataset": "KEPT_DS", "field": "v"}}}, workflow_code="wf_gone_t", unit="NONE", enabled=True)])
            s.flush()
            ctx = SimpleNamespace(session=s, state={"missing_datasets": ["GONE_DS"]})
            gone = gone_metrics(ctx)
            assert {"g_base", "g_derived"} <= gone and "g_other" not in gone
            assert _binding_gone(ctx, ViewBinding(workflow_code="wf_gone_t", artifact_key="k", path="table:x", builder="b", params={"dataset": "GONE_DS"}))
            assert _binding_gone(ctx, ViewBinding(workflow_code="wf_gone_t", artifact_key="k", path="table:x", builder="b", params={"metrics": ["g_derived"]}))
            assert not _binding_gone(ctx, ViewBinding(workflow_code="wf_gone_t", artifact_key="k", path="table:x", builder="b", params={"dataset": "KEPT_DS"}))
            assert gone_metrics(SimpleNamespace(session=s, state={})) == set()
        finally:
            s.rollback()


def test_no_data_resets_goal_and_plan_state(db):
    from nhdip.models import Workflow
    from nhdip.views import user_state as S
    from nhdip.workflow.engine import reset_user_state

    with db() as s:
        try:
            S.put(s, S.NS_GOAL_OVERRIDE, "goal-x", {"targetValue": 9.9}, "t")
            S.put(s, S.NS_GOAL_ADDED, "goal-new", {"title": "신설"}, "t")
            S.put(s, S.NS_PROPOSAL_ACTION, "prop-x", {"action": "applied"}, "t")
            S.put(s, S.NS_PLAN_RUNTIME, "plan-from-analysis", {"status": "in_progress", "branchShared": True}, "t")
            S.put(s, S.NS_PLAN_RUNTIME, "plan-user-written", {"status": "in_progress"}, "t")
            S.put(s, S.NS_PLAN_USER, "plan-user-written", {"title": "직접 쓴 수행방안"}, "t")
            S.put(s, S.NS_REPORT_REQUEST, "req-x", {"title": "요청"}, "t")
            s.flush()
            wf = Workflow(code="wf_reset_t", name="비우기 시험", description="", outputs=["goals", "action_plans"], sort=997, enabled=True)
            out = reset_user_state(s, wf, {"goals": [{"id": "goal-x"}], "action_plans": [{"id": "plan-from-analysis"}]})
            s.flush()
            assert out["goal.override"] == 1 and out["goal.added"] == 1 and out["goal.proposal_action"] == 1 and out["plan.runtime"] == 1
            assert not S.get_ns(s, S.NS_GOAL_OVERRIDE) and not S.get_ns(s, S.NS_GOAL_ADDED) and not S.get_ns(s, S.NS_PROPOSAL_ACTION)
            # 분석에서 나온 수행방안 상태만 — 직접 쓴 수행방안 · 요청 글은 남긴다
            assert set(S.get_ns(s, S.NS_PLAN_RUNTIME)) == {"plan-user-written"} and "plan-user-written" in S.get_ns(s, S.NS_PLAN_USER)
            assert "req-x" in S.get_ns(s, S.NS_REPORT_REQUEST)
            assert reset_user_state(s, wf, {"hq_dashboard": {}}) == {}  # 목표 · 수행방안이 아닌 산출물은 결정을 건드리지 않는다
        finally:
            s.rollback()
