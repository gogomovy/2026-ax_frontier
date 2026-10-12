"""Phase C 후속 (2026-10-12) — 부서 데이터 책임자 (UPL-04 · Q107)
- iam.app_user.data_steward — 관리자가 지정한 부서 데이터 책임자. 자기 부서(가장 가까운 부 · 지역본부) 사용자의 자료 요청을 승인 · 반려한다
Revision ID: 0013_data_steward
Revises: 0012_phase_c
Create Date: 2026-10-12
"""
from __future__ import annotations

from alembic import op

revision = "0013_data_steward"
down_revision = "0012_phase_c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE iam.app_user ADD COLUMN IF NOT EXISTS data_steward BOOLEAN NOT NULL DEFAULT false")


def downgrade() -> None:
    op.execute("ALTER TABLE iam.app_user DROP COLUMN IF EXISTS data_steward")
