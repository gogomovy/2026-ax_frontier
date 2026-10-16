/**
 * 데이터 접근 계층 (서버 컴포넌트 전용) — 백엔드 화면 API (`/screens/*`, 세션 쿠키 전달 · 권한 검사).
 * 화면의 수치 · 기간 · 문구는 모두 업로드된 자료로 계산된 산출물에서 온다(Phase I — 목데이터 모드 없음 · Q140).
 */
import { apiGet, apiTry } from "./api-server";
import type {
  ActionPlan,
  AnalysisSpaceInfo,
  AnalysisSpaceTabs,
  AnalysisTab,
  BranchDashboard,
  BranchOfficeList,
  RegionKpi,
  BranchTabs,
  BranchTarget,
  CapitalView,
  CascadeNode,
  ChangeFeed,
  ComparisonView,
  DatasetMeta,
  DefaultRateTrend,
  DocumentMeta,
  DocumentView,
  DomainCardInfo,
  Goal,
  HqDashboard,
  InclusiveAnalysis,
  Insight,
  LoanOverview,
  ProfitabilityRow,
  Proposal,
  ReportDoc,
  ReportRequest,
  ReviewQueueItem,
  RiskDashboard,
  Term,
} from "./types";

const api = <T,>(path: string) => apiGet<T>(path);
const enc = encodeURIComponent;

/* ── 조직·도메인 ─────────────────────────────────────────── */
export const getDomains = (): Promise<DomainCardInfo[]> => api("/screens/domains");
export const getDomain = (code: string): Promise<DomainCardInfo | null> => api(`/screens/domains/${enc(code)}`);

/* ── 종합기획부 ──────────────────────────────────────────── */
export const getHqDashboard = (): Promise<HqDashboard> => api("/screens/hq-dashboard");
export const getAttentions = (): Promise<Insight[]> => api("/screens/attentions");
export const getReportRequests = (): Promise<ReportRequest[]> => api("/screens/report-requests");
export const getLoanOverview = (): Promise<LoanOverview> => api("/screens/loan-overview");
export const getComparisonView = (): Promise<ComparisonView> => api("/screens/comparison-view");
export const getCapitalView = (): Promise<CapitalView> => api("/screens/capital-view");
export const getProfitability = (): Promise<ProfitabilityRow[]> => api("/screens/profitability");
export const getGoals = (): Promise<Goal[]> => api("/screens/goals");
export const getGoal = (id: string): Promise<Goal | null> => api(`/screens/goals/${enc(id)}`);
export const getProposals = (): Promise<Proposal[]> => api("/screens/proposals");
export const getReviewQueue = (): Promise<ReviewQueueItem[]> => api("/screens/review-queue");
export const getCascade = (): Promise<CascadeNode[]> => api("/screens/cascade");

/* ── 신용리스크관리부 ────────────────────────────────────── */
export const getRiskDashboard = (): Promise<RiskDashboard> => api("/screens/risk-dashboard");
/** 분석 레지스트리(기존 탭 + 분석 에이전트 탭 · Phase C) */
export const getAnalysisTabs = (): Promise<{ current: AnalysisTab[]; previous: AnalysisTab[]; builder?: { allowed: boolean }; space?: { key: string; label: string; path: string; scoped?: string | null } }> => api("/screens/analysis/risk/tabs");

/* ── 부서 분석 공간 (Phase C · DAG-07) ── */
/** 지점 인자(B.47 · 다지점) — 비우면 서버가 사용자 소속 영업점 → 기본 지점으로 고른다 */
const officeQs = (office?: string | null) => (office ? `?office=${enc(office)}` : "");
export const getAnalysisSpaces = (): Promise<AnalysisSpaceInfo[]> => api("/screens/analysis/spaces");
export const getSpaceTabs = (space: string, office?: string | null): Promise<AnalysisSpaceTabs | null> => api(`/screens/analysis/${enc(space)}/tabs${officeQs(office)}`);
/** 화면 안에 맞춤 분석 탭을 붙일 때 — 권한이 없거나 실패하면 null (화면 자체는 그대로 · Q109) */
export const getSpaceTabsOptional = (space: string): Promise<AnalysisSpaceTabs | null> => apiTry<AnalysisSpaceTabs>(`/screens/analysis/${enc(space)}/tabs`);
export const getSpaceReport = (space: string, tabKey: string, office?: string | null): Promise<ReportDoc | null> =>
  api(`/screens/analysis/${enc(space)}/reports/${enc(tabKey)}${officeQs(office)}`);
export const getReport = (tabKey: string): Promise<ReportDoc | null> => api(`/screens/reports/${enc(tabKey)}`);
export const getInclusiveAnalysis = (): Promise<InclusiveAnalysis> => api("/screens/inclusive");
export const getActionPlans = (): Promise<ActionPlan[]> => api("/screens/action-plans");
export const getDefaultRateTrend = (): Promise<DefaultRateTrend> => api("/screens/default-rate-trend");
export const getBranchTargets = (): Promise<BranchTarget[]> => api("/screens/branch-targets");

/* ── 영업점 (B.29) — 서버가 사용자 영업점과 산출물 영업점을 대조한다 ─────────── */
export const getBranchOffices = (): Promise<BranchOfficeList> => api("/screens/branch/offices");
/** 영업본부 통합 업적평가 (§37 RGN) — 지역본부 직원은 자기 지역, 관리자는 region 인자로 고른다 */
export const getRegionKpi = (region?: string | null): Promise<RegionKpi> => api(`/screens/region/kpi${region ? `?region=${enc(region)}` : ""}`);
export const getBranchDashboard = (office?: string | null): Promise<BranchDashboard> => api(`/screens/branch/dashboard${officeQs(office)}`);
export const getBranchTabs = (office?: string | null): Promise<BranchTabs> => api(`/screens/branch/tabs${officeQs(office)}`);
export const getBranchReport = (tabKey: string, office?: string | null): Promise<ReportDoc | null> => api(`/screens/branch/reports/${enc(tabKey)}${officeQs(office)}`);

/* ── 지식 ───────────────────────────────────────────────── */
export const getDocuments = (dbClass?: string): Promise<DocumentMeta[]> => api(`/screens/documents${dbClass ? `?dbClass=${enc(dbClass)}` : ""}`);
/** 원본 문서 뷰어 — 면별 본문 + 인용 강조 */
export async function getDocumentView(params: { id?: string; file?: string; title?: string; page?: number; q?: string }): Promise<DocumentView | null> {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== "") qs.set(k, String(v));
  return api(`/documents/view?${qs.toString()}`);
}
export const getDatasets = (): Promise<DatasetMeta[]> => api("/screens/datasets");
export const getTerms = (): Promise<Term[]> => api("/screens/terms");

/* ── 변화 감지 에이전트 (B.30) — 서버가 화면 권한 · 영업점 범위로 거른다 ── */
export const getChanges = (workflow?: string, limit = 8): Promise<ChangeFeed> => api(`/screens/changes?limit=${limit}${workflow ? `&workflow=${enc(workflow)}` : ""}`);

/** 산출물을 만드는 워크플로우 (서버의 워크플로우 정의 outputs 기준) */
export async function getProducer(key: string): Promise<string | null> {
  return (await api<{ workflow: string | null }>(`/screens/producer?key=${enc(key)}`)).workflow;
}

/* ── 인사이트 조회 ──────────────────────────────────────── */
export const getInsight = (id: string): Promise<Insight | null> => api(`/screens/insights/${enc(id)}`);
