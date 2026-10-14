"""삭제한 자료의 파생물이 새지 않게 (DEL-11) — 표 · 차트 갱신 실패 표시와 색인 제외, 삭제된 자료로 계산한 지표 이력을 쓰지 않음."""
from __future__ import annotations

import copy
from datetime import timedelta

import pytest

REPORT = {
    "title": "시험 보고서",
    "sections": [
        {
            "heading": "현황",
            "blocks": [
                {"type": "p", "text": "본문 설명 문장입니다. 자료 현황을 보여 줍니다."},
                {
                    "type": "table",
                    "table": {
                        "caption": "등급별 현황",
                        "columns": [{"key": "grade", "label": "등급"}, {"key": "cnt", "label": "건수"}],
                        "rows": [{"grade": "A등급", "cnt": 1234567}, {"grade": "B등급", "cnt": 7654321}],
                        "note": "비고 문구 999",
                    },
                },
                {
                    "type": "chart",
                    "chart": {
                        "kind": "bar",
                        "title": "등급별 추이",
                        "unit": "CNT",
                        "series": [{"name": "건수", "points": [{"label": "A", "value": 111222}, {"label": "B", "value": 333444}]}],
                    },
                },
            ],
        }
    ],
}


def _text(payload: dict) -> str:
    from nhdip.knowledge.render import render_artifact

    return "\n".join(d.text for d in render_artifact("report.derived-test", payload).drafts)


def test_stale_table_and_chart_are_not_indexed():
    """갱신 실패한 표 · 차트는 값(행 · 계열 · 비고)을 검색 색인 문장에 싣지 않고 '미산출(갱신 실패)' 만 남긴다."""
    fresh = _text(REPORT)
    assert "1234567" in fresh.replace(",", "") and "111222" in fresh.replace(",", "") and "비고 문구 999" in fresh

    stale = copy.deepcopy(REPORT)
    blocks = stale["sections"][0]["blocks"]
    blocks[1]["table"].update(stale=True, staleReason="확정된 버전 없음: X")
    blocks[2]["chart"].update(stale=True, staleReason="확정된 버전 없음: X")
    out = _text(stale)
    flat = out.replace(",", "")
    assert "등급별 현황" in out and "등급별 추이" in out  # 제목은 남겨 무엇이 비었는지 알린다
    assert out.count("미산출(갱신 실패)") >= 2
    for leaked in ("1234567", "7654321", "111222", "333444", "비고 문구 999"):
        assert leaked not in flat, leaked
    assert "본문 설명 문장입니다" in out  # 다른 내용은 그대로


def test_stale_series_node_not_indexed():
    """계열(points) 객체가 갱신 실패이면 추이 문장을 싣지 않는다."""
    payload = {"title": "추이", "trends": [{"key": "corp", "name": "기업", "points": [{"label": "1월", "value": 555111}, {"label": "2월", "value": 666222}], "stale": True, "staleReason": "계산 실패"}]}
    out = _text(payload)
    assert "555111" not in out.replace(",", "") and "666222" not in out.replace(",", "")
    assert "미산출(갱신 실패)" in out


def test_mark_binding_stale_only_marks_table_chart_series_targets():
    from nhdip.views.template import binding_targets, mark_binding_stale

    payload = copy.deepcopy(REPORT)
    tpath = "table:등급별 현황"
    targets = binding_targets(payload, tpath)
    assert targets and targets[0][1] == "rows"
    assert mark_binding_stale(payload, tpath, targets, "확정된 버전 없음") is True
    tb = payload["sections"][0]["blocks"][1]["table"]
    assert tb["stale"] is True and tb["staleReason"] == "확정된 버전 없음"
    assert tb["rows"][0]["cnt"] == 1234567  # 이전 값은 그대로 둔다
    assert mark_binding_stale(payload, tpath, targets, "확정된 버전 없음") is False  # 같은 사유면 바뀐 게 없다
    assert mark_binding_stale(payload, tpath, targets, None) is True  # 다시 계산되면 표시를 뗀다
    assert "stale" not in tb and "staleReason" not in tb
    assert mark_binding_stale(payload, tpath, targets, None) is False

    ctab = "chart:등급별 추이"
    assert mark_binding_stale(payload, ctab, binding_targets(payload, ctab), "x") is True
    assert payload["sections"][0]["blocks"][2]["chart"]["stale"] is True

    # 점 표기 경로(부모가 여러 수치를 품은 큰 객체)에는 표시를 달지 않는다 — 멀쩡한 수치까지 색인에서 빠지지 않게
    big = {"corporate": {"balance": {"id": "f", "label": "잔액", "unit": "KRW_BN", "value": 3}, "yearly": [{"label": "a", "value": 1}]}}
    p = "corporate.yearly"
    assert mark_binding_stale(big, p, binding_targets(big, p), "x") is False
    assert "stale" not in big["corporate"]


def test_metric_history_from_deleted_data_is_not_reused(db):
    """다른 지표가 {"metric": ...} 로 참조할 때, 이후에 버전이 삭제된 데이터셋으로 계산한 저장 값은 건너뛴다."""
    from nhdip.calc.metrics import EvalContext, ResolveError, resolve_ref
    from nhdip.models import CalcRun, MetricValue, new_id, source, utcnow

    code, ds = "tst_derived_metric", "TEST_DERIVED_DS"
    with db() as s:
        now = utcnow()
        old_run = CalcRun(id=new_id(), formula_id="VALUE", metric_code=code, inputs={}, sources=[{"param": "v", "source": "x", "dataset": ds, "version": 1}], created_at=now - timedelta(hours=2))
        clean_run = CalcRun(id=new_id(), formula_id="VALUE", metric_code=code, inputs={}, sources=[{"param": "v", "source": "x", "dataset": "OTHER_DS", "version": 1}], created_at=now - timedelta(hours=3))
        s.add_all([old_run, clean_run])
        s.flush()
        s.add(MetricValue(metric_code=code, value=11, display_value=11, calc_run_id=clean_run.id, created_at=now - timedelta(hours=3)))
        s.add(MetricValue(metric_code=code, value=99, display_value=99, calc_run_id=old_run.id, created_at=now - timedelta(hours=2)))
        s.commit()

        # 아직 아무 버전도 삭제되지 않았다 — 가장 최근 값(99)을 쓴다
        v, src, _ = resolve_ref(EvalContext(session=s), {"metric": code})
        assert float(v) == 99 and code in src

        # 데이터셋 ds 의 버전 하나가 삭제됨(삭제 시각이 99 를 계산한 뒤) — 99 는 건너뛰고 다른 데이터셋으로 계산한 11 을 쓴다
        from nhdip.models import Dataset

        if s.get(Dataset, ds) is None:
            s.add(Dataset(code=ds, name="파생물 시험", origin="bank", kind="fact", columns=[], key_columns=[], quality_rules=[], mapping={}, parser={}))
            s.flush()
        t = source("bank")
        s.add(t.version(dataset_code=ds, version=1, status="deleted", is_current=False, row_count=0, quality={}, deleted_at=now - timedelta(hours=1), deleted_by="tester", delete_reason="시험"))
        s.commit()
        v, _, _ = resolve_ref(EvalContext(session=s), {"metric": code})
        assert float(v) == 11

        # 삭제 뒤에 다시 계산된 값은 쓴다
        new_run = CalcRun(id=new_id(), formula_id="VALUE", metric_code=code, inputs={}, sources=[{"param": "v", "source": "x", "dataset": ds, "version": 2}])
        s.add(new_run)
        s.flush()
        s.add(MetricValue(metric_code=code, value=55, display_value=55, calc_run_id=new_run.id))
        s.commit()
        v, _, _ = resolve_ref(EvalContext(session=s), {"metric": code})
        assert float(v) == 55

        # 삭제된 자료로 계산한 값밖에 없으면 오류로 알린다
        s.query(MetricValue).filter(MetricValue.metric_code == code, MetricValue.value.in_([11, 55])).delete(synchronize_session=False)
        s.commit()
        with pytest.raises(ResolveError, match="삭제된 자료"):
            resolve_ref(EvalContext(session=s), {"metric": code})
