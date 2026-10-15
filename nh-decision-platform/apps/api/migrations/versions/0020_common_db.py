"""공통 통합 DB (2026-10-16) — 모든 부서가 함께 보는 자료 (요구사항 §38 CMN)
- cfg.dataset.common — 공통 통합 DB 자료(관리자만 올림 · 소유 팀 없음 · 모든 부서 흐름 · 질의 · 온톨로지가 함께 씀)
- 공통 문서는 문서 분류(설정 common.doc_classes, 기본 common_ref)로 구분한다 — 표는 바꾸지 않는다
Revision ID: 0020_common_db
Revises: 0019_owner_org
Create Date: 2026-10-16
"""
from __future__ import annotations

from alembic import op

revision = "0020_common_db"
down_revision = "0019_owner_org"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE cfg.dataset ADD COLUMN IF NOT EXISTS common BOOLEAN NOT NULL DEFAULT false")


def downgrade() -> None:
    op.execute("ALTER TABLE cfg.dataset DROP COLUMN IF EXISTS common")
