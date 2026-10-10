"""청크 문서 구조 경로 (작업 3.2.3) — bank.chunk · ext.chunk.section_path

Revision ID: 0007_chunk_section_path
Revises: 0006_trace_id
Create Date: 2026-10-10
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007_chunk_section_path"
down_revision = "0006_trace_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    for schema in ("bank", "ext"):
        if "section_path" not in {c["name"] for c in insp.get_columns("chunk", schema=schema)}:
            op.add_column("chunk", sa.Column("section_path", sa.String(500), nullable=True), schema=schema)


def downgrade() -> None:
    for schema in ("bank", "ext"):
        op.drop_column("chunk", "section_path", schema=schema)
