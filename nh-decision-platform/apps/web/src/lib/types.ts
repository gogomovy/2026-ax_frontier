/**
 * 도메인 타입. 향후 백엔드 API 응답 스키마와 동일한 형태를 유지한다.
 * (설계서 §11.4 응답 예시 기준 — MVP 는 목데이터가 이 타입을 그대로 채운다)
 */

export type DataOrigin = "actual" | "simulated" | "mixed";
export type Severity = "info" | "watch" | "caution" | "critical";
export type EvidenceCategory = "bank_data" | "internal_direction" | "external_policy";
export type AlignmentVerdict = "aligned" | "conflict" | "unknown";
export type Persona = "P1" | "P2" | "P3";

/** 계산 추적 — 화면의 모든 수치는 이 정보를 가진다 (요구사항 UX-03, CALC-01) */
export interface CalcInputRef {
  key: string;
  label: string;
  value: string;
  unit?: string;
  /** 원천 위치: 파일!셀 또는 테이블/행 */
  source: string;
}

export interface CalcTrace {
  calcId: string;
  formulaId: string;
  formulaVersion: number;
  expression: string;
  inputs: CalcInputRef[];
  executedAt: string;
  note?: string;
  /** 계산은 됐지만 확인이 필요한 사항 (기준 시점 불일치 · 단위 경고) */
  warnings?: string[];
}

/** 참조 가능한 수치. LLM 이 만든 리터럴이 아니라 계산 결과를 가리킨다 (PRIN-05) */
export interface Figure {
  id: string;
  label: string;
  value: number | null;
  unit: "KRW_MN" | "KRW_BN" | "KRW_TN" | "PCT" | "PP" | "CNT" | "RATIO" | "NONE";
  decimals?: number;
  dataOrigin: DataOrigin;
  /** 값이 없을 때 표시 문구 (예: 데이터 미제공) */
  undefinedLabel?: string;
  calc?: CalcTrace;
  /** 원천 데이터 직접 참조인 경우 */
  sourceRef?: string;
  /** 최근 계산이 실패해 이전 값을 보여 주는 중 (B.32) */
  stale?: boolean;
  staleReason?: string;
}

export interface EvidenceDoc {
  title: string;
  issuer?: string;
  effectiveDate?: string;
  page?: number;
  sectionPath?: string;
  dbClass: "gov_policy" | "mgmt_decision" | "model_method" | "branch_ref" | "external_web";
  isOfficial?: boolean;
  fileName?: string;
}

export interface Evidence {
  id: string;
  category: EvidenceCategory;
  sourceKind: "doc_chunk" | "metric_value" | "calc_run" | "external" | "none";
  label: string;
  snippet?: string;
  relevance?: number;
  doc?: EvidenceDoc;
  /** 데이터 근거인 경우 참조 지표/계산 */
  figureId?: string;
  tableRef?: string;
}

export interface Verification {
  checkCode:
    | "numeric_provenance"
    | "evidence_present"
    | "causality_language"
    | "alignment"
    | "goal_consistency";
  passed: boolean;
  detail?: string;
}

export interface Insight {
  id: string;
  kind: "attention" | "opinion" | "analysis_result";
  persona: Persona;
  domainCode: string;
  subDomain?: string;
  title: string;
  /** 인라인 마커 포함: [[fig:ID]] · {{term:CODE|표시어}} */
  statement: string;
  severity: Severity;
  asOf: string;
  dataOrigin: DataOrigin;
  figures: Record<string, Figure>;
  evidence: Evidence[];
  verifications: Verification[];
  rankScore?: number;
  rankBasis?: string;
  relatedGoalId?: string;
  reportKind?: ReportKind;
  reportAnchor?: string;
  tabKey?: string;
}

export interface ReportRequest {
  id: string;
  fromOrg: string;
  toOrg: string;
  reqType: "perf_report" | "direction_check" | "new_biz_check";
  reqTypeLabel: string;
  title: string;
  body: string;
  dueDate?: string;
  createdAt: string;
  status: "open" | "reviewing" | "done";
  relatedGoalId?: string;
}

export interface DomainCardInfo {
  domainCode: string;
  name: string;
  status: "active" | "placeholder";
  summary?: string;
  headline?: Figure;
  sub?: { label: string; figure: Figure }[];
  note?: string;
}

/* ── 경영목표 ───────────────────────────────────────────────── */
export type GoalStatus = "active" | "ai_proposed" | "under_review" | "pending_confirm" | "archived";

export interface Goal {
  id: string;
  domainCode: string;
  subDomain?: string;
  title: string;
  targetType: "growth" | "limit" | "ratio" | "amount" | "qualitative";
  direction: "increase" | "decrease" | "maintain";
  targetValue: number | null;
  targetText?: string;
  unit: Figure["unit"];
  decimals?: number;
  periodLabel: string;
  status: GoalStatus;
  creationMode: "existing" | "user_manual" | "ai_proposed";
  updatedAt: string;
  version: number;
  metricLabel: string;
  actual?: Figure;
  /** 목표 대비 이탈 (pp 또는 %) */
  gap?: Figure;
  /** gap 의 의미 라벨 (예: 목표 대비 / 진행률 / 이탈 / 초과 / 여유) */
  gapLabel?: string;
  /** gap 을 부호와 함께 표시할지 (진행률처럼 부호가 불필요한 경우 false) */
  gapSigned?: boolean;
  gapVerdict?: "on_track" | "below" | "near_limit" | "breach";
  history?: GoalHistoryEntry[];
}

export interface GoalHistoryEntry {
  version: number;
  at: string;
  actor: string;
  from?: string;
  to: string;
  reason: string;
  creationMode: Goal["creationMode"];
  evidenceIds: string[];
}

export interface ConstraintCheck {
  label: string;
  ceiling: Figure;
  proposed: Figure;
  headroom: Figure;
  passed: boolean;
  basisDoc?: EvidenceDoc;
}

export interface Proposal {
  id: string;
  kind: "goal_modify" | "goal_new";
  targetGoalId?: string;
  domainCode: string;
  title: string;
  /** 왜 수정해야 하는가 (Question 1) */
  judgement: string;
  /** 왜 이 수치인가 (Question 2) */
  recommendation: {
    mode: "range" | "point" | "direction_only";
    low?: number;
    high?: number;
    value?: number;
    unit: Figure["unit"];
    decimals?: number;
    currentValue?: number;
    text: string;
  };
  ruleId: string;
  ruleInputs: { label: string; value: string; source: string }[];
  figures: Record<string, Figure>;
  evidence: Evidence[];
  constraintChecks: ConstraintCheck[];
  alignment: { verdict: AlignmentVerdict; matched: string[]; conflicts: string[] };
  verifications: Verification[];
  asOf: string;
  /** 사용자 액션 결과 (MVP: 클라이언트 상태) */
  action?: "keep" | "adopt" | "manual_edit" | "rejected";
}

export interface ReviewQueueItem {
  id: string;
  title: string;
  sourceKind: "attention" | "report_request" | "agent_scan";
  sourceLabel: string;
  domainCode: string;
  registeredAt: string;
}

/* ── 여신 실적 ─────────────────────────────────────────────── */
export interface SeriesPoint {
  label: string;
  value: number | null;
}

export interface ComparisonRow {
  label: string;
  current: Figure;
  prior: Figure;
  prior2?: Figure;
  diff: Figure;
  diffRate: Figure;
}

export interface LoanOverview {
  asOf: string;
  generatedAt: string;
  dataOrigin: DataOrigin;
  revenue: {
    rows: ComparisonRow[];
    nimShare: Figure;
    nimShareTrend: SeriesPoint[];
    narrative: string;
    narrativeFigures: Record<string, Figure>;
    evidence: Evidence[];
  };
  corporate: LoanSegmentDetail;
  household: LoanSegmentDetail;
}

export interface LoanSegmentDetail {
  key: "corporate" | "household";
  name: string;
  balance: Figure;
  growth: Figure;
  share: Figure;
  interestRevenue: Figure;
  monthly: SeriesPoint[];
  yearly: SeriesPoint[];
  goalId?: string;
  goalLabel?: string;
  goalValue?: Figure;
  gap?: Figure;
  gapVerdict?: Goal["gapVerdict"];
  narrative: string;
  narrativeFigures: Record<string, Figure>;
  evidence: Evidence[];
}

export interface ComparisonView {
  asOf: string;
  balanceSeries: { name: string; points: SeriesPoint[] }[];
  shareSeries: { name: string; points: SeriesPoint[] }[];
  interestRows: ComparisonRow[];
  balanceRows: ComparisonRow[];
  divergence: Insight | null;
  proxyNote: string;
}

/* ── 자본·수익성 ───────────────────────────────────────────── */
export interface CapitalView {
  asOf: string;
  constraints: {
    id: string;
    kind: string;
    label: string;
    scope: string;
    value: Figure;
    period: string;
    issuer: string;
    doc: EvidenceDoc;
  }[];
  bankTarget: { label: string; value: Figure; ceiling: Figure; headroom: Figure; passed: boolean };
  rwaAllocation: { org: string; allocated: Figure; used: Figure; usageRate: Figure }[];
  bisSimulation: { label: string; value: Figure; floor: Figure; note: string }[];
  proxyNote: string;
  evidence: Evidence[];
}

export interface ProfitabilityRow {
  assetClass: string;
  balance: Figure;
  revenue: Figure;
  returnOnScale: Figure;
  trend: SeriesPoint[];
  rank: number;
  verdict: string;
}

/* ── 모형 모니터링 ─────────────────────────────────────────── */
export interface ModelSummaryRow {
  modelCode: string;
  name: string;
  portfolio: "corp" | "retail";
  segment: string;
  psi?: Figure;
  ar: Figure;
  arDecline: Figure;
  ks: Figure;
  auroc: Figure;
  verdict: string;
  verdictSeverity: Severity;
  verdictBasis: string;
  dataOrigin: DataOrigin;
}

export interface ModelGradeRow {
  gradeCode: string;
  obsCount: number;
  obsShare: number;
  defaultCount: number;
  defaultRate: number;
  pdMid?: number;
  pdMax?: number;
  ks?: number;
  auroc?: number;
  sdrRank?: number;
  breach?: "within_mid" | "above_mid_within_max" | "above_max";
  monotonicBreak?: boolean;
}

export interface PsiBucketRow {
  bucket: string;
  baseShare: number;
  currentShare: number;
  contribution: number;
}

/* ── 포용금융 ─────────────────────────────────────────────── */
export interface InclusiveProductRow {
  productCode: string;
  productName: string;
  productGroup: string;
  provisionBase: number;
  provisionNow: number;
  diff: number;
  contribution: number;
}

export interface InclusiveAnalysis {
  asOf: string;
  baseYm: string;
  nowYm: string;
  shareBase: Figure;
  shareNow: Figure;
  shareDeltaPP: Figure;
  shareDeltaPct: Figure;
  provisionInclusiveNow: Figure;
  provisionTotalNow: Figure;
  verdict: "증가" | "유지" | "감소";
  severity: Severity;
  products: InclusiveProductRow[];
  groupSummary: { group: string; codes: number; base: number; now: number; deltaPP: number }[];
  unmatchedCodes: string[];
  exposure: { label: string; figure: Figure }[];
  limitations: string[];
  ruleId: string;
}

/* ── 보고서 ───────────────────────────────────────────────── */
export type ReportKind = "model_monitoring" | "inclusive_risk" | "goal_review" | "branch_prime_corp" | "branch_seomin";

export interface ReportTableBlock {
  caption?: string;
  columns: { key: string; label: string; align?: "left" | "right"; term?: string }[];
  rows: Record<string, string | number | null>[];
  highlightRowKey?: string;
  highlightRowValue?: string | number;
  note?: string;
}

export interface ReportBlock {
  type: "p" | "ul" | "callout" | "chart" | "table" | "kv";
  /** p/callout: 인라인 마커 지원 */
  text?: string;
  items?: string[];
  tone?: "info" | "attention" | "critical" | "success";
  chart?: {
    kind: "bar" | "line" | "stacked-share";
    title: string;
    series: { name: string; points: SeriesPoint[] }[];
    unit: Figure["unit"];
  };
  table?: ReportTableBlock;
  kv?: { label: string; value: string; term?: string }[];
}

export interface ReportSection {
  id: string;
  heading: string;
  level: 2 | 3;
  blocks: ReportBlock[];
}

export interface ReportDoc {
  id: string;
  kind: ReportKind;
  title: string;
  subtitle: string;
  asOf: string;
  generatedAt: string;
  dataOrigin: DataOrigin;
  toc: { id: string; label: string; level: 2 | 3 }[];
  sections: ReportSection[];
  figures: Record<string, Figure>;
  opinions: Insight[];
  evidence: Evidence[];
  limitations: string[];
  /** 영업점 보고서 — 대상 영업점 (B.29) */
  office?: BranchOffice;
  /** 이 보고서를 만드는 워크플로우 (서버가 산출물 정의에서 찾아 붙인다) */
  workflow?: string | null;
}

export interface AnalysisTab {
  tabKey: string;
  label: string;
  reportKind: ReportKind;
  insightId: string;
  severity: Severity;
  generation: "current" | "previous";
  asOf: string;
  generatedAt: string;
  /** 보고서 산출물 키 (기본 report.{tabKey}) */
  reportKey?: string;
}

/* ── 영업점 (B.29) — 업적평가 기반 영업 가이드 ─────────────── */
export interface BranchOffice {
  code: string;
  name: string;
  region?: string;
  sigungu?: string;
  regionHq?: string;
  orgCode?: string;
}

/** 업적평가 평가항목 — 배점표(데이터셋) × 득점 현황 */
export interface KpiItem {
  code: string;
  label: string;
  score: number | null;
  max: number | null;
  prevMax?: number | null;
  changeType?: string | null;
  changeSummary?: string | null;
  docPage?: string | null;
  actual?: number;
  target?: number | null;
  actualUnit?: string;
  note?: string;
  details?: KpiItem[];
}

export interface KpiGroup {
  code: string;
  label: string;
  kind: "kpi" | "adjustment";
  score: number;
  max: number | null;
  prevMax?: number | null;
  items: KpiItem[];
}

/** 기준 변경 알림 — 의견 탭으로 이어진다 */
export interface BranchKpiAlert {
  id: string;
  /** 배점표 항목 코드 — 득점표의 해당 항목에서 이 알림 탭으로 연결 */
  itemCode: string;
  path: string;
  changeType: string;
  title: string;
  /** 인라인 마커 포함 */
  summary: string;
  tabKey: string;
  insightId: string;
  severity: Severity;
  uplift: Figure;
}

export interface BranchDashboard {
  available: boolean;
  /** 이 화면을 만드는 워크플로우 (서버 제공) */
  workflow?: string | null;
  /** 로그인 사용자의 영업점 (영업점 소속이 아니면 null) */
  viewer?: { code: string; name: string; orgCode: string } | null;
  office: BranchOffice;
  asOf: string;
  generatedAt: string;
  dataOrigin: DataOrigin;
  periodLabel: string;
  asOfLabel: string;
  scorecard: { total: Figure; max: Figure; adjustments: Figure; uplift: Figure; totalAfter: Figure; groups: KpiGroup[] };
  alerts: BranchKpiAlert[];
  figures: Record<string, Figure>;
  segments: DomainCardInfo[];
  loan: { total: Figure; corp: Figure; corpCount: Figure; retail: Figure; retailCount: Figure; avgGrade: Figure; bankAvgGrade: Figure; avgGradeGap: Figure };
  evidence: Evidence[];
}

export interface BranchTabs {
  office?: BranchOffice;
  current: AnalysisTab[];
  previous: AnalysisTab[];
}

/** 볼 수 있는 계산 대상 지점 (B.47 · 다지점) — 둘 이상이면 영업점 화면에 지점 선택 상자 */
export interface BranchOfficeList {
  offices: { code: string; name: string; available: boolean; primary: boolean }[];
  /** 지점 인자가 없을 때 보이는 지점(사용자 소속 영업점 → 기본 지점) */
  default: string | null;
}

/* ── 부도율 추이 (신용리스크관리부 1화면) ───────────────────── */
export interface DefaultRateSeries {
  /** 세그먼트 또는 풀 코드 */
  key: string;
  label: string;
  /** 월별 부도율 (단위 %) */
  points: SeriesPoint[];
  latest: Figure;
  /** 연초 대비 증감 (pp) */
  deltaPP: Figure;
  severity: Severity;
  note?: string;
}

export interface DefaultRateTrend {
  asOf: string;
  generatedAt: string;
  /** 기업 규모별 — 대기업 / 외감 / 비외감 / 소기업 / 기업형소호 */
  corpSegments: DefaultRateSeries[];
  /** 개인 풀별 — 풀 정의는 확정 전 임시 구분 */
  retailPools: DefaultRateSeries[];
  corpNote?: string;
  retailNote?: string;
  evidence: Evidence[];
}

/* ── 수행방안·사업·전파 ───────────────────────────────────── */
/** proposed = Agent 제안안 / in_progress = 진행사업 등록 완료 */
export type PlanStatus = "proposed" | "in_progress";

export interface ActionPlan {
  id: string;
  title: string;
  body: string;
  ownerOrg: string;
  monitoringMetrics: string[];
  reviewCycle: string;
  relatedGoalTitle?: string;
  /** 연결 경영목표 ID — 전파 경로 트리 매칭에 사용 */
  relatedGoalId?: string;
  alignment: { verdict: AlignmentVerdict; matched: string[]; conflicts: string[] };
  evidence: Evidence[];
  status: PlanStatus;
  /** 영업점 Agent 가 참고 가능한 상태인지 (토글) */
  branchShared: boolean;
  /** Agent 제안 / 담당자 직접 등록 */
  origin: "agent" | "user";
  sourceInsightId?: string;
  /** 연결된 분석 탭 — 보고서 열람에 사용 */
  linkedTabKey?: string;
  linkedAnalysisLabel?: string;
  /** 직접 등록 시 담당자가 입력한 근거 메모 */
  evidenceNote?: string;
  registeredAt?: string;
  updatedAt?: string;
  guideRuleId: string;
  /** 규칙 GUIDE_CATALOG 로 고른 가이드(2.5.3) — 조건 지표 · 비교 · 기준 */
  guide?: {
    ruleId: string;
    title?: string;
    text?: string;
    basis: { metric: string; label?: string; value?: number; op?: string; threshold?: number; met?: boolean }[];
  };
}

export interface CascadeNode {
  id: string;
  kind: "goal" | "plan" | "branch_target";
  label: string;
  detail?: string;
  org?: string;
  children?: CascadeNode[];
}

export interface BranchTarget {
  id: string;
  orgCode: string;
  orgName: string;
  title: string;
  guideline: string;
  metricLabel: string;
  target: Figure;
  actual?: Figure;
  progress?: number;
  periodLabel: string;
  sourcePlanTitle: string;
  sourceGoalTitle: string;
}

/* ── 지식 ─────────────────────────────────────────────────── */
export interface Term {
  termCode: string;
  prefLabel: string;
  altLabels: string[];
  definition: string;
  formula?: string;
  judgement?: string;
  example?: string;
  src: { title: string; page: number; fileName: string };
  relatedTerms: string[];
}

export interface DocumentMeta {
  docId: string;
  title: string;
  dbClass: EvidenceDoc["dbClass"];
  dbClassLabel: string;
  docType: string;
  issuer: string;
  effectiveDate: string;
  registeredAt: string;
  domainLabels: string[];
  tags: string[];
  accessClass: "public" | "internal" | "dept_only";
  pageCount: number;
  isOfficial: boolean;
  ingestStatus: "ready" | "parsing" | "pending";
  usedByCount: number;
  fileName: string;
}

/** 원본 문서 뷰어 응답 (F.12 · DB-07, `GET /documents/view`) */
export interface DocumentViewPage {
  page: number;
  text: string;
  section?: string | null;
  /** 원문 기준 [start, end) */
  highlights: { start: number; end: number }[];
}
export interface DocumentView {
  docId: string;
  origin: "bank" | "ext";
  version: number;
  title: string;
  issuer?: string | null;
  effectiveDate?: string | null;
  dbClass: string;
  fileName?: string | null;
  pageCount: number;
  hasFile: boolean;
  /** file: 원본 PDF 면별 추출 · excerpt: 근거 인용이 실린 면만(원본 미등록) · chunks: 업로드 텍스트 */
  source: "file" | "excerpt" | "chunks";
  requestedPage?: number | null;
  focusPage?: number | null;
  query?: string | null;
  matched: boolean;
  pages: DocumentViewPage[];
}
export interface DatasetMeta {
  fileName: string;
  reportCode: string;
  asOfYm: string;
  rows: number;
  unit: string;
  quality: "passed" | "warning" | "failed";
  qualityNote: string;
  registeredAt: string;
  usedBy: string[];
}

/* ── 대시보드 ─────────────────────────────────────────────── */
export interface HqDashboard {
  asOf: string;
  generatedAt: string;
  batchLabel: string;
  degradedSources: string[];
  domains: DomainCardInfo[];
  attentions: Insight[];
  requests: ReportRequest[];
  loanMini: { label: string; figure: Figure; caption: string; href: string }[];
}

export interface RiskDashboard {
  asOf: string;
  generatedAt: string;
  batchLabel: string;
  degradedSources: string[];
  corpModels: ModelSummaryRow[];
  retailModels: ModelSummaryRow[];
  appliedGoals: { title: string; value: string; source: string; updatedAt: string }[];
  opinions: Insight[];
  dataQuality: { label: string; status: "passed" | "warning" | "failed"; note: string }[];
}

/* ── 변화 감지 에이전트 (B.30) ─────────────────────────────── */
export interface ChangeItem {
  id: string;
  at: string;
  workflow: string;
  workflowName: string;
  runId?: string;
  kind: "metric" | "data";
  code: string;
  label: string;
  unit: Figure["unit"];
  decimals?: number | null;
  before: number;
  after: number;
  delta: number;
  deltaPct: number | null;
  /** major = 주요(기준의 N배 이상) · minor = 일반 */
  level: "major" | "minor";
  direction: "up" | "down" | "same";
  files?: string[];
  scope?: { office?: string };
}

export interface ChangeFeed {
  items: ChangeItem[];
  updatedAt: string | null;
}
