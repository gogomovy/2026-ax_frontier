"""부서 데이터 책임자의 자료 삭제 (Phase J 후속 · DEL-09~12 · Q157~Q159) — 부서 범위 소유 판정 · 연쇄 삭제 · 감사 · 삭제 자료가 검색 색인에 새지 않는지."""
from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

ADMIN = ("00000001", "Admin1234!")
DS = "TEST_STW_DS"
PW = "abcd1234"
# 신용리스크관리부(T211 · 부 D200) 사용자·책임자, 종합기획부(T111) 책임자
REQ, STW, OTHER, PLAIN, LATE = "20259141", "20259142", "20259143", "20259144", "20259145"


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
    c.post("/auth/signup", json={"emp_no": emp, "name": f"스튜어드{emp[-2:]}", "password": PW, "org_code": org})  # 이미 있으면 무시
    admin.post(f"/admin/users/{emp}/approve")
    _login(c, emp, PW)
    if steward:
        assert admin.patch(f"/admin/users/{emp}", json={"data_steward": True}).status_code == 200
    return c


@pytest.fixture(scope="module")
def world(db):
    admin = _client()
    _login(admin, *ADMIN)
    body = {
        "code": DS, "name": "책임자 삭제 시험 자료", "origin": "bank", "kind": "fact", "description": "책임자 삭제 시험",
        "columns": [{"name": "ym", "type": "str", "required": True}, {"name": "item", "type": "str", "required": True}, {"name": "amount", "type": "num"}],
        "key_columns": ["ym", "item"], "as_of_column": "ym", "quality_rules": [],
    }
    if admin.patch(f"/admin/datasets/{DS}", json={"description": "책임자 삭제 시험"}).status_code != 200:
        assert admin.post("/admin/datasets", json=body).status_code == 201
    return {
        "admin": admin,
        "req": _user(admin, REQ, "T211"),
        "stw": _user(admin, STW, "T211", steward=True),
        "other": _user(admin, OTHER, "T111", steward=True),
        "plain": _user(admin, PLAIN, "T211"),
    }


def _csv(rows: list[tuple[str, str, float]]) -> bytes:
    return ("ym,item,amount\n" + "".join(f"{a},{b},{v}\n" for a, b, v in rows)).encode()


def _request_dataset(c: TestClient, name: str, rows: list[tuple[str, str, float]]) -> int:
    r = c.post("/db/uploads/dataset", data={"target": DS, "data_origin": "simulated"}, files={"file": (name, io.BytesIO(_csv(rows)), "text/csv")})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _approve(c: TestClient, rid: int) -> dict:
    r = c.post(f"/db/uploads/{rid}/approve", json={"note": "시험 승인"})
    assert r.status_code == 200, r.text
    return r.json()


def _versions(admin: TestClient) -> dict[int, dict]:
    d = next(x for x in admin.get("/admin/datasets").json() if x["code"] == DS)
    return {v["version"]: v for v in d["versions"]}


def _item(c: TestClient, rid: int, deleted: bool = False) -> dict | None:
    items = c.get(f"/db/steward/items?deleted={'true' if deleted else 'false'}").json()["items"]
    return next((i for i in items if i["requestId"] == rid), None)


def test_permissions_and_department_boundary(db, world):
    """책임자만 · 자기 부서가 올린 자료만 — 다른 부서는 없는 것처럼 404, 책임자가 아니면 403, 관리자 직접 업로드 자료는 목록에 없다."""
    stw, other, plain, admin, req = world["stw"], world["other"], world["plain"], world["admin"], world["req"]
    rid = _request_dataset(req, "stw_perm.csv", [("202601", "A", 1), ("202601", "B", 2)])
    # 승인 전에는 '반영된 자료'가 아니다
    assert _item(stw, rid) is None
    assert stw.get(f"/db/steward/items/{rid}/delete-preview").status_code == 404
    _approve(stw, rid)
    mine = _item(stw, rid)
    assert mine and mine["kind"] == "dataset" and mine["target"] == DS and mine["requestedBy"] == REQ and mine["label"] == "책임자 삭제 시험 자료"
    # 책임자가 아니면 모든 엔드포인트 403
    for method, url in (("get", "/db/steward/items"), ("get", f"/db/steward/items/{rid}/delete-preview"), ("get", "/db/steward/purge-status"), ("post", "/db/steward/purge-run")):
        assert getattr(plain, method)(url).status_code == 403, url
    assert plain.post(f"/db/steward/items/{rid}/delete", json={"reason": "권한 시험"}).status_code == 403
    # 다른 부서 책임자 — 목록에 없고 미리보기 · 삭제 모두 404 (자료는 그대로)
    assert _item(other, rid) is None
    assert other.get(f"/db/steward/items/{rid}/delete-preview").status_code == 404
    assert other.post(f"/db/steward/items/{rid}/delete", json={"reason": "남의 부서 자료"}).status_code == 404
    assert any(v["status"] != "deleted" for v in _versions(admin).values())
    # 관리자가 직접 올린 버전은 요청이 없어 책임자 목록에 없다
    csv = _csv([("202601", "Z", 9)])
    direct = admin.post(f"/admin/datasets/{DS}/upload", data={"origin": "bank", "data_origin": "simulated", "force": "true"}, files={"file": ("direct.csv", io.BytesIO(csv), "text/csv")})
    assert direct.status_code == 201, direct.text
    assert all(i["subjectId"] != direct.json()["id"] for i in stw.get("/db/steward/items").json()["items"] if i["kind"] == "dataset")
    # 없는 요청 번호
    assert stw.get("/db/steward/items/99999999/delete-preview").status_code == 404


def test_steward_deletes_current_version_cascade_and_audit(db, world):
    from nhdip.models import AuditLog, OutboxEvent, PurgeTask, UploadRequest, source

    stw, admin, req = world["stw"], world["admin"], world["req"]
    r1 = _request_dataset(req, "stw_del_v1.csv", [("202602", "A", 10), ("202602", "B", 20)])
    r2 = _request_dataset(req, "stw_del_v2.csv", [("202602", "A", 11), ("202602", "B", 21), ("202602", "C", 31)])
    v1, v2 = _approve(stw, r1)["result"], _approve(stw, r2)["result"]
    assert _versions(admin)[v2["version"]]["isCurrent"]
    pv = stw.get(f"/db/steward/items/{r2}/delete-preview").json()
    assert pv["isCurrent"] and pv["promote"]["version"] == v1["version"] and pv["rows"] == 3 and pv["event"] == "dataset.deleted" and pv["requestId"] == r2
    assert isinstance(pv["workflows"], list)
    # 사유 필수
    assert stw.post(f"/db/steward/items/{r2}/delete", json={"reason": " "}).status_code == 422
    r = stw.post(f"/db/steward/items/{r2}/delete", json={"reason": "잘못 올린 파일"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["wasCurrent"] and out["promoted"]["version"] == v1["version"] and out["removed"]["rows"] == 3 and out["event"] and out["purgeTasks"]
    vs = _versions(admin)
    assert vs[v1["version"]]["isCurrent"] and vs[v2["version"]]["status"] == "deleted" and vs[v2["version"]]["deletedBy"] == STW
    assert admin.get(f"/admin/datasets/{DS}/versions/{v2['versionId']}/rows").json()["rows"] == []
    # 두 번 지우기 · 이미 지운 요청 미리보기
    assert stw.post(f"/db/steward/items/{r2}/delete", json={"reason": "다시"}).status_code == 409
    assert stw.get(f"/db/steward/items/{r2}/delete-preview").status_code == 409
    # 목록: 지울 수 있는 것에서 빠지고 지운 기록에 사유 · 지운 사람이 남는다
    assert _item(stw, r2) is None and _item(stw, r1) is not None
    gone = _item(stw, r2, deleted=True)
    assert gone and gone["deleted"]["reason"] == "잘못 올린 파일" and gone["deleted"]["by"] == STW and gone["deleted"]["byName"]
    with db() as s:
        t = source("bank")
        assert s.execute(select(func.count()).select_from(t.row).where(t.row.version_id == v2["versionId"])).scalar() == 0
        assert s.get(OutboxEvent, out["event"]).type == "dataset.deleted"
        tasks = {x.store: x for x in s.execute(select(PurgeTask).where(PurgeTask.id.in_(out["purgeTasks"]))).scalars()}
        assert set(tasks) == {"neo4j", "pg"}  # 그래프 노드 삭제 + 지난 산출물 세대 정리(삭제 뒤 재계산이 끝나면)
        task = tasks["neo4j"]
        assert task.created_by == STW and tasks["pg"].payload["dataset"] == DS  # 시험 환경의 Neo4j 는 꺼져 있다 — 대기 후 재시도
        a = s.execute(select(AuditLog).where(AuditLog.action == "admin.dataset.version_delete", AuditLog.target_id == DS).order_by(AuditLog.id.desc())).scalars().first()
        assert a.actor == STW and a.detail["via"] == "steward" and a.detail["reason"] == "잘못 올린 파일" and a.detail["was_current"] is True
        # 지운 자료의 내용 미리보기(표 앞부분 행)는 요청 기록에서도 지운다 — 건수 · 품질 요약은 남는다
        pr = s.get(UploadRequest, r2)
        assert "sample" not in pr.preview and pr.preview.get("rows") == 3 and pr.result["deleted"]["by"] == STW
    # 내가 낸 삭제 작업 반영 상태 · 다시 실행
    st = stw.get("/db/steward/purge-status").json()
    assert any(t["id"] in out["purgeTasks"] for t in st["tasks"]) and all(t["createdBy"] == STW for t in st["tasks"])
    assert set(stw.post("/db/steward/purge-run").json()) == {"done", "skipped", "pending"}
    # 다른 부서 책임자는 이 부서의 삭제 작업을 보지 못한다
    assert all(t["createdBy"] != STW for t in world["other"].get("/db/steward/purge-status").json()["tasks"])


def test_steward_deletes_document_all_versions_requires_ownership(db, world):
    """문서 — 한 버전만은 자기 부서 것이면 가능, 전체 버전 삭제는 다른 부서 · 관리자가 올린 버전이 섞이면 거절. 청크(pgvector)는 같은 트랜잭션에서 지운다."""
    from nhdip.models import source

    stw, admin, req = world["stw"], world["admin"], world["req"]
    d = req.post("/db/uploads/document", data={"doc_class": "reference", "title": "책임자 삭제 시험 문서", "text": "신용리스크 부서가 올린 첫 판 본문입니다. 포용금융 충당금 설명. " * 12})
    assert d.status_code == 201, d.text
    rid = d.json()["id"]
    res = _approve(stw, rid)["result"]
    origin, code, first = res["origin"], res["docCode"], res["documentId"]
    # 관리자가 같은 문서 코드로 둘째 판을 직접 올림 — 요청이 없는 판
    up = admin.post("/admin/documents/upload", data={"origin": origin, "doc_class": "reference", "title": "책임자 삭제 시험 문서", "doc_code": code, "text": "관리자가 직접 올린 둘째 판 본문입니다. 서민금융 신규 유치. " * 12})
    assert up.status_code == 201, up.text
    second = up.json()["id"]
    with db() as s:
        t = source(origin)
        n1 = s.execute(select(func.count()).select_from(t.chunk).where(t.chunk.document_id == first)).scalar()
        n2 = s.execute(select(func.count()).select_from(t.chunk).where(t.chunk.document_id == second)).scalar()
        assert n1 and n2
    # 전체 버전 — 관리자가 올린 판이 섞여 있어 거절(미리보기도 같은 판단), 아무것도 바뀌지 않는다
    assert stw.get(f"/db/steward/items/{rid}/delete-preview?all_versions=true").status_code == 403
    r = stw.post(f"/db/steward/items/{rid}/delete", json={"reason": "문서 전체 폐기", "all_versions": True})
    assert r.status_code == 403 and "데이터 관리자" in r.json()["detail"]
    with db() as s:
        t = source(origin)
        assert s.get(t.document, first).status != "deleted" and s.get(t.document, second).status != "deleted"
    # 자기 부서가 올린 첫 판만 — 현재 판이 아니므로 이벤트 · 그래프 작업 없음
    pv = stw.get(f"/db/steward/items/{rid}/delete-preview").json()
    assert pv["isCurrent"] is False and pv["chunks"] == n1 and pv["workflows"] == []
    out = stw.post(f"/db/steward/items/{rid}/delete", json={"reason": "첫 판 폐기"})
    assert out.status_code == 200, out.text
    body = out.json()
    assert body["wasCurrent"] is False and body["event"] is None and body["purgeTasks"] == [] and body["removed"]["chunks"] == n1
    with db() as s:
        t = source(origin)
        doc = s.get(t.document, first)
        assert doc.status == "deleted" and doc.text == "" and doc.extraction == {} and doc.deleted_by == STW and doc.delete_reason == "첫 판 폐기"
        assert s.execute(select(func.count()).select_from(t.chunk).where(t.chunk.document_id == first)).scalar() == 0  # pgvector 청크 삭제
        assert s.execute(select(func.count()).select_from(t.chunk).where(t.chunk.document_id == second)).scalar() == n2  # 관리자 판은 그대로
        assert s.get(t.document, second).is_current
    # 요청 기록의 문서 앞부분(excerpt)도 지운다
    from nhdip.models import UploadRequest

    with db() as s:
        assert "excerpt" not in s.get(UploadRequest, rid).preview


def test_steward_designation_removed_blocks_delete(db, world):
    """책임자 지정을 해제하면 바로 삭제 권한이 사라진다."""
    admin = world["admin"]
    late = _user(admin, LATE, "T211", steward=True)
    rid = _request_dataset(world["req"], "stw_late.csv", [("202603", "A", 1)])
    _approve(world["stw"], rid)
    assert late.get(f"/db/steward/items/{rid}/delete-preview").status_code == 200
    assert admin.patch(f"/admin/users/{LATE}", json={"data_steward": False}).status_code == 200
    assert late.get(f"/db/steward/items/{rid}/delete-preview").status_code == 403
    assert late.post(f"/db/steward/items/{rid}/delete", json={"reason": "해제 후"}).status_code == 403


def test_stale_figure_not_served_to_search_index():
    """삭제로 다시 계산하지 못한(stale) 수치는 검색 · 질문하기 색인 문장에 값이 실리지 않는다 (DEL-11)."""
    from nhdip.knowledge.render import fig_line, fig_text, resolve_text

    f = {"id": "dr", "label": "부도율", "unit": "PCT", "value": 1.23, "decimals": 2}
    assert "1.23" in fig_text(f)
    old = {**f, "stale": True, "staleReason": "확정된 버전 없음: TEST_STW_DS"}
    assert fig_text(old) == "미산출(갱신 실패)" and "1.23" not in fig_line(old)
    assert "1.23" not in resolve_text("부도율은 [[fig:dr]] 입니다", {"dr": old})
    # 값이 다시 계산되어 stale 이 풀리면 값이 다시 색인된다
    assert "1.23" in resolve_text("부도율은 [[fig:dr]] 입니다", {"dr": f})
