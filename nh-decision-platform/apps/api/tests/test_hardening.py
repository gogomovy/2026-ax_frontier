"""점검 보완 (B.32) — CSRF 출처 검사 · 보안 헤더 · 초기화 권한 · 진행사업 소유 · 속도 제한 · SSRF · 열린 리디렉션."""
from __future__ import annotations

from fastapi.testclient import TestClient


def _client():
    from nhdip.main import app

    return TestClient(app)


def _login(c: TestClient, emp: str, pw: str):
    return c.post("/auth/login", json={"emp_no": emp, "password": pw})


def _user(admin: TestClient, emp: str, org: str) -> TestClient:
    c = _client()
    assert c.post("/auth/signup", json={"emp_no": emp, "name": f"사용자{emp[-2:]}", "password": "abcd1234", "org_code": org}).status_code == 201
    assert admin.post(f"/admin/users/{emp}/approve").status_code == 200
    assert _login(c, emp, "abcd1234").status_code == 200
    return c


def _admin() -> TestClient:
    a = _client()
    assert _login(a, "00000001", "Admin1234!").status_code == 200
    return a


def test_csrf_origin_and_security_headers(db):
    c = _client()
    # 다른 출처의 변경 요청은 차단, 같은 출처 · Origin 없음은 통과
    r = c.post("/auth/login", json={"emp_no": "00000001", "password": "Admin1234!"}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    assert c.post("/auth/login", json={"emp_no": "00000001", "password": "Admin1234!"}, headers={"Origin": "null"}).status_code == 403
    assert c.post("/auth/login", json={"emp_no": "00000001", "password": "Admin1234!"}, headers={"Origin": "http://testserver"}).status_code == 200
    # 프록시(Next) 경유 — X-Forwarded-Host 가 브라우저 출처와 같으면 통과
    r = c.post("/auth/logout", headers={"Origin": "http://localhost:3000", "X-Forwarded-Host": "localhost:3000"})
    assert r.status_code != 403
    h = c.get("/health")
    assert h.headers["X-Frame-Options"] == "DENY" and h.headers["X-Content-Type-Options"] == "nosniff"
    assert "error" not in h.json() or h.json()["error"] == "db unavailable"


def test_runtime_guard_and_docs_toggle():
    from nhdip.config import DEFAULT_SESSION_SECRET, Settings, check_runtime, docs_enabled

    import pytest

    with pytest.raises(RuntimeError):
        check_runtime(Settings(nhdip_env="prod", session_secret=DEFAULT_SESSION_SECRET))
    with pytest.raises(RuntimeError):
        check_runtime(Settings(nhdip_env="prod", session_secret="short"))
    check_runtime(Settings(nhdip_env="prod", session_secret="x" * 40))
    check_runtime(Settings(nhdip_env="dev"))
    assert docs_enabled(Settings(nhdip_env="dev")) and not docs_enabled(Settings(nhdip_env="prod"))
    assert docs_enabled(Settings(nhdip_env="prod", api_docs="true"))


def test_reset_admin_only_and_plan_ownership(db):
    admin = _admin()
    risk = _user(admin, "20259101", "T211")  # 신용리스크관리부 — 진행사업 권한
    plan = risk.post("/state/plans", json={"title": "리스크 방안", "body": "본문"}).json()
    pid = plan["id"]
    mine = next(p for p in plan["userPlans"] if p["id"] == pid)
    assert mine["ownerOrg"] == "신용리스크관리부" and mine["createdBy"] == "20259101"
    # 화면 입력 ownerOrg 는 일반 사용자에게 무시된다
    other = risk.post("/state/plans", json={"title": "x", "body": "y", "ownerOrg": "종합기획부"}).json()
    assert next(p for p in other["userPlans"] if p["id"] == other["id"])["ownerOrg"] == "신용리스크관리부"
    # 같은 부서(다른 팀)는 수정 가능
    peer = _user(admin, "20259102", "T212")
    assert peer.patch(f"/state/plans/{pid}", json={"title": "수정"}).status_code == 200
    # 다른 부서에 진행사업 권한을 줘도 남의 부서 사업은 못 고친다
    assert admin.put("/admin/screens/grants", json={"org_code": "B110", "screen_code": "RISK_GUIDES", "granted": True}).status_code == 200
    plan_dept = _user(admin, "20259103", "T111")
    assert plan_dept.patch(f"/state/plans/{pid}", json={"title": "탈취"}).status_code == 403
    assert plan_dept.delete(f"/state/plans/{pid}").status_code == 403
    assert plan_dept.post(f"/state/plans/{pid}/toggle-share").status_code == 403
    # 전체 초기화는 관리자만
    assert risk.post("/state/plans/reset").status_code == 403
    assert admin.post("/state/plans/reset").status_code == 200
    assert admin.put("/admin/screens/grants", json={"org_code": "B110", "screen_code": "RISK_GUIDES", "granted": False}).status_code == 200


def test_login_rate_limit_and_timed_unlock(db):
    from nhdip.db import SessionLocal
    from nhdip.models import AppUser, Setting

    c = _client()
    c.post("/auth/signup", json={"emp_no": "20259104", "name": "속도", "password": "abcd1234", "org_code": "T211"})
    codes = [_login(c, "20259199", "wrong999").status_code for _ in range(11)]
    assert codes[-1] == 429 and "Retry-After" in c.post("/auth/login", json={"emp_no": "20259199", "password": "x"}).headers
    # 잠금 메시지에 실패 횟수를 드러내지 않는다
    msgs = [_login(c, "20259104", "wrong999").json().get("detail") for _ in range(3)]
    import re

    assert all(not re.search(r"\d", str(m)) for m in msgs)
    # 잠금 → 설정 시간이 지나면 자동 해제
    with SessionLocal() as s:
        u = s.get(AppUser, "20259104")
        u.status, u.failed_count = "locked", 5
        st = s.get(Setting, "auth.lockout_minutes")
        st.value = 0
        s.commit()
    from nhdip import ratelimit

    ratelimit.reset()
    assert _login(c, "20259104", "abcd1234").status_code == 423  # 0 = 관리자만 해제
    with SessionLocal() as s:
        s.get(Setting, "auth.lockout_minutes").value = 30
        u = s.get(AppUser, "20259104")
        from datetime import timedelta

        from nhdip.models import utcnow

        u.updated_at = utcnow() - timedelta(minutes=31)
        s.commit()
    assert _login(c, "20259104", "abcd1234").status_code == 200


def test_llm_connection_ssrf_guard_and_open_redirect(db):
    admin = _admin()
    for bad in ["http://169.254.169.254/latest", "file:///etc/passwd", "http://metadata.google.internal/", "http://[fe80::1]/"]:
        r = admin.post("/admin/llm/connections", json={"name": "bad", "base_url": bad})
        assert r.status_code == 422, bad
    r = admin.post("/admin/llm/connections", json={"name": "gw", "base_url": "http://10.1.2.3:4000"})
    assert r.status_code == 201  # 사내 사설 대역 게이트웨이는 허용
    assert admin.patch(f"/admin/llm/connections/{r.json()['id']}", json={"base_url": "http://169.254.0.1"}).status_code == 422
    from nhdip.api.oidc import _safe_next

    assert _safe_next("/hq/goals?x=1") == "/hq/goals?x=1"
    for bad in ["//evil.example", "/\\evil.example", "https://evil.example", "/a b", "/\x00x"]:
        assert _safe_next(bad) == "", bad


# ═════════════════════════ 신뢰성 ═════════════════════════
def test_merge3_keeps_concurrent_changes():
    from nhdip.views.store import merge3

    base = {"a": 1, "b": {"x": 1, "y": 1}, "items": [{"id": "i1", "v": 1}, {"id": "i2", "v": 1}], "gone": 1}
    ours = {"a": 2, "b": {"x": 2, "y": 1}, "items": [{"id": "i1", "v": 2}, {"id": "i2", "v": 1}, {"id": "i3", "v": 1}]}
    theirs = {"a": 1, "b": {"x": 1, "y": 9}, "items": [{"id": "i0", "v": 0}, {"id": "i1", "v": 1}, {"id": "i2", "v": 7}], "gone": 1, "new": True}
    m = merge3(base, ours, theirs)
    assert m["a"] == 2 and m["b"] == {"x": 2, "y": 9} and m["new"] is True and "gone" not in m
    assert [(i["id"], i["v"]) for i in m["items"]] == [("i0", 0), ("i1", 2), ("i2", 7), ("i3", 1)]
    assert merge3(base, base, theirs) == theirs and merge3(base, ours, base) == ours


def test_recover_stale_respects_live_heartbeat(db):
    from datetime import timedelta

    from nhdip.models import Job, WorkerHeartbeat, WorkflowRun, new_id, utcnow
    from nhdip.workflow.dispatcher import recover_stale

    with db() as s:
        old = utcnow() - timedelta(minutes=45)
        live = Job(kind="workflow", workflow_code="wf_x_live", causes=[], status="running", locked_by="live:1", locked_at=old)
        dead = Job(kind="workflow", workflow_code="wf_x_dead", causes=[], status="running", locked_by="dead:1", locked_at=old)
        s.add_all([live, dead])
        s.merge(WorkerHeartbeat(worker_id="live:1", seen_at=utcnow(), info={}))
        s.merge(WorkerHeartbeat(worker_id="dead:1", seen_at=old, info={}))
        s.flush()
        run = WorkflowRun(id=new_id(), workflow_code="wf_x_dead", job_id=dead.id, status="running", causes=[])
        s.add(run)
        s.commit()
        assert recover_stale(s) == 1
        s.expire_all()
        assert s.get(Job, live.id).status == "running" and s.get(Job, dead.id).status == "queued"
        assert s.get(WorkflowRun, run.id).status == "failed"
        s.delete(s.get(Job, live.id))
        s.delete(s.get(Job, dead.id))
        s.commit()


def test_dispatch_blocks_cycles_and_depth(db):
    from nhdip.events import emit
    from nhdip.models import OutboxEvent
    from nhdip.workflow.dispatcher import dispatch_once

    with db() as s:
        dispatch_once(s)
        emit(s, "agent.followup", {"workflow": "wf_branch_kpi", "chain": ["wf_branch_kpi"], "by": "planner"}, "planner")
        emit(s, "agent.followup", {"workflow": "wf_hq_goal_review", "chain": ["wf_a", "wf_b", "wf_c"], "by": "planner"}, "planner")
        s.commit()
        dispatch_once(s)
        evs = s.query(OutboxEvent).filter(OutboxEvent.type == "agent.followup").order_by(OutboxEvent.id.desc()).limit(2).all()
        depth, cycle = evs[0], evs[1]
        assert cycle.matched and cycle.matched[0].get("blocked", "").startswith("순환 방지")
        assert depth.matched and "최대 연쇄" in depth.matched[0].get("blocked", "")


def test_retention_purge_keeps_current_and_audit(db):
    from datetime import timedelta

    from nhdip.models import AuditLog, LlmCall, Setting, ViewArtifact, utcnow
    from nhdip.retention import purge
    from nhdip.views.store import publish

    with db() as s:
        for i in range(5):
            publish(s, "test.retention", {"i": i}, produced_by="test")
            s.flush()
        s.add(LlmCall(id="oldcall0000000000000000000000001", purpose="test", created_at=utcnow() - timedelta(days=400)))
        s.add(AuditLog(actor="t", action="test.keep", at=utcnow() - timedelta(days=4000)))
        st = s.get(Setting, "retention.policy")
        if st is None:
            s.add(Setting(key="retention.policy", value={"artifact_generations": 2}))
        else:
            st.value = {**st.value, "artifact_generations": 2}
        s.commit()
        out = purge(s)
        gens = sorted(g for (g,) in s.query(ViewArtifact.generation).filter(ViewArtifact.key == "test.retention"))
        assert gens == [2, 3, 4] and out["view_artifact"] >= 2
        assert s.get(LlmCall, "oldcall0000000000000000000000001") is None
        assert s.query(AuditLog).filter(AuditLog.action == "test.keep").count() == 1
        s.get(Setting, "retention.policy").value = {**s.get(Setting, "retention.policy").value, "artifact_generations": 50}
        s.commit()


def test_llm_call_log_survives_rollback_and_masks_pii(db, monkeypatch):
    import httpx

    from nhdip.llm.client import ResolvedLlm, chat
    from nhdip.models import LlmCall

    def fake_post(url, headers=None, json=None, timeout=None):  # noqa: A002
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}], "usage": {}}, request=httpx.Request("POST", url))

    monkeypatch.setattr("nhdip.llm.client.httpx.post", fake_post)
    cfg = ResolvedLlm(agent_code="t", connection_id=1, connection_name="fake", base_url="http://fake", api_key="", model="m", params={}, timeout=5, retries=0, tools_enabled=False)
    with db() as s:
        res = chat(s, cfg, [{"role": "user", "content": "고객 900101-1234567 · 010-1234-5678 · a@b.com 확인"}])
        s.rollback()  # 업무 트랜잭션이 롤백돼도
    with db() as s:
        call = s.get(LlmCall, res.call_id)
        assert call is not None and call.status == "ok"
        text = call.messages[0]["content"]
        assert "900101-1234567" not in text and "010-1234-5678" not in text and "a@b.com" not in text and "가림" in text


# ═════════════════════════ 기능 · 컴플라이언스 ═════════════════════════
def test_patch_figures_stale_and_unit():
    from nhdip.views.store import patch_figures

    art = {"a": {"id": "f1", "label": "x", "unit": "KRW_BN", "value": 10, "dataOrigin": "simulated"}}
    ch: list = []
    patch_figures(art, {"f1": {"stale": True, "staleReason": "선행 지표 오류"}}, ch, "k")
    assert art["a"]["value"] == 10 and art["a"]["stale"] is True and ch[0]["stale"]
    ch = []
    patch_figures(art, {"f1": {"value": 1.2, "unit": "KRW_TN", "dataOrigin": "mixed"}}, ch, "k")
    assert art["a"]["value"] == 1.2 and art["a"]["unit"] == "KRW_TN" and "stale" not in art["a"] and art["a"]["dataOrigin"] == "mixed"


def test_pii_scan_blocks_load_and_name_mask(db):
    from nhdip.data.datasets import quality_check
    from nhdip.models import Dataset
    from nhdip.privacy import mask_name

    from conftest import code_of

    with db() as s:
        ds = s.get(Dataset, code_of("BRANCH_BIZ_BALANCE"))  # 파일에서 만든 정의(Phase O) — 열 이름은 파일 머리글
        oc, nm = "사무소코드", "부문명"
        ok = quality_check(ds, [{oc: "001068", nm: "수신"}], [])
        assert next(c for c in ok["checks"] if c["rule"] == "pii")["passed"]
        bad = quality_check(ds, [{oc: "001068", nm: "900101-1234567"}, {oc: "001068", nm: "연락 010-9999-8888"}], [])
        pii = next(c for c in bad["checks"] if c["rule"] == "pii")
        assert bad["status"] == "failed" and not pii["passed"] and "900101" not in pii["detail"]
        allowed = quality_check(ds, [{oc: "001068", nm: "010-9999-8888"}], [], privacy={"pii_allow_columns": [nm]})
        assert next(c for c in allowed["checks"] if c["rule"] == "pii")["passed"]
    assert mask_name("김철수") == "김*수" and mask_name("홍길") == "홍*" and mask_name("농협은행주식회사") == "농협******"


def test_rule_dual_control(db):
    from nhdip.models import Setting

    admin = _admin()
    with db() as s:
        s.get(Setting, "governance.dual_control").value = {"enabled": True, "rules": True}
        s.commit()
    try:
        r = next(x for x in admin.get("/admin/rules").json() if x["code"] == "CRITIC_RULES")
        active, body = r["activeVersion"], r["versions"][0]["body"]
        out = admin.post("/admin/rules/CRITIC_RULES/versions", json={"body": body, "note": "이중 승인 시험"}).json()
        new = next(x for x in out if x["code"] == "CRITIC_RULES")
        assert new["activeVersion"] == active and new["versions"][0]["pending"] is True  # 저장만, 미적용
        v = new["versions"][0]["version"]
        assert admin.post("/admin/rules/CRITIC_RULES/activate", json={"version": v}).status_code == 409  # 본인 승인 불가
        with db() as s:
            from nhdip.models import AppUser
            from nhdip.security import hash_password

            if not s.get(AppUser, "00000002"):
                s.add(AppUser(emp_no="00000002", name="관리자2", org_code="D100", role="admin", status="active", password_hash=hash_password("Admin1234!")))
                s.commit()
        a2 = _client()
        assert _login(a2, "00000002", "Admin1234!").status_code == 200
        assert a2.post("/admin/rules/CRITIC_RULES/activate", json={"version": v}).status_code == 200
    finally:
        with db() as s:
            s.get(Setting, "governance.dual_control").value = {"enabled": False, "rules": True}
            s.commit()


def test_hitl_approval_gate(db):
    from nhdip.events import emit
    from nhdip.models import Job, Setting
    from nhdip.workflow.dispatcher import dispatch_once

    admin = _admin()
    with db() as s:
        dispatch_once(s)
        st = s.get(Setting, "orchestrator.policy")
        st.value = {**st.value, "require_approval": ["wf_branch_kpi"]}
        s.commit()
        emit(s, "rule.changed", {"rule": "BRANCH_PRIME_CORP_POLICY", "version": 1}, "test")
        s.commit()
        dispatch_once(s)
        j = s.query(Job).filter(Job.workflow_code == "wf_branch_kpi", Job.status == "approval").first()
    try:
        assert j is not None
        lst = admin.get("/admin/jobs/approval").json()
        assert any(x["id"] == j.id for x in lst)
        assert admin.post(f"/admin/jobs/{j.id}/reject", json={"reason": "시험 반려"}).status_code == 200
        with db() as s:
            assert s.get(Job, j.id).status == "rejected"
        # 수동 실행은 승인 없이 바로 대기열
        assert admin.post("/admin/workflows/wf_branch_kpi/run").status_code == 200
        with db() as s:
            dispatch_once(s)
            assert s.query(Job).filter(Job.workflow_code == "wf_branch_kpi", Job.status == "queued").count() >= 1
    finally:
        with db() as s:
            st = s.get(Setting, "orchestrator.policy")
            st.value = {**st.value, "require_approval": []}
            for q in s.query(Job).filter(Job.workflow_code == "wf_branch_kpi", Job.status.in_(["queued", "approval"])):
                s.delete(q)
            s.commit()


def test_branch_report_request_reaches_hq(db):
    admin = _admin()
    br = _user(admin, "20259105", "T211")
    types = br.get("/state/report-requests/types").json()
    assert any(t["value"] == "guide_check" for t in types)
    r = br.post("/state/report-requests", json={"reqType": "guide_check", "title": "우량기업 가중치 적용 기준 확인", "body": "하반기 가중치 적용 대상 확인을 요청합니다", "dueDate": "2026-10-31"})
    assert r.status_code == 201 and r.json()["fromOrg"] == "신용리스크관리부"
    assert br.post("/state/report-requests", json={"reqType": "bogus", "title": "xx", "body": "yy"}).status_code == 422
    assert [x["id"] for x in br.get("/state/report-requests/mine").json()] == [r.json()["id"]]
    hq = admin.get("/screens/report-requests").json()
    assert hq[0]["id"] == r.json()["id"] and "createdBy" not in hq[0]


# ═════════════════════════ B.33 ═════════════════════════
def test_app_role_is_dml_only_and_audit_append_only(db):
    import secrets as _s

    import pytest
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url
    from sqlalchemy.exc import DBAPIError

    from nhdip.config import get_settings
    from nhdip.dbrole import ensure_app_role

    owner = create_engine(get_settings().database_url, future=True)
    user, pw = "nhdip_app_test", "T" + _s.token_hex(8) + "'x"
    try:
        assert ensure_app_role(owner, user, pw)
        assert ensure_app_role(owner, user, pw)  # 멱등
        app = create_engine(make_url(get_settings().database_url).set(username=user, password=pw), future=True)
        try:
            with app.begin() as c:
                assert c.execute(text("SELECT count(*) FROM cfg.setting")).scalar() > 0
                c.execute(text("INSERT INTO audit.audit_log (at, actor, action) VALUES (now(), 't', 'test.app_role')"))
                c.execute(text("UPDATE cfg.setting SET description = description WHERE key = 'ui.as_of'"))
            for stmt in (
                "UPDATE audit.audit_log SET actor = 'x' WHERE action = 'test.app_role'",
                "DELETE FROM audit.audit_log WHERE action = 'test.app_role'",
                "TRUNCATE audit.audit_log",
                "ALTER TABLE audit.audit_log DISABLE TRIGGER ALL",
                "CREATE TABLE mart.x_test (id int)",
                "DROP TABLE cfg.setting",
            ):
                with pytest.raises(DBAPIError) as ei:
                    with app.begin() as c:
                        c.execute(text(stmt))
                assert "permission denied" in str(ei.value).lower() or "must be owner" in str(ei.value).lower(), stmt
        finally:
            app.dispose()
    finally:
        with owner.begin() as c:
            c.execute(text(f"DROP OWNED BY {user}"))
            c.execute(text(f"DROP ROLE IF EXISTS {user}"))
        owner.dispose()


def test_runtime_url_uses_app_role():
    from nhdip.config import Settings, runtime_database_url

    st = Settings(database_url="postgresql+psycopg://own:ownpw@pg:5432/nhdip", app_db_password="apw", nhdip_use_app_role=True)
    assert runtime_database_url(st) == "postgresql+psycopg://nhdip_app:apw@pg:5432/nhdip"
    assert runtime_database_url(Settings(database_url="postgresql+psycopg://own:ownpw@pg:5432/nhdip", app_db_password="")).startswith("postgresql+psycopg://own:")
    assert runtime_database_url(Settings(database_url="postgresql+psycopg://own:ownpw@pg:5432/nhdip", app_db_password="apw", nhdip_use_app_role=False)).startswith("postgresql+psycopg://own:")


def test_route_claim_prevents_duplicate_judgement(db, monkeypatch):
    from nhdip.events import emit
    from nhdip.models import OutboxEvent, utcnow
    from nhdip.workflow import orchestrator
    from nhdip.workflow.dispatcher import dispatch_once

    calls = []
    monkeypatch.setattr(orchestrator, "route", lambda session, ev, matched: calls.append(ev.id) or matched)
    with db() as s:
        dispatch_once(s)
        emit(s, "change.detected", {"workflow": "wf_branch_kpi", "chain": ["wf_branch_kpi"], "major": 0}, "test")
        s.commit()
        ev = s.query(OutboxEvent).order_by(OutboxEvent.id.desc()).first()
        ev.routing_at = utcnow()  # 다른 워커가 판단 중
        s.commit()
        dispatch_once(s)
        s.expire_all()
        assert s.get(OutboxEvent, ev.id).dispatched_at is None and ev.id not in calls
        from datetime import timedelta

        s.get(OutboxEvent, ev.id).routing_at = utcnow() - timedelta(minutes=10)  # 선점 만료
        s.commit()
        dispatch_once(s)
        s.expire_all()
        assert s.get(OutboxEvent, ev.id).dispatched_at is not None and calls == [ev.id]


def test_rate_limit_db_backend_shared(db):
    from fastapi import HTTPException

    from nhdip import ratelimit
    from nhdip.models import Setting

    with db() as s:
        st = s.get(Setting, "auth.rate_limits")
        st.value = {**st.value, "t_shared": [2, 60]}
        s.commit()
        ratelimit.check(s, "t_shared", "k1")
        ratelimit._hits.clear()  # 다른 프로세스를 흉내 — 메모리 기록 없이도 DB 카운터로 이어서 센다
        ratelimit.check(s, "t_shared", "k1")
        ratelimit._hits.clear()
        import pytest

        with pytest.raises(HTTPException) as ei:
            ratelimit.check(s, "t_shared", "k1")
        assert ei.value.status_code == 429 and int(ei.value.headers["Retry-After"]) >= 1
        ratelimit.check(s, "t_shared", "k2")  # 키별로 따로


def test_client_ip_behind_trusted_proxy(monkeypatch):
    from starlette.requests import Request

    from nhdip.api import deps
    from nhdip.api.deps import client_ip
    from nhdip.config import get_settings

    monkeypatch.setattr(get_settings(), "trusted_proxies", "127.0.0.1/32,172.19.0.7/32")
    monkeypatch.setattr(get_settings(), "trusted_proxy_hops", 1)
    deps._NETS.update(at=0.0, nets=[])

    def req(peer: str, xff: str | None):
        headers = [(b"x-forwarded-for", xff.encode())] if xff else []
        return Request({"type": "http", "method": "GET", "path": "/", "headers": headers, "client": (peer, 1234), "query_string": b""})

    assert client_ip(req("172.19.0.7", "203.0.113.9")) == "203.0.113.9"  # web 컨테이너 경유
    assert client_ip(req("172.19.0.7", "6.6.6.6, 203.0.113.9")) == "203.0.113.9"  # 사용자가 넣은 앞부분은 무시
    assert client_ip(req("172.19.0.7", "203.0.113.77, 172.20.0.9")) == "172.20.0.9"  # 사내망 사용자가 위조해도 Next 가 붙인 실제 주소
    assert client_ip(req("203.0.113.50", "1.2.3.4")) == "203.0.113.50"  # 신뢰하지 않는 곳에서 직접 온 헤더는 무시
    assert client_ip(req("172.19.0.8", "1.2.3.4")) == "172.19.0.8"  # 같은 대역이라도 목록에 없는 주소는 신뢰하지 않음
    assert client_ip(req("172.19.0.7", None)) == "172.19.0.7"
    monkeypatch.setattr(get_settings(), "trusted_proxy_hops", 2)  # 앞에 사내 L7 프록시가 한 겹 더
    assert client_ip(req("172.19.0.7", "6.6.6.6, 198.51.100.4, 10.0.0.5")) == "198.51.100.4"
    deps._NETS.update(at=0.0, nets=[])


def test_merge3_prepends_new_feed_items():
    from nhdip.views.store import merge3

    base = {"items": [{"id": "o1"}, {"id": "o2"}]}
    theirs = {"items": [{"id": "b1"}, {"id": "o1"}, {"id": "o2"}]}
    ours = {"items": [{"id": "a1"}, {"id": "o1"}, {"id": "o2"}]}
    assert [x["id"] for x in merge3(base, ours, theirs)["items"]] == ["a1", "b1", "o1", "o2"]


def test_goal_rule_update_waits_and_respects_dual_control(db):
    from nhdip.api.state import _update_goal_rule
    from nhdip.models import Rule, RuleVersion, Setting

    with db() as s:
        links = (s.get(Setting, "goal.rule_links").value or {}) if s.get(Setting, "goal.rule_links") else {}
        if not links:
            import pytest

            pytest.skip("목표-규칙 연결 없음")
        gid, link = next(iter(links.items()))
        rule = s.get(Rule, link["rule"])
        active = rule.active_version
        s.get(Setting, "governance.dual_control").value = {"enabled": True, "rules": True}
        s.commit()
        try:
            out = _update_goal_rule(s, gid, 123.45, "tester")
            s.commit()
            assert out and out["pendingApproval"] is True
            s.refresh(rule)
            assert rule.active_version == active  # 이중 승인 — 저장만
            assert s.query(RuleVersion).filter(RuleVersion.rule_code == rule.code, RuleVersion.version == out["version"]).one().body[link["path"]] == 123.45
        finally:
            s.get(Setting, "governance.dual_control").value = {"enabled": False, "rules": True}
            s.commit()


def test_governance_setting_needs_second_admin(db):
    from nhdip.models import AppUser, Setting
    from nhdip.security import hash_password

    with db() as s:
        if not s.get(AppUser, "00000002"):
            s.add(AppUser(emp_no="00000002", name="관리자2", org_code="D100", role="admin", status="active", password_hash=hash_password("Admin1234!")))
        s.get(Setting, "governance.dual_control").value = {"enabled": True, "rules": True}
        s.commit()
    a1, a2 = _admin(), _client()
    assert _login(a2, "00000002", "Admin1234!").status_code == 200
    off = {"value": {"enabled": False, "rules": True}}
    r = a1.put("/admin/settings/governance.dual_control", json=off).json()
    assert r.get("pending") is True
    with db() as s:
        assert s.get(Setting, "governance.dual_control").value["enabled"] is True  # 혼자서는 못 끈다
    assert a1.put("/admin/settings/governance.dual_control", json=off).json().get("pending") is True  # 같은 사람 재요청도 대기
    assert a2.put("/admin/settings/governance.dual_control", json=off).json().get("pending") is None  # 다른 관리자가 같은 값 → 반영
    with db() as s:
        assert s.get(Setting, "governance.dual_control").value["enabled"] is False


def test_orphan_jobs_of_previous_boot_are_requeued(db):
    from nhdip.models import Job, WorkerHeartbeat, WorkflowRun, new_id, utcnow
    from nhdip.workflow.dispatcher import recover_own_orphans, recover_stale

    with db() as s:
        j = Job(kind="workflow", workflow_code="wf_x_orphan", causes=[], status="running", locked_by="hostA:1:oldboot", locked_at=utcnow())
        other = Job(kind="workflow", workflow_code="wf_x_other", causes=[], status="running", locked_by="hostB:1:x", locked_at=utcnow())
        s.add_all([j, other])
        s.merge(WorkerHeartbeat(worker_id="hostA:1:oldboot", seen_at=utcnow(), info={}))
        s.flush()
        run = WorkflowRun(id=new_id(), workflow_code="wf_x_orphan", job_id=j.id, status="running", causes=[])
        s.add(run)
        s.commit()
        assert recover_stale(s) == 0  # 심장박동은 살아 있어 보인다(같은 이름 재기동)
        assert recover_own_orphans(s, "hostA", "hostA:1:newboot") == 1
        s.expire_all()
        assert s.get(Job, j.id).status == "queued" and s.get(Job, other.id).status == "running"
        assert s.get(WorkflowRun, run.id).status == "failed"
        s.delete(s.get(Job, j.id))
        s.delete(s.get(Job, other.id))
        s.commit()


# ═════════════════════════ B.34 ═════════════════════════
def test_preflight_readiness_and_backup_record(db):
    from nhdip.cli import main as cli
    from nhdip.preflight import run_checks

    with db() as s:
        rep = run_checks(s)
    keys = {i["key"]: i for i in rep["items"]}
    assert {"env", "session_secret", "db_role", "cookie_secure", "admin_password", "llm", "worker", "backup", "alerts", "knowledge_index"} <= set(keys)
    assert keys["knowledge_index"]["level"] in ("ok", "warn") and "AI 어시스턴트" in keys["knowledge_index"]["label"]
    assert keys["session_secret"]["level"] == "ok"
    assert keys["admin_password"]["level"] == "warn"  # 테스트 관리자는 최초 비밀번호 그대로
    assert all(i["level"] in ("ok", "warn", "fail") and "Admin1234" not in i["message"] for i in rep["items"])  # 비밀값 미노출
    assert cli(["record-backup", "backups/20261011-020000", "1024"]) == 0
    with db() as s:
        assert {i["key"]: i for i in run_checks(s)["items"]}["backup"]["level"] == "ok"
    admin = _admin()
    r = admin.get("/admin/readiness")
    assert r.status_code == 200 and r.json()["counts"]["ok"] >= 1
    assert _client().get("/admin/readiness").status_code == 401


# ═════════════════════════ B.36 외부 LiteLLM ═════════════════════════
def test_external_litellm_quick_setup(db, monkeypatch):
    from nhdip.api import admin_core
    from nhdip.llm import LlmUnavailable, resolve
    from nhdip.models import LlmConnection, LlmProfile
    from nhdip.security import decrypt_secret

    seen = {}

    def fake_test(base_url, api_key, model=None, timeout=15.0, embedding_model=None):
        seen.update(url=base_url, key=api_key, model=model, embedding_model=embedding_model)
        return {"ok": True, "models": ["gpt-x", "embed-x"], "latency_ms": 12, "chat_ok": True, "chat_latency_ms": 30,
                "embed_model": embedding_model, "embed_ok": True, "embed_dim": 1024, "embed_latency_ms": 40}

    monkeypatch.setattr(admin_core, "test_connection", fake_test)
    admin = _admin()
    with db() as s:
        prof = s.query(LlmProfile).filter(LlmProfile.is_default).first()
        conn = s.get(LlmConnection, prof.connection_id)
        before = (conn.base_url, conn.api_key_enc, conn.active, prof.model)
        conn.base_url = ""
        s.commit()
        try:
            resolve(s, "narrator_model")
            raise AssertionError("주소가 비었는데 호출 가능")
        except LlmUnavailable as exc:
            assert "주소" in str(exc)
    try:
        assert admin.post("/admin/llm/setup", json={"base_url": "http://169.254.169.254/x", "api_key": "k"}).status_code == 422  # SSRF 차단
        r = admin.post("/admin/llm/setup", json={"base_url": "https://litellm.example.test/v1", "api_key": "sk-test-123", "model": "gpt-x", "embedding_model": "embed-x"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["test"]["ok"] and body["model"] == "gpt-x" and body["embeddingModel"] == "embed-x"
        assert "sk-test-123" not in r.text and body["connection"]["hasKey"]  # 키는 돌려주지 않는다
        # 임베딩 모델도 연결 확인에 함께 넘어간다(채팅 시험만으로는 /embeddings 규격이 확인되지 않는다)
        assert seen == {"url": "https://litellm.example.test/v1", "key": "sk-test-123", "model": "gpt-x", "embedding_model": "embed-x"}
        assert body["test"]["embed_ok"] and body["test"]["embed_dim"] == 1024
        # 키를 비우면 유지
        assert admin.post("/admin/llm/setup", json={"base_url": "https://litellm.example.test/v1", "model": "gpt-x"}).status_code == 200
        with db() as s:
            prof = s.query(LlmProfile).filter(LlmProfile.is_default).first()
            conn = s.get(LlmConnection, prof.connection_id)
            assert decrypt_secret(conn.api_key_enc) == "sk-test-123" and conn.active
            cfg = resolve(s, "narrator_model")
            assert cfg.base_url == "https://litellm.example.test/v1" and cfg.model == "gpt-x"
        g = admin.get("/admin/llm/setup").json()
        assert g["connection"]["baseUrl"] == "https://litellm.example.test/v1" and g["model"] == "gpt-x"
        assert _client().post("/admin/llm/setup", json={"base_url": "https://x.test"}).status_code == 401
    finally:
        with db() as s:
            prof = s.query(LlmProfile).filter(LlmProfile.is_default).first()
            conn = s.get(LlmConnection, prof.connection_id)
            conn.base_url, conn.api_key_enc, conn.active, prof.model = before
            emb = s.query(LlmProfile).filter(LlmProfile.name == "embedding").first()
            if emb:
                emb.model = ""
            s.commit()


def test_bundled_litellm_default_is_cleared():
    from types import SimpleNamespace

    from nhdip.security import encrypt_secret
    from nhdip.seed.run import _clear_bundled_litellm

    def gone(*_):
        raise OSError("no litellm")

    old = SimpleNamespace(base_url="http://litellm:4000", api_key_enc=encrypt_secret(""), active=True, note="")
    assert _clear_bundled_litellm(old, resolver=gone) and old.base_url == "" and old.active is False  # 내장 컨테이너가 없으면 비움
    alive = SimpleNamespace(base_url="http://litellm:4000", api_key_enc=encrypt_secret(""), active=True, note="")
    assert not _clear_bundled_litellm(alive, resolver=lambda *_: [("ok",)])  # 내장 게이트웨이를 켜 두었으면 그대로
    keyed = SimpleNamespace(base_url="http://litellm:4000", api_key_enc=encrypt_secret("sk-1"), active=True, note="")
    assert not _clear_bundled_litellm(keyed, resolver=gone) and keyed.base_url == "http://litellm:4000"  # 키를 넣었으면 보존
    ext = SimpleNamespace(base_url="https://gw.example", api_key_enc=encrypt_secret(""), active=True, note="")
    assert not _clear_bundled_litellm(ext)


# ═════════════════════════ B.37 실제 게이트웨이 대응 ═════════════════════════
def test_chat_drops_param_the_model_rejects(db, monkeypatch):
    import httpx

    from nhdip.llm import client
    from nhdip.llm.client import ResolvedLlm, chat

    client._UNSUPPORTED.clear()
    sent = []

    def fake_post(url, headers=None, json=None, timeout=None):  # noqa: A002
        sent.append(dict(json))
        if "temperature" in json:
            msg = "litellm.UnsupportedParamsError: global.anthropic.claude-sonnet-5 does not support temperature=0.2. Only temperature=1 is supported."
            return httpx.Response(400, json={"error": {"message": msg}}, request=httpx.Request("POST", url))
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}], "usage": {}}, request=httpx.Request("POST", url))

    monkeypatch.setattr("nhdip.llm.client.httpx.post", fake_post)
    cfg = ResolvedLlm(agent_code="t", connection_id=1, connection_name="gw", base_url="http://gw", api_key="", model="claude-sonnet-5", params={"temperature": 0.2, "max_tokens": 100}, timeout=5, retries=0, tools_enabled=False)
    with db() as s:
        r = chat(s, cfg, [{"role": "user", "content": "x"}])
        assert r.text == "{}" and len(sent) == 2 and "temperature" not in sent[1] and sent[1]["max_tokens"] == 100  # 재시도 0 이어도 한 번 더
        sent.clear()
        chat(s, cfg, [{"role": "user", "content": "y"}])
        assert len(sent) == 1 and "temperature" not in sent[0]  # 기억해서 처음부터 빼고 보낸다
    client._UNSUPPORTED.clear()


def test_chat_expands_max_tokens_when_truncated(db, monkeypatch):
    """B.40 — 추론형 모델이 생각 토큰으로 max_tokens 를 다 써서 JSON 이 잘리면(finish_reason=length) 상한을 두 배로 늘려 다시 호출."""
    import httpx

    from nhdip.llm.client import ResolvedLlm, chat

    sent = []

    def fake_post(url, headers=None, json=None, timeout=None):  # noqa: A002
        sent.append(dict(json))
        if json["max_tokens"] < 3000:
            return httpx.Response(200, json={"choices": [{"message": {"content": '{"changes": [{"code": "a", "le'}, "finish_reason": "length"}], "usage": {}}, request=httpx.Request("POST", url))
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"changes": []}'}, "finish_reason": "stop"}], "usage": {}}, request=httpx.Request("POST", url))

    monkeypatch.setattr("nhdip.llm.client.httpx.post", fake_post)
    cfg = ResolvedLlm(agent_code="t", connection_id=1, connection_name="gw", base_url="http://gw", api_key="", model="m-trunc", params={"max_tokens": 1500}, timeout=5, retries=0, tools_enabled=False)
    with db() as s:
        r = chat(s, cfg, [{"role": "user", "content": "x"}])
    assert r.text == '{"changes": []}' and [b["max_tokens"] for b in sent] == [1500, 3000]


def test_judge_output_budget_and_timeout(db, monkeypatch):
    """2026-10-12 LLM 모드 업로드 시험 — 출력 상한을 늘리면 대기 시간도 늘고(고정 30초에 끊기지 않게),
    후보 수에 비례하는 판단은 처음부터 그만큼 출력 상한을 둔다(설정 llm.max_tokens_cap 이내)."""
    import types

    from nhdip.llm.client import ResolvedLlm, _timeout_for
    from nhdip.workflow import llm_judge

    assert _timeout_for(30, 1500) == 30 and _timeout_for(30, 6000) == 120 and _timeout_for(30, None) == 30 and _timeout_for(60, 1000) == 60
    cfg = ResolvedLlm(agent_code="judge_t", connection_id=1, connection_name="gw", base_url="http://gw", api_key="", model="m", params={"max_tokens": 1500}, timeout=60, retries=2, tools_enabled=False)
    seen = []

    def fake_chat(session, llm, messages, **kw):
        seen.append(llm)
        return types.SimpleNamespace(text='{"changes": []}', call_id="c1")

    monkeypatch.setattr(llm_judge, "resolve", lambda s, a: cfg)
    monkeypatch.setattr(llm_judge, "chat", fake_chat)
    llm_judge.reset_cooldown()
    with db() as s:
        for want, got in ((3350, 3350), (20000, 8000), (0, 1500), (1000, 1500)):
            data, meta = llm_judge.ask_json(s, "judge_t", "task", {"candidates": [1]}, required=("changes",), min_tokens=want)
            assert data == {"changes": []} and meta["by"] == "llm"
            assert seen[-1].params["max_tokens"] == got and seen[-1].timeout == 30 and seen[-1].retries == 1
