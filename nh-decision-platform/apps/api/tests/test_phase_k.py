"""Phase K (요구사항 §27 · Q148~Q155) — 화면 설정(ui.*) · 업무 영역 단위 · 이름 바꾸기 · Elasticsearch 인증 진단 · 연결 설정."""
from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

ADMIN = ("00000001", "Admin1234!")


def _admin() -> TestClient:
    from nhdip.main import app

    c = TestClient(app)
    assert c.post("/auth/login", json={"emp_no": ADMIN[0], "password": ADMIN[1]}).status_code == 200
    return c


@pytest.fixture()
def restore_ui(db):
    """시험이 바꾼 ui.* 설정을 원래대로."""
    from nhdip.models import Setting
    from nhdip.ui_config import DEFAULTS

    with db() as s:
        before = {k: (s.get(Setting, k).value if s.get(Setting, k) else None) for k in DEFAULTS}
    yield
    with db() as s:
        for k, v in before.items():
            row = s.get(Setting, k)
            if v is None and row is not None:
                s.delete(row)
            elif row is not None:
                row.value = v
        s.commit()


def test_menu_config_defaults_and_sections(db):
    c = _admin()
    m = c.get("/me/menu").json()
    cfg = m["config"]
    # 판정 구간 · 기준값 · 목표 역할 — 화면 코드에 있던 값이 기본값
    assert [b["max"] for b in cfg["bands"]["limitUsage"]] == [85, 100, None]
    assert cfg["bands"]["rwaUsage"] == cfg["bands"]["limitUsage"]  # 같은 판정은 같은 구간(Q149)
    assert cfg["thresholds"] == {"planPaceTolerancePp": 5, "headroomAlert": 1, "shareReferencePct": 50, "proposalReasonMin": 5}
    assert cfg["goalRoles"]["corpGrowth"] == "goal-corp-growth" and cfg["goalRoles"]["hhLimit"] == "goal-hh-balance"
    assert cfg["issueOrder"] == ["breach", "below", "near_limit"]
    assert cfg["labels"]["subDomain"]["corporate"] == "기업여신" and cfg["labels"]["subDomainHref"]["inclusive_finance"] == "/risk/analysis"
    assert len(cfg["examples"]["assist"]) >= 1 and all(e["q"] for e in cfg["examples"]["assist"])
    assert {n["countKey"] for n in cfg["notices"]} >= {"goalProposals", "proposedPlans", "adminTodo"}
    # 업무 영역 — 종류별 단위. 화면이 없는 부서는 준비 중(available=false)
    dept = cfg["scopes"]["dept"]
    assert dept["label"] == "사업부서"
    units = {u["code"]: u for u in dept["units"]}
    assert units["D200"]["available"] is True and units["D200"]["home"] == "/risk"
    assert units["D310"]["available"] is False and units["D310"]["name"] == "여신관리부"
    assert cfg["ownerOrgs"][:1] == ["종합기획부"] and "신용리스크관리부" in cfg["ownerOrgs"]
    # 지점 목록 — 관리자는 계산 대상 지점 전부
    assert cfg["offices"]["default"] and any(o["code"] == cfg["offices"]["default"] for o in cfg["offices"]["offices"])
    # 메뉴 묶음에 업무 영역(종류 · 조직)이 붙는다 — 주소 접두어(/risk)로 판정하지 않는다
    secs = {s["section"]: s for s in m["sections"]}
    assert secs["종합기획부"]["scope"] == "hq" and secs["종합기획부"]["orgCode"] == "D100"
    assert secs["신용리스크관리부"]["scope"] == "dept" and secs["신용리스크관리부"]["orgCode"] == "D200"
    assert secs["영업점"]["scope"] == "branch"
    assert secs["공통"]["scope"] is None
    assert all(s["scope"] is None for s in m["sections"] if s["admin"])
    # 이름 바꾸기(REN-01) · 화면 설정 메뉴
    items = {i["code"]: i for s in m["sections"] for i in [*s["flow"], *s["reference"]]}
    assert items["ANALYSIS_BUILDER"]["label"] == "분석 에이전트 만들기"
    assert items["ADMIN_UI"]["href"] == "/admin/ui"


def test_ui_settings_are_validated_and_reflected(db, restore_ui):
    c = _admin()
    bad = [
        ("ui.bands", {"limitUsage": [{"max": 100, "label": "a", "tone": "neutral"}, {"max": 90, "label": "b", "tone": "attention"}, {"max": None, "label": "c", "tone": "critical"}]}, "오름차순"),
        ("ui.bands", {"limitUsage": [{"max": 80, "label": "a", "tone": "neutral"}, {"max": 90, "label": "b", "tone": "attention"}]}, "마지막"),
        ("ui.bands", {"limitUsage": [{"max": None, "label": "a", "tone": "pink"}]}, "색"),
        ("ui.bands", {"nope": []}, "알 수 없는"),
        ("ui.thresholds", {"planPaceTolerancePp": -1}, "사이"),
        ("ui.goal_roles", {"corpGrowth": "goal-없는-목표"}, "없습니다"),
        ("ui.scopes", {"dept": {"label": "사업부서", "units": [{"org": "NOPE", "section": "x"}]}}, "조직"),
        ("ui.scopes", {"dept": {"label": "사업부서", "units": [{"org": "D200", "section": "a"}, {"org": "D310", "section": "a"}]}}, "두 번"),
        ("ui.notices", [{"countKey": "bad key!", "label": "x"}], "건수 키"),
        ("ui.issue_order", ["breach", "breach"], "중복"),
        ("ui.labels", {"subDomainHref": {"corporate": "https://evil.example"}}, "주소"),
        ("ui.labels", {"nope": {}}, "묶음"),
    ]
    for key, value, msg in bad:
        r = c.put(f"/admin/settings/{key}", json={"value": value})
        assert r.status_code == 422 and msg in r.json()["detail"], (key, r.text)
    # 저장한 값이 /me/menu.config 로 바로 나간다
    bands = [{"max": 70, "label": "정상", "tone": "neutral"}, {"max": 95, "label": "근접", "tone": "attention"}, {"max": None, "label": "초과", "tone": "critical"}]
    assert c.put("/admin/settings/ui.bands", json={"value": {"limitUsage": bands}}).status_code == 200
    cfg = c.get("/me/menu").json()["config"]
    assert [b["max"] for b in cfg["bands"]["limitUsage"]] == [70, 95, None]
    assert [b["max"] for b in cfg["bands"]["rwaUsage"]] == [85, 100, None]  # 저장하지 않은 키는 기본값 유지
    # 새 부서 단위 — 메뉴 묶음을 사업부서로 지정하면 영역 · 조직이 붙는다
    scopes = c.get("/admin/ui-config").json()["values"]["ui.scopes"]
    scopes["dept"]["units"].append({"org": "D900", "section": "디지털전략부"})
    assert c.put("/admin/settings/ui.scopes", json={"value": scopes}).status_code == 200
    dept = c.get("/me/menu").json()["config"]["scopes"]["dept"]["units"]
    assert [u["code"] for u in dept] == ["D200", "D310", "D900"] and dept[-1]["available"] is False
    # 깨진 값이 DB 에 직접 들어가도 화면은 기본값으로 (멈추지 않게)
    from nhdip.models import Setting

    with db() as s:
        s.get(Setting, "ui.thresholds").value = {"planPaceTolerancePp": "다섯"}
        s.commit()
    assert c.get("/me/menu").json()["config"]["thresholds"]["planPaceTolerancePp"] == 5


def test_ui_config_meta_for_admin_form(db):
    c = _admin()
    meta = c.get("/admin/ui-config").json()
    assert set(meta["values"]) == set(meta["defaults"]) and "ui.bands" in meta["descriptions"]
    assert any(g["id"] == "goal-corp-growth" for g in meta["goals"])
    assert "신용리스크관리부" in meta["sections"] and "goalProposals" in meta["countKeys"]
    assert {o["code"] for o in meta["orgs"]} >= {"D100", "D200", "D310"}
    from nhdip.main import app

    anon = TestClient(app)
    assert anon.get("/admin/ui-config").status_code in (401, 403)


def test_owner_org_and_period_come_from_config(db):
    """신규 목표 담당 조직 기본값 = 종기부 단위 조직(코드에 부서 이름 없음)."""
    from nhdip.ui_config import hq_org_name

    with db() as s:
        assert hq_org_name(s) == "종합기획부"


def test_builder_rename_upgrade_keeps_admin_label(db):
    from nhdip.models import Screen, Setting
    from nhdip.seed.run import builder_rename_upgrade

    with db() as s:
        sc = s.get(Screen, "ANALYSIS_BUILDER")
        st = s.get(Setting, "seed.applied_upgrades")
        st.value = [x for x in st.value if x != "analysis-builder-rename-v1"]
        sc.label = "분석 만들기"
        out: dict = {}
        builder_rename_upgrade(s, out)
        assert sc.label == "분석 에이전트 만들기" and out == {"builder_rename_upgrade": 1}
        # 한 번만 — 관리자가 다른 이름으로 바꾼 뒤에는 건드리지 않는다
        sc.label = "새 분석 요청"
        builder_rename_upgrade(s, out)
        assert sc.label == "새 분석 요청"
        sc.label = "분석 에이전트 만들기"
        s.commit()


# ── Elasticsearch 인증 (ES-01~03) ───────────────────────────────
@pytest.fixture()
def es_clean():
    from nhdip.knowledge import elastic

    elastic.reset_breaker()
    elastic.set_client(None)
    elastic.invalidate_override()
    yield elastic
    elastic.reset_breaker()
    elastic.set_client(None)
    elastic.invalidate_override()


def _mock(handler) -> httpx.Client:
    return httpx.Client(base_url="http://es.test", transport=httpx.MockTransport(handler))


def test_es_401_is_auth_error_with_remedy(db, es_clean, monkeypatch):
    elastic = es_clean
    body = '{"error":{"root_cause":[{"type":"security_exception","reason":"unable to authenticate user [elastic] for REST request [/_cluster/health]"}]},"status":401}'
    elastic.set_client(_mock(lambda r: httpx.Response(401, text=body, headers={"content-type": "application/json"})))
    with pytest.raises(elastic.EsAuthError) as ei:
        elastic.request("GET", "/_cluster/health")
    assert "인증 실패" in str(ei.value) and "security_exception" not in str(ei.value)
    assert not elastic.es_up()  # 인증 실패는 저절로 낫지 않음 — 차단기로 호출을 줄인다
    elastic.reset_breaker()
    monkeypatch.setattr(elastic, "configured", lambda: True)
    with db() as s:
        st = elastic.status(s)
    assert st["up"] is False and st["errorKind"] == "auth" and any("make es-password" in r for r in st["remedy"])
    # 관리자 화면 · 운영 점검에 같은 진단
    elastic.reset_breaker()
    c = _admin()
    sb = c.get("/admin/knowledge/status").json()["searchBackend"]
    assert sb["es"]["errorKind"] == "auth"
    items = {i["key"]: i for i in c.get("/admin/readiness").json()["items"]}
    assert "make es-password" in items["search_backend"]["fix"]
    # 그 밖의 4xx 는 rejected, 연결 오류는 down
    elastic.reset_breaker()
    elastic.set_client(_mock(lambda r: httpx.Response(400, text="bad")))
    with db() as s:
        assert elastic.status(s)["errorKind"] == "rejected"

    def boom(_r):
        raise httpx.ConnectError("refused")

    elastic.reset_breaker()
    elastic.set_client(_mock(boom))
    with db() as s:
        assert elastic.status(s)["errorKind"] == "down"


def test_es_connection_saved_masked_and_used(db, es_clean, monkeypatch):
    elastic = es_clean
    from nhdip.models import AuditLog, Secret

    c = _admin()
    calls: list[tuple[str, str, str]] = []

    def probe(url, user, password):
        calls.append((url, user, password))
        return {"ok": password == "right-pw", "errorKind": None if password == "right-pw" else "auth", "message": "연결됨" if password == "right-pw" else elastic.AUTH_MESSAGE[401]}

    monkeypatch.setattr(elastic, "probe", probe)
    assert c.get("/admin/knowledge/es-connection").json()["source"] == "env"
    t = c.post("/admin/knowledge/es-connection/test", json={"url": "http://es.internal:9200", "user": "elastic", "password": "wrong"}).json()
    assert t["ok"] is False and t["errorKind"] == "auth"
    r = c.put("/admin/knowledge/es-connection", json={"url": "http://es.internal:9200", "user": "elastic", "password": "wrong"})
    assert r.status_code == 422 and "인증 실패" in r.json()["detail"]  # 시험을 통과해야 저장
    assert c.put("/admin/knowledge/es-connection", json={"url": "http://169.254.169.254", "user": "x", "password": "right-pw"}).status_code == 422  # 메타데이터 주소 차단
    r = c.put("/admin/knowledge/es-connection", json={"url": "http://es.internal:9200", "user": "elastic", "password": "right-pw"})
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["source"] == "db" and v["saved"]["password"] == "••••••••" and "right-pw" not in json.dumps(v)
    # 비밀번호를 비우면 저장값을 그대로 쓴다
    c.post("/admin/knowledge/es-connection/test", json={"url": "http://es.internal:9200", "user": "elastic"})
    assert calls[-1][2] == "right-pw"
    with db() as s:
        row = s.get(Secret, elastic.SECRET_KEY)
        assert row.secret_enc.startswith("v1:") and "right-pw" not in row.secret_enc
        logs = s.execute(select(AuditLog).where(AuditLog.action == "admin.es_connection.save")).scalars().all()
        assert logs and all("right-pw" not in json.dumps(a.detail, ensure_ascii=False) for a in logs)
    # 이 프로세스는 바로 새 값으로
    conn = elastic.connection()
    assert conn["source"] == "db" and conn["url"] == "http://es.internal:9200" and conn["password"] == "right-pw"
    assert elastic.configured()
    # 설정 목록 API 에는 나오지 않는다
    assert "right-pw" not in json.dumps(c.get("/admin/settings").json(), ensure_ascii=False)
    # 되돌리기 → 환경변수
    assert c.delete("/admin/knowledge/es-connection").json()["source"] == "env"
    assert elastic.connection()["source"] == "env"


def test_attention_rank_rule_label_comes_from_rule_version(db):
    """우선순위 산출 규칙 표기 = 규칙 코드 · 적용 판(화면에 'v1' 을 박지 않는다)."""
    from nhdip.models import Rule
    from nhdip.workflow.engine import run_workflow

    with db() as s:
        r = run_workflow(s, "wf_hq_goal_review", [{"type": "manual"}])
        assert r.status in ("succeeded", "degraded"), r.summary
        rule = s.get(Rule, "ATTENTION_SCORE")
        want = f"ATTENTION_SCORE v{rule.active_version}"
    atts = _admin().get("/screens/attentions").json()
    ranked = [a for a in atts if isinstance(a, dict) and a.get("rankScore") is not None]
    assert ranked, "우선순위가 계산된 주목 사항이 있어야 한다(시연 자료 업로드 후)"
    assert all(a.get("rankRule") == want for a in ranked)


def test_es_password_cli_requires_temp_account(monkeypatch, capsys):
    """make es-password 의 CLI — ES 주소 · 비밀번호 없으면 2, 임시 계정 없으면 안내 후 2(이미 맞으면 0)."""
    from types import SimpleNamespace

    from nhdip import cli
    from nhdip.knowledge import elastic

    monkeypatch.setattr("nhdip.config.get_settings", lambda: SimpleNamespace(es_url="", es_user="elastic", es_password=""))
    assert cli.main(["es-password"]) == 2 and "ES_PASSWORD" in capsys.readouterr().err

    class Fake:
        def __init__(self, code):
            self.code = code

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, path):
            return SimpleNamespace(status_code=self.code)

    monkeypatch.setattr("nhdip.config.get_settings", lambda: SimpleNamespace(es_url="http://es.test:9200", es_user="elastic", es_password="pw"))
    monkeypatch.setattr(elastic, "make_client", lambda *a, **k: Fake(200))
    assert cli.main(["es-password"]) == 0 and "이미" in capsys.readouterr().out
    monkeypatch.setattr(elastic, "make_client", lambda *a, **k: Fake(401))
    monkeypatch.delenv("ES_RESET_USER", raising=False)
    assert cli.main(["es-password"]) == 2 and "임시 관리 계정" in capsys.readouterr().err
