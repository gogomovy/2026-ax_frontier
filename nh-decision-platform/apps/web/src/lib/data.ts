/**
 * 데이터 접근 계층 (서버 컴포넌트 전용).
 *  - NEXT_PUBLIC_DATA_SOURCE=api  → 백엔드 화면 API (`/screens/*`, 세션 쿠키 전달 · 권한 검사)
 *  - 그 외(mock)                   → 목데이터 (백엔드 없이 화면 단독 실행)
 * 함수 시그니처와 응답 형식은 두 모드가 같다.
 */
import { CAPITAL_VIEW, COMPARISON_VIEW, LOAN_OVERVIEW, PROFITABILITY } from "@/mock/finance";
import { CASCADE, GOALS, PROPOSALS, REVIEW_QUEUE } from "@/mock/goals";
import { DATASETS, DOCUMENTS } from "@/mock/knowledge";
import { TERMS } from "@/mock/terms";
import { CHANGE_FEED } from "@/mock/changes";
import { BRANCH_DASHBOARD, BRANCH_REPORTS, BRANCH_TABS, PRIME_OPINION, SEOMIN_OPINION } from "@/mock/branch";
import { ATTENTIONS, DOMAIN_MAP, DOMAINS, HQ_DASHBOARD, REPORT_REQUESTS } from "@/mock/dashboard";
import {
  ACTION_PLANS,
  ANALYSIS_TABS,
  BRANCH_TARGETS,
  DEFAULT_RATE_TREND,
  INCLUSIVE,
  MODEL_OPINION,
  INCLUSIVE_OPINION,
  PREVIOUS_TABS,
  REPORTS,
  RISK_DASHBOARD,
} from "@/mock/risk";
import { apiGet } from "./api-server";
import { API_MODE } from "./config";
import type {
  ActionPlan,
  AnalysisTab,
  BranchDashboard,
  BranchOfficeList,
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

export { DATA_SOURCE } from "./config";

const api = <T,>(path: string) => apiGet<T>(path);

/* ── 조직·도메인 ─────────────────────────────────────────── */
export async function getDomains(): Promise<DomainCardInfo[]> {
  return API_MODE ? api("/screens/domains") : DOMAINS;
}
export async function getDomain(code: string): Promise<DomainCardInfo | null> {
  return API_MODE ? api(`/screens/domains/${encodeURIComponent(code)}`) : (DOMAIN_MAP[code] ?? null);
}

/* ── 종합기획부 ──────────────────────────────────────────── */
export async function getHqDashboard(): Promise<HqDashboard> {
  return API_MODE ? api("/screens/hq-dashboard") : HQ_DASHBOARD;
}
export async function getAttentions(): Promise<Insight[]> {
  return API_MODE ? api("/screens/attentions") : ATTENTIONS;
}
export async function getReportRequests(): Promise<ReportRequest[]> {
  return API_MODE ? api("/screens/report-requests") : REPORT_REQUESTS;
}
export async function getLoanOverview(): Promise<LoanOverview> {
  return API_MODE ? api("/screens/loan-overview") : LOAN_OVERVIEW;
}
export async function getComparisonView(): Promise<ComparisonView> {
  return API_MODE ? api("/screens/comparison-view") : COMPARISON_VIEW;
}
export async function getCapitalView(): Promise<CapitalView> {
  return API_MODE ? api("/screens/capital-view") : CAPITAL_VIEW;
}
export async function getProfitability(): Promise<ProfitabilityRow[]> {
  return API_MODE ? api("/screens/profitability") : PROFITABILITY;
}
export async function getGoals(): Promise<Goal[]> {
  return API_MODE ? api("/screens/goals") : GOALS;
}
export async function getGoal(id: string): Promise<Goal | null> {
  return API_MODE ? api(`/screens/goals/${encodeURIComponent(id)}`) : (GOALS.find((g) => g.id === id) ?? null);
}
export async function getProposals(): Promise<Proposal[]> {
  return API_MODE ? api("/screens/proposals") : PROPOSALS;
}
export async function getReviewQueue(): Promise<ReviewQueueItem[]> {
  return API_MODE ? api("/screens/review-queue") : REVIEW_QUEUE;
}
export async function getCascade(): Promise<CascadeNode[]> {
  return API_MODE ? api("/screens/cascade") : CASCADE;
}

/* ── 신용리스크관리부 ────────────────────────────────────── */
export async function getRiskDashboard(): Promise<RiskDashboard> {
  return API_MODE ? api("/screens/risk-dashboard") : RISK_DASHBOARD;
}
export async function getAnalysisTabs(): Promise<{ current: AnalysisTab[]; previous: AnalysisTab[] }> {
  return API_MODE ? api("/screens/analysis-tabs") : { current: ANALYSIS_TABS, previous: PREVIOUS_TABS };
}
export async function getReport(tabKey: string): Promise<ReportDoc | null> {
  return API_MODE ? api(`/screens/reports/${encodeURIComponent(tabKey)}`) : (REPORTS[tabKey] ?? null);
}
export async function getInclusiveAnalysis(): Promise<InclusiveAnalysis> {
  return API_MODE ? api("/screens/inclusive") : INCLUSIVE;
}
export async function getActionPlans(): Promise<ActionPlan[]> {
  return API_MODE ? api("/screens/action-plans") : ACTION_PLANS;
}
export async function getDefaultRateTrend(): Promise<DefaultRateTrend> {
  return API_MODE ? api("/screens/default-rate-trend") : DEFAULT_RATE_TREND;
}
export async function getBranchTargets(): Promise<BranchTarget[]> {
  return API_MODE ? api("/screens/branch-targets") : BRANCH_TARGETS;
}

/* ── 영업점 (B.29) — 서버가 사용자 영업점과 산출물 영업점을 대조한다 ─────────── */
/** 지점 인자(B.47 · 다지점) — 비우면 서버가 사용자 소속 영업점 → 기본 지점으로 고른다 */
const officeQs = (office?: string | null) => (office ? `?office=${encodeURIComponent(office)}` : "");
export async function getBranchOffices(): Promise<BranchOfficeList> {
  return API_MODE
    ? api("/screens/branch/offices")
    : { offices: [{ code: BRANCH_DASHBOARD.office.code, name: BRANCH_DASHBOARD.office.name, available: true, primary: true }], default: BRANCH_DASHBOARD.office.code };
}
export async function getBranchDashboard(office?: string | null): Promise<BranchDashboard> {
  return API_MODE ? api(`/screens/branch/dashboard${officeQs(office)}`) : { ...BRANCH_DASHBOARD, available: true, viewer: null };
}
export async function getBranchTabs(office?: string | null): Promise<BranchTabs> {
  return API_MODE ? api(`/screens/branch/tabs${officeQs(office)}`) : BRANCH_TABS;
}
export async function getBranchReport(tabKey: string, office?: string | null): Promise<ReportDoc | null> {
  return API_MODE ? api(`/screens/branch/reports/${encodeURIComponent(tabKey)}${officeQs(office)}`) : (BRANCH_REPORTS[tabKey] ?? null);
}

/* ── 지식 ───────────────────────────────────────────────── */
export async function getDocuments(dbClass?: string): Promise<DocumentMeta[]> {
  if (API_MODE) return api(`/screens/documents${dbClass ? `?dbClass=${encodeURIComponent(dbClass)}` : ""}`);
  return dbClass ? DOCUMENTS.filter((d) => d.dbClass === dbClass) : DOCUMENTS;
}
/** 원본 문서 뷰어 — API 모드 전용(목업 모드는 원본 저장소가 없으므로 null) */
export async function getDocumentView(params: { id?: string; file?: string; title?: string; page?: number; q?: string }): Promise<DocumentView | null> {
  if (!API_MODE) return null;
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== "") qs.set(k, String(v));
  return api(`/documents/view?${qs.toString()}`);
}
export async function getDatasets(): Promise<DatasetMeta[]> {
  return API_MODE ? api("/screens/datasets") : DATASETS;
}
export async function getTerms(): Promise<Term[]> {
  return API_MODE ? api("/screens/terms") : TERMS;
}

/* ── 변화 감지 에이전트 (B.30) — 서버가 화면 권한 · 영업점 범위로 거른다 ── */
export async function getChanges(workflow?: string, limit = 8): Promise<ChangeFeed> {
  if (API_MODE) return api(`/screens/changes?limit=${limit}${workflow ? `&workflow=${encodeURIComponent(workflow)}` : ""}`);
  const items = CHANGE_FEED.items.filter((i) => !workflow || i.workflow === workflow).slice(0, limit);
  return { ...CHANGE_FEED, items };
}

/** 산출물을 만드는 워크플로우 (API 모드 — 서버의 워크플로우 정의 outputs 기준). 목데이터 모드는 null */
export async function getProducer(key: string): Promise<string | null> {
  if (!API_MODE) return null;
  return (await api<{ workflow: string | null }>(`/screens/producer?key=${encodeURIComponent(key)}`)).workflow;
}

/* ── 인사이트 조회 ──────────────────────────────────────── */
const ALL_INSIGHTS: Insight[] = [...ATTENTIONS, MODEL_OPINION, INCLUSIVE_OPINION, PRIME_OPINION, SEOMIN_OPINION];
export async function getInsight(id: string): Promise<Insight | null> {
  return API_MODE ? api(`/screens/insights/${encodeURIComponent(id)}`) : (ALL_INSIGHTS.find((i) => i.id === id) ?? null);
}
