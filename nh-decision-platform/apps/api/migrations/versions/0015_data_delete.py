"""Phase J (2026-10-13) — 업로드 자료 삭제 (DEL-01~08 · Q143~Q147)
- iam.app_user.data_admin — 데이터 관리자(업로드 자료 삭제 권한). 관리자(role=admin) 중 지정된 사람만 삭제한다
- {bank,ext}.dataset_version · {bank,ext}.document — 삭제 표시(deleted_at · deleted_by · delete_reason).
  내용(행 · 본문 · 청크 · 원본 파일)은 지우고 메타만 남긴다 — 버전 번호 재사용 방지 · 감사 추적
- ops.purge_task — 외부 저장소(Elasticsearch 색인 · Neo4j 그래프) 삭제 작업. 워커가 끝날 때까지 다시 시도한다
Revision ID: 0015_data_delete
Revises: 0014_knowledge_index
Create Date: 2026-10-13
"""
from __future__ import annotations

from alembic import op

revision = "0015_data_delete"
down_revision = "0014_knowledge_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE iam.app_user ADD COLUMN IF NOT EXISTS data_admin BOOLEAN NOT NULL DEFAULT false")
    for schema in ("bank", "ext"):
        for table in ("dataset_version", "document"):
            op.execute(f"ALTER TABLE {schema}.{table} ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ NULL")
            op.execute(f"ALTER TABLE {schema}.{table} ADD COLUMN IF NOT EXISTS deleted_by VARCHAR(40) NULL")
            op.execute(f"ALTER TABLE {schema}.{table} ADD COLUMN IF NOT EXISTS delete_reason TEXT NULL")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ops.purge_task (
            id SERIAL PRIMARY KEY,
            store VARCHAR(12) NOT NULL,
            subject_kind VARCHAR(20) NOT NULL,
            subject_ref VARCHAR(200) NOT NULL,
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            status VARCHAR(12) NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT NULL,
            result JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_by VARCHAR(40) NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            done_at TIMESTAMPTZ NULL
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_ops_purge_task_status ON ops.purge_task (status, id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ops.purge_task")
    for schema in ("bank", "ext"):
        for table in ("dataset_version", "document"):
            for col in ("deleted_at", "deleted_by", "delete_reason"):
                op.execute(f"ALTER TABLE {schema}.{table} DROP COLUMN IF EXISTS {col}")
    op.execute("ALTER TABLE iam.app_user DROP COLUMN IF EXISTS data_admin")
