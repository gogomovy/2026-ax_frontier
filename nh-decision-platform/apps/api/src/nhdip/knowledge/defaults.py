"""질문하기 지식 색인 · 검색 설정의 기본값 (설계 §21.10) — 시드(seed/defs_knowledge.py)가 설정 행으로 넣고,
설정 행이 없거나 일부 키가 빠져도 이 값으로 동작한다(관리자 편집 값이 우선)."""
from __future__ import annotations

from typing import Any

SEARCH_DEFAULT: dict[str, Any] = {
    "weights": {"keyword": 1.0, "vector": 1.0, "graph": 0.8},
    "rrf_k": 60,
    "candidates_per_channel": 40,
    "analysis_k": 4,
    "doc_k": 4,
    "per_source_max": 2,
    "team_boost": 0.15,
    "screen_boost": 0.08,
    "recency_boost": 0.05,
    "intent_boost": 0.1,
    "min_keyword_coverage": 1,
    "fusion": "convex",
    "min_term_ratio": 0.34,
    "keyword_candidates": 3000,
    "max_cosine_distance": 0.65,
    "graph_expand_max": 24,
    "expand_weight": 0.5,
    "rerank_llm": False,
    "hnsw_dim": None,
    "hnsw_ef_search": 200,  # HNSW 후보 풀(pgvector 기본 40). 접근 범위가 좁은 사용자도 후보 수 · 재현율이 유지되게(10만 건 실측, 설계 §21.18). 0 이면 pgvector 기본값
    "hnsw_iterative_scan": "strict_order",  # pgvector 0.8+ 반복 탐색(요청한 건수가 찰 때까지 계속 탐색, 순서 유지). '' = 끔 · 'relaxed_order'. 0.8 미만이면 건너뜀
    "backend": "pg",  # 'pg' = PostgreSQL(기본) · 'es' = 키워드 · 의미 채널을 Elasticsearch 로(ES_URL 설정 + 동기화 후 · 설계 §21.18). ES 가 안 되면 자동으로 pg 로 폴백
    "es_candidates": 60,  # ES 에서 채널별로 가져올 후보 수 — PostgreSQL 에서 권한을 다시 걸러 낼 몫까지 넉넉히
    "es_sync_max_per_run": 2000,  # 워커 한 번에 ES 로 올릴 청크 수 상한
}

INDEX_DEFAULT: dict[str, Any] = {
    "chunk_chars": 900,
    "overlap": 80,
    "table_rows": 12,
    "embed_batch": 32,
    "embed_max_per_run": 160,
    "exclude_keys": ["documents", "meta", "change_feed", "domains"],
    "skip_keys": [
        "id", "kind", "calc", "sourceRef", "tableRef", "dataOrigin", "executedAt", "formulaId", "formulaVersion", "href", "verifications", "rankScore", "rankBasis",
        "generatedAt", "degradedSources", "batchLabel", "persona", "domainCode", "subDomain", "sourceKind", "figureId", "checkCode", "reportAnchor", "tabKey", "reportKind",
        "insightId", "relatedGoalId", "sourceInsightId", "linkedTabKey", "guideRuleId", "creationMode", "history", "toc", "unit", "decimals", "generation", "office",
    ],
}

# 산출물 키 → 그 산출물을 보여 주는 화면 API 리소스 (화면 API 의 require_resource 와 같은 값 — ACL-05). 끝이 '.' · '-' 인 키는 접두어
ARTIFACT_RESOURCES: dict[str, str] = {
    "hq_dashboard": "hq_dashboard", "attentions": "attentions", "loan_overview": "loan_overview", "comparison_view": "comparison_view", "capital_view": "capital_view",
    "profitability": "profitability", "goals": "goals", "proposals": "proposals", "review_queue": "review_queue", "cascade": "cascade", "report_requests": "report_requests",
    "risk_dashboard": "risk_dashboard", "analysis_tabs": "analysis_tabs", "inclusive": "inclusive", "default_rate_trend": "default_rate_trend",
    "insights": "insights", "action_plans": "plan_actions",
    "branch_dashboard": "branch_dashboard", "branch_tabs": "branch_tabs", "branch_targets": "branch_targets",
    "terms": "terms", "dataset_meta": "datasets",
    "report.": "reports", "report.branch-": "branch_reports",
}

# 단위(인사이트 등)에 페르소나가 있으면 산출물 기본 리소스보다 우선 — 부서 간 인사이트 열람 불가 (B.32 와 같은 원칙)
PERSONA_RESOURCES: dict[str, str] = {"P1": "hq_dashboard", "P2": "risk_dashboard", "P3": "branch_dashboard"}

# 산출물 키 → 화면 주소 ('{tab}' = 접두어 뒤 탭 키)
ARTIFACT_ROUTES: dict[str, str] = {
    "hq_dashboard": "/hq/overview", "attentions": "/hq/overview", "report_requests": "/hq/overview",
    "loan_overview": "/hq/analysis", "comparison_view": "/hq/analysis", "capital_view": "/hq/capital", "profitability": "/hq/capital",
    "goals": "/hq/goals", "proposals": "/hq/goals", "review_queue": "/hq/goals", "cascade": "/hq/goals",
    "risk_dashboard": "/risk", "default_rate_trend": "/risk", "analysis_tabs": "/risk/analysis", "insights": "/risk/analysis",
    "inclusive": "/risk/analysis/inclusive-risk", "action_plans": "/risk/guides",
    "branch_dashboard": "/branch", "branch_tabs": "/branch", "branch_targets": "/branch/targets",
    "terms": "/knowledge", "dataset_meta": "/knowledge",
    "report.branch-": "/branch/analysis/{tab}", "report.": "/risk/analysis/{tab}",
}

REWRITE_DEFAULT: dict[str, Any] = {"enabled": True, "llm": True, "max_history": 3}
