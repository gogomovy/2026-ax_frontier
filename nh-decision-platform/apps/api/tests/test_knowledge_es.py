"""질문하기 선택 검색 엔진(Elasticsearch) — 설계 §21.18.

ES 없이 도는 시험(가짜 전송): 접근 규칙 변환 · 목록 대조 · 차단기 · 폴백 · PostgreSQL 재확인(권한 누수 0).
실제 ES 가 있어야 도는 시험(`ES_URL` 환경 변수가 있을 때만): 동기화 · 접근 규칙 SQL ↔ ES 동치 · 의미 · 키워드 채널 · 지워진 청크 · 새 청크 보충.
"""
from __future__ import annotations

import json
import os
import uuid

import httpx
import pytest
from sqlalchemy import delete, text

from nhdip.knowledge import elastic
from nhdip.knowledge.access import AccessContext, AccessScope, kb_filter
from test_knowledge import _admin, _admin_scope, _ask, _fake_vec, _restore_setting, _set_setting, _user, fake_embedder  # noqa: F401 — fake_embedder 는 픽스처

ES_LIVE = pytest.mark.skipif(not os.environ.get("ES_URL"), reason="ES_URL 없음 — 실제 Elasticsearch 가 있어야 하는 시험")


def _scope(admin=False, full=("a",), gated=(), resources=("r1",), offices=None):
    ctx = AccessContext(emp_no="1", is_admin=admin, org_codes={"D100"}, resources=None if admin else set(resources), offices=offices, dept_docs=None)
    return AccessScope(ctx=ctx, collections={}, full=list(full), gated=list(gated), owned=set(), doc_classes=None)


def _client(handler) -> httpx.Client:
    return httpx.Client(base_url="http://es.test", transport=httpx.MockTransport(handler))


@pytest.fixture()
def es_clean():
    """차단기 · 클라이언트를 시험 전후로 되돌린다."""
    elastic.reset_breaker()
    elastic.set_client(None)
    yield
    elastic.reset_breaker()
    elastic.set_client(None)


# ═════════════════════════ 단위 — ES 없이 ═════════════════════════
def test_es_filter_mirrors_sql_filter_shape():
    adm = elastic.es_filter(_scope(admin=True, full=("a", "b")))
    assert adm == {"bool": {"filter": [{"bool": {"should": [{"terms": {"collection_code": ["a", "b"]}}], "minimum_should_match": 1}}]}}  # 관리자 — 지점 범위 없음
    sc = elastic.es_filter(_scope(full=("a",), gated=("g",), resources=("r2", "r1"), offices={"009902", "009901"}))
    flt = sc["bool"]["filter"]
    should = flt[0]["bool"]["should"]
    assert should[0] == {"terms": {"collection_code": ["a"]}}
    assert should[1] == {"bool": {"filter": [{"terms": {"collection_code": ["g"]}}, {"terms": {"required_resource": ["r1", "r2"]}}]}}  # 화면 리소스는 정렬
    office = flt[1]["bool"]["should"]
    assert office[1] == {"terms": {"scope_key": ["office:009901", "office:009902"]}} and "exists" in json.dumps(office[0])  # 범위 없는 청크 ∪ 내 지점
    # 화면 리소스가 하나도 없으면 청크 단위 열람 컬렉션은 아예 조건에서 빠진다(SQL kb_filter 와 같음)
    none = elastic.es_filter(_scope(full=("a",), gated=("g",), resources=()))["bool"]["filter"][0]["bool"]["should"]
    assert len(none) == 1


def test_diff_uploads_changed_or_missing_and_deletes_vanished():
    pg = {1: ("h1", "m"), 2: ("h2", ""), 3: ("h3", "m"), 5: ("h5", "")}
    es = {1: ("h1", "m"), 2: ("h2", "m"), 3: ("old", "m"), 4: ("h4", "")}
    up, dele = elastic.diff(pg, es)
    assert up == [2, 3, 5]  # 임베딩 모델 달라짐 · 내용 달라짐 · ES 에 없음
    assert dele == [4]  # PG 에서 사라짐
    assert elastic.diff({}, {}) == ([], [])


def test_index_body_uses_nori_and_falls_back_to_standard():
    nori = elastic.index_body("nori")
    assert "nori_tokenizer" in json.dumps(nori["settings"]["analysis"])
    std = elastic.index_body("standard")
    assert "nori" not in json.dumps(std) and std["mappings"]["properties"]["text"]["analyzer"] == "ko"
    assert nori["mappings"]["dynamic"] == "strict"  # 모르는 필드는 거절 — 매핑이 슬그머니 늘지 않게
    assert set(nori["mappings"]["_source"]["excludes"]) >= {"text", "title", "embedding"}  # 본문 · 벡터의 원본은 PostgreSQL


def test_breaker_backs_off_exponentially_and_recovers(es_clean, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(elastic.time, "monotonic", lambda: now[0])
    assert elastic.es_up()
    elastic.mark_down()
    assert not elastic.es_up()
    now[0] += 31
    assert elastic.es_up()  # 30초 뒤 다시 시도
    elastic.mark_down()
    now[0] += 31
    assert not elastic.es_up()  # 두 번째는 60초
    now[0] += 30
    assert elastic.es_up()
    for _ in range(10):
        elastic.mark_down()
    now[0] += 299
    assert not elastic.es_up()  # 상한 300초
    now[0] += 2
    assert elastic.es_up()
    elastic.mark_down()
    elastic.mark_ok()
    assert elastic.es_up()


def test_request_maps_errors_to_unavailable_and_trips_breaker(es_clean):
    def boom(req):
        raise httpx.ConnectError("refused")

    elastic.set_client(_client(boom))
    with pytest.raises(elastic.EsUnavailable):
        elastic.request("GET", "/_cluster/health")
    assert not elastic.es_up()
    elastic.reset_breaker()
    elastic.set_client(_client(lambda r: httpx.Response(503, text="overloaded")))
    with pytest.raises(elastic.EsUnavailable):
        elastic.request("GET", "/x")
    assert not elastic.es_up()
    elastic.reset_breaker()
    elastic.set_client(_client(lambda r: httpx.Response(400, text='{"error":"bad"}')))
    with pytest.raises(elastic.EsError) as ei:  # 4xx 는 설정 · 매핑 문제 — 차단기를 열지 않는다
        elastic.request("GET", "/x")
    assert ei.value.status == 400 and elastic.es_up()


def test_keyword_hits_names_each_stem_and_counts_matched(es_clean):
    seen = {}

    def handler(req):
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={"hits": {"hits": [{"_id": "7", "_score": 3.5, "matched_queries": ["s0", "s2"]}, {"_id": "9", "_score": 1.0, "matched_queries": ["s1"]}]}})

    elastic.set_client(_client(handler))
    got = elastic.keyword_hits(_scope(admin=True), ["부도율", "소기업", "등급"], 3, size=10, min_ratio=0.34)
    assert got == [(7, 3.5, 2), (9, 1.0, 1)]  # 맞춘 어절 수 = 이름 붙은 절 중 맞은 개수
    q = seen["body"]["query"]["bool"]
    assert q["minimum_should_match"] == 2 and [c["multi_match"]["_name"] for c in q["should"]] == ["s0", "s1", "s2"]  # ceil(3 × 0.34)
    assert q["filter"] and seen["body"]["_source"] is False
    assert elastic.keyword_hits(_scope(admin=True), [], 0, size=10, min_ratio=0.34) == []
    assert elastic.keyword_hits(_scope(admin=True), ["a"], 4, size=10, min_ratio=0.5) == []  # 최소 어절 수에 못 미치면 묻지도 않는다


def test_vector_hits_converts_score_to_cosine_distance(es_clean):
    def handler(req):
        body = json.loads(req.content)
        assert body["knn"]["filter"]["bool"]["filter"][1] == {"term": {"embedding_model": "m1"}}  # 같은 모델의 임베딩만
        return httpx.Response(200, json={"hits": {"hits": [{"_id": "3", "_score": 1.0}, {"_id": "4", "_score": 0.75}, {"_id": "5", "_score": 0.5}]}})

    elastic.set_client(_client(handler))
    got = dict(elastic.vector_hits(_scope(admin=True), [0.1, 0.2], "m1", k=3))
    assert got[3] == pytest.approx(0.0) and got[4] == pytest.approx(0.5) and got[5] == pytest.approx(1.0)  # 거리 = 2 − 2 × 점수


def test_ensure_index_falls_back_to_standard_analyzer_when_nori_is_missing(es_clean, monkeypatch):
    monkeypatch.setattr(elastic, "index_name", lambda: "idx-test")
    created = []

    def handler(req):
        if req.method == "HEAD":
            return httpx.Response(404)
        body = json.loads(req.content)
        if "nori_tokenizer" in json.dumps(body):
            return httpx.Response(400, json={"error": {"reason": "Unknown tokenizer type [nori_tokenizer] for [ko_tokenizer]"}})
        created.append(body)
        return httpx.Response(200, json={"acknowledged": True})

    elastic.set_client(_client(handler))
    assert elastic.ensure_index() == "standard"  # nori 플러그인이 없으면 standard 로 색인을 만든다(경고만)
    assert len(created) == 1 and "nori" not in json.dumps(created[0])


def test_cli_kb_es_requires_configuration(monkeypatch, capsys):
    from nhdip import cli

    monkeypatch.setattr(elastic, "configured", lambda: False)
    assert cli.main(["kb-es"]) == 2 and "ES_URL" in capsys.readouterr().err


# ═════════════════════════ 통합(PostgreSQL) — 가짜 ES 로 검색 경로 ═════════════════════════
def _scope_for(db, emp: str):
    from nhdip.api.assist import access_context
    from nhdip.knowledge.access import resolve_scope
    from nhdip.models import AppUser

    with db() as s:
        return resolve_scope(s, access_context(s, s.get(AppUser, emp)))


def _use_es(db, monkeypatch, handler, *, synced: int | None, dims: int | None = None):
    """검색 설정을 es 로, ES 응답을 handler 로 — 동기화 상태를 직접 심는다. 돌려주는 값 = 되돌릴 설정."""
    monkeypatch.setattr(elastic, "configured", lambda: True)
    elastic.reset_breaker()
    elastic.set_client(_client(handler))
    before = _set_setting(db, "knowledge.search", {"backend": "es"})
    with db() as s:
        elastic._save_state(s, synced_max_id=synced, dims=dims)
        s.commit()
    return before


def _drop_state(db):
    from nhdip.models import Setting

    with db() as s:
        st = s.get(Setting, elastic.STATE_KEY)
        if st is not None:
            s.delete(st)
        s.commit()


def test_es_hits_are_rechecked_against_postgres_so_stale_acl_cannot_leak(db, es_clean, monkeypatch):
    """ES 가 (색인의 권한 필드가 낡아서) 다른 팀 청크 · 지워진 청크의 id 를 돌려줘도 PostgreSQL 재확인에서 사라진다 — 설계 §21.18 핵심 불변식."""
    from nhdip.knowledge.search import _kb_keyword_es

    admin = _admin()
    _user(admin, "20269103", "BR301")
    branch = _scope_for(db, "20269103")
    with db() as s:
        risk_ids = [int(i) for i in s.execute(text("SELECT id FROM app.kb_chunk WHERE collection_code = 'analysis.risk' ORDER BY id LIMIT 3")).scalars()]
        ok_ids = [int(i) for i in s.execute(text("SELECT id FROM app.kb_chunk WHERE collection_code = 'analysis.branch' AND scope_key IS NULL ORDER BY id LIMIT 2")).scalars()]
        assert risk_ids and ok_ids
        # 영업점이 볼 수 없는 청크가 ES 응답에 섞여 있다(+ 존재하지 않는 id)
        ids = [*risk_ids, 987654321, *ok_ids]
        handler = lambda req: httpx.Response(200, json={"hits": {"hits": [{"_id": str(i), "_score": 5.0 - n, "matched_queries": ["s0"]} for n, i in enumerate(ids)]}})  # noqa: E731
        elastic.set_client(_client(handler))
        diag: dict = {}
        rows = _kb_keyword_es(s, branch, ["부도율"], 40, 60, 0.34, diag)
        got = [r["chunk_id"] for r in rows]
        assert sorted(got) == sorted(ok_ids), got  # 내 컬렉션 청크만 남는다
        assert not set(got) & set(risk_ids)
        assert diag["es"]["kb_keyword"] == {"hits": len(ids), "kept": len(ok_ids)}
        assert all(r["raw"] >= 1.0 and int(r["sig"]["keyword_score"]) == 1 for r in rows)  # 정수부 = 맞춘 어절 수 (게이팅 척도)
        # 의미 채널도 같다
        from nhdip.knowledge.search import _kb_vector_es

        vh = lambda req: httpx.Response(200, json={"hits": {"hits": [{"_id": str(i), "_score": 0.9} for i in ids]}})  # noqa: E731
        elastic.set_client(_client(vh))
        vrows = _kb_vector_es(s, branch, [0.1] * 4, "m", 40, 60, diag)
        assert sorted(r["chunk_id"] for r in vrows) == sorted(ok_ids)
        assert all(r["sig"]["cosine_distance"] == pytest.approx(0.2, abs=1e-3) for r in vrows)  # 2 − 2 × 0.9


def test_es_down_falls_back_to_postgres_with_same_answers(db, es_clean, monkeypatch):
    from nhdip.knowledge.search import retrieve

    q = "소기업 6B 등급 실제부도율은 예측 대표값 대비 어떤가요?"
    with db() as s:
        base = retrieve(s, _admin_scope(s), q)
    assert base.diagnostics["backend"] == "pg" and "esFallback" not in base.diagnostics  # 기본 설정 — ES 를 건드리지 않는다

    def boom(req):
        raise httpx.ConnectError("refused")

    before = _use_es(db, monkeypatch, boom, synced=0)
    try:
        with db() as s:
            r1 = retrieve(s, _admin_scope(s), q)
        assert r1.diagnostics["backend"] == "pg" and "kb_keyword" in r1.diagnostics["esFallback"]
        assert [(h["source_key"], h["chunk_id"]) for h in r1.analysis] == [(h["source_key"], h["chunk_id"]) for h in base.analysis]  # 폴백해도 답은 같다
        assert not elastic.es_up()  # 차단기가 열렸다
        with db() as s:
            r2 = retrieve(s, _admin_scope(s), q)
        assert "차단기" in r2.diagnostics["esFallback"] and [h["chunk_id"] for h in r2.analysis] == [h["chunk_id"] for h in base.analysis]
        with db() as s:  # 동기화 상태가 없으면(한 번도 올리지 않았으면) ES 를 믿지 않는다
            elastic.reset_breaker()
            elastic._save_state(s, synced_max_id=None)
            s.commit()
            r3 = retrieve(s, _admin_scope(s), q)
        assert r3.diagnostics["backend"] == "pg" and "동기화 전" in r3.diagnostics["esFallback"]
    finally:
        _restore_setting(db, "knowledge.search", before)
        _drop_state(db)


def test_new_chunks_not_yet_in_es_are_found_through_postgres_supplement(db, es_clean, monkeypatch):
    """게시 직후 — ES 에 아직 안 올라간 청크(id > synced_max_id)는 PostgreSQL 이 보충한다(KB-01: 게시 직후에도 검색에 잡힘)."""
    from nhdip.knowledge.search import retrieve

    q = "소기업 6B 등급 실제부도율은 예측 대표값 대비 어떤가요?"
    empty = lambda req: httpx.Response(200, json={"hits": {"hits": []}})  # noqa: E731  — ES 는 아무것도 못 찾는다
    with db() as s:
        base = retrieve(s, _admin_scope(s), q)
        mx = int(s.execute(text("SELECT max(id) FROM app.kb_chunk")).scalar())
    assert base.analysis
    before = _use_es(db, monkeypatch, empty, synced=mx, dims=None)
    try:
        with db() as s:
            r_all_synced = retrieve(s, _admin_scope(s), q)
        assert r_all_synced.diagnostics["backend"] == "es"
        assert r_all_synced.diagnostics["candidates"]["kb_keyword"] == 0  # 전부 동기화됐다고 보면 ES 가 빈손일 때 PG 보충도 없다
        with db() as s:
            elastic._save_state(s, synced_max_id=0)  # 아무것도 못 올렸다고 보면 전체를 PG 가 보충
            s.commit()
            r_none_synced = retrieve(s, _admin_scope(s), q)
        assert r_none_synced.diagnostics["backend"] == "es" and r_none_synced.diagnostics["es"]["kb_keyword"]["supplement"] > 0
        assert [h["chunk_id"] for h in r_none_synced.analysis] == [h["chunk_id"] for h in base.analysis]
    finally:
        _restore_setting(db, "knowledge.search", before)
        _drop_state(db)


def test_retrieval_view_reports_backend_actually_used(db, es_clean, monkeypatch):
    admin = _admin()
    r = _ask(admin, "포용금융 충당금 비중은 얼마인가요?")
    assert r["retrieval"]["backend"] == "pg"


def test_search_backend_is_visible_to_admin_and_preflight(db, es_clean, monkeypatch):
    monkeypatch.setattr(elastic, "configured", lambda: False)  # ES_URL 이 있는 환경에서 돌려도 '설정 안 함' 경로를 시험
    admin = _admin()
    st = admin.get("/admin/knowledge/status").json()["searchBackend"]
    assert st["setting"] == "pg" and st["configured"] is False  # 기본 — ES 를 쓰지 않으면 연결 확인도 하지 않는다
    assert not any(i["key"] == "search_backend" for i in admin.get("/admin/readiness").json()["items"])  # 쓰지 않으면 항목 자체가 없다
    before = _set_setting(db, "knowledge.search", {"backend": "es"})
    try:
        items = {i["key"]: i for i in admin.get("/admin/readiness").json()["items"]}
        assert items["search_backend"]["level"] == "warn" and "ES_URL" in items["search_backend"]["message"]  # es 로 정했는데 주소가 없다
    finally:
        _restore_setting(db, "knowledge.search", before)


# ═════════════════════════ 실제 ES ═════════════════════════
@pytest.fixture()
def live(db, monkeypatch, es_clean):
    """시험마다 겹치지 않는 색인 이름 — 끝나면 색인 · 동기화 상태 · 검색 설정을 원래대로."""
    name = f"nhdip-kb-test-{uuid.uuid4().hex[:8]}"
    monkeypatch.setattr(elastic, "index_name", lambda: name)
    before = _set_setting(db, "knowledge.search", {"backend": "pg"})
    _drop_state(db)
    yield name
    try:
        elastic.request("DELETE", f"/{name}", ok=(200, 404))
    except elastic.EsUnavailable:
        pass
    _restore_setting(db, "knowledge.search", before)
    _drop_state(db)
    with db() as s:
        s.execute(text("UPDATE app.kb_chunk SET embedding = NULL, embedding_model = NULL"))
        s.commit()


def _es_ids(scope) -> set[int]:
    r = elastic.request("POST", f"/{elastic.index_name()}/_search", json_body={"size": 10000, "_source": False, "track_total_hits": False, "query": elastic.es_filter(scope)})
    return {int(h["_id"]) for h in r["hits"]["hits"]}


@ES_LIVE
def test_live_sync_is_idempotent_and_access_filter_equals_sql(db, live):
    """접근 규칙을 SQL(kb_filter)과 ES(es_filter)에서 같은 결과로 — 관리자 · 본부 · 신용리스크 · 영업점(지점 범위) · 지역본부."""
    admin = _admin()
    for emp, org in (("20269101", "T121"), ("20269102", "T211"), ("20269111", "BR301"), ("20269113", "D300")):
        _user(admin, emp, org)
    with db() as s:
        out = elastic.sync(s, limit=10**9, force=True)
        s.commit()
        total = int(s.execute(text("SELECT count(*) FROM app.kb_chunk")).scalar())
        assert out["failed"] == 0 and out["indexed"] == total and out["pending"] == 0, out
        again = elastic.sync(s, force=True)
        assert again["indexed"] == 0 and again["deleted"] == 0  # 멱등 — 목록이 같으면 아무것도 안 올린다
        assert elastic.synced_max_id(s) == int(s.execute(text("SELECT max(id) FROM app.kb_chunk")).scalar())
    for emp in (None, "20269101", "20269102", "20269111", "20269113"):
        with db() as s:
            scope = _admin_scope(s) if emp is None else _scope_for(db, emp)
            filt, fp = kb_filter(scope)
            sql_ids = {int(i) for i in s.execute(text(f"SELECT c.id FROM app.kb_chunk c WHERE {filt}"), fp).scalars()}
        assert sql_ids, emp
        assert _es_ids(scope) == sql_ids, f"{emp}: SQL {len(sql_ids)}건 ≠ ES {len(_es_ids(scope))}건"
    # 서로 다른 팀의 범위는 실제로 다르다(위 동치가 '전부 같은 집합' 이라서 통과한 것이 아님)
    sets = [_es_ids(_scope_for(db, e)) for e in ("20269101", "20269102", "20269111")]
    assert len({frozenset(x) for x in sets}) == 3


@ES_LIVE
def test_live_status_rebuild_and_cli(db, live, capsys):
    from nhdip import cli

    with db() as s:
        elastic.sync(s, limit=10**9, force=True)
        s.commit()
        total = int(s.execute(text("SELECT count(*) FROM app.kb_chunk")).scalar())
        st = elastic.status(s)
    assert st["up"] and st["es_docs"] == st["pg_chunks"] == total and st["lag"] == 0 and st["state"]["analyzer"] == "nori"
    with db() as s:
        rb = elastic.rebuild(s)  # 색인을 지우고 처음부터 — 차원 · 분석기가 바뀐 뒤의 복구 경로
        s.commit()
    assert rb["indexed"] == total and rb["failed"] == 0 and rb["pending"] == 0
    capsys.readouterr()
    assert cli.main(["kb-es"]) == 0
    assert json.loads(capsys.readouterr().out)["es_docs"] == total
    assert cli.main(["kb-es", "--sync"]) == 0
    assert json.loads(capsys.readouterr().out)["indexed"] == 0  # 이미 같다 — 멱등


@ES_LIVE
def test_live_keyword_and_isolation_with_es_backend(db, live):
    """검색 설정을 es 로 바꾼 뒤에도 팀 격리 · 지점 격리 단언이 그대로 성립한다(기존 시험을 그대로 재사용)."""
    import test_knowledge as tk

    with db() as s:
        elastic.sync(s, limit=10**9, force=True)
        s.commit()
    _set_setting(db, "knowledge.search", {"backend": "es"})
    tk.test_team_isolation_in_assist(db)
    tk.test_branch_scope_is_isolated_by_office(db)
    from nhdip.knowledge.search import retrieve

    with db() as s:
        ret = retrieve(s, _admin_scope(s), "소기업 6B 등급 실제부도율은 예측 대표값 대비 어떤가요?")
    assert ret.diagnostics["backend"] == "es" and "esFallback" not in ret.diagnostics, ret.diagnostics
    assert ret.analysis and ret.diagnostics["candidates"]["kb_keyword"] > 0


@ES_LIVE
def test_live_golden_set_passes_with_es_backend(db, live):
    """프로젝트의 품질 관문(골든셋 — 팀별 질문하기 범위 포함)을 검색 엔진만 ES 로 바꿔 그대로 통과한다."""
    import test_golden as tg
    from nhdip.evals import run

    tg._drain(db)
    with db() as s:
        elastic.sync(s, limit=10**9, force=True)
        s.commit()
    _set_setting(db, "knowledge.search", {"backend": "es"})
    count = lambda: int(elastic.request("GET", f"/{elastic.index_name()}/_stats/search")["_all"]["primaries"]["search"]["query_total"])  # noqa: E731
    before = count()
    with db() as s:
        rep = run(s)
    assert count() > before  # 골든셋의 질문하기 사례가 실제로 ES 를 거쳤다
    bad = {k: v["failures"] for k, v in rep["categories"].items() if not v["ok"]}
    assert rep["passed"], bad
    assert rep["categories"]["knowledge"]["total"] >= 4


@ES_LIVE
def test_live_vector_channel_matches_postgres_top_hits(db, live, fake_embedder):
    from nhdip.knowledge.maintenance import embed_pending
    from nhdip.knowledge.search import _kb_vector, _kb_vector_es

    with db() as s:
        assert embed_pending(s, limit=100_000)["embedded"] > 0
        s.commit()
        out = elastic.sync(s, limit=10**9, force=True)
        s.commit()
        assert out["failed"] == 0 and elastic.search_state(s)["dims"] == 32
        scope = _admin_scope(s)
        for q in ("소기업 부도율 대표값", "포용금융 충당금 비중", "지점 업적평가 점수", "기업여신 증가율 목표 이탈"):
            qv = _fake_vec(q)
            pg = _kb_vector(s, scope, qv, "fake-emb", None, 10)
            es = _kb_vector_es(s, scope, qv, "fake-emb", 10, 60, {})
            assert pg and es
            assert {r["chunk_id"] for r in pg[:3]} & {r["chunk_id"] for r in es[:5]}, q  # 가까운 청크가 겹친다(ES 는 근사)
            assert es[0]["raw"] == pytest.approx(pg[0]["raw"], abs=0.02) or es[0]["raw"] <= pg[0]["raw"] + 0.02  # 거리 환산이 맞다


@ES_LIVE
def test_live_deleted_chunk_in_postgres_vanishes_even_though_es_is_stale(db, live):
    from nhdip.knowledge.search import _kb_keyword_es

    with db() as s:
        elastic.sync(s, limit=10**9, force=True)
        s.commit()
        scope = _admin_scope(s)
        rows = _kb_keyword_es(s, scope, ["부도율", "소기업"], 40, 60, 0.34, {})
        assert rows
        gone = rows[0]["chunk_id"]
        s.execute(text("DELETE FROM app.kb_chunk WHERE id = :i"), {"i": gone})  # PG 에서만 지움(ES 는 다음 동기화 전까지 낡음)
        assert gone in {h[0] for h in elastic.keyword_hits(scope, ["부도율", "소기업"], 2, size=60, min_ratio=0.34)}  # ES 는 아직 안다
        assert gone not in {r["chunk_id"] for r in _kb_keyword_es(s, scope, ["부도율", "소기업"], 40, 60, 0.34, {})}  # 그래도 결과에는 없다
        s.rollback()


@ES_LIVE
def test_live_new_chunk_is_searchable_before_sync_then_synced_and_removed(db, live, monkeypatch):
    from nhdip.knowledge.indexer import index_artifacts
    from nhdip.knowledge.search import retrieve
    from nhdip.models import KbChunk, ViewArtifact
    from nhdip.views.store import publish

    key = "report.test-es-new"
    with db() as s:
        elastic.sync(s, limit=10**9, force=True)
        s.commit()
    _set_setting(db, "knowledge.search", {"backend": "es"})
    try:
        with db() as s:
            publish(s, key, {"title": "ES 시험 보고", "asOf": "2026-08-31", "sections": [{"heading": "x", "blocks": [{"type": "p", "text": "쿼츠미러 라이브러리 정합성 점검 결과가 정상입니다. 충분히 길게 씁니다."}]}]}, produced_by="test")
            s.flush()
            index_artifacts(s, [key])
            s.commit()
        with db() as s:
            ret = retrieve(s, _admin_scope(s), "쿼츠미러 라이브러리 정합성")
            assert any(h["source_key"] == key for h in ret.analysis), ret.diagnostics  # 동기화 전이어도 PG 보충으로 잡힌다
            assert ret.diagnostics["es"]["kb_keyword"]["supplement"] >= 1
            out = elastic.sync(s, force=True)
            s.commit()
            assert out["indexed"] >= 1
            ret2 = retrieve(s, _admin_scope(s), "쿼츠미러 라이브러리 정합성")
            assert any(h["source_key"] == key for h in ret2.analysis) and "supplement" not in ret2.diagnostics.get("es", {}).get("kb_keyword", {})  # 이제 ES 가 직접
    finally:
        with db() as s:
            s.execute(delete(KbChunk).where(KbChunk.source_key == key))
            s.execute(delete(ViewArtifact).where(ViewArtifact.key == key))
            s.commit()
    with db() as s:
        out = elastic.sync(s, force=True)  # 사라진 청크는 ES 에서도 지운다
        s.commit()
        assert out["deleted"] >= 1


@ES_LIVE
def test_live_es_outage_mid_flight_falls_back_and_recovers(db, live):
    from nhdip.knowledge.search import retrieve

    with db() as s:
        elastic.sync(s, limit=10**9, force=True)
        s.commit()
    _set_setting(db, "knowledge.search", {"backend": "es"})
    q = "소기업 6B 등급 실제부도율은 예측 대표값 대비 어떤가요?"
    good = elastic.client()
    elastic.set_client(httpx.Client(base_url="http://127.0.0.1:9", timeout=2.0))  # 아무도 듣지 않는 포트
    with db() as s:
        down = retrieve(s, _admin_scope(s), q)
    assert down.analysis and down.diagnostics["backend"] == "pg" and "esFallback" in down.diagnostics
    elastic.set_client(good)
    elastic.reset_breaker()
    with db() as s:
        up = retrieve(s, _admin_scope(s), q)
    assert up.diagnostics["backend"] == "es" and [h["chunk_id"] for h in up.analysis][:1]
