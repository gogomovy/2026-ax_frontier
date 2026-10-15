"""자료 소유 조직 (2026-10-14) — 올린 팀 · 영업점 단위 자료 (요구사항 §33 OWN)
- bank/ext.dataset_version.owner_org · bank/ext.document.owner_org — 올린 사람의 소속(관리자는 올릴 때 고름). 없으면 전행 공통
- 예전 자료: 승인된 업무 자료 요청이 만든 판 · 문서는 요청 부서(requested_org)로 채운다
Revision ID: 0019_owner_org
Revises: 0018_business_config
Create Date: 2026-10-14
"""
from __future__ import annotations

from alembic import op

revision = "0019_owner_org"
down_revision = "0018_business_config"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for schema in ("bank", "ext"):
        for table in ("dataset_version", "document"):
            op.execute(f"ALTER TABLE {schema}.{table} ADD COLUMN IF NOT EXISTS owner_org VARCHAR(32)")
            op.execute(f"CREATE INDEX IF NOT EXISTS ix_{schema}_{table}_owner_org ON {schema}.{table} (owner_org)")
        op.execute(
            f"UPDATE {schema}.dataset_version v SET owner_org = r.requested_org FROM ops.upload_request r "
            f"WHERE r.status = 'approved' AND r.kind = 'dataset' AND r.origin = '{schema}' AND (r.result->>'versionId') ~ '^[0-9]+$' "
            f"AND v.id = (r.result->>'versionId')::int AND v.owner_org IS NULL"
        )
        op.execute(
            f"UPDATE {schema}.document d SET owner_org = r.requested_org FROM ops.upload_request r "
            f"WHERE r.status = 'approved' AND r.kind = 'document' AND r.origin = '{schema}' AND (r.result->>'documentId') ~ '^[0-9]+$' "
            f"AND d.id = (r.result->>'documentId')::int AND d.owner_org IS NULL"
        )


def downgrade() -> None:
    for schema in ("bank", "ext"):
        for table in ("dataset_version", "document"):
            op.execute(f"DROP INDEX IF EXISTS {schema}.ix_{schema}_{table}_owner_org")
            op.execute(f"ALTER TABLE {schema}.{table} DROP COLUMN IF EXISTS owner_org")
