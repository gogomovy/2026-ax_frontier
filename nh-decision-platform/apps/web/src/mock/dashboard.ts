import type { DomainCardInfo, HqDashboard, Insight, ReportRequest } from "@/lib/types";
import { AS_OF, BATCH_LABEL, GENERATED_AT, PASSED_VERIFICATIONS, evidence, fig, figMap, withAlignment } from "./helpers";
import { DOC } from "./knowledge";
import { CORPORATE, FINANCE_FIGURES, HOUSEHOLD, REVENUE_FIGURES } from "./finance";
import { INCLUSIVE_OPINION } from "./risk";

/* ═══════════════════════════════════════════════════════════════
 * 사업부문 Card (DASH-02) — 여신만 active, 나머지는 준비 중
 * ═══════════════════════════════════════════════════════════════ */
export const DOMAINS: DomainCardInfo[] = [
  {
    domainCode: "loan",
    name: "여신",
    status: "active",
    summary: "기업·가계여신 및 여신 종합수익",
    headline: fig("dom_loan_head", "여신 잔액(기업+가계)", 214.58, "KRW_TN", { decimals: 2 }),
    sub: [
      { label: "여신 이자마진 수익", figure: REVENUE_FIGURES.nim_2026 },
      { label: "전체 수익 중 비중", figure: REVENUE_FIGURES.nim_share_2026 },
    ],
  },
  { domainCode: "deposit", name: "수신", status: "placeholder", note: "2차 범위" },
  { domainCode: "pension", name: "퇴직연금", status: "placeholder", note: "2차 범위" },
  { domainCode: "wm", name: "자산관리", status: "placeholder", note: "2차 범위" },
  { domainCode: "trust", name: "신탁", status: "placeholder", note: "2차 범위" },
  { domainCode: "fx", name: "외환", status: "placeholder", note: "2차 범위" },
  { domainCode: "card", name: "카드", status: "placeholder", note: "2차 범위" },
];

export const DOMAIN_MAP: Record<string, DomainCardInfo> = Object.fromEntries(
  DOMAINS.map((d) => [d.domainCode, d]),
);

/* ═══════════════════════════════════════════════════════════════
 * AI 주요 Attention (DASH-03) — 랭킹 순
 * ═══════════════════════════════════════════════════════════════ */
export const ATTENTIONS: Insight[] = [
  {
    id: "att-corp-gap",
    kind: "attention",
    persona: "P1",
    domainCode: "loan",
    subDomain: "corporate",
    title: "기업여신 증가율이 현재 경영목표를 하회하고 있습니다",
    statement:
      "기업여신 증가율은 [[fig:corp_growth]]로 현재 경영목표 [[fig:corp_goal]]을 [[fig:corp_gap]] 하회하고 있습니다. 기업여신 구성비도 2024년 8월 대비 [[fig:corp_share_delta]] 낮아져, 정부 정책과 내부 의사결정에서 확인되는 기업여신 확대 기조와 다른 방향으로 운영되고 있는 점이 주요 변화로 확인됩니다.",
    severity: "caution",
    asOf: AS_OF,
    dataOrigin: "simulated",
    figures: figMap(
      FINANCE_FIGURES.corp_growth,
      FINANCE_FIGURES.corp_goal,
      FINANCE_FIGURES.corp_gap,
      FINANCE_FIGURES.corp_share_delta,
    ),
    evidence: [
      evidence("ev-att-corp-data", "bank_data", "기업자금대출금 증가율 및 구성비(3개년)", {
        sourceKind: "calc_run",
        tableRef: "calc.calc_run(GROWTH_RATE, SHARE)",
        snippet: "증가율 4.04% · 목표 7.0% · 이탈 −2.96%p",
        figureId: "corp_gap",
      }),
      evidence("ev-att-corp-policy", "external_policy", "생산적 금융 공급 확대 및 기업금융 활성화 방안", {
        doc: DOC.corpLoanPolicy,
        relevance: 0.88,
      }),
      evidence("ev-att-corp-mgmt", "internal_direction", "2026년 하반기 경영전략회의 결과", {
        doc: DOC.stratMeeting,
        relevance: 0.91,
      }),
    ],
    verifications: withAlignment(PASSED_VERIFICATIONS),
    rankScore: 92.4,
    rankBasis:
      "목표 이탈 폭(2.96%p → 34.2점) + 목표 중요도(상 → 25.0점) + 변화 속도(3개년 연속 → 18.4점) + 정책 정합성 영향(상 → 14.8점)",
    relatedGoalId: "goal-corp-growth",
  },
  {
    id: "att-hh-limit",
    kind: "attention",
    persona: "P1",
    domainCode: "loan",
    subDomain: "household",
    title: "가계여신 잔액이 관리목표 상단에 근접했습니다",
    statement:
      "가계여신 잔액은 [[fig:hh_bal]]으로 관리 한도 100.00조원의 99.2%를 소진했습니다. 증가율도 [[fig:hh_growth]]로 관리목표 [[fig:hh_goal]] 이하를 [[fig:hh_gap]] 초과한 수준입니다. 가계 부문 신용RWA 소진율은 92.3%로 자본 여력 관점의 여유도 축소되고 있습니다.",
    severity: "watch",
    asOf: AS_OF,
    dataOrigin: "simulated",
    figures: figMap(
      FINANCE_FIGURES.hh_bal,
      FINANCE_FIGURES.hh_growth,
      FINANCE_FIGURES.hh_goal,
      FINANCE_FIGURES.hh_gap,
    ),
    evidence: [
      evidence("ev-att-hh-data", "bank_data", "가계자금대출금 잔액·증가율·RWA 소진율", {
        sourceKind: "calc_run",
        tableRef: "calc.calc_run(GROWTH_RATE, CAP_HEADROOM)",
        snippet: "잔액 99.24조원 / 한도 100.00조원 · 증가율 6.50%",
        figureId: "hh_bal",
      }),
      evidence("ev-att-hh-policy", "external_policy", "가계부채 관리방안(2026년)", {
        doc: DOC.householdPolicy,
        relevance: 0.9,
      }),
      evidence("ev-att-hh-mgmt", "internal_direction", "2026년 사업계획(여신 부문)", {
        doc: DOC.bizPlan,
        relevance: 0.85,
      }),
    ],
    verifications: withAlignment(PASSED_VERIFICATIONS),
    rankScore: 86.1,
    rankBasis: "한도 소진율(99.2% → 32.6점) + 목표 초과(2.50%p → 26.5점) + 목표 중요도(상 → 25.0점) + 자본 영향(2.0점)",
    relatedGoalId: "goal-hh-balance",
  },
  {
    id: "att-nim-share",
    kind: "attention",
    persona: "P1",
    domainCode: "loan",
    subDomain: "revenue",
    title: "여신 이자마진 비중이 3개년 연속 축소되고 있습니다",
    statement:
      "전체 수익 중 여신(일반)부문 이자마진 비중은 [[fig:nim_share_2026]]로 전년 동기 [[fig:nim_share_2025]] 대비 [[fig:nim_share_delta]] 낮아졌습니다. 전체 수익은 [[fig:total_rev_growth]] 증가한 반면 여신 이자마진 수익은 [[fig:nim_growth]] 증가하여 증가 속도 차이가 유지되고 있습니다.",
    severity: "watch",
    asOf: AS_OF,
    dataOrigin: "simulated",
    figures: REVENUE_FIGURES,
    evidence: [
      evidence("ev-att-nim-data", "bank_data", "2633_상품부문별손익계산서 3개년 8월 누계", {
        sourceKind: "calc_run",
        tableRef: "calc.calc_run(SHARE, GROWTH_RATE)",
        snippet: "비중 46.53% → 45.90% → 45.43%",
        figureId: "nim_share_2026",
      }),
      evidence("ev-att-nim-plan", "internal_direction", "2026년 사업계획(여신 부문) — 수익 목표", {
        doc: DOC.bizPlan,
        relevance: 0.79,
      }),
    ],
    verifications: withAlignment(PASSED_VERIFICATIONS),
    rankScore: 74.8,
    rankBasis: "변화 지속성(3개년 → 28.4점) + 수익 목표 연관성(상 → 24.0점) + 변화 폭(0.47%p → 12.4점) + 기타(10.0점)",
    relatedGoalId: "goal-annual-revenue",
  },
  {
    ...INCLUSIVE_OPINION,
    id: "att-inclusive-provision",
    kind: "attention",
    persona: "P1",
    title: "포용금융 확대에 따라 충당금 비중이 상승하고 있습니다",
    rankScore: 78.3,
    rankBasis: "사업부서 보고 연계(상 → 30.0점) + 비중 증가 폭(1.18%p → 26.3점) + 신규 목표 제안 연관성(22.0점)",
    relatedGoalId: undefined,
  },
];

/* ═══════════════════════════════════════════════════════════════
 * 확인·보고 요청 (DASH-04) — AI Attention 과 데이터 경로가 다르다
 * ═══════════════════════════════════════════════════════════════ */
export const REPORT_REQUESTS: ReportRequest[] = [
  {
    id: "req-1",
    fromOrg: "신용리스크관리부",
    toOrg: "종합기획부",
    reqType: "direction_check",
    reqTypeLabel: "경영방향 확인 요청",
    title: "포용금융 확대에 따른 충당금 비중 상승 — 목표 설정 방향 확인 요청",
    body:
      "포용금융 대상 상품 충당금 비중이 2026년 1월 7.97%에서 8월 9.16%로 상승했습니다. 포용금융 공급 확대 목표를 신설하는 경우 신용리스크 중점관리사항을 병행 반영할 필요가 있어 방향 확인을 요청합니다.",
    dueDate: "2026-09-30",
    createdAt: "2026-09-15",
    status: "open",
  },
  {
    id: "req-2",
    fromOrg: "여신관리부",
    toOrg: "종합기획부",
    reqType: "perf_report",
    reqTypeLabel: "전기 사업 성과보고",
    title: "상반기 기업여신 확대 사업 성과보고",
    body:
      "상반기 기업여신 확대 사업 취급 실적은 목표 대비 71.4% 수준입니다. 정책자금 연계 상품 취급은 계획을 상회했으나 우량 중소기업 신규 발굴이 지연되었습니다. 하반기 목표 재조정 검토를 요청합니다.",
    dueDate: "2026-09-25",
    createdAt: "2026-09-10",
    status: "reviewing",
    relatedGoalId: "goal-corp-growth",
  },
  {
    id: "req-3",
    fromOrg: "수도권1지역본부",
    toOrg: "종합기획부",
    reqType: "direction_check",
    reqTypeLabel: "취급 기준 확인 요청",
    title: "가계여신 관리목표 상단 근접에 따른 취급 기준 확인 요청",
    body:
      "가계여신 잔액 관리 한도 소진율이 99.2%에 도달하여 4분기 신규 취급 가능 여부와 예외 승인 기준 확인을 요청합니다.",
    dueDate: "2026-09-22",
    createdAt: "2026-09-12",
    status: "open",
    relatedGoalId: "goal-hh-balance",
  },
];

/* ═══════════════════════════════════════════════════════════════
 * 은행 Dashboard (DASH-01)
 * ═══════════════════════════════════════════════════════════════ */
export const HQ_DASHBOARD: HqDashboard = {
  asOf: AS_OF,
  generatedAt: GENERATED_AT,
  batchLabel: BATCH_LABEL,
  degradedSources: ["graph", "vector"],
  domains: DOMAINS,
  attentions: ATTENTIONS,
  requests: REPORT_REQUESTS,
  loanMini: [
    {
      label: "여신 종합수익",
      figure: REVENUE_FIGURES.nim_2026,
      caption: `전년 동기 대비 +${REVENUE_FIGURES.nim_growth.value}% · 전체 수익 중 ${REVENUE_FIGURES.nim_share_2026.value}%`,
      href: "/hq/dashboard/loan/revenue",
    },
    {
      label: "기업여신",
      figure: CORPORATE.balance,
      caption: `증가율 +${CORPORATE.growth.value}% · 목표 +7.0% 대비 ${CORPORATE.gap?.value}%p`,
      href: "/hq/dashboard/loan/corporate",
    },
    {
      label: "가계여신",
      figure: HOUSEHOLD.balance,
      caption: `증가율 +${HOUSEHOLD.growth.value}% · 관리목표 +4.0% 이하 대비 +${HOUSEHOLD.gap?.value}%p`,
      href: "/hq/dashboard/loan/household",
    },
  ],
};
