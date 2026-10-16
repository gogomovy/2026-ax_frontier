"""확정한 목표 변경 되돌리기 · 다시 수정 · 삭제(소프트) — 사유 필수, 이력은 지우지 않고 새 버전으로만 쌓는다."""
from __future__ import annotations

from fastapi.testclient import TestClient

from test_integration import _drain

GOAL = "goal-corp-growth"
PROP = "prop-corp-growth"
REASON = "지주 협의 결과에 따라 조정"


def _client() -> TestClient:
    from nhdip.main import app

    return TestClient(app)


def _admin() -> TestClient:
    c = _client()
    assert c.post("/auth/login", json={"emp_no": "00000001", "password": "Admin1234!"}).status_code == 200
    return c


def _base(c: TestClient) -> dict:
    return next(g for g in c.get("/screens/goals").json() if g["id"] == GOAL)


def _restore_base(c: TestClient) -> None:
    """뒤 시험(골든 등)이 기준 목표값을 보도록 규칙 값까지 기준 버전으로 돌려 두고 처리 상태를 비운다."""
    if GOAL in c.get("/state/goals").json()["overrides"]:
        assert c.post("/state/goals/revert", json={"goalId": GOAL, "toVersion": _base(c)["version"], "reason": REASON}).status_code == 200
    c.post("/state/goals/reset")


def _hist(c: TestClient, gid: str = GOAL) -> list[dict]:
    return c.get(f"/state/goals/{gid}/history").json()


def test_revert_and_edit_append_versions(db):
    _drain(db)
    c = _admin()
    c.post("/state/goals/reset")
    base = _base(c)
    b, base_value = base["version"], base["targetValue"]

    st = c.post("/state/goals/apply", json={"proposalId": PROP, "mode": "manual_edit", "value": 8.0}).json()
    assert st["overrides"][GOAL]["version"] == b + 1 and st["proposalActions"][PROP] == "manual_edit"

    # 다시 수정 — 경고(기조 반대)는 409, 경고 확인(force) 후 새 버전
    r = c.post("/state/goals/edit", json={"goalId": GOAL, "value": 7.8, "reason": REASON})
    assert r.status_code == 409 and r.json()["detail"]["issues"]
    st = c.post("/state/goals/edit", json={"goalId": GOAL, "value": 7.8, "reason": REASON, "force": True}).json()
    ov = st["overrides"][GOAL]
    assert ov["version"] == b + 2 and ov["targetValue"] == 7.8 and ov["creationMode"] == "user_manual"
    assert st["proposalActions"][PROP] == "manual_edit"  # 다시 수정은 제안 처리 상태를 건드리지 않는다
    before = _hist(c)

    # 되돌리기(기본 = 바로 앞 버전) — 8.0 이 v(b+3) 으로 다시 기록되고, 이전 기록은 그대로
    st = c.post("/state/goals/revert", json={"goalId": GOAL, "reason": REASON}).json()
    ov = st["overrides"][GOAL]
    assert ov["version"] == b + 3 and ov["targetValue"] == 8.0
    assert PROP not in st["proposalActions"]  # 제안을 다시 검토할 수 있다
    hist = _hist(c)
    assert len(hist) == len(before) + 1 and hist[1:] == before
    top = hist[0]
    assert top["action"] == "goal.revert" and top["version"] == b + 3 and top["restoredVersion"] == b + 1
    assert top["value"] == 8.0 and top["fromValue"] == 7.8 and top["reason"] == REASON and top["actorName"]
    assert [h["version"] for h in hist if h["action"] in ("goal.apply", "goal.edit")] == [b + 2, b + 1]

    # 특정 이전 버전으로 — v(b+2)(7.8)
    st = c.post("/state/goals/revert", json={"goalId": GOAL, "toVersion": b + 2, "reason": REASON}).json()
    assert st["overrides"][GOAL]["version"] == b + 4 and st["overrides"][GOAL]["targetValue"] == 7.8

    # 기준 버전으로 — 기준값으로 돌아가되 새 버전으로 기록
    st = c.post("/state/goals/revert", json={"goalId": GOAL, "toVersion": b, "reason": REASON}).json()
    ov = st["overrides"][GOAL]
    assert ov["version"] == b + 5 and ov["targetValue"] == base_value and ov["creationMode"] == base["creationMode"]
    assert len(ov["versions"]) == 5 and _hist(c)[0]["restoredVersion"] == b

    # 현재 버전 · 없는 버전은 되돌릴 수 없다
    assert c.post("/state/goals/revert", json={"goalId": GOAL, "toVersion": b + 5, "reason": REASON}).status_code == 422
    assert c.post("/state/goals/revert", json={"goalId": GOAL, "toVersion": b + 99, "reason": REASON}).status_code == 422
    _restore_base(c)


def test_reason_required_unknown_goal_and_permissions(db):
    _drain(db)
    c = _admin()
    c.post("/state/goals/reset")
    c.post("/state/goals/apply", json={"proposalId": PROP, "mode": "manual_edit", "value": 8.0})
    for path, extra in [("/state/goals/revert", {}), ("/state/goals/edit", {"value": 7.9}), ("/state/goals/delete", {})]:
        for reason in [None, "", "    ", "짧음"]:
            body = {"goalId": GOAL, **extra, **({} if reason is None else {"reason": reason})}
            r = c.post(path, json=body)
            assert r.status_code == 422, (path, reason)
            assert "자 이상 입력하세요" in r.json()["detail"]["message"]
        assert c.post(path, json={"goalId": "goal-unknown-x", **extra, "reason": REASON}).status_code == 404, path
    # 처리한 적 없는 목표는 되돌릴 것이 없다
    other = next(g["id"] for g in c.get("/screens/goals").json() if g["id"] != GOAL and g["id"] not in c.get("/state/goals").json()["overrides"])
    assert c.post("/state/goals/revert", json={"goalId": other, "reason": REASON}).status_code == 422

    # 권한 — apply 와 같다 (goal_actions 없는 사업부서 · 영업점 사용자는 403)
    for emp, org in [("20271571", "T211"), ("20259071", "BR301")]:
        u = _client()
        assert u.post("/auth/signup", json={"emp_no": emp, "name": f"사용자{emp[-2:]}", "password": "abcd1234", "org_code": org}).status_code == 201
        assert c.post(f"/admin/users/{emp}/approve").status_code == 200
        assert u.post("/auth/login", json={"emp_no": emp, "password": "abcd1234"}).status_code == 200
        assert u.post("/state/goals/apply", json={"proposalId": PROP, "mode": "adopt"}).status_code == 403
        for path, extra in [("/state/goals/revert", {}), ("/state/goals/edit", {"value": 7.9}), ("/state/goals/delete", {})]:
            assert u.post(path, json={"goalId": GOAL, **extra, "reason": REASON}).status_code == 403, (emp, path)
    _restore_base(c)


def test_soft_delete_and_restore(db):
    _drain(db)
    c = _admin()
    c.post("/state/goals/reset")
    b = _base(c)["version"]
    c.post("/state/goals/apply", json={"proposalId": PROP, "mode": "manual_edit", "value": 8.0})

    st = c.post("/state/goals/delete", json={"goalId": GOAL, "reason": REASON}).json()
    ov = st["overrides"][GOAL]
    assert ov["status"] == "archived" and ov["version"] == b + 2 and ov["targetValue"] == 8.0
    assert ov["versions"][-1]["creationMode"] == "delete" and ov["versions"][-1]["reason"] == REASON
    hist = _hist(c)
    assert hist[0]["action"] == "goal.delete" and hist[0]["version"] == b + 2 and hist[1]["action"] == "goal.apply"
    assert c.post("/state/goals/delete", json={"goalId": GOAL, "reason": REASON}).status_code == 422  # 이미 삭제
    assert c.post("/state/goals/edit", json={"goalId": GOAL, "value": 7.9, "reason": REASON}).status_code == 422

    # 이력에서 삭제 전 버전으로 복원 — 새 버전으로 되살린다
    st = c.post("/state/goals/revert", json={"goalId": GOAL, "toVersion": b + 1, "reason": REASON}).json()
    ov = st["overrides"][GOAL]
    assert ov["status"] == "active" and ov["version"] == b + 3 and ov["targetValue"] == 8.0

    # 직접 추가한 목표도 보관 처리
    st = c.post("/state/goals/manual", json={"title": "시험 목표", "targetLabel": "10건", "periodLabel": "연간"}).json()
    gid = st["addedGoals"][-1]["id"]
    st = c.post("/state/goals/delete", json={"goalId": gid, "reason": REASON}).json()
    added = next(g for g in st["addedGoals"] if g["id"] == gid)
    assert added["status"] == "archived" and added["archiveReason"] == REASON
    assert _hist(c, gid)[0]["action"] == "goal.delete"
    _restore_base(c)
