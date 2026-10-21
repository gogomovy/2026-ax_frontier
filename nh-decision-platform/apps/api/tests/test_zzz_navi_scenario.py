"""NAVI 시나리오 그대로 — 빈 플랫폼(자료 비우기 뒤)에서 종합기획부 · 신용모형팀 · 영업점 3곳 계정으로 가입하고 각자 자료를 올려 발표 흐름이 이어지는지.

  1) 자료 비우기(reset-data) → 조직(신용모형팀) 추가 → 가입 · 승인
  2) 시나리오 묶음(sample.scenario_pack) 폴더 순서대로, 폴더의 소유로 업로드 → 흐름 계산
  3) 화면 — 종합기획부(현황 · 제안) · 사업부서(현황 · 분석 탭 · 수행방안) · 영업점(자기 지점만) · 영업본부(세 지점 통합, 자료 없는 기본 지점 제외)
  4) 흐름 연결 — 종합기획부 목표 확정 → 사업부서 · 영업점 흐름이 '경영목표'로 다시 돈다 / 수행방안 영업점 참고 → 영업점 화면 · 흐름
시험 DB 의 업무 자료를 모두 지우므로 가장 마지막에 돈다(파일 이름 zzz).
"""
from __future__ import annotations

import json

from fastapi.testclient import TestClient
from sqlalchemy import select

ADMIN = ("00000001", "Admin1234!")
PW = "abcd1234"


def _client() -> TestClient:
    from nhdip.main import app

    return TestClient(app)


def _login(emp: str, pw: str = PW) -> TestClient:
    from nhdip import ratelimit

    ratelimit.reset()
    c = _client()
    r = c.post("/auth/login", json={"emp_no": emp, "password": pw})
    assert r.status_code == 200, (emp, r.text[:200])
    return c


def _runs(s, since=None) -> dict[str, list]:
    from nhdip.models import WorkflowRun

    out: dict[str, list] = {}
    q = select(WorkflowRun).order_by(WorkflowRun.started_at)
    if since is not None:
        q = q.where(WorkflowRun.started_at >= since)
    for r in s.execute(q).scalars():
        out.setdefault(r.workflow_code, []).append(r)
    return out


def _reasons(runs: list) -> list[str]:
    return [str(x) for r in runs for c in (r.causes or []) if isinstance(c, dict) for x in (c.get("reasons") or [])]


def test_navi_scenario_end_to_end(computed, tmp_path):
    db = computed
    from conftest import drain_workflows

    from nhdip import ratelimit
    from nhdip.data import reset as R
    from nhdip.models import utcnow
    from nhdip.sample.scenario_pack import ACCOUNTS, NEW_ORGS, folders, upload_http, write

    out = write(str(tmp_path / "navi"))
    assert len(out["folders"]) == 6 and (tmp_path / "navi" / "안내.txt").exists()
    man = json.loads((tmp_path / "navi" / "manifest.json").read_text(encoding="utf-8"))
    assert [f["owner"] for f in man["folders"]] == [None, "T111", "T213", "BR301", "BR302", "BR303"]

    # 1) 빈 플랫폼 — 업무 자료 · 산출물 · 사용자 결정을 비우고 정의만 남긴다
    with db() as s:
        R.reset_business_data(s, "test", external=False, force=True)
        s.commit()
    admin = _login(*ADMIN)
    for o in NEW_ORGS:
        r = admin.post("/admin/orgs", json={"code": o.code, "name": o.name, "unit_type": o.unit_type, "parent_code": o.parent, "sort": o.sort})
        assert r.status_code in (201, 409), r.text
    for emp, name, org, _ in ACCOUNTS:
        ratelimit.reset()
        r = _client().post("/auth/signup", json={"emp_no": emp, "name": name, "password": PW, "org_code": org})
        assert r.status_code in (200, 201, 409), (emp, r.text[:200])
        assert admin.post(f"/admin/users/{emp}/approve").status_code == 200

    # 계산 전 — 영업본부 통합에 계산된 지점이 없다(기본 지점 0점 틀이 1위로 나오지 않는다)
    region = _login("20269300")
    rk0 = region.get("/screens/region/kpi").json()
    assert rk0["summary"]["computed"] == 0 and not [b for b in rk0["branches"] if b.get("rank")], rk0["summary"]

    # 2) 폴더 순서대로 업로드(폴더의 소유) — 안내서의 한 번에 올리기 명령(scenario-upload)과 같은 함수 → 흐름 계산
    rep = upload_http("http://testserver", *ADMIN, client=_client())
    assert rep["ok"] and rep["uploaded"] == sum(len(fd.files) for fd in folders()), rep["failed"][:3]
    assert upload_http("http://testserver", *ADMIN, client=_client())["uploaded"] == 0  # 다시 실행해도 같은 결과(이미 올린 파일은 건너뜀)
    with db() as s:
        from nhdip.models import source

        t = source("bank")
        owners = {(fn, o) for fn, o in s.execute(select(t.version.file_name, t.version.owner_org).where(t.version.is_current))}
    for fd in folders():
        for f in fd.files:
            if f.kind == "dataset" and f.origin == "bank":
                assert (f.name, fd.owner) in owners, (f.name, fd.owner)
    # 여러 영업점 자료 — 영업점마다 따로 현재 판, 다른 영업점 파일이 다른 영업점 판을 교체 · 중복 적용하지 않는다
    from nhdip.data.datasets import branch_owner_from_rows, current_rows, current_versions
    from nhdip.data.sources import Resolver
    from nhdip.sample.branches import BRANCHES, branch_files

    with db() as s:
        ds = Resolver(s).resolve("영업점 업적평가 득점 현황")
        cur_v = current_versions(s, ds)
        assert sorted(v.owner_org for v in cur_v) == ["BR301", "BR302", "BR303"], [(v.version, v.owner_org) for v in cur_v]
        _, rows_all = current_rows(s, ds)
        expect = sum(len(f["rows"]) for b in BRANCHES for f in branch_files(b) if f["dataset"] == "BRANCH_KPI_SCORE")
        assert len(rows_all) == expect, (len(rows_all), expect)  # 세 지점 행이 한 번씩
        code = ds.code
    seo = next(f for fd in folders() if "BR302" in fd.name for f in fd.files if f.dataset == "BRANCH_KPI_SCORE")
    # 파일 이름엔 코드가 없어도(…_서초지점.xlsx) 행의 사무소코드로 서초를 추천 — 기본 소유가 다른 지점으로 잡혀 있어도 바꾸라고 알린다
    pv = admin.post(f"/admin/datasets/{code}/preview", data={"origin": "bank", "data_origin": "simulated"}, files={"file": (seo.name, seo.content)}).json()["placement"]
    assert pv["fileOwnerHint"]["code"] == "BR302" and pv["fileOwnerHint"]["by"] == "content" and pv["ownerMismatch"], pv
    wrong = admin.post(f"/admin/datasets/{code}/preview", data={"origin": "bank", "data_origin": "simulated", "owner_org": "BR301"}, files={"file": (seo.name, seo.content)}).json()["placement"]
    assert wrong["error"] and "서초" in wrong["error"], wrong
    r = admin.post(f"/admin/datasets/{code}/upload", data={"origin": "bank", "data_origin": "simulated", "owner_org": "BR301"}, files={"file": (seo.name, seo.content)})
    assert r.status_code == 422 and "서초" in r.text, r.text[:300]  # 강남 판을 서초 행으로 교체하지 않는다
    right = admin.post(f"/admin/datasets/{code}/preview", data={"origin": "bank", "data_origin": "simulated", "owner_org": "BR302"}, files={"file": (seo.name, seo.content)}).json()["placement"]
    assert right["action"] == "replace" and right["duplicateOf"] and not right["error"] and not right["ownerMismatch"], right  # 같은 파일 다시 — 서초 자기 판만
    with db() as s:
        ds = Resolver(s).resolve("영업점 업적평가 득점 현황")
        rows = [{k: v for k, v in r.items() if not k.startswith("__")} for r in current_rows(s, ds)[1] if "BR303" in {str(x) for x in r.values()}]  # 열 이름은 파일 그대로(사무소코드)
        assert rows
        # 관리자 · 영업본부가 요청으로 올린 영업점 파일 — 요청자 팀이 아니라 그 영업점 판으로(같은 기준일 다른 영업점 판 교체 방지)
        assert branch_owner_from_rows(s, ds, rows, "T911", "*") == "BR303"
        assert branch_owner_from_rows(s, ds, rows, "T311", "T311") == "BR303"  # 영업본부 — 자기 지역본부 아래 지점
        assert branch_owner_from_rows(s, ds, rows, "D200", "D200") == "D200"  # 다른 조직 아래 지점은 그대로
        assert branch_owner_from_rows(s, ds, rows_all, "T911", "*") == "T911"  # 여러 지점 섞인 파일은 그대로(전행 · 팀)
    drain_workflows(db, rounds=12, per_round=80)
    with db() as s:
        runs = _runs(s)
        for wf in ("wf_hq_goal_review", "wf_model_monitoring", "wf_inclusive_risk", "wf_branch_kpi"):
            assert runs.get(wf), (wf, sorted(runs))
            last = runs[wf][-1]
            assert last.status in ("succeeded", "degraded"), (wf, last.status, last.error)

    # 3) 화면 — 소속마다 자기 화면 · 자기 자료
    hq = _login("20269101")
    me = hq.get("/me").json()
    assert "HQ_OVERVIEW" in me["screens"] and "RISK_HOME" not in me["screens"] and "BRANCH_HOME" not in me["screens"]
    dash = hq.get("/screens/hq-dashboard").json()
    assert dash.get("computed") is not False
    props = hq.get("/screens/proposals").json()
    assert props, "경영목표 제안이 계산돼야 한다"
    assert hq.get("/screens/risk-dashboard").status_code == 403

    risk = _login("20269201")
    me = risk.get("/me").json()
    assert {"RISK_HOME", "RISK_ANALYSIS", "RISK_GUIDES"} <= set(me["screens"]) and "HQ_GOALS" not in me["screens"]
    assert risk.get("/screens/risk-dashboard").json().get("computed") is not False
    tabs = risk.get("/screens/analysis-tabs").json()
    keys = [t["tabKey"] for t in tabs["current"]]
    assert len(keys) >= 2, keys
    for k in keys:
        assert risk.get(f"/screens/reports/{k}").status_code == 200, k
    plans = risk.get("/screens/action-plans").json()
    assert plans, "수행방안이 근거 분석과 함께 나와야 한다"

    for emp, _, org, _ in ACCOUNTS:
        if not org.startswith("BR"):
            continue
        br = _login(emp)
        d = br.get("/screens/branch/dashboard").json()
        assert d["available"] and d["office"]["code"] == org, (emp, d.get("office"))
        assert [o["code"] for o in br.get("/screens/branch/offices").json()["offices"]] == [org]
        assert [t["tabKey"] for t in br.get("/screens/branch/tabs").json()["current"]], emp
        assert br.get("/screens/region/kpi").status_code == 403  # 영업점 직원은 통합 화면 없음

    rk = region.get("/screens/region/kpi").json()
    rows = {b["code"]: b for b in rk["branches"]}
    assert rk["summary"]["computed"] == 3, rk["summary"]
    assert all(rows[c]["available"] and rows[c]["rank"] for c in ("BR301", "BR302", "BR303")), rows
    assert not any(r.get("rank") for c, r in rows.items() if c not in ("BR301", "BR302", "BR303"))  # 자료 없는 기본 지점 · 다른 지점은 순위 밖
    # 관리자 · 영업본부 지점 선택 — 계산된 세 지점이 먼저(기본 지점 후보), 자료 없는 지점(수원영통 등)은 뒤에 '자료 대기'로 고를 수만 있다
    for viewer in (admin, region):
        ol = viewer.get("/screens/branch/offices").json()
        offices = [o["code"] for o in ol["offices"]]
        assert set(offices[:3]) == {"BR301", "BR302", "BR303"} and all(o["available"] for o in ol["offices"][:3]), offices
        assert not any(o["available"] for o in ol["offices"][3:]) and ol["default"] in {"BR301", "BR302", "BR303"}
        assert len(offices) >= 4  # 선택 상자가 보인다(둘 이상)

    # 4) 흐름 연결 — 목표 확정 → 사업부서 · 영업점 흐름이 '경영목표' 원인으로 다시 돈다
    before = utcnow()
    p = next(x for x in props if x.get("targetGoalId"))
    r = hq.post("/state/goals/apply", json={"proposalId": p["id"], "mode": "adopt", "force": True, "reason": "시나리오 — 제안 반영 확정(정합성 경고 확인)"})
    assert r.status_code == 200, r.text[:300]
    drain_workflows(db, rounds=8, per_round=80)
    with db() as s:
        runs = _runs(s, before)
        for wf in ("wf_model_monitoring", "wf_inclusive_risk", "wf_branch_kpi"):
            assert any(x.startswith("lineage:goal") for x in _reasons(runs.get(wf, []))), (wf, _reasons(runs.get(wf, [])))
        from nhdip.views.user_state import goal_lines

        assert goal_lines(s), "확정 목표가 사업부서 · 영업점 서술 근거로 보여야 한다"

    # 수행방안 진행사업 등록 + 영업점 참고 → 영업점 화면에 보이고 영업점 흐름이 다시 돈다
    before = utcnow()
    pid = plans[0]["id"]
    assert risk.post(f"/state/plans/{pid}/register").status_code == 200
    st = risk.get("/state/plans").json()
    if not st["runtime"].get(pid, {}).get("branchShared"):
        assert risk.post(f"/state/plans/{pid}/toggle-share").status_code == 200
    drain_workflows(db, rounds=8, per_round=80)
    br = _login("20269301")
    assert pid in [x["id"] for x in br.get("/screens/action-plans").json()]
    with db() as s:
        assert any(x.startswith("lineage:plan_share") for x in _reasons(_runs(s, before).get("wf_branch_kpi", [])))
