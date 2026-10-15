"""Phase O (2026-10-15) — 업무 구성 파일 (요구사항 §32 · BIZ-02 · BIZ-05)
- cfg.business_config — 관리자가 올린 업무 구성(자료 · 지표 · 업무 흐름 · 화면 연결 · 화면 틀 · 규칙 · 조직 · 화면 · 설정 …).
  같은 이름 = 같은 구성의 새 판. owned = 이 구성이 만든 것(지우면 함께 지움).
Revision ID: 0018_business_config
Revises: 0017_agentic_ontology
Create Date: 2026-10-15
"""
from __future__ import annotations

from alembic import op

revision = "0018_business_config"
down_revision = "0017_agentic_ontology"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cfg.business_config (
            id SERIAL PRIMARY KEY,
            name VARCHAR(150) NOT NULL,
            version INTEGER NOT NULL DEFAULT 1,
            file_name VARCHAR(255) NULL,
            sha256 VARCHAR(64) NULL,
            status VARCHAR(12) NOT NULL DEFAULT 'active',
            content JSONB NOT NULL DEFAULT '{}'::jsonb,
            owned JSONB NOT NULL DEFAULT '{}'::jsonb,
            report JSONB NOT NULL DEFAULT '{}'::jsonb,
            uploaded_by VARCHAR(40) NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (name, version)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_cfg_business_config_status ON cfg.business_config (status, name)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS cfg.business_config")
