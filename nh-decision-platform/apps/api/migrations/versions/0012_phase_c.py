"""Phase C (2026-10-12) — 업무 자료 등록 요청 · 분석 에이전트
- ops.upload_request — 업무 사용자가 데이터베이스 화면에서 올린 자료(승인 대기 → 승인 때 기존 확정 경로) (UPL · Q99)
- cfg.analysis_agent · cfg.analysis_agent_version — 사용자 글을 정제한 분석 명세 · 승인 · 수명 (DAG · Q100)
Revision ID: 0012_phase_c
Revises: 0011_routing_ratelimit
Create Date: 2026-10-12
"""
from __future__ import annotations

from alembic import op

revision = "0012_phase_c"
down_revision = "0011_routing_ratelimit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE TABLE IF NOT EXISTS ops.upload_request ("
        " id BIGSERIAL PRIMARY KEY,"
        " kind VARCHAR(12) NOT NULL,"
        " target VARCHAR(80) NOT NULL,"
        " origin VARCHAR(10) NOT NULL,"
        " file_name VARCHAR(300) NOT NULL,"
        " file_path VARCHAR(500) NOT NULL,"
        " file_sha256 VARCHAR(64) NULL,"
        " meta JSONB NOT NULL DEFAULT '{}'::jsonb,"
        " preview JSONB NOT NULL DEFAULT '{}'::jsonb,"
        " status VARCHAR(12) NOT NULL DEFAULT 'pending',"
        " requested_by VARCHAR(40) NOT NULL,"
        " requested_org VARCHAR(40) NULL,"
        " reviewed_by VARCHAR(40) NULL,"
        " reviewed_at TIMESTAMPTZ NULL,"
        " review_note TEXT NULL,"
        " result JSONB NOT NULL DEFAULT '{}'::jsonb,"
        " created_at TIMESTAMPTZ NOT NULL DEFAULT now())"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_ops_upload_request_status_at ON ops.upload_request (status, created_at)")
    op.execute(
        "CREATE TABLE IF NOT EXISTS cfg.analysis_agent ("
        " code VARCHAR(40) PRIMARY KEY,"
        " space VARCHAR(40) NOT NULL,"
        " title VARCHAR(200) NOT NULL,"
        " status VARCHAR(12) NOT NULL DEFAULT 'draft',"
        " version INTEGER NOT NULL DEFAULT 0,"
        " spec JSONB NOT NULL DEFAULT '{}'::jsonb,"
        " workflow_code VARCHAR(60) NULL,"
        " tab_key VARCHAR(60) NOT NULL,"
        " requested_by VARCHAR(40) NULL,"
        " approved_by VARCHAR(40) NULL,"
        " approved_at TIMESTAMPTZ NULL,"
        " created_at TIMESTAMPTZ NOT NULL DEFAULT now(),"
        " updated_at TIMESTAMPTZ NOT NULL DEFAULT now())"
    )
    op.execute(
        "CREATE TABLE IF NOT EXISTS cfg.analysis_agent_version ("
        " id SERIAL PRIMARY KEY,"
        " agent_code VARCHAR(40) NOT NULL REFERENCES cfg.analysis_agent(code) ON DELETE CASCADE,"
        " version INTEGER NOT NULL,"
        " source_text TEXT NOT NULL DEFAULT '',"
        " spec JSONB NOT NULL DEFAULT '{}'::jsonb,"
        " validation JSONB NOT NULL DEFAULT '{}'::jsonb,"
        " preview JSONB NOT NULL DEFAULT '{}'::jsonb,"
        " status VARCHAR(12) NOT NULL DEFAULT 'pending',"
        " requested_by VARCHAR(40) NULL,"
        " reviewed_by VARCHAR(40) NULL,"
        " reviewed_at TIMESTAMPTZ NULL,"
        " review_note TEXT NULL,"
        " created_at TIMESTAMPTZ NOT NULL DEFAULT now(),"
        " UNIQUE (agent_code, version))"
    )
    # API 전용 계정(B.33) 권한은 기동 때 `nhdip.cli db-app-role`(스키마 전체 · 기본 권한)이 준다


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS cfg.analysis_agent_version")
    op.execute("DROP TABLE IF EXISTS cfg.analysis_agent")
    op.execute("DROP TABLE IF EXISTS ops.upload_request")
