"""AI 어시스턴트 대화 기억 (knowledge.memory) — 사번별 저장 · 토큰 예산을 넘으면 누적 요약 · 떠날 때 전체 요약 · 다시 열면 요약으로 이어 가기 ·
다시 생성(replaceLast) · 앞 턴의 도구 조건 이어받기 · 다른 사용자 격리."""
from __future__ import annotations

import uuid

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from nhdip.knowledge.defaults import MEMORY_DEFAULT
from nhdip.knowledge.memory import Turn, _rule_summary, estimate_tokens


@pytest.fixture(autouse=True)
def _analysis_computed(request):
    if "db" in request.fixturenames:
        request.getfixturevalue("computed")
    yield


def _client() -> TestClient:
    from nhdip.main import app

    return TestClient(app)


def _admin() -> TestClient:
    a = _client()
    assert a.post("/auth/login", json={"emp_no": "00000001", "password": "Admin1234!"}).status_code == 200
    return a


def _user(admin: TestClient, emp: str, org: str) -> TestClient:
    c = _client()
    r = c.post("/auth/signup", json={"emp_no": emp, "name": f"사용자{emp[-2:]}", "password": "abcd1234", "org_code": org})
    assert r.status_code in (201, 409), r.text
    admin.post(f"/admin/users/{emp}/approve")
    assert c.post("/auth/login", json={"emp_no": emp, "password": "abcd1234"}).status_code == 200
    return c


def _ask(c: TestClient, q: str, **kw) -> dict:
    r = c.post("/assist", json={"question": q, **kw})
    assert r.status_code == 200, r.text
    return r.json()


def _cid() -> str:
    return "c" + uuid.uuid4().hex[:12]


def _memory(db, **kw) -> None:
    from nhdip.models import Setting

    with db() as s:
        st = s.get(Setting, "assist.memory")
        if st is None:
            s.add(Setting(key="assist.memory", value={**MEMORY_DEFAULT, **kw}, description="시험"))
        else:
            st.value = {**MEMORY_DEFAULT, **kw}
        s.commit()


# ═════════════════════════ 단위 ═════════════════════════
def test_token_estimate_and_rule_summary_cap():
    assert estimate_tokens("") == 0
    assert estimate_tokens("가나다라") == 5 and estimate_tokens("abcdefg") == 3  # 한글 1자 ≈ 1토큰 · 그 밖 3.5자 ≈ 1토큰
    assert estimate_tokens("가나다라", 2.0) == 9  # 내부 모델 토크나이저 보정(token_factor)
    turns = [Turn(f"질문{i} " + "가" * 100, "답 " + "나" * 400, i * 2 + 1, i * 2 + 2, 0) for i in range(10)]
    s = _rule_summary("", turns, 300, 1.0)
    assert s.startswith("(앞부분 대화는 생략") and "질문9" in s and "질문0" not in s  # 상한을 넘으면 오래된 줄부터 뺀다
    again = _rule_summary(s, turns[:1], 5000, 1.0)
    assert again.count("(앞부분 대화는 생략") <= 1 and "질문0" in again  # 이전 요약에 이어 붙인다


# ═════════════════════════ 통합 ═════════════════════════
def test_conversation_is_saved_per_user_and_private(db):
    from nhdip.models import AssistMessage

    admin = _admin()
    other = _user(admin, "20269991", "T211")  # 시나리오 시험의 사번(2026930x · 2026910x · 2026920x)과 겹치지 않게
    cid = _cid()
    r1 = _ask(admin, "포용금융 충당금 비중은 얼마인가요?", conversationId=cid)
    assert r1["conversationId"] == cid and r1["conversation"]["messageCount"] == 2 and "memory" not in r1  # 첫 질문 — 저장된 맥락 없음
    r2 = _ask(admin, "그럼 증가율은?", conversationId=cid)
    assert r2["memory"]["turns"] == 1 and not r2["memory"]["summary"] and not r2["memory"]["compacted"]
    rt = r2["retrieval"]
    assert rt["rewritten"] and (any("포용금융" in c for c in r2["concepts"]) or "포용금융" in rt["rewritten"])  # 화면이 이력을 안 보내도 서버 기억으로 후속 질문을 푼다

    mine = next(c for c in admin.get("/assist/conversations").json()["items"] if c["id"] == cid)
    assert mine["messageCount"] == 4 and mine["title"].startswith("포용금융") and not mine["hasSummary"]
    d = admin.get(f"/assist/conversations/{cid}").json()
    assert [m["role"] for m in d["messages"]] == ["user", "assistant", "user", "assistant"]
    first = d["messages"][1]["result"]
    assert first["metrics"] and "scope" not in first and first["toolCalls"] == []  # 다시 열 때 출처 · 수치 카드를 그릴 재료(접근 범위 목록은 빼고)

    # 다른 사용자 — 목록에 없고, id 를 알아도 없는 대화처럼(읽기 · 이어 묻기 · 떠나기 · 지우기 모두)
    assert cid not in {c["id"] for c in other.get("/assist/conversations").json()["items"]}
    assert other.get(f"/assist/conversations/{cid}").status_code == 404
    assert other.post(f"/assist/conversations/{cid}/close").status_code == 404
    assert other.delete(f"/assist/conversations/{cid}").status_code == 404
    assert other.post("/assist", json={"question": "그럼 증가율은?", "conversationId": cid}).status_code == 404
    assert other.post("/assist/stream", json={"question": "그럼 증가율은?", "conversationId": cid}).status_code == 404
    assert admin.post("/assist", json={"question": "그럼 증가율은?", "conversationId": "../x"}).status_code == 422
    # 다른 사용자가 자기 대화를 모두 지워도 내 대화는 남는다
    _ask(other, "포용금융 충당금 비중은 얼마인가요?", conversationId=_cid())
    assert other.delete("/assist/conversations").json()["deleted"] == 1
    assert admin.get(f"/assist/conversations/{cid}").status_code == 200

    assert admin.patch(f"/assist/conversations/{cid}", json={"title": "충당금 대화"}).json()["title"] == "충당금 대화"
    assert admin.delete(f"/assist/conversations/{cid}").json()["ok"]
    assert admin.get(f"/assist/conversations/{cid}").status_code == 404
    with db() as s:
        assert s.execute(select(func.count()).select_from(AssistMessage).where(AssistMessage.conversation_id == cid)).scalar() == 0  # 메시지도 함께


def _llm_fake(db, monkeypatch, answer: str, summary: str):
    from nhdip.models import Agent, LlmProfile

    seen: dict = {"answers": [], "summaries": []}
    with db() as s:
        s.execute(select(LlmProfile).where(LlmProfile.name == "default")).scalar().model = "coder.general.multimodal"
        s.get(Agent, "query_assistant").override = {"tools_enabled": False}
        s.commit()

    def fake_post(url, headers=None, json=None, timeout=None):  # noqa: A002
        msgs = json["messages"]
        if "검색 질의 재작성기" in msgs[0]["content"]:
            content = "{}"
        elif "은행 경영 분석 AI 어시스턴트와 사용자의 대화다" in msgs[-1]["content"]:
            seen["summaries"].append(msgs[-1]["content"])
            content = '{"summary": "%s"}' % summary
        else:
            seen["answers"].append(msgs)
            content = answer
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": content}}], "usage": {}}, request=httpx.Request("POST", url))

    monkeypatch.setattr("nhdip.llm.client.httpx.post", fake_post)
    return seen


def _llm_off(db):
    from nhdip.models import Agent, LlmProfile

    with db() as s:
        s.execute(select(LlmProfile).where(LlmProfile.name == "default")).scalar().model = ""
        s.get(Agent, "query_assistant").override = {}
        s.commit()


def test_budget_compaction_close_and_reopen_continue_from_summary(db, monkeypatch):
    from nhdip.models import AssistConversation

    answer = "포용금융 충당금 관련 답변입니다. " + "설명을 이어 갑니다 " * 40  # 한 턴 ≈ 350 토큰(추정)
    seen = _llm_fake(db, monkeypatch, answer, "사용자는 포용금융 충당금 비중과 증가율을 물었다")
    _memory(db, max_context_tokens=500, keep_recent_turns=1)
    try:
        admin = _admin()
        cid = _cid()
        q1, q2, q3 = "포용금융 충당금 비중은 얼마인가요?", "그럼 증가율은?", "같은 기준으로 기업여신은?"
        _ask(admin, q1, conversationId=cid)
        r2 = _ask(admin, q2, conversationId=cid)
        # 예산 안 — 앞 턴 원문이 자르지 않은 그대로 대화 메시지(user/assistant)로 간다
        m2 = seen["answers"][-1]
        assert r2["memory"]["turns"] == 1 and not r2["memory"]["compacted"]
        assert [m["role"] for m in m2] == ["system", "user", "assistant", "user"] and q1 in m2[1]["content"] and answer.strip() in m2[2]["content"]
        assert "이전 대화 요약과 앞 턴들은 맥락 참고용" in m2[0]["content"]
        assert not seen["summaries"]

        # 예산 초과 — 오래된 턴을 요약에 합치고 최근 턴만 원문으로
        r3 = _ask(admin, q3, conversationId=cid)
        assert r3["memory"]["compacted"] and r3["memory"]["summary"] and r3["memory"]["turns"] == 1 and r3["memory"]["tokens"] <= 500
        assert len(seen["summaries"]) == 1 and q1 in seen["summaries"][0]
        m3 = seen["answers"][-1]
        assert "이전 대화 요약" in m3[1]["content"] and "사용자는 포용금융 충당금 비중과 증가율을 물었다" in m3[1]["content"]
        assert q2 in m3[3]["content"] and q1 not in "".join(m["content"] for m in m3[3:])  # 요약된 턴의 원문은 다시 보내지 않는다
        with db() as s:
            c = s.get(AssistConversation, cid)
            assert c.summarized_upto == 2 and c.summary_by == "llm" and c.closed_at is None

        # 떠날 때 — 남은 원문(2 · 3턴)까지 전체 요약
        out = admin.post(f"/assist/conversations/{cid}/close").json()
        assert out["summarized"] == 2 and out["by"] == "llm"
        assert admin.post(f"/assist/conversations/{cid}/close").json()["summarized"] == 0  # 새 턴이 없으면 다시 요약하지 않는다
        assert len(seen["summaries"]) == 2
        with db() as s:
            c = s.get(AssistConversation, cid)
            assert c.summarized_upto == 6 and c.closed_at is not None

        # 다시 열어 이어 묻기 — 맥락은 전체 요약뿐(원문은 화면 표시용으로만 남는다)
        r4 = _ask(admin, "그 중 가장 큰 변화는?", conversationId=cid)
        assert r4["memory"] == {"conversationId": cid, "turns": 0, "summary": True, "tokens": r4["memory"]["tokens"], "compacted": False}
        assert [m["role"] for m in seen["answers"][-1]] == ["system", "user", "assistant", "user"]
        d = admin.get(f"/assist/conversations/{cid}").json()
        assert len(d["messages"]) == 8 and [m["summarized"] for m in d["messages"]] == [True] * 6 + [False] * 2 and d["hasSummary"] and d["closedAt"] is None
        assert d["summary"] == "사용자는 포용금융 충당금 비중과 증가율을 물었다"
    finally:
        _memory(db)
        _llm_off(db)


def test_summary_with_invented_numbers_falls_back_to_rule_summary(db, monkeypatch):
    from nhdip.models import AssistConversation

    seen = _llm_fake(db, monkeypatch, "답변입니다 " * 10, "충당금 비중은 77.7% 였다")  # 대화에 없던 숫자
    try:
        admin = _admin()
        cid = _cid()
        _ask(admin, "포용금융 충당금 비중은 얼마인가요?", conversationId=cid)
        assert admin.post(f"/assist/conversations/{cid}/close").json()["by"] == "rule"
        assert seen["summaries"]
        with db() as s:
            c = s.get(AssistConversation, cid)
            assert "77.7" not in c.summary and "포용금융 충당금 비중은 얼마인가요?" in c.summary
    finally:
        _llm_off(db)


def test_regenerate_replaces_last_turn_and_memory_switch(db):
    admin = _admin()
    cid = _cid()
    q = "포용금융 충당금 비중은 얼마인가요?"
    _ask(admin, q, conversationId=cid)
    r = _ask(admin, q, conversationId=cid, replaceLast=True)
    assert r["conversation"]["messageCount"] == 2 and r["memory"]["turns"] == 0  # 바꿀 턴은 맥락에서도 뺀다
    # 마지막 턴과 질문이 다르면(실패해 저장되지 않은 답을 다시 만든 경우) 지우지 않고 덧붙인다
    r = _ask(admin, "기업여신 증가율과 목표 대비 이탈은?", conversationId=cid, replaceLast=True)
    assert r["conversation"]["messageCount"] == 4 and r["memory"]["turns"] == 1
    # 대화 기억을 끄면 저장 · 맥락 없이 예전처럼(화면 이력)
    _memory(db, enabled=False)
    try:
        r = _ask(admin, "그럼 증가율은?", conversationId=cid)
        assert "conversationId" not in r and "memory" not in r
        assert admin.get(f"/assist/conversations/{cid}").json()["messageCount"] == 4
    finally:
        _memory(db)
    admin.delete(f"/assist/conversations/{cid}")


def test_tool_conditions_carry_into_next_turn_and_conversation_cap(db):
    from nhdip.knowledge import memory as M
    from nhdip.models import AssistConversation

    emp = "99990001"
    with db() as s:
        cfg = {**M.config(s), "max_conversations": 2}
        result = {
            "answer": "강남금융센터 예수금 합계입니다.",
            "scope": [{"code": "x"}],
            "toolResults": [{"tool": "dataset_aggregate", "args": '{"dataset": "branch_deposit", "filters": {"office_cd": "009901"}, "group_by": ["product"]}', "result": {"rows": [{"v": 1}]}}],
        }
        conv = M.record(s, emp, "ctool0001", "강남금융센터 예수금은?", result, cfg)
        msg = s.execute(select(M.AssistMessage).where(M.AssistMessage.conversation_id == conv.id, M.AssistMessage.role == "assistant")).scalar_one()
        assert "scope" not in msg.meta and msg.meta["toolCalls"][0]["tool"] == "dataset_aggregate"
        ctx = M.context(s, conv, cfg)
        assert "[이 답에서 쓴 도구 · 조건: dataset_aggregate(" in ctx.turns[0].a and "009901" in ctx.turns[0].a  # '그럼 대출은?' 이 같은 지점 조건에서 출발
        assert any("009901" in t for t in ctx.texts())
        # 사용자당 보관 수 — 넘으면 오래된 대화부터
        M.record(s, emp, "ctool0002", "두 번째", {"answer": "b"}, cfg)
        M.record(s, emp, "ctool0003", "세 번째", {"answer": "c"}, cfg)
        ids = set(s.execute(select(AssistConversation.id).where(AssistConversation.emp_no == emp)).scalars())
        assert ids == {"ctool0002", "ctool0003"}
        with pytest.raises(M.MemoryDenied):
            M.get_owned(s, "ctool0003", "99990002")
        s.rollback()
