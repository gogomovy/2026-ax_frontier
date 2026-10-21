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


def test_ontology_proposals_split_by_dataset_and_unscoped_ops_stay_admin():
    from nhdip.graph.proposals import proposal_datasets
    from nhdip.workflow.onto_nodes import _proposal_groups

    cls = {"op": "add_class", "class": {"label": "Channel", "backing": [{"dataset": "A", "key_col": "k"}]}}
    prop = {"op": "add_property", "label": "Channel", "property": {"name": "kind"}}
    rel = {"op": "add_relation", "relation": {"type": "IN_CHANNEL", "from": "Sale", "to": "Channel", "backing": [{"dataset": "B", "from_col": "id", "to_col": "ch"}]}}
    other = {"op": "add_class", "class": {"label": "Topic", "backing": [{"dataset": "C", "key_col": "k"}]}}
    alias = {"op": "add_alias", "label": "Channel", "key": "CH01", "aliases": ["창구"]}
    # 속성은 같은 제안에서 그 클래스에 원천을 붙이는 자료로 본다 · 원천 없는 연산(별칭 · 홀로 남은 속성)은 부서로 가를 수 없다
    assert proposal_datasets([cls, prop]) == ({"A"}, False)
    assert proposal_datasets([prop]) == (set(), True)
    assert proposal_datasets([cls, alias]) == ({"A"}, True)
    assert proposal_datasets([{"op": "update_class", "label": "Channel", "set": {"ko": "채널"}}]) == (set(), True)

    def it(op, ds, group="model"):
        return {"op": op, "group": group, "datasets": ds, "confidence": 0.9, "why": "", "by": "rule"}

    groups = _proposal_groups([it(cls, ["A"]), it(prop, ["A"]), it(other, ["C"]), it(rel, ["B"], "link"), it(alias, [], "alias")])
    # 새 클래스(Channel · 자료 A)를 잇는 링크(자료 B)는 클래스 제안과 한 묶음 — 따로면 적용 검증에서 실패한다
    assert [[x["op"] for x in g] for g in groups] == [[cls, prop, rel], [other], [alias]]


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


def _upload_master(world, filename: str, body: str) -> str:
    r = world["req"].post("/db/uploads/dataset", data={"data_origin": "simulated"}, files={"file": (filename, io.BytesIO(body.encode("utf-8")), "text/csv")})
    assert r.status_code == 201, r.text
    return _approve_upload(world["stw"], r.json()["id"])["result"]["createdDataset"]


def _onto(c: TestClient, code: str, status: str = "pending") -> list[dict]:
    return [i for i in _items(c, status) if i["kind"] == "ontology" and code in {d["code"] for d in i["datasets"]}]


def test_ontology_change_on_own_dataset_is_reviewed_by_steward(world, db):
    from conftest import drain_workflows

    from nhdip.events import emit
    from nhdip.graph.proposals import active
    from nhdip.models import OntologyProposal

    # 부서가 올린 기준 정보 표(키 하나) 두 개 → 구축 에이전트가 자료마다 '새 객체 유형' 제안
    a = _upload_master(world, "영업채널_마스터.csv", "채널코드,채널명,채널구분\nCHX01,창구,대면\nCHX02,인터넷뱅킹,비대면\nCHX03,모바일앱,비대면\nCHX04,ATM,무인\n")
    b = _upload_master(world, "상담유형_마스터.csv", "상담코드,상담명,상담분류\nQAX01,예금상담,수신\nQAX02,대출상담,여신\nQAX03,카드상담,카드\n")
    drain_workflows(db)
    pa, pb = _onto(world["stw"], a), _onto(world["stw"], b)
    assert len(pa) == 1 and len(pb) == 1, (pa, pb)
    pa, pb = pa[0], pb[0]
    assert [d["code"] for d in pa["datasets"]] == [a] and pa["scoped"] and pa["canReview"]
    assert any(o["op"]["op"] == "add_class" for o in pa["ops"]) and all(o.get("why") for o in pa["ops"])  # 근거가 연산과 같은 순서
    assert pa["pid"] != pb["pid"]  # 자료별로 갈린다
    # 다른 부서 책임자는 보지도 승인하지도 못한다(없는 것처럼) · 관리자는 본다
    assert not _onto(world["other"], a)
    assert world["other"].post(f"/db/steward/proposals/ontology/{pa['pid']}/approve", json={}).status_code == 404
    assert _onto(world["admin"], a)
    with db() as s:
        v0 = active(s).version
    r = world["stw"].post(f"/db/steward/proposals/ontology/{pa['pid']}/approve", json={})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "applied" and r.json()["version"] == v0 + 1
    with db() as s:
        sc = active(s)
        assert sc.version == v0 + 1
        assert any(bk.get("dataset") == a for c in sc.classes or [] for bk in c.get("backing") or [])
        p = s.get(OntologyProposal, pa["pid"])
        assert p.status == "applied" and p.decided_by == STW
    assert world["stw"].post(f"/db/steward/proposals/ontology/{pa['pid']}/approve", json={}).status_code == 409  # 이미 처리됨
    assert _onto(world["stw"], a, "approved")
    # 반려는 사유 필수 · 반려한 변경은 구축을 다시 돌려도 다시 제안하지 않는다
    assert world["stw"].post(f"/db/steward/proposals/ontology/{pb['pid']}/reject", json={}).status_code == 422
    assert world["stw"].post(f"/db/steward/proposals/ontology/{pb['pid']}/reject", json={"note": "업무 개체가 아님"}).status_code == 200
    with db() as s:
        emit(s, "manual", {"workflow": "wf_ontology_build", "reason": "시험 재실행"}, "test")
        s.commit()
    drain_workflows(db)
    assert not _onto(world["stw"], b) and _onto(world["stw"], b, "rejected")


def test_ontology_steward_review_can_be_turned_off(world, db):
    from nhdip.models import Setting

    with db() as s:
        st = s.get(Setting, "ontology.build")
        orig = dict(st.value)
        st.value = {**orig, "steward_review": False}
        s.commit()
    try:
        assert not [i for i in _items(world["stw"], "") if i["kind"] == "ontology"]
        assert [i for i in _items(world["admin"], "") if i["kind"] == "ontology"]
    finally:
        with db() as s:
            s.get(Setting, "ontology.build").value = orig
            s.commit()


def test_yoy_without_same_month_compares_nearest_stored_period_and_says_so(world, db):
    """1월 · 8월 · 9월만 올린 자료에서 '전년 동기($latest-12 = 2025.09)'는 없다 — 최신보다 앞선 가장 가까운 기준일(2026.01)과 견주고,
    그 사실이 계산 근거 · 이 지표를 쓰는 지표(증가율)까지 따라간다. 설정 strict 면 비교하지 않는다(값 없음)."""
    from nhdip.calc.metrics import EvalContext, evaluate
    from nhdip.models import Dataset, Metric, Setting

    code = world["code"]
    with db() as s:
        ds = s.get(Dataset, code)
        col = {c["label"]: c["name"] for c in ds.columns}
        ym = ds.as_of_column

        def q(tok: str) -> dict:
            return {"q": {"dataset": code, "where": {ym: tok, col["상품군"]: {"nin": ["합계"]}}, "col": col["공급잔액"], "agg": "sum"}}

        def mets() -> list[Metric]:
            common = {"unit": "NONE", "decimals": 2, "sort": 0, "workflow_code": "wf_x", "figure_ids": []}
            return [Metric(code="t_now", label="현재", formula="VALUE", args={"value": q("$latest")}, **common),
                    Metric(code="t_yoy", label="전년 동기", formula="VALUE", args={"value": q("$latest-12")}, **common),
                    Metric(code="t_chg", label="전년 동기 대비 증가율", formula="GROWTH_RATE", args={"v0": {"metric": "t_yoy"}, "v1": {"metric": "t_now"}}, **common)]

        out = evaluate(EvalContext(s), mets())
        fb = [{"col": ym, "token": "$latest-12", "wanted": "202509", "used": "202601", "latest": "202609", "months": 8, "wantedMonths": 12}]
        assert float(out["t_now"].value) == 800 and float(out["t_yoy"].value) == 350  # 9월 vs 1월(합계 행 제외)
        assert out["t_now"].fallbacks == [] and out["t_yoy"].fallbacks == fb and out["t_chg"].fallbacks == fb
        assert round(float(out["t_chg"].value), 2) == 128.57
        note = "전년 동기(2025.09) 자료가 없어 가장 가까운 기준일 2026.01 과 비교"
        assert note in out["t_chg"].trace["warnings"] and out["t_chg"].trace["periodBasis"] == fb
        s.rollback()

        st = s.get(Setting, "calc.period_fallback")
        if st is None:
            s.add(Setting(key="calc.period_fallback", value="strict"))
        else:
            st.value = "strict"
        s.flush()
        out = evaluate(EvalContext(s), mets())
        assert out["t_yoy"].error and out["t_chg"].error and out["t_now"].error is None
        s.rollback()


def test_goal_and_period_params_follow_actual_comparison_span(world, db):
    """비교 기간 맞춤(PER-05) — 전년 동기(12개월) 대신 8개월(2026.01 → 2026.09)과 견줬으면, 경영목표 대비 이탈은 목표를 8/12 로 환산해 견주고
    CAGR 기간 인자는 실제 비교 기간으로 바꾼다. 맞춘 결과는 다시 맞추지 않고(normalized), 목표 판정 · 계산 기록 · 저장 값이 같은 기준을 쓴다."""
    from decimal import Decimal

    from nhdip.calc.metrics import EvalContext, evaluate, run_basis
    from nhdip.models import Dataset, Metric, Rule, RuleVersion, Setting
    from nhdip.views.goal_verdict import apply_goal_verdicts

    code = world["code"]
    with db() as s:
        ds = s.get(Dataset, code)
        col = {c["label"]: c["name"] for c in ds.columns}
        ym = ds.as_of_column

        def q(tok: str) -> dict:
            return {"q": {"dataset": code, "where": {ym: tok, col["상품군"]: {"nin": ["합계"]}}, "col": col["공급잔액"], "agg": "sum"}}

        s.add(Rule(code="T_GOALS", name="시험 목표", kind="threshold", active_version=1))
        s.flush()
        s.add(RuleVersion(rule_code="T_GOALS", version=1, body={"growth": 12}))
        links = s.get(Setting, "goal.rule_links")
        orig = dict(links.value) if links is not None else None
        if links is None:
            s.add(Setting(key="goal.rule_links", value={"goal-t": {"rule": "T_GOALS", "path": "growth"}}))
        else:
            links.value = {**links.value, "goal-t": {"rule": "T_GOALS", "path": "growth"}}
        s.flush()
        common = {"unit": "PCT", "decimals": 2, "sort": 0, "workflow_code": "wf_x", "figure_ids": []}
        mets = [Metric(code="g_now", label="현재", formula="VALUE", args={"value": q("$latest")}, **{**common, "unit": "NONE"}),
                Metric(code="g_yoy", label="전년 동기", formula="VALUE", args={"value": q("$latest-12")}, **{**common, "unit": "NONE"}),
                Metric(code="g_chg", label="전년 동기 대비 증가율", formula="GROWTH_RATE", args={"v0": {"metric": "g_yoy"}, "v1": {"metric": "g_now"}}, **common),
                Metric(code="g_goal", label="경영목표", formula="VALUE", args={"value": {"rule": "T_GOALS", "path": "growth", "label": "확정 목표"}}, **common),
                Metric(code="g_gap", label="목표 대비 이탈", formula="DIFF", args={"a": {"metric": "g_chg"}, "b": {"metric": "g_goal", "label": "경영목표"}}, **{**common, "unit": "PP"}),
                Metric(code="g_cagr", label="연평균 성장률", formula="CAGR", args={"v_start": q("$latest-12"), "v_end": q("$latest"), "years": {"const": 1, "label": "기간(년)"}}, **common)]
        out = evaluate(EvalContext(s), mets)
        chg, goal, gap, cagr = (float(out[k].value) for k in ("g_chg", "g_goal", "g_gap", "g_cagr"))
        assert out["g_goal"].goal and not out["g_chg"].goal
        # 목표 12% × 8/12 = 8% 와 견준다 — 이탈 = 128.57 − 8
        assert goal == 12 and round(gap, 2) == round(chg - 8, 2)
        assert out["g_gap"].align["goal"]["b"]["from"] == "12" and Decimal(out["g_gap"].align["goal"]["b"]["to"]) == 8
        assert all(f.get("normalized") for f in out["g_gap"].fallbacks) and not any(f.get("normalized") for f in out["g_chg"].fallbacks)
        assert any("경영목표" in w and "8/12" in w for w in out["g_gap"].trace["warnings"])
        # CAGR 기간 1년 → 8개월(0.667년) — 연평균은 실제 비교 기간으로
        assert round(cagr, 4) == round(((800 / 350) ** (12 / 8) - 1) * 100, 4)
        assert out["g_cagr"].align["params"]["years"]["from"] == "1"
        # 계산 기록에 비교 기준이 남는다 — 저장된 값을 다른 지표가 읽어도 맞춤 표시가 따라간다(변화 감지 · 선행 지표)
        assert all(f.get("normalized") for f in run_basis(s, out["g_gap"].calc_run_id))
        # 목표 판정 — 실적(증가율)은 8개월 값이라 목표를 8/12 로 환산해 판정 · 근거를 남긴다
        actual = {"id": "g_chg", "label": "증가율", "unit": "PCT", "value": chg, "basis": out["g_chg"].fallbacks}
        arts = {"goals": [{"id": "goal-t", "targetType": "growth", "direction": "increase", "unit": "PCT", "targetValue": 12, "actual": actual}]}
        apply_goal_verdicts(s, arts)
        g = arts["goals"][0]
        assert g["gapVerdict"] == "on_track" and g["gapBasis"]["aligned"] == 8 and g["gapBasis"]["months"] == 8 and "8개월로 환산" in g["gapBasis"]["note"]
        # 설정 off — 맞추지 않고 판정 보류
        st = s.get(Setting, "calc.period_align")
        if st is None:
            s.add(Setting(key="calc.period_align", value="off"))
        else:
            st.value = "off"
        s.flush()
        arts["goals"][0]["actual"]["value"] = 9.0  # 8% 환산 목표면 정상 · 연 목표 12% 면 미달 — 보류는 어느 쪽도 아님
        apply_goal_verdicts(s, arts)
        assert arts["goals"][0]["gapVerdict"] is None and arts["goals"][0]["gapBasis"]["held"]
        out2 = evaluate(EvalContext(s), [m for m in mets if m.code in ("g_now", "g_yoy", "g_chg", "g_goal", "g_gap")])
        assert round(float(out2["g_gap"].value), 2) == round(chg - 12, 2) and out2["g_gap"].align is None
        s.rollback()
        if orig is None:
            assert s.get(Setting, "goal.rule_links") is None


def test_period_span_helpers_and_goal_verdict_alignment():
    from decimal import Decimal

    from nhdip.calc.metrics import span_months, span_of
    from nhdip.views.goal_verdict import align_target, verdict_of

    assert span_months("202609", "202509", "202601") == {"months": 8, "wantedMonths": 12}
    assert span_months("x", "202509", "202601") == {}
    b = {"token": "$latest-12", "used": "202601", "wanted": "202509", "latest": "202609", "months": 8, "wantedMonths": 12}
    assert span_of([b]) == b and span_of([{**b, "normalized": True}]) is None and span_of([{**b, "months": 12}]) is None
    # 원래 비교 기간이 가장 긴 대체를 고른다(전년 동기 · 2년 전이 섞이면 2년 전)
    b24 = {**b, "token": "$latest-24", "months": 20, "wantedMonths": 24}
    assert span_of([b, b24]) == b24
    pol = {"near_pct": 10.0, "maintain_tol_pp": 1.0}
    g = {"targetType": "limit", "direction": "decrease", "unit": "PCT", "actual": {"value": 3.0, "unit": "PCT", "basis": [b]}}
    eff, info = align_target(g, Decimal("4"), "prorate")
    assert round(float(eff), 4) == round(4 * 8 / 12, 4) and info["aligned"] == float(eff)
    assert verdict_of(g, eff, "PCT", pol) == "breach"  # 8개월에 3% 는 연 4% 한도(8개월 환산 2.67%)를 넘는다
    assert verdict_of(g, Decimal("4"), "PCT", pol) == "on_track"  # 맞추지 않으면 정상으로 잘못 보인다
    # 구성비(ratio) 목표는 수준이라 환산하지 않는다 — 근거만
    r = {**g, "targetType": "ratio"}
    assert align_target(r, Decimal("40"), "prorate")[0] == Decimal("40") and "aligned" not in align_target(r, Decimal("40"), "prorate")[1]
    # 대체가 없으면 그대로
    assert align_target({**g, "actual": {"value": 3.0}}, Decimal("4"), "prorate") == (Decimal("4"), None)


def test_templates_and_agents_speak_the_actual_comparison_period():
    from types import SimpleNamespace

    from nhdip.views.period_words import basis_range, basis_short, figure_note, figures_span
    from nhdip.views.template import eval_condition, render_text
    from nhdip.workflow.agent_nodes import basis_change

    b = {"token": "$latest-12", "used": "202601", "wanted": "202509", "latest": "202609", "months": 8, "wantedMonths": 12}
    idx = {"chg": {"id": "chg", "label": "2026.01 대비 증가율", "unit": "PCT", "value": 9.0, "decimals": 2, "basis": [b]},
           "goal": {"id": "goal", "label": "경영목표", "unit": "PCT", "value": 12.0, "decimals": 1, "goal": True}}
    # 실적 9%(8개월) vs 목표 12% — 환산 목표 8% 와 견주면 상회
    assert eval_condition("chg<goal", idx) is False and eval_condition("chg>goal", idx) is True
    span = figures_span(idx)
    text = render_text("증가율 [[fig:chg]] · 목표 [[fig:goal]] 대비 [[if:chg<goal|하회|상회]]", idx, span=span)
    assert text == "증가율 9.00% · 목표 12.0%(8개월 환산 8.00%) 대비 상회"
    kept = render_text("목표 [[fig:goal]] 대비", idx, keep_fig=True, span=span)
    assert kept == "목표 [[fig:goal]](8개월 환산 8.00%) 대비"  # 수치 칩은 그대로, 환산 값은 글로
    assert render_text("목표 [[fig:goal]]", idx) == "목표 12.0%"  # 비교 기간이 원래와 같으면 붙이지 않는다
    assert "8개월로 환산하면 8.0" in figure_note(idx["goal"], span) and "2026.01" in figure_note(idx["chg"], span)
    assert basis_short([b], {"goal": {"b": {}}, "months": 8, "wantedMonths": 12}) == "2026.01 대비 · 목표 8개월 환산"
    assert basis_range([b]) == "2026.01~2026.09" and basis_range([]) is None
    # 변화 감지 — 직전 기록이 없고 이번에 대체됐으면 기준 변경, 둘 다 없으면 아님
    oc = SimpleNamespace(fallbacks=[b], previous_run=None)
    assert basis_change(None, oc) == {"before": "전년 동기 대비", "after": "2026.01 대비"}
    assert basis_change(None, SimpleNamespace(fallbacks=[], previous_run=None)) is None


def test_link_to_other_departments_object_type_needs_admin(world, db):
    """다른 부서 자료로 만든 객체 유형으로 잇는 링크(§40 STW-08) — 그 부서 그래프에도 관계가 생기므로 양쪽을 소유한 책임자 · 관리자만 승인."""
    from conftest import drain_workflows

    # 종합기획부(T111) 사용자가 올리고 그 부서 책임자가 승인한 기준 정보 표
    peer = _user(world["admin"], "20259174", "T111")
    r = peer.post("/db/uploads/dataset", data={"data_origin": "simulated"},
                  files={"file": ("지역본부_마스터.csv", io.BytesIO("지역코드,지역명\nRGX01,서울\nRGX02,경기\nRGX03,부산\nRGX04,대구\n".encode("utf-8")), "text/csv")})
    assert r.status_code == 201, r.text
    theirs = _approve_upload(world["other"], r.json()["id"])["result"]["createdDataset"]
    drain_workflows(db)
    pt = _onto(world["other"], theirs)
    assert len(pt) == 1 and pt[0]["canReview"], pt
    # 다른 부서(T111) 책임자는 자기 자료의 객체 유형을 승인한다
    assert world["other"].post(f"/db/steward/proposals/ontology/{pt[0]['pid']}/approve", json={}).status_code == 200
    mine = _upload_master(world, "점포_마스터.csv", "점포코드,점포명,지역코드\nSHX01,강남점,RGX01\nSHX02,수원점,RGX02\nSHX03,해운대점,RGX03\nSHX04,수성점,RGX04\nSHX05,종로점,RGX01\n")
    drain_workflows(db)
    adm = _onto(world["admin"], mine)
    linked = [p for p in adm if any(o["op"]["op"] == "add_relation" for o in p["ops"])]
    assert linked, adm
    assert theirs in {d["code"] for d in linked[0]["linkedDatasets"]}
    # 내 부서(T211) 책임자에게는 보이지 않고 승인할 수 없다(없는 것처럼) — 관리자 몫
    assert not [p for p in _onto(world["stw"], mine) if p["pid"] == linked[0]["pid"]]
    assert world["stw"].post(f"/db/steward/proposals/ontology/{linked[0]['pid']}/approve", json={}).status_code == 404
