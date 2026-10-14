"""초기 설정 시드 — 조직 · 화면 · 권한 · 설정값 · 규칙 · 온톨로지 스키마 · 에이전트.

모두 최초 1회만 넣고(이미 있으면 건드리지 않음) 이후에는 관리자 화면에서 바꾼다.
"""
from __future__ import annotations

from nhdip.ui_config import DEFAULTS as UI_DEFAULTS

# ═════════════════════════ 조직 (요구사항 Q12 확정) ═════════════════════════
# 본점: 본부 > 부 > 국 > 팀 / 영업 조직: 지역본부 > 영업점 (지역본부 직속 국·팀 허용)
# 유형 정의와 허용 상위 유형은 setting 'org.unit_types' — 관리자 화면에서 수정
ORG_UNIT_TYPES = [
    {"code": "HQ_DIV", "label": "본부", "parents": []},
    {"code": "DEPT", "label": "부", "parents": ["HQ_DIV"]},
    {"code": "BUREAU", "label": "국", "parents": ["DEPT", "REGION"]},
    {"code": "TEAM", "label": "팀", "parents": ["BUREAU", "DEPT"]},
    {"code": "REGION", "label": "지역본부", "parents": []},
    {"code": "BRANCH", "label": "영업점", "parents": ["REGION"]},
]

# (code, name, unit_type, parent, sort) — 깊이(level)는 상위 조직 기준으로 계산
ORGS = [
    ("H100", "경영기획본부", "HQ_DIV", None, 10),
    ("D100", "종합기획부", "DEPT", "H100", 11),
    ("B110", "경영기획국", "BUREAU", "D100", 12),
    ("T111", "경영목표팀", "TEAM", "B110", 13),
    ("T112", "성과관리팀", "TEAM", "B110", 14),
    ("B120", "자본관리국", "BUREAU", "D100", 15),
    ("T121", "자본관리팀", "TEAM", "B120", 16),
    ("H200", "리스크관리본부", "HQ_DIV", None, 20),
    ("D200", "신용리스크관리부", "DEPT", "H200", 21),
    ("B210", "리스크측정국", "BUREAU", "D200", 22),
    ("T211", "모형검증팀", "TEAM", "B210", 23),
    ("T212", "포용금융리스크팀", "TEAM", "B210", 24),
    ("B220", "여신감리국", "BUREAU", "D200", 25),
    ("T221", "여신감리팀", "TEAM", "B220", 26),
    ("H300", "여신본부", "HQ_DIV", None, 30),
    ("D310", "여신관리부", "DEPT", "H300", 31),
    ("H900", "디지털전략본부", "HQ_DIV", None, 90),
    ("D900", "디지털전략부", "DEPT", "H900", 91),
    ("B910", "AI플랫폼국", "BUREAU", "D900", 92),
    ("T911", "플랫폼운영팀", "TEAM", "B910", 93),
    # 영업 조직 — 기존 코드(D300) 유지
    ("D300", "수도권1지역본부", "REGION", None, 100),
    ("B310", "영업지원국", "BUREAU", "D300", 101),
    ("T311", "영업점지원팀", "TEAM", "B310", 102),
    ("BR301", "강남금융센터", "BRANCH", "D300", 103),
    ("BR302", "서초지점", "BRANCH", "D300", 104),
    ("BR303", "역삼역지점", "BRANCH", "D300", 105),
    # 영업점 시나리오(B.29 · Q43) — 조직 코드 = 사무소 코드
    ("001068", "수원영통지점", "BRANCH", "D300", 106),
    ("D400", "중부지역본부", "REGION", None, 110),
    ("BR401", "대전지점", "BRANCH", "D400", 111),
    ("BR402", "청주지점", "BRANCH", "D400", 112),
    ("D500", "충북지역본부", "REGION", None, 120),
    ("BR501", "충주지점", "BRANCH", "D500", 121),
]

# ═════════════════════════ 화면 ═════════════════════════
# resources: 이 화면이 호출하는 화면 API 리소스 키 — API 권한 판정 기준(AUTH-08)
SCREENS = [
    dict(code="HQ_OVERVIEW", path="/hq/overview", label="현황·목표", section="종합기획부", kind="flow", step=1, sort=10, resources=["changes", "hq_dashboard", "attentions", "report_requests", "goals", "proposals", "domains", "loan_overview", "cascade", "insights", "goal_state", "plan_state", "action_plans"]),
    # 데이터 분석 — 여신 실적 분석 + 맞춤 분석 탭(분석 에이전트 · 공간 hq · Phase C 후속 Q109)
    dict(code="HQ_ANALYSIS", path="/hq/analysis", label="데이터 분석", section="종합기획부", kind="flow", step=2, sort=11, resources=["loan_overview", "comparison_view", "insights", "hq_reports"]),
    dict(code="HQ_GOALS", path="/hq/goals", label="경영목표 설정", section="종합기획부", kind="flow", step=3, count_key="goalProposals", sort=12, resources=["attentions", "goals", "proposals", "review_queue", "report_requests", "cascade", "insights", "goal_state", "goal_actions", "plan_state", "action_plans"]),
    dict(code="HQ_INITIATIVES", path="/hq/initiatives", label="사업부서 진행 사업", section="종합기획부", kind="reference", sort=13, resources=["action_plans", "plan_state", "analysis_tabs"]),
    dict(code="HQ_CAPITAL", path="/hq/capital", label="총자산·수익성 기준", section="종합기획부", kind="reference", sort=14, resources=["capital_view", "profitability"]),
    dict(code="DOMAINS", path="/domains", label="사업부문 상세", section="종합기획부", kind="hidden", sort=15, resources=["domains"]),
    dict(code="RISK_HOME", path="/risk", label="현황", section="신용리스크관리부", kind="flow", step=1, match="=/risk", sort=20, resources=["changes", "risk_dashboard", "analysis_tabs", "default_rate_trend", "insights", "action_plans", "plan_state"]),
    dict(code="RISK_ANALYSIS", path="/risk/analysis", label="분석 결과", section="신용리스크관리부", kind="flow", step=2, count_key="analyses", match="/risk/analysis", sort=21, resources=["analysis_tabs", "reports", "inclusive", "insights", "action_plans", "plan_state", "plan_actions"]),
    # 전파 경로(경영목표 → 실행 사업 → 영업점)를 종합기획부와 같은 흐름도로 — 목표 · 전파 트리는 읽기만 (Phase K 후속 · SCP-04 · Q156)
    dict(code="RISK_GUIDES", path="/risk/guides", label="수행방안", section="신용리스크관리부", kind="flow", step=3, count_key="proposedPlans", sort=22, resources=["analysis_tabs", "action_plans", "plan_state", "plan_actions", "reports", "cascade", "goals"]),
    dict(code="BRANCH_HOME", path="/branch", label="현황", section="영업점", kind="flow", step=1, match="=/branch", sort=30, resources=["branch_dashboard", "branch_tabs", "changes"]),
    dict(code="BRANCH_ANALYSIS", path="/branch/analysis", label="분석 결과", section="영업점", kind="flow", step=2, count_key="branchAnalyses", match="/branch/analysis", sort=31, resources=["branch_dashboard", "branch_tabs", "branch_reports"]),
    dict(code="BRANCH_TARGETS", path="/branch/targets", label="본부 전파 목표·가이드", section="영업점", kind="reference", sort=32, resources=["branch_targets", "action_plans", "plan_state", "cascade", "goals"]),
    dict(code="KNOWLEDGE", path="/knowledge", label="데이터베이스", section="공통", kind="reference", sort=80, resources=["documents", "datasets", "terms", "search"]),
    # 업무 자료 올리기 (Phase C · UPL · Q99) — 화면을 받은 조직만 [데이터베이스]에서 자료를 올려 승인 요청
    # 분석 에이전트 만들기 (Phase C · DAG-01 · 이름 Phase K · Q155) — 화면을 받은 조직은 부서 분석 공간에 새 분석을 요청(관리자 승인)
    dict(code="ANALYSIS_BUILDER", path="/analysis/builder", label="분석 에이전트 만들기", section="공통", kind="reference", sort=82, match="/analysis/builder", resources=["analysis_builder"]),
    dict(code="KNOWLEDGE_UPLOAD", path="/knowledge/upload", label="자료 올리기", section="공통", kind="reference", sort=81, resources=["db_upload"]),
    # 관리자 — 묶음 6개 (Phase C · ADM-01 · Q104). 화면 코드 · 경로는 그대로, 묶음(section) · 이름 · 정렬만
    dict(code="ADMIN_HOME", path="/admin", label="관리자 홈", section="관리자 홈", kind="admin", sort=100, admin_only=True, match="=/admin", count_key="adminTodo"),
    dict(code="ADMIN_USERS", path="/admin/users", label="사용자", section="사용자와 권한", kind="admin", sort=110, admin_only=True, count_key="adminUsers"),
    dict(code="ADMIN_ORGS", path="/admin/orgs", label="조직", section="사용자와 권한", kind="admin", sort=111, admin_only=True),
    dict(code="ADMIN_SCREENS", path="/admin/screens", label="화면 권한", section="사용자와 권한", kind="admin", sort=112, admin_only=True),
    dict(code="ADMIN_AUDIT", path="/admin/audit", label="감사 로그", section="사용자와 권한", kind="admin", sort=113, admin_only=True),
    dict(code="ADMIN_UPLOADS", path="/admin/uploads", label="자료 승인", section="데이터와 지식", kind="admin", sort=120, admin_only=True, count_key="adminUploads"),
    dict(code="ADMIN_DATASETS", path="/admin/datasets", label="데이터셋·문서", section="데이터와 지식", kind="admin", sort=121, admin_only=True),
    dict(code="ADMIN_CONTRACTS", path="/admin/contracts", label="컬럼 정의서", section="데이터와 지식", kind="admin", sort=122, admin_only=True),
    dict(code="ADMIN_ONTOLOGY", path="/admin/ontology", label="온톨로지", section="데이터와 지식", kind="admin", sort=123, admin_only=True),
    dict(code="ADMIN_KNOWLEDGE", path="/admin/knowledge", label="AI 어시스턴트 색인", section="데이터와 지식", kind="admin", sort=124, admin_only=True),
    dict(code="ADMIN_ANALYSIS_AGENTS", path="/admin/analysis-agents", label="분석 에이전트", section="AI · 에이전트", kind="admin", sort=130, admin_only=True, count_key="adminAnalyses"),
    dict(code="ADMIN_LLM", path="/admin/llm", label="LLM 연동", section="AI · 에이전트", kind="admin", sort=131, admin_only=True),
    dict(code="ADMIN_AGENTS", path="/admin/agents", label="에이전트·프롬프트", section="AI · 에이전트", kind="admin", sort=132, admin_only=True),
    dict(code="ADMIN_WORKFLOWS", path="/admin/workflows", label="워크플로", section="AI · 에이전트", kind="admin", sort=133, admin_only=True),
    dict(code="ADMIN_METRICS", path="/admin/metrics", label="지표·계산", section="계산과 규칙", kind="admin", sort=141, admin_only=True),
    dict(code="ADMIN_RULES", path="/admin/rules", label="판정 규칙", section="계산과 규칙", kind="admin", sort=142, admin_only=True),
    dict(code="ADMIN_SETTINGS", path="/admin/settings", label="운영 설정", section="계산과 규칙", kind="admin", sort=143, admin_only=True),
    # 화면 설정 (Phase K · Q148) — 판정 구간 · 기준값 · 목표 역할 · 업무 영역 · 예시 질문 · 알림
    dict(code="ADMIN_UI", path="/admin/ui", label="화면 설정", section="계산과 규칙", kind="admin", sort=144, admin_only=True),
    dict(code="ADMIN_MONITOR", path="/admin/monitor", label="운영 개요", section="운영 모니터링", kind="admin", sort=150, admin_only=True, match="=/admin/monitor"),
    dict(code="ADMIN_PIPELINE", path="/admin/pipeline", label="파이프라인", section="운영 모니터링", kind="admin", sort=151, admin_only=True),
    dict(code="ADMIN_FLOW", path="/admin/monitor/flow", label="데이터 흐름", section="운영 모니터링", kind="admin", sort=152, admin_only=True),
    dict(code="ADMIN_RUNS", path="/admin/monitor/runs", label="에이전트 실행", section="운영 모니터링", kind="admin", sort=153, admin_only=True),
    dict(code="ADMIN_AGENT_DECISIONS", path="/admin/monitor/agents", label="에이전트 결정", section="운영 모니터링", kind="admin", sort=154, admin_only=True),
    dict(code="ADMIN_CALC", path="/admin/monitor/calc", label="수치 모니터링", section="운영 모니터링", kind="admin", sort=155, admin_only=True),
    dict(code="ADMIN_TRACE", path="/admin/monitor/trace", label="요청 추적", section="운영 모니터링", kind="admin", sort=156, admin_only=True),
    dict(code="ADMIN_EVALS", path="/admin/monitor/evals", label="골든셋 평가", section="운영 모니터링", kind="admin", sort=157, admin_only=True),
    dict(code="ADMIN_ALERTS", path="/admin/monitor/alerts", label="운영 알림 · 비용", section="운영 모니터링", kind="admin", sort=158, admin_only=True),
]

# 조직 → 화면 (하위 조직은 상속)
GRANTS = {
    "D100": ["HQ_OVERVIEW", "HQ_ANALYSIS", "HQ_GOALS", "HQ_INITIATIVES", "HQ_CAPITAL", "DOMAINS", "KNOWLEDGE", "KNOWLEDGE_UPLOAD", "ANALYSIS_BUILDER"],
    "D200": ["RISK_HOME", "RISK_ANALYSIS", "RISK_GUIDES", "KNOWLEDGE", "KNOWLEDGE_UPLOAD", "ANALYSIS_BUILDER"],
    "D300": ["BRANCH_HOME", "BRANCH_ANALYSIS", "BRANCH_TARGETS", "KNOWLEDGE"],
    "D400": ["BRANCH_HOME", "BRANCH_ANALYSIS", "BRANCH_TARGETS", "KNOWLEDGE"],
    "D500": ["BRANCH_HOME", "BRANCH_ANALYSIS", "BRANCH_TARGETS", "KNOWLEDGE"],
    "D900": ["KNOWLEDGE"],
}

# ═════════════════════════ 설정값 ═════════════════════════
# 관리자 [파이프라인] 기본 단계 (B.39 · 설정 pipeline.stages)
PIPELINE_STAGES: list[dict[str, Any]] = [
    {"key": "input", "label": "입력 고정", "impls": ["load_inputs", "embed_chunks", "extract_documents"]},
    {"key": "compute", "label": "계산 · 판정(커널 · 규칙)", "impls": ["compute_metrics", "judge", "recommend_goals", "rank_attentions", "project_graph"]},
    {"key": "detect", "label": "변화 감지", "impls": ["detect_changes"]},
    {"key": "views", "label": "화면 갱신", "impls": ["build_views", "sync_analysis_tabs", "select_guides", "apply_segment_labels"]},
    {"key": "plan", "label": "실행 계획", "impls": ["plan_run"]},
    {"key": "evidence", "label": "근거 검색", "impls": ["retrieve_evidence"]},
    {"key": "narrate", "label": "의견 서술", "impls": ["narrate"]},
    {"key": "verify", "label": "검증", "impls": ["critic"]},
    {"key": "load", "label": "정의서 적재", "impls": ["materialize_contracts"]},
    {"key": "publish", "label": "게시", "impls": ["publish"]},
]


SETTINGS = {
    "org.unit_types": (ORG_UNIT_TYPES, "조직 유형(본부 · 부 · 국 · 팀 · 지역본부 · 영업점)과 허용 상위 유형"),
    "auth.max_failed_logins": (5, "연속 로그인 실패 시 잠금 횟수"),
    "auth.signup_requires_approval": (True, "가입 후 관리자 승인 필요"),
    "auth.session_idle_minutes": (120, "세션 유휴 만료(분)"),
    "auth.lockout_minutes": (30, "로그인 잠금 자동 해제(분) — 0 이면 관리자만 해제 (B.32)"),
    "auth.rate_limits": (
        {"login_ip": [30, 300], "login_emp": [10, 300], "signup_ip": [10, 3600], "assist_user": [30, 60], "assist_feedback": [30, 60], "assist_scope": [60, 60], "stream_user": [10, 60], "request_user": [20, 86400]},
        "요청 속도 제한 {이름: [허용 횟수, 초]} — 0 이면 끄기. 로그인(IP · 사번) · 가입(IP) · 질의(사용자) · 질문하기 피드백 · 범위 조회(사용자) · 분석 스트림(사용자) · 확인 요청(사용자) (B.32)",
    ),
    "ops.backup_max_age_days": (1, "운영 준비 점검 — 마지막 백업(make backup)이 이 일수보다 오래되면 '확인' 표시 (B.34)"),
    "workflow.max_run_minutes": (120, "워크플로우 한 번 실행 시간 상한(분) — 넘으면 워커가 재시작하고 작업을 다시 대기열로 (0 = 끔) (B.33 · 시뮬레이션 가정)"),
    "auth.rate_limit_backend": ("db", "속도 제한 저장 위치 — db(여러 API 프로세스가 함께 셈 · 기본) · memory(프로세스별) (B.33)"),
    # ── 점검 보완 (B.32) ──
    "retention.policy": (
        {"enabled": True, "artifact_generations": 50, "llm_call_days": 180, "node_run_days": 180, "agent_decision_days": 180, "outbox_days": 90, "job_days": 90},
        "보관 기간 정리(워커 하루 1회) — 화면 산출물 이전 세대 수 · 운영 기록 보관 일수. 0 = 정리 안 함. 감사 로그 · 계산 기록은 정리하지 않음",
    ),
    "privacy.policy": (
        {"pii_scan": True, "pii_allow_columns": [], "display_mask_columns": ["brwr_nm"], "mask_llm_log": True, "mask_assist_audit": True},
        "개인정보 — 적재 전 개인정보 형식 값 검사(주민번호 · 휴대전화 · 이메일 · 카드번호, 발견 시 적재 거부) · 검사 제외 열 · 화면 가림 열 · LLM 호출 기록 가림 · 질문하기 감사 기록의 질문 가림",
    ),
    "governance.dual_control": ({"enabled": False, "rules": True}, "이중 승인 — 켜면 판정 규칙 새 버전은 만든 관리자가 아닌 다른 관리자가 적용해야 활성화"),
    "calc.unit_check": (
        {"formulas": ["SUM", "DIFF", "MEAN", "MIN_OF", "GROWTH_RATE"], "mode": "block"},
        "단위 검사 — 이 수식들은 입력 단위가 같아야 한다(mode: block = 계산 거부 · warn = 계산 후 경고). 입력 단위는 지표 인자의 unit · 선행 지표 단위",
    ),
    "request.types": (
        {"direction_check": "경영방향 확인 요청", "perf_report": "사업 성과보고", "new_biz_check": "신규사업 확인 요청", "guide_check": "영업 가이드 확인 요청"},
        "확인 · 보고 요청 유형 {코드: 표시 이름} — 영업점 · 사업부서가 본부에 보내는 요청",
    ),
    "request.to_org": ("종합기획부", "확인 · 보고 요청을 받는 부서 이름"),
    "workflow.debounce_default_sec": (60, "변경 이벤트 후 워크플로우 실행 대기(초) — 연속 변경 병합"),
    "calc.rounding_default": ("HALF_UP", "지표 표시 반올림 기본값 (HALF_UP · HALF_EVEN · DOWN · UP)"),
    "embedding.agent": ("embedder", "문서 임베딩에 사용할 에이전트 코드"),
    "search.top_k": (5, "근거 검색 결과 수"),
    "contracts.dept_prefix": ({"종기부": "hq", "리스크": "risk", "사업부서": "risk", "영업점": "branch"}, "컬럼 정의서 부서 → mart 테이블 접두어 (예: 종기부 T01 → mart.hq_t01 · 사업부서 T01 → 표 코드 RISK_T01 · mart.risk_t01)"),
    "pipeline.stages": (PIPELINE_STAGES, "관리자 [파이프라인] 단계 — [{key, label, impls[]}] 순서대로 표시, 비우면 기본 단계(api/pipeline_view.DEFAULT_STAGES). 미지정 구현은 '기타'"),
    "contracts.raw_depts": (["종기부"], "표 코드에 부서 접두를 붙이지 않는 기준 부서 (T01 그대로) — 나머지 부서는 '<접두>_T01'"),
    "assist.workflow_resources": ({"wf_model_monitoring": "risk_dashboard", "wf_inclusive_risk": "risk_dashboard", "wf_hq_goal_review": "hq_dashboard", "wf_branch_kpi": "branch_dashboard"}, "질의 패널 — 워크플로우 지표를 볼 수 있는 화면 리소스 (권한 없는 지표는 답변에서 제외)"),
    "format.unit_labels": ({"KRW_MN": "백만원", "KRW_BN": "억원", "KRW_TN": "조원", "PCT": "%", "PP": "%p", "CNT": "건", "RATIO": "", "NONE": ""}, "단위 코드 → 표시 문자 (전파 경로 목표 라벨 갱신 · 보고서 내보내기)"),
    "report.export_formats": (["pdf", "hwpx", "hwp", "html"], "보고서 내려받기 형식과 메뉴 순서 (pdf · hwpx · hwp · html) — 빼면 화면 메뉴에서도 사라짐"),
    "report.pdf_fonts": ({"regular": "/usr/share/fonts/truetype/nanum/NanumGothic.ttf", "bold": "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"}, "PDF 한글 글꼴 경로 (없으면 내장 CID 글꼴 HYGothic-Medium)"),
    "obs.slow_request_ms": (1000, "느린 조회 기준(ms) — 이보다 오래 걸린 GET 요청도 추적 기록(ops.request_log)에 남김. 변경 요청 · 오류는 항상 기록"),
    "upload.policy": ({"max_mb": 50, "zip_max_uncompressed_mb": 300, "zip_max_ratio": 150, "zip_max_entries": 5000, "block_pdf_active": True, "av_timeout_sec": 60}, "업로드 보안 정책 — 크기 · 압축 폭탄 한도 · PDF 스크립트 차단 · 백신 시간 제한(백신 명령은 배포 환경변수 UPLOAD_AV_COMMAND)"),
    "analysis.spaces": ({}, "부서 분석 공간(Phase C · DAG-07) — 기본(risk · branch · hq)에 덧붙이거나 바꿀 값. 공간 = {label, path, tabs(기존 탭 산출물), tabsResource, resource(보고서 열람 리소스), reportPrefix, scoped, builder(분석 에이전트 만들기 허용), domain, persona, enabled}. 새 공간은 관리자 [화면 권한] 화면 등록과 함께"),
    "upload.user_targets": ({"datasets": "*", "doc_classes": "*"}, "업무 화면 [자료 올리기]에서 올릴 수 있는 대상 — datasets · doc_classes 에 \"*\"(전체) 또는 코드 목록. 올린 자료는 관리자 [자료 승인] 후 반영 (Phase C · UPL)"),
    "obs.request_log_days": (30, "요청 추적 기록(ops.request_log) 보관 일수 — 지난 기록은 워커가 하루 1회 정리"),
    "analysis.min_interval_sec": (60, "업무 화면 온디맨드 분석 — 같은 분석을 다시 요청할 수 있는 최소 간격(초). 간격 안의 요청은 진행 중인 실행을 함께 본다"),
    "risk.segment_labels": ({}, "부도율 추이 구분코드 → 화면 표시명 (예: {\"pool_1\": \"신용대출 일반\"}). 비우면 데이터의 구분명(segment_label)을 쓴다 — 개인 풀 확정 시 여기만 바꾼다(F.18)"),
    "risk.retail_pool_note": ("", "개인 풀 안내 문구 — 비우면 산출물 기본 문구 유지"),
    "docs.owner_orgs": ({"doc-mgmt-rwadept": ["D100"], "doc-model-corp": ["D200"], "doc-model-retail": ["D200"]}, "부서한정 문서의 소유 부서(조직 코드, 하위 조직 포함) — 목록 · 근거 검색 · 원본 열람에서 같은 기준으로 검증"),
    "evidence.policy": ({"weights": {"official": 0.40, "recency": 0.25, "semantic": 0.20, "path": 0.15}, "recency_half_life_days": 365, "max_age_days": 1825, "min_keyword_coverage": 1, "max_cosine_distance": 0.65}, "근거 선별 — 우선순위 가중치(공식성 · 시점 · 의미 · 개념경로) · 시점 반감기 · 최대 경과일 · 의미 기준"),
    "alerts.policy": ({"enabled": False, "channels": ["webhook", "email"], "min_severity": "warning", "lookback_min": 30, "rules": {"workflow_failed": {"enabled": True, "severity": "critical"}, "quality_failed": {"enabled": True, "severity": "warning"}, "auth_failures": {"enabled": True, "severity": "warning", "threshold": 10, "window_min": 10}, "llm_budget": {"enabled": True, "severity": "warning", "levels": [80, 100]}, "golden_failed": {"enabled": True, "severity": "warning"}}}, "운영 알림 — 켜기 · 채널 · 최소 심각도 · 조건별 기준. 채널 주소 · 계정은 배포 환경변수(ALERT_WEBHOOK_URL · ALERT_SMTP_*)"),
    "assist.synonyms": ({"차이": ["초과 폭", "격차", "이탈", "증감"], "초과": ["초과 폭"], "변화": ["증감", "증가율"], "비중": ["구성비"]}, "질의 패널 지표 찾기 — 질문어 → 같은 뜻의 지표명 표현(질문어가 지표명에 없을 때 보강) (B.40)"),
    "workflow.scopes": ({
        "wf_branch_kpi": {"rule": "BRANCH_SCOPE", "key": "office_code", "list": "office_codes", "name": "office", "max": 20, "narrate_max": 5, "shared_keys": ["change_feed"],
                          "requires": [{"dataset": "BRANCH_OFFICE_MASTER", "column": "office_cd"}, {"dataset": "BRANCH_KPI_SCORE", "column": "office_cd"}],
                          "placeholder": "이 지점의 영업 가이드 의견은 다음 서술 실행(LLM) 후 표시됩니다."},
    }, "범위 실행(다지점 · B.47) — 워크플로우별 범위 규칙 · 기본 범위 키 · 추가 범위 목록 키 · 필수 자료 · 상한(max, 기본 범위 포함) · "
       "LLM 을 쓸 추가 범위 수(narrate_max, 실행마다 서술이 오래된 지점부터 · 0 = 쓰지 않음 · -1 = 제한 없음) · 공유 산출물. 추가 범위 산출물은 '<키>@<값>' 으로 게시"),
    "assist.metric_synonyms": ({
        "breach_gap_6b": ["대표값 차이", "대표 PD 차이", "PD 차이", "부도율 차이", "초과폭", "대표값을 넘은 폭"],
        "dr_6b": ["6B 부도율", "6B 실제부도율"],
        "psi_micro": ["안정성 지수", "모집단 안정성", "PSI 지수"],
        "share_now": ["포용금융 비중", "충당금 비중"],
        "corp_gap": ["목표 이탈", "목표와 차이", "목표 대비 차이"],
        "ros_gap": ["수익률 차이", "기업 가계 수익률 차이"],
    }, "질의 패널 지표 찾기 — 지표 코드 → 지표명 외의 질의 표현(별칭). 별칭 문구가 질문에 들어 있으면 그 지표를 우선 (B.44)"),
    "llm.max_tokens_cap": (8000, "LLM 출력이 max_tokens 에서 잘리면(추론형 모델의 생각 토큰 등) 두 배씩(최대 2회) 늘려 다시 호출할 상한. 0 = 늘리지 않음 (B.40)"),
    "llm.pricing": ({}, "LLM 단가(1천 토큰당, 원) — {\"모델명\" 또는 \"*\": {\"prompt_per_1k\": 0, \"completion_per_1k\": 0}}. 비우면 금액 0(사내 게이트웨이)"),
    "llm.budget": ({"monthly_tokens": 0, "monthly_cost": 0, "per_agent_tokens": {}, "on_exceed": "warn", "warn_pct": 80}, "LLM 월 예산 — 0 = 한도 없음. on_exceed: warn(알림만) · block(초과 후 호출 차단, 서술은 기존 문장 유지)"),
    "orchestrator.policy": ({"enabled": True, "depends_on": {}, "derive": True, "evidence_upstream": "wf_graph_projection", "hold_sec": 15, "max_hold_sec": 300,
                             "route_on": ["change.detected", "document.ingested"], "max_route": 2, "max_chain": 3, "route_exclude": ["wf_graph_projection"], "route_rules": [], "require_approval": []},
                            "오케스트레이터 — 실행 순서(명시 의존 · 정의 도출 · 대기 간격 · 최대 대기) + LLM 경로 지정(route_on 이벤트 · 최대 추가 · 최대 연쇄 · 제외 · LLM 미연결 시 route_rules)"),
    "agents.llm_judge": ({"enabled": True, "cooldown_sec": 300, "max_context_chars": 14000, "timeout_sec": 30, "retries": 1}, "판단 에이전트(변화 감지 · 플래너 · 오케스트레이터) LLM 판단 — 켜기 · 연속 실패 시 쉬는 시간(초) · 입력 자료 최대 길이 · 호출 대기 상한(초) · 재시도 상한"),
    "ui.as_of": ("", "화면 기준일 표시 — 비우면 올라온 자료의 최신 기준일(Phase I). 특정 날짜로 고정할 때만 입력"),
    "ui.timezone": ("Asia/Seoul", "화면 산출물 생성 시각의 시간대"),
    "doc_class.labels": ({"gov_policy": "정부정책 DB", "mgmt_decision": "경영 의사결정 DB", "model_method": "모형·방법론", "branch_ref": "영업점 기준·공문", "reference": "참고 자료"}, "문서 분류 코드 → 화면 표시명"),
    "doc_class.default_origin": ({"gov_policy": "ext", "mgmt_decision": "bank", "model_method": "bank", "branch_ref": "bank", "reference": "ext"}, "문서 분류별 기본 출처(업로드 화면 기본값)"),
    "goal.rule_links": ({"goal-corp-growth": {"rule": "GOAL_TARGETS", "path": "corp_loan_growth"}, "goal-hh-control": {"rule": "GOAL_TARGETS", "path": "hh_loan_growth"}}, "경영목표 확정 시 갱신할 규칙 값 (목표 → 규칙 경로)"),
    "ui.batch_label": ("변경 기반 실행 (wf_model_monitoring · wf_inclusive_risk · wf_hq_goal_review · wf_branch_kpi)", "화면 상단 실행 라벨"),
    "branch.office_codes": ({}, "영업점 조직 코드 → 사무소 코드 (비우면 조직 코드 = 사무소 코드). 영업점 데이터(조사자사무소코드 · 사무소코드)와 사용자 소속을 잇는 기준 (Q43)"),
    # 화면 설정 (Phase K · Q148~Q151) — 기본값 · 설명은 nhdip.ui_config 한 곳에
    **UI_DEFAULTS,
}

# ═════════════════════════ 판정 규칙 (버전 관리) ═════════════════════════
PSI_BANDS_V1 = {"bands": [{"max": 0.1, "label": "안정", "severity": "info"}, {"max": 0.25, "label": "관찰", "severity": "watch"}, {"max": None, "label": "불안정", "severity": "caution"}]}
PSI_BANDS_V2 = {"bands": [{"max": 0.05, "label": "안정", "severity": "info"}, {"max": 0.1, "label": "관찰", "severity": "watch"}, {"max": None, "label": "불안정", "severity": "caution"}], "note": "Q37 잠정 임계(시나리오 판정 재현) — 업계 통상 0.1 · 0.25 와 다름"}
RULES = [
    ("MDL_PSI_BANDS", "PSI 안정성 구간", "threshold", "PSI 값 구간 → 안정/관찰/불안정 (Q37: 시나리오 판정 0.024·0.038 안정, 0.061·0.082 관찰과 일치하는 잠정 임계 — 행내 기준 확정 시 교체)", PSI_BANDS_V2),
    ("MDL_CHI_TEST", "등급계량화 카이제곱 검정", "threshold", "신뢰수준", {"confidence": 0.95}),
    ("MDL_AR_DECLINE_BANDS", "AR 하락률 구간", "threshold", "AR 하락률 → 유사/하락 주의/큰 하락", {"bands": [{"max": 10, "label": "유사수준", "severity": "info"}, {"max": 30, "label": "하락 주의", "severity": "watch"}, {"max": None, "label": "큰 하락", "severity": "caution"}]}),
    ("MDL_AR_BASELINE", "개발시점 AR (시뮬레이션 가정 · Q22 추천안)", "threshold", "모형별 개발시점 AR(%) — AR 하락률 = (개발시점 AR − 현재 AR) ÷ 개발시점 AR. 모형 개발 보고서의 실제 개발시점 AR 로 교체",
     {"CORP_MICRO": 65.12, "CORP_LARGE": 68.02, "CORP_MID": 67.21, "CORP_SMALL": 67.14, "RETAIL_AS": 54.39, "RETAIL_BS": 85.60,
      "note": "시뮬레이션 가정값 — 예: 65.12 = 49.62 ÷ (1 − 0.238). 모형 개발 보고서의 개발시점 AR 로 교체"}),
    ("ATTENTION_SCORE", "AI Attention 우선순위 점수 (Phase 2.5.4 · 시뮬레이션 가정)", "threshold",
     "수치 항목 = min(|지표 값| × 단위당 점수, 상한), 정성 항목 = 고정 점수 · 중요도 표. 단위당 점수는 목업 점수(92.4 · 86.1 · 74.8 · 78.3)를 재현하도록 맞춘 시뮬레이션 가정 — 운영 평가 기준으로 교체",
     {"importance_points": {"상": 25.0, "중": 15.0, "하": 5.0},
      "items": {
          "att-corp-gap": [
              {"label": "목표 이탈 폭", "metric": "corp_gap", "per_unit": 11.55, "max": 40, "decimals": 2, "unit": "%p"},
              {"label": "목표 중요도", "importance": "상"},
              {"label": "변화 속도", "points": 18.4, "text": "3개년 연속"},
              {"label": "정책 정합성 영향", "points": 14.8, "text": "상"}],
          "att-hh-limit": [
              {"label": "한도 소진율", "metric": "hh_bal_usage", "per_unit": 0.3285, "max": 35, "decimals": 1, "unit": "%"},
              {"label": "목표 초과", "metric": "hh_gap", "per_unit": 10.6, "max": 30, "decimals": 2, "unit": "%p"},
              {"label": "목표 중요도", "importance": "상"},
              {"label": "자본 영향", "points": 2.0}],
          "att-nim-share": [
              {"label": "변화 지속성", "points": 28.4, "text": "3개년"},
              {"label": "수익 목표 연관성", "points": 24.0, "text": "상"},
              {"label": "변화 폭", "metric": "nim_share_delta", "per_unit": 26.4, "max": 30, "decimals": 2, "unit": "%p"},
              {"label": "기타", "points": 10.0}],
          "att-inclusive-provision": [
              {"label": "사업부서 보고 연계", "points": 30.0, "text": "상"},
              {"label": "비중 증가 폭", "metric": "share_delta_pp", "per_unit": 22.29, "max": 35, "decimals": 2, "unit": "%p"},
              {"label": "신규 목표 제안 연관성", "points": 22.0}],
      },
      "note": "Q29 추천안 — 정성 항목(변화 속도 · 정책 정합성 등)은 담당자 평가 고정값, 수치 항목은 커널 지표 값"}),
    ("GOAL_CONSISTENCY", "경영목표 확정 전 정합성 검증 (6.4.7)", "threshold",
     "목표별 검사 — max_metric(지표 상한) · min_value(고정 하한) · direction(기조 반대) · asset_limit(총자산 한도). 심각도 block=확정 불가 · warn=사유 입력 후 강제 확정",
     {"goals": {
         "goal-corp-growth": [
             {"kind": "max_metric", "metric": "corp_rec_ceiling", "severity": "warn", "message": "목표 {value} 가 지주 총자산 한도 환산 상한 {limit} 을 넘습니다"},
             {"kind": "asset_limit", "severity": "warn", "message": "목표 {value} 반영 시 은행 총자산 예상 증가율 {expected} 가 지주 한도 {limit} 를 넘습니다"},
             {"kind": "direction", "policy": "corp_loan_growth", "severity": "warn", "message": "기업여신 확대 기조인데 목표를 현재 {current} 보다 낮춥니다({value})"},
             {"kind": "min_value", "value": -10, "severity": "block", "message": "목표 {value} 는 허용 하한 {limit} 미만입니다"}],
         "goal-hh-control": [
             {"kind": "min_value", "value": 0, "severity": "block", "message": "관리목표 {value} 는 {limit} 미만으로 둘 수 없습니다"},
             {"kind": "direction", "policy": "hh_loan_growth", "severity": "warn", "message": "가계여신 관리 기조인데 관리목표를 현재 {current} 보다 높입니다({value})"}],
     }}),
    ("GUIDE_CATALOG", "수행방안 가이드 카탈로그 (Phase 2.5.3)", "guide",
     "가이드 = 제목 · 안내 · 조건(지표 · 비교 · 기준). 방안별 후보 가이드를 순서대로 검사해 처음 맞는 가이드를 고른다",
     {"guides": {
         "GUIDE_RETAIL_POOL_WATCH": {"title": "소매 풀 연체 집중 모니터링", "text": "포용금융 충당금 비중이 기준시점보다 늘었습니다. 해당 풀의 연체 발생 · 연체율을 월 단위로 모니터링하고 영업점 취급 후 3개월 연체를 점검합니다.", "when": [{"metric": "share_delta_pp", "label": "충당금 비중 증감(%p)", "op": ">", "value": 0}]},
         "GUIDE_PERIODIC_WATCH": {"title": "정기 관리", "text": "포용금융 충당금 비중이 줄었거나 같습니다. 정기 점검 주기로 관리합니다.", "when": [{"metric": "share_delta_pp", "label": "충당금 비중 증감(%p)", "op": "<=", "value": 0}]},
         "GUIDE_RECALIBRATION": {"title": "등급계량화 재검토", "text": "실제부도율이 예측부도율 대표값을 넘었습니다. 표본 · 신규 취급 구성을 점검하고, 차기 모니터링에서도 초과하면 재산출을 모형위원회에 상정합니다.", "when": [{"metric": "breach_gap_6b", "label": "대표값 초과 폭(%p)", "op": ">", "value": 0}]},
         "GUIDE_PERIODIC_MODEL": {"title": "정기 모니터링 유지", "text": "실제부도율이 예측부도율 대표값 이내입니다. 정기 모니터링을 유지합니다.", "when": [{"metric": "breach_gap_6b", "label": "대표값 초과 폭(%p)", "op": "<=", "value": 0}]},
     },
      "plans": {"plan-inclusive-risk": ["GUIDE_RETAIL_POOL_WATCH", "GUIDE_PERIODIC_WATCH"], "plan-micro-recalibration": ["GUIDE_RECALIBRATION", "GUIDE_PERIODIC_MODEL"]}}),
    ("INC_PROVISION_SHARE_TREND", "포용금융 충당금 비중 추이", "threshold", "기준시점 · 비중 증감 임계(%p)", {"base_ym": "202601", "bands": [{"max": 0, "label": "감소", "severity": "info"}, {"max": 0.5, "label": "증가", "severity": "watch"}, {"max": None, "label": "증가(임계 초과)", "severity": "caution"}]}),
    ("GOAL_TARGETS", "확정 경영목표 수준", "threshold", "경영목표 확정 시 갱신 — 이탈 계산 기준", {"corp_loan_growth": 7.0, "hh_loan_growth": 4.0}),
    ("CRITIC_RULES", "서술 검증 규칙", "guide", "LLM 서술 차단 규칙", {"literal_number_regex": r"\d+(?:[.,]\d+)+\s*(?:%p?|bp|배)?|\d+\s*(?:%p?|bp|억|조|만|천|원|건|배)", "causal_phrases": ["때문에", "로 인해", "로 인하여", "원인은", "탓에", "초래했"]}),
    ("CHANGE_SIGNIFICANCE", "변화 감지 유의 기준 (B.30 · 시뮬레이션 가정 · Q51 추천안)", "threshold",
     "직전 확정값 대비 변화 — 단위별 절대 변화(abs) · 변화율(pct, %) 중 큰 비율이 1 이상이면 일반, major_multiplier 배 이상이면 주요. 지표별(metrics) 우선 · 제외(ignore) · 데이터 행 수 변화율 · 범위(scope, 영업점 산출물)",
     {"units": {"PCT": {"abs": 0.1}, "PP": {"abs": 0.1}, "RATIO": {"abs": 0.005}, "NONE": {"abs": 0.05, "pct": 1.0}, "CNT": {"pct": 1.0}, "KRW_*": {"pct": 0.5}},
      "major_multiplier": 5, "candidate_factor": 0.5, "protect_major": True, "llm_max_candidates": 25, "llm_guidance": "",
      "metrics": {"psi_micro": {"abs": 0.01}, "chi_stat": {"abs": 0.5}}, "ignore": [], "max_feed": 200, "data": {"row_change_pct": 1.0},
      "scope": {"wf_branch_kpi": {"office": {"rule": "BRANCH_SCOPE", "path": "office_code"}}},
      "note": "기준값은 시뮬레이션 가정 — 행내 유의 변화 기준(보고 기준) 확정 시 교체"}),
    ("PLANNER_POLICY", "실행 계획 기준 (B.30 · Q52 추천안)", "guide",
     "전체 서술 갱신 원인(full_refresh_on) · 정기 실행 시 무조건 갱신 여부 · 데이터 변경 시 수치 없는 인사이트 갱신 · 한 번에 서술할 최대 건수(0 = 제한 없음)",
     {"full_refresh_on": ["manual", "rule.changed", "config.changed"], "force_on": ["manual"], "refresh_on_schedule": False, "narrate_on_data_change": True, "max_targets": 0,
      "max_followups": 2, "max_chain": 3, "followup_exclude": ["wf_graph_projection"], "llm_guidance": ""}),
    ("ROUNDING", "반올림 정책", "rounding", "지표별 반올림은 지표 정의에서, 기본값은 설정 calc.rounding_default", {"default": "HALF_UP", "note": "요구사항 Q9 확정 — 사사오입(HALF_UP): 9.1575% → 9.16%"}),
]

# ═════════════════════════ 온톨로지 스키마 v2 (설계 §19.3) ═════════════════════════
def _c(label, desc, key_hint="name", extractable=True, resolve=None, required=None):
    return {"label": label, "description": desc, "key_hint": key_hint, "extractable": extractable, **({"resolve": resolve} if resolve else {}), "required": required or []}


ONTOLOGY_CLASSES = [
    _c("Dataset", "데이터셋 정의", "code", extractable=False),
    _c("DatasetVersion", "적재 버전", "code:v", extractable=False),
    _c("Metric", "지표(화면 수치)", "code", extractable=False),
    _c("Workflow", "에이전틱 워크플로우", "code", extractable=False),
    _c("Artifact", "화면 산출물(인사이트·보고서·탭)", "key", extractable=False),
    _c("Document", "문서(BankDocument / ExternalDocument)", "origin:doc_code", extractable=False),
    _c("DocClass", "문서 분류 DB", "code", extractable=False),
    _c("Issuer", "외부 문서 발행 기관", "name"),
    _c("PolicyTheme", "정책·경영 주제 (포용금융 · 기업여신 확대 · 가계부채 관리 · 자본비율 관리 등)", "theme", resolve="master"),
    _c("ProductGroup", "상품군 (새희망홀씨대출 · 햇살론 · 사잇돌 등)", "group", resolve="master"),
    _c("Product", "상품코드", "product_code", extractable=False),
    _c("Segment", "분석 세그먼트 (대기업·외감·비외감·소기업·기업형소호 / 개인 풀)", "code", resolve="master"),
    _c("RatingModel", "신용평가모형", "model_code", resolve="master"),
    _c("BusinessDomain", "사업부문 (기업여신 · 가계여신 등)", "code", resolve="master"),
    _c("CapitalConstraint", "자본·한도 제약 (총자산 증가율 · RWA 순증 · 부서별 RWA 배분)", "code", resolve="master"),
    _c("Candidate", "스키마·마스터로 해석되지 않은 추출 결과 (검토 대기)", "raw", extractable=False),
]

ONTOLOGY_RELATIONS = [
    {"type": "HAS_VERSION", "from": "Dataset", "to": "DatasetVersion", "extractable": False},
    {"type": "FEEDS", "from": "Dataset", "to": "Metric", "extractable": False},
    {"type": "DERIVED_FROM", "from": "Metric", "to": "Metric", "extractable": False},
    {"type": "USES", "from": "Workflow", "to": "*", "extractable": False},
    {"type": "PRODUCES", "from": "Workflow", "to": "Artifact", "extractable": False},
    {"type": "READS_CLASS", "from": "Workflow", "to": "DocClass", "extractable": False},
    {"type": "DESCRIBES", "from": "Dataset", "to": "*", "extractable": False},
    {"type": "IN_CLASS", "from": "Document", "to": "DocClass", "extractable": False},
    {"type": "ISSUED_BY", "from": "Document", "to": "Issuer"},
    {"type": "MENTIONS", "from": "Document", "to": "*"},
    {
        "type": "STATES_STANCE",
        "from": "Document",
        "to": "PolicyTheme",
        "props": ["direction"],
        "allowed": {"direction": ["expand", "manage", "maintain"]},
        "rule_keywords": {"expand": ["확대", "활성화", "공급 확대", "지원 강화", "강화"], "manage": ["관리", "억제", "건전성", "안정화"], "maintain": ["유지"]},
    },
    {"type": "SETS_CONSTRAINT", "from": "Document", "to": "CapitalConstraint"},
    {"type": "IN_GROUP", "from": "Product", "to": "ProductGroup", "extractable": False},
    {"type": "PART_OF_THEME", "from": "ProductGroup", "to": "PolicyTheme", "extractable": False},
    {"type": "APPLIES_TO", "from": "RatingModel", "to": "Segment", "extractable": False},
    {"type": "MEASURES", "from": "Metric", "to": "*", "extractable": False},
    {"type": "BELONGS_TO", "from": "Segment", "to": "BusinessDomain", "extractable": False},
]

ONTOLOGY_ALIASES = {
    "PolicyTheme": {
        "포용금융": ["포용금융", "포용적 금융", "서민금융", "취약계층", "포용", "정책서민금융", "서민금융 공급", "취약차주", "중·저신용", "중저신용"],
        "기업여신 확대": ["생산적 금융", "기업금융 활성화", "기업여신 확대", "생산적금융"],
        "가계부채 관리": ["가계부채", "가계부채 관리", "DSR", "가계여신 관리", "가계대출 관리"],
        "자본비율 관리": ["자본비율", "BIS", "RWA 순증", "자본적정성"],
    },
    "ProductGroup": {
        "새희망홀씨대출": ["새희망홀씨", "새희망홀씨대출"],
        "햇살론": ["햇살론", "햇살론뱅크", "햇살론youth", "근로자햇살론", "햇살론15", "햇살론유스", "햇살론 유스"],
        "사잇돌": ["사잇돌", "사잇돌중금리대출"],
    },
    "Segment": {
        "대기업": ["대기업"],
        "외감": ["외감", "외부감사"],
        "비외감": ["비외감"],
        "소기업": ["소기업"],
        "기업형소호": ["기업형소호", "소호"],
    },
    "RatingModel": {
        "CORP_MICRO": ["소기업 모형", "소기업모형", "소기업 신용평가모형", "소기업 평가모형"],
        "CORP_SMALL": ["중소기업 모형"],
        "CORP_MID": ["중견기업 모형"],
        "CORP_LARGE": ["대기업 모형"],
        "RETAIL_AS": ["AS모형", "저신용자 AS모형"],
        "RETAIL_BS": ["BS모형"],
    },
    "BusinessDomain": {"기업여신": ["기업여신", "기업자금대출"], "가계여신": ["가계여신", "가계자금대출"]},
    "CapitalConstraint": {
        "총자산 증가율 한도": ["총자산 최대 성장률", "총자산 증가율"],
        "RWA 순증 한도": ["RWA 순증", "RWA 한도"],
        "부서별 신용RWA 배분": ["신용RWA 한도 배분", "부서별 신용RWA"],
    },
}

# ═════════════════════════ 에이전트 · 프롬프트 ═════════════════════════
NARRATOR_SYSTEM = (
    "너는 NH농협은행 경영 의사결정 플랫폼의 분석 서술 에이전트다.\n"
    "규칙:\n"
    "1) 수치는 직접 쓰지 않고 제공된 [[fig:ID]] 마커로만 참조한다(계산은 커널이 이미 끝냈다).\n"
    "2) 인과를 단정하지 않는다('때문에', '로 인해' 금지). 관찰·비교·확인 표현을 쓴다.\n"
    "3) 근거에 없는 사실을 만들지 않는다.\n"
    "4) 출력은 JSON 하나: {\"statement\": \"...\"}"
)
EXTRACTOR_SYSTEM_V1 = (
    "너는 은행 문서를 온톨로지로 구조화하는 추출기다. 허용된 클래스와 관계만 쓰고, 모든 항목에 원문 그대로의 evidence_span 을 붙인다.\n"
    "마스터 키 목록에 있는 값이면 그 키를 key 로 쓴다. 확실하지 않으면 출력하지 않는다. JSON 만 출력한다."
)
# B.42 — 업로드 시험에서 근거 문장을 요약 · 제목 인용 · 바꿔 쓰기로 내 '부분 추출' 이 났다. 복사 규칙과 마스터 키 우선을 분명히 한다.
EXTRACTOR_SYSTEM = (
    "너는 은행 문서를 온톨로지로 구조화하는 추출기다. 허용된 클래스와 관계만 쓴다.\n"
    "1) 모든 항목에 evidence_span 을 붙인다 — 본문(또는 제목)에서 글자 그대로 복사한 한 문장 이내. 요약 · 말줄임 · 바꿔 쓰기 금지.\n"
    "2) key 는 마스터 키 목록의 키를 그대로 쓴다(별칭 · 설명형 이름 대신). 목록에 없는 대상만 원문 표현 그대로 쓴다(검토 대기로 간다).\n"
    "3) 관계의 from · to 는 엔티티 key 또는 문서 자신이면 \"$doc\". 확실하지 않으면 출력하지 않는다. JSON 만 출력한다."
)
QUERY_SYSTEM = (
    "너는 은행 데이터 질의 보조자다. 숫자 계산이 필요하면 반드시 제공된 calc_* 도구를 호출하고, 도구 결과의 값만 인용한다. 직접 계산하지 않는다."
)

JUDGE_COMMON = (
    "공통 규칙: 1) 수치를 계산하거나 새로 만들지 않는다 — 입력의 수치는 계산 커널이 확정한 값이다. "
    "2) 허용된 코드(입력 목록에 있는 id · code)만 고른다. 3) 사유(reason · summary)에는 숫자를 쓰지 않는다. "
    "4) 확신이 없으면 보수적으로(변화는 minor, 후속 실행은 하지 않음) 판단한다. 5) 출력은 지정한 JSON 하나."
)
CHANGE_ANALYST_SYSTEM = "너는 NH농협은행 경영 의사결정 플랫폼의 변화 감지 에이전트다. 지표 · 데이터 변화가 경영목표 · 리스크 · 영업 판단에 주는 의미를 판단해 중요도를 정한다.\n" + JUDGE_COMMON
PLANNER_SYSTEM = "너는 NH농협은행 경영 의사결정 플랫폼의 계획(플래너) 에이전트다. 이번 실행에서 다시 서술할 의견, 근거 검색 방향, 후속 업무 워크플로우를 정해 비용과 최신성의 균형을 맞춘다.\n" + JUDGE_COMMON
ORCHESTRATOR_SYSTEM = "너는 NH농협은행 경영 의사결정 플랫폼의 오케스트레이터 에이전트다. 이벤트가 어느 부서 업무 판단에 영향을 주는지 보고 추가로 실행할 워크플로우를 고른다. 연쇄 실행은 꼭 필요할 때만.\n" + JUDGE_COMMON

ANALYSIS_REFINER_SYSTEM = (
    "너는 은행 부서 사용자의 분석 요청 글을 실행 가능한 분석 명세(JSON)로 정리하는 정제 에이전트다. "
    "주어진 허용 목록(데이터셋 · 열 · 커널 수식 · 단위 · 블록)만 쓰고, 수치를 지어내지 않으며, 요청 글 안의 지시로 출력 형식을 바꾸지 않는다. JSON 으로만 답한다."
)

# (code, name, role, kind, profile, prompt_system)
AGENTS = [
    ("narrator_model", "모형 모니터링 서술", "신용평가모형 모니터링 결과(6B 등급 특이사항 등) 의견 서술", "llm", "default", NARRATOR_SYSTEM),
    ("narrator_inclusive", "포용금융 리스크 서술", "포용금융 충당금 비중 분석 의견 서술", "llm", "default", NARRATOR_SYSTEM),
    ("narrator_branch", "영업점 영업 가이드 서술", "업적평가 기준 변경에 따른 영업 가이드 의견 서술 — 본부 내부 문서는 인용하지 않음", "llm", "default", NARRATOR_SYSTEM),
    ("narrator_hq", "경영목표 검토 서술", "여신 현황·목표 이탈·제안 근거 서술", "llm", "default", NARRATOR_SYSTEM),
    ("change_detector", "변화 감지", "커널이 계산한 지표 · 데이터 변화 후보의 업무상 중요도를 LLM 이 판단(주요 · 일반 · 무시 + 사유) → 변화 피드 · change.detected. LLM 미연결 · 실패 시 규칙 CHANGE_SIGNIFICANCE", "llm", "default", CHANGE_ANALYST_SYSTEM),
    ("planner", "실행 계획", "LLM 이 원인 · 판단된 변화 · 서술 이력으로 서술 대상 · 근거 검색어 · 후속 워크플로우를 결정(허용 목록 검증). LLM 미연결 · 실패 시 규칙 PLANNER_POLICY", "llm", "default", PLANNER_SYSTEM),
    ("orchestrator", "오케스트레이터", "이벤트마다 LLM 이 영향받는 워크플로우를 추가 지정하고, 실행 순서(상위 대기 · 원인 연쇄 · 즉시 실행)는 규칙으로 보장 (설정 orchestrator.policy)", "llm", "default", ORCHESTRATOR_SYSTEM),
    ("critic", "서술 검증", "리터럴 숫자 · 미등록 마커 · 인과 단정 차단 (규칙 기반)", "rule", None, ""),
    ("ontology_extractor", "온톨로지 구조화", "문서 → 엔티티·관계 추출 (스키마 검증 후 그래프 반영)", "llm", "default", EXTRACTOR_SYSTEM),
    ("embedder", "문서 임베딩", "청크 임베딩(pgvector) — 임베딩 모델 지정 필요", "llm", "embedding", ""),
    ("analysis_refiner", "분석 정제", "사용자 글(도메인 지식 · 하고 싶은 분석) → 분석 명세 초안(허용 목록 검증) — LLM 미연결 · 실패 시 규칙 정제 (Phase C · DAG-02)", "llm", "default", ANALYSIS_REFINER_SYSTEM),
    ("report_renderer", "범용 렌더링", "분석 명세 구성 + 계산 결과 + 판단으로 표준 보고서 조립(결정론, LLM 없음 · DAG-06)", "rule", None, ""),
    ("query_assistant", "질의 보조", "자연어 질의 → 커널 도구 호출(CALC-10)", "llm", "default", QUERY_SYSTEM),
]

# 질문하기 통합 지식 색인 설정 (Phase D · 요구사항 §21) — 정의는 defs_knowledge.py, 설정 시드에 합친다
from .defs_knowledge import SETTINGS as _KB_SETTINGS  # noqa: E402

SETTINGS.update(_KB_SETTINGS)
