"""데이터 품질 — 기간 연속성 · 급변 경고 (작업 1.4). DB 불필요."""
from nhdip.data.datasets import quality_check
from nhdip.models import Dataset


def _ds(rules):
    return Dataset(code="T", name="t", origin="bank", kind="fact", columns=[], key_columns=["ym", "k"], quality_rules=rules)


def test_period_continuity_reports_missing_months_per_group():
    rows = [{"ym": ym, "k": "a", "v": 1} for ym in ("202511", "202512", "202602")] + [{"ym": ym, "k": "b", "v": 1} for ym in ("202601", "202602")]
    q = quality_check(_ds([{"rule": "period_continuity", "column": "ym", "group": "k", "severity": "warning"}]), rows, [])
    c = next(x for x in q["checks"] if x["rule"] == "continuity:ym")
    assert not c["passed"] and "a: 202601" in c["detail"] and "b:" not in c["detail"]
    assert q["status"] == "warning"


def test_max_change_against_previous_version():
    rule = {"rule": "max_change", "column": "v", "pct": 50, "severity": "warning"}
    prev = [{"ym": "202608", "k": "a", "v": 100}, {"ym": "202608", "k": "b", "v": 100}]
    rows = [{"ym": "202608", "k": "a", "v": 180}, {"ym": "202608", "k": "b", "v": 120}, {"ym": "202609", "k": "a", "v": 1}]
    q = quality_check(_ds([rule]), rows, [], previous=prev)
    c = next(x for x in q["checks"] if x["rule"] == "max_change:v")
    assert not c["passed"] and "1건" in c["detail"] and "202608/a 100→180" in c["detail"]
    # 이전 버전이 없으면(최초 적재) 검사하지 않는다
    q = quality_check(_ds([rule]), rows, [])
    assert not any(x["rule"] == "max_change:v" for x in q["checks"])
