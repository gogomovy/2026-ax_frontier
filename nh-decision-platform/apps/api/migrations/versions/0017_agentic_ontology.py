"""Phase M (2026-10-14) — 에이전틱 온톨로지 구축 · 에이전트 그룹 (요구사항 §30 · Q179~Q190)
- cfg.agent_group — 에이전트 기능 묶음(오케스트레이션 · 온톨로지 구축 · 지식 · 검색 · 변화 판단 · 서술 · 검증 · AI 어시스턴트 · 분석 에이전트)
- cfg.agent.group_code — 에이전트가 속한 묶음(비우면 미분류)
- cfg.ontology_proposal — 에이전트 · 관리자의 스키마 변경 제안(연산 목록 · 근거 · 영향 · 검증) → 승인 = 적용(새 판)
- ops.data_profile — 구조 파악 에이전트의 데이터셋 버전별 열 통계 · 의미 · 키 후보
Revision ID: 0017_agentic_ontology
Revises: 0016_cfg_secret
Create Date: 2026-10-14
"""
from __future__ import annotations

from alembic import op

revision = "0017_agentic_ontology"
down_revision = "0016_cfg_secret"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cfg.agent_group (
            code VARCHAR(40) PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            sort INTEGER NOT NULL DEFAULT 0,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("ALTER TABLE cfg.agent ADD COLUMN IF NOT EXISTS group_code VARCHAR(40) NULL REFERENCES cfg.agent_group(code) ON DELETE SET NULL")
    op.execute("ALTER TABLE cfg.ontology_schema ADD COLUMN IF NOT EXISTS interfaces JSONB NOT NULL DEFAULT '[]'::jsonb")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cfg.ontology_proposal (
            id SERIAL PRIMARY KEY,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            source VARCHAR(20) NOT NULL DEFAULT 'agent',
            agent_code VARCHAR(60) NULL,
            workflow_run_id VARCHAR(40) NULL,
            title VARCHAR(200) NOT NULL DEFAULT '',
            summary TEXT NOT NULL DEFAULT '',
            ops JSONB NOT NULL DEFAULT '[]'::jsonb,
            evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
            impact JSONB NOT NULL DEFAULT '{}'::jsonb,
            validation JSONB NOT NULL DEFAULT '{}'::jsonb,
            base_version INTEGER NULL,
            applied_version INTEGER NULL,
            created_by VARCHAR(40) NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            decided_by VARCHAR(40) NULL,
            decided_at TIMESTAMPTZ NULL,
            note TEXT NULL
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_cfg_ontology_proposal_status ON cfg.ontology_proposal (status, created_at)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ops.data_profile (
            id SERIAL PRIMARY KEY,
            dataset_code VARCHAR(60) NOT NULL,
            origin VARCHAR(10) NOT NULL,
            version_sig VARCHAR(200) NOT NULL,
            rows INTEGER NOT NULL DEFAULT 0,
            profile JSONB NOT NULL DEFAULT '{}'::jsonb,
            semantics JSONB NOT NULL DEFAULT '{}'::jsonb,
            by VARCHAR(80) NOT NULL DEFAULT 'rule',
            workflow_run_id VARCHAR(40) NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (dataset_code, version_sig)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_ops_data_profile_code ON ops.data_profile (dataset_code, created_at)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ops.data_profile")
    op.execute("DROP TABLE IF EXISTS cfg.ontology_proposal")
    op.execute("ALTER TABLE cfg.ontology_schema DROP COLUMN IF EXISTS interfaces")
    op.execute("ALTER TABLE cfg.agent DROP COLUMN IF EXISTS group_code")
    op.execute("DROP TABLE IF EXISTS cfg.agent_group")
