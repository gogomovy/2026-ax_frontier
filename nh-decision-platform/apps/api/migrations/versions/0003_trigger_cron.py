"""cron 트리거 — cfg.workflow_trigger.last_fired_at (정기 실행 · 일배치)

Revision ID: 0003_trigger_cron
Revises: 0002_org_unit_type
Create Date: 2026-10-06
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_trigger_cron"
down_revision = "0002_org_unit_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("workflow_trigger", schema="cfg")}
    if "last_fired_at" not in cols:
        op.add_column("workflow_trigger", sa.Column("last_fired_at", sa.DateTime(timezone=True), nullable=True), schema="cfg")


def downgrade() -> None:
    op.drop_column("workflow_trigger", "last_fired_at", schema="cfg")
