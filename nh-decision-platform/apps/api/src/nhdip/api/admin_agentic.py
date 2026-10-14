"""관리자 [에이전틱 파이프라인] (Phase M · 요구사항 AGG-03 · Q189).

그룹(AGG-01)마다 그 그룹 에이전트가 맡은 워크플로 단계를 순서대로(그룹 → 워크플로 노드 순서) 보여 준다.
워크플로 노드에 없는 에이전트(AI 어시스턴트 · 검색 · 자료 등록 · 오케스트레이터)는 호출 경로(flow)를 정해 둔 순서로 그린다.
상태는 실제 기록에서 읽는다 — 노드 실행(ops.node_run) · 워크플로 실행 · LLM 호출(ops.llm_call 24시간) · 에이전트 결정 · 연결 차단기.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from nhdip.db import get_session
from nhdip.llm import LlmUnavailable, resolve
from nhdip.models import Agent, AgentDecision, AgentGroup, Dataset, Workflow, WorkflowNode, WorkflowRun, utcnow
from nhdip.models.runtime import NodeRun

from .admin_core import _group_summary, agent_stats_24h
from .deps import require_admin

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])

# 워크플로 노드 밖에서 부르는 에이전트의 호출 경로 — (단계 이름, 에이전트 코드 | None, 설명)
FLOWS: dict[str, list[tuple[str, str | None, str]]] = {
    "orchestration": [("이벤트 수신", None, "outbox · 트리거 매칭"), ("실행 순서 · 대기", "orchestrator", "같은 출력 묶기 · 경로 판단"), ("실행 계획", "planner", "서술 대상 고르기")],
    "intake": [("파일 판별", None, "정형 · 비정형"), ("정형 분석", "data_intake", "정의 초안 + 이름 · 의미"), ("문서 분석", "doc_intake", "제목 · 분류 · 기관 · 시행일"),
               ("확인 · 반영", None, "책임자 반영 · 승인 요청"), ("원장 · 3-way 저장", None, "PostgreSQL · pgvector · ES · Neo4j")],
    "knowledge": [("청크 · 카드 색인", None, "산출물 · 데이터셋 설명 카드"), ("임베딩", "embedder", "pgvector"), ("검색어 재작성", "query_rewriter", "후속 질문"), ("검색 재정렬", "search_reranker", "선택")],
    "assistant": [("접근 범위", None, "화면 리소스 · 부서"), ("질문 이해", "query_rewriter", "후속 질문 재작성"), ("하이브리드 검색", "search_reranker", "키워드 · 의미 · 그래프"),
                  ("답변 · 도구", "query_assistant", "calc_* · onto_* · data_aggregate"), ("숫자 · 인용 점검", None, "출처 없는 숫자 · 지어낸 출처")],
}


def _iso(v: Any) -> str | None:
    return v.isoformat() if v else None


def _agent_view(session: Session, a: Agent, stats: dict[str, dict[str, Any]]) -> dict[str, Any]:
    model, conn, ok, reason = None, None, True, None
    if a.kind == "llm":
        try:
            r = resolve(session, a.code)
            model, conn = r.model, r.connection_name
        except LlmUnavailable as exc:
            ok, reason = False, str(exc)[:160]
    return {"code": a.code, "name": a.name, "kind": a.kind, "enabled": a.enabled, "model": model, "connection": conn, "ready": ok, "reason": reason, "stats": stats.get(a.code) or {}}


def _pipelines(session: Session, codes: set[str], names: dict[str, str], group_of: dict[str, str | None], since) -> list[dict[str, Any]]:
    wf_codes = sorted({n.workflow_code for n in session.execute(select(WorkflowNode).where(WorkflowNode.agent_code.in_(codes or {"-"}))).scalars()})
    out = []
    for wc in wf_codes:
        wf = session.get(Workflow, wc)
        if wf is None:
            continue
        nodes = session.execute(select(WorkflowNode).where(WorkflowNode.workflow_code == wc).order_by(WorkflowNode.seq)).scalars().all()
        last = session.execute(select(WorkflowRun).where(WorkflowRun.workflow_code == wc).order_by(WorkflowRun.started_at.desc()).limit(1)).scalars().first()
        nr = {x.node_key: x for x in session.execute(select(NodeRun).where(NodeRun.workflow_run_id == last.id)).scalars()} if last is not None else {}
        counts = dict(session.execute(select(WorkflowRun.status, func.count()).where(WorkflowRun.workflow_code == wc, WorkflowRun.started_at >= since).group_by(WorkflowRun.status)).all())
        out.append({
            "workflow": wc, "name": wf.name, "enabled": wf.enabled,
            "nodes": [{"key": n.key, "name": n.name, "impl": n.impl, "enabled": n.enabled, "agent": n.agent_code, "agentName": names.get(n.agent_code or ""), "agentGroup": group_of.get(n.agent_code or ""),
                       "inGroup": (n.agent_code or "") in codes, "status": nr[n.key].status if n.key in nr else None, "ms": nr[n.key].duration_ms if n.key in nr else None} for n in nodes],
            "lastRun": {"id": last.id, "status": last.status, "startedAt": _iso(last.started_at), "finishedAt": _iso(last.finished_at)} if last is not None else None,
            "runs24h": {"total": sum(counts.values()), **counts},
        })
    return out


def _flow(code: str, names: dict[str, str], stats: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for label, agent, desc in FLOWS.get(code, []):
        st = stats.get(agent or "") or {}
        status = None
        if agent:
            status = "failed" if st.get("calls") and st.get("errors", 0) >= st.get("calls", 0) else ("degraded" if st.get("errors") else ("succeeded" if st.get("calls") else None))
        out.append({"label": label, "agent": agent, "agentName": names.get(agent or ""), "description": desc, "status": status, "calls24h": st.get("calls", 0)})
    return out


def _ontology_extra(session: Session) -> dict[str, Any]:
    from nhdip.models import DataProfile, OntologyProposal

    datasets = session.execute(select(func.count()).select_from(Dataset).where(Dataset.active)).scalar() or 0
    profiled = session.execute(select(func.count(func.distinct(DataProfile.dataset_code))).join(Dataset, Dataset.code == DataProfile.dataset_code).where(Dataset.active)).scalar() or 0
    pending = session.execute(select(func.count()).select_from(OntologyProposal).where(OntologyProposal.status == "pending")).scalar() or 0
    applied = session.execute(select(func.count()).select_from(OntologyProposal).where(OntologyProposal.status == "applied")).scalar() or 0
    q = session.execute(select(NodeRun).where(NodeRun.impl == "check_ontology").order_by(NodeRun.started_at.desc()).limit(1)).scalars().first()
    out = q.output if q is not None and isinstance(q.output, dict) else {}
    return {"datasets": datasets, "profiled": profiled, "pendingProposals": pending, "appliedProposals": applied, "grade": out.get("grade"), "checkedAt": _iso(q.started_at) if q is not None else None}


def _intake_extra(session: Session, since) -> dict[str, Any]:
    from nhdip.models import UploadRequest

    rows = dict(session.execute(select(UploadRequest.status, func.count()).where(UploadRequest.meta["intake"].astext.is_not(None)).group_by(UploadRequest.status)).all())
    recent = session.execute(select(func.count()).select_from(UploadRequest).where(UploadRequest.meta["intake"].astext.is_not(None), UploadRequest.status == "approved", UploadRequest.reviewed_at >= since)).scalar() or 0
    return {"drafts": rows.get("draft", 0), "pending": rows.get("pending", 0), "applied": rows.get("approved", 0), "failed": rows.get("failed", 0), "applied24h": recent}


@router.get("/agentic/overview")
def agentic_overview(session: Session = Depends(get_session)):
    from nhdip.llm.breaker import snapshot

    since = utcnow() - timedelta(hours=24)
    stats = agent_stats_24h(session)
    agents = session.execute(select(Agent).order_by(Agent.code)).scalars().all()
    names = {a.code: a.name for a in agents}
    group_of = {a.code: a.group_code for a in agents}
    groups = session.execute(select(AgentGroup).order_by(AgentGroup.sort, AgentGroup.code)).scalars().all()
    out = []
    for g in groups:
        mem = [a for a in agents if a.group_code == g.code]
        codes = {a.code for a in mem}
        decisions = session.execute(select(AgentDecision).where(AgentDecision.agent_code.in_(codes or {"-"})).order_by(AgentDecision.id.desc()).limit(8)).scalars().all() if codes else []
        item: dict[str, Any] = {
            "code": g.code, "name": g.name, "description": g.description, "summary": _group_summary(mem, stats),
            "agents": [_agent_view(session, a, stats) for a in mem],
            "pipelines": _pipelines(session, codes, names, group_of, since), "flow": _flow(g.code, names, stats),
            "decisions": [{"id": d.id, "at": _iso(d.at), "agent": d.agent_code, "agentName": names.get(d.agent_code), "decision": d.decision, "summary": d.summary, "workflow": d.workflow_code} for d in decisions],
        }
        if g.code == "ontology":
            item["ontology"] = _ontology_extra(session)
        if g.code == "intake":
            item["intake"] = _intake_extra(session, since)
        out.append(item)
    return {"groups": out, "breaker": snapshot(), "generatedAt": _iso(utcnow()),
            "totals": {"agents": len(agents), "llm": sum(1 for a in agents if a.kind == "llm"), "calls24h": sum(v.get("calls", 0) for v in stats.values()), "errors24h": sum(v.get("errors", 0) for v in stats.values())}}
