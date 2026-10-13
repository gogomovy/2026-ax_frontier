"""Phase G — 온톨로지 구성 지도 (요구사항 §23 OV-01~06 · 설계 §23): 수집 = 투영 입력 · 군집 · 배치 결정성 · 상한 · API."""
from __future__ import annotations

import numpy as np
from fastapi.testclient import TestClient


# ── 순수 함수 ────────────────────────────────────────────────
def test_louvain_splits_two_cliques_and_is_deterministic():
    from nhdip.graph.ontology_map import louvain

    a = [(i, j) for i in range(5) for j in range(i + 1, 5)]
    b = [(i, j) for i in range(5, 10) for j in range(i + 1, 10)]
    edges = a + b + [(4, 5)]
    c = louvain(10, edges)
    assert len(set(c[:5])) == 1 and len(set(c[5:])) == 1 and c[0] != c[9]
    assert louvain(10, edges) == c  # 난수 없음 — 같은 입력이면 같은 군집
    assert louvain(3, []) == [0, 1, 2]  # 간선 없으면 각자
    # 번호는 큰 군집부터
    big = [(i, j) for i in range(6) for j in range(i + 1, 6)]
    small = [(6, 7), (7, 8), (6, 8)]
    cc = louvain(9, big + small + [(5, 6)])
    assert cc[0] == 0 and cc[8] == 1


def test_force_layout_is_deterministic_and_normalized():
    from nhdip.graph.ontology_map import force_layout, layout

    edges = [(0, 1, 1.0), (1, 2, 1.0), (2, 0, 1.0), (3, 4, 1.0)]
    p = force_layout(5, edges, 3, 60)
    assert p.shape == (5, 3) and np.abs(p).max() <= 1.0 + 1e-9
    assert np.allclose(force_layout(5, edges, 3, 60), p)
    # 연결된 점끼리가 연결 안 된 점보다 가깝다
    d01 = np.linalg.norm(p[0] - p[1])
    d03 = np.linalg.norm(p[0] - p[3])
    assert d01 < d03
    pos, centers = layout(5, [0, 0, 0, 1, 1], [(0, 1), (1, 2), (2, 0), (3, 4)], 2)
    assert pos.shape == (5, 2) and set(centers) == {0, 1} and np.abs(pos).max() <= 1.0 + 1e-9


def test_select_nodes_keeps_class_quota_then_degree():
    from nhdip.graph.ontology_map import select_nodes

    ids = [f"A:{i}" for i in range(100)] + [f"B:{i}" for i in range(6)]
    cls = {i: i.split(":")[0] for i in ids}
    deg = {i: (200 - n) for n, i in enumerate(ids)}  # A 가 연결 수가 모두 높다
    keep = select_nodes(ids, cls, deg, 20)
    assert len(keep) == 20 and sum(1 for k in keep if k.startswith("B:")) >= 5  # 연결이 적은 클래스도 최소 몫
    assert select_nodes(ids[:10], cls, deg, 20) == ids[:10]


# ── 원장 → 지도 (DB) ─────────────────────────────────────────
def test_collect_graph_is_what_projection_flushes(db, monkeypatch):
    """지도와 Neo4j 투영은 같은 수집 코드 — 투영이 보내려는 노드 · 관계 = 수집 결과 (Q128)."""
    from nhdip.graph import projection

    sent = {}

    def fake_flush(self):
        sent["nodes"] = {(lab[0], k) for lab, items in self.nodes.items() for k in items}
        sent["rels"] = sum(len(v) for v in self.rels.values())
        return {"nodes": len(sent["nodes"]), "relationships": sent["rels"]}

    monkeypatch.setattr(projection.Batch, "flush", fake_flush)
    monkeypatch.setattr(projection, "ensure_constraints", lambda labels: None)
    with db() as s:
        _with_extraction(s)
        out = projection.project_all(s)
        b = projection.collect_graph(s)
        s.rollback()
    got = {(lab[0], k) for lab, items in b.nodes.items() for k in items}
    assert out["nodes"] == len(got) > 50 and got == sent["nodes"] and sum(len(v) for v in b.rels.values()) == sent["rels"]
    assert out["documents"] > 0 and "schema_version" in out
    # 문서 추출 개체에는 화면용 근거(Neo4j 로는 보내지 않음 — 노드 속성에 근거 문장이 없다)
    meta = b.meta.get(("PolicyTheme", "지도시험주제"))
    assert meta and meta["evidence"] == "서민 포용금융 공급을 늘린다" and meta["page"] == 3
    assert all("evidence" not in p for items in b.nodes.values() for p in items.values())


def _with_extraction(s):
    """시험 문서 하나에 규칙 추출 결과(개체 · 근거)를 넣는다 — 호출한 시험이 되돌린다."""
    from sqlalchemy import select

    from nhdip.models import source

    t = source("ext")
    d = s.execute(select(t.document).where(t.document.is_current).order_by(t.document.id)).scalars().first()
    assert d is not None
    d.extraction = {
        "by": "rule",
        "entities": [{"label": "PolicyTheme", "key": "지도시험주제", "name": "지도 시험 주제", "evidence_span": "서민 포용금융 공급을 늘린다", "page": 3}],
        "relations": [{"type": "MENTIONS", "from": "$doc", "from_label": "Document", "to": "지도시험주제", "to_label": "PolicyTheme"}],
    }
    s.flush()
    return d


def test_ontology_map_from_ledger_without_neo4j(db):
    from nhdip.graph.ontology_map import ontology_map

    with db() as s:
        _with_extraction(s)
        m = ontology_map(s, refresh=True)
        again = ontology_map(s)
        small = ontology_map(s, limit=50, refresh=True)
        only = ontology_map(s, classes=["Product", "ProductGroup"], refresh=True)
        s.rollback()
    n = len(m["nodes"])
    assert n > 50 and m["total"]["nodes"] == n and not m["truncated"]
    assert all(0 <= a < n and 0 <= b < n and 0 <= t < len(m["relTypes"]) for a, b, t in m["links"])
    assert sum(c["size"] for c in m["clusters"]) == n and {x["c"] for x in m["nodes"]} == {c["id"] for c in m["clusters"]}
    assert all(abs(v) <= 1.0001 for x in m["nodes"] for v in [*x["p3"], *x["p2"]])
    assert again["cached"] is True and [x["p3"] for x in again["nodes"]] == [x["p3"] for x in m["nodes"]]  # 같은 원장 → 보관본
    assert all(c["label"] for c in m["clusters"]) and any(c["count"] > 0 for c in m["classes"])
    assert {r["type"] for r in m["relations"]} == set(m["relTypes"]) and m["schema"]
    pol = next(x for x in m["nodes"] if x["id"] == "PolicyTheme:지도시험주제")
    assert pol["evidence"] == "서민 포용금융 공급을 늘린다" and pol["evidencePage"] == 3 and pol["kind"] == "document"  # 문서 추출 개체의 근거 문장 · 면
    assert len(small["nodes"]) == 50 and small["truncated"] and small["total"]["nodes"] == n
    assert only["nodes"] and {x["cls"] for x in only["nodes"]} <= {"Product", "ProductGroup"}


def test_ontology_map_api_admin_only_and_validates(db):
    from nhdip.main import app

    admin = TestClient(app)
    assert admin.post("/auth/login", json={"emp_no": "00000001", "password": "Admin1234!"}).status_code == 200
    r = admin.get("/admin/ontology/map")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["nodes"] and body["neo4j"]["ok"] is False  # 시험은 Neo4j 없음 — 그래도 원장 기준으로 보인다(OV-01)
    assert admin.get("/admin/ontology/map", params={"classes": "Product;DROP"}).status_code == 422
    assert admin.get("/admin/ontology/map", params={"limit": 5}).status_code == 422
    assert TestClient(app).get("/admin/ontology/map").status_code == 401
