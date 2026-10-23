"""업무 자료 비우기 (Phase M 후속 M.19 · DEL-13 · Q203).

시연 · 시험으로 올린 업무 자료와 그 파생물을 모두 지우고 **정의만 있는 새 DB 와 같은 상태**로 되돌린다 — 이후 화면 업로드로 다시 채운다.

- 남기는 것(설정): 사용자 · 조직 · 화면 권한 · 세션 · 설정 · 규칙 · LLM 연결 · 비밀 값 · 에이전트 · 그룹 · 프롬프트 · 워크플로 · 트리거 · 지표 ·
  화면 바인딩 · 데이터셋 정의 · 컬럼 정의서 · 지식 컬렉션 · 온톨로지 판 · 분석 에이전트 정의, 감사 기록 · 요청 기록 · 속도 제한 · 워커 상태.
- 지우는 것(업무 자료와 파생물): 데이터셋 버전 · 행 · 문서 · 청크(임베딩), mart 표의 행, 계산 기록 · 지표 값, 화면 산출물 전 세대(값 없는 틀로 다시 게시),
  분석 결과 색인, 업무 사용자 상태(목표 처리 · 수행방안), 온톨로지 변경 제안, 실행 기록(워크플로 · 노드 · LLM 호출 · 에이전트 결정 · 작업 · 이벤트),
  자료 요청 · 등록, 구조 파악 결과, 추출 이슈, 삭제 작업, 알림, 원본 파일, Elasticsearch 두 색인 · Neo4j 관리 노드.

화면 버튼은 두지 않는다(Q203 — 되돌릴 수 없는 일괄 삭제는 서버 셸에서만). `python -m nhdip.cli reset-data` 는 기본이 미리보기이고 `--yes` 로 실행한다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from nhdip.config import get_settings
from nhdip.events import audit, emit
from nhdip.models import Base, Job, Setting, UploadRequest, WorkflowRun, source

log = logging.getLogger(__name__)

# 지우는 표 — 정의 · 설정이 아닌 업무 자료와 그 파생물. 순서는 외래키에서 정한다(참조하는 표가 먼저)
CLEAR_TABLES: frozenset[str] = frozenset(
    {
        "bank.dataset_version", "bank.row_store", "bank.document", "bank.chunk",
        "ext.dataset_version", "ext.row_store", "ext.document", "ext.chunk",
        "calc.calc_run", "calc.metric_value",
        "app.view_artifact", "app.user_state", "app.kb_chunk",
        # AI 어시스턴트 대화 — 지운 자료로 낸 수치 · 출처가 든 답이라 함께 비운다(다음 대화가 옛 수치를 맥락으로 쓰지 않게)
        "app.assist_message", "app.assist_conversation",
        "cfg.ontology_proposal",
        "ops.outbox_event", "ops.job", "ops.workflow_run", "ops.node_run", "ops.llm_call", "ops.agent_decision",
        "ops.extraction_issue", "ops.data_profile", "ops.upload_request", "ops.purge_task", "ops.alert",
    }
)
# 남기는 표 — 새 표가 생기면 둘 중 하나에 넣어야 시험(test_reset_tables_are_classified)이 통과한다
KEEP_TABLES: frozenset[str] = frozenset(
    {
        "iam.app_user", "iam.org_unit", "iam.screen", "iam.screen_grant", "iam.session",
        "cfg.setting", "cfg.secret", "cfg.rule", "cfg.rule_version", "cfg.llm_connection", "cfg.llm_profile",
        "cfg.agent", "cfg.agent_group", "cfg.prompt", "cfg.workflow", "cfg.workflow_node", "cfg.workflow_trigger",
        "cfg.metric", "cfg.view_binding", "cfg.dataset", "cfg.column_contract", "cfg.kb_collection", "cfg.ontology_schema",
        "cfg.analysis_agent", "cfg.analysis_agent_version", "cfg.business_config",
        "audit.audit_log", "ops.request_log", "ops.rate_limit", "ops.worker_heartbeat",
        "public.alembic_version",
    }
)
MART_SCHEMA = "mart"  # 컬럼 정의서 적재 표(contracts.materialize 가 만든다) — 표는 두고 행만 지운다
# 색인 · 동기화 내부 상태 — 청크를 지웠으니 처음부터 다시 맞춘다
STATE_SETTINGS = ("knowledge.state", "knowledge.es_state", "knowledge.es_doc_state")
NEO4J_BATCH = 5000


class ResetBusy(RuntimeError):
    """실행 중인 작업이 있다 — 끝난 뒤 다시(또는 --force)."""


@dataclass
class ResetReport:
    tables: dict[str, int] = field(default_factory=dict)
    mart: dict[str, int] = field(default_factory=dict)
    settings: list[str] = field(default_factory=list)
    artifacts: Any = None
    knowledge: Any = None
    files: list[str] = field(default_factory=list)
    external: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "tables": {k: v for k, v in sorted(self.tables.items()) if v},
            "rowsRemoved": sum(self.tables.values()) + sum(self.mart.values()),
            "mart": {k: v for k, v in sorted(self.mart.items()) if v},
            "settingsCleared": self.settings,
            "templatesPublished": self.artifacts,
            "knowledge": self.knowledge,
            "files": len(self.files),
            "external": self.external,
        }


def _ordered_clear_tables() -> list[Any]:
    """지울 표(SQLAlchemy Table) — 참조하는 표가 먼저 오도록(sorted_tables 의 역순)."""
    return [t for t in reversed(Base.metadata.sorted_tables) if t.fullname in CLEAR_TABLES]


def mart_tables(session: Session) -> list[str]:
    return list(session.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema = :s AND table_type = 'BASE TABLE' ORDER BY 1"), {"s": MART_SCHEMA}).scalars())


def busy(session: Session) -> dict[str, int]:
    """실행 중인 작업 · 워크플로 — 있으면 비우는 도중 워커가 지운 자료로 산출물을 다시 쓸 수 있다."""
    jobs = session.execute(select(func.count()).select_from(Job).where(Job.status == "running")).scalar() or 0
    runs = session.execute(select(func.count()).select_from(WorkflowRun).where(WorkflowRun.status == "running")).scalar() or 0
    return {"runningJobs": int(jobs), "runningWorkflows": int(runs)}


def preview(session: Session) -> dict[str, Any]:
    """지울 행 수(미리보기) — 아무것도 바꾸지 않는다."""
    tables = {t.fullname: int(session.execute(select(func.count()).select_from(t)).scalar() or 0) for t in _ordered_clear_tables()}
    mart = {f"{MART_SCHEMA}.{n}": int(session.execute(text(f'SELECT count(*) FROM {MART_SCHEMA}."{n}"')).scalar() or 0) for n in mart_tables(session)}
    current = {o: int(session.execute(select(func.count()).select_from(source(o).version).where(source(o).version.is_current)).scalar() or 0) for o in ("bank", "ext")}
    docs = {o: int(session.execute(select(func.count()).select_from(source(o).document).where(source(o).document.is_current)).scalar() or 0) for o in ("bank", "ext")}
    return {
        "tables": {k: v for k, v in sorted(tables.items()) if v},
        "mart": {k: v for k, v in sorted(mart.items()) if v},
        "rows": sum(tables.values()) + sum(mart.values()),
        "currentDatasetVersions": current,
        "currentDocuments": docs,
        "busy": busy(session),
        "kept": sorted(KEEP_TABLES - {"public.alembic_version"}),
    }


def _files(session: Session) -> list[str]:
    out: list[str] = []
    for o in ("bank", "ext"):
        t = source(o)
        out += [p for p in session.execute(select(t.version.file_path).where(t.version.file_path.is_not(None))).scalars() if p]
        out += [p for p in session.execute(select(t.document.file_path).where(t.document.file_path.is_not(None))).scalars() if p]
    out += [p for p in session.execute(select(UploadRequest.file_path).where(UploadRequest.file_path.is_not(None))).scalars() if p]
    return list(dict.fromkeys(out))


def clear_external() -> dict[str, Any]:
    """Elasticsearch 두 색인 · Neo4j 관리 노드 — 저장소가 멈춰 있어도 실패로 보지 않는다(재투영 · 동기화가 원장 기준으로 다시 맞춘다)."""
    from nhdip.graph.neo4j_client import GraphUnavailable, run
    from nhdip.knowledge import elastic

    out: dict[str, Any] = {}
    try:
        if not elastic.configured():
            out["es"] = {"status": "skipped", "reason": "ES_URL 미설정"}
        else:
            for idx in (elastic.index_name(), elastic.doc_index_name()):
                elastic.request("DELETE", f"/{idx}", ok=(200, 404))
            out["es"] = {"status": "done", "indices": [elastic.index_name(), elastic.doc_index_name()]}
    except Exception as exc:  # noqa: BLE001 — 동기화가 PG 목록과 대조해 지운다
        out["es"] = {"status": "pending", "reason": f"{type(exc).__name__}: {str(exc)[:200]} — 다음 동기화가 정리"}
    if not (get_settings().neo4j_uri or "").strip():
        out["neo4j"] = {"status": "skipped", "reason": "Neo4j 미구성"}
        return out
    try:
        n = 0
        while True:
            rows = run(f"MATCH (n) WHERE n.managed = true WITH n LIMIT {NEO4J_BATCH} DETACH DELETE n RETURN count(*) AS n")
            got = int(rows[0]["n"]) if rows else 0
            n += got
            if got < NEO4J_BATCH:
                break
        out["neo4j"] = {"status": "done", "nodes": n}
    except GraphUnavailable as exc:
        out["neo4j"] = {"status": "pending", "reason": f"{str(exc)[:200]} — 다음 재투영이 정리"}
    except Exception as exc:  # noqa: BLE001
        out["neo4j"] = {"status": "pending", "reason": f"{type(exc).__name__}: {str(exc)[:200]} — 다음 재투영이 정리"}
    return out


def reset_business_data(session: Session, actor: str, ip: str | None = None, *, external: bool = True, force: bool = False) -> ResetReport:
    """업무 자료를 모두 지우고 값 없는 화면 틀을 다시 게시한다. 호출자가 commit 하고, 그 뒤 `remove_files(rep.files)` 로 원본을 지운다.

    external=True 면 커밋 전에 ES 색인 · Neo4j 관리 노드도 지운다(커밋이 실패해도 원장 기준으로 다시 만들 수 있는 저장소들)."""
    from nhdip.locks import lock
    from nhdip.seed.run import seed_knowledge

    b = busy(session)
    if not force and any(b.values()):
        raise ResetBusy(f"실행 중인 작업 {b['runningJobs']}건 · 워크플로 {b['runningWorkflows']}건 — 끝난 뒤 다시 실행하세요(wait-idle) 또는 --force")
    lock(session, "data:reset")
    rep = ResetReport(files=_files(session))
    for t in _ordered_clear_tables():
        rep.tables[t.fullname] = int(session.execute(t.delete()).rowcount or 0)
    for name in mart_tables(session):
        rep.mart[f"{MART_SCHEMA}.{name}"] = int(session.execute(text(f'DELETE FROM {MART_SCHEMA}."{name}"')).rowcount or 0)
    for key in STATE_SETTINGS:
        st = session.get(Setting, key)
        if st is not None:
            session.delete(st)
            rep.settings.append(key)
    session.flush()
    # 새 DB 와 같은 상태 — 값 없는 화면 틀(0세대) · 그 틀의 분석 결과 색인
    out: dict[str, Any] = {}
    from nhdip.bizconfig.apply import publish_templates

    out["artifacts"] = publish_templates(session)  # 활성 업무 구성의 화면 틀(값 없는 0세대) — 시드에는 화면 틀이 없다(Phase O)
    session.flush()
    seed_knowledge(session, out)
    session.flush()
    rep.artifacts, rep.knowledge = out.get("artifacts"), out.get("knowledge")
    if external:
        rep.external = clear_external()
    # 그래프는 정의(데이터셋 · 지표 · 워크플로)만으로 다시 투영한다 — 이 이벤트가 워커에서 돌며 남은 관리 노드도 정리한다
    emit(session, "manual", {"workflow": "wf_graph_projection", "reason": "업무 자료 비우기 뒤 정의만으로 다시 투영"}, actor)
    audit(session, actor, "ops.data_reset", "database", "business_data", {"rows": sum(rep.tables.values()) + sum(rep.mart.values()), "tables": {k: v for k, v in rep.tables.items() if v}, "mart": {k: v for k, v in rep.mart.items() if v}, "files": len(rep.files), "external": rep.external, "force": force}, ip)
    return rep
