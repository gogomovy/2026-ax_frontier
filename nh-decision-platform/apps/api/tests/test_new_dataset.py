"""정의 없는 새 종류 자료 (Phase J 후속 · DEF-01~05 · Q160~Q163) — 추론 → 확인 · 수정 → 제안 → 승인 → 데이터셋 생성 + 첫 버전, 그리고 정의가 비었거나 열이 모자란 경우."""
from __future__ import annotations

import io
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

ADMIN = ("00000001", "Admin1234!")
PW = "abcd1234"
REQ, STW = "20259151", "20259152"  # 신용리스크관리부(T211) 사용자 · 책임자


def _client() -> TestClient:
    from nhdip.main import app

    return TestClient(app)


def _login(c: TestClient, emp: str, pw: str) -> None:
    from nhdip import ratelimit

    ratelimit.reset()
    assert c.post("/auth/login", json={"emp_no": emp, "password": pw}).status_code == 200


def _user(admin: TestClient, emp: str, org: str, steward: bool = False) -> TestClient:
    c = _client()
    c.post("/auth/signup", json={"emp_no": emp, "name": f"신규자료{emp[-2:]}", "password": PW, "org_code": org})
    admin.post(f"/admin/users/{emp}/approve")
    _login(c, emp, PW)
    if steward:
        assert admin.patch(f"/admin/users/{emp}", json={"data_steward": True}).status_code == 200
    return c


@pytest.fixture(scope="module")
def world(db):
    admin = _client()
    _login(admin, *ADMIN)
    return {"admin": admin, "req": _user(admin, REQ, "T211"), "stw": _user(admin, STW, "T211", steward=True)}


def _csv(header: str, rows: list[str]) -> bytes:
    return (header + "\n" + "\n".join(rows) + "\n").encode("utf-8")


PRODUCTS = [("A01", "새희망홀씨"), ("B02", "햇살론"), ("C03", "사잇돌")]
MONTHLY = _csv("기준월,상품코드,상품명,잔액", [f"2026{m:02d},{p},{n},{1000 * i + m}" for m in (6, 7) for i, (p, n) in enumerate(PRODUCTS, start=1)])


def _files(name: str, data: bytes) -> dict:
    return {"file": (name, io.BytesIO(data), "text/csv")}


def _versions(admin: TestClient, code: str) -> list[dict]:
    return next(d for d in admin.get("/admin/datasets").json() if d["code"] == code)["versions"]


# ═════════════════════════ 업무 사용자 제안 흐름 ═════════════════════════
def test_propose_new_dataset_from_file_then_steward_approves(db, world):
    """정의 없는 새 파일 → 추론 초안 → (사용자가 고친) 정의로 제안 → 책임자 승인 → 데이터셋 생성 + 첫 버전 → 다음 달 파일은 같은 데이터셋으로."""
    from nhdip.models import AuditLog, Dataset, UploadRequest, source

    req, stw, admin = world["req"], world["stw"], world["admin"]
    opts = req.get("/db/uploadable").json()
    assert opts["canPropose"] is True

    inf = req.post("/db/uploads/dataset-infer", files=_files("신규상품잔액_202607.csv", MONTHLY), data={"origin": "bank"})
    assert inf.status_code == 200, inf.text
    d = inf.json()
    labels = {c["label"]: c for c in d["columns"]}
    assert labels["잔액"]["type"] == "int" and labels["기준월"]["type"] == "str"
    assert d["as_of_column"] == labels["기준월"]["name"] and d["key_columns"] == [labels["기준월"]["name"], labels["상품코드"]["name"]]
    code = d["code"]
    assert code and not req.get("/db/uploadable").json()["datasets"] == [] and all(x["code"] != code for x in opts["datasets"])

    # 사용자가 이름을 고친다 — 정의는 사람이 확인 · 수정한 것이 기준
    d["name"] = "신규 상품 잔액(시험)"
    r = req.post("/db/uploads/dataset-proposal", data={"definition": json.dumps(d), "data_origin": "simulated"}, files=_files("신규상품잔액_202607.csv", MONTHLY))
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    assert r.json()["meta"]["proposal"]["code"] == code and r.json()["status"] == "pending"
    # 같은 코드의 두 번째 제안 · 이미 있는 코드는 거절
    assert req.post("/db/uploads/dataset-proposal", data={"definition": json.dumps(d)}, files=_files("x.csv", MONTHLY)).status_code == 409
    with db() as s:
        assert s.get(Dataset, code) is None  # 승인 전에는 데이터셋이 만들어지지 않는다

    ok = stw.post(f"/db/uploads/{rid}/approve", json={"note": "새 자료 승인"})
    assert ok.status_code == 200, ok.text
    res = ok.json()["result"]
    assert res["createdDataset"] == code and res["status"] == "committed" and res["rows"] == 6 and res["isCurrent"] is True
    with db() as s:
        ds = s.get(Dataset, code)
        assert ds and ds.name == "신규 상품 잔액(시험)" and ds.origin == "bank" and len(ds.columns) == 4 and ds.key_columns == d["key_columns"]
        t = source("bank")
        assert s.execute(select(func.count()).select_from(t.row).where(t.row.dataset_code == code)).scalar() == 6
        a = s.execute(select(AuditLog).where(AuditLog.action == "db.dataset.create_by_request", AuditLog.target_id == code)).scalar_one()
        assert a.actor == STW and a.detail["request"] == rid and a.detail["via"] == "steward"
        assert s.get(UploadRequest, rid).result["via"] == "steward"
    # 이제 목록에 있고, 다음 달 파일은 새 정의 없이 같은 데이터셋으로 올라간다
    assert any(x["code"] == code for x in req.get("/db/uploadable").json()["datasets"])
    nxt = _csv("기준월,상품코드,상품명,잔액", [f"202608,{p},{n},{500 + i}" for i, (p, n) in enumerate(PRODUCTS)])
    r2 = req.post("/db/uploads/dataset", data={"target": code, "data_origin": "simulated"}, files=_files("신규상품잔액_202608.csv", nxt))
    assert r2.status_code == 201, r2.text
    # 올라간 첫 버전은 책임자가 자기 부서 자료로 삭제할 수 있다(앞 단계의 삭제 권한과 같은 소유 판정)
    assert stw.get(f"/db/steward/items/{rid}/delete-preview").status_code == 200
    assert next(v for v in _versions(admin, code) if v["id"] == res["versionId"])["status"] == "committed"


def test_proposal_is_checked_like_any_upload(db, world):
    """제안도 같은 검사를 거친다 — 개인정보 형식 값 · 정의가 파일을 못 읽는 경우 · 잘못된 정의 · 제안 차단 설정."""
    from nhdip.models import Dataset, Setting

    req = world["req"]
    pii = _csv("이름,번호", ["가,900101-1234567", "나,900101-2234567"])
    d = req.post("/db/uploads/dataset-infer", files=_files("개인정보시험.csv", pii), data={}).json()
    r = req.post("/db/uploads/dataset-proposal", data={"definition": json.dumps(d)}, files=_files("개인정보시험.csv", pii))
    assert r.status_code == 422 and "pii" in r.json()["detail"]

    d = req.post("/db/uploads/dataset-infer", files=_files("정상표.csv", MONTHLY), data={}).json()
    other = _csv("전혀,다른,표", ["1,2,3", "4,5,6"])
    r = req.post("/db/uploads/dataset-proposal", data={"definition": json.dumps(d)}, files=_files("정상표.csv", other))
    assert r.status_code == 422 and "필수 컬럼 없음" in r.json()["detail"]  # 정의의 키 열이 파일에 없다

    bad = {**d, "columns": [], "code": "ok_code"}
    assert req.post("/db/uploads/dataset-proposal", data={"definition": json.dumps(bad)}, files=_files("정상표.csv", MONTHLY)).status_code == 422
    bad2 = {**d, "key_columns": ["없는열"]}
    assert req.post("/db/uploads/dataset-proposal", data={"definition": json.dumps(bad2)}, files=_files("정상표.csv", MONTHLY)).status_code == 422
    assert req.post("/db/uploads/dataset-proposal", data={"definition": "[1]"}, files=_files("정상표.csv", MONTHLY)).status_code == 422

    with db() as s:
        row = s.get(Setting, "upload.user_targets")
        before = None if row is None else dict(row.value)
        if row is None:
            s.add(Setting(key="upload.user_targets", value={"datasets": "*", "doc_classes": "*", "new_datasets": False}, description="시험"))
        else:
            row.value = {**row.value, "new_datasets": False}
        s.commit()
    try:
        assert req.get("/db/uploadable").json()["canPropose"] is False
        assert req.post("/db/uploads/dataset-infer", files=_files("정상표.csv", MONTHLY), data={}).status_code == 403
        assert req.post("/db/uploads/dataset-proposal", data={"definition": json.dumps(d)}, files=_files("정상표.csv", MONTHLY)).status_code == 403
    finally:
        with db() as s:
            row = s.get(Setting, "upload.user_targets")
            if before is None:
                s.delete(row)
            else:
                row.value = before
            s.commit()
    with db() as s:
        assert s.get(Dataset, d["code"]) is None


# ═════════════════════════ 관리자 · 정의 보강 ═════════════════════════
def test_admin_infer_create_upload_and_find_new_columns(db, world):
    """관리자: 추론 → 정의 저장 → 업로드. 이후 새 열이 든 파일은 '저장하지 않은 열' 안내가 나오고, 새 열 찾기 → 정의 갱신으로 이어서 저장된다."""
    admin = world["admin"]
    inf = admin.post("/admin/datasets/infer", files=_files("관리자신규_202606.csv", MONTHLY), data={"origin": "bank", "code": "TEST_NEWDS_ADMIN", "name": "관리자 신규 시험"})
    assert inf.status_code == 200, inf.text
    d = inf.json()
    assert d["code"] == "TEST_NEWDS_ADMIN" and d["exists"] is False and d["rows"] == 6
    created = admin.post("/admin/datasets", json={k: d[k] for k in ("code", "name", "origin", "kind", "description", "file_pattern", "columns", "key_columns", "as_of_column", "quality_rules", "parser")})
    assert created.status_code == 201, created.text
    up = admin.post("/admin/datasets/TEST_NEWDS_ADMIN/upload", data={"origin": "bank", "data_origin": "simulated"}, files=_files("a.csv", MONTHLY))
    assert up.status_code == 201 and up.json()["status"] == "committed" and up.json()["rows"] == 6

    wider = _csv("기준월,상품코드,상품명,잔액,담당부서", [f"202608,{p},{n},{700 + i},부서{i}" for i, (p, n) in enumerate(PRODUCTS)])
    up2 = admin.post("/admin/datasets/TEST_NEWDS_ADMIN/upload", data={"origin": "bank", "data_origin": "simulated"}, files=_files("b.csv", wider)).json()
    info = next(c for c in up2["quality"]["checks"] if c["rule"] == "unmapped_headers")
    assert info["passed"] is True and info["severity"] == "info" and "담당부서" in info["detail"]  # 조용히 버리지 않고 알린다
    assert up2["quality"]["status"] == "passed" and up2["status"] == "committed"  # 안내일 뿐 통과를 바꾸지 않는다

    diff = admin.post("/admin/datasets/TEST_NEWDS_ADMIN/infer-diff", files=_files("b.csv", wider))
    assert diff.status_code == 200, diff.text
    nd = diff.json()
    assert [c["label"] for c in nd["newColumns"]] == ["담당부서"] and all(c["required"] is False for c in nd["newColumns"])
    assert len(nd["columns"]) == len(d["columns"]) + 1
    patched = admin.patch("/admin/datasets/TEST_NEWDS_ADMIN", json={"columns": nd["columns"]})
    assert patched.status_code == 200, patched.text
    up3 = admin.post("/admin/datasets/TEST_NEWDS_ADMIN/upload", data={"origin": "bank", "data_origin": "simulated"}, files=_files("c.csv", wider)).json()
    assert not any(c["rule"] == "unmapped_headers" for c in up3["quality"]["checks"])
    rows = admin.get(f"/admin/datasets/TEST_NEWDS_ADMIN/versions/{up3['id']}/rows").json()["rows"]
    assert {r.get("담당부서") for r in rows} == {"부서0", "부서1", "부서2"}  # 새 열 값이 이제 저장된다


def test_definition_guards(db, world):
    """정의가 비었거나 서로 안 맞는 정의는 만들지 못하고, 이미 열이 비어 있는 데이터셋에 올리면 '통과' 가 아니라 실패로 알린다."""
    from nhdip.models import Dataset

    admin = world["admin"]
    base = {"code": "TEST_NEWDS_BAD", "name": "나쁜 정의", "origin": "bank", "columns": [{"name": "a", "type": "str"}]}
    assert admin.post("/admin/datasets", json={**base, "columns": []}).status_code == 422
    assert admin.post("/admin/datasets", json={**base, "key_columns": ["zz"]}).status_code == 422
    assert admin.post("/admin/datasets", json={**base, "code": "한글 코드"}).status_code == 422
    assert admin.post("/admin/datasets", json={**base, "columns": [{"name": "a", "type": "str"}, {"name": "A", "type": "str"}]}).status_code == 422
    # 수정으로 키가 없는 열을 가리키게 만들 수 없다
    assert admin.post("/admin/datasets", json={**base, "code": "TEST_NEWDS_OK"}).status_code == 201
    assert admin.patch("/admin/datasets/TEST_NEWDS_OK", json={"key_columns": ["nope"]}).status_code == 422
    assert admin.patch("/admin/datasets/TEST_NEWDS_OK", json={"description": "설명만"}).status_code == 200

    # 예전 방식으로 열이 비어 만들어진 데이터셋 — 모든 행이 빈 값으로 통과 저장되던 것을 막는다
    with db() as s:
        s.add(Dataset(code="TEST_NEWDS_EMPTY", name="열 없음", origin="bank", kind="fact", columns=[], key_columns=[], quality_rules=[], mapping={}, parser={}))
        s.commit()
    up = admin.post("/admin/datasets/TEST_NEWDS_EMPTY/upload", data={"origin": "bank", "data_origin": "simulated"}, files=_files("e.csv", MONTHLY))
    assert up.status_code == 201 and up.json()["status"] == "rejected"
    assert "컬럼 정의가 없습니다" in json.dumps(up.json()["quality"], ensure_ascii=False)


def test_int_column_with_text_is_a_quality_failure_not_a_server_error(db, world):
    admin = world["admin"]
    body = {"code": "TEST_NEWDS_INT", "name": "정수 시험", "origin": "bank", "columns": [{"name": "k", "type": "str", "required": True}, {"name": "n", "type": "int"}], "key_columns": ["k"]}
    assert admin.post("/admin/datasets", json=body).status_code == 201
    up = admin.post("/admin/datasets/TEST_NEWDS_INT/upload", data={"origin": "bank", "data_origin": "simulated"}, files=_files("i.csv", _csv("k,n", ["a,1", "b,abc"])))
    assert up.status_code == 201, up.text  # 예전에는 InvalidOperation 으로 500
    assert up.json()["status"] == "rejected" and "정수 아님" in json.dumps(up.json()["quality"], ensure_ascii=False)



def test_admin_infer_suggests_a_free_code(db, world):
    """파일 이름에서 정한 코드가 이미 있으면 번호를 붙여 제안하고(업무 화면과 같은 규칙), 직접 정한 코드는 그대로 두고 exists 로 알린다."""
    admin = world["admin"]
    taken = {"code": "TEST_NEWDS_TAKEN", "name": "코드 선점", "origin": "bank", "columns": [{"name": "a", "type": "str"}]}
    assert admin.post("/admin/datasets", json=taken).status_code in (201, 409)
    auto = admin.post("/admin/datasets/infer", files=_files("TEST_NEWDS_TAKEN_202607.csv", MONTHLY), data={"origin": "bank"}).json()
    assert auto["code"] == "TEST_NEWDS_TAKEN_2" and auto["codeAdjusted"] is True and auto["exists"] is False
    manual = admin.post("/admin/datasets/infer", files=_files("TEST_NEWDS_TAKEN_202607.csv", MONTHLY), data={"origin": "bank", "code": "TEST_NEWDS_TAKEN"}).json()
    assert manual["code"] == "TEST_NEWDS_TAKEN" and manual["exists"] is True and manual["codeAdjusted"] is False