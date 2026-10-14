"""삭제한 자료의 흔적 정리 (Phase J 후속 · DEL-13~15 · Q167~Q169) — 호출 기록 · 노드 입출력의 내용, 산출물 근거 조각, 옛 산출물 세대."""
from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

ADMIN = ("00000001", "Admin1234!")


def _admin() -> TestClient:
    from nhdip import ratelimit
    from nhdip.main import app

    ratelimit.reset()
    c = TestClient(app)
    assert c.post("/auth/login", json={"emp_no": ADMIN[0], "password": ADMIN[1]}).status_code == 200
    return c


# ═════════════════════════ 본문 조각 (DB 없음) ═════════════════════════
def test_snippets_avoid_json_escaped_characters_and_short_pieces():
    from nhdip.data.scrub import SNIPPET_LEN, SNIPPET_MIN, snippets_of

    text = '포용금융 공급 확대 방안을 단계적으로 추진한다\n"서민금융" 상품군별 한도를 조정하고 \\ 잔액 기준을 점검한다.\t짧음'
    got = snippets_of([text, "", "짧다"])
    assert got and all(SNIPPET_MIN <= len(s) <= SNIPPET_LEN for s in got)
    for s in got:
        assert not any(ch in s for ch in '"\\\n\r\t')  # JSON 에서 이스케이프되는 글자는 조각에 없다 — 호출 기록 · 산출물 본문과 그대로 일치
    assert snippets_of(["같은 문장입니다 같은 문장입니다 같은 문장입니다"] * 3) == snippets_of(["같은 문장입니다 같은 문장입니다 같은 문장입니다"])  # 중복 제거


def test_strip_evidence_only_removes_matching_document_snippets():
    from nhdip.data.scrub import _strip_evidence

    ev_gone = {"id": "ev-1", "snippet": "지울 문서의 근거 조각 문장입니다 가나다라마바사", "doc": {"title": "t"}}
    ev_keep = {"id": "ev-2", "snippet": "다른 문서의 근거 조각 문장입니다 아자차카타파하", "doc": {"title": "u"}}
    not_ev = {"snippet": "지울 문서의 근거 조각 문장입니다 가나다라마바사"}  # doc 표시가 없으면 근거가 아니다
    payload = {"opinions": [{"evidence": [ev_gone, ev_keep]}], "evidence": [dict(ev_gone)], "x": not_ev}
    n = _strip_evidence(payload, lambda s: s.startswith("지울 문서"))
    assert n == 2 and payload["opinions"][0]["evidence"] == [ev_keep] and payload["evidence"] == [] and payload["x"] == not_ev


# ═════════════════════════ 호출 기록 · 노드 입출력 ═════════════════════════
def test_scrub_run_traces_keeps_metadata_and_leaves_unrelated_rows(db):
    from nhdip.data.scrub import SCRUBBED, scrub_run_traces
    from nhdip.models import LlmCall, NodeRun, new_id, utcnow

    mark = "스크럽시험전용문장 포용금융 공급확대 세부방안 가나다"
    ids: dict[str, str] = {}
    with db() as s:
        now = utcnow()
        hit = LlmCall(id=new_id(), purpose="chat", model="m", messages=[{"role": "user", "content": f"근거: {mark} 입니다"}], response={"choices": [{"message": {"content": mark}}], "usage": {"total_tokens": 321}},
                      output_text=f"요약 {mark}", prompt_tokens=100, completion_tokens=221, status="ok", created_at=now)
        other = LlmCall(id=new_id(), purpose="chat", model="m", messages=[{"role": "user", "content": "전혀 상관없는 질문입니다"}], output_text="상관없는 답", status="ok", created_at=now)
        old = LlmCall(id=new_id(), purpose="chat", model="m", messages=[{"role": "user", "content": mark}], status="ok", created_at=now - timedelta(days=30))  # 문서가 생기기 전 기록 — 건드리지 않는다
        nr = NodeRun(id=new_id(), workflow_run_id="wrscrub", seq=1, node_key="retrieve", impl="retrieve_evidence", status="succeeded", input={"config": {}}, output={"hits": [{"text": mark}]}, started_at=now)
        nr_other = NodeRun(id=new_id(), workflow_run_id="wrscrub", seq=2, node_key="x", impl="x", status="succeeded", input={}, output={"hits": [{"text": "다른 내용"}]}, started_at=now)
        s.add_all([hit, other, old, nr, nr_other])
        s.commit()
        ids = {"hit": hit.id, "other": other.id, "old": old.id, "nr": nr.id, "nr_other": nr_other.id}
        counts = scrub_run_traces(s, [mark[:40]], now - timedelta(days=1))
        s.commit()
    assert counts == {"llmCalls": 1, "nodeRuns": 1}
    with db() as s:
        h = s.get(LlmCall, ids["hit"])
        assert SCRUBBED in str(h.messages) and h.output_text == SCRUBBED and mark not in str(h.response) and mark not in str(h.messages)
        assert h.response["usage"]["total_tokens"] == 321 and h.prompt_tokens == 100 and h.completion_tokens == 221 and h.status == "ok"  # 메타는 남는다
        assert "상관없는" in str(s.get(LlmCall, ids["other"]).messages)
        assert mark in str(s.get(LlmCall, ids["old"]).messages)
        n = s.get(NodeRun, ids["nr"])
        assert n.output.get("scrubbed") is True and n.status == "succeeded" and n.node_key == "retrieve"
        assert s.get(NodeRun, ids["nr_other"]).output["hits"][0]["text"] == "다른 내용"
        for cls, key in ((LlmCall, "hit"), (LlmCall, "other"), (LlmCall, "old"), (NodeRun, "nr"), (NodeRun, "nr_other")):
            s.delete(s.get(cls, ids[key]))
        s.commit()


# ═════════════════════════ 문서 삭제 → 흔적까지 ═════════════════════════
def test_document_delete_scrubs_traces_and_report_evidence_and_old_generations(db):
    """문서를 지우면 호출 기록 · 노드 입출력의 내용, 산출물의 근거 조각(새 세대로 게시), 그 조각이 든 옛 세대까지 정리된다 — 다른 산출물은 그대로."""
    from nhdip.models import AuditLog, LlmCall, NodeRun, ViewArtifact, new_id, source, utcnow

    c = _admin()
    body = "스크럽종합시험 포용금융 공급 확대를 위해 서민금융 상품군별 한도를 단계적으로 조정하고 취약 차주 보호 방안을 마련한다. " * 6
    r = c.post("/admin/documents/upload", data={"origin": "ext", "doc_class": "reference", "title": "스크럽 종합 시험 문서", "doc_code": "test-scrub-doc", "text": body})
    assert r.status_code == 201, r.text
    doc_id = r.json()["id"]
    key = "report.test-scrub"
    ids: dict[str, str] = {}
    with db() as s:
        t = source("ext")
        chunk = s.execute(select(t.chunk.text).where(t.chunk.document_id == doc_id).order_by(t.chunk.seq)).scalars().first()
        assert chunk
        snippet = chunk[:240]
        now = utcnow()
        evidence = [{"id": "ev-1", "category": "external_policy", "sourceKind": "doc_chunk", "label": "스크럽 종합 시험 문서", "snippet": snippet, "doc": {"title": "스크럽 종합 시험 문서", "page": 1}},
                    {"id": "ev-2", "sourceKind": "doc_chunk", "label": "다른 문서", "snippet": "전혀 다른 문서에서 가져온 근거 조각의 문장입니다 하나둘셋넷", "doc": {"title": "다른"}}]
        def payload(note: str) -> dict:
            return {"title": "스크럽 시험 보고서", "evidence": evidence, "sections": [{"heading": note, "blocks": []}]}
        # 산출물 세대는 문서가 올라온 뒤에 만들어졌다 — 문서가 있기 전의 세대에는 그 문서의 조각이 들어갈 수 없어 정리 대상이 아니다
        s.add_all([
            ViewArtifact(key=key, generation=0, is_current=False, payload=payload("옛 세대"), produced_by="seed", created_at=now + timedelta(seconds=1)),
            ViewArtifact(key=key, generation=1, is_current=True, payload=payload("현재"), produced_by="seed", created_at=now + timedelta(seconds=2)),
            ViewArtifact(key="report.test-scrub-other", generation=0, is_current=True, payload={"title": "무관", "evidence": [evidence[1]]}, produced_by="seed", created_at=now + timedelta(seconds=2)),
            ViewArtifact(key="report.test-scrub-other", generation=-1, is_current=False, payload={"title": "무관 옛 세대", "evidence": [evidence[1]]}, produced_by="seed", created_at=now + timedelta(seconds=1)),
        ])
        # 문서가 생기기 전에 만든 세대 — 같은 조각이 들어 있어도(시험용) 지우지 않는다
        s.add(ViewArtifact(key=key, generation=-1, is_current=False, payload=payload("문서 이전 세대"), produced_by="seed", created_at=now - timedelta(days=400)))
        call = LlmCall(id=new_id(), purpose="chat", model="m", messages=[{"role": "user", "content": f"근거: {chunk[:120]}"}], output_text="답", status="ok", created_at=now)
        nr = NodeRun(id=new_id(), workflow_run_id="wrscrub2", seq=1, node_key="retrieve", impl="retrieve_evidence", status="succeeded", output={"hits": [{"text": chunk[:200]}]}, started_at=now)
        s.add_all([call, nr])
        s.commit()
        ids = {"call": call.id, "nr": nr.id}

    res = c.post(f"/admin/documents/ext/{doc_id}/delete", json={"reason": "흔적 정리 시험"})
    assert res.status_code == 200, res.text
    sc = res.json()["scrubbed"]
    with db() as s:
        gens = [(r.generation, r.is_current, r.produced_by) for r in s.execute(select(ViewArtifact).where(ViewArtifact.key == key).order_by(ViewArtifact.generation)).scalars()]
    assert sc["llmCalls"] >= 1 and sc["nodeRuns"] >= 1 and sc["evidenceRemoved"] == 1 and sc["republished"] == [key], sc
    assert sc["generationsRemoved"] >= 2, (sc, gens)  # 옛 세대(0)와 방금 이전 현재가 된 세대(1)

    with db() as s:
        # 호출 기록 · 노드 입출력: 내용은 지워지고 행(메타)은 남는다
        assert chunk[:60] not in str(s.get(LlmCall, ids["call"]).messages) and s.get(LlmCall, ids["call"]).status == "ok"
        assert s.get(NodeRun, ids["nr"]).output.get("scrubbed") is True
        # 산출물: 새 세대(deletion)에는 지운 문서의 근거가 없고 다른 근거는 그대로, 옛 세대 · 이전 현재 세대는 지워진다
        rows = s.execute(select(ViewArtifact).where(ViewArtifact.key == key).order_by(ViewArtifact.generation)).scalars().all()
        assert [r.generation for r in rows] == [-1, 2]  # 문서 이후 세대(0 · 이전 현재 1)는 지워지고, 문서 이전 세대(-1)와 새 현재 세대(2)만 남는다
        cur = rows[1]
        assert cur.is_current and cur.produced_by == "deletion"
        assert [e["id"] for e in cur.payload["evidence"]] == ["ev-2"] and chunk[:60] not in str(cur.payload)
        # 무관한 산출물은 현재 · 옛 세대 모두 그대로
        other = s.execute(select(ViewArtifact).where(ViewArtifact.key == "report.test-scrub-other")).scalars().all()
        assert len(other) == 2
        a = s.execute(select(AuditLog).where(AuditLog.action == "admin.document.delete", AuditLog.target_id == "ext:test-scrub-doc").order_by(AuditLog.id.desc())).scalars().first()
        assert a.detail["scrubbed"]["evidenceRemoved"] == 1
        # 정리
        s.query(ViewArtifact).filter(ViewArtifact.key.in_([key, "report.test-scrub-other"])).delete(synchronize_session=False)
        s.delete(s.get(LlmCall, ids["call"]))
        s.delete(s.get(NodeRun, ids["nr"]))
        s.commit()


# ═════════════════════════ 데이터셋 삭제 → 옛 산출물 세대 ═════════════════════════
@pytest.fixture()
def lineage(db):
    """데이터셋 → 지표 → 워크플로우 → 산출물(여러 세대) 계보. 시험이 끝나면 지운다."""
    from nhdip.models import Dataset, Metric, ViewArtifact, Workflow, WorkflowRun, utcnow

    ds, wf, art = "TST_SCRUB_DS", "wf_tst_scrub", "tst_scrub_art"
    fig = {"id": "tst_scrub_m", "label": "시험 수치", "unit": "CNT", "value": 7}
    now = utcnow()
    with db() as s:
        s.add(Dataset(code=ds, name="이력 정리 시험", origin="bank", kind="fact", columns=[{"name": "x", "type": "int"}], key_columns=[], quality_rules=[], mapping={}, parser={}))
        s.add(Workflow(code=wf, name="이력 정리 시험", outputs=[art], enabled=True))
        s.flush()
        s.add(Metric(code="tst_scrub_m", label="시험 수치", formula="VALUE", args={"v": {"q": {"dataset": ds, "col": "x", "agg": "sum"}}}, workflow_code=wf, figure_ids=[]))
        for gen, ago, cur in ((0, 5, False), (1, 3, False), (2, 0.5, True)):  # 삭제(1시간 전) 이전 세대 둘 + 삭제 뒤 새 현재 세대
            s.add(ViewArtifact(key=art, generation=gen, is_current=cur, payload={"title": "시험", "kpi": fig}, produced_by=wf, created_at=now - timedelta(hours=ago)))
        s.add(ViewArtifact(key=f"{art}@BR1", generation=0, is_current=False, payload={"kpi": fig}, produced_by=wf, created_at=now - timedelta(hours=4)))  # 범위 실행 산출물
        s.add(ViewArtifact(key="tst_unrelated_art", generation=0, is_current=False, payload={"kpi": {"id": "other_fig", "label": "다른", "unit": "CNT", "value": 1}}, produced_by="seed", created_at=now - timedelta(hours=4)))
        s.commit()
    yield {"ds": ds, "wf": wf, "art": art, "after": now - timedelta(hours=1)}
    with db() as s:
        s.query(WorkflowRun).filter(WorkflowRun.workflow_code == wf).delete(synchronize_session=False)
        s.query(ViewArtifact).filter(ViewArtifact.key.in_([art, f"{art}@BR1", "tst_unrelated_art"])).delete(synchronize_session=False)
        s.query(Metric).filter(Metric.code == "tst_scrub_m").delete(synchronize_session=False)
        s.query(Workflow).filter(Workflow.code == wf).delete(synchronize_session=False)
        s.query(Dataset).filter(Dataset.code == ds).delete(synchronize_session=False)
        s.commit()


def test_artifact_history_waits_for_recompute_then_removes_only_older_generations(db, lineage):
    from nhdip.data.scrub import NotReady, purge_artifact_history
    from nhdip.models import ViewArtifact, WorkflowRun, utcnow

    payload = {"dataset": lineage["ds"], "origin": "bank", "kind": "fact", "after": lineage["after"].isoformat()}
    with db() as s:
        # 삭제 뒤 아직 다시 계산되지 않았다 — 지금 지우면 낡은 현재 세대가 지난 세대로 다시 남으므로 대기
        with pytest.raises(NotReady, match=lineage["wf"]):
            purge_artifact_history(s, payload)
        s.rollback()
        # 실패한 실행은 '다시 계산됨' 이 아니다
        s.add(WorkflowRun(workflow_code=lineage["wf"], status="failed", finished_at=utcnow()))
        s.commit()
        with pytest.raises(NotReady):
            purge_artifact_history(s, payload)
        s.rollback()
        # 삭제 뒤 한 번 끝났다
        s.add(WorkflowRun(workflow_code=lineage["wf"], status="succeeded", finished_at=utcnow() - timedelta(minutes=20)))
        s.commit()
        res = purge_artifact_history(s, payload)
        s.commit()
        assert res["status"] == "done" and res["generations"] == 3 and lineage["art"] in res["artifacts"] and lineage["wf"] in res["workflows"]
        gens = {(r.key, r.generation) for r in s.execute(select(ViewArtifact).where(ViewArtifact.key.in_([lineage["art"], f"{lineage['art']}@BR1", "tst_unrelated_art"]))).scalars()}
        assert gens == {(lineage["art"], 2), ("tst_unrelated_art", 0)}  # 삭제 이전 세대(범위 산출물 포함)만 지워지고 새 현재 세대 · 무관한 산출물은 남는다


def test_artifact_history_gives_up_after_a_day_and_skips_when_no_lineage(db, lineage):
    from nhdip.data.scrub import purge_artifact_history
    from nhdip.models import utcnow

    with db() as s:
        old = {"dataset": lineage["ds"], "origin": "bank", "kind": "fact", "after": (utcnow() - timedelta(hours=26)).isoformat()}
        res = purge_artifact_history(s, old)
        assert res["status"] == "skipped" and lineage["wf"] in res["reason"]
        none = {"dataset": "NO_SUCH_DS", "origin": "bank", "kind": "fact", "after": lineage["after"].isoformat()}
        assert purge_artifact_history(s, none)["status"] == "skipped"


def test_dataset_delete_queues_history_task_with_distinct_reference(db):
    """데이터셋 현재 버전을 지우면 그래프 삭제와 별도로 산출물 이력 정리 작업이 큐에 들어간다(참조 이름이 달라 서로 섞이지 않음)."""
    import io

    from nhdip.models import PurgeTask

    c = _admin()
    code = "TEST_SCRUB_DEL"
    body = {"code": code, "name": "이력 큐 시험", "origin": "bank", "columns": [{"name": "k", "type": "str", "required": True}], "key_columns": ["k"]}
    if c.post("/admin/datasets", json=body).status_code not in (201, 409):
        pytest.fail("데이터셋을 만들지 못했습니다")
    up = c.post(f"/admin/datasets/{code}/upload", data={"origin": "bank", "data_origin": "simulated"}, files={"file": ("a.csv", io.BytesIO("k\na\nb\n".encode()), "text/csv")})
    assert up.status_code == 201, up.text
    out = c.post(f"/admin/datasets/{code}/versions/{up.json()['id']}/delete", json={"reason": "이력 큐 시험"}).json()
    with db() as s:
        tasks = {t.store: t for t in s.execute(select(PurgeTask).where(PurgeTask.id.in_(out["purgeTasks"]))).scalars()}
        assert set(tasks) == {"neo4j", "pg"}
        assert tasks["pg"].subject_ref.endswith("#history") and tasks["pg"].subject_ref.startswith(tasks["neo4j"].subject_ref)
        assert tasks["pg"].payload["dataset"] == code and tasks["pg"].payload["after"]
        # 관련 워크플로우가 없으면 건너뜀(정리할 이력이 없음) — 대기로 남지 않는다
        from nhdip.data.deletion import run_purge_tasks

        run_purge_tasks(s, ids=[tasks["pg"].id])
        s.refresh(tasks["pg"])
        assert tasks["pg"].status == "skipped" and "정리할 이력이 없음" in str(tasks["pg"].result)
