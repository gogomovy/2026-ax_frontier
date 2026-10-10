"""조직 유형(본부 · 부 · 국 · 팀 · 지역본부 · 영업점) — iam.org_unit.unit_type

요구사항 Q12 확정: 본부 · 지역본부 · 영업점까지 하나의 조직 트리로 관리한다.
기존 조직의 유형 지정·상위 본부 연결·깊이 재계산은 시드(멱등)가 수행한다.

Revision ID: 0002_org_unit_type
Revises: 0001_baseline
Create Date: 2026-10-06
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_org_unit_type"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    cols = {c["name"] for c in insp.get_columns("org_unit", schema="iam")}
    # 0001 이 현재 모델로 create_all 한 새 DB 에는 이미 있다
    if "unit_type" not in cols:
        op.add_column("org_unit", sa.Column("unit_type", sa.String(length=20), nullable=True), schema="iam")


def downgrade() -> None:
    op.drop_column("org_unit", "unit_type", schema="iam")
