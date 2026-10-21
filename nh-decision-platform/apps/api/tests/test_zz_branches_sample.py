"""영업점 3곳 시험 자료(sample.branches) — 실제 업로드 API 로 공통 · 지점별 자료를 올리면 지점마다 계산되고, 영업본부 통합 업적평가에 모인다.

시험 DB 의 영업점 자료(다른 지점 판 · 사무소 마스터)를 바꾸므로 마지막에 돈다(파일 이름 zz).
"""
from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

ADMIN = ("00000001", "Admin1234!")


def _client() -> TestClient:
    from nhdip.main import app

    return TestClient(app)


def test_three_branches_compute_and_gather_in_region(computed, tmp_path):
    db = computed
    from conftest import drain_workflows

    from nhdip import ratelimit
    from nhdip.sample.branches import BRANCHES, REGION_CODE, build_branches, write
    from nhdip.scopes import computed_offices, resolve_office
    from nhdip.ui_config import office_list
    from nhdip.views.readiness import computed as is_computed
    from nhdip.views.region import region_kpi
    from nhdip.views.store import get_current

    out = write(str(tmp_path / "branches"))
    assert len(out["folders"]) == 4 and (tmp_path / "branches" / "안내.txt").exists()

    c = _client()
    ratelimit.reset()
    assert c.post("/auth/login", json={"emp_no": ADMIN[0], "password": ADMIN[1]}).status_code == 200
    for folder, files in build_branches().items():
        owner = next((b.code for b in BRANCHES if b.code in folder), "")
        for f in files:
            r = c.post("/admin/datasets/auto-upload", data={"origin": f.origin, "data_origin": "simulated", "owner_org": owner, "force": "true"}, files={"file": (f.name, f.content)})
            assert r.status_code == 201 and r.json().get("status") == "committed", (folder, f.name, r.text[:300])
            if owner:
                assert (r.json().get("owner") or {}).get("code", owner) == owner
    drain_workflows(db, rounds=10)

    with db() as s:
        ready = computed_offices(s)
        for b in BRANCHES:
            assert b.code in ready, (b.code, ready)
            v = get_current(s, f"branch_dashboard@{b.code}")
            assert v["office"]["code"] == b.code and v["office"]["name"] == b.name and is_computed(v)
        # 지점 직원 — 자기 지점, 다른 지점은 목록에 없다
        me = SimpleNamespace(role="user", org_code="BR302", emp_no="t")
        assert resolve_office(s, me, None) == "BR302"
        assert [o["code"] for o in office_list(s, me)["offices"]] == ["BR302"]
        # 영업본부(지역본부 팀) — 통합 업적평가에 세 지점이 순위 · 득점률과 함께
        rk = region_kpi(s, SimpleNamespace(role="user", org_code="T311", emp_no="t"))
        assert rk["region"]["code"] == REGION_CODE
        rows = {r["code"]: r for r in rk["branches"]}
        for b in BRANCHES:
            assert rows[b.code]["available"] and rows[b.code]["rank"] and rows[b.code]["total"] is not None, rows.get(b.code)
        totals = [rows[b.code]["total"] for b in BRANCHES]
        assert len(set(totals)) == 3  # 지점마다 득점이 다르다
        # 기본 지점(규칙 BRANCH_SCOPE.office_code = 001068)은 사무소 마스터에서 빠졌다 — 기본 실행이 틀을 만들어도 계산된 지점 · 순위에 나타나지 않는다
        assert "001068" not in ready
        assert "001068" not in rows or (not rows["001068"]["available"] and not rows["001068"].get("rank")), rows.get("001068")
        assert rk["summary"]["computed"] == len(BRANCHES)
