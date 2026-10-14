"""Phase K 후속 (요구사항 §27 SCP-04 · Q156) — 사업부서 수행방안의 전파 경로를 종합기획부와 같은 흐름도로.

수행방안 화면(RISK_GUIDES)이 전파 트리 · 경영목표를 읽기만 하도록 리소스 cascade · goals 를 받는다.
목표 처리(goal_actions) · 수정 제안(proposals)은 여전히 종합기획부 전용."""
from __future__ import annotations

from fastapi.testclient import TestClient

OLD_RISK_GUIDES = ["analysis_tabs", "action_plans", "plan_state", "plan_actions", "reports"]


def _client() -> TestClient:
    from nhdip.main import app

    return TestClient(app)


def _login(c: TestClient, emp: str, pw: str):
    return c.post("/auth/login", json={"emp_no": emp, "password": pw})


def _admin() -> TestClient:
    a = _client()
    assert _login(a, "00000001", "Admin1234!").status_code == 200
    return a


def _user(admin: TestClient, emp: str, org: str) -> TestClient:
    c = _client()
    assert c.post("/auth/signup", json={"emp_no": emp, "name": f"사용자{emp[-2:]}", "password": "abcd1234", "org_code": org}).status_code == 201
    assert admin.post(f"/admin/users/{emp}/approve").status_code == 200
    assert _login(c, emp, "abcd1234").status_code == 200
    return c


def test_dept_user_reads_cascade_and_goals_only(db):
    """신용리스크관리부 사용자 — 전파 트리 · 경영목표는 읽고, 목표 처리 · 수정 제안은 못 본다."""
    admin = _admin()
    risk = _user(admin, "20271561", "T211")
    menu = risk.get("/me/menu").json()
    assert any(i["href"] == "/risk/guides" for s in menu["sections"] for i in s["flow"])

    cascade = risk.get("/screens/cascade")
    assert cascade.status_code == 200, cascade.text
    nodes = cascade.json()
    assert nodes and all(n["kind"] == "goal" for n in nodes)
    assert any(c["kind"] == "plan" for n in nodes for c in n.get("children") or [])
    goals = risk.get("/screens/goals")
    assert goals.status_code == 200
    goal_ids = {g["id"] for g in goals.json()}
    assert goal_ids and goal_ids & {n["id"] for n in nodes}  # 흐름도가 목표 노드의 확정 · 변경 상태를 목표 정의로 판정
    assert risk.get("/cascade/tree").status_code == 200

    # 읽기만 — 목표 처리 · 목표 상태 · 수정 제안은 종합기획부 전용 그대로
    assert risk.get("/screens/proposals").status_code == 403
    assert risk.get("/state/goals").status_code == 403
    r = risk.post("/state/goals/apply", json={"proposalId": "prop-corp-growth", "mode": "accept"})
    assert r.status_code == 403


def test_risk_cascade_upgrade_adds_resources_once(db):
    """기존 DB — 수행방안 리소스에 cascade · goals 를 1회 더한다. 이후 관리자가 회수하면 다시 넣지 않는다."""
    from nhdip.models import Setting
    from nhdip.seed.run import risk_cascade_upgrade

    with db() as s:
        res = s.get(Setting, "screen.resources")
        applied = s.get(Setting, "seed.applied_upgrades")
        before_res, before_applied = dict(res.value), list(applied.value)
        try:
            # 이전 기본값(Phase K 이전) · 보강 미적용 상태로 되돌린다
            res.value = {**before_res, "RISK_GUIDES": list(OLD_RISK_GUIDES)}
            applied.value = [x for x in before_applied if x != "risk-guides-cascade-v1"]
            s.flush()
            out: dict = {}
            risk_cascade_upgrade(s, out)
            assert out["risk_cascade_upgrade"] == ["cascade", "goals"]
            assert s.get(Setting, "screen.resources").value["RISK_GUIDES"] == OLD_RISK_GUIDES + ["cascade", "goals"]
            assert "risk-guides-cascade-v1" in s.get(Setting, "seed.applied_upgrades").value

            # 관리자가 회수 → 다시 시드해도 보존
            res.value = {**res.value, "RISK_GUIDES": list(OLD_RISK_GUIDES)}
            s.flush()
            out2: dict = {}
            risk_cascade_upgrade(s, out2)
            assert "risk_cascade_upgrade" not in out2
            assert s.get(Setting, "screen.resources").value["RISK_GUIDES"] == OLD_RISK_GUIDES
        finally:
            res.value, applied.value = before_res, before_applied
            s.commit()


def test_fresh_seed_risk_guides_resources():
    """새 DB 의 기본 화면 정의에도 같은 리소스가 있다(시드 정의 = 보강 결과)."""
    from nhdip.seed import defs_core as C

    spec = next(x for x in C.SCREENS if x["code"] == "RISK_GUIDES")
    assert {"cascade", "goals"} <= set(spec["resources"])
    assert "proposals" not in spec["resources"] and "goal_actions" not in spec["resources"]


def test_server_tree_marks_changed_goal():
    """서버 트리는 목표값이 바뀐 목표에 changed 를 단다 — 목표 처리 상태 권한 없는 사업부서 흐름도의 '최신' 표시."""
    from nhdip.views.cascade import build_tree

    base = [{"id": "g1", "kind": "goal", "label": "목표 7.0%", "children": []}, {"id": "g2", "kind": "goal", "label": "다른 목표 3.0%", "children": []}]
    goals = [{"id": "g1", "targetValue": 7.0, "unit": "PCT", "decimals": 1}, {"id": "g2", "targetValue": 3.0, "unit": "PCT"}]
    tree = build_tree(base, goals, {"overrides": {"g1": {"targetValue": 8.5}, "g2": {"targetValue": 3.0}}}, [])
    by = {n["id"]: n for n in tree}
    assert by["g1"]["changed"] is True and by["g1"]["label"] == "목표 8.5%" and "7.0% → 8.5%" in by["g1"]["detail"]
    assert "changed" not in by["g2"]  # 같은 값이면 변경 아님
