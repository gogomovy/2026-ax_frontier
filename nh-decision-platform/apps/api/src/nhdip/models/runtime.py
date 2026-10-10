"""calc · app · ops · audit — 계산 이력, 화면 산출물·사용자 상태, 작업 큐·실행 기록, 감사."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, Date, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, new_id, utcnow
from nhdip.obs import current as _trace  # 추적 ID 기본값 (작업 0.5)
from nhdip.obs import current_or_new as _trace_or_new


# ═════════════════════════ calc ═════════════════════════
class CalcRun(Base):
    """커널 실행 1건 — 수식·입력 스냅샷·결과를 불변 저장 (CALC-02)."""

    __tablename__ = "calc_run"
    __table_args__ = {"schema": "calc"}

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    formula_id: Mapped[str] = mapped_column(String(40), index=True)
    formula_version: Mapped[int] = mapped_column(Integer, default=1)
    metric_code: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    inputs: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    sources: Mapped[list[Any]] = mapped_column(JSONB, default=list)  # 입력 출처(데이터셋 버전·행)
    result: Mapped[Any] = mapped_column(JSONB, nullable=True)
    value: Mapped[float | None] = mapped_column(Numeric(28, 10), nullable=True)
    display_value: Mapped[float | None] = mapped_column(Numeric(28, 10), nullable=True)
    decimals: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rounding: Mapped[str | None] = mapped_column(String(12), nullable=True)
    library: Mapped[str | None] = mapped_column(String(100), nullable=True)
    workflow_run_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)


class MetricValue(Base):
    """지표 값 이력 — 관리자 [수치 모니터링] 추이의 원천."""

    __tablename__ = "metric_value"
    __table_args__ = (Index("ix_calc_metric_value_code_at", "metric_code", "created_at"), {"schema": "calc"})

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    metric_code: Mapped[str] = mapped_column(String(80))
    as_of: Mapped[date | None] = mapped_column(Date, nullable=True)
    value: Mapped[float | None] = mapped_column(Numeric(28, 10), nullable=True)
    display_value: Mapped[float | None] = mapped_column(Numeric(28, 10), nullable=True)
    previous_value: Mapped[float | None] = mapped_column(Numeric(28, 10), nullable=True)
    calc_run_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    workflow_run_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


# ═════════════════════════ app ═════════════════════════
class ViewArtifact(Base):
    """화면 산출물(대시보드·보고서·인사이트 등) — 세대 교체(is_current), 이전 세대 보존."""

    __tablename__ = "view_artifact"
    __table_args__ = (UniqueConstraint("key", "generation"), {"schema": "app"})

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(80), index=True)
    generation: Mapped[int] = mapped_column(Integer)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    payload: Mapped[Any] = mapped_column(JSONB)
    produced_by: Mapped[str] = mapped_column(String(60), default="seed")
    workflow_run_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    changes: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class UserState(Base):
    """업무 사용자 상태 — 경영목표 처리·진행사업 등록 등 (산출물 재생성과 무관하게 보존, §8.8)."""

    __tablename__ = "user_state"
    __table_args__ = {"schema": "app"}

    namespace: Mapped[str] = mapped_column(String(40), primary_key=True)
    item_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    payload: Mapped[Any] = mapped_column(JSONB, default=dict)
    updated_by: Mapped[str | None] = mapped_column(String(40), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


# ═════════════════════════ ops ═════════════════════════
class OutboxEvent(Base):
    __tablename__ = "outbox_event"
    __table_args__ = {"schema": "ops"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # dataset.committed | dataset.rolled_back | document.ingested | master.changed | rule.changed | goal.confirmed | manual
    type: Mapped[str] = mapped_column(String(40), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    actor: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    dispatched_at: Mapped[datetime | None] = mapped_column(nullable=True, index=True)
    matched: Mapped[list[Any]] = mapped_column(JSONB, default=list)  # 매칭된 워크플로우와 사유
    trace_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True, default=_trace_or_new)


class Job(Base):
    """작업 큐 (FOR UPDATE SKIP LOCKED)."""

    __tablename__ = "job"
    __table_args__ = (Index("ix_ops_job_status_run_after", "status", "run_after"), {"schema": "ops"})

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(30))  # workflow
    workflow_code: Mapped[str | None] = mapped_column(String(60), nullable=True, index=True)
    causes: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(12), default="queued")  # queued|running|done|failed|cancelled
    run_after: Mapped[datetime] = mapped_column(default=utcnow)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    locked_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class WorkflowRun(Base):
    __tablename__ = "workflow_run"
    __table_args__ = {"schema": "ops"}

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workflow_code: Mapped[str] = mapped_column(String(60), index=True)
    job_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="running")  # running|succeeded|degraded|failed
    causes: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    summary: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True, default=_trace)


class NodeRun(Base):
    __tablename__ = "node_run"
    __table_args__ = {"schema": "ops"}

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workflow_run_id: Mapped[str] = mapped_column(String(32), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    node_key: Mapped[str] = mapped_column(String(60))
    impl: Mapped[str] = mapped_column(String(60))
    agent_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    status: Mapped[str] = mapped_column(String(12))  # succeeded|degraded|skipped|failed
    input: Mapped[Any] = mapped_column(JSONB, nullable=True)
    output: Mapped[Any] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)


class LlmCall(Base):
    __tablename__ = "llm_call"
    __table_args__ = {"schema": "ops"}

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    node_run_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    workflow_run_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    agent_code: Mapped[str | None] = mapped_column(String(60), nullable=True, index=True)
    purpose: Mapped[str] = mapped_column(String(30), default="chat")  # chat | embedding | test
    connection_name: Mapped[str | None] = mapped_column(String(60), nullable=True)
    base_url: Mapped[str | None] = mapped_column(String(300), nullable=True)
    model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    messages: Mapped[Any] = mapped_column(JSONB, nullable=True)
    response: Mapped[Any] = mapped_column(JSONB, nullable=True)
    output_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="ok")  # ok | error | skipped
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    trace_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True, default=_trace)


class ExtractionIssue(Base):
    __tablename__ = "extraction_issue"
    __table_args__ = {"schema": "ops"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    origin: Mapped[str] = mapped_column(String(40))
    document_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chunk_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # schema_violation | unresolved_entity | span_not_found | llm_error | parse_error
    kind: Mapped[str] = mapped_column(String(30))
    raw: Mapped[Any] = mapped_column(JSONB, nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(10), default="open")  # open | accepted | rejected
    resolved_by: Mapped[str | None] = mapped_column(String(40), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class WorkerHeartbeat(Base):
    __tablename__ = "worker_heartbeat"
    __table_args__ = {"schema": "ops"}

    worker_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    seen_at: Mapped[datetime] = mapped_column(default=utcnow)
    info: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


# ═════════════════════════ audit ═════════════════════════
class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = {"schema": "audit"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    actor: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(60), index=True)
    target_kind: Mapped[str | None] = mapped_column(String(40), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    detail: Mapped[Any] = mapped_column(JSONB, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True, default=_trace)


class RequestLog(Base):
    """HTTP 요청 구간 (작업 0.5) — 변경 요청 · 오류 · 느린 조회만 남긴다(설정 `obs.slow_request_ms`)."""

    __tablename__ = "request_log"
    __table_args__ = {"schema": "ops"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    trace_id: Mapped[str] = mapped_column(String(32), index=True)
    at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    method: Mapped[str] = mapped_column(String(8))
    path: Mapped[str] = mapped_column(String(300))
    route: Mapped[str | None] = mapped_column(String(300), nullable=True)
    status: Mapped[int] = mapped_column(Integer)
    duration_ms: Mapped[int] = mapped_column(Integer)
    db_queries: Mapped[int] = mapped_column(Integer, default=0)
    db_ms: Mapped[int] = mapped_column(Integer, default=0)
    actor: Mapped[str | None] = mapped_column(String(40), nullable=True)


class Alert(Base):
    """운영 알림 (작업 8.5) — 조건 · 심각도 · 채널별 발송 결과. dedupe_key 로 같은 알림 반복 방지."""

    __tablename__ = "alert"
    __table_args__ = {"schema": "ops"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    severity: Mapped[str] = mapped_column(String(12))
    title: Mapped[str] = mapped_column(String(300))
    detail: Mapped[Any] = mapped_column(JSONB, default=dict)
    dedupe_key: Mapped[str] = mapped_column(String(200), index=True)
    channels: Mapped[Any] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="logged")  # logged · sent · failed · no_channel · below_threshold
    trace_id: Mapped[str | None] = mapped_column(String(32), nullable=True, default=_trace)


class AgentDecision(Base):
    """에이전트 결정 기록 (B.30) — 오케스트레이터(실행 순서 · 대기) · 변화 감지(유의 변화) · 플래너(서술 대상) · 서술(갱신 완료).

    결정 근거(detail)를 남겨 관리자 화면 [에이전트 결정]에서 왜 그렇게 실행했는지 추적한다.
    """

    __tablename__ = "agent_decision"
    __table_args__ = (Index("ix_ops_agent_decision_agent_at", "agent_code", "at"), {"schema": "ops"})

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    agent_code: Mapped[str] = mapped_column(String(60))
    workflow_code: Mapped[str | None] = mapped_column(String(60), nullable=True, index=True)
    job_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    workflow_run_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    decision: Mapped[str] = mapped_column(String(30))  # hold · release · detect · plan · narrated
    summary: Mapped[str] = mapped_column(String(500), default="")
    detail: Mapped[Any] = mapped_column(JSONB, default=dict)
    trace_id: Mapped[str | None] = mapped_column(String(32), nullable=True, default=_trace)
