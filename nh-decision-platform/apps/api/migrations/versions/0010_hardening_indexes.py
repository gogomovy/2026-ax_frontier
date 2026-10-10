"""점검 보완 인덱스 (B.32) — 에이전트 결정 조회 · 데이터셋 버전 번호 유일성

Revision ID: 0010_hardening_indexes
Revises: 0009_agent_decision
Create Date: 2026-10-10
"""
from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op

revision = "0010_hardening_indexes"
down_revision = "0009_agent_decision"
branch_labels = None
depends_on = None
log = logging.getLogger("alembic.0010")


def upgrade() -> None:
    bind = op.get_bind()
    # 변화 감지의 '직전 감지 기록' · 모니터 화면 조회
    op.execute("CREATE INDEX IF NOT EXISTS ix_ops_agent_decision_agent_wf_decision ON ops.agent_decision (agent_code, workflow_code, decision, id DESC)")
    # 동시 업로드로 같은 버전 번호가 생기지 않도록 — 이미 겹친 버전이 있으면 일반 인덱스로 두고 경고
    for schema in ("bank", "ext"):
        if not sa.inspect(bind).has_table("dataset_version", schema=schema):
            continue
        dup = bind.execute(sa.text(f"SELECT count(*) FROM (SELECT dataset_code, version FROM {schema}.dataset_version GROUP BY 1, 2 HAVING count(*) > 1) d")).scalar()
        if dup:
            log.warning("%s.dataset_version 에 겹친 버전 번호 %d건 — 유일 인덱스 대신 일반 인덱스", schema, dup)
            op.execute(f"CREATE INDEX IF NOT EXISTS ix_{schema}_dataset_version_code_ver ON {schema}.dataset_version (dataset_code, version)")
        else:
            op.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS ux_{schema}_dataset_version_code_ver ON {schema}.dataset_version (dataset_code, version)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_ops_workflow_run_status_started ON ops.workflow_run (status, started_at)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ops.ix_ops_agent_decision_agent_wf_decision")
    op.execute("DROP INDEX IF EXISTS ops.ix_ops_workflow_run_status_started")
    for schema in ("bank", "ext"):
        op.execute(f"DROP INDEX IF EXISTS {schema}.ux_{schema}_dataset_version_code_ver")
        op.execute(f"DROP INDEX IF EXISTS {schema}.ix_{schema}_dataset_version_code_ver")
