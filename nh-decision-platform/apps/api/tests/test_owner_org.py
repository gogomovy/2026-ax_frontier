"""자료 소유 조직 (§33 OWN) — 관리자가 고른 팀 · 영업점으로 올라가고, 영업점 자료는 영업점마다 현재 판을 따로 두며, 목록에 소유 팀이 보인다."""
from __future__ import annotations

import io

from fastapi.testclient import TestClient
from sqlalchemy import update

ADMIN = ("00000001", "Admin1234!")
PW = "abcd1234"


def _client() -> TestClient:
    from nhdip.main import app

    return TestClient(app)


def _login(c: TestClient, emp: str, pw: str) -> None:
    from nhdip import ratelimit

    ratelimit.reset()
    assert c.post("/auth/login", json={"emp_no": emp, "password": pw}).status_code == 200


def _csv(rows: list[str]) -> bytes:
    return ("소유시험점코드,기준월,소유시험값\n" + "\n".join(rows) + "\n").encode("utf-8")


def _up(c: TestClient, data: bytes, owner: str | None):
    form = {"origin": "bank", "data_origin": "simulated", **({"owner_org": owner} if owner is not None else {})}
    return c.post("/admin/datasets/auto-upload", data=form, files={"file": ("소유시험_202608.csv", io.BytesIO(data), "text/csv")})


def test_owner_org_partition_and_lists(db):
    admin = _client()
    _login(admin, *ADMIN)
    assert _up(admin, _csv(["001068,202608,1"]), "NO_SUCH_ORG").status_code == 422
    a = _up(admin, _csv(["001068,202608,1", "001068,202608,2"]), "001068")
    assert a.status_code == 201, a.text
    code = a.json()["dataset"]
    b = _up(admin, _csv(["BR301,202608,5"]), "BR301")
    assert b.status_code == 201 and b.json()["dataset"] == code, b.text
    c = _up(admin, _csv(["ALL,202608,9"]), None)  # 전행 공통 — 영업점 판은 밀어내지 않는다
    assert c.status_code == 201 and c.json()["dataset"] == code
    d = _up(admin, _csv(["001068,202608,3"]), "001068")  # 같은 영업점이 다시 올리면 그 영업점 판만 바뀐다
    assert d.status_code == 201
    vs = next(x for x in admin.get("/admin/datasets").json() if x["code"] == code)["versions"]
    cur = {(v["owner"] or {}).get("code"): v["version"] for v in vs if v["isCurrent"]}
    assert cur == {"001068": 4, "BR301": 2, None: 3}, cur
    # 영업점 직원 — 자기 영업점 자료(내 팀) · 전행 공통은 보이고 다른 영업점 자료는 보이지 않는다
    emp = "20259361"
    u = _client()
    u.post("/auth/signup", json={"emp_no": emp, "name": "소유시험", "password": PW, "org_code": "BR301"})
    admin.post(f"/admin/users/{emp}/approve")
    _login(u, emp, PW)
    from nhdip.models import ScreenGrant

    with db() as s:
        if s.get(ScreenGrant, ("BR301", "KNOWLEDGE")) is None:
            s.add(ScreenGrant(org_code="BR301", screen_code="KNOWLEDGE"))
            s.commit()
    r = u.get("/screens/datasets")
    assert r.status_code == 200, r.text
    owners = {(x["owner"] or {}).get("code"): x["mine"] for x in r.json() if x.get("dataset") == code}
    assert owners == {"BR301": True, None: False}, owners
    allv = [x for x in admin.get("/screens/datasets").json() if x.get("dataset") == code]
    assert len(allv) == 3 and {(x["owner"] or {}).get("code") for x in allv} == {"001068", "BR301", None}
    assert next(x for x in allv if (x["owner"] or {}).get("code") == "001068")["owner"]["name"] == "수원영통지점"
    # 영업점이 올린 자료가 있으면 그 영업점도 영업점 범위 계산 대상(규칙에 지점을 더하지 않아도)
    from nhdip.scopes import owner_offices

    with db() as s:
        assert {"001068", "BR301"} <= set(owner_offices(s))
        # 정리 — 다른 시험의 영업점 범위에 섞이지 않게
        from nhdip.models import source

        t = source("bank")
        s.execute(update(t.version).where(t.version.dataset_code == code).values(is_current=False))
        s.commit()
