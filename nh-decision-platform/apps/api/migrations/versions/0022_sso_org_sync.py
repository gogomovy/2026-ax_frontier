"""사내 SSO(INISAFE Nexess 티켓) · 조직/인사 .dat 동기화 (2026-10-17 · Phase R)
- iam.app_user.emp_no · iam.session.emp_no — 8 → 20자. 인사 .dat 개인번호(9자리) · 외부 직원(영문 포함) 사번을 받는다(기존 8자리 사번은 그대로)
- iam.app_user.source — local(가입 신청) · dat(인사 동기화) · sso(SSO 자동 생성). hr — 인사 .dat 원천 필드(법인 · 직급 · 소속 경로 등)
- iam.org_unit.source — manual(관리자 · 업무 구성) · dat(조직 동기화). ext — 조직 .dat 원천 필드(법인 · 본부 · 시도 · 트리 레벨 등)
Revision ID: 0022_sso_org_sync
Revises: 0021_version_memo
Create Date: 2026-10-17
"""
from __future__ import annotations

from alembic import op

revision = "0022_sso_org_sync"
down_revision = "0021_version_memo"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE iam.app_user ALTER COLUMN emp_no TYPE VARCHAR(20)")
    op.execute("ALTER TABLE iam.session ALTER COLUMN emp_no TYPE VARCHAR(20)")
    op.execute("ALTER TABLE iam.app_user ADD COLUMN IF NOT EXISTS source VARCHAR(10) NOT NULL DEFAULT 'local'")
    op.execute("ALTER TABLE iam.app_user ADD COLUMN IF NOT EXISTS hr JSONB NOT NULL DEFAULT '{}'::jsonb")
    op.execute("ALTER TABLE iam.org_unit ADD COLUMN IF NOT EXISTS source VARCHAR(10) NOT NULL DEFAULT 'manual'")
    op.execute("ALTER TABLE iam.org_unit ADD COLUMN IF NOT EXISTS ext JSONB NOT NULL DEFAULT '{}'::jsonb")
    op.execute("CREATE INDEX IF NOT EXISTS ix_iam_app_user_source ON iam.app_user (source)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_iam_org_unit_source ON iam.org_unit (source)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS iam.ix_iam_org_unit_source")
    op.execute("DROP INDEX IF EXISTS iam.ix_iam_app_user_source")
    op.execute("ALTER TABLE iam.org_unit DROP COLUMN IF EXISTS ext")
    op.execute("ALTER TABLE iam.org_unit DROP COLUMN IF EXISTS source")
    op.execute("ALTER TABLE iam.app_user DROP COLUMN IF EXISTS hr")
    op.execute("ALTER TABLE iam.app_user DROP COLUMN IF EXISTS source")
    # 사번 길이는 되돌리지 않는다(9자리 이상 사번이 있으면 실패하므로)
