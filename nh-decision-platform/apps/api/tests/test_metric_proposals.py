"""새 지표 제안 (§35 MET) — 지표가 없는 새 자료를 올리면 지표 제안 에이전트(규칙)가 꺼진 지표를 만들고, 승인하면 계산 커널이 계산한다."""
from __future__ import annotations

import io

from fastapi.testclient import TestClient
from sqlalchemy import select


def _admin() -> TestClient:
    from nhdip import ratelimit
    from nhdip.main import app

    ratelimit.reset()
    c = TestClient(app)
    assert c.post("/auth/login", json={"emp_no": "00000001", "password": "Admin1234!"}).status_code == 200
    return c


def test_agent_proposes_metric_and_approval_computes(db):
    from conftest import drain_workflows

    from nhdip.models import Metric, MetricValue

    c = _admin()
    rows = "\n".join(f"2026{m:02d},A{i},{100 * i + m}" for m in (6, 7, 8) for i in (1, 2))
    data = ("기준월,외화상품코드,외화예수금잔액\n" + rows + "\n").encode("utf-8")
    r = c.post("/admin/datasets/auto-upload", data={"origin": "bank", "data_origin": "simulated"}, files={"file": ("외화예수금_월별.csv", io.BytesIO(data), "text/csv")})
    assert r.status_code == 201, r.text
    drain_workflows(db)
    props = c.get("/admin/metric-proposals").json()
    mine = [p for p in props if "외화예수금잔액" in p["description"]]
    assert mine, props
    sums = [p for p in mine if p["code"].endswith("_sum")]
    assert sums and sums[0]["formula"] == "VALUE"
    code = sums[0]["code"]
    assert c.post(f"/admin/metric-proposals/{code}/approve").status_code == 200
    drain_workflows(db)
    with db() as s:
        assert s.get(Metric, code).enabled
        mv = s.execute(select(MetricValue).where(MetricValue.metric_code == code).order_by(MetricValue.id.desc())).scalars().first()
        assert mv is not None and float(mv.value) == 108 + 208  # 최근 기준일(2026.08) 합계
    # 반려한 제안은 목록에서 빠지고 다시 만들어지지 않는다
    rest = [p["code"] for p in mine if p["code"] != code]
    for x in rest:
        assert c.post(f"/admin/metric-proposals/{x}/reject").status_code == 200
    assert not [p for p in c.get("/admin/metric-proposals").json() if "외화예수금잔액" in p["description"]]
