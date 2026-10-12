"""지표 where 조건 — ne · nin(집계 행 빼기) · 집계 행 이름 판별."""

from nhdip.analysis_agents.spec import AGG_ROW_RE
from nhdip.calc.metrics import _match


def test_match_ne_and_nin():
    rows = [{"p": "A"}, {"p": "OTHERS"}, {"p": "합계"}, {"p": "B"}]
    assert [r["p"] for r in rows if _match(r, {"p": {"ne": "OTHERS"}}, None)] == ["A", "합계", "B"]
    assert [r["p"] for r in rows if _match(r, {"p": {"nin": ["OTHERS", "합계"]}}, None)] == ["A", "B"]
    assert [r["p"] for r in rows if _match(r, {"p": {"in": ["A", "B"]}}, None)] == ["A", "B"]


def test_aggregate_row_names():
    for name in ("OTHERS", "other", "Total", "합계", "소계", "기타", "전체", "그 외 상품 합계", "그외"):
        assert AGG_ROW_RE.search(name), name
    for name in ("사잇돌중금리대출", "기업형소호", "가계대출", "전체적금"):
        assert not AGG_ROW_RE.search(name), name
