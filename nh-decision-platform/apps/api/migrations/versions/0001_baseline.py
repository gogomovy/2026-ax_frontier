"""baseline — 스키마(iam/cfg/bank/ext/calc/app/ops/audit) + pgvector + 전체 테이블

이후 변경은 `alembic revision --autogenerate` 로 추가한다.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-10-06
"""
from __future__ import annotations

from alembic import op

from nhdip.db import SCHEMAS
from nhdip.models import Base

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    for schema in SCHEMAS:
        op.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    for schema in reversed(SCHEMAS):
        op.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
