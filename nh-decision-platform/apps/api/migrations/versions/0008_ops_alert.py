"""운영 알림 (작업 8.5) — ops.alert

Revision ID: 0008_ops_alert
Revises: 0007_chunk_section_path
Create Date: 2026-10-10
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0008_ops_alert"
down_revision = "0007_chunk_section_path"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("alert", schema="ops"):
        return
    op.create_table(
        "alert",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("severity", sa.String(12), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("detail", JSONB, nullable=False, server_default="{}"),
        sa.Column("dedupe_key", sa.String(200), nullable=False),
        sa.Column("channels", JSONB, nullable=False, server_default="{}"),
        sa.Column("status", sa.String(20), nullable=False, server_default="logged"),
        sa.Column("trace_id", sa.String(32), nullable=True),
        schema="ops",
    )
    op.create_index("ix_ops_alert_at", "alert", ["at"], schema="ops")
    op.create_index("ix_ops_alert_kind", "alert", ["kind"], schema="ops")
    op.create_index("ix_ops_alert_dedupe_key", "alert", ["dedupe_key"], schema="ops")


def downgrade() -> None:
    op.drop_table("alert", schema="ops")
