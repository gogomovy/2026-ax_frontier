"""운영 알림 · LLM 예산 (작업 8.5 · 4.7)."""
from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select


def _admin():
    from nhdip.main import app

    c = TestClient(app)
    c.post("/auth/login", json={"emp_no": "00000001", "password": "Admin1234!"})
    return c


def _set(db, key, value):
    from nhdip.models import Setting

    with db() as s:
        s.get(Setting, key).value = value
        s.commit()


def test_llm_budget_status_and_block(db, monkeypatch):
    from nhdip.llm import LlmError, chat, resolve
    from nhdip.llm.budget import status
    from nhdip.models import Agent, LlmCall, LlmProfile

    with db() as s:
        s.execute(delete(LlmCall).where(LlmCall.agent_code == "budget_probe"))
        s.add(LlmCall(agent_code="budget_probe", purpose="chat", model="m-test", status="ok", prompt_tokens=6000, completion_tokens=4000))
        s.commit()
    _set(db, "llm.pricing", {"m-test": {"prompt_per_1k": 2.0, "completion_per_1k": 5.0}})
    _set(db, "llm.budget", {"monthly_tokens": 10000, "monthly_cost": 0, "per_agent_tokens": {}, "on_exceed": "block", "warn_pct": 80})
    with db() as s:
        st = status(s)
        probe = next(i for i in st["usage"]["items"] if i["agent"] == "budget_probe")
        assert probe["tokens"] == 10000 and probe["cost"] == 32.0  # 6×2 + 4×5
        assert st["tokensPct"] >= 100
        p = s.execute(select(LlmProfile).where(LlmProfile.name == "default")).scalar()
        p.model = "coder.general.multimodal"
        s.commit()
        called = {"n": 0}
        monkeypatch.setattr("nhdip.llm.client.httpx.post", lambda *a, **k: called.__setitem__("n", called["n"] + 1))
        with pytest.raises(LlmError, match="예산"):
            chat(s, resolve(s, "query_assistant"), [{"role": "user", "content": "x"}])
        assert called["n"] == 0  # 예산 초과 → 게이트웨이 호출 없음
        p.model = ""
        s.get(Agent, "query_assistant")
        s.commit()
    c = _admin()
    assert c.get("/admin/llm/usage").json()["maxPct"] >= 100
    _set(db, "llm.budget", {"monthly_tokens": 0, "monthly_cost": 0, "per_agent_tokens": {}, "on_exceed": "warn", "warn_pct": 80})
    _set(db, "llm.pricing", {})
    with db() as s:
        s.execute(delete(LlmCall).where(LlmCall.agent_code == "budget_probe"))
        s.commit()


def test_alerts_scan_send_dedupe_and_test(db, monkeypatch):
    from nhdip.alerts import DEFAULT_POLICY, scan
    from nhdip.models import AuditLog, WorkflowRun, new_id
    from nhdip.models.runtime import Alert

    sent: list[dict] = []

    def fake_post(url, json=None, timeout=None):  # noqa: A002
        sent.append(json)
        return httpx.Response(200, request=httpx.Request("POST", url))

    monkeypatch.setenv("ALERT_WEBHOOK_URL", "https://hooks.example.test/x")
    monkeypatch.setattr("nhdip.alerts.httpx.post", fake_post)
    rid = new_id()
    with db() as s:
        s.add(WorkflowRun(id=rid, workflow_code="wf_model_monitoring", status="failed", causes=[], error="테스트 실패"))
        for _ in range(3):
            s.add(AuditLog(actor=None, action="auth.sso_failed", detail={"reason": "test"}))
        s.commit()
    # 꺼짐(기본) → 기록만
    with db() as s:
        scan(s)
        a = s.execute(select(Alert).where(Alert.dedupe_key == f"workflow_failed:{rid}")).scalar()
        assert a.status == "logged" and not sent
        s.execute(delete(Alert).where(Alert.dedupe_key == f"workflow_failed:{rid}"))
        s.commit()
    pol = {**DEFAULT_POLICY, "enabled": True, "channels": ["webhook"], "rules": {**DEFAULT_POLICY["rules"], "auth_failures": {"enabled": True, "severity": "warning", "threshold": 3, "window_min": 10}}}
    _set(db, "alerts.policy", pol)
    with db() as s:
        scan(s)
        scan(s)  # 같은 조건 두 번 → 한 번만
        a = s.execute(select(Alert).where(Alert.dedupe_key == f"workflow_failed:{rid}")).scalars().all()
        assert len(a) == 1 and a[0].status == "sent" and a[0].channels == {"webhook": "ok"} and a[0].severity == "critical"
        assert s.execute(select(Alert).where(Alert.kind == "auth_failures")).scalars().first() is not None
    assert any("워크플로우 실패" in m["text"] for m in sent)
    c = _admin()
    r = c.post("/admin/alerts/test").json()
    assert r["status"] == "sent"
    items = c.get("/admin/alerts").json()
    assert items["channelsConfigured"]["webhook"] and items["items"][0]["kind"] == "test"
    _set(db, "alerts.policy", DEFAULT_POLICY)
