"""Phase E (UI/UX) — 관리자 첫 화면 · 관리자 처리 대기 건수 · 데이터 성격 표시 (요구사항 §22 · NAV-01 · NAV-04 · NAV-05)."""
from __future__ import annotations

from fastapi.testclient import TestClient


def _client() -> TestClient:
    from nhdip.main import app

    return TestClient(app)


def _login(c: TestClient, emp: str, pw: str):
    return c.post("/auth/login", json={"emp_no": emp, "password": pw})


def _admin() -> TestClient:
    c = _client()
    assert _login(c, "00000001", "Admin1234!").status_code == 200
    return c


def test_admin_home_and_pending_counts(db):
    admin = _client()
    r = _login(admin, "00000001", "Admin1234!")
    assert r.status_code == 200 and r.json()["home"] == "/admin"  # Q122 — 관리자는 관리자 홈부터
    assert admin.get("/me").json()["home"] == "/admin"
    before = admin.get("/me/menu").json()
    counts = before["counts"]
    for k in ("adminUsers", "adminUploads", "adminAnalyses", "adminTodo"):
        assert isinstance(counts[k], int)
    assert counts["adminTodo"] == counts["adminUsers"] + counts["adminUploads"] + counts["adminAnalyses"]
    # 관리자 화면에 건수 키(시드 기본값)
    keys = {i["code"]: i["countKey"] for sec in before["sections"] for i in [*sec["flow"], *sec["reference"]]}
    assert keys["ADMIN_HOME"] == "adminTodo" and keys["ADMIN_USERS"] == "adminUsers"
    assert keys["ADMIN_UPLOADS"] == "adminUploads" and keys["ADMIN_ANALYSIS_AGENTS"] == "adminAnalyses"
    # 가입 신청 1건 → 가입 승인 · 처리할 일 건수 +1
    u = _client()
    assert u.post("/auth/signup", json={"emp_no": "20259701", "name": "건수시험", "password": "abcd1234", "org_code": "T111"}).status_code == 201
    after = admin.get("/me/menu").json()["counts"]
    assert after["adminUsers"] == counts["adminUsers"] + 1 and after["adminTodo"] == counts["adminTodo"] + 1
    # 승인 후 업무 사용자 — 첫 화면은 업무 화면, 관리자 건수는 내려가지 않는다
    assert admin.post("/admin/users/20259701/approve").status_code == 200
    assert admin.get("/me/menu").json()["counts"]["adminUsers"] == counts["adminUsers"]
    r = _login(u, "20259701", "abcd1234")
    assert r.status_code == 200 and r.json()["home"] == "/hq/overview"
    menu = u.get("/me/menu").json()
    assert not any(k.startswith("admin") for k in menu["counts"])


def test_screen_for_path_and_upload_limit(db):
    """권한 없음 안내(NAV-04) — 주소 → 화면 이름 · 묶음 · 권한 여부(가장 길게 일치) · 업로드 용량 한도(UXF-01)."""
    admin = _admin()
    u = _client()
    assert u.post("/auth/signup", json={"emp_no": "20259702", "name": "안내시험", "password": "abcd1234", "org_code": "T111"}).status_code == 201
    assert admin.post("/admin/users/20259702/approve").status_code == 200
    assert _login(u, "20259702", "abcd1234").status_code == 200
    mine = set(u.get("/me").json()["screens"])
    r = u.get("/me/screen", params={"path": "/risk"}).json()
    # 권한 여부는 실제 화면 권한과 같다(다른 시험이 같은 부서에 권한을 줄 수 있어 고정값으로 보지 않음)
    assert r["screen"]["code"] == "RISK_HOME" and r["screen"]["section"] == "신용리스크관리부" and r["granted"] is ("RISK_HOME" in mine) and r["home"] == "/hq/overview"
    r = u.get("/me/screen", params={"path": "/risk/analysis/inclusive-risk"}).json()
    assert r["screen"]["code"] == "RISK_ANALYSIS"  # '=/risk'(정확히)보다 긴 접두어
    r = u.get("/me/screen", params={"path": "/knowledge/upload?target=X"}).json()
    assert r["screen"]["code"] == "KNOWLEDGE_UPLOAD" and r["granted"] is True  # /knowledge 보다 긴 일치 · 질의 문자열 무시
    r = u.get("/me/screen", params={"path": "/admin"}).json()
    assert r["screen"]["admin"] is True and r["granted"] is False
    assert u.get("/me/screen", params={"path": "/no-such-page"}).json()["screen"] is None
    assert _client().get("/me/screen", params={"path": "/risk"}).status_code == 401  # 로그인 필요
    assert u.get("/db/uploadable").json()["maxMb"] == 50


def test_menu_data_origin(db):
    from sqlalchemy import select

    from nhdip.api.auth import _data_origin
    from nhdip.models import source

    admin = _admin()
    got = admin.get("/me/menu").json()["dataOrigin"]
    assert got in {"simulated", "mixed", "actual", "none"}
    with db() as s:
        assert _data_origin(s) == got
        kinds = set()
        for origin in ("bank", "ext"):
            t = source(origin)
            kinds |= set(s.execute(select(t.version.data_origin).where(t.version.is_current)).scalars())
        # 시드는 모의 자료 — 실제 자료가 없으면 '모의'
        if kinds and "actual" not in kinds:
            assert got == "simulated"


def test_admin_counts_upgrade_preserves_admin_edits(db):
    from nhdip.models import Screen, Setting
    from nhdip.seed.run import admin_counts_upgrade

    with db() as s:
        users, uploads = s.get(Screen, "ADMIN_USERS"), s.get(Screen, "ADMIN_UPLOADS")
        old_users, old_uploads = users.count_key, uploads.count_key
        users.count_key, uploads.count_key = None, "custom"  # 이전 DB(키 없음) · 관리자가 바꾼 키
        st = s.get(Setting, "seed.applied_upgrades")
        st.value = [x for x in st.value if x != "admin-counts-v1"]
        s.flush()
        out: dict = {}
        admin_counts_upgrade(s, out)
        assert users.count_key == "adminUsers" and uploads.count_key == "custom"
        assert "ADMIN_USERS" in out["admin_counts_upgrade"] and "ADMIN_UPLOADS" not in out["admin_counts_upgrade"]
        out2: dict = {}
        admin_counts_upgrade(s, out2)  # 1회만
        assert "admin_counts_upgrade" not in out2
        s.rollback()
        assert s.get(Screen, "ADMIN_USERS").count_key == old_users and s.get(Screen, "ADMIN_UPLOADS").count_key == old_uploads
