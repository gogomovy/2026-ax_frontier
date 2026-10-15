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


# ── B.42 온톨로지 추출 '부분 추출' 보완 ─────────────────────────────

def _seed_schema():
    """플랫폼 시스템 온톨로지 + 시연 업무 구성 파일의 온톨로지(Phase O — 업무 클래스 · 별칭은 구성 파일에서 온다)."""
    from nhdip.sample.build import business_config
    from nhdip.seed import defs_core as C

    o = business_config()["ontology"]
    return SimpleNamespace(classes=[*C.ONTOLOGY_CLASSES, *(o.get("classes") or [])], relations=[*C.ONTOLOGY_RELATIONS, *(o.get("relations") or [])],
                           aliases={**C.ONTOLOGY_ALIASES, **(o.get("aliases") or {})})


def test_span_found_in_title_spacing_and_ellipsis():
    """근거 문장: 본문 띄어쓰기 · 가운뎃점 차이, 말줄임으로 이은 조각, 제목 인용은 통과 — 원문에 없는 문장 · 짧은 조각 잇기는 거부."""
    from nhdip.graph.extraction import span_source

    body = "2026년 9월 말 기준 소기업 모형 6B 등급의 실제부도율이 예측부도율 대표값을 2개월 연속 상회했다. 재무 · 비재무 항목을 추가 확인한다."
    title = "(시뮬레이션) 신용리스크관리부 공문 - 소기업 모형 6B 등급 부도율 점검 요청(2026.09)"
    assert span_source("소기업모형 6B등급의 실제부도율이", body, title) == "body"  # PDF 추출 띄어쓰기 차이
    assert span_source("재무ㆍ비재무 항목을", body, title) == "body"  # 가운뎃점 표기 차이
    assert span_source("소기업 모형 6B 등급의 실제부도율이 … 2개월 연속 상회했다", body, title) == "body"
    assert span_source("6B 등급 부도율 점검 요청", body, title) == "title"
    assert span_source("6B 등급 부도율이 급등했다", body, title) is None
    assert span_source("2개월 연속 상회했다 … 소기업 모형", body, title) is None  # 조각 순서가 다르면 거부
    assert span_source("6B … 등급", body, title) is None  # 짧은 조각만 이은 근거는 인용으로 보지 않음
    assert span_source("", body, title) is None


def test_resolver_compact_contains_and_ambiguity():
    """별칭 해석: 공백 무시 · 포함 일치(가장 긴 별칭 우선 — '비외감' 안의 '외감' 제외), 복합 이름 · 없는 이름은 해석하지 않음."""
    s = _seed_schema()
    r = Resolver(s)
    assert r.resolve("RatingModel", "소기업모형") == "CORP_MICRO"
    assert r.resolve("RatingModel", "소기업 모형 6B 등급") == "CORP_MICRO"
    assert r.resolve("PolicyTheme", "서민금융 공급 확대") == "포용금융"
    assert r.resolve("PolicyTheme", "취약차주 보호") == "포용금융"
    assert r.resolve("Segment", "비외감 기업") == "비외감"
    assert r.resolve("Segment", "외감기업") == "외감"
    assert r.resolve("PolicyTheme", "가계부채 관리 및 포용금융 확대") is None  # 서로 다른 주제가 섞인 이름
    assert r.resolve("ProductGroup", "정책서민금융 상품") is None  # 특정 상품군이 아님 → 검토 대기
    assert r.resolve("Issuer", "금융위원회") == "금융위원회"  # 마스터 해석 대상이 아닌 클래스는 그대로


def test_validate_title_span_name_fallback_and_relation_label():
    """제목 인용 근거는 span_source=title 로 통과, key 가 설명형이면 name 으로 해석, 관계 끝 라벨이 없으면 관계 정의 라벨로 해석."""
    s = _seed_schema()
    title = "(시뮬레이션) 2026년 하반기 서민금융 공급 확대 및 취약차주 보호 방안"
    body = "정책서민금융 상품의 공급 목표를 상향하고, 금융회사의 자체 서민금융 상품 취급을 확대해 불법사금융 이용을 줄인다. 새희망홀씨 등 은행권 자체 서민금융 공급 목표를 확대한다."
    data = {
        "entities": [
            {"label": "PolicyTheme", "key": "2026 하반기 정책 방향", "name": "서민금융", "props": {}, "evidence_span": "서민금융 공급 확대 및 취약차주 보호 방안"},
            {"label": "ProductGroup", "key": "새희망홀씨", "name": "새희망홀씨", "props": {}, "evidence_span": "새희망홀씨 등 은행권 자체 서민금융 공급 목표를"},
        ],
        "relations": [
            {"type": "STATES_STANCE", "from": "$doc", "to": "정책서민금융", "props": {"direction": "expand"}, "evidence_span": "자체 서민금융 상품 취급을 확대해"},
            {"type": "MENTIONS", "from": "$doc", "to": "새희망홀씨", "evidence_span": "새희망홀씨 등"},
        ],
    }
    ents, rels, issues = validate(s, Resolver(s), body, data, title=title)
    assert issues == []
    assert [(e["label"], e["key"], e.get("span_source")) for e in ents] == [("PolicyTheme", "포용금융", "title"), ("ProductGroup", "새희망홀씨대출", None)]
    assert [(r["type"], r["to_label"], r["to"]) for r in rels] == [("STATES_STANCE", "PolicyTheme", "포용금융"), ("MENTIONS", "ProductGroup", "새희망홀씨대출")]
    # 제목 없이 같은 입력이면 제목 인용 근거는 원문에 없다고 본다(이전 동작)
    _, _, issues2 = validate(s, Resolver(s), body, data)
    assert [i["kind"] for i in issues2] == ["span_not_found"]


# ── B.43 판단 입력 글자 상한 — JSON 을 자르지 않고 목록을 덜어 낸다 ─────────────

def test_fit_context_trims_list_tail_and_keeps_valid_json():
    import json

    from nhdip.workflow.llm_judge import fit_context

    small = {"workflow": {"code": "wf"}, "candidates": [{"code": "a"}]}
    text, trimmed = fit_context(small, 14000)
    assert json.loads(text) == small and trimmed == {}

    cands = [{"code": f"m{i:03d}", "label": "지표" * 10, "deltaPct": 100 - i} for i in range(120)]
    ctx = {"workflow": {"code": "wf_branch_kpi", "name": "영업점"}, "guidance": "", "candidates": cands, "notes": ["x" * 50] * 40}
    text, trimmed = fit_context(ctx, 3000, shrink=("candidates",))
    data = json.loads(text)  # 잘린 JSON 이 아니다
    assert len(text) <= 3000
    kept = data["candidates"]
    assert kept == cands[: len(kept)] and len(kept) >= 1  # 앞쪽(중요한 순) 후보를 남긴다
    assert data["_omitted"]["candidates"] == trimmed["candidates"] == 120 - len(kept)
    assert data["workflow"] == ctx["workflow"]
    assert len(ctx["candidates"]) == 120  # 원본은 바꾸지 않는다

    # 우선 줄일 키가 없으면 큰 목록부터
    text2, trimmed2 = fit_context({"a": ["y" * 100] * 30, "b": ["z"] * 3}, 1200)
    assert "a" in trimmed2 and "b" not in trimmed2 and len(text2) <= 1200

    # 목록을 다 줄여도 넘으면 보내지 않는다(호출자가 규칙 판단)
    text3, _ = fit_context({"big": "q" * 5000, "c": [1, 2]}, 1000)
    assert text3 is None


def test_ask_json_reports_trimmed_candidates(monkeypatch):
    """ask_json 이 상한을 넘는 입력을 덜어 내고 메타 contextTrimmed 로 알린다 — LLM 에는 완전한 JSON 만 간다."""
    import dataclasses

    from nhdip.workflow import llm_judge as J

    sent = []

    class R:
        text, call_id = '{"changes": []}', "c1"

    def fake_chat(session, llm, messages, **kw):
        sent.append(messages[-1]["content"])
        return R()

    llm = SimpleNamespace(timeout=30, retries=1, user_template="", system_prompt="", model="m", prompt_version=1)
    monkeypatch.setattr(J, "chat", fake_chat)
    monkeypatch.setattr(J, "resolve", lambda session, code: llm)
    monkeypatch.setattr(J, "policy", lambda session: {**J.DEFAULT_POLICY, "max_context_chars": 2000})
    monkeypatch.setattr(J, "_cooling", lambda *a: False)
    monkeypatch.setattr(dataclasses, "replace", lambda obj, **kw: obj)
    J._COOL.clear()
    cands = [{"code": f"c{i}", "label": "변화 후보 " * 5} for i in range(80)]
    data, meta = J.ask_json(None, "change_detector", "과제", {"candidates": cands}, required=("changes",), shrink=("candidates",))
    assert meta["by"] == "llm" and 0 < meta["contextTrimmed"]["candidates"] < 80
    assert '"_omitted"' in sent[0] and "_omitted 는 글자 상한" in sent[0]


def test_relation_prop_values_normalized_to_codes():
    """2026-10-12 LLM 모드 업로드 시험 — 허용값이 코드(expand · manage · maintain)인데 모델이 '확대' · 'Expand' 로 답하면
    관계 정의의 rule_keywords 로 코드에 맞춘다. 뜻을 알 수 없는 값은 이전처럼 '허용 외'."""
    s = SimpleNamespace(
        classes=[{"label": "PolicyTheme", "resolve": "master"}],
        relations=[{"type": "STATES_STANCE", "from": "Document", "to": "PolicyTheme", "props": ["direction"], "allowed": {"direction": ["expand", "manage", "maintain"]},
                    "rule_keywords": {"expand": ["확대", "공급 확대"], "manage": ["관리"], "maintain": ["유지"]}}],
        aliases={"PolicyTheme": {"포용금융": ["포용금융", "서민금융"]}},
    )
    text = "서민금융 공급을 확대한다."
    rel = lambda d: {"type": "STATES_STANCE", "from": "$doc", "to": "포용금융", "props": {"direction": d}, "evidence_span": "서민금융 공급을 확대한다"}  # noqa: E731
    _, rels, issues = validate(s, Resolver(s), text, {"entities": [], "relations": [rel("확대"), rel("Expand"), rel("공급 확대"), rel("줄임")]})
    assert [r["props"]["direction"] for r in rels] == ["expand", "expand", "expand"]
    assert [i["kind"] for i in issues] == ["schema_violation"] and "줄임" in issues[0]["reason"]
