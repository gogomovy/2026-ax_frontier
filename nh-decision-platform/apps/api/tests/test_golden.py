"""골든셋 평가 (작업 8.1 · QA-02) — 시드 + 선계산 직후 상태에서 모든 범주가 기준을 넘어야 한다. CI backend 잡에서 실행."""
from __future__ import annotations

from sqlalchemy import select


def _drain(SessionLocal):
    from nhdip.models import Job, utcnow
    from nhdip.worker import process_one
    from nhdip.workflow.dispatcher import dispatch_once

    with SessionLocal() as s:
        dispatch_once(s)
        for j in s.execute(select(Job).where(Job.status == "queued")).scalars():
            j.run_after = utcnow()
        s.commit()
    n = 0
    while n < 20 and process_one("golden"):
        n += 1


def test_golden_set(db):
    from nhdip.evals import run

    _drain(db)
    with db() as s:
        rep = run(s)
    bad = {k: v["failures"] for k, v in rep["categories"].items() if not v["ok"]}
    assert rep["passed"], bad
    assert rep["categories"]["metrics"]["total"] >= 25 and rep["categories"]["narration"]["total"] >= 10


def test_golden_admin_api(db):
    from fastapi.testclient import TestClient

    from nhdip.main import app

    c = TestClient(app)
    c.post("/auth/login", json={"emp_no": "00000001", "password": "Admin1234!"})
    r = c.post("/admin/evals/run").json()
    assert r["passed"] and set(r["categories"]) == {"metrics", "verdicts", "artifacts", "narration", "retrieval", "assist"}
    assert c.get("/admin/evals/latest").json()["at"] == r["at"]
