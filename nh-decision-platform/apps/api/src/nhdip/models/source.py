"""bank / ext — 출처별 원천 저장 (당행 데이터와 외부 데이터를 스키마로 분리, ING-01).

두 스키마는 같은 구조를 가지며, 아래 팩토리로 클래스를 각각 만든다.
  dataset_version · row_store  : 데이터셋 정의 기반 정형 데이터 (JSONB 행 저장)
  document · chunk             : 비정형 문서와 청크 (pgvector 임베딩 + 전문 검색)
"""
from __future__ import annotations

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, Boolean, Column, Computed, Date, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR

from .base import Base, utcnow


def _ts(**kw):
    return Column(DateTime(timezone=True), **kw)


def _make(schema: str, prefix: str):
    version = type(
        f"{prefix}DatasetVersion",
        (Base,),
        {
            "__tablename__": "dataset_version",
            "__table_args__": {"schema": schema},
            "id": Column(Integer, primary_key=True, autoincrement=True),
            "dataset_code": Column(String(60), ForeignKey("cfg.dataset.code", ondelete="CASCADE"), index=True, nullable=False),
            "version": Column(Integer, nullable=False),
            "as_of": Column(Date, nullable=True),
            "data_origin": Column(String(10), default="simulated", nullable=False),  # actual | simulated
            "status": Column(String(12), default="staged", nullable=False),  # staged|committed|rolled_back|rejected|deleted
            "is_current": Column(Boolean, default=False, nullable=False),
            "file_name": Column(String(300)),
            "file_sha256": Column(String(64)),
            "file_path": Column(String(500)),
            "row_count": Column(Integer, default=0, nullable=False),
            "quality": Column(JSONB, default=dict, nullable=False),
            "note": Column(Text),
            "uploaded_by": Column(String(40)),
            # 요청자 메모 · 요청자 (Phase P · UPV-06) — note 는 승인 기록, uploaded_by 는 반영한 사람
            "memo": Column(Text),
            "requested_by": Column(String(40)),
            # 자료 소유 조직(팀 · 영업점) — 올린 사람의 소속, 관리자는 올릴 때 고른다. 없으면 전행 공통 (요구사항 §33 OWN)
            "owner_org": Column(String(32), index=True),
            "created_at": _ts(default=utcnow, nullable=False),
            "committed_at": _ts(nullable=True),
            # 삭제 표시 (Phase J · Q145) — 행 · 원본 파일은 지우고 메타만 남긴다(status=deleted, 버전 번호 재사용 방지)
            "deleted_at": _ts(nullable=True),
            "deleted_by": Column(String(40)),
            "delete_reason": Column(Text),
        },
    )
    row = type(
        f"{prefix}RowStore",
        (Base,),
        {
            "__tablename__": "row_store",
            "__table_args__": (Index(f"ix_{schema}_row_store_data", "data", postgresql_using="gin"), {"schema": schema}),
            "id": Column(BigInteger, primary_key=True, autoincrement=True),
            "version_id": Column(Integer, ForeignKey(f"{schema}.dataset_version.id", ondelete="CASCADE"), index=True, nullable=False),
            "dataset_code": Column(String(60), index=True, nullable=False),
            "row_no": Column(Integer, nullable=False),
            "row_key": Column(String(300), index=True),
            "as_of": Column(Date),
            "data": Column(JSONB, nullable=False),
        },
    )
    document = type(
        f"{prefix}Document",
        (Base,),
        {
            "__tablename__": "document",
            "__table_args__": {"schema": schema},
            "id": Column(Integer, primary_key=True, autoincrement=True),
            "doc_code": Column(String(80), index=True, nullable=False),
            "version": Column(Integer, default=1, nullable=False),
            "is_current": Column(Boolean, default=True, nullable=False),
            "title": Column(String(300), nullable=False),
            # gov_policy | mgmt_decision | model_method | term | reference ...
            "doc_class": Column(String(40), index=True, nullable=False),
            "issuer": Column(String(100)),
            "published_at": Column(Date),
            "file_name": Column(String(300)),
            "file_sha256": Column(String(64)),
            "file_path": Column(String(500)),
            "mime": Column(String(100)),
            "text": Column(Text, default="", nullable=False),
            "meta": Column(JSONB, default=dict, nullable=False),
            "status": Column(String(12), default="ingested", nullable=False),  # ingested|extracted|partial|failed|deleted
            "extraction": Column(JSONB, default=dict, nullable=False),
            "uploaded_by": Column(String(40)),
            "owner_org": Column(String(32), index=True),  # 자료 소유 조직(팀 · 영업점) — 없으면 전행 공통
            "created_at": _ts(default=utcnow, nullable=False),
            # 삭제 표시 (Phase J · Q145) — 본문 · 청크 · 추출 · 원본 파일은 지우고 메타만 남긴다(status=deleted)
            "deleted_at": _ts(nullable=True),
            "deleted_by": Column(String(40)),
            "delete_reason": Column(Text),
        },
    )
    chunk = type(
        f"{prefix}Chunk",
        (Base,),
        {
            "__tablename__": "chunk",
            "__table_args__": (Index(f"ix_{schema}_chunk_tsv", "tsv", postgresql_using="gin"), {"schema": schema}),
            "id": Column(Integer, primary_key=True, autoincrement=True),
            "document_id": Column(Integer, ForeignKey(f"{schema}.document.id", ondelete="CASCADE"), index=True, nullable=False),
            "seq": Column(Integer, nullable=False),
            "page": Column(Integer),
            "section_path": Column(String(500)),  # 문서 구조 경로 (예: 'Ⅱ. 추진 방향 > 1. 공급 확대 > 가. 대상')
            "text": Column(Text, nullable=False),
            # 차원은 임베딩 모델에 따라 달라지므로 고정하지 않는다(소규모 → 순차 탐색으로 충분)
            "embedding": Column(Vector(), nullable=True),
            "embedding_model": Column(String(200)),
            "tsv": Column(TSVECTOR, Computed("to_tsvector('simple', text)", persisted=True)),
        },
    )
    return version, row, document, chunk


BankDatasetVersion, BankRowStore, BankDocument, BankChunk = _make("bank", "Bank")
ExtDatasetVersion, ExtRowStore, ExtDocument, ExtChunk = _make("ext", "Ext")


class SourceTables:
    def __init__(self, origin, version, row, document, chunk):
        self.origin = origin
        self.version = version
        self.row = row
        self.document = document
        self.chunk = chunk


SOURCES: dict[str, SourceTables] = {
    "bank": SourceTables("bank", BankDatasetVersion, BankRowStore, BankDocument, BankChunk),
    "ext": SourceTables("ext", ExtDatasetVersion, ExtRowStore, ExtDocument, ExtChunk),
}


def source(origin: str) -> SourceTables:
    if origin not in SOURCES:
        raise ValueError(f"unknown origin: {origin}")
    return SOURCES[origin]
