"""수행방안 '영업점 참고' = 영업점 공통 연동 — 켜면 영업본부 · 영업점이 그 수행방안의 연결 자료(연결 분석 보고서 · 근거 문서 · 계산 데이터셋 ·
그래프 연결)를 지금 원장 그대로 쓰고, 끄면 바로 빠지며, 사업부서가 다시 계산하면 새 결과가 그대로 이어진다(복사본 없음).
종합기획부는 고정 부서, 사업부서 안의 부서(신용리스크관리부 등) 이름은 코드가 아니라 구성(화면 · 업무 영역 · 조직)에서 온다."""
from __future__ import annotations

import copy
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import select, text

ADMIN = ("00000001", "Admin1234!")
PW = "abcd1234"
PID = "plan-inclusive-risk"
KEY = "report.inclusive-risk"
QUERY = "포용금융 충당금 비중은 얼마인가요?"


def _client() -> TestClient:
    from nhdip.main import app

    return TestClient(app)


def _login(c: TestClient, emp: str, pw: str) -> None:
    from nhdip import ratelimit

    ratelimit.reset()
    assert c.post("/auth/login", json={"emp_no": emp, "password": pw}).status_code == 200


def _member(admin: TestClient, emp: str, org: str) -> TestClient:
    u = _client()
    u.post("/auth/signup", json={"emp_no": emp, "name": f"공유시험{emp[-2:]}", "password": PW, "org_code": org})
    admin.post(f"/admin/users/{emp}/approve")
    _login(u, emp, PW)
    return u


def _shared(admin: TestClient, on: bool) -> None:
    st = admin.get("/state/plans").json()
    if st["runtime"].get(PID, {}).get("status") != "in_progress":
        admin.post(f"/state/plans/{PID}/register")
        st = admin.get("/state/plans").json()
    if bool(st["runtime"].get(PID, {}).get("branchShared")) != on:
        assert admin.post(f"/state/plans/{PID}/toggle-share").status_code == 200


def _ctx(s, emp: str):
    from nhdip.api.assist import access_context
    from nhdip.models import AppUser

    return access_context(s, s.get(AppUser, emp))


def _granted_chunks(s, emp: str) -> set[str]:
    """그 사용자의 질문하기 사전 필터(kb_filter)로 열리는 연결 보고서 청크의 산출물 키."""
    from nhdip.knowledge.access import kb_filter, resolve_scope

    scope = resolve_scope(s, _ctx(s, emp))
    filt, fp = kb_filter(scope)
    rows = s.execute(text(f"SELECT DISTINCT c.source_key FROM app.kb_chunk c WHERE {filt} AND c.source_key = ANY(CAST(:k AS text[]))"), {**fp, "k": [KEY, "branch_shared_plans"]}).scalars()
    return set(rows)


def test_branch_common_live_link(computed):
    db = computed
    from nhdip.knowledge.access import resolve_scope
    from nhdip.knowledge.search import retrieve
    from nhdip.models import AppUser, KbChunk
    from nhdip.views.plan_share import branch_grant, in_branch_common

    admin = _client()
    _login(admin, *ADMIN)
    admin.post("/state/plans/reset")
    br = _member(admin, "20259381", "001068")  # 영업점
    rg = _member(admin, "20259382", "T311")  # 영업본부(지역본부 팀)
    rk = _member(admin, "20259383", "T211")  # 사업부서(영업점 공통 아님)
    try:
        _shared(admin, False)
        with db() as s:
            assert PID not in branch_grant(s).plans
            assert KEY not in _granted_chunks(s, "20259381")  # 끈 상태 — 영업점은 사업부서 보고서 청크를 못 연다
        assert br.get(f"/screens/plans/{PID}/report").status_code == 404

        # ── 켜기 — 연결 자료 전부가 영업점 공통으로 열린다 ──
        _shared(admin, True)
        with db() as s:
            g = branch_grant(s)
            assert g.plans[PID]["reportKey"] == KEY and g.sources[KEY] == PID and "branch_shared_plans" in g.sources
            assert g.datasets, "연결 보고서를 계산하는 데이터셋(지표 계보)이 연결돼야 한다"
            assert set(g.plans[PID]["datasets"]) == {c for c, p in g.datasets.items() if p == PID}
            for emp in ("20259381", "20259382"):
                assert in_branch_common(s, s.get(AppUser, emp), _ctx(s, emp).resources)
                assert {KEY, "branch_shared_plans"} <= _granted_chunks(s, emp), emp
            assert not in_branch_common(s, s.get(AppUser, "20259383"), _ctx(s, "20259383").resources)
            # 영업점 참고 요약 산출물 — 영업점 공통 컬렉션에, 연결 자료 이름과 함께
            rows = s.execute(select(KbChunk).where(KbChunk.source_key == "branch_shared_plans")).scalars().all()
            assert rows and {r.collection_code for r in rows} == {"analysis.branch_common"}
            assert any("연결 데이터" in r.text for r in rows)
            # 질문하기 — 영업점이 연결 보고서를 찾고, 출처는 '영업점 공통' · 화면 열기는 공유 보고서 화면
            scope = resolve_scope(s, _ctx(s, "20259381"))
            assert "analysis.branch_common" in {c["code"] for c in scope.public()}
            hits = [h for h in retrieve(s, scope, QUERY, user=s.get(AppUser, "20259381")).analysis if h["sourceKey"] == KEY]
            assert hits, "영업점 공통으로 연결 보고서 청크가 검색돼야 한다"
            assert all(h["collectionLabel"].startswith("영업점 공통") and h["href"] == f"/branch/shared/{PID}" and h.get("shared") for h in hits)

        # ── 화면 — 공유 보고서(지금 세대 그대로) · 연결 분석 링크 ──
        r = br.get(f"/screens/plans/{PID}/report")
        assert r.status_code == 200, r.text
        doc = r.json()
        assert doc["sharedPlan"]["id"] == PID and doc["sharedPlan"]["scope"] == "영업점 공통" and doc["workflow"] is None
        # 원본 보고서 그대로(수치 마커 + figures — 화면이 값으로 그린다), 서식 원문(Tpl)은 없다
        assert doc["reportKey"] == KEY and doc["analysisFrom"] and doc["opinions"] and doc["figures"] and "Tpl" not in "".join(doc["opinions"][0])
        assert rg.get(f"/screens/plans/{PID}/report").status_code == 200  # 영업본부도
        assert rk.get(f"/screens/plans/{PID}/report").status_code == 403  # 영업점 공통이 아닌 사업부서 사용자
        la = br.get(f"/screens/plans/{PID}/linked-analysis").json()
        assert la["analysis"]["tabKey"] == "inclusive-risk" and la["href"] == f"/branch/shared/{PID}"
        assert admin.get(f"/screens/plans/{PID}/linked-analysis").json()["href"].endswith("/inclusive-risk")  # 부서 보고서 화면을 열 수 있으면 그 화면

        # ── 다시 계산 — 같은 키의 새 세대가 그대로 이어진다(내려 줄 것 없음) ──
        from nhdip.knowledge.indexer import index_artifacts
        from nhdip.views.plan_share import refresh_if_linked
        from nhdip.views.store import get_current, get_current_row, publish

        with db() as s:
            orig = copy.deepcopy(get_current_row(s, KEY).payload)
        try:
            with db() as s:
                publish(s, KEY, {**orig, "title": f"{orig['title']} (재계산 시험)"}, produced_by="test")
                s.flush()
                index_artifacts(s, [KEY])
                assert refresh_if_linked(s, [KEY], "test") is True
                s.commit()
                items = get_current(s, "branch_shared_plans")
                assert any((it.get("analysis") or {}).get("title", "").endswith("(재계산 시험)") for it in items)
            assert br.get(f"/screens/plans/{PID}/report").json()["title"].endswith("(재계산 시험)")
        finally:
            with db() as s:
                publish(s, KEY, orig, produced_by="test")
                s.flush()
                index_artifacts(s, [KEY])
                refresh_if_linked(s, [KEY], "test")
                s.commit()

        # ── 끄기 — 바로 빠진다 ──
        _shared(admin, False)
        with db() as s:
            assert KEY not in _granted_chunks(s, "20259381")
            assert PID not in branch_grant(s).plans
        assert br.get(f"/screens/plans/{PID}/report").status_code == 404
    finally:
        admin.post("/state/plans/reset")


def test_branch_common_docs_data_graph(computed):
    db = computed
    from nhdip.graph.evidence import doc_visible
    from nhdip.graph.projection import collect_graph
    from nhdip.knowledge.access import AccessContext
    from nhdip.knowledge.assist_tools import build, can_aggregate, data_aggregate
    from nhdip.models import Dataset, OutboxEvent
    from nhdip.views.plan_share import branch_grant, doc_codes
    from nhdip.workflow.dispatcher import match_event

    admin = _client()
    _login(admin, *ADMIN)
    admin.post("/state/plans/reset")
    try:
        _shared(admin, True)
        with db() as s:
            g = branch_grant(s)
            assert PID in g.plans
            # 근거 문서 — 근거 항목의 문서 코드(옛 근거는 구간 참조로)
            assert doc_codes(s, [{"evidence": [{"doc": {"docCode": "DOC-A"}}, {"doc": {"title": "x"}, "chunkRef": {"origin": "bank", "chunkId": -1}}]}]) == {"DOC-A"}
            branch = SimpleNamespace(role="user", org_code="001068", emp_no="t")
            meta = {"accessClass": "dept_only"}
            assert doc_visible(s, branch, "DOC-SHARED", meta)[0] is False
            assert doc_visible(s, branch, "DOC-SHARED", meta, grant={"DOC-SHARED"})[0] is True
            # 데이터 — 데이터셋 화면 권한 없이도 연결 데이터셋만 집계(행 원문 없이)
            code = sorted(g.datasets)[0]
            other = next(d.code for d in s.execute(select(Dataset).where(Dataset.active)).scalars() if d.code not in g.datasets)
            ctx = AccessContext(emp_no="t", resources={"branch_targets"}, grant_datasets=dict(g.datasets))
            assert can_aggregate(ctx) and not can_aggregate(AccessContext(emp_no="t", resources={"branch_targets"}))
            assert "영업점 공통" in data_aggregate(s, ctx, other, "count")["error"]
            out = data_aggregate(s, ctx, code, "count")
            assert "error" not in out and out["dataset"] == code, out
            tool = next(t for t in build(s, ctx).schemas if t["function"]["name"] == "data_aggregate")
            assert code in tool["function"]["description"]
            # 그래프 — 수행방안 노드 → 연결 보고서 · 데이터셋 (스키마 판과 상관없이 플랫폼 연결)
            b = collect_graph(s)
            assert PID in b.nodes.get(("Plan",), {}) and b.nodes[("Plan",)][PID]["scope"] == "branch_common"
            assert any(r["from"] == PID and r["to"] == KEY for r in b.rels.get(("LINKED_TO", "Plan", "Artifact"), []))
            assert {r["to"] for r in b.rels.get(("USES_DATA", "Plan", "Dataset"), [])} & set(g.datasets)
            assert not any(x.startswith(("label:Plan", "rel:LINKED_TO", "rel:USES_DATA", "rel:EVIDENCED_BY")) for x in b.rejected)
            # 켜기 · 끄기 이벤트 — 영업점 흐름 + 그래프 투영
            wfs = match_event(s, OutboxEvent(id=0, type="plan.branch_shared", payload={"plan": PID, "title": "시험"}))
            assert "wf_graph_projection" in wfs and "wf_branch_kpi" in wfs, wfs
            # 원본 문서 뷰어 — 연결 보고서가 인용한 근거 문서
            assert g.docs, "연결 보고서의 근거 문서(근거 붙이기)가 연결돼야 한다"
            linked = sorted(g.docs)[0]
            from nhdip.models import source as src

            unlinked = next((d for o in ("bank", "ext") for d in s.execute(select(src(o).document.doc_code).where(src(o).document.is_current)).scalars() if d not in g.docs), None)
        br = _member(admin, "20259384", "001068")
        with db() as s:
            limited = "documents" not in (_ctx(s, "20259384").resources or set())
        assert br.get("/documents/view", params={"id": linked}).status_code == 200
        if limited:  # 문서 화면 권한이 없는 영업점 — 연결 문서만, 나머지는 있든 없든 같은 답
            if unlinked:
                assert br.get("/documents/view", params={"id": unlinked}).status_code == 403
            assert br.get("/documents/view", params={"id": "NO-SUCH-DOC"}).status_code == 403
        _shared(admin, False)
        if limited:
            assert br.get("/documents/view", params={"id": linked}).status_code == 403  # 끄면 바로 닫힌다
    finally:
        admin.post("/state/plans/reset")


def test_department_names_come_from_config(db):
    """사업부서 공간 이름은 조직 구성에서(신용리스크관리부를 코드에 두지 않는다), 종합기획부는 고정 — 신설 목표 담당 기본값."""
    from nhdip.analysis_registry import DEFAULT_SPACES, spaces
    from nhdip.models import OrgUnit
    from nhdip.views.cascade import build_tree

    # 종합기획부는 고정 부서, 사업부서 공간(신용리스크관리부 등)은 코드에 부서 이름을 두지 않는다
    assert DEFAULT_SPACES["hq"]["label"] == "종합기획부" and DEFAULT_SPACES["risk"]["label"] == "사업부서"
    with db() as s:
        org = s.get(OrgUnit, "D200")
        assert spaces(s)["risk"]["label"] == org.name
        org.name = "리스크관리부(시험)"
        s.flush()
        assert spaces(s)["risk"]["label"] == "리스크관리부(시험)"  # 조직 이름을 바꾸면 따라 바뀐다
        s.rollback()
    added = {"addedGoals": [{"id": "goal-x", "title": "시험 목표", "targetLabel": "1%"}]}
    assert build_tree([], [], added, [], hq_org="기획부(시험)")[-1]["org"] == "기획부(시험)"
    assert build_tree([], [], added, [])[-1]["org"] == "종합기획부"
