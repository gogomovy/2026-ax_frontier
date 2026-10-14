"""Phase M (요구사항 §30 · §31 · Q179~Q197) — 온톨로지 v3 · 구축 에이전트 · 변경 제안 · 자료 등록 · 에이전트 그룹 · LLM 플랫폼 보강.

앞쪽은 DB 없이 도는 순수 시험, 뒤쪽(`db`)은 시연 자료가 올라간 시험 DB 위에서 돈다. 스키마를 바꾼 시험은 끝에 이전 판으로 되돌린다.
"""
from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

ADMIN = ("00000001", "Admin1234!")


def _admin() -> TestClient:
    from nhdip.main import app

    c = TestClient(app)
    assert c.post("/auth/login", json={"emp_no": ADMIN[0], "password": ADMIN[1]}).status_code == 200
    return c


# ═════════════════════════ 온톨로지 v3 스키마 (순수) ═════════════════════════
BASE = {
    "classes": [
        {"label": "Product", "ko": "상품", "kind": "object", "primary_key": "key", "title_property": "name", "properties": [{"name": "name", "ko": "이름", "base_type": "string"}]},
        {"label": "ProductGroup", "ko": "상품군", "kind": "concept", "properties": [{"name": "name", "ko": "이름", "base_type": "string"}]},
    ],
    "relations": [{"type": "IN_GROUP", "from": "Product", "to": "ProductGroup", "cardinality": "N:1"}],
    "aliases": {"ProductGroup": {"햇살론": ["햇살론뱅크"]}},
    "interfaces": [{"name": "BusinessConcept", "ko": "업무 개념", "properties": ["name"]}],
}


def test_validate_schema_catches_endpoints_alias_labels_types_and_cardinality():
    from nhdip.graph.schema import validate_schema

    assert validate_schema(BASE)["errors"] == []
    bad = {**BASE, "relations": [{"type": "IN_GROUP", "from": "Product", "to": "Nope", "cardinality": "M:N"}], "aliases": {"Ghost": {"a": []}},
           "classes": [*BASE["classes"], {"label": "X", "properties": [{"name": "v", "base_type": "money"}], "primary_key": "zzz", "implements": ["Missing"]}]}
    errs = " | ".join(validate_schema(bad)["errors"])
    for frag in ("to 클래스 없음 Nope", "cardinality", "별칭의 클래스 없음: Ghost", "base_type", "primary_key", "없는 인터페이스"):
        assert frag in errs, frag


def test_apply_ops_is_idempotent_and_reports_skips():
    from nhdip.graph.schema import apply_ops, diff_schema, op_key

    ops = [
        {"op": "add_class", "class": {"label": "Branch", "ko": "영업점", "kind": "object", "properties": [{"name": "name", "ko": "이름", "base_type": "string"}], "backing": [{"dataset": "BRANCH", "key_col": "code"}]}},
        {"op": "add_relation", "relation": {"type": "IN_BRANCH", "from": "Product", "to": "Branch", "cardinality": "N:1", "backing": [{"dataset": "P", "from_col": "pc", "to_col": "bc"}]}},
        {"op": "add_alias", "label": "ProductGroup", "key": "햇살론", "aliases": ["햇살론15", "햇살론뱅크"]},
        {"op": "add_property", "label": "Product", "property": {"name": "group", "ko": "상품군", "base_type": "code"}},
    ]
    new, applied, skipped = apply_ops(BASE, ops)
    assert len(applied) == 4 and not skipped
    assert new["aliases"]["ProductGroup"]["햇살론"] == ["햇살론뱅크", "햇살론15"]  # 이미 있는 별칭은 다시 넣지 않음
    again, applied2, skipped2 = apply_ops(new, ops)
    assert not applied2 and len(skipped2) == 4 and again == new  # 멱등
    assert BASE["classes"][0].get("properties")[-1]["name"] == "name"  # 입력은 바뀌지 않음
    d = diff_schema(BASE, new)
    assert d["classesAdded"] == ["Branch"] and "IN_BRANCH:Product→Branch" in d["relationsAdded"] and d["aliasesAdded"][0]["aliases"] == ["햇살론15"]
    assert op_key(ops[2]) != op_key({**ops[2], "aliases": ["다른"]})


def test_profile_and_link_candidates_are_deterministic():
    from types import SimpleNamespace

    from nhdip.graph.extraction import Resolver
    from nhdip.graph.links import link_candidates, object_type_candidates
    from nhdip.graph.profile import profile_rows

    prod = SimpleNamespace(code="PRODUCTS", name="상품 마스터", kind="master", origin="bank", description="", key_columns=["product_code"], as_of_column=None, mapping={},
                           columns=[{"name": "product_code", "label": "상품코드", "type": "str"}, {"name": "product_name", "label": "상품명", "type": "str"}, {"name": "group", "label": "상품군", "type": "str"}, {"name": "bal_amt", "label": "잔액", "type": "num"}])
    rows = [{"product_code": f"P{i:03d}", "product_name": f"상품{i}", "group": "햇살론뱅크" if i % 2 else "햇살론", "bal_amt": 100.0 + i} for i in range(20)]
    prof = profile_rows(prod, rows)
    assert prof["columns"]["product_code"]["keyCandidate"] and prof["columns"]["bal_amt"]["semantic"] == "amount" and "bal_amt" in prof["measures"]
    assert prof["columns"]["product_name"]["semantic"] == "name" and prof["columns"]["group"]["semantic"] == "code"
    schema = SimpleNamespace(version=1, classes=BASE["classes"][1:], relations=[], aliases=BASE["aliases"], interfaces=[])
    res = Resolver(schema)
    pol = {"link_min_containment": 0.95, "link_min_distinct": 1}
    cands = object_type_candidates([prod], {"PRODUCTS": prof}, schema, {"PRODUCTS": rows}, res, pol)
    assert len(cands) == 1 and cands[0]["label"] == "Products" and cands[0]["key_col"] == "product_code" and cands[0]["title_col"] == "product_name"
    assert "bal_amt" not in cands[0]["props"]  # 측정값은 객체 속성으로 복제하지 않는다
    links = link_candidates([prod], {"PRODUCTS": prof}, schema, {"PRODUCTS": rows}, res, pol, planned={"PRODUCTS": ("Products", "product_code")})
    assert len(links) == 1 and links[0]["to_class"] == "ProductGroup" and links[0]["to_col"] == "group" and links[0]["cardinality"] == "N:1" and links[0]["containment"] == 1.0


def test_resolver_similarity_and_best_match():
    from nhdip.graph.resolve import best_match, similarity

    assert similarity("햇살론 뱅크", "햇살론뱅크") == 1.0
    assert similarity("새희망홀씨", "새희망홀씨대출") >= 0.85
    m = best_match({"label": "ProductGroup", "raw": "햇살론-뱅크"}, {"ProductGroup": [("햇살론", "햇살론"), ("햇살론", "햇살론뱅크"), ("사잇돌", "사잇돌")]})
    assert m["key"] == "햇살론" and m["score"] == 1.0 and m["ambiguous"] == []


# ═════════════════════════ 시험 DB ═════════════════════════
def test_seeded_schema_is_v3_and_projection_reads_backing(db):
    from nhdip.graph.projection import active_schema, collect_graph
    from nhdip.graph.schema import validate_schema, as_dict

    with db() as s:
        sc = active_schema(s)
        prod = next(c for c in sc.classes if c["label"] == "Product")
        assert prod.get("ko") == "상품" and prod.get("kind") == "object" and prod.get("properties")
        assert any(r.get("cardinality") for r in sc.relations) and sc.interfaces
        assert validate_schema(as_dict(sc), s)["errors"] == []
        b = collect_graph(s, sc)
        assert isinstance(b.dangling(), dict)


def test_ontology_build_workflow_profiles_and_proposes_then_admin_applies(db):
    from nhdip.graph.projection import active_schema
    from nhdip.models import DataProfile, OntologyProposal, Workflow, WorkflowNode
    from nhdip.workflow.engine import run_workflow

    with db() as s:
        assert s.get(Workflow, "wf_ontology_build") is not None
        impls = [n.impl for n in s.execute(select(WorkflowNode).where(WorkflowNode.workflow_code == "wf_ontology_build").order_by(WorkflowNode.seq)).scalars()]
        assert impls == ["profile_datasets", "design_object_types", "discover_links", "resolve_entities", "check_ontology", "propose_ontology"]
        before = active_schema(s).version
        run = run_workflow(s, "wf_ontology_build", [{"type": "manual", "payload": {"workflow": "wf_ontology_build"}}])
        assert run.status in ("succeeded", "degraded"), run.error
        assert s.execute(select(DataProfile)).first() is not None  # 구조 파악 결과 저장
        assert active_schema(s).version == before  # 스키마는 제안으로만 바뀐다(Q181)
        pending = s.execute(select(OntologyProposal).where(OntologyProposal.status == "pending")).scalars().all()
        assert pending, "구축 에이전트가 제안을 만들지 않음"
        p = pending[0]
        assert p.ops and p.validation.get("errors") == [] and "nodesDelta" in (p.impact or {})
        pid = p.id
        # 다시 돌려도(남은 데이터셋을 이어서 파악) 대기 중 제안끼리 같은 연산이 겹치지 않는다
        run_workflow(s, "wf_ontology_build", [{"type": "manual", "payload": {}}])
        from nhdip.graph.proposals import create_proposal
        from nhdip.graph.schema import op_key

        keys = [op_key(o) for q in s.execute(select(OntologyProposal).where(OntologyProposal.status == "pending")).scalars() for o in q.ops]
        assert len(keys) == len(set(keys))
        assert create_proposal(s, list(p.ops), title="같은 연산") is None  # 대기 중 제안과 같은 연산이면 만들지 않는다
    c = _admin()
    lst = c.get("/admin/ontology/proposals?status=pending").json()
    assert any(x["id"] == pid for x in lst["proposals"])
    r = c.post(f"/admin/ontology/proposals/{pid}/decide", json={"approve": True})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "applied" and r.json()["version"] > before
    st = c.get("/admin/ontology/build").json()
    assert st["runs"] and st["stages"] and any(x["profiled"] for x in st["profiles"])
    # 되돌리기 — 이전 판 내용으로 새 판(뒤 시험이 시드 스키마를 보게)
    back = c.post(f"/admin/ontology/schema/{before}/activate")
    assert back.status_code == 200, back.text
    with db() as s:
        from nhdip.graph.schema import diff_schema, as_dict
        from nhdip.models import OntologySchema

        assert diff_schema(as_dict(s.get(OntologySchema, before)), as_dict(active_schema(s)))["classesAdded"] == []


def test_schema_put_rejects_broken_schema_and_proposal_reject_needs_note(db):
    c = _admin()
    cur = c.get("/admin/ontology").json()["schema"]
    broken = {**cur, "relations": [*cur["relations"], {"type": "BROKEN_REL", "from": "Product", "to": "NoSuchClass"}]}
    r = c.put("/admin/ontology/schema", json={k: broken[k] for k in ("classes", "relations", "aliases", "interfaces")})
    assert r.status_code == 422 and "NoSuchClass" in r.text
    from nhdip.graph.proposals import create_proposal

    with db() as s:
        p = create_proposal(s, [{"op": "add_alias", "label": "ProductGroup", "key": "햇살론", "aliases": ["시험용 별칭 M"]}], title="시험", source="admin", with_impact=False)
        s.commit()
        pid = p.id
    assert c.post(f"/admin/ontology/proposals/{pid}/decide", json={"approve": False}).status_code == 422
    assert c.post(f"/admin/ontology/proposals/{pid}/decide", json={"approve": False, "note": "시험 반려"}).json()["status"] == "rejected"


def test_config_trigger_and_dataset_wildcard_match(db):
    from nhdip.models import OutboxEvent
    from nhdip.workflow.dispatcher import match_event

    with db() as s:
        m = match_event(s, OutboxEvent(id=0, type="config.changed", payload={"kind": "dataset", "code": "X"}))
        assert "wf_ontology_build" in m
        m2 = match_event(s, OutboxEvent(id=0, type="dataset.committed", payload={"dataset": "INCLUSIVE_PRODUCTS"}))
        assert "wf_ontology_build" in m2
        assert "wf_ontology_build" not in match_event(s, OutboxEvent(id=0, type="config.changed", payload={"kind": "setting", "key": "x"}))


# ═════════════════════════ 자료 등록(온보딩) · 정의 관리 (§31) ═════════════════════════
PW = "abcd1234"
I_REQ, I_STW = "20259171", "20259172"  # 신용리스크관리부(T211) 일반 사용자 · 데이터 책임자


def _client() -> TestClient:
    from nhdip.main import app

    return TestClient(app)


def _login(c: TestClient, emp: str, pw: str) -> None:
    from nhdip import ratelimit

    ratelimit.reset()
    assert c.post("/auth/login", json={"emp_no": emp, "password": pw}).status_code == 200


def _user(admin: TestClient, emp: str, org: str, steward: bool = False) -> TestClient:
    c = _client()
    c.post("/auth/signup", json={"emp_no": emp, "name": f"자료등록{emp[-2:]}", "password": PW, "org_code": org})
    admin.post(f"/admin/users/{emp}/approve")
    _login(c, emp, PW)
    if steward:
        assert admin.patch(f"/admin/users/{emp}", json={"data_steward": True}).status_code == 200
    return c


@pytest.fixture(scope="module")
def iw(db):
    admin = _client()
    _login(admin, *ADMIN)
    return {"admin": admin, "req": _user(admin, I_REQ, "T211"), "stw": _user(admin, I_STW, "T211", steward=True)}


def _csv(header: str, rows: list[str]) -> bytes:
    return (header + "\n" + "\n".join(rows) + "\n").encode("utf-8")


ITEMS = [("K01", "농업인 우대"), ("K02", "청년 창업"), ("K03", "귀농 정착")]
INTAKE_CSV = _csv("기준월,지원코드,지원명,지원금액", [f"2026{m:02d},{k},{n},{100 * i + m}" for m in (6, 7) for i, (k, n) in enumerate(ITEMS, start=1)])


def _f(name: str, data: bytes, mime: str = "text/csv") -> dict:
    return {"file": (name, io.BytesIO(data), mime)}


def test_intake_new_structured_steward_applies_and_triggers_ontology_build(db, iw):
    """새 정형 자료 → 분석(정의 추론 · 구조 파악) 초안 → 책임자가 고쳐 확인 → 바로 반영 → 데이터셋 · 첫 버전 · 이벤트 · 구축 워크플로 매칭 · 설명 카드 · 반영 상태."""
    from nhdip.models import Dataset, KbChunk, OutboxEvent, UploadRequest
    from nhdip.workflow.dispatcher import match_event

    stw = iw["stw"]
    r = stw.post("/db/intake", files=_f("농업지원실적_202607.csv", INTAKE_CSV), data={"origin": "bank"})
    assert r.status_code == 201, r.text
    it = r.json()
    rid, an = it["id"], it["intake"]
    assert it["status"] == "draft" and it["kind"] == "dataset" and an["mode"] == "new" and an["kind"] == "structured"
    assert it["canApply"] is True and it["applyMode"] == "apply"
    d = an["definition"]
    code = d["code"]
    assert {c["label"] for c in d["columns"]} >= {"기준월", "지원코드", "지원명", "지원금액"}
    assert an["profile"]["rows"] == 6 and an["llm"]["by"]  # LLM 이 없으면 규칙으로 끝까지
    assert it["storage"][0]["state"] == "idle"
    with db() as s:
        assert s.get(Dataset, code) is None  # 초안은 아무것도 반영하지 않는다
    # 책임자가 이름을 고친다 — 잘못된 정의는 저장 전에 막는다
    bad = {**d, "key_columns": ["없는열"]}
    assert stw.patch(f"/db/intake/{rid}", json={"definition": bad}).status_code == 422
    d2 = {**d, "name": "농업 지원 실적(시험)"}
    p = stw.patch(f"/db/intake/{rid}", json={"definition": d2, "asOf": "2026-07-31"})
    assert p.status_code == 200, p.text
    assert p.json()["meta"]["proposal"]["name"] == "농업 지원 실적(시험)"
    # 다른 사람은 이 초안을 볼 수 없다
    assert iw["req"].get(f"/db/intake/{rid}").status_code == 404
    ok = stw.post(f"/db/intake/{rid}/submit", json={"note": "확인 완료"})
    assert ok.status_code == 200, ok.text
    out = ok.json()
    assert out["status"] == "approved" and out["result"]["createdDataset"] == code and out["result"]["via"] == "steward-self" and out["result"]["rows"] == 6
    keys = {st["key"]: st for st in out["storage"]}
    assert keys["ledger"]["state"] == "done" and "profile" in keys and "catalog" in keys and "workflows" in keys
    # 다시 제출 · 버리기는 초안만
    assert stw.post(f"/db/intake/{rid}/submit", json={}).status_code == 409
    assert stw.post(f"/db/intake/{rid}/discard").status_code == 409
    with db() as s:
        ds = s.get(Dataset, code)
        assert ds is not None and ds.name == "농업 지원 실적(시험)"
        assert s.get(UploadRequest, rid).reviewed_by == I_STW
        evs = {e.type: e for e in s.execute(select(OutboxEvent).where(OutboxEvent.payload["code"].astext == code, OutboxEvent.type == "config.changed")).scalars()}
        assert "config.changed" in evs
        com = s.execute(select(OutboxEvent).where(OutboxEvent.type == "dataset.committed", OutboxEvent.payload["dataset"].astext == code)).scalars().first()
        assert com is not None and "wf_ontology_build" in match_event(s, com)  # 반영 → 온톨로지 구축 에이전트가 이어 받는다
        card = s.execute(select(KbChunk).where(KbChunk.source_key == f"dataset:{code}")).scalars().all()
        assert len(card) == 1 and card[0].source_kind == "dataset" and card[0].required_resource == "datasets"
        assert "농업 지원 실적(시험)" in card[0].text and "지원금액" in card[0].text
        assert not any(v in card[0].text for v in ("106", "207", "306", "307"))  # 설명만, 값(금액) 없음
    mine = stw.get("/db/intake/mine").json()
    assert any(x["id"] == rid and x["mode"] == "new" for x in mine["items"]) and mine["applyMode"] == "apply"


def test_intake_existing_dataset_by_plain_user_goes_to_steward(db, iw):
    """기존 자료 다음 달 파일 — 일반 사용자는 승인 요청(대기)이 되고, 책임자가 기존 승인 화면에서 승인한다."""
    req, stw = iw["req"], iw["stw"]
    code = next(x["target"] for x in stw.get("/db/intake/mine").json()["items"] if x["mode"] == "new")
    nxt = _csv("기준월,지원코드,지원명,지원금액", [f"202608,{k},{n},{50 + i}" for i, (k, n) in enumerate(ITEMS)])
    r = req.post("/db/intake", files=_f("농업지원실적_202608.csv", nxt), data={"origin": "bank"})
    assert r.status_code == 201, r.text
    it = r.json()
    assert it["intake"]["mode"] == "existing" and it["target"] == code and it["canApply"] is False and it["applyMode"] == "request"
    assert it["intake"]["quality"] in ("passed", "warning") or isinstance(it["intake"]["quality"], (str, dict))
    sub = req.post(f"/db/intake/{it['id']}/submit", json={})
    assert sub.status_code == 200 and sub.json()["status"] == "pending"
    assert any(x["id"] == it["id"] for x in stw.get("/db/uploads/review").json()["items"])
    ok = stw.post(f"/db/uploads/{it['id']}/approve", json={"note": "다음 달 승인"})
    assert ok.status_code == 200, ok.text
    assert ok.json()["result"]["status"] == "committed" and ok.json()["result"]["version"] == 2


def test_intake_document_draft_patch_discard_and_apply(db, iw):
    """비정형 — 본문 → 규칙(분류 · 기관 · 시행일) 초안 → 고치기 → 버리기(파일도 지움) / 반영(문서 · 청크 · 단계 상태)."""
    import os

    from nhdip.models import UploadRequest

    stw = iw["stw"]
    body = "농업인 지원 정책 안내\n금융위원회는 2026. 7. 1. 부터 농업인 정책자금 지원 방안을 시행한다.\n" + "세부 내용 " * 80
    r = stw.post("/db/intake", data={"text": body, "title": "농업인 지원 정책 안내(시험)"})
    assert r.status_code == 201, r.text
    it = r.json()
    doc = it["intake"]["document"]
    assert it["kind"] == "document" and it["status"] == "draft" and doc["title"] == "농업인 지원 정책 안내(시험)"
    assert doc["issuer"] == "금융위원회" and doc["published_at"] == "2026-07-01" and doc["origin"] == "ext"
    assert stw.patch(f"/db/intake/{it['id']}", json={"document": {"published_at": "2026/07/01"}}).status_code == 422
    with db() as s:
        path = s.get(UploadRequest, it["id"]).file_path
    assert os.path.exists(path)
    assert stw.post(f"/db/intake/{it['id']}/discard").json()["ok"] is True
    assert not os.path.exists(path)
    assert stw.get(f"/db/intake/{it['id']}").json()["status"] == "discarded"
    # 두 번째는 반영
    r2 = stw.post("/db/intake", data={"text": body, "title": "농업인 지원 정책 안내(반영 시험)"})
    rid2 = r2.json()["id"]
    p = stw.patch(f"/db/intake/{rid2}", json={"document": {"title": "농업인 지원 정책 안내(반영 시험 고침)", "issuer": "금융위원회"}})
    assert p.status_code == 200 and p.json()["meta"]["title"] == "농업인 지원 정책 안내(반영 시험 고침)"
    ok = stw.post(f"/db/intake/{rid2}/submit", json={})
    assert ok.status_code == 200, ok.text
    out = ok.json()
    assert out["status"] == "approved" and out["result"]["documentId"]
    keys = {st["key"]: st for st in out["storage"]}
    assert keys["ledger"]["state"] == "done" and {"vector", "search", "extract", "graph", "workflows"} <= set(keys)
    # 빈 요청 · 잘못된 출처
    assert stw.post("/db/intake", data={}).status_code == 422
    assert stw.post("/db/intake", data={"text": "x", "origin": "zzz"}).status_code == 422


def test_dataset_definition_delete_guard_and_seed_suppression(db, iw):
    """정의 삭제 — 버전 · 지표가 참조하면 409(이유), 참조 없는 정의는 지우고 시드가 되살리지 않게 억제 목록에 올린다. 사용/중지는 PATCH active."""
    from nhdip.models import Dataset, Setting
    from nhdip.seed import run as seed_run

    admin = iw["admin"]
    lst = {d["code"]: d for d in admin.get("/admin/datasets").json()}
    seeded = next(c for c, d in lst.items() if d.get("seedDefined"))
    r = admin.delete(f"/admin/datasets/{seeded}")
    assert r.status_code == 409 and "지울 수 없습니다" in r.json()["detail"]
    assert lst[seeded]["references"]
    created = next(x["target"] for x in iw["stw"].get("/db/intake/mine").json()["items"] if x["mode"] == "new")
    r = admin.delete(f"/admin/datasets/{created}")
    assert r.status_code == 409 and "올라온 버전" in r.json()["detail"]
    # 참조 없는 정의 — 만들고 중지 · 다시 사용 · 지우기
    new = {"code": "PHASE_M_DEL_TEST", "name": "삭제 시험", "origin": "bank", "kind": "fact", "description": "", "columns": [{"name": "k", "label": "키", "type": "str", "required": True}], "key_columns": ["k"]}
    assert admin.post("/admin/datasets", json=new).status_code in (200, 201)
    assert admin.patch("/admin/datasets/PHASE_M_DEL_TEST", json={"active": False}).status_code == 200
    assert admin.patch("/admin/datasets/PHASE_M_DEL_TEST", json={"active": True}).status_code == 200
    d = admin.delete("/admin/datasets/PHASE_M_DEL_TEST")
    assert d.status_code == 200, d.text
    assert admin.delete("/admin/datasets/PHASE_M_DEL_TEST").status_code == 404
    with db() as s:
        assert s.get(Dataset, "PHASE_M_DEL_TEST") is None
        assert "PHASE_M_DEL_TEST" in s.get(Setting, "seed.suppressed_datasets").value
    # 시드 — 억제된 정의는 넣지 않고, 억제를 빼면 다시 넣는다. SEED_DATASET_DEFS=0 이면 아무것도 넣지 않는다
    fake = {"code": "PHASE_M_SEED_FAKE", "name": "시드 시험", "origin": "bank", "kind": "fact", "description": "", "columns": [{"name": "k", "label": "키", "type": "str"}], "key_columns": ["k"]}
    mp = pytest.MonkeyPatch()
    try:
        mp.setattr(seed_run.D, "DATASETS", [*seed_run.D.DATASETS, fake])
        with db() as s:
            st = s.get(Setting, "seed.suppressed_datasets")
            st.value = [*st.value, "PHASE_M_SEED_FAKE"]
            s.flush()
            assert seed_run.seed_dataset_defs(s) == []
            st.value = [c for c in st.value if c != "PHASE_M_SEED_FAKE"]
            s.flush()
            mp.setenv("SEED_DATASET_DEFS", "0")
            assert seed_run.seed_dataset_defs(s) == []
            mp.delenv("SEED_DATASET_DEFS")
            assert seed_run.seed_dataset_defs(s) == ["PHASE_M_SEED_FAKE"]
            s.rollback()  # 시험용 변경은 모두 되돌린다
    finally:
        mp.undo()


def test_dataset_cards_reconcile_in_maintenance(db):
    """워커 주기 작업이 설명 카드를 맞춘다 — 같은 본문이면 그대로, 설정으로 끌 수 있다."""
    from nhdip.data.catalog import index_dataset_cards
    from nhdip.knowledge.maintenance import run_maintenance
    from nhdip.models import Setting

    with db() as s:
        out = run_maintenance(s)
        assert "datasetCards" in out and "skipped" not in out["datasetCards"], out.get("datasetCards")
        again = index_dataset_cards(s)
        assert again["inserted"] == 0 and again["kept"] >= 1
        s.add(Setting(key="knowledge.dataset_cards", value=False, description="시험"))
        s.flush()
        assert index_dataset_cards(s) == {"inserted": 0, "kept": 0, "deleted": 0}
        s.rollback()


# ═════════════════════════ LLM 플랫폼 보강 (LLM-P02 · P03 · P04 · P05 · P06 · P08 · P09) ═════════════════════════
def _cfg(conn_id: int = 9901):
    from nhdip.llm.client import ResolvedLlm

    return ResolvedLlm(agent_code=None, connection_id=conn_id, connection_name="시험 연결", base_url="http://gw.invalid", api_key="", model="m-test", params={}, timeout=1.0, retries=0, tools_enabled=False)


def test_breaker_opens_after_consecutive_failures_and_skips_calls(db, monkeypatch):
    import httpx

    from nhdip.llm import breaker, client

    sent = []

    def boom(*a, **kw):
        sent.append(1)
        raise httpx.ConnectError("게이트웨이 없음")

    monkeypatch.setattr(client.httpx, "post", boom)
    monkeypatch.setattr(client.time, "sleep", lambda *_: None)
    cfg = _cfg()
    with db() as s:
        for _ in range(3):
            with pytest.raises(client.LlmError):
                client.chat(s, cfg, [{"role": "user", "content": "x"}])
        assert len(sent) == 3
        with pytest.raises(breaker.BreakerOpen):  # 네 번째는 보내지 않고 곧바로 실패(LlmError 하위)
            client.chat(s, cfg, [{"role": "user", "content": "x"}])
        assert len(sent) == 3
        snap = {x["key"]: x for x in breaker.snapshot()}
        assert snap["conn:9901"]["open"] and snap["conn:9901"]["fails"] == 3
        # 다른 연결은 막히지 않는다
        with pytest.raises(client.LlmError):
            client.chat(s, _cfg(9902), [{"role": "user", "content": "x"}])
        assert len(sent) == 4
    breaker.reset()


def test_outgoing_messages_are_masked_unless_policy_off(db, monkeypatch):
    from nhdip.llm import client
    from nhdip.models import Setting

    bodies = []

    class Resp:
        status_code = 200
        text = ""

        def json(self):
            return {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}], "usage": {}}

    def fake_post(url, headers=None, json=None, timeout=None):
        bodies.append(json)
        return Resp()

    monkeypatch.setattr(client.httpx, "post", fake_post)
    msgs = [{"role": "user", "content": "담당자 연락처 010-1234-5678, 메일 kim@example.com"}]
    with db() as s:
        client.chat(s, _cfg(), msgs)
        sent = bodies[-1]["messages"][0]["content"]
        assert "010-1234-5678" not in sent and "kim@example.com" not in sent and "[휴대전화 가림]" in sent
        assert msgs[0]["content"].startswith("담당자 연락처 010")  # 호출자의 원본은 그대로
        st = s.get(Setting, "privacy.policy")
        st.value = {**st.value, "mask_llm_input": False}
        s.flush()
        client.chat(s, _cfg(), msgs)
        assert "010-1234-5678" in bodies[-1]["messages"][0]["content"]
        s.rollback()


def test_budget_check_caches_usage_aggregate(db, monkeypatch):
    from nhdip.llm import budget
    from nhdip.models import Setting

    n = []
    real = budget.status
    monkeypatch.setattr(budget, "status", lambda session: (n.append(1), real(session))[1])
    with db() as s:
        row = s.get(Setting, "llm.budget")
        val = {"monthly_tokens": 10**12, "monthly_cost": 0, "per_agent_tokens": {}, "on_exceed": "block", "warn_pct": 80}
        if row is None:
            s.add(Setting(key="llm.budget", value=val, description="시험"))
        else:
            row.value = val
        s.flush()
        budget.clear_cache()
        for _ in range(4):
            budget.check(s, None)
        assert len(n) == 1  # 30초 안에는 한 번만 집계
        row = s.get(Setting, "llm.budget")
        row.value = {**val, "cache_sec": 0}
        s.flush()
        budget.check(s, None)
        budget.check(s, None)
        assert len(n) == 3  # 설정이 바뀌면 다시 · 보관 0 이면 매번
        s.rollback()
    budget.clear_cache()


def test_narrate_format_retry_recovers_once(db, monkeypatch):
    from types import SimpleNamespace

    from nhdip.llm.client import ChatResult
    from nhdip.workflow import nodes

    outs = iter(["설명: {statement: 깨짐", '{"statement": "비중이 [[fig:fx]] 수준이다."}'])
    seen = []

    def fake_chat(session, cfg, messages, **kw):
        seen.append(kw.get("purpose"))
        t = next(outs)
        return ChatResult(t, [], {}, "call-x", {"content": t})

    monkeypatch.setattr(nodes, "chat", fake_chat)
    with db() as s:
        ctx = SimpleNamespace(session=s, run=SimpleNamespace(id="run-x"), node_run_id=None)
        st, res = nodes._narrate_call(ctx, _cfg(), [{"role": "user", "content": "x"}])
    assert st == "비중이 [[fig:fx]] 수준이다." and len(seen) == 2 and seen[1] == "chat:format-retry"
    with pytest.raises(ValueError):
        nodes._statement_of('{"statement": ""}')


def test_critic_grounding_is_advisory_by_default_and_blocks_when_set(db, monkeypatch):
    from types import SimpleNamespace

    from nhdip.models import AgentDecision, Setting
    from nhdip.workflow import llm_judge, nodes

    def fake(session, agent_code, task, context, **kw):
        assert agent_code == "critic_grounded" and context["statement"]
        return {"verdict": "unsupported", "reason": "근거 문서와 방향이 다르다", "claims": ["수준이다", "문장에 없는 구절"]}, {"by": "llm", "llm_call_id": None}

    monkeypatch.setattr(llm_judge, "ask_json", fake)
    with db() as s:
        arts = {"insights": [{"id": "ins-g", "title": "시험 의견", "statement": "기존", "figures": {"fx": {"label": "비중", "value": 1.0}}}]}

        def ctx():
            return SimpleNamespace(session=s, state={"narratives": {"ins-g": {"statement": "비중이 [[fig:fx]] 수준이다.", "figures": ["fx"], "agent": "narrator_inclusive"}}, "evidence": [], "verdicts": {}},
                                   load_artifacts=lambda: arts, changed=set(), llm_off=None, eval=SimpleNamespace(scope_suffix=""), workflow=SimpleNamespace(code="wf_test"),
                                   run=SimpleNamespace(id="run-g", job_id=None), node_run_id=None)

        node = SimpleNamespace(config={"rule": "CRITIC_RULES"}, agent_code="critic")
        rev = nodes.n_critic(ctx(), node).output["reviewed"][0]
        g = next(c for c in rev["checks"] if c["checkCode"] == "grounding")
        assert rev["passed"] is True and g["passed"] is True and g["advisory"] is True and g["verdict"] == "unsupported"
        s.flush()  # 시험 세션은 autoflush 를 끈다
        d = s.execute(select(AgentDecision).where(AgentDecision.agent_code == "critic_grounded", AgentDecision.workflow_run_id == "run-g")).scalars().first()
        assert d is not None and d.decision == "grounding" and d.detail["claims"] == ["수준이다"]  # 문장에 실제로 있는 구절만
        st = s.get(Setting, "agents.grounding")
        st.value = {"enabled": True, "block": True, "max_per_run": 6}
        s.flush()
        rev2 = nodes.n_critic(ctx(), node).output["reviewed"][0]
        assert rev2["passed"] is False and arts["insights"][0]["statement"] == "비중이 [[fig:fx]] 수준이다."  # 첫 실행(권고)은 반영, 두 번째(차단)는 반려
        st.value = {"enabled": False}
        s.flush()
        rev3 = nodes.n_critic(ctx(), node).output["reviewed"][0]
        assert not any(c["checkCode"] == "grounding" for c in rev3["checks"])
        s.rollback()


def test_assistant_tools_ontology_and_data_aggregate_respect_scope(db):
    from decimal import Decimal

    from nhdip.data.datasets import current_rows
    from nhdip.graph.projection import active_schema
    from nhdip.knowledge.access import AccessContext
    from nhdip.knowledge.assist_tools import build, data_aggregate, onto_find, onto_neighbors
    from nhdip.models import Dataset

    admin = AccessContext(emp_no="00000001", is_admin=True, org_codes=set(), resources=None, offices=None, dept_docs=None)
    plain = AccessContext(emp_no="x", is_admin=False, org_codes=set(), resources={"hq_dashboard"}, offices=None, dept_docs=None)
    with db() as s:
        names = {t["function"]["name"] for t in build(s, admin).schemas}
        assert names == {"onto_find", "onto_neighbors", "data_aggregate"}
        assert "data_aggregate" not in {t["function"]["name"] for t in build(s, plain).schemas}
        assert "권한" in data_aggregate(s, plain, "PROVISION_BY_PRODUCT", "count")["error"]
        ds = s.get(Dataset, "PROVISION_BY_PRODUCT")
        _, rows = current_rows(s, ds)
        want = sum(Decimal(str(r["provision"])) for r in rows if r.get("provision") is not None)
        got = data_aggregate(s, admin, "PROVISION_BY_PRODUCT", "sum", "provision")
        assert Decimal(got["value"]) == want and got["rows"] == len(rows) and not any(isinstance(v, list) for v in got.values())  # 행 원문 없음
        grp = data_aggregate(s, admin, "PROVISION_BY_PRODUCT", "count", group_by="ym")
        assert grp["groupCount"] >= 1 and sum(g["value"] for g in grp["groups"]) == len(rows)
        assert "정의에 없는 열" in data_aggregate(s, admin, "PROVISION_BY_PRODUCT", "sum", "provision", filters={"없는열": 1})["error"]
        assert "숫자 열" in data_aggregate(s, admin, "PROVISION_BY_PRODUCT", "sum", "product_name")["error"]
        sc = active_schema(s)
        label, entries = next((lb, e) for lb, e in (sc.aliases or {}).items() if e)
        key = next(iter(entries))
        f = onto_find(s, key)
        assert any(x["label"] == label and x["key"] == key for x in f["found"])
        nb = onto_neighbors(s, "Product", key=None)
        assert nb["ko"] and isinstance(nb["links"], list) and nb["links"]
        assert "없는 클래스" in onto_neighbors(s, "NoSuch")["error"]


def test_citation_tags_are_checked_against_real_sources():
    from nhdip.api.assist import Prepared, verify_citations

    prep = Prepared(q="q", history=[], metrics=[{"code": "share_now"}], analysis=[{"artifactTitle": "포용금융 충당금 분석", "title": "요약"}], evidence=[{"title": "가계부채 관리 방안"}],
                    facts="", ana_txt="", docs="", result={})
    ok = verify_citations("비중은 높다 [지표:share_now]. 근거 [문서:가계부채 관리 방안] · [분석:포용금융 충당금 분석]", prep, [{"tool": "data_aggregate"}])
    assert ok == {"checkCode": "citation_tags", "passed": True, "count": 3, "invalid": []}
    bad = verify_citations("[지표:made_up] [문서:없는 문서 제목] [도구:data_aggregate]", prep, [{"tool": "data_aggregate"}])
    assert bad["passed"] is False and bad["invalid"] == ["[지표:made_up]", "[문서:없는 문서 제목]"]


def test_attention_rule_reason_has_no_numbers():
    from nhdip.workflow.nodes import _rule_rank_reason

    r = _rule_rank_reason([{"label": "한도 근접", "points": 3}, {"label": "증가 기조", "points": 5}, {"label": "중요도", "points": 0}])
    assert r.startswith("증가 기조 · 한도 근접") and not any(ch.isdigit() for ch in r)
    assert not any(ch.isdigit() for ch in _rule_rank_reason([]))


# ═════════════════════════ 에이전트 그룹 · 에이전틱 파이프라인 (AGG-01~03) ═════════════════════════
def test_agent_groups_summary_bulk_apply_and_move(db):
    c = _admin()
    g = c.get("/admin/agent-groups").json()
    by = {x["code"]: x for x in g["groups"]}
    assert {"orchestration", "intake", "ontology", "knowledge", "narrative", "assistant"} <= set(by)
    assert {"onto_profiler", "onto_modeler", "onto_linker", "onto_resolver"} <= set(by["ontology"]["agents"])
    assert by["ontology"]["summary"]["agents"] == len(by["ontology"]["agents"]) and by["ontology"]["summary"]["rule"] >= 2
    assert c.post("/admin/agent-groups/intake/apply", json={"override": {"prompt": "x"}}).status_code == 422
    assert c.post("/admin/agent-groups/intake/apply", json={"override": {"temperature": 5}}).status_code == 422
    r = c.post("/admin/agent-groups/intake/apply", json={"override": {"temperature": 0.1, "max_tokens": 900}})
    assert r.status_code == 200, r.text
    assert set(r.json()["changed"]) == {"data_intake", "doc_intake"}
    agents = {a["code"]: a for a in c.get("/admin/agents").json()}
    assert agents["data_intake"]["override"]["temperature"] == 0.1 and agents["data_intake"]["groupCode"] == "intake"
    r2 = c.post("/admin/agent-groups/intake/apply", json={"override": {"temperature": None, "max_tokens": None}})
    assert set(r2.json()["changed"]) == {"data_intake", "doc_intake"}
    assert "temperature" not in {a["code"]: a for a in c.get("/admin/agents").json()}["data_intake"]["override"]
    assert c.patch("/admin/agents/doc_intake", json={"group_code": "nope"}).status_code == 422
    assert c.patch("/admin/agents/doc_intake", json={"group_code": "knowledge"}).json()["groupCode"] == "knowledge"
    assert c.patch("/admin/agents/doc_intake", json={"group_code": "intake"}).json()["groupCode"] == "intake"
    assert c.patch("/admin/agent-groups/intake", json={"name": " "}).status_code == 422


def test_agentic_overview_groups_pipelines_and_flows(db):
    c = _admin()
    r = c.get("/admin/agentic/overview")
    assert r.status_code == 200, r.text
    o = r.json()
    by = {g["code"]: g for g in o["groups"]}
    onto = by["ontology"]
    assert onto["ontology"]["datasets"] >= 1 and "pendingProposals" in onto["ontology"]
    wf = next(p for p in onto["pipelines"] if p["workflow"] == "wf_ontology_build")
    assert [n["impl"] for n in wf["nodes"]][:2] == ["profile_datasets", "design_object_types"] and any(n["inGroup"] for n in wf["nodes"])
    assert len(by["assistant"]["flow"]) == 5 and by["assistant"]["flow"][3]["agent"] == "query_assistant"
    nar = by["narrative"]
    assert nar["pipelines"] and all(any(n["inGroup"] for n in p["nodes"]) for p in nar["pipelines"])
    assert "intake" in by["intake"] and o["totals"]["agents"] >= 20 and isinstance(o["breaker"], list)
    assert _client().get("/admin/agentic/overview").status_code in (401, 403)


def test_kernel_records_library_input_errors_instead_of_failing_the_run(db):
    """팀이 올린 자료가 일부 구분(모형)에만 있을 때 — 빈 등급 배열이 scikit-learn ValueError 로 워크플로 전체를 멈추던 것. 그 지표만 실패로 기록한다."""
    from nhdip.calc import run_and_record

    with db() as s:
        run, res, disp = run_and_record(s, "AUROC_GRADED", {"defaults": [], "obs": []}, metric_code="auroc_test")
        assert res is None and disp is None and "등급 자료가 없습니다" in run.error
        run2, res2, _ = run_and_record(s, "AUROC_GRADED", {"defaults": [1, 2], "obs": [10]}, metric_code="auroc_test")
        assert res2 is None and "등급 수" in run2.error
        s.rollback()
