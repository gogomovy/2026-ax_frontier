"""데이터셋 정의 삭제 — 연결까지 함께 (Phase M 후속 · DOB-12 · Q208).

정의만 지우는 삭제는 연결(버전 · 지표 · 바인딩 · 트리거)이 있으면 막힌다. 데이터 관리자는 미리보기 · 사유 확인 뒤
버전은 모두 지우고 지표 · 바인딩은 끄고 트리거는 지운 다음 정의를 지울 수 있다.
"""
from __future__ import annotations

import io

from fastapi.testclient import TestClient
from sqlalchemy import func, select

ADMIN = ("00000001", "Admin1234!")
DS = "TEST_DEFDEL_DS"
DS2 = "TEST_DEFDEL_EMPTY"
WF = "wf_test_defdel"


def _client() -> TestClient:
    from nhdip.main import app

    return TestClient(app)


def _admin() -> TestClient:
    c = _client()
    assert c.post("/auth/login", json={"emp_no": ADMIN[0], "password": ADMIN[1]}).status_code == 200
    return c


def _definition(code: str) -> dict:
    return {
        "code": code, "name": f"정의 삭제 시험 {code}", "origin": "bank", "kind": "fact", "description": "정의 삭제 시험",
        "columns": [{"name": "ym", "type": "str", "required": True}, {"name": "item", "type": "str", "required": True}, {"name": "amount", "type": "num"}],
        "key_columns": ["ym", "item"], "as_of_column": "ym", "quality_rules": [],
    }


def _upload(c: TestClient, name: str, rows: list[tuple[str, str, float]]) -> dict:
    csv = "ym,item,amount\n" + "".join(f"{a},{b},{v}\n" for a, b, v in rows)
    r = c.post(f"/admin/datasets/{DS}/upload", data={"origin": "bank", "data_origin": "simulated", "force": "true"}, files={"file": (name, io.BytesIO(csv.encode()), "text/csv")})
    assert r.status_code == 201, r.text
    return r.json()


def _wire(db) -> None:
    """시험 워크플로 — 이 자료를 읽는 지표 · 파생 지표 · 바인딩 · 트리거, 그리고 무관한 지표."""
    from nhdip.models import Metric, ViewBinding, Workflow, WorkflowTrigger

    with db() as s:
        s.add(Workflow(code=WF, name="정의 삭제 시험 워크플로", enabled=True, outputs=[]))
        s.flush()
        s.add(Metric(code="t_defdel_sum", label="시험 합계", formula="SUM", args={"q": {"dataset": DS, "column": "amount"}}, workflow_code=WF))
        s.add(Metric(code="t_defdel_half", label="시험 파생", formula="SHARE", args={"numerator": {"metric": "t_defdel_sum"}, "denominator": {"const": 2}}, workflow_code=WF))
        s.add(Metric(code="t_defdel_other", label="무관한 지표", formula="SUM", args={"q": {"dataset": "NO_SUCH_DS", "column": "x"}}, workflow_code=WF))
        s.add(ViewBinding(workflow_code=WF, artifact_key="t_defdel_view", path="rows", builder="table", params={"dataset": DS}))
        s.add(WorkflowTrigger(workflow_code=WF, kind="dataset", target=DS))
        s.add(WorkflowTrigger(workflow_code=WF, kind="master", target=DS2))
        s.commit()


def _cleanup(db) -> None:
    from nhdip.models import Dataset, Job, OutboxEvent, PurgeTask, Setting, UploadRequest, Workflow, utcnow

    with db() as s:
        for t in s.execute(select(PurgeTask).where(PurgeTask.subject_ref.like(f"bank:{DS}:%"))).scalars():
            s.delete(t)
        for ev in s.execute(select(OutboxEvent).where(OutboxEvent.dispatched_at.is_(None))).scalars():
            if (ev.payload or {}).get("workflow") == WF or (ev.payload or {}).get("dataset") in (DS, DS2) or (ev.payload or {}).get("code") in (DS, DS2):
                ev.dispatched_at = utcnow()
        for j in s.execute(select(Job).where(Job.workflow_code == WF)).scalars():
            s.delete(j)
        for r in s.execute(select(UploadRequest).where(UploadRequest.target.in_([DS, DS2]))).scalars():
            s.delete(r)
        s.flush()
        w = s.get(Workflow, WF)
        if w is not None:
            s.delete(w)  # 지표 · 바인딩 · 트리거는 FK 로 함께
        for code in (DS, DS2):
            d = s.get(Dataset, code)
            if d is not None:
                s.delete(d)
        st = s.get(Setting, "seed.suppressed_datasets")
        if st is not None and isinstance(st.value, list):
            st.value = [x for x in st.value if x not in (DS, DS2)]
        s.commit()


def test_cascade_delete_removes_versions_and_unwires(db):
    from nhdip.models import AuditLog, Dataset, Metric, OutboxEvent, PurgeTask, Setting, ViewBinding, WorkflowTrigger, source

    c = _admin()
    _cleanup(db)
    assert c.post("/admin/datasets", json=_definition(DS)).status_code == 201
    _wire(db)
    try:
        v1 = _upload(c, "defdel_v1.csv", [("202608", "A", 10), ("202608", "B", 20)])
        v2 = _upload(c, "defdel_v2.csv", [("202608", "A", 11), ("202608", "B", 21)])
        v3 = _upload(c, "defdel_v3.csv", [("202607", "A", 9)])
        # 정의만 지우기 — 연결이 있으면 막히고, 연결까지 지우는 길을 알려 준다
        r = c.delete(f"/admin/datasets/{DS}")
        assert r.status_code == 409 and "연결까지 정의 삭제" in r.json()["detail"]
        # 미리보기 — 지울 버전 · 끌 지표(파생 포함, 무관한 지표 제외) · 바인딩 · 트리거 · 다시 도는 워크플로
        p = c.get(f"/admin/datasets/{DS}/delete-preview").json()
        assert [v["version"] for v in p["versions"]] == sorted([v1["version"], v2["version"], v3["version"]])
        assert p["rows"] == 5 and p["blocked"] is None and p["seedDefined"] is False
        assert {m["code"]: m["derived"] for m in p["metrics"]} == {"t_defdel_sum": False, "t_defdel_half": True}
        assert len(p["bindings"]) == 1 and [(t["workflow"], t["kind"]) for t in p["triggers"]] == [(WF, "dataset")]
        assert [w["code"] for w in p["workflows"]] == [WF]
        # 사유 없음 → 422 (아무것도 바뀌지 않음)
        assert c.post(f"/admin/datasets/{DS}/delete", json={"reason": " "}).status_code == 422
        with db() as s:
            assert s.get(Dataset, DS) is not None and s.get(Metric, "t_defdel_sum").enabled
        # 실행
        r = c.post(f"/admin/datasets/{DS}/delete", json={"reason": "시험 정의 정리"})
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["deleted"] == DS and out["removed"]["versions"] == 3 and out["removed"]["rows"] == 5
        assert out["removed"]["metricsDisabled"] == 2 and out["removed"]["bindingsDisabled"] == 1 and out["removed"]["triggersRemoved"] == 1
        assert out["rerun"] == [WF] and out["purgeTasks"]
        with db() as s:
            t = source("bank")
            assert s.get(Dataset, DS) is None
            assert s.execute(select(func.count()).select_from(t.version).where(t.version.dataset_code == DS)).scalar() == 0
            assert s.execute(select(func.count()).select_from(t.row).where(t.row.version_id.in_([v1["id"], v2["id"], v3["id"]]))).scalar() == 0
            assert s.get(Metric, "t_defdel_sum").enabled is False and s.get(Metric, "t_defdel_half").enabled is False
            assert s.get(Metric, "t_defdel_other").enabled is True  # 이 자료와 무관한 지표는 그대로
            assert all(not b.enabled for b in s.execute(select(ViewBinding).where(ViewBinding.workflow_code == WF)).scalars())
            trig = [(x.kind, x.target) for x in s.execute(select(WorkflowTrigger).where(WorkflowTrigger.workflow_code == WF)).scalars()]
            assert trig == [("master", DS2)]  # 다른 자료의 트리거는 남는다
            assert DS in s.get(Setting, "seed.suppressed_datasets").value
            evs = s.execute(select(OutboxEvent).where(OutboxEvent.dispatched_at.is_(None))).scalars().all()
            assert any(e.type == "manual" and e.payload.get("workflow") == WF and DS in e.payload.get("reason", "") for e in evs)
            assert any(e.type == "config.changed" and e.payload.get("code") == DS and e.payload.get("deleted") for e in evs)
            a = s.execute(select(AuditLog).where(AuditLog.action == "admin.dataset.delete_cascade", AuditLog.target_id == DS).order_by(AuditLog.id.desc())).scalars().first()
            assert a is not None and sorted(a.detail["metrics_disabled"]) == ["t_defdel_half", "t_defdel_sum"] and a.detail["reason"] == "시험 정의 정리"
            assert s.execute(select(func.count()).select_from(PurgeTask).where(PurgeTask.subject_ref.like(f"bank:{DS}:%"))).scalar() >= 1
        assert c.post(f"/admin/datasets/{DS}/delete", json={"reason": "다시"}).status_code == 404
    finally:
        _cleanup(db)


def test_cascade_delete_without_versions_and_guards(db):
    from nhdip.models import AppUser, Dataset, OutboxEvent, UploadRequest
    from nhdip.security import hash_password

    c = _admin()
    _cleanup(db)
    assert c.post("/admin/datasets", json=_definition(DS2)).status_code == 201
    _wire(db)  # DS2 는 master 트리거 하나만
    try:
        with db() as s:
            u = s.get(AppUser, "90000021")
            if u is None:
                s.add(AppUser(emp_no="90000021", name="시험", password_hash=hash_password("Test1234!"), org_code="T911", role="admin", status="active", data_admin=False))
            s.commit()
        plain = _client()
        assert plain.post("/auth/login", json={"emp_no": "90000021", "password": "Test1234!"}).status_code == 200
        assert plain.get(f"/admin/datasets/{DS2}/delete-preview").status_code == 403
        assert plain.post(f"/admin/datasets/{DS2}/delete", json={"reason": "권한 시험"}).status_code == 403
        # 처리 중인 요청이 있으면 막는다
        with db() as s:
            s.add(UploadRequest(kind="dataset", target=DS2, origin="bank", file_name="x.csv", file_path="", status="pending", requested_by="90000021"))
            s.commit()
        p = c.get(f"/admin/datasets/{DS2}/delete-preview").json()
        assert p["pending"] == 1 and "처리 중" in p["blocked"]
        assert [w["code"] for w in p["workflows"]] == [WF] and len(p["triggers"]) == 1
        # 멈춘 워크플로는 '다시 도는 워크플로' 에 넣지 않는다(트리거는 그래도 정리 대상)
        from nhdip.models import Workflow

        with db() as s:
            s.get(Workflow, WF).enabled = False
            s.commit()
        p = c.get(f"/admin/datasets/{DS2}/delete-preview").json()
        assert p["workflows"] == [] and len(p["triggers"]) == 1
        r = c.post(f"/admin/datasets/{DS2}/delete", json={"reason": "요청 대기 중"})
        assert r.status_code == 409 and "처리 중" in r.json()["detail"]
        with db() as s:
            for x in s.execute(select(UploadRequest).where(UploadRequest.target == DS2)).scalars():
                s.delete(x)
            s.commit()
        # 버전이 없으면 다시 돌릴 워크플로가 없다(화면에 이 자료로 만든 수치가 없음)
        r = c.post(f"/admin/datasets/{DS2}/delete", json={"reason": "빈 정의 정리"})
        assert r.status_code == 200, r.text
        assert r.json()["rerun"] == [] and r.json()["removed"]["versions"] == 0 and r.json()["removed"]["triggersRemoved"] == 1
        with db() as s:
            assert s.get(Dataset, DS2) is None
            assert not any(e.type == "manual" and DS2 in (e.payload or {}).get("reason", "") for e in s.execute(select(OutboxEvent).where(OutboxEvent.dispatched_at.is_(None))).scalars())
    finally:
        _cleanup(db)
