"""컬럼 정의서(화면 데이터 계약) — cfg.column_contract + mart 스키마

mart.* 테이블은 컬럼 정의서의 TYPE 으로 실행 시점에 생성·확장된다(contracts/materialize.py).

Revision ID: 0004_column_contract
Revises: 0003_trigger_cron
Create Date: 2026-10-10
"""
from __future__ import annotations

from alembic import op

from nhdip.models import Base

revision = "0004_column_contract"
down_revision = "0003_trigger_cron"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE SCHEMA IF NOT EXISTS "mart"')
    Base.metadata.tables["cfg.column_contract"].create(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    op.drop_table("column_contract", schema="cfg")
    op.execute('DROP SCHEMA IF EXISTS "mart" CASCADE')
