"""cfg — 관리자 화면에서 제어하는 모든 업무 설정 (하드코딩 배제, 설계 §19.4)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, utcnow

S = {"schema": "cfg"}


class LlmConnection(Base):
    """LiteLLM(또는 OpenAI 호환) 게이트웨이 연결 — 키는 AES-GCM 암호화 저장."""

    __tablename__ = "llm_connection"
    __table_args__ = S

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(60), unique=True)
    base_url: Mapped[str] = mapped_column(String(300))
    api_key_enc: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_test: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class LlmProfile(Base):
    """모델 + 파라미터 묶음. 에이전트는 프로필을 상속하고 override 로 덮어쓴다."""

    __tablename__ = "llm_profile"
    __table_args__ = S

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(60), unique=True)
    connection_id: Mapped[int | None] = mapped_column(ForeignKey("cfg.llm_connection.id", ondelete="SET NULL"), nullable=True)
    model: Mapped[str] = mapped_column(String(200), default="")
    temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    top_p: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timeout_sec: Mapped[float] = mapped_column(Float, default=60.0)
    retries: Mapped[int] = mapped_column(Integer, default=2)
    tools_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    extra: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)  # 기타 OpenAI 호환 파라미터
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class AgentGroup(Base):
    """에이전트 기능 묶음 (Phase M · AGG-01 · Q188) — 관리자 [에이전트·프롬프트] 그룹 탭 · [에이전틱 파이프라인] 그림 단위."""

    __tablename__ = "agent_group"
    __table_args__ = S

    code: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, default="")
    sort: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class Agent(Base):
    __tablename__ = "agent"
    __table_args__ = S

    code: Mapped[str] = mapped_column(String(60), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(10), default="llm")  # llm | rule
    group_code: Mapped[str | None] = mapped_column(ForeignKey("cfg.agent_group.code", ondelete="SET NULL"), nullable=True)
    profile_id: Mapped[int | None] = mapped_column(ForeignKey("cfg.llm_profile.id", ondelete="SET NULL"), nullable=True)
    # 에이전트 전용 연결·모델·파라미터 (프로필 값 위에 덮어씀): connection_id, model, temperature ...
    override: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    prompt_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class Prompt(Base):
    __tablename__ = "prompt"
    __table_args__ = (UniqueConstraint("agent_code", "version"), S)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_code: Mapped[str] = mapped_column(ForeignKey("cfg.agent.code", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer)
    system: Mapped[str] = mapped_column(Text, default="")
    user_template: Mapped[str] = mapped_column(Text, default="")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Workflow(Base):
    __tablename__ = "workflow"
    __table_args__ = S

    code: Mapped[str] = mapped_column(String(60), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # 산출물(화면 산출물 키) — 그래프 PRODUCES 관계 원천
    outputs: Mapped[list[str]] = mapped_column(JSONB, default=list)
    sort: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class WorkflowNode(Base):
    __tablename__ = "workflow_node"
    __table_args__ = (UniqueConstraint("workflow_code", "key"), S)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workflow_code: Mapped[str] = mapped_column(ForeignKey("cfg.workflow.code", ondelete="CASCADE"))
    seq: Mapped[int] = mapped_column(Integer)
    key: Mapped[str] = mapped_column(String(60))
    name: Mapped[str] = mapped_column(String(100))
    impl: Mapped[str] = mapped_column(String(60))  # 노드 구현 레지스트리 키
    agent_code: Mapped[str | None] = mapped_column(ForeignKey("cfg.agent.code", ondelete="SET NULL"), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class WorkflowTrigger(Base):
    __tablename__ = "workflow_trigger"
    __table_args__ = S

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workflow_code: Mapped[str] = mapped_column(ForeignKey("cfg.workflow.code", ondelete="CASCADE"))
    # dataset | doc_class | master | rule | event | any | cron
    kind: Mapped[str] = mapped_column(String(20))
    # 데이터셋 코드 · 문서 분류 · 이벤트 유형 · '*' · cron 식(분 시 일 월 요일, 업무 시간대 기준)
    target: Mapped[str] = mapped_column(String(100))
    debounce_sec: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 비우면 setting 기본값
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_fired_at: Mapped[datetime | None] = mapped_column(nullable=True)  # cron 마지막 실행 시각


class Dataset(Base):
    """데이터셋 정의 (ING-03) — 정의만으로 새 형식의 파일을 수용한다."""

    __tablename__ = "dataset"
    __table_args__ = S

    code: Mapped[str] = mapped_column(String(60), primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    origin: Mapped[str] = mapped_column(String(40))  # bank | ext  → 저장 스키마 분리
    kind: Mapped[str] = mapped_column(String(10), default="fact")  # fact | master
    description: Mapped[str] = mapped_column(Text, default="")
    file_pattern: Mapped[str | None] = mapped_column(String(200), nullable=True)
    refresh_cycle: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # [{name, label, type(str|int|num|date|bool), required, aliases:[원본 헤더명]}]
    columns: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    key_columns: Mapped[list[str]] = mapped_column(JSONB, default=list)
    as_of_column: Mapped[str | None] = mapped_column(String(60), nullable=True)
    # 온톨로지 매핑 (결정론 투영): {"metric_concepts":[...], "segment_column":"grade", "concept":"RatingModel", ...}
    mapping: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    # [{rule: not_null|unique_key|range|allowed|sum_equals, column, ...}]
    quality_rules: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    # 파일 파서 설정: {sheet, header_row, skip_rows}
    parser: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    materialize: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    # 공통 통합 DB (요구사항 §38 CMN) — 모든 부서(종기부 · 사업부서 · 영업본부 · 영업점)가 함께 보는 자료. 관리자만 올리고 소유 팀이 없다(전행 공통)
    common: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class Metric(Base):
    """화면 수치(figure) 정의 — 어떤 데이터셋 값을 어떤 커널 수식으로 계산하는지 (CALC-01)."""

    __tablename__ = "metric"
    __table_args__ = S

    code: Mapped[str] = mapped_column(String(80), primary_key=True)
    label: Mapped[str] = mapped_column(String(150))
    formula: Mapped[str] = mapped_column(String(40))  # 커널 수식 ID
    # {"param": {"q": {...}} | {"metric": code, "field": ...} | {"const": v} | {"rule": code, "path": ...}}
    args: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    unit: Mapped[str] = mapped_column(String(12), default="")
    decimals: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rounding: Mapped[str | None] = mapped_column(String(12), nullable=True)  # 비우면 setting 기본(HALF_UP)
    scale: Mapped[float | None] = mapped_column(Float, nullable=True)  # 결과 ÷ scale (예: 백만원→억원 100)
    workflow_code: Mapped[str] = mapped_column(ForeignKey("cfg.workflow.code", ondelete="CASCADE"))
    figure_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)  # 비우면 [code]
    description: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    sort: Mapped[int] = mapped_column(Integer, default=0)


class ViewBinding(Base):
    """화면 산출물 내 표·차트 블록을 계산 결과로 다시 그리는 바인딩."""

    __tablename__ = "view_binding"
    __table_args__ = S

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workflow_code: Mapped[str] = mapped_column(ForeignKey("cfg.workflow.code", ondelete="CASCADE"))
    artifact_key: Mapped[str] = mapped_column(String(80))
    path: Mapped[str] = mapped_column(String(300))  # 점 표기 경로 (예: sections.4.blocks.0.table.rows)
    builder: Mapped[str] = mapped_column(String(60))
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class Rule(Base):
    __tablename__ = "rule"
    __table_args__ = S

    code: Mapped[str] = mapped_column(String(60), primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    kind: Mapped[str] = mapped_column(String(20))  # threshold | guide | weight | rounding
    description: Mapped[str] = mapped_column(Text, default="")
    active_version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class RuleVersion(Base):
    __tablename__ = "rule_version"
    __table_args__ = (UniqueConstraint("rule_code", "version"), S)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_code: Mapped[str] = mapped_column(ForeignKey("cfg.rule.code", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer)
    body: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class OntologySchema(Base):
    __tablename__ = "ontology_schema"
    __table_args__ = S

    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    classes: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    relations: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    # 엔티티 링크 별칭 사전: {"ProductGroup": {"햇살론": ["햇살론", "햇살론뱅크"]}, ...}
    aliases: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    # 인터페이스(공통 모양) — [{name, ko, properties[]}] (Phase M · ONB-01)
    interfaces: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class OntologyProposal(Base):
    """온톨로지 변경 제안 (Phase M · ONB-09 · Q181) — 연산 목록(ops)을 승인하면 활성 스키마에 적용해 새 판을 만든다.

    status: pending(대기) | applied(적용) | rejected(반려) | superseded(같은 연산이 이미 반영 · 새 제안으로 대체) | failed(적용 검증 실패)
    ops: [{op, ...}] — add_class · update_class · add_property · add_backing · add_relation · update_relation · add_alias (graph.schema.apply_ops)
    """

    __tablename__ = "ontology_proposal"
    __table_args__ = S

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    source: Mapped[str] = mapped_column(String(20), default="agent")  # agent | admin | review
    agent_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    workflow_run_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    title: Mapped[str] = mapped_column(String(200), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    ops: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    impact: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    validation: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    base_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    applied_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    decided_by: Mapped[str | None] = mapped_column(String(40), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class Setting(Base):
    __tablename__ = "setting"
    __table_args__ = S

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[Any] = mapped_column(JSONB)
    description: Mapped[str] = mapped_column(Text, default="")
    updated_by: Mapped[str | None] = mapped_column(String(40), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class Secret(Base):
    """관리자 화면에서 입력한 외부 연결 비밀값 (Phase K · ES-03 · Q154) — 예: es.connection.

    `meta` 는 가리지 않는 값(주소 · 계정), `secret_enc` 는 AES-GCM 암호문(security.encrypt_secret). 설정(`cfg.setting`)과
    분리해 관리자 [운영 설정] 목록 · 설정 요약 API 에 나오지 않게 한다.
    """

    __tablename__ = "secret"
    __table_args__ = S

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    meta: Mapped[Any] = mapped_column(JSONB, default=dict)
    secret_enc: Mapped[str] = mapped_column(Text, default="")
    updated_by: Mapped[str | None] = mapped_column(String(40), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class ColumnContract(Base):
    """컬럼 정의서(화면 데이터 계약) — 업무 담당자가 엑셀로 정의한 '화면 테이블의 컬럼 · 원천 · 산식 · 기대 화면값'.

    binding 은 컬럼을 시스템 값에 연결한다(관리자 화면에서 편집):
      {"metric": 지표코드}                     커널 계산 지표 (값 = 내부 정밀도, 화면값 = 지표 표시값)
      {"base_ym": 데이터셋코드}                데이터셋 최근 기준년월
      {"const": 값}                            고정값(사업부문 등)
      {"version": true}                        값이 바뀔 때마다 증가하는 제안 버전
      {"insight": ID} / {"proposal": ID, "field": "judgement"}   에이전트 서술(Critic 통과분)
      {"unmapped": 사유, "question": "Q15"}     원천·산식 미확정
    """

    __tablename__ = "column_contract"
    __table_args__ = (UniqueConstraint("table_code", "column_name"), S)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    table_code: Mapped[str] = mapped_column(String(10))
    table_name: Mapped[str] = mapped_column(String(100))
    dept: Mapped[str] = mapped_column(String(40))
    seq: Mapped[int] = mapped_column(Integer)
    column_name: Mapped[str] = mapped_column(String(63))
    kor_name: Mapped[str] = mapped_column(String(200))
    is_pk: Mapped[bool] = mapped_column(Boolean, default=False)
    data_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    source_desc: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_column: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_mock: Mapped[bool] = mapped_column(Boolean, default=False)
    expected_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    binding: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    workbook: Mapped[str | None] = mapped_column(String(200), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class BusinessConfig(Base):
    """업무 구성 파일 (Phase O · BIZ-02 · BIZ-05) — 자료 · 지표 · 업무 흐름 · 화면 연결 · 화면 틀 · 규칙 · 조직 · 화면 · 설정 …
    시드 대신 관리자가 올린다. 같은 이름 = 같은 구성의 새 판(활성은 이름마다 하나). owned = 이 구성이 만든 것(지우면 함께 지움)."""

    __tablename__ = "business_config"
    __table_args__ = (UniqueConstraint("name", "version"), S)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150))
    version: Mapped[int] = mapped_column(Integer, default=1)
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="active")  # active | superseded | removed
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    owned: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    report: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    uploaded_by: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class AnalysisAgent(Base):
    """분석 에이전트 (Phase C · DAG · Q100) — 사용자 글을 정제한 분석 명세로 만든 분석. 승인되면 지표 · 워크플로 · 전용 에이전트가 생긴다."""

    __tablename__ = "analysis_agent"
    __table_args__ = S

    code: Mapped[str] = mapped_column(String(40), primary_key=True)  # an_<slug>
    space: Mapped[str] = mapped_column(String(40))  # 분석 공간(부서) — 설정 analysis.spaces 의 키
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(12), default="draft")  # draft | pending | active | paused | retired | rejected
    version: Mapped[int] = mapped_column(Integer, default=0)  # 승인된 명세 버전(0 = 아직 없음)
    spec: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    workflow_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    tab_key: Mapped[str] = mapped_column(String(60))
    requested_by: Mapped[str | None] = mapped_column(String(40), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(40), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class AnalysisAgentVersion(Base):
    """분석 에이전트 명세 버전 — 요청 글 · 정제된 명세 · 검증 · 미리보기 요약 · 승인 기록."""

    __tablename__ = "analysis_agent_version"
    __table_args__ = (UniqueConstraint("agent_code", "version"), S)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_code: Mapped[str] = mapped_column(ForeignKey("cfg.analysis_agent.code", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer)
    source_text: Mapped[str] = mapped_column(Text, default="")
    spec: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    validation: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    preview: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(12), default="pending")  # pending | approved | rejected | superseded
    requested_by: Mapped[str | None] = mapped_column(String(40), nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(40), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
