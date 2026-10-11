"""업로드 시험(B.40)에서 찾은 에이전트 견고성 보완 — DB 없이."""
from __future__ import annotations

from types import SimpleNamespace

from nhdip.graph.extraction import Resolver, validate


def _schema():
    return SimpleNamespace(
        classes=[{"label": "PolicyTheme", "resolve": "master"}, {"label": "ProductGroup", "resolve": "master"}],
        relations=[{"type": "STATES_STANCE", "from": "Document", "to": "PolicyTheme", "props": ["direction"], "allowed": {"direction": ["확대", "축소", "유지"]}},
                   {"type": "MENTIONS", "from": "Document", "to": "*"}],
        aliases={"PolicyTheme": {"INCLUSIVE_FINANCE": ["포용금융", "서민금융"]}, "ProductGroup": {"새희망홀씨대출": ["새희망홀씨"]}},
    )


def test_relation_endpoints_as_objects_are_resolved():
    """모델이 관계 양끝을 {key, label} 객체 · 별칭 이름으로 답해도 마스터 키로 해석한다(이전: '양끝 해석 불가' 로 모두 버림)."""
    text = "정책서민금융 상품의 공급 목표를 상향하고 서민금융 상품 취급을 확대한다. 새희망홀씨 등 공급을 늘린다."
    data = {
        "entities": [],
        "relations": [
            {"type": "STATES_STANCE", "from": "$doc", "to": {"key": "포용금융", "label": "PolicyTheme"}, "props": {"direction": "확대"}, "evidence_span": "서민금융 상품 취급을 확대한다"},
            {"type": "MENTIONS", "from": {"key": "$doc"}, "to": {"key": "새희망홀씨", "label": "ProductGroup"}, "evidence_span": "새희망홀씨 등 공급을 늘린다"},
            {"type": "MENTIONS", "from": "$doc", "to": {"key": "없는것", "label": "ProductGroup"}, "evidence_span": "새희망홀씨 등 공급을 늘린다"},
        ],
    }
    s = _schema()
    ents, rels, issues = validate(s, Resolver(s), text, data)
    assert [(r["type"], r["to"], r["to_label"]) for r in rels] == [("STATES_STANCE", "INCLUSIVE_FINANCE", "PolicyTheme"), ("MENTIONS", "새희망홀씨대출", "ProductGroup")]
    assert [i["kind"] for i in issues] == ["unresolved_entity"]  # 마스터에 없는 이름은 계속 검토 대기


def test_judge_repairs_malformed_json_without_cooldown(monkeypatch):
    """판단 LLM 출력의 JSON 형식 오류는 한 번 다시 요청해 고치고, 모델 장애처럼 쉬지 않는다."""
    from nhdip.workflow import llm_judge as J

    calls = []

    class R:
        def __init__(self, text):
            self.text, self.call_id = text, f"c{len(calls)}"

    def fake_chat(session, llm, messages, **kw):
        calls.append(messages)
        return R('{"changes": [{"code": "a" "level": "major"}]}' if len(calls) == 1 else '{"changes": [{"code": "a", "level": "major"}]}')

    llm = SimpleNamespace(timeout=30, retries=1, user_template="", system_prompt="", model="m", prompt_version=1)
    monkeypatch.setattr(J, "chat", fake_chat)
    monkeypatch.setattr(J, "resolve", lambda session, code: llm)
    monkeypatch.setattr(J, "policy", lambda session: {**J.DEFAULT_POLICY})
    monkeypatch.setattr(J, "_cooling", lambda *a: False)
    import dataclasses

    monkeypatch.setattr(dataclasses, "replace", lambda obj, **kw: obj)
    J._COOL.clear()
    data, meta = J.ask_json(None, "change_detector", "과제", {"x": 1}, required=("changes",))
    assert data == {"changes": [{"code": "a", "level": "major"}]} and meta["by"] == "llm"
    assert len(calls) == 2 and "JSON 형식 오류" in calls[1][-1]["content"]
    assert "change_detector" not in J._COOL


def test_marker_unit_not_doubled():
    from nhdip.contracts.materialize import render_markers

    figs = {"c": {"value": 12, "unit": "CNT", "decimals": 0}, "p": {"value": 1.27, "unit": "PCT", "decimals": 2}}
    assert render_markers("권고 [[fig:c]]건, 비중 [[fig:p]]", figs) == "권고 12건, 비중 1.27%"
    assert render_markers("[[fig:c]] 규모", figs) == "12건 규모"


def test_prospect_select_excludes_existing_borrowers():
    """B.40 — 이미 유치한(당행 차주 명세에 있는) 기업은 '미거래' 후보에서 제외 — 표기 차이((주) · 공백) 무시."""
    from nhdip.calc import execute

    pol = {"max_grade": "3B", "max_debt_ratio_pct": 200, "max_candidates": 5, "loan_mn_by_model": {"11": 5000}}
    office = {"region": "경기", "sigungu": "수원시"}
    mk = lambda n, ind: {"corp_nm": n, "region": "경기", "sigungu": "수원시 영통구", "exp_grade": "2A", "tot_equity": 100, "tot_liab": 50, "tot_asset": 500, "ind_cd": ind, "nics_model": "11"}  # noqa: E731
    args = {"prospects": [mk("신동에너지(주)", "D35113"), mk("광교바이오팜(주)", "C21210")], "branch_rows": [], "office": office, "policy": pol, "weights": [], "grade_scale": ["1", "2A", "2B", "3A", "3B"]}
    r0 = execute("PROSPECT_SELECT", args)
    r1 = execute("PROSPECT_SELECT", {**args, "existing": ["신동에너지 (주)", "다른기업"]})
    assert r0.value == 2 and r1.value == 1 and r1.extra["excluded"]["existing"] == 1
    assert [x["corp_nm"] for x in r1.extra["selected"]] == ["광교바이오팜(주)"]
