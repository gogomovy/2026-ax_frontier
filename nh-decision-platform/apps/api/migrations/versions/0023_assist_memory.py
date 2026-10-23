"""AI 어시스턴트 대화 기억 (2026-10-22) — 사용자별 대화 · 메시지 · 누적 요약

- app.assist_conversation — 대화(사번 · 제목 · 누적 요약 · 요약된 마지막 메시지 번호 · 떠날 때 요약 시각)
- app.assist_message — 질문 · 답 원문(토큰 추정 · 화면 표시 · 도구 호출 조건 meta)

Revision ID: 0023_assist_memory
Revises: 0022_sso_org_sync
Create Date: 2026-10-22
"""
from __future__ import annotations

from alembic import op

revision = "0023_assist_memory"
down_revision = "0022_sso_org_sync"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS app.assist_conversation (
            id VARCHAR(64) PRIMARY KEY,
            emp_no VARCHAR(20) NOT NULL,
            title VARCHAR(120) NOT NULL DEFAULT '새 대화',
            summary TEXT NOT NULL DEFAULT '',
            summary_tokens INTEGER NOT NULL DEFAULT 0,
            summarized_upto INTEGER NOT NULL DEFAULT 0,
            summary_by VARCHAR(12),
            message_count INTEGER NOT NULL DEFAULT 0,
            last_seq INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            closed_at TIMESTAMPTZ
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_app_assist_conversation_emp_no ON app.assist_conversation (emp_no)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_app_assist_conversation_emp_updated ON app.assist_conversation (emp_no, updated_at)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS app.assist_message (
            id BIGSERIAL PRIMARY KEY,
            conversation_id VARCHAR(64) NOT NULL REFERENCES app.assist_conversation(id) ON DELETE CASCADE,
            seq INTEGER NOT NULL,
            role VARCHAR(10) NOT NULL,
            text TEXT NOT NULL DEFAULT '',
            tokens INTEGER NOT NULL DEFAULT 0,
            meta JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_app_assist_message_conv_seq ON app.assist_message (conversation_id, seq)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS app.assist_message")
    op.execute("DROP TABLE IF EXISTS app.assist_conversation")
