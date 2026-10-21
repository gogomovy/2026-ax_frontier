"""데이터 책임자 승인형 동적 분석 (§40 STW) — 새 자료 → 에이전트 제안(분석 화면 · 추적 지표 · 개념 연결) → 소유 부서 책임자 승인 → 반영.

순수 함수(후보 · 명세 · 소유 판정)는 DB 없이, 승인 흐름은 실제 업로드 → 승인 → 워크플로 실행으로 확인한다.
"""
from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select


# ═════════════════════════ 순수 함수 ═════════════════════════
CLASSES = [{"label": "PolicyTheme", "kind": "concept"}, {"label": "ProductGroup", "kind": "concept"}, {"label": "Segment", "kind": "concept"}, {"label": "Product", "kind": "object"}]
ALIASES = {"PolicyTheme": {"포용금융": ["서민금융"]}, "ProductGroup": {"햇살론": ["햇살론뱅크"], "사잇돌": []}, "Segment": {"외감": ["외부감사"]}, "Product": {"P1": ["상품하나"]}}


def test_concept_candidates_scores_name_values_and_ignores_short_substrings():
    from nhdip.workflow.proposal_nodes import concept_candidates

    texts = [("포용금융 상품군 공급실적", "name", ""), ("비외감 차주 수", "column", "'비외감 차주 수'")]
    got = concept_candidates(CLASSES, ALIASES, texts, {"상품군": ["햇살론", "기타"]})
    keys = {(c["label"], c["key"]): c for c in got}
    assert keys[("PolicyTheme", "포용금융")]["score"] >= 0.95  # 자료 이름에 대표 키
    assert ("ProductGroup", "햇살론") in keys and keys[("ProductGroup", "햇살론")]["evidence"][0].startswith("열 '상품군' 값")
    # 두 글자 별칭 '외감' 은 낱말이 같을 때만 — '비외감' 에 걸리지 않는다
    assert ("Segment", "외감") not in keys
    # 객체 유형(kind=object)은 개념 연결 후보가 아니다
    assert not [c for c in got if c["label"] == "Product"]
    assert [c["score"] for c in got] == sorted((c["score"] for c in got), reverse=True)


def test_concept_candidates_threshold_and_limit():
    from nhdip.workflow.proposal_nodes import concept_candidates

    texts = [("햇살론뱅크 운영 기준", "meaning", "")]
    assert concept_candidates(CLASSES, ALIASES, texts, {}, min_score=0.7) == []  # 열 의미만 겹치면(0.6) 기준 미달
    assert len(concept_candidates(CLASSES, ALIASES, texts, {}, min_score=0.5)) == 1
    many = [("포용금융 햇살론 사잇돌", "name", "")]
    assert len(concept_candidates(CLASSES, ALIASES, many, {}, limit=2)) == 2


PROF = {
    "rows": 8, "asOfColumn": "ym",
    "columns": {
        "ym": {"label": "기준월", "semantic": "yearmonth", "distinct": 2, "nullRate": 0, "keyCandidate": False, "pii": False},
        "grp": {"label": "상품군", "semantic": "code", "distinct": 4, "nullRate": 0, "keyCandidate": False, "pii": False},
        "bal": {"label": "공급잔액", "semantic": "amount", "distinct": 8, "nullRate": 0, "keyCandidate": False, "pii": False, "max": 400},
        "cnt": {"label": "공급건수", "semantic": "count", "distinct": 8, "nullRate": 0, "keyCandidate": False, "pii": False, "max": 39},
        "rt": {"label": "연체율", "semantic": "rate", "distinct": 8, "nullRate": 0, "keyCandidate": False, "pii": False, "max": 3.1},
        "id": {"label": "일련번호", "semantic": "identifier", "distinct": 8, "nullRate": 0, "keyCandidate": True, "pii": False},
    },
    "measures": ["rt", "cnt", "bal"], "dimensions": ["grp", "id"],
}


def test_usable_columns_order_and_filters():
    from nhdip.workflow.proposal_nodes import usable_dimensions, usable_measures

    assert usable_measures(PROF) == ["bal", "cnt", "rt"]  # 금액 → 건수 → 비율
    assert usable_dimensions(PROF) == ["grp"]  # 식별자 · 키 후보는 묶음 열이 아니다


def test_auto_spec_compares_latest_with_previous_stored_period_and_validates_shape():
    from nhdip.analysis_agents.spec import KEY_RE, TOKEN_RE
    from nhdip.workflow.proposal_nodes import auto_spec

    spec = auto_spec({"code": "DS_X", "name": "포용금융 공급실적", "as_of_column": "ym"}, PROF, {"summary": "상품군별 공급 실적", "columns": {"bal": {"meaning": "공급 잔액"}}},
                     agg_rows={"grp": ["합계"]})
    keys = [m["key"] for m in spec["metrics"]]
    assert all(KEY_RE.match(k) for k in keys) and len(keys) <= 20
    assert {"m1_now", "m1_prev", "m1_chg", "rows_now", "rows_prev", "rows_chg"} <= set(keys)
    by = {m["key"]: m for m in spec["metrics"]}
    now_w = by["m1_now"]["args"]["values"]["q"]["where"]
    prev_w = by["m1_prev"]["args"]["values"]["q"]["where"]
    # 최근 기준일 vs 직전 '보관' 기준일 — 올린 기준일이 띄어 있어도 비교된다
    assert now_w["ym"] == "$latest" and prev_w["ym"] == "$prev" and TOKEN_RE.match(prev_w["ym"])
    assert now_w["grp"] == {"nin": ["합계"]}  # 합계 행은 더하지 않는다
    assert by["m1_chg"]["formula"] == "GROWTH_RATE" and by["m1_chg"]["args"] == {"v0": {"metric": "m1_prev"}, "v1": {"metric": "m1_now"}}
    assert by["m3_chg"]["formula"] == "DIFF"  # 비율은 증감(차이)
    assert by["m3_now"]["formula"] == "MEAN" and by["m2_now"]["unit"] == "CNT"
    assert spec["tables"][0]["group_by"] == "grp" and spec["tables"][0]["where"]["ym"] == "$latest"
    assert spec["insights"][0]["metrics"][0] == "m1_chg"
    assert "0" not in spec["task"] and spec["schedule"] == {"cron": None, "on_data_change": True}


def test_auto_spec_single_period_has_no_comparison():
    from nhdip.workflow.proposal_nodes import auto_spec

    one = {**PROF, "columns": {**PROF["columns"], "ym": {**PROF["columns"]["ym"], "distinct": 1}}}
    spec = auto_spec({"code": "DS_X", "name": "자료", "as_of_column": "ym"}, one, None, max_measures=1)
    keys = [m["key"] for m in spec["metrics"]]
    assert keys == ["m1_now", "rows_now"]
    assert [s["heading"] for s in spec["sections"]][:1] == ["핵심 지표"] and "직전 기준일 대비" not in [s["heading"] for s in spec["sections"]]


def test_owns_requires_every_current_version_in_scope():
    from nhdip.stewardship import owns

    assert owns({"T211"}, False, {"D200", "T211"})
    assert not owns({"T211", "T111"}, False, {"D200", "T211"})  # 다른 부서 판이 섞이면 관리자 몫
    assert not owns({"T211"}, True, {"T211"})  # 전행(소유 없음) 판이 섞이면 관리자 몫
    assert not owns(set(), True, {"T211"})


# ═════════════════════════ 승인 흐름 (통합) ═════════════════════════
ADMIN = ("00000001", "Admin1234!")
PW = "abcd1234"
# 신용리스크관리부(T211 · 부 D200) 사용자 · 책임자, 종합기획부(T111) 책임자
REQ, STW, OTHER = "20259171", "20259172", "20259173"
STEM = "포용금융_상품군_공급실적"


def _client() -> TestClient:
    from nhdip.main import app

    return TestClient(app)


def _login(c: TestClient, emp: str, pw: str) -> None:
    from nhdip import ratelimit

    ratelimit.reset()
    assert c.post("/auth/login", json={"emp_no": emp, "password": pw}).status_code == 200


def _user(admin: TestClient, emp: str, org: str, steward: bool = False) -> TestClient:
    from nhdip import ratelimit

    ratelimit.reset()
    c = _client()
    c.post("/auth/signup", json={"emp_no": emp, "name": f"승인함{emp[-2:]}", "password": PW, "org_code": org})
    admin.post(f"/admin/users/{emp}/approve")
    _login(c, emp, PW)
    if steward:
        assert admin.patch(f"/admin/users/{emp}", json={"data_steward": True}).status_code == 200
    return c


def _csv(ym: str, rows: list[tuple[str, int, int]]) -> bytes:
    return ("기준월,상품군,공급잔액,공급건수\n" + "".join(f"{ym},{g},{b},{n}\n" for g, b, n in rows)).encode("utf-8")


JAN = [("햇살론", 100, 10), ("새희망홀씨대출", 200, 20), ("사잇돌", 50, 5), ("합계", 350, 35)]
AUG = [("햇살론", 130, 12), ("새희망홀씨대출", 210, 21), ("사잇돌", 60, 6), ("합계", 400, 39)]
SEP = [("햇살론", 300, 30), ("새희망홀씨대출", 400, 40), ("사잇돌", 100, 10), ("합계", 800, 80)]


def _request(c: TestClient, ym: str, rows, target: str | None = None) -> int:
    data = {"data_origin": "simulated", **({"target": target} if target else {})}
    r = c.post("/db/uploads/dataset", data=data, files={"file": (f"{STEM}_{ym}.csv", io.BytesIO(_csv(ym, rows)), "text/csv")})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _approve_upload(c: TestClient, rid: int) -> dict:
    r = c.post(f"/db/uploads/{rid}/approve", json={"note": "승인함 시험"})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module")
def world(db):
    from conftest import drain_workflows

    admin = _client()
    _login(admin, *ADMIN)
    w = {"admin": admin, "req": _user(admin, REQ, "T211"), "stw": _user(admin, STW, "T211", steward=True), "other": _user(admin, OTHER, "T111", steward=True)}
    # 1월 자료(새 종류 — 정의 제안) → 같은 부서 책임자 승인 → 8월 자료(같은 자료의 새 기준일) → 승인. 2~7월은 없다(띄어 올림)
    first = _approve_upload(w["stw"], _request(w["req"], "202601", JAN))
    code = first["result"]["createdDataset"]
    _approve_upload(w["stw"], _request(w["req"], "202608", AUG, target=code))
    drain_workflows(db)
    w["code"] = code
    return w


def _items(c: TestClient, status: str = "pending") -> list[dict]:
    r = c.get(f"/db/steward/proposals?status={status}")
    assert r.status_code == 200, r.text
    return r.json()["items"]


def test_agents_propose_and_only_owning_department_sees_them(world, db):
    code = world["code"]
    mine = [i for i in _items(world["stw"]) if i.get("dataset") == code]
    kinds = {i["kind"] for i in mine}
    assert {"analysis", "metric", "concept"} <= kinds, mine
    ana = next(i for i in mine if i["kind"] == "analysis")
    assert ana["auto"] and ana["canReview"] and ana["requestedBy"].startswith("agent:") and ana["periods"] == 2
    assert {"m1_now", "m1_prev", "m1_chg"} <= {m["key"] for m in ana["metrics"]}
    concepts = {(i["label"], i["key"]) for i in mine if i["kind"] == "concept"}
    assert ("ProductGroup", "햇살론") in concepts, concepts
    # 다른 부서 책임자 · 일반 사용자는 보지 못한다 · 관리자는 본다
    assert not [i for i in _items(world["other"]) if i.get("dataset") == code]
    assert world["req"].get("/db/steward/proposals").status_code == 403
    assert [i for i in _items(world["admin"]) if i.get("dataset") == code]
    # 사이드바 건수(자료 올리기 메뉴)
    counts = world["stw"].get("/me/menu").json()["counts"]
    assert counts.get("stewardTodo", 0) >= len([i for i in mine if i["canReview"]])
    # 다른 부서 책임자는 승인할 수 없다(없는 것처럼)
    r = world["other"].post(f"/db/steward/proposals/analysis/{ana['agent']}/{ana['version']}/approve", json={})
    assert r.status_code == 404


def test_approved_analysis_compares_gap_months_and_publishes(world, db):
    from conftest import drain_workflows

    from nhdip.analysis_registry import dynamic_tabs
    from nhdip.models import AnalysisAgent, MetricValue
    from nhdip.analysis_agents.spec import token_of

    code = world["code"]
    ana = next(i for i in _items(world["stw"]) if i.get("dataset") == code and i["kind"] == "analysis")
    r = world["stw"].post(f"/db/steward/proposals/analysis/{ana['agent']}/{ana['version']}/approve", json={"note": "부서 승인"})
    assert r.status_code == 200, r.text
    drain_workflows(db)
    tok = token_of(ana["agent"])

    def last(metric: str) -> float:
        with db() as s:
            mv = s.execute(select(MetricValue).where(MetricValue.metric_code == f"dyn_{tok}_{metric}").order_by(MetricValue.id.desc())).scalars().first()
            assert mv is not None, metric
            return float(mv.value)

    # 공급잔액(합계 행 제외): 8월 130+210+60 = 400, 직전 보관 기준일(1월) 100+200+50 = 350 → (400-350)/350 = 14.2857%
    assert last("m1_now") == 400 and last("m1_prev") == 350
    assert round(last("m1_chg"), 2) == 14.29
    with db() as s:
        a = s.get(AnalysisAgent, ana["agent"])
        assert a.status == "active" and a.approved_by == STW
        assert any(t["tabKey"] == a.tab_key for t in dynamic_tabs(s, a.space))
    approved = [i for i in _items(world["stw"], "approved") if i["kind"] == "analysis" and i["agent"] == ana["agent"]]
    assert approved and approved[0]["href"]


def test_new_month_reruns_analysis_and_change_agent_reports(world, db):
    from conftest import drain_workflows

    from nhdip.models import AnalysisAgent, MetricValue
    from nhdip.views.store import get_current

    code = world["code"]
    _approve_upload(world["stw"], _request(world["req"], "202609", SEP, target=code))
    drain_workflows(db)
    with db() as s:
        a = s.execute(select(AnalysisAgent).where(AnalysisAgent.status == "active", AnalysisAgent.requested_by.like("agent:%"))).scalars().all()
        a = next(x for x in a if ((x.spec or {}).get("auto") or {}).get("dataset") == code)
        tok = a.code.split("_", 1)[1]
        prev = s.execute(select(MetricValue).where(MetricValue.metric_code == f"dyn_{tok}_m1_prev").order_by(MetricValue.id.desc())).scalars().first()
        assert float(prev.value) == 400  # 이제 직전 보관 기준일은 8월
        feed = get_current(s, "change_feed") or {}
        assert any(i.get("workflow") == a.workflow_code for i in feed.get("items") or []), "분석 흐름의 변화가 변화 피드에 남아야 한다"


def test_concept_approve_links_graph_and_card_and_reject_is_sticky(world, db):
    from conftest import drain_workflows

    from nhdip.events import emit
    from nhdip.graph.projection import collect_graph
    from nhdip.models import Dataset, KbChunk

    code = world["code"]
    pend = [i for i in _items(world["stw"]) if i.get("dataset") == code and i["kind"] == "concept"]
    keep = next(i for i in pend if (i["label"], i["key"]) == ("ProductGroup", "햇살론"))
    r = world["stw"].post(f"/db/steward/proposals/concept/{code}/approve", json={"label": keep["label"], "key": keep["key"]})
    assert r.status_code == 200, r.text
    others = [i for i in pend if i is not keep]
    for i in others:
        assert world["stw"].post(f"/db/steward/proposals/concept/{code}/reject", json={"label": i["label"], "key": i["key"]}).status_code == 422  # 사유 필수
        assert world["stw"].post(f"/db/steward/proposals/concept/{code}/reject", json={"label": i["label"], "key": i["key"], "note": "관련 없음"}).status_code == 200
    with db() as s:
        ds = s.get(Dataset, code)
        assert any(c["key"] == "햇살론" and c.get("about") for c in ds.mapping.get("concepts") or [])
        rels = collect_graph(s).rels
        assert any(rt == "DESCRIBES" and (code, "햇살론") in {(x["from"], x["to"]) for x in items} for (rt, _f, _t), items in rels.items())
        card = s.execute(select(KbChunk).where(KbChunk.source_key == f"dataset:{code}")).scalars().first()
        assert card is not None and "햇살론" in (card.concepts or []) and "연결 개념" in card.text
    # 반려한 연결은 구축을 다시 돌려도 다시 제안하지 않는다
    with db() as s:
        emit(s, "manual", {"workflow": "wf_ontology_build", "reason": "시험 재실행"}, "test")
        s.commit()
    drain_workflows(db)
    again = {(i["label"], i["key"]) for i in _items(world["stw"]) if i.get("dataset") == code and i["kind"] == "concept"}
    assert not again & {(i["label"], i["key"]) for i in others} and ("ProductGroup", "햇살론") not in again


def test_metric_proposal_approved_by_steward_computes(world, db):
    from conftest import drain_workflows

    from nhdip.models import Metric, MetricValue

    code = world["code"]
    mets = [i for i in _items(world["stw"]) if i.get("dataset") == code and i["kind"] == "metric"]
    assert mets
    m = mets[0]
    assert world["other"].post(f"/db/steward/proposals/metric/{m['code']}/approve", json={}).status_code == 404
    assert world["stw"].post(f"/db/steward/proposals/metric/{m['code']}/approve", json={}).status_code == 200
    drain_workflows(db)
    with db() as s:
        assert s.get(Metric, m["code"]).enabled
        assert s.execute(select(MetricValue).where(MetricValue.metric_code == m["code"])).first() is not None
    for x in mets[1:]:
        assert world["stw"].post(f"/db/steward/proposals/metric/{x['code']}/reject", json={"note": "중복"}).status_code == 200
    assert not [i for i in _items(world["stw"]) if i.get("dataset") == code and i["kind"] == "metric"]
