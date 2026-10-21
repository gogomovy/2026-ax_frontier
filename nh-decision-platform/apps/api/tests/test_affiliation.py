"""가입 승인 때 업무 소속 정하기 — 종합기획부 · 사업부서 · 영업본부 · 영업점 (ui.scopes · 조직 유형 기준).

인사 조직(.dat)의 팀 · 사무소는 화면 권한이 없을 수 있어, 관리자가 승인하면서 화면이 붙는 단위로 정한다.
정한 소속은 hr.orgAssigned 로 남아 인사 동기화가 사무소 기준으로 되돌리지 않는다."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

PW = "abcd1234"


def _client() -> TestClient:
    from nhdip import ratelimit
    from nhdip.main import app

    ratelimit.reset()
    return TestClient(app)


def _admin() -> TestClient:
    a = _client()
    assert a.post("/auth/login", json={"emp_no": "00000001", "password": "Admin1234!"}).status_code == 200
    return a


@pytest.fixture()
def orgs(db):
    """신용리스크관리부(D200) 아래 팀 · 화면이 없는 인사 조직(본부 유형, 최상위) · 사용 안 함 조직"""
    from nhdip.models import OrgUnit

    with db() as s:
        for code, name, typ, parent, active in [("AFT1", "소속시험팀", "TEAM", "D200", True), ("AFX1", "소속시험인사본부", "HQ_DIV", None, True), ("AFOFF", "소속시험폐쇄", "TEAM", "D200", False)]:
            if s.get(OrgUnit, code) is None:
                s.add(OrgUnit(code=code, name=name, unit_type=typ, parent_code=parent, level=2 if parent else 1, active=active, sort=990, source="dat" if code == "AFX1" else "manual"))
        s.commit()
    return db


def test_groups_and_suggestion(orgs):
    a = _admin()
    g = a.get("/admin/users/affiliations").json()["groups"]
    assert [x["key"] for x in g] == ["hq", "dept", "region", "branch"]
    by = {x["key"]: x for x in g}
    assert by["hq"]["label"] == "종합기획부" and [o["code"] for o in by["hq"]["options"]] == ["D100"]
    assert {o["code"] for o in by["dept"]["options"]} >= {"D200", "D310"} and by["dept"]["label"] == "사업부서"
    assert by["region"]["label"] == "영업본부" and all(o["unitType"] == "REGION" for o in by["region"]["options"])
    assert by["branch"]["search"] == {"types": ["BRANCH"]}

    c = _client()
    assert c.post("/auth/signup", json={"emp_no": "20259801", "name": "소속시험", "password": PW, "org_code": "AFT1"}).status_code == 201
    info = a.get("/admin/users/20259801/affiliation").json()
    # 신청 소속(팀) 경로에서 처음 맞는 단위 — 신용리스크관리부(사업부서)
    assert info["current"]["code"] == "AFT1" and info["suggested"]["group"] == "dept" and info["suggested"]["code"] == "D200"
    assert info["suggested"]["org"]["name"] and info["preview"]["org"]["code"] == "D200"
    hq = a.get("/admin/users/20259801/affiliation", params={"org": "D100"}).json()["preview"]
    assert hq["affiliation"]["group"] == "hq" and hq["screens"] and hq["home"]["path"].startswith("/")
    # 화면이 붙지 않는 인사 조직 — 영역 없음 · 화면 없음
    none = a.get("/admin/users/20259801/affiliation", params={"org": "AFX1"}).json()["preview"]
    assert none["affiliation"] is None and none["screens"] == [] and none["home"] is None


def test_approve_with_affiliation(orgs):
    a = _admin()
    c = _client()
    assert c.post("/auth/signup", json={"emp_no": "20259802", "name": "승인소속", "password": PW, "org_code": "AFT1"}).status_code == 201
    # 없는 · 쓰지 않는 조직은 거절하고 상태는 그대로
    assert a.post("/admin/users/20259802/approve", json={"org_code": "NOPE"}).status_code == 422
    assert a.post("/admin/users/20259802/approve", json={"org_code": "AFOFF"}).status_code == 422
    assert a.post("/admin/users/20259802/disable", json={"org_code": "D100"}).status_code == 422
    row = a.get("/admin/users", params={"status": "pending", "q": "20259802"}).json()["items"][0]
    assert row["status"] == "pending" and row["org"]["code"] == "AFT1" and row["orgAssigned"] is None
    preview = a.get("/admin/users/20259802/affiliation", params={"org": "D100"}).json()["preview"]
    r = a.post("/admin/users/20259802/approve", json={"org_code": "D100"})
    assert r.status_code == 200 and r.json()["org"]["code"] == "D100" and r.json()["status"] == "active"
    row = a.get("/admin/users", params={"q": "20259802"}).json()["items"][0]
    assert row["orgAssigned"]["code"] == "D100" and row["orgAssigned"]["from"] == "AFT1" and row["orgAssigned"]["by"] == "00000001"
    # 승인한 소속의 화면으로 로그인 — 미리보기와 같은 화면
    from nhdip import ratelimit

    ratelimit.reset()
    assert c.post("/auth/login", json={"emp_no": "20259802", "password": PW}).status_code == 200
    mine = set(c.get("/me").json()["screens"])
    assert {s["code"] for s in preview["screens"]} <= mine
    # 감사 기록에 소속 변경
    from sqlalchemy import select

    from nhdip.models import AuditLog

    with orgs() as s:
        log = s.execute(select(AuditLog).where(AuditLog.action == "admin.user.approve", AuditLog.target_id == "20259802").order_by(AuditLog.id.desc())).scalars().first()
        assert log is not None and log.detail == {"org": {"from": "AFT1", "to": "D100"}}
    # 소속 없이 승인(예전 방식)도 된다 — 신청 소속 그대로
    assert c.post("/auth/signup", json={"emp_no": "20259803", "name": "그대로", "password": PW, "org_code": "D310"}).status_code == 201
    r = a.post("/admin/users/20259803/approve")
    assert r.status_code == 200 and r.json()["org"]["code"] == "D310"


def _emp_line(emp: str, name: str, office: str) -> str:
    f = [emp, name, "1", "1", "1", "05", "과장", "101", "팀장", "20200101", "", "01", "서울", office, f"{office}명", "", "", "", "", "", "", "", "", "", ""]
    return "|".join(f)


def test_assigned_org_survives_hr_sync_and_follow_hr(orgs):
    from nhdip.models import AppUser

    a = _admin()
    with orgs() as s:
        if s.get(AppUser, "990009801") is None:
            s.add(AppUser(emp_no="990009801", name="동기화소속", password_hash="", org_code="AFX1", role="user", status="active", source="dat", hr={"officeCode": "AFX1", "officeName": "소속시험인사본부"}))
            s.commit()
    # 관리자가 사업부서로 — 표지가 남는다
    assert a.patch("/admin/users/990009801", json={"org_code": "D200"}).status_code == 200
    # 인사 동기화(같은 사무소 AFX1) — 소속은 그대로, 인사 정보는 갱신
    r = a.post("/admin/data-sync/employee/text", json={"text": _emp_line("990009801", "동기화소속", "AFX1"), "dry_run": False})
    assert r.status_code == 200, r.text
    assert r.json()["keptAssigned"] == 1 and any("유지" in w for w in r.json()["warnings"])
    row = a.get("/admin/users", params={"q": "990009801"}).json()["items"][0]
    assert row["org"]["code"] == "D200" and row["orgAssigned"]["code"] == "D200" and row["hrOffice"]["code"] == "AFX1"
    # 인사 기준으로 — 표지를 풀고 사무소로
    assert a.patch("/admin/users/990009801", json={"follow_hr": True}).status_code == 200
    row = a.get("/admin/users", params={"q": "990009801"}).json()["items"][0]
    assert row["org"]["code"] == "AFX1" and row["orgAssigned"] is None
    assert a.patch("/admin/users/990009801", json={"org_code": "D200", "follow_hr": True}).status_code == 422


def test_admin_password_reset_route(orgs):
    """POST /admin/users/{사번}/password 가 작업 경로(/{action})에 가려 404 가 나던 문제"""
    a = _admin()
    c = _client()
    assert c.post("/auth/signup", json={"emp_no": "20259804", "name": "비번초기화", "password": PW, "org_code": "D310"}).status_code == 201
    assert a.post("/admin/users/20259804/approve").status_code == 200
    assert a.post("/admin/users/20259804/password", json={"password": "short"}).status_code == 422
    assert a.post("/admin/users/20259804/password", json={"password": "newpass1234"}).status_code == 200
    from nhdip import ratelimit

    ratelimit.reset()
    assert c.post("/auth/login", json={"emp_no": "20259804", "password": "newpass1234"}).status_code == 200
