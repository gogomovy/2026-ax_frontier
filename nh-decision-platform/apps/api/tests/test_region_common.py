"""영업본부 통합 업적평가(§37 RGN) · 부서 화면 격리 · 공통 통합 DB(§38 CMN) · 분석 에이전트 상위 KPI · 코드 고정 보완."""
from __future__ import annotations

import io
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

ADMIN = ("00000001", "Admin1234!")
PW = "abcd1234"


def _client() -> TestClient:
    from nhdip.main import app

    return TestClient(app)


def _login(c: TestClient, emp: str, pw: str) -> None:
    from nhdip import ratelimit

    ratelimit.reset()
    assert c.post("/auth/login", json={"emp_no": emp, "password": pw}).status_code == 200


def _user(org: str) -> SimpleNamespace:
    return SimpleNamespace(role="user", org_code=org, emp_no="t")


# ═════════════════════════ 화면 격리 · 영업본부 통합 ═════════════════════════
def test_screen_isolation_by_department(db):
    from nhdip.api.deps import user_screen_codes

    with db() as s:
        hq, risk, region, branch = (user_screen_codes(s, _user(o)) for o in ("T111", "T211", "T311", "001068"))
    # 다른 시험이 화면 권한을 더할 수 있어(같은 시험 DB) 이 기능이 정하는 것만 본다 — 통합 화면은 지역본부에만
    assert "HQ_OVERVIEW" in hq and "REGION_KPI" not in hq, sorted(hq)
    assert "RISK_HOME" in risk and "REGION_KPI" not in risk, sorted(risk)
    assert {"REGION_KPI", "BRANCH_HOME"} <= region and "HQ_OVERVIEW" not in region, sorted(region)
    # 영업점 직원 — 지역본부 권한을 이어받지만 통합 화면은 빠진다(설정 screen.deny_unit_types)
    assert "BRANCH_HOME" in branch and "REGION_KPI" not in branch


def test_region_kpi_scope(db):
    from nhdip.sample.verify import drain
    from nhdip.views.region import RegionDenied, region_kpi

    drain(db)  # 올린 자료로 영업점 흐름이 돈 뒤
    with db() as s:
        out = region_kpi(s, SimpleNamespace(role="admin", org_code="H100", emp_no="a"), "D300")
        codes = {b["code"]: b for b in out["branches"]}
        assert out["region"]["code"] == "D300" and "001068" in codes and "BR401" not in codes
        assert codes["001068"]["available"] and codes["001068"]["rank"] == 1 and codes["001068"]["total"] is not None
        assert out["summary"]["computed"] >= 1 and len(out["regions"]) >= 3
        mine = region_kpi(s, _user("T311"))  # 수도권1지역본부 직원 — 자기 지역
        assert mine["region"]["code"] == "D300" and [r["code"] for r in mine["regions"]] == ["D300"]
        other = region_kpi(s, _user("D400"))
        assert other["region"]["code"] == "D400" and "001068" not in {b["code"] for b in other["branches"]}
        with pytest.raises(RegionDenied):
            region_kpi(s, _user("T311"), "D400")
        with pytest.raises(RegionDenied):
            region_kpi(s, _user("001068"))


def test_region_api_and_targets(db):
    admin = _client()
    _login(admin, *ADMIN)
    r = admin.get("/screens/region/kpi?region=D300")
    assert r.status_code == 200 and r.json()["region"]["code"] == "D300"
    t = admin.get("/screens/branch-targets")
    assert t.status_code == 200 and all(x.get("orgCode") in (None, "D300") for x in t.json())


# ═════════════════════════ 공통 통합 DB ═════════════════════════
def _csv(rows: list[str]) -> bytes:
    return ("공통시험상품코드,공통시험상품명\n" + "\n".join(rows) + "\n").encode("utf-8")


def test_common_db_admin_only_and_owner(db):
    from nhdip.common_db import CommonOnly, assert_can_upload, common_doc_classes, summary
    from nhdip.data.datasets import current_versions
    from nhdip.models import Dataset, KbChunk
    from sqlalchemy import select

    admin = _client()
    _login(admin, *ADMIN)
    # 공통으로 올리면 소유 팀을 골라도 비운다(전행 공통)
    r = admin.post("/admin/datasets/auto-upload", data={"origin": "bank", "data_origin": "simulated", "common": "true", "owner_org": "T211"},
                   files={"file": ("공통시험_상품기준.csv", io.BytesIO(_csv(["P001,가", "P002,나"])), "text/csv")})
    assert r.status_code == 201, r.text
    code = r.json()["dataset"]
    with db() as s:
        d = s.get(Dataset, code)
        assert d.common is True
        assert {v.owner_org for v in current_versions(s, d)} == {None}
        with pytest.raises(CommonOnly):
            assert_can_upload(_user("T211"), dataset=d)
        assert_can_upload(SimpleNamespace(role="admin"), dataset=d)
        with pytest.raises(CommonOnly):
            assert_can_upload(_user("T211"), doc_class=common_doc_classes(s)[0], session=s)
        from nhdip.data.catalog import index_dataset_cards

        index_dataset_cards(s, [code])
        s.commit()
        card = s.execute(select(KbChunk).where(KbChunk.source_key == f"dataset:{code}")).scalar()
        assert card is not None and card.collection_code == "catalog.common" and card.required_resource is None
        assert code in {x["code"] for x in summary(s)["datasets"]}
    # 업무 사용자 업로드 대상 목록에서 빠지고, 정의를 직접 고르면 거절
    emp = "20259371"
    u = _client()
    u.post("/auth/signup", json={"emp_no": emp, "name": "공통시험", "password": PW, "org_code": "T211"})
    admin.post(f"/admin/users/{emp}/approve")
    _login(u, emp, PW)
    up = u.get("/db/uploadable")
    if up.status_code == 200:
        assert code not in {x["code"] for x in up.json()["datasets"]}
        assert "common_ref" not in {x["key"] for x in up.json()["docClasses"]}
        rq = u.post("/db/uploads/dataset", data={"target": code, "data_origin": "simulated"}, files={"file": ("공통시험_상품기준.csv", io.BytesIO(_csv(["P003,다"])), "text/csv")})
        assert rq.status_code == 403, rq.text
    # 부서 자료로 되돌리기 · 다시 공통으로(판 소유 비움)
    assert admin.patch(f"/admin/datasets/{code}", json={"common": False}).json()["common"] is False
    assert admin.patch(f"/admin/datasets/{code}", json={"common": True}).json()["common"] is True


def test_reference_candidates_link_fact_table_to_common_class():
    from nhdip.graph.links import reference_candidates

    schema = SimpleNamespace(classes=[{"label": "Dataset", "kind": "system"}, {"label": "Product", "kind": "object", "backing": [{"dataset": "COMMON_P", "key_col": "code"}]}], relations=[])
    rows = {"COMMON_P": [{"code": "P1"}, {"code": "P2"}, {"code": "P3"}], "FACT_A": [{"ym": "202608", "prod": "P1", "amt": 1}, {"ym": "202608", "prod": "P2", "amt": 2}]}
    profiles = {"FACT_A": {"columns": {"prod": {"semantic": "code"}, "ym": {"semantic": "yearmonth"}, "amt": {"semantic": "measure"}}}}
    dss = [SimpleNamespace(code="COMMON_P", name="공통 상품"), SimpleNamespace(code="FACT_A", name="부서 실적")]
    out = reference_candidates(dss, profiles, schema, rows, None, {}, {"COMMON_P"}, lambda x: x)
    assert len(out) == 1 and out[0]["dataset"] == "FACT_A" and out[0]["col"] == "prod" and out[0]["type"] == "REFERS_PRODUCT"
    # 이미 있는 참조는 다시 제안하지 않는다
    schema.relations = [{"type": "REFERS_PRODUCT", "from": "Dataset", "to": "Product", "backing": [{"dataset": "FACT_A", "from_col": "$dataset", "to_col": "prod"}]}]
    assert reference_candidates(dss, profiles, schema, rows, None, {}, {"COMMON_P"}, lambda x: x) == []


def test_reference_relation_schema_validation(db):
    from nhdip.graph.schema import validate_schema

    with db() as s:
        bad = {"classes": [{"label": "Dataset", "kind": "system"}, {"label": "Product", "kind": "object"}],
               "relations": [{"type": "REFERS_PRODUCT", "from": "Product", "to": "Product", "backing": [{"dataset": "X", "from_col": "$dataset", "to_col": "c"}]}]}
        res = validate_schema(bad, s)
        assert any("$dataset" in e for e in res["errors"])


# ═════════════════════════ 분석 에이전트 — 상위 KPI · 코드 고정 보완 ═════════════════════════
def test_analysis_spec_accepts_upper_kpi(db):
    from sqlalchemy import select

    from nhdip.analysis_agents.lifecycle import _metric_rows, upstream_workflows
    from nhdip.analysis_agents.spec import kpi_catalog, validate_spec
    from nhdip.models import Metric

    with db() as s:
        kpis = kpi_catalog(s)
        assert {k["workflow"] for k in kpis} >= {"wf_hq_goal_review"}, sorted({k["workflow"] for k in kpis})
        hq = next(k for k in kpis if k["workflow"] == "wf_hq_goal_review")
        raw = {"title": "상위 목표 대비", "metrics": [{"key": "goal", "label": "상위 목표", "formula": "VALUE", "args": {"value": {"kpi": hq["code"]}}, "unit": "NONE"}],
               "sections": [{"heading": "목표", "blocks": [{"type": "metrics", "metrics": ["goal"]}]}]}
        spec, val = validate_spec(s, raw, "risk")
        assert spec["metrics"] and spec["metrics"][0]["args"]["value"]["kpi"] == hq["code"], val
        rows = _metric_rows(spec, "t1", "wf_an_t1")
        assert rows[0]["args"]["value"] == {"metric": hq["code"]}
        assert upstream_workflows(s, spec) == ["wf_hq_goal_review"]
        dyn = s.execute(select(Metric.code).where(Metric.code.like("dyn_%")).limit(1)).scalar()
        if dyn:
            spec2, val2 = validate_spec(s, {**raw, "metrics": [{**raw["metrics"][0], "args": {"value": {"kpi": dyn}}}]}, "risk")
            assert not spec2["metrics"] and any("KPI" in i["message"] for i in val2["issues"])


def test_resolver_successor_for_code_bound_refs(db):
    from nhdip.data.sources import Resolver
    from nhdip.models import Dataset

    with db() as s:
        res = Resolver(s)
        live = next(d for d in res.datasets if d.code in res.latest and d.columns)
        ghost = Dataset(code="ZZ_OLD_" + live.code[:40], name=live.name, origin=live.origin, kind=live.kind, columns=[dict(c) for c in live.columns], key_columns=[], active=True)
        s.add(ghost)
        s.flush()
        r2 = Resolver(s)
        assert r2.resolve(ghost.code).code == live.code  # 자료 없는 예전 코드 → 같은 자료의 지금 정의
        assert ghost.code in r2.refs_for(live.code)  # 지금 정의의 변경 이벤트가 예전 코드에 묶인 흐름도 깨운다
        s.rollback()
