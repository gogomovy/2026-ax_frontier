"""업로드 자료 삭제 (Phase J · DEL-01~08 · Q143~Q147) — 권한 · 승격 · 연쇄 삭제(pgvector 청크 · Elasticsearch · Neo4j) · 파일 정리."""
from __future__ import annotations

import io
import json
import os

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

ADMIN = ("00000001", "Admin1234!")
DS = "TEST_DEL_DS"


def _client() -> TestClient:
    from nhdip.main import app

    return TestClient(app)


def _admin() -> TestClient:
    c = _client()
    assert c.post("/auth/login", json={"emp_no": ADMIN[0], "password": ADMIN[1]}).status_code == 200
    return c


def _ensure_dataset(c: TestClient) -> None:
    if c.patch(f"/admin/datasets/{DS}", json={"description": "삭제 시험"}).status_code == 200:
        return
    body = {
        "code": DS, "name": "삭제 시험 자료", "origin": "bank", "kind": "fact", "description": "삭제 시험",
        "columns": [{"name": "ym", "type": "str", "required": True}, {"name": "item", "type": "str", "required": True}, {"name": "amount", "type": "num"}],
        "key_columns": ["ym", "item"], "as_of_column": "ym", "quality_rules": [],
    }
    assert c.post("/admin/datasets", json=body).status_code == 201


def _upload(c: TestClient, name: str, rows: list[tuple[str, str, float]]) -> dict:
    csv = "ym,item,amount\n" + "".join(f"{a},{b},{v}\n" for a, b, v in rows)
    r = c.post(f"/admin/datasets/{DS}/upload", data={"origin": "bank", "data_origin": "simulated", "force": "true"}, files={"file": (name, io.BytesIO(csv.encode()), "text/csv")})
    assert r.status_code == 201, r.text
    return r.json()


def _versions(c: TestClient) -> dict[int, dict]:
    d = next(x for x in c.get("/admin/datasets").json() if x["code"] == DS)
    return {v["version"]: v for v in d["versions"]}


def _make_user(s, emp: str, *, role: str = "admin", data_admin: bool = False) -> None:
    from nhdip.models import AppUser
    from nhdip.security import hash_password

    u = s.get(AppUser, emp)
    if u is None:
        u = AppUser(emp_no=emp, name="시험", password_hash=hash_password("Test1234!"), org_code="T911", role=role, status="active", data_admin=data_admin)
        s.add(u)
    else:
        u.role, u.data_admin, u.status = role, data_admin, "active"
    s.commit()


def test_permissions_require_data_admin(db):
    c = _admin()
    _ensure_dataset(c)
    v = _upload(c, "perm_v1.csv", [("202607", "A", 1)])
    with db() as s:
        _make_user(s, "90000001", role="admin", data_admin=False)
        _make_user(s, "90000002", role="user", data_admin=True)  # 관리자가 아니면 표시가 있어도 효력 없음
        _make_user(s, "90000003", role="user", data_admin=False)
    me = _admin().get("/me").json()["user"]
    assert me["dataAdmin"] is True  # 부트스트랩 관리자 = 데이터 관리자
    plain = _client()
    assert plain.post("/auth/login", json={"emp_no": "90000001", "password": "Test1234!"}).status_code == 200
    assert plain.get("/me").json()["user"]["dataAdmin"] is False
    r = plain.post(f"/admin/datasets/{DS}/versions/{v['id']}/delete", json={"reason": "권한 시험"})
    assert r.status_code == 403 and "데이터 관리자" in r.json()["detail"]
    assert plain.get(f"/admin/datasets/{DS}/versions/{v['id']}/delete-preview").status_code == 403
    # 데이터 관리자가 아닌 관리자는 지정 · 해제를 바꾸지 못한다
    assert plain.patch("/admin/users/90000001", json={"data_admin": True}).status_code == 403
    user = _client()
    assert user.post("/auth/login", json={"emp_no": "90000002", "password": "Test1234!"}).status_code == 200
    assert user.post(f"/admin/datasets/{DS}/versions/{v['id']}/delete", json={"reason": "권한 시험"}).status_code == 403
    # 데이터 관리자는 관리자에게만 지정, 마지막 데이터 관리자는 해제 불가
    a = _admin()
    assert a.patch("/admin/users/90000003", json={"data_admin": True}).status_code == 422
    assert a.patch(f"/admin/users/{ADMIN[0]}", json={"data_admin": False}).status_code == 409
    assert a.patch("/admin/users/90000001", json={"data_admin": True}).status_code == 200
    assert a.patch("/admin/users/90000001", json={"data_admin": False}).status_code == 200


def test_delete_current_version_promotes_previous_and_keeps_tombstone(db):
    from nhdip.models import AuditLog, OutboxEvent, PurgeTask, source

    c = _admin()
    _ensure_dataset(c)
    v1 = _upload(c, "del_v1.csv", [("202608", "A", 10), ("202608", "B", 20)])
    v2 = _upload(c, "del_v2.csv", [("202608", "A", 11), ("202608", "B", 21), ("202608", "C", 31)])
    assert _versions(c)[v2["version"]]["isCurrent"]
    # 사유 없음 → 422
    assert c.post(f"/admin/datasets/{DS}/versions/{v2['id']}/delete", json={"reason": " "}).status_code == 422
    pv = c.get(f"/admin/datasets/{DS}/versions/{v2['id']}/delete-preview").json()
    assert pv["isCurrent"] and pv["promote"]["version"] == v1["version"] and pv["rows"] == 3 and pv["event"] == "dataset.deleted"
    r = c.post(f"/admin/datasets/{DS}/versions/{v2['id']}/delete", json={"reason": "잘못 올린 파일"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["wasCurrent"] and out["promoted"]["version"] == v1["version"] and out["removed"]["rows"] == 3 and out["event"]
    vs = _versions(c)
    assert vs[v1["version"]]["isCurrent"] and vs[v2["version"]]["status"] == "deleted" and not vs[v2["version"]]["isCurrent"]
    assert vs[v2["version"]]["deleteReason"] == "잘못 올린 파일" and vs[v2["version"]]["deletedBy"] == ADMIN[0]
    assert c.get(f"/admin/datasets/{DS}/versions/{v2['id']}/rows").json()["rows"] == []
    # 두 번 삭제 → 409, 되돌리기 대상도 아님
    assert c.post(f"/admin/datasets/{DS}/versions/{v2['id']}/delete", json={"reason": "다시"}).status_code == 409
    assert c.post(f"/admin/datasets/{DS}/versions/{v2['id']}/rollback").status_code == 422
    with db() as s:
        t = source("bank")
        assert s.execute(select(func.count()).select_from(t.row).where(t.row.version_id == v2["id"])).scalar() == 0
        ev = s.get(OutboxEvent, out["event"])
        assert ev.type == "dataset.deleted" and ev.payload["dataset"] == DS and ev.payload["promoted_version"] == v1["version"]
        task = s.execute(select(PurgeTask).where(PurgeTask.subject_ref == f"bank:{DS}:v{v2['version']}")).scalar_one()
        assert task.store == "neo4j" and task.payload["key"] == f"{DS}:v{v2['version']}"
        # 시험 환경의 Neo4j 는 꺼져 있다 — 응답 뒤 1회 시도 후 대기(다음 주기 재시도)
        assert task.status == "pending" and task.attempts >= 1 and task.last_error
        a = s.execute(select(AuditLog).where(AuditLog.action == "admin.dataset.version_delete", AuditLog.target_id == DS).order_by(AuditLog.id.desc())).scalars().first()
        assert a.detail["reason"] == "잘못 올린 파일" and a.detail["was_current"] is True
    # 다음 업로드는 지운 버전 번호를 다시 쓰지 않는다
    v3 = _upload(c, "del_v3.csv", [("202608", "A", 12)])
    assert v3["version"] == v2["version"] + 1
    # 현재 아닌 버전 삭제 — 이벤트 · 그래프 작업 없음
    out = c.post(f"/admin/datasets/{DS}/versions/{v1['id']}/delete", json={"reason": "이전 판 정리"}).json()
    assert out["wasCurrent"] is False and out["event"] is None and out["purgeTasks"] == []
    assert _versions(c)[v3["version"]]["isCurrent"]


def test_delete_last_current_version_empties_partition(db):
    from nhdip.data.datasets import current_rows
    from nhdip.models import Dataset

    c = _admin()
    _ensure_dataset(c)
    v = _upload(c, "only_v.csv", [("202512", "A", 5)])
    pv = c.get(f"/admin/datasets/{DS}/versions/{v['id']}/delete-preview").json()
    assert pv["isCurrent"] and pv["promote"] is None and pv["emptyAfter"] is True
    assert c.post(f"/admin/datasets/{DS}/versions/{v['id']}/delete", json={"reason": "기준월 정리"}).status_code == 200
    with db() as s:
        _, rows = current_rows(s, s.get(Dataset, DS))
        assert all(r["ym"] != "202512" for r in rows)


def _doc(c: TestClient, code: str, text: str) -> dict:
    r = c.post("/admin/documents/upload", data={"origin": "ext", "doc_class": "reference", "title": "삭제 시험 문서", "doc_code": code, "text": text})
    assert r.status_code == 201, r.text
    return r.json()


def test_delete_document_cascades_chunks_issues_and_queues_index_graph(db, monkeypatch):
    from nhdip.knowledge import elastic
    from nhdip.models import ExtractionIssue, OutboxEvent, PurgeTask, source

    monkeypatch.setattr(elastic, "configured", lambda: False)  # ES_URL 이 있는 환경에서 돌려도 '미구성' 경로를 시험
    c = _admin()
    d1 = _doc(c, "test-del-doc", "첫 판 본문 — 포용금융 공급 확대. " * 20)
    d2 = _doc(c, "test-del-doc", "둘째 판 본문 — 서민금융 신규 유치. " * 20)
    with db() as s:
        s.add(ExtractionIssue(origin="ext", document_id=d2["id"], kind="unresolved_entity", raw={}, reason="시험"))
        s.commit()
        t = source("ext")
        chunk_ids = list(s.execute(select(t.chunk.id).where(t.chunk.document_id == d2["id"])).scalars())
        assert chunk_ids
    pv = c.get(f"/admin/documents/ext/{d2['id']}/delete-preview").json()
    assert pv["isCurrent"] and pv["promote"]["version"] == d1["version"] and pv["chunks"] == len(chunk_ids)
    r = c.post(f"/admin/documents/ext/{d2['id']}/delete", json={"reason": "폐기된 판"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["wasCurrent"] and out["promoted"]["id"] == d1["id"] and out["removed"]["chunks"] == len(chunk_ids) and out["removed"]["issues"] == 1
    with db() as s:
        t = source("ext")
        doc = s.get(t.document, d2["id"])
        assert doc.status == "deleted" and doc.text == "" and doc.extraction == {} and not doc.is_current and doc.delete_reason == "폐기된 판"
        assert s.get(t.document, d1["id"]).is_current
        assert s.execute(select(func.count()).select_from(t.chunk).where(t.chunk.document_id == d2["id"])).scalar() == 0
        assert s.execute(select(func.count()).select_from(ExtractionIssue).where(ExtractionIssue.origin == "ext", ExtractionIssue.document_id == d2["id"])).scalar() == 0
        tasks = s.execute(select(PurgeTask).where(PurgeTask.id.in_(out["purgeTasks"]))).scalars().all()
        es = [x for x in tasks if x.store == "es"]
        # 직전 판이 현재가 되므로 그래프 문서 노드는 그대로(재투영이 갱신) — 색인 청크만 지운다
        assert len(tasks) == 1 and es and sorted(es[0].payload["ids"]) == sorted(f"ext:{i}" for i in chunk_ids)
        assert es[0].status == "skipped"  # 시험 환경은 ES_URL 없음 — 미구성이면 건너뜀
        ev = s.get(OutboxEvent, out["event"])
        assert ev.type == "document.deleted" and ev.payload["doc_class"] == "reference" and ev.payload["promoted_id"] == d1["id"]
    listed = {(d["origin"], d["id"]) for d in c.get("/admin/documents").json()}
    assert ("ext", d2["id"]) not in listed and ("ext", d1["id"]) in listed
    assert ("ext", d2["id"]) in {(d["origin"], d["id"]) for d in c.get("/admin/documents?include_deleted=true").json()}
    assert c.post(f"/admin/documents/ext/{d2['id']}/reextract").status_code == 409
    assert c.post(f"/admin/documents/ext/{d2['id']}/delete", json={"reason": "다시"}).status_code == 409
    # 남은 판까지 지우면 그래프 문서 노드 삭제 작업이 생긴다
    out = c.post(f"/admin/documents/ext/{d1['id']}/delete", json={"reason": "문서 폐기", "all_versions": True}).json()
    with db() as s:
        tasks = s.execute(select(PurgeTask).where(PurgeTask.id.in_(out["purgeTasks"]))).scalars().all()
        g = next(x for x in tasks if x.store == "neo4j")
        assert g.payload["key"] == "ext:test-del-doc" and f"ext.document({d1['id']})" in g.payload["src_refs"]
    # 같은 코드로 다시 올리면 버전 번호를 이어 쓰고, 그래프 삭제 작업은 건너뛴다
    d3 = _doc(c, "test-del-doc", "셋째 판 — 다시 등록. " * 20)
    assert d3["version"] == d2["version"] + 1


def test_purge_runner_es_and_neo4j(db, monkeypatch):
    from nhdip.data import deletion
    from nhdip.knowledge import elastic
    from nhdip.models import PurgeTask, source

    sent: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        sent.append(req.content.decode())
        lines = [json.loads(x) for x in req.content.decode().splitlines() if x]
        return httpx.Response(200, json={"items": [{"delete": {"_id": ln["delete"]["_id"], "status": 404 if i else 200}} for i, ln in enumerate(lines)]})

    cypher: list[tuple[str, dict]] = []

    def fake_run(q: str, **params):
        cypher.append((q, params))
        return [{"n": 1}]

    import nhdip.graph.neo4j_client as nc

    monkeypatch.setattr(elastic, "configured", lambda: True)
    elastic.reset_breaker()
    elastic.set_client(httpx.Client(base_url="http://es.test", transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(nc, "run", fake_run)
    try:
        with db() as s:
            s.query(PurgeTask).filter(PurgeTask.status == "pending").update({"status": "skipped"})  # 앞 시험이 남긴 작업 정리
            es = PurgeTask(store="es", subject_kind="document", subject_ref="ext:x", payload={"index": "doc", "ids": ["ext:999001", "ext:999002"]}, status="pending", attempts=0, result={})
            gv = PurgeTask(store="neo4j", subject_kind="dataset_version", subject_ref=f"bank:{DS}:v99", payload={"label": "DatasetVersion", "key": f"{DS}:v99"}, status="pending", attempts=0, result={})
            gd = PurgeTask(store="neo4j", subject_kind="document", subject_ref="ext:gone-doc", payload={"label": "Document", "key": "ext:gone-doc", "origin": "ext", "doc_code": "gone-doc", "src_refs": ["ext.document(999003)"]}, status="pending", attempts=0, result={})
            # 다시 올라와 현재 문서가 있는 코드 — 그래프 삭제 건너뜀
            t = source("ext")
            live = s.execute(select(t.document).where(t.document.is_current)).scalars().first()
            gl = PurgeTask(store="neo4j", subject_kind="document", subject_ref=f"ext:{live.doc_code}", payload={"label": "Document", "key": f"ext:{live.doc_code}", "origin": "ext", "doc_code": live.doc_code}, status="pending", attempts=0, result={})
            s.add_all([es, gv, gd, gl])
            s.commit()
            ids = [es.id, gv.id, gd.id, gl.id]
            stats = deletion.run_purge_tasks(s, ids=ids)
            assert stats == {"done": 3, "skipped": 1, "pending": 0}
            rows = {x.id: x for x in s.execute(select(PurgeTask).where(PurgeTask.id.in_(ids))).scalars()}
            assert rows[es.id].status == "done" and rows[es.id].result["deleted"] == 2
            assert rows[gl.id].status == "skipped" and "다시 올라와" in rows[gl.id].result["reason"]
        assert sent and '"_id": "ext:999001"' in sent[0] and '"delete"' in sent[0]
        qs = [q for q, _ in cypher]
        assert any("MATCH (n:DatasetVersion {key: $key})" in q and "DETACH DELETE" in q for q in qs)
        assert any("MATCH (n:Document {key: $key})" in q for q in qs)
        assert any("NOT EXISTS" in q and p.get("refs") == ["ext.document(999003)"] for q, p in cypher)
    finally:
        elastic.set_client(None)
        elastic.reset_breaker()


def test_purge_runner_keeps_pending_when_store_down(db, monkeypatch):
    from nhdip.data import deletion
    from nhdip.graph.neo4j_client import GraphUnavailable
    from nhdip.models import PurgeTask

    import nhdip.graph.neo4j_client as nc

    def down(q: str, **params):
        raise GraphUnavailable("connection refused")

    monkeypatch.setattr(nc, "run", down)
    with db() as s:
        t = PurgeTask(store="neo4j", subject_kind="dataset_version", subject_ref="bank:X:v1", payload={"label": "DatasetVersion", "key": "X:v1"}, status="pending", attempts=0, result={})
        s.add(t)
        s.commit()
        assert deletion.run_purge_tasks(s, ids=[t.id]) == {"done": 0, "skipped": 0, "pending": 1}
        s.refresh(t)
        assert t.status == "pending" and t.attempts == 1 and "connection refused" in t.last_error
    c = _admin()
    st = c.get("/admin/purge-tasks").json()
    assert st["counts"].get("pending", 0) >= 1 and any(x["id"] == t.id for x in st["tasks"])


def test_remove_files_only_unreferenced(db, tmp_path):
    from nhdip.config import get_settings
    from nhdip.data import deletion

    root = get_settings().filestore_dir
    os.makedirs(os.path.join(root, "bank", DS), exist_ok=True)
    lone = os.path.join(root, "bank", DS, "lone_test.csv")
    with open(lone, "w") as fh:
        fh.write("x")
    outside = tmp_path / "outside.csv"
    outside.write_text("x")
    with db() as s:
        out = deletion.remove_files(s, [lone, str(outside)])
    assert out["removed"] == 1 and out["kept"] == 1 and not os.path.exists(lone) and outside.exists()


def test_clean_reason():
    from nhdip.data.deletion import DeleteError, clean_reason

    assert clean_reason("  잘못   올림 ") == "잘못 올림"
    assert len(clean_reason("가" * 900)) == 500
    with pytest.raises(DeleteError):
        clean_reason("가")
