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

    with db() as s:
        ds = s.get(Dataset, "BRANCH_BIZ_BALANCE")
        ok = quality_check(ds, [{"office_cd": "001068", "segment_nm": "수신"}], [])
        assert next(c for c in ok["checks"] if c["rule"] == "pii")["passed"]
        bad = quality_check(ds, [{"office_cd": "001068", "segment_nm": "900101-1234567"}, {"office_cd": "001068", "segment_nm": "연락 010-9999-8888"}], [])
        pii = next(c for c in bad["checks"] if c["rule"] == "pii")
        assert bad["status"] == "failed" and not pii["passed"] and "900101" not in pii["detail"]
        allowed = quality_check(ds, [{"office_cd": "001068", "segment_nm": "010-9999-8888"}], [], privacy={"pii_allow_columns": ["segment_nm"]})
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


def test_client_ip_behind_trusted_proxy():
    from starlette.requests import Request

    from nhdip.api.deps import client_ip

    def req(peer: str, xff: str | None):
        headers = [(b"x-forwarded-for", xff.encode())] if xff else []
        return Request({"type": "http", "method": "GET", "path": "/", "headers": headers, "client": (peer, 1234), "query_string": b""})

    assert client_ip(req("172.19.0.7", "203.0.113.9")) == "203.0.113.9"  # web 컨테이너 경유
    assert client_ip(req("172.19.0.7", "6.6.6.6, 203.0.113.9")) == "203.0.113.9"  # 사용자가 넣은 가짜 앞부분은 무시
    assert client_ip(req("203.0.113.50", "1.2.3.4")) == "203.0.113.50"  # 신뢰하지 않는 곳에서 직접 온 헤더는 무시
    assert client_ip(req("172.19.0.7", None)) == "172.19.0.7"
