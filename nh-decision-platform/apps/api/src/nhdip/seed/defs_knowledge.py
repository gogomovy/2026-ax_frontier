"""질문하기 통합 지식 색인 시드 (요구사항 §21 · 설계 §21.3 · §21.10) — 컬렉션 정의와 설정.

모두 최초 1회만 넣고(이미 있으면 건드리지 않음) 이후에는 관리자 화면 · 관리자 API 에서 바꾼다.
조직 코드: D100 종합기획부 · D200 신용리스크관리부 · D300/D400/D500 지역본부(영업점은 그 아래라 조직 경로에 포함).
"""
from __future__ import annotations

from typing import Any

# ═════════════════════════ 컬렉션 ═════════════════════════
# 포함 규칙(sources): doc_classes(문서 분류, '*' = 다른 컬렉션이 가져가지 않은 나머지) · artifact_keys(정확히 일치) · artifact_prefixes
#                     · spaces(분석 공간) · personas(P1 종합기획부 · P2 신용리스크 · P3 영업점) · screens(현재 화면 경로 접두어 — 가산점)
COLLECTIONS: list[dict[str, Any]] = [
    dict(code="doc.gov_policy", label="정부정책 DB", kind="document", description="금융당국 · 정부 정책 문서 (전행 공개)", owner_orgs=[], shared_orgs=[], required_resources=[], audience="all",
         sources={"doc_classes": ["gov_policy"]}, sort=10),
    dict(code="doc.mgmt_decision", label="경영 의사결정 DB", kind="document", description="지주 · 행내 경영 의사결정 문서 (문서별 부서한정 등급은 그대로 적용)", owner_orgs=["D100"], shared_orgs=[], required_resources=[], audience="all",
         sources={"doc_classes": ["mgmt_decision"]}, sort=11),
    dict(code="doc.model_method", label="모형 · 방법론", kind="document", description="신용평가모형 · 통계 방법론 문서 — 신용리스크 담당, 종합기획부 공유 (시뮬레이션 가정 · Q117)", owner_orgs=["D200"], shared_orgs=["D100"], required_resources=[], audience="restricted",
         sources={"doc_classes": ["model_method"]}, sort=12),
    dict(code="doc.branch_ref", label="영업점 기준 · 공문", kind="document", description="업적평가 세부기준 · 영업점 공문 — 영업 조직 담당, 종합기획부 · 신용리스크 공유 (시뮬레이션 가정 · Q117)", owner_orgs=["D300", "D400", "D500"], shared_orgs=["D100", "D200"], required_resources=[], audience="restricted",
         sources={"doc_classes": ["branch_ref"]}, sort=13),
    dict(code="doc.reference", label="기타 문서", kind="document", description="참고 자료와 위 컬렉션에 없는 문서 분류", owner_orgs=[], shared_orgs=[], required_resources=[], audience="all",
         sources={"doc_classes": ["reference", "*"]}, sort=19),
    dict(code="analysis.hq", label="종합기획부 분석 결과", kind="analysis", description="은행 대시보드 · 여신 분석 · 자본 · 수익성 · 경영목표 · 제안 · 요청", owner_orgs=["D100"], shared_orgs=[], required_resources=[], audience="restricted",
         sources={"spaces": ["hq"], "personas": ["P1"], "screens": ["/hq"],
                  "artifact_keys": ["hq_dashboard", "loan_overview", "comparison_view", "capital_view", "profitability", "goals", "proposals", "attentions", "report_requests", "review_queue", "cascade"]}, sort=20),
    dict(code="analysis.risk", label="신용리스크 분석 결과", kind="analysis", description="모형 모니터링 · 포용금융 · 부도율 추이 · 인사이트 · 수행방안", owner_orgs=["D200"], shared_orgs=[], required_resources=[], audience="restricted",
         sources={"spaces": ["risk"], "personas": ["P2"], "screens": ["/risk"],
                  "artifact_keys": ["risk_dashboard", "analysis_tabs", "inclusive", "default_rate_trend", "insights", "action_plans", "report.model-monitoring", "report.inclusive-risk"]}, sort=21),
    dict(code="analysis.branch", label="영업점 분석 결과", kind="analysis", description="영업점 업적평가 · 영업 가이드 · 본부 전파 목표 (지점 범위 유지)", owner_orgs=["D300", "D400", "D500"], shared_orgs=[], required_resources=[], audience="restricted",
         sources={"spaces": ["branch"], "personas": ["P3"], "screens": ["/branch"],
                  "artifact_keys": ["branch_dashboard", "branch_tabs", "branch_targets"], "artifact_prefixes": ["report.branch-"]}, sort=22),
    dict(code="glossary", label="용어집", kind="glossary", description="통계 · 리스크 용어 정의 (전행 공개)", owner_orgs=[], shared_orgs=[], required_resources=[], audience="all",
         sources={"artifact_keys": ["terms"]}, sort=30),
    dict(code="catalog.data", label="데이터 목록", kind="catalog", description="올라와 있는 데이터셋 파일 · 기준월 · 품질 (데이터베이스 화면 권한)", owner_orgs=[], shared_orgs=[], required_resources=[], audience="restricted",
         sources={"artifact_keys": ["dataset_meta"]}, sort=31),
    dict(code="admin.contracts", label="컬럼 정의서 대조 보고(관리자)", kind="catalog", description="관리자 [컬럼 정의서] 화면의 표별 대조 보고 — 관리자만 열람, 검색 순위는 낮춘다", owner_orgs=[], shared_orgs=[], required_resources=[], audience="owner_only",
         sources={"artifact_prefixes": ["contract."]}, boost=-0.15, sort=40),
    dict(code="analysis.unassigned", label="미분류 분석 결과", kind="analysis", description="어느 컬렉션 규칙에도 맞지 않은 산출물 — 관리자만 열람, 컬렉션 규칙을 정해 주세요", owner_orgs=[], shared_orgs=[], required_resources=[], audience="owner_only",
         sources={}, sort=99),
]

UNASSIGNED = "analysis.unassigned"

# ═════════════════════════ 설정 ═════════════════════════
# 기본값은 nhdip.knowledge.defaults 한 곳에 둔다(설정 행이 없어도 같은 값으로 동작)
from nhdip.knowledge.defaults import (  # noqa: E402
    ARTIFACT_RESOURCES,
    ARTIFACT_ROUTES,
    INDEX_DEFAULT,
    PERSONA_RESOURCES,
    REWRITE_DEFAULT,
    SEARCH_DEFAULT,
)

SETTINGS: dict[str, tuple[Any, str]] = {
    "knowledge.search": (SEARCH_DEFAULT, "질문하기 하이브리드 검색 — 채널 가중치(키워드 · 의미 · 그래프) · RRF 상수 · 채널별 후보 수 · 분석/문서 결과 수 · 출처당 상한 · 팀/화면/최신성/의도 가산점 · 게이팅 기준 · 개념 확장 · LLM 재순위 · HNSW 차원 (요구사항 §21 · 설계 §21.6)"),
    "knowledge.index": (INDEX_DEFAULT, "분석 결과 색인 — 청크 길이/겹침 · 표 최대 행 · 임베딩 배치/회당 최대 · 제외 산출물 키 · 본문에서 뺄 필드 이름 (설계 §21.5)"),
    "knowledge.artifact_resources": (ARTIFACT_RESOURCES, "산출물 키 → 화면 API 리소스 (청크의 열람 권한). 끝이 '.' 또는 '-' 인 키는 접두어"),
    "knowledge.persona_resources": (PERSONA_RESOURCES, "페르소나(P1 종합기획부 · P2 신용리스크 · P3 영업점) → 화면 리소스. 단위에 페르소나가 있으면 산출물 기본 리소스보다 우선"),
    "knowledge.artifact_routes": (ARTIFACT_ROUTES, "산출물 키 → 화면 주소 (질문하기 출처의 '화면 열기'). '{tab}' 은 접두어 뒤 탭 키"),
    "assist.rewrite": (REWRITE_DEFAULT, "질문하기 후속 질문 재작성 — 켜기 · LLM 사용 여부 · 반영할 이전 대화 수"),
}
