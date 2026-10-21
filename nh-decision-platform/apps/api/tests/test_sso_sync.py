"""사내 SSO(NC 티켓) · 조직/인사 .dat 동기화 (Phase R)."""
from __future__ import annotations

import io
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

ADMIN = ("00000001", "Admin1234!")


def _client() -> TestClient:
    from nhdip.main import app

    return TestClient(app)


def _login(c: TestClient, emp: str, pw: str) -> None:
    from nhdip import ratelimit

    ratelimit.reset()
    assert c.post("/auth/login", json={"emp_no": emp, "password": pw}).status_code == 200


def _org(code, name, p1, p2, hq, region="01", use="Y", corp="1"):
    f = [corp, code, name, p1, f"{p1}명", p2, f"{p2}명", hq, f"{hq}명", "", "10", "3", region, "서울"] + [""] * 12 + [use, "", ""]
    assert len(f) == 29
    return "|".join(f)


def _emp(emp, name, office, p1="", p2="", p3="", corp="1", region="01"):
    f = [emp, name, corp, "1", "1", "05", "과장", "101", "팀장", "20200101", "", region, "서울", office, f"{office}명", p1, "", p2, "", p3, "", "", "", "", ""]
    return "|".join(f)


ORGS = "\n".join([
    _org("990100", "시험디지털본부", "990100", "990100", "990100"),
    _org("990110", "시험전략부", "990110", "990110", "990100"),
    _org("990111", "시험기획국", "990111", "990110", "990100"),
    _org("990112", "시험AI팀", "990111", "990110", "990100"),
    _org("990200", "시험서울지역본부", "990200", "990200", "990200"),
    _org("990201", "시험광화문지점", "990200", "990200", "990200"),
    _org("990299", "시험폐쇄지점", "990200", "990200", "990200", use="N"),
])
EMPS = [_emp("990000001", "김시험", "990112", "990111", "990110", "990100"), _emp("990000002", "이시험", "990201", "990200", "990200", "990200"),
        _emp("990000003", "박시험", "990112"), _emp("990000004", "최시험", "990201"), _emp("X99000005", "외부직원", "990112")]


def _up(c, kind, text, dry=False, enc="cp949"):
    return c.post(f"/admin/data-sync/{kind}", data={"dry_run": "true" if dry else "false"}, files={"file": (f"{kind}.dat", io.BytesIO(text.encode(enc)), "text/plain")})


@pytest.fixture()
def nc(monkeypatch):
    from nhdip.config import get_settings

    st = get_settings()
    for k, v in {"nc_sso_enabled": True, "nc_sso_verifier": "stub", "nc_sso_allowed_toa": "2,3"}.items():
        monkeypatch.setattr(st, k, v)
    return st


def _sso(c: TestClient, emp: str, toa: int = 3, nonce: str | None = None):
    r = c.get("/auth/nc/init", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/sso-proxy.html?"), r.headers
    q = parse_qs(urlparse(r.headers["location"]).query)
    assert q["callback"] == ["/backend/auth/nc/callback"] and q["stub"] == ["1"]
    return c.get("/auth/nc/callback", params={"ticket": f"stub:{emp}:{toa}:{nonce or q['nonce'][0]}", "nlsurl": "https://nls.example"}, follow_redirects=False)


def test_parsers_and_rules(db):
    from nhdip.orgsync import SyncError, decode, filter_rules, unit_type_of, type_rules
    from nhdip.models import Setting

    assert decode("가|나".encode("cp949"))[1] == "euc-kr" and decode("\ufeff가".encode("utf-8"))[1] == "utf-8-sig"
    with db() as s:
        rules = type_rules(s)
        assert [unit_type_of(n, rules) for n in ("광화문지점", "서울지역본부", "디지털본부", "전략부", "기획국", "AI팀", "기타")] == ["BRANCH", "REGION", "HQ_DIV", "DEPT", "BUREAU", "TEAM", None]
        st = s.get(Setting, "sync.filter_rules")
        st.value = [{"corpType": "1", "regionCodes": " 01, 02 "}]
        assert filter_rules(s) == [{"corpType": {"1"}, "regionCode": {"01", "02"}}]  # CSV trim (가이드 문제 8)
        st.value = [{"nope": "1"}]
        with pytest.raises(SyncError):
            filter_rules(s)  # 틀린 규칙이면 멈춘다(가이드 문제 7)
        s.rollback()


def test_org_emp_sync_and_sso(db, nc):
    from nhdip.models import AppUser, OrgUnit

    admin = _client()
    _login(admin, *ADMIN)
    # 미리보기 — 아무것도 바뀌지 않는다
    pv = _up(admin, "organization", ORGS, dry=True)
    assert pv.status_code == 200 and pv.json()["dryRun"] and pv.json()["inserted"] == 7 and pv.json()["encoding"] == "euc-kr", pv.text
    with db() as s:
        assert s.get(OrgUnit, "990100") is None
    r = _up(admin, "organization", ORGS)
    assert r.status_code == 200 and r.json()["inserted"] == 7 and not r.json()["errors"], r.text
    with db() as s:
        o = {c: s.get(OrgUnit, c) for c in ("990100", "990110", "990111", "990112", "990200", "990201", "990299")}
        assert o["990110"].parent_code == "990100" and o["990111"].parent_code == "990110" and o["990112"].parent_code == "990111"
        assert o["990201"].parent_code == "990200" and o["990201"].unit_type == "BRANCH" and o["990200"].unit_type == "REGION"
        assert o["990112"].level == 4 and o["990112"].unit_type == "TEAM" and o["990112"].source == "dat" and not o["990299"].active
    again = _up(admin, "organization", ORGS).json()
    assert again["inserted"] == 0 and again["unchanged"] == 7, again
    # 인사 — 조직이 없으면 그 행만 오류
    bad = _up(admin, "employee", _emp("990000009", "없는소속", "000000")).json()
    assert bad["inserted"] == 0 and "조직에 없습니다" in bad["errors"][0]
    e = _up(admin, "employee", "\n".join(EMPS)).json()
    assert e["inserted"] == 5 and not e["errors"], e
    with db() as s:
        u = s.get(AppUser, "990000001")
        assert u.source == "dat" and u.password_hash == "" and u.org_code == "990112" and u.position == "팀장" and u.status == "active" and u.hr["officeCode"] == "990112"
    # 사번 · 비밀번호 로그인은 안 된다(SSO 전용 · 실패 횟수도 올리지 않음)
    assert _client().post("/auth/login", json={"emp_no": "990000001", "password": "x"}).status_code == 401
    # SSO — 동기화된 사번만 · nonce · TOA 확인
    u1 = _client()
    ok = _sso(u1, "990000001")
    assert ok.status_code == 303 and "sso_error" not in ok.headers["location"], ok.headers
    me = u1.get("/me").json()
    assert me["user"]["empNo"] == "990000001" and me["user"]["source"] == "dat" and me["user"]["org"]["code"] == "990112"
    for emp, toa, nonce, code in (("990000001", 3, "WRONG", "nonce"), ("990000001", 92, None, "toa"), ("990009999", 3, None, "user_not_found")):
        r = _sso(_client(), emp, toa, nonce)
        assert r.status_code == 303 and r.headers["location"] == f"/login?sso_error={code}", (emp, r.headers)
    # 쿠키 없이(만료 · 다른 브라우저) 콜백 — 거부
    assert _client().get("/auth/nc/callback", params={"ticket": "stub:990000001:3:x"}, follow_redirects=False).headers["location"] == "/login?sso_error=state"
    # 다음 달 파일 — 1명 빠짐(4명 중 25%) → 사용 중지 + 세션 폐기 → SSO 거부. 외부 직원(영문)은 빠져도 그대로
    e2 = _up(admin, "employee", "\n".join(EMPS[1:4])).json()
    assert e2["deactivated"] == 1, e2
    with db() as s:
        assert s.get(AppUser, "990000001").status == "disabled" and s.get(AppUser, "X99000005").status == "active"
    assert u1.get("/me").status_code == 401
    assert _sso(_client(), "990000001").headers["location"] == "/login?sso_error=account"
    # 다시 파일에 오면 다시 켠다
    assert _up(admin, "employee", "\n".join(EMPS)).json()["reactivated"] == 1
    # 30% 안전장치 — 한 명만 든 파일로 대량 사용 중지하지 않는다
    guard = _up(admin, "employee", EMPS[0]).json()
    assert guard["deactivated"] == 0 and any("30%" in w for w in guard["warnings"]), guard
    ov = admin.get("/admin/data-sync").json()
    assert ov["orgs"]["dat"] >= 7 and ov["history"] and ov["sso"]["enabled"] and ov["sso"]["verifier"] == "stub"
    # 필터 규칙 저장 — 틀리면 거부
    assert admin.put("/admin/data-sync/settings", json={"filter_rules": [{"corpType": "1", "nope": 1}]}).status_code == 422
    assert admin.put("/admin/data-sync/settings", json={"filter_rules": [{"corpType": "1", "regionCode": "01"}]}).status_code == 200
    admin.put("/admin/data-sync/settings", json={"filter_rules": []})
    # 정리 — 다른 시험의 조직 · 사용자 목록에 섞이지 않게
    with db() as s:
        from sqlalchemy import delete

        from nhdip.models import UserSession

        s.execute(delete(UserSession).where(UserSession.emp_no.like("%99000%")))
        s.execute(delete(AppUser).where(AppUser.emp_no.in_([x.split("|")[0] for x in EMPS])))
        for c in ("990112", "990111", "990110", "990201", "990299", "990200", "990100"):
            s.execute(delete(OrgUnit).where(OrgUnit.code == c))
        s.commit()


def test_sso_disabled_and_assets(db, tmp_path, monkeypatch):
    from nhdip.config import get_settings

    c = _client()
    assert c.get("/auth/nc/config").json()["enabled"] is False
    assert c.get("/auth/nc/init", follow_redirects=False).headers["location"] == "/login?sso_error=disabled"
    (tmp_path / "NexessDemonFunc.js").write_text("var CONST_LOCAL_DEMON_ADDRESS='https://127.0.0.1:13015';", encoding="utf-8")
    monkeypatch.setattr(get_settings(), "nc_sso_assets_dir", str(tmp_path))
    assert c.get("/auth/nc/assets/NexessDemonFunc.js").status_code == 200
    assert c.get("/auth/nc/assets/..%2Fsecret.js").status_code == 404
    assert c.get("/auth/nc/assets/none.js").status_code == 404


def test_signup_with_hr_prefill(db, nc):
    """가입 화면 — 인사 동기화 사번이면 소속 자동 선택 · 가린 이름, 가입 = 비밀번호 로그인 신청(관리자 승인 · SSO 는 그대로)."""
    from sqlalchemy import delete

    from nhdip.models import AppUser, OrgUnit, UserSession

    admin = _client()
    _login(admin, *ADMIN)
    assert _up(admin, "organization", ORGS).status_code == 200
    assert not _up(admin, "employee", "\n".join(EMPS)).json()["errors"]
    try:
        c = _client()
        lk = c.get("/auth/signup/lookup", params={"emp_no": "990000001"}).json()
        assert lk == {"found": True, "name": "김*험", "orgCode": "990112", "orgPath": ["시험디지털본부", "시험전략부", "시험기획국", "시험AI팀"], "position": "팀장"}, lk
        assert c.get("/auth/signup/lookup", params={"emp_no": "00000001"}).json() == {"found": False, "registered": True}
        assert c.get("/auth/signup/lookup", params={"emp_no": "20999999"}).json() == {"found": False, "registered": False}
        assert c.get("/auth/signup/lookup", params={"emp_no": "../x"}).json() == {"found": False, "registered": False}
        body = {"emp_no": "990000001", "name": "김 시험", "password": "abcd1234", "org_code": "990201", "position": None}
        # 이름이 인사 정보와 다르면 거부 — 남의 사번에 비밀번호를 걸지 못하게
        assert c.post("/auth/signup", json={**body, "name": "홍길동"}).status_code == 422
        r = c.post("/auth/signup", json=body)
        assert r.status_code == 201 and r.json()["status"] == "pending", r.text
        with db() as s:
            u = s.get(AppUser, "990000001")
            assert u.org_code == "990112" and u.status == "active" and u.password_hash and u.hr["pwRequest"]  # 소속은 인사 정보 그대로
        assert c.post("/auth/signup", json=body).status_code == 409  # 두 번 신청 불가
        assert c.get("/auth/signup/lookup", params={"emp_no": "990000001"}).json()["pending"] is True
        assert _client().post("/auth/login", json={"emp_no": "990000001", "password": "abcd1234"}).status_code == 403  # 승인 대기
        assert "sso_error" not in _sso(_client(), "990000001").headers["location"]  # 신청 중에도 SSO 는 그대로
        row = next(x for x in admin.get("/admin/users", params={"status": "pending", "q": "990000001"}).json()["items"] if x["empNo"] == "990000001")
        assert row["passwordRequestAt"]
        from nhdip.api.menu_counts import admin_counts

        with db() as s:
            assert admin_counts(s)["adminUsers"] >= 1  # 관리자 처리 대기 건수에 들어간다
        # 인사 동기화를 다시 해도 신청은 남는다
        _up(admin, "employee", "\n".join(EMPS))
        assert admin.post("/admin/users/990000001/approve").status_code == 200
        assert _client().post("/auth/login", json={"emp_no": "990000001", "password": "abcd1234"}).status_code == 200
        # 반려 — 비밀번호만 지우고 계정(SSO)은 그대로
        c2 = _client()
        assert c2.post("/auth/signup", json={**body, "emp_no": "990000002", "name": "이시험"}).status_code == 201
        assert admin.post("/admin/users/990000002/reject").status_code == 200
        with db() as s:
            u2 = s.get(AppUser, "990000002")
            assert u2.status == "active" and u2.password_hash == "" and "pwRequest" not in u2.hr
        # 잠김(남이 비밀번호를 틀림)이어도 SSO 로 들어오면 풀린다
        with db() as s:
            s.get(AppUser, "990000001").status = "locked"
            s.commit()
        assert "sso_error" not in _sso(_client(), "990000001").headers["location"]
        with db() as s:
            assert s.get(AppUser, "990000001").status == "active"
        # 인사 정보에 없는 사번은 예전 그대로 8자리 규칙
        assert _client().post("/auth/signup", json={**body, "emp_no": "9900001"}).status_code == 422
    finally:
        with db() as s:
            s.execute(delete(UserSession).where(UserSession.emp_no.like("%99000%")))
            s.execute(delete(AppUser).where(AppUser.emp_no.in_([x.split("|")[0] for x in EMPS])))
            for code in ("990112", "990111", "990110", "990201", "990299", "990200", "990100"):
                s.execute(delete(OrgUnit).where(OrgUnit.code == code))
            s.commit()


def test_sync_from_pasted_text(db):
    """DRM 등으로 .dat 파일을 올릴 수 없을 때 — 메모장에서 복사한 본문(JSON)도 파일과 같은 검사 · 파서 · 결과."""
    from sqlalchemy import delete

    from nhdip.models import AppUser, AuditLog, OrgUnit, UserSession

    orgs = "\r\n".join([_org("980100", "붙임디지털본부", "980100", "980100", "980100"), _org("980110", "붙임전략부", "980110", "980110", "980100"),
                        _org("980111", "붙임AI팀", "980110", "980110", "980100")]) + "\r\n"  # 메모장 복사(CRLF · 끝 줄바꿈)
    emps = "\n".join([_emp("980000001", "김붙임", "980111", "980110", "980110", "980100"), _emp("980000002", "이붙임", "980110")])
    admin = _client()
    _login(admin, *ADMIN)
    try:
        pv = admin.post("/admin/data-sync/organization/text", json={"text": orgs, "dry_run": True})
        assert pv.status_code == 200 and pv.json()["dryRun"] and pv.json()["inserted"] == 3 and pv.json()["file"] == "붙여넣기 · 3줄", pv.text
        with db() as s:
            assert s.get(OrgUnit, "980100") is None  # 미리보기는 저장하지 않는다
        r = admin.post("/admin/data-sync/organization/text", json={"text": orgs}).json()
        assert r["inserted"] == 3 and not r["errors"] and r["encoding"] == "utf-8", r
        e = admin.post("/admin/data-sync/employee/text", json={"text": emps}).json()
        assert e["inserted"] == 2 and not e["errors"], e
        with db() as s:
            u = s.get(AppUser, "980000001")
            assert u.source == "dat" and u.org_code == "980111" and u.name == "김붙임"
            # 이력(감사)에는 건수만 — 본문(인사 정보)은 남기지 않는다
            a = s.query(AuditLog).filter(AuditLog.action == "admin.sync.employee").order_by(AuditLog.id.desc()).first()
            assert a.target_id == "붙여넣기 · 2줄" and "김붙임" not in str(a.detail)
        # 칸이 모자란 줄은 그 줄만 오류(파일과 같다) · 빈 본문 · 모르는 대상 · DRM 표지는 거부
        bad = admin.post("/admin/data-sync/employee/text", json={"text": "980000009|짧은줄|1", "dry_run": True}).json()
        assert bad["inserted"] == 0 and "필드 수 부족" in bad["errors"][0]
        assert admin.post("/admin/data-sync/employee/text", json={"text": ""}).status_code == 422
        assert admin.post("/admin/data-sync/branch/text", json={"text": "x"}).status_code == 404
        assert admin.post("/admin/data-sync/employee/text", json={"text": "DRMONE 암호화"}).status_code == 422
        # 관리자만
        assert _client().post("/admin/data-sync/employee/text", json={"text": emps}).status_code in (401, 403)
    finally:
        with db() as s:
            s.execute(delete(UserSession).where(UserSession.emp_no.like("98000000%")))
            s.execute(delete(AppUser).where(AppUser.emp_no.in_(["980000001", "980000002"])))
            for c in ("980111", "980110", "980100"):
                s.execute(delete(OrgUnit).where(OrgUnit.code == c))
            s.commit()
