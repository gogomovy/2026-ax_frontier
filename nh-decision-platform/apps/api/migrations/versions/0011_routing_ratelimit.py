"""경로 판단 선점 · 공유 속도 제한 (B.33)

- ops.outbox_event.routing_at — LLM 경로 판단을 시작한 시각. 여러 워커가 같은 이벤트를 동시에 판단하지 않도록 선점한다.
- ops.rate_limit — 여러 API 프로세스가 함께 쓰는 고정 창 요청 카운터(UNLOGGED: 재시작 시 비워져도 무방)

Revision ID: 0011_routing_ratelimit
Revises: 0010_hardening_indexes
Create Date: 2026-10-10
"""
from __future__ import annotations

from alembic import op

revision = "0011_routing_ratelimit"
down_revision = "0010_hardening_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE ops.outbox_event ADD COLUMN IF NOT EXISTS routing_at TIMESTAMPTZ NULL")
    op.execute(
        "CREATE UNLOGGED TABLE IF NOT EXISTS ops.rate_limit ("
        " key VARCHAR(200) PRIMARY KEY,"
        " window_start TIMESTAMPTZ NOT NULL DEFAULT now(),"
        " count INTEGER NOT NULL DEFAULT 0)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ops.rate_limit")
    op.execute("ALTER TABLE ops.outbox_event DROP COLUMN IF EXISTS routing_at")
