"""질문하기 통합 지식 색인 (요구사항 §21 · 설계 §21.2) — 컬렉션 정의(cfg)와 분석 결과 청크(app).

문서 청크(bank/ext.chunk)는 그대로 두고, 분석 결과(화면 산출물)를 검색 단위로 바꾼 청크를 여기에 둔다.
같은 테이블 안에서 키워드(tsv) · 의미(embedding) · 개념(concepts) 검색과 팀/지점 사전 필터(collection_code · scope_key)를 함께 쓴다.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, Boolean, Computed, Date, Float, Index, Integer, String, Text
from sqlalchemy import text as sa_text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, utcnow


class KbCollection(Base):
    """컬렉션 — 색인 대상 묶음. 담당 팀 · 공유 팀 · 화면 리소스 · 공개 범위로 팀별 검색 범위를 정한다 (KB-04)."""

    __tablename__ = "kb_collection"
    __table_args__ = {"schema": "cfg"}

    code: Mapped[str] = mapped_column(String(60), primary_key=True)
    label: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(12), default="analysis")  # document | analysis | glossary | catalog
    owner_orgs: Mapped[list[Any]] = mapped_column(JSONB, default=list)  # 담당 팀(조직 코드, 하위 조직 포함)
    shared_orgs: Mapped[list[Any]] = mapped_column(JSONB, default=list)  # 열람을 공유한 팀
    required_resources: Mapped[list[Any]] = mapped_column(JSONB, default=list)  # 이 화면 리소스가 있으면 컬렉션 전체 열람
    audience: Mapped[str] = mapped_column(String(12), default="restricted")  # all | restricted | owner_only
    sources: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)  # 포함 규칙: doc_classes · artifact_keys · artifact_prefixes · spaces · personas · screens
    boost: Mapped[float] = mapped_column(Float, default=0.0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    sort: Mapped[int] = mapped_column(Integer, default=0)
    updated_by: Mapped[str | None] = mapped_column(String(40), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class KbChunk(Base):
    """분석 결과 청크 — 산출물 한 덩어리를 선형화해 나눈 검색 단위 (KB-01 · KB-02)."""

    __tablename__ = "kb_chunk"
    __table_args__ = (
        Index("ix_app_kb_chunk_collection", "collection_code"),
        Index("ix_app_kb_chunk_source", "source_key"),
        Index("ix_app_kb_chunk_tsv", "tsv", postgresql_using="gin"),
        Index("ix_app_kb_chunk_concepts", "concepts", postgresql_using="gin"),
        Index("uq_app_kb_chunk_unit", "source_key", sa_text("COALESCE(scope_key, '')"), "unit_hash", unique=True),
        Index("ix_app_kb_chunk_pending", "id", postgresql_where=sa_text("embedding IS NULL")),
        {"schema": "app"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    collection_code: Mapped[str] = mapped_column(String(60))
    source_kind: Mapped[str] = mapped_column(String(20), default="artifact")
    source_key: Mapped[str] = mapped_column(String(200))  # 산출물 키 (범위 산출물은 '<키>@<지점>')
    source_generation: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unit_hash: Mapped[str] = mapped_column(String(40))  # 본문 SHA-1 앞 40자 — 같은 본문은 같은 행(멱등 · 임베딩 재사용)
    ordinal: Mapped[int] = mapped_column(Integer, default=0)
    scope_key: Mapped[str | None] = mapped_column(String(60), nullable=True)  # 'office:<코드>'
    required_resource: Mapped[str | None] = mapped_column(String(60), nullable=True)  # 그 산출물을 보여 주는 화면 API 리소스
    owner_org: Mapped[str | None] = mapped_column(String(40), nullable=True)
    title: Mapped[str] = mapped_column(String(300), default="")
    section_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    text: Mapped[str] = mapped_column(Text)
    concepts: Mapped[list[str]] = mapped_column(ARRAY(String(80)), default=list, server_default=sa_text("'{}'"))
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    as_of: Mapped[date | None] = mapped_column(Date, nullable=True)
    # 차원은 임베딩 모델에 따라 달라지므로 고정하지 않는다(bank/ext.chunk 와 같음) — 모델 확정 후 부분 HNSW 인덱스(CLI kb-hnsw)
    embedding: Mapped[Any] = mapped_column(Vector(), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    tsv: Mapped[Any] = mapped_column(TSVECTOR, Computed("to_tsvector('simple', coalesce(title, '') || ' ' || text)", persisted=True))
    indexed_at: Mapped[datetime] = mapped_column(default=utcnow)
