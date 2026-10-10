"""에이전트 결정 기록 (B.30) — ops.agent_decision

Revision ID: 0009_agent_decision
Revises: 0008_ops_alert
Create Date: 2026-10-10
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0009_agent_decision"
down_revision = "0008_ops_alert"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("agent_decision", schema="ops"):
        return
    op.create_table(
        "agent_decision",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("agent_code", sa.String(60), nullable=False),
        sa.Column("workflow_code", sa.String(60), nullable=True),
        sa.Column("job_id", sa.BigInteger, nullable=True),
        sa.Column("workflow_run_id", sa.String(32), nullable=True),
        sa.Column("decision", sa.String(30), nullable=False),
        sa.Column("summary", sa.String(500), nullable=False, server_default=""),
        sa.Column("detail", JSONB, nullable=False, server_default="{}"),
        sa.Column("trace_id", sa.String(32), nullable=True),
        schema="ops",
    )
    op.create_index("ix_ops_agent_decision_at", "agent_decision", ["at"], schema="ops")
    op.create_index("ix_ops_agent_decision_agent_at", "agent_decision", ["agent_code", "at"], schema="ops")
    op.create_index("ix_ops_agent_decision_workflow_code", "agent_decision", ["workflow_code"], schema="ops")
    op.create_index("ix_ops_agent_decision_workflow_run_id", "agent_decision", ["workflow_run_id"], schema="ops")


def downgrade() -> None:
    op.drop_table("agent_decision", schema="ops")
