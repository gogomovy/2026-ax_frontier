"""관측성 — 추적 ID 컬럼 + HTTP 요청 구간 (작업 0.5 · NFR-09)

trace_id: ops.outbox_event · ops.workflow_run · ops.llm_call · audit.audit_log
ops.request_log: 변경 요청 · 오류 · 느린 조회의 구간(소요 · DB 질의 수/소요 · 사용자)

Revision ID: 0006_trace_id
Revises: 0005_audit_append_only
Create Date: 2026-10-10
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_trace_id"
down_revision = "0005_audit_append_only"
branch_labels = None
depends_on = None

TABLES = [("ops", "outbox_event"), ("ops", "workflow_run"), ("ops", "llm_call"), ("audit", "audit_log")]


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    for schema, table in TABLES:
        cols = {c["name"] for c in insp.get_columns(table, schema=schema)}
        if "trace_id" not in cols:
            op.add_column(table, sa.Column("trace_id", sa.String(32), nullable=True), schema=schema)
            op.create_index(f"ix_{schema}_{table}_trace_id", table, ["trace_id"], schema=schema)
    if not insp.has_table("request_log", schema="ops"):
        op.create_table(
            "request_log",
            sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
            sa.Column("trace_id", sa.String(32), nullable=False),
            sa.Column("at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("method", sa.String(8), nullable=False),
            sa.Column("path", sa.String(300), nullable=False),
            sa.Column("route", sa.String(300), nullable=True),
            sa.Column("status", sa.Integer, nullable=False),
            sa.Column("duration_ms", sa.Integer, nullable=False),
            sa.Column("db_queries", sa.Integer, nullable=False, server_default="0"),
            sa.Column("db_ms", sa.Integer, nullable=False, server_default="0"),
            sa.Column("actor", sa.String(40), nullable=True),
            schema="ops",
        )
        op.create_index("ix_ops_request_log_trace_id", "request_log", ["trace_id"], schema="ops")
        op.create_index("ix_ops_request_log_at", "request_log", ["at"], schema="ops")


def downgrade() -> None:
    op.drop_table("request_log", schema="ops")
    for schema, table in TABLES:
        op.drop_index(f"ix_{schema}_{table}_trace_id", table_name=table, schema=schema)
        op.drop_column(table, "trace_id", schema=schema)
