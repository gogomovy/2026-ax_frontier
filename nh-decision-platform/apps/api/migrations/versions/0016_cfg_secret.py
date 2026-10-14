"""Phase K (2026-10-14) — 관리자 입력 외부 연결 비밀값 (ES-03 · Q154)
- cfg.secret — 관리자 화면에서 입력한 연결 정보(예: es.connection = Elasticsearch 주소 · 계정 · 비밀번호).
  비밀번호는 AES-GCM 암호문(secret_enc), 주소 · 계정은 meta. 운영 설정(cfg.setting)과 분리해 설정 목록 API 에 나오지 않는다
Revision ID: 0016_cfg_secret
Revises: 0015_data_delete
Create Date: 2026-10-14
"""
from __future__ import annotations

from alembic import op

revision = "0016_cfg_secret"
down_revision = "0015_data_delete"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cfg.secret (
            key VARCHAR(80) PRIMARY KEY,
            meta JSONB NOT NULL DEFAULT '{}'::jsonb,
            secret_enc TEXT NOT NULL DEFAULT '',
            updated_by VARCHAR(40) NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS cfg.secret")
