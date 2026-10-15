"""컬럼 정의서 시연 화면값 제거 (M.22 · Q209) — 시드 가져오기는 화면값을 비우고, 운영 DB 는 1회 정리한다.
시험 DB 는 SEED_CONTRACT_EXPECTED=1(conftest)로 화면값을 넣어 시연 자료 계산과 대조하므로, 정리 시험은 되돌린다(rollback)."""
from __future__ import annotations

from sqlalchemy import select


def test_seed_import_strips_mock_values(monkeypatch):
    from nhdip.seed import run as seed_run

    tables = [{"table_code": "T01", "columns": [{"column_name": "A", "expected_text": "7.4%"}, {"column_name": "B", "expected_text": None}]}]
    bindings = {"A": {"metric": "m1", "expected": "45.44%", "expected_note": "Q16"}, "B": {"const": "LOAN"}}
    monkeypatch.setenv("SEED_CONTRACT_EXPECTED", "0")
    assert [c["expected_text"] for c in seed_run._contract_tables(tables)[0]["columns"]] == [None, None]
    assert seed_run._contract_bindings(bindings) == {"A": {"metric": "m1"}, "B": {"const": "LOAN"}}
    assert tables[0]["columns"][0]["expected_text"] == "7.4%" and "expected" in bindings["A"]  # 원본(시드 정의)은 그대로
    monkeypatch.setenv("SEED_CONTRACT_EXPECTED", "1")
    assert seed_run._contract_tables(tables) is tables and seed_run._contract_bindings(bindings) is bindings


def test_existing_db_cleared_once_keeps_admin_values(db, monkeypatch):
    from nhdip.models import ColumnContract, OutboxEvent, Setting
    from nhdip.seed import run as seed_run

    monkeypatch.setenv("SEED_CONTRACT_EXPECTED", "0")
    with db() as s:
        try:
            st = s.get(Setting, "seed.applied_upgrades")
            st.value = [x for x in st.value if x != "contract-mock-values-v1"]
            s.flush()
            seeded = s.execute(select(ColumnContract).where(ColumnContract.expected_text.isnot(None)).order_by(ColumnContract.id)).scalars().all()
            assert len(seeded) > 5
            mine = seeded[0]
            mine.expected_text = "관리자가 고친 값 1.0%"  # 시드 값과 다르면 건드리지 않는다
            share = s.execute(select(ColumnContract).where(ColumnContract.column_name == "LOAN_INCOME_SHARE_RT")).scalar()
            assert share is not None and share.binding.get("expected") == "45.44%"
            s.flush()
            out: dict = {}
            seed_run.contract_mock_values_upgrade(s, out)
            rep = out["contract_mock_values"]
            assert rep["expected_text"] >= 5 and rep["binding_expected"] >= 1 and "T01" in rep["tables"]
            left = [c.expected_text for c in s.execute(select(ColumnContract).where(ColumnContract.expected_text.isnot(None))).scalars()]
            assert "관리자가 고친 값 1.0%" in left and len(left) <= len(seeded) - rep["expected_text"]
            assert "expected" not in share.binding and "expected_note" not in share.binding and share.binding.get("metric") == "nim_share_2026"
            s.flush()
            assert s.execute(select(OutboxEvent).where(OutboxEvent.type == "contract.changed", OutboxEvent.dispatched_at.is_(None))).scalars().first() is not None
            # 1회만
            out2: dict = {}
            seed_run.contract_mock_values_upgrade(s, out2)
            assert "contract_mock_values" not in out2
        finally:
            s.rollback()  # 다른 시험이 정의서 화면값 대조를 쓴다
