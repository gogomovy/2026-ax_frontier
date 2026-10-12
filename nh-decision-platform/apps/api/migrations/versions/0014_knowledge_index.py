"""Phase D (2026-10-12) — 질문하기 통합 지식 색인 (KB-01 · KB-04 · 요구사항 §21 · 설계 §21.2)
- cfg.kb_collection — 컬렉션(담당/공유 팀 · 화면 리소스 · 공개 범위 · 포함 규칙)
- app.kb_chunk — 분석 결과 청크(tsvector 생성 열 · 개념 배열 · 임베딩 · 팀/지점 사전 필터 열)

새 DB 는 0001 baseline 의 create_all 이 이미 만들므로 모두 IF NOT EXISTS.
Revision ID: 0014_knowledge_index
Revises: 0013_data_steward
Create Date: 2026-10-12
"""
from __future__ import annotations

from alembic import op

revision = "0014_knowledge_index"
down_revision = "0013_data_steward"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        "CREATE TABLE IF NOT EXISTS cfg.kb_collection ("
        " code VARCHAR(60) PRIMARY KEY,"
        " label VARCHAR(100) NOT NULL,"
        " description TEXT NOT NULL DEFAULT '',"
        " kind VARCHAR(12) NOT NULL DEFAULT 'analysis',"
        " owner_orgs JSONB NOT NULL DEFAULT '[]'::jsonb,"
        " shared_orgs JSONB NOT NULL DEFAULT '[]'::jsonb,"
        " required_resources JSONB NOT NULL DEFAULT '[]'::jsonb,"
        " audience VARCHAR(12) NOT NULL DEFAULT 'restricted',"
        " sources JSONB NOT NULL DEFAULT '{}'::jsonb,"
        " boost DOUBLE PRECISION NOT NULL DEFAULT 0,"
        " enabled BOOLEAN NOT NULL DEFAULT true,"
        " sort INTEGER NOT NULL DEFAULT 0,"
        " updated_by VARCHAR(40) NULL,"
        " updated_at TIMESTAMPTZ NOT NULL DEFAULT now())"
    )
    op.execute(
        "CREATE TABLE IF NOT EXISTS app.kb_chunk ("
        " id BIGSERIAL PRIMARY KEY,"
        " collection_code VARCHAR(60) NOT NULL,"
        " source_kind VARCHAR(20) NOT NULL DEFAULT 'artifact',"
        " source_key VARCHAR(200) NOT NULL,"
        " source_generation INTEGER NULL,"
        " unit_hash VARCHAR(40) NOT NULL,"
        " ordinal INTEGER NOT NULL DEFAULT 0,"
        " scope_key VARCHAR(60) NULL,"
        " required_resource VARCHAR(60) NULL,"
        " owner_org VARCHAR(40) NULL,"
        " title VARCHAR(300) NOT NULL DEFAULT '',"
        " section_path VARCHAR(500) NULL,"
        " text TEXT NOT NULL,"
        " concepts VARCHAR(80)[] NOT NULL DEFAULT '{}',"
        " meta JSONB NOT NULL DEFAULT '{}'::jsonb,"
        " as_of DATE NULL,"
        " embedding vector NULL,"
        " embedding_model VARCHAR(200) NULL,"
        " tsv tsvector GENERATED ALWAYS AS (to_tsvector('simple', coalesce(title, '') || ' ' || text)) STORED,"
        " indexed_at TIMESTAMPTZ NOT NULL DEFAULT now())"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_app_kb_chunk_collection ON app.kb_chunk (collection_code)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_app_kb_chunk_source ON app.kb_chunk (source_key)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_app_kb_chunk_tsv ON app.kb_chunk USING gin (tsv)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_app_kb_chunk_concepts ON app.kb_chunk USING gin (concepts)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_app_kb_chunk_unit ON app.kb_chunk (source_key, COALESCE(scope_key, ''), unit_hash)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_app_kb_chunk_pending ON app.kb_chunk (id) WHERE embedding IS NULL")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS app.kb_chunk")
    op.execute("DROP TABLE IF EXISTS cfg.kb_collection")
