"""audit.audit_log append-only 강제 (작업 1.1.5)

UPDATE · DELETE · TRUNCATE 를 트리거로 막고, PUBLIC 의 수정 권한을 회수한다.
되돌리기: `alembic downgrade 0004_column_contract` (트리거 · 함수 삭제).

Revision ID: 0005_audit_append_only
Revises: 0004_column_contract
Create Date: 2026-10-10
"""
from __future__ import annotations

from alembic import op

revision = "0005_audit_append_only"
down_revision = "0004_column_contract"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION audit.forbid_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION 'audit.audit_log 는 추가만 허용됩니다 (% 차단)', TG_OP
            USING ERRCODE = 'insufficient_privilege';
        END;
        $$;
        """
    )
    op.execute("DROP TRIGGER IF EXISTS audit_log_no_update_delete ON audit.audit_log")
    op.execute("DROP TRIGGER IF EXISTS audit_log_no_truncate ON audit.audit_log")
    op.execute(
        "CREATE TRIGGER audit_log_no_update_delete BEFORE UPDATE OR DELETE ON audit.audit_log "
        "FOR EACH ROW EXECUTE FUNCTION audit.forbid_mutation()"
    )
    op.execute(
        "CREATE TRIGGER audit_log_no_truncate BEFORE TRUNCATE ON audit.audit_log "
        "FOR EACH STATEMENT EXECUTE FUNCTION audit.forbid_mutation()"
    )
    op.execute("REVOKE UPDATE, DELETE, TRUNCATE ON audit.audit_log FROM PUBLIC")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_log_no_truncate ON audit.audit_log")
    op.execute("DROP TRIGGER IF EXISTS audit_log_no_update_delete ON audit.audit_log")
    op.execute("DROP FUNCTION IF EXISTS audit.forbid_mutation()")
