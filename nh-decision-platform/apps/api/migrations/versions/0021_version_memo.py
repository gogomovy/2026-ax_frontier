"""판 메모 · 요청자 (2026-10-16) — 같은 자료를 날짜별로 올릴 때 판을 알아보기 쉽게 (Phase P · UPV-06)
- bank/ext.dataset_version.memo — 요청자가 적은 메모(승인 기록 note 와 따로)
- bank/ext.dataset_version.requested_by — 자료를 요청한 사람(uploaded_by 는 승인 · 반영한 사람)
- 예전 판: 승인된 업무 자료 요청의 meta.note · requested_by 로 채운다
Revision ID: 0021_version_memo
Revises: 0020_common_db
Create Date: 2026-10-16
"""
from __future__ import annotations

from alembic import op

revision = "0021_version_memo"
down_revision = "0020_common_db"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for schema in ("bank", "ext"):
        op.execute(f"ALTER TABLE {schema}.dataset_version ADD COLUMN IF NOT EXISTS memo TEXT")
        op.execute(f"ALTER TABLE {schema}.dataset_version ADD COLUMN IF NOT EXISTS requested_by VARCHAR(40)")
        op.execute(
            f"UPDATE {schema}.dataset_version v SET memo = NULLIF(r.meta->>'note', ''), requested_by = r.requested_by FROM ops.upload_request r "
            f"WHERE r.status = 'approved' AND r.kind = 'dataset' AND r.origin = '{schema}' AND (r.result->>'versionId') ~ '^[0-9]+$' "
            f"AND v.id = (r.result->>'versionId')::int AND v.requested_by IS NULL"
        )


def downgrade() -> None:
    for schema in ("bank", "ext"):
        op.execute(f"ALTER TABLE {schema}.dataset_version DROP COLUMN IF EXISTS memo")
        op.execute(f"ALTER TABLE {schema}.dataset_version DROP COLUMN IF EXISTS requested_by")
