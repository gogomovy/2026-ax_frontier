"""인사 동기화 규모(조직 · 사용자 수천 건)의 관리자 [사용자] · [조직] API — 서버 페이지 · 검색 · 탭 건수 · 조직 검색.

예전에는 /admin/users 가 전체 사용자를, 화면은 행마다 전체 조직 선택 상자를 그려 승인 대기 목록이 '불러오는 중'에서 멈췄다."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, event

N_BR = 300
N_USERS = 1500
EMP = "77{:06d}".format


def _admin() -> TestClient:
    from nhdip import ratelimit
    from nhdip.main import app

    ratelimit.reset()
    c = TestClient(app)
    assert c.post("/auth/login", json={"emp_no": "00000001", "password": "Admin1234!"}).status_code == 200
    return c


@pytest.fixture()
def world(db):
    """지역본부 2곳 · 영업점 300곳 · 사용자 1,500명(승인 대기 30 · 잠김 10 · 비밀번호 로그인 신청 5). 끝나면 지운다(다른 시험의 건수에 섞이지 않게)."""
    from nhdip.models import AppUser, OrgUnit

    with db() as s:
        s.add_all([
            OrgUnit(code="SCLR1", name="규모시험지역본부", unit_type="REGION", level=1, parent_code=None, active=True, sort=901),
            OrgUnit(code="SCLR2", name="규모시험남부본부", unit_type="REGION", level=1, parent_code=None, active=True, sort=902),
        ])
        s.flush()
        s.add_all([OrgUnit(code=f"SCLB{i:04d}", name=f"규모{i:04d}지점", unit_type="BRANCH", level=2, parent_code="SCLR1" if i % 2 == 0 else "SCLR2", active=i != 7, sort=i) for i in range(N_BR)])
        s.flush()
        s.add_all([
            AppUser(emp_no=EMP(i), name=f"규모{i:04d}", password_hash="", org_code=f"SCLB{i % N_BR:04d}", role="user",
                    status="pending" if i < 30 else "locked" if i < 40 else "active",
                    hr={"pwRequest": {"at": "2026-10-01T00:00:00+00:00"}} if 1000 <= i < 1005 else {})
            for i in range(N_USERS)
        ])
        s.commit()
    yield
    with db() as s:
        s.execute(delete(AppUser).where(AppUser.emp_no.like("77%"), AppUser.name.like("규모%")))
        s.execute(delete(OrgUnit).where(OrgUnit.code.like("SCLB%")))
        s.execute(delete(OrgUnit).where(OrgUnit.code.in_(["SCLR1", "SCLR2"])))
        s.commit()


def _queries(fn):
    """요청 하나가 DB 에 보낸 질의 수 — 사용자마다 조직을 따로 읽는(N+1) 회귀를 잡는다."""
    from nhdip.db import engine

    n = {"q": 0}

    def count(*_a, **_k):
        n["q"] += 1

    event.listen(engine, "before_cursor_execute", count)
    try:
        r = fn()
    finally:
        event.remove(engine, "before_cursor_execute", count)
    return r, n["q"]


def test_users_paged_counts_search(world):
    a = _admin()
    r = a.get("/admin/users", params={"status": "pending", "q": "규모", "size": 20})
    assert r.status_code == 200, r.text
    d = r.json()
    # 탭 건수는 같은 검색 조건 기준 — 승인 대기 = 가입 대기 30 + 비밀번호 로그인 신청 5
    assert d["counts"] == {"pending": 35, "active": 1460, "locked": 10, "disabled": 0, "all": 1500}, d["counts"]
    assert d["total"] == 35 and d["page"] == 1 and len(d["items"]) == 20
    assert all(u["status"] == "pending" or u["passwordRequestAt"] for u in d["items"])
    assert d["items"][0]["status"] == "pending"  # 가입 대기가 먼저
    # 끝을 넘는 쪽 → 마지막 쪽(승인으로 목록이 줄어든 뒤에도 빈 화면이 아니게)
    last = a.get("/admin/users", params={"status": "pending", "q": "규모", "size": 20, "page": 99}).json()
    assert last["page"] == 2 and len(last["items"]) == 15
    # 사번 · 소속 경로 · 신청 시각
    one = a.get("/admin/users", params={"q": EMP(1003)}).json()
    assert one["total"] == 1 and one["items"][0]["passwordRequestAt"]
    assert [o["name"] for o in one["items"][0]["orgPath"]] == ["규모시험남부본부", "규모0103지점"]  # 1003 % 300 = 103(홀수 → 남부)
    # LIKE 특수 문자는 글자 그대로
    assert a.get("/admin/users", params={"q": "규모%"}).json()["counts"]["all"] == 0
    # 잘못된 값
    assert a.get("/admin/users", params={"status": "nope"}).status_code == 422
    assert a.get("/admin/users", params={"size": 500}).status_code == 422


def test_users_org_filter_includes_children(world):
    a = _admin()
    region = a.get("/admin/users", params={"org": "SCLR1", "size": 5}).json()
    assert region["counts"]["all"] == 750 and len(region["items"]) == 5  # 짝수 영업점 150곳 × 5명
    branch = a.get("/admin/users", params={"org": "SCLB0001"}).json()
    assert branch["total"] == 5 and {u["org"]["code"] for u in branch["items"]} == {"SCLB0001"}
    assert a.get("/admin/users", params={"org": "NOPE"}).json()["total"] == 0


def test_users_page_query_count_is_flat(world):
    """한 쪽 50명 — 소속 경로를 사용자마다 읽지 않는다(질의 수가 사용자 수에 비례하지 않음)."""
    a = _admin()
    r, n = _queries(lambda: a.get("/admin/users", params={"status": "active", "q": "규모", "size": 50}))
    assert r.status_code == 200 and len(r.json()["items"]) == 50
    assert n <= 25, n


def test_org_lookup(world):
    a = _admin()
    # 앞부분 일치가 먼저 · total 은 잘리기 전 건수 · 상위 경로
    d = a.get("/admin/orgs/lookup", params={"q": "규모00", "limit": 5}).json()
    assert d["total"] == 99 and len(d["items"]) == 5  # 규모0000~0099지점 중 사용 안 함(0007) 제외
    assert d["items"][0]["code"] == "SCLB0000" and d["items"][0]["path"] == ["규모시험지역본부"] and d["items"][0]["unitLabel"] == "영업점"
    # 코드 정확 일치가 맨 앞
    assert a.get("/admin/orgs/lookup", params={"q": "sclb0123"}).json()["items"][0]["code"] == "SCLB0123"
    # 상위 조직 이름으로도 — 낱말마다 모두 맞아야
    both = a.get("/admin/orgs/lookup", params={"q": "남부본부 규모0001", "limit": 100}).json()
    assert [o["code"] for o in both["items"]] == ["SCLB0001"]
    # 사용 안 함은 기본 제외, inactive=1 이면 포함
    assert not a.get("/admin/orgs/lookup", params={"q": "규모0007"}).json()["items"]
    assert a.get("/admin/orgs/lookup", params={"q": "규모0007", "inactive": "true"}).json()["items"][0]["active"] is False
    # 유형 제한(상위 조직 고르기) · 자기와 하위 제외
    regions = a.get("/admin/orgs/lookup", params={"q": "규모시험", "types": "REGION"}).json()
    assert {o["code"] for o in regions["items"]} == {"SCLR1", "SCLR2"}
    ex = a.get("/admin/orgs/lookup", params={"q": "규모", "exclude": "SCLR1", "limit": 100}).json()
    assert ex["total"] == 150 and all(o["path"] != ["규모시험지역본부"] and o["code"] != "SCLR1" for o in ex["items"])
    # 현재 값 표시 — 코드로 바로
    got = a.get("/admin/orgs/lookup", params={"codes": "SCLB0002,SCLR2,NOPE"}).json()
    assert [o["code"] for o in got["items"]] == ["SCLB0002", "SCLR2"]
    assert a.get("/admin/orgs/lookup", params={"limit": 101}).status_code == 422
