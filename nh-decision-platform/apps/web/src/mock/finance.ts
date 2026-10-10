import type {
  CapitalView,
  ComparisonRow,
  ComparisonView,
  Figure,
  Insight,
  LoanOverview,
  LoanSegmentDetail,
  ProfitabilityRow,
  SeriesPoint,
} from "@/lib/types";
import { AS_OF, GENERATED_AT, PASSED_VERIFICATIONS, evidence, fig, figMap, trace, withAlignment } from "./helpers";
import { DOC } from "./knowledge";

/* ═══════════════════════════════════════════════════════════════
 * 원천 값 (백만원) — (202408)/(202508)/(202608) 2633 · 2020 기준
 * ═══════════════════════════════════════════════════════════════ */
const RAW = {
  totalRevenue: { y2024: 4_371_940, y2025: 4_603_180, y2026: 4_812_360 },
  loanNim: { y2024: 2_034_120, y2025: 2_112_880, y2026: 2_186_540 },
  corpInterest: { y2024: 1_003_560, y2025: 1_048_900, y2026: 1_089_820 },
  hhInterest: { y2024: 812_300, y2025: 852_110, y2026: 909_960 },
  corpBalance: { y2024: 106_240_000, y2025: 110_860_000, y2026: 115_340_000 },
  hhBalance: { y2024: 88_120_000, y2025: 93_180_000, y2026: 99_240_000 },
};

const BN = 100; // 백만원 → 억원
const TN = 1_000_000; // 백만원 → 조원

const toBn = (v: number) => Math.round(v / BN);
const toTn = (v: number) => Number((v / TN).toFixed(2));

/* ── 계산 추적 헬퍼 ────────────────────────────────────────── */
const cellPL = (ym: string, cell: string) => `(${ym})2633_상품부문별손익계산서.xlsx!${cell}`;
const cellLoan = (ym: string, cell: string) => `(${ym})2020 과목별 월별 여신현황.xlsx!${cell}`;

const growthTrace = (
  calcId: string,
  label: string,
  prior: number,
  current: number,
  priorSrc: string,
  currentSrc: string,
) =>
  trace(
    calcId,
    "GROWTH_RATE",
    "(당기 − 전기) / |전기| × 100",
    [
      { key: "v0", label: `${label} (전년 동기)`, value: prior.toLocaleString("ko-KR"), unit: "백만원", source: priorSrc },
      { key: "v1", label: `${label} (당기)`, value: current.toLocaleString("ko-KR"), unit: "백만원", source: currentSrc },
    ],
    "8월 누계 기준. 표시 자릿수 2자리, 내부 보존 6자리.",
  );

const shareTrace = (calcId: string, numerator: number, denominator: number, ym: string) =>
  trace(
    calcId,
    "SHARE",
    "분자 / 분모 × 100",
    [
      {
        key: "numerator",
        label: "여신(일반)부문 이자마진 수익",
        value: numerator.toLocaleString("ko-KR"),
        unit: "백만원",
        source: cellPL(ym, "Sheet1!D118"),
      },
      {
        key: "denominator",
        label: "전체 수익",
        value: denominator.toLocaleString("ko-KR"),
        unit: "백만원",
        source: cellPL(ym, "Sheet1!D12"),
      },
    ],
  );

/* ═══════════════════════════════════════════════════════════════
 * 여신 종합수익
 * ═══════════════════════════════════════════════════════════════ */
const totalRevGrowth = ((RAW.totalRevenue.y2026 - RAW.totalRevenue.y2025) / RAW.totalRevenue.y2025) * 100; // 4.5443
const nimGrowth = ((RAW.loanNim.y2026 - RAW.loanNim.y2025) / RAW.loanNim.y2025) * 100; // 3.4863
const nimShare2026 = (RAW.loanNim.y2026 / RAW.totalRevenue.y2026) * 100; // 45.4348
const nimShare2025 = (RAW.loanNim.y2025 / RAW.totalRevenue.y2025) * 100; // 45.8995
const nimShare2024 = (RAW.loanNim.y2024 / RAW.totalRevenue.y2024) * 100; // 46.5261

export const REVENUE_FIGURES: Record<string, Figure> = figMap(
  fig("total_rev_2026", "전체 수익(2026.08 누계)", toBn(RAW.totalRevenue.y2026), "KRW_BN", {
    sourceRef: cellPL("202608", "Sheet1!D12"),
  }),
  fig("total_rev_2025", "전체 수익(2025.08 누계)", toBn(RAW.totalRevenue.y2025), "KRW_BN", {
    sourceRef: cellPL("202508", "Sheet1!D12"),
  }),
  fig("total_rev_growth", "전체 수익 증가율", Number(totalRevGrowth.toFixed(2)), "PCT", {
    decimals: 2,
    calc: growthTrace(
      "calc-rev-growth",
      "전체 수익",
      RAW.totalRevenue.y2025,
      RAW.totalRevenue.y2026,
      cellPL("202508", "Sheet1!D12"),
      cellPL("202608", "Sheet1!D12"),
    ),
  }),
  fig("nim_2026", "여신(일반)부문 이자마진 수익(2026.08 누계)", toBn(RAW.loanNim.y2026), "KRW_BN", {
    sourceRef: cellPL("202608", "Sheet1!D118"),
  }),
  fig("nim_2025", "여신(일반)부문 이자마진 수익(2025.08 누계)", toBn(RAW.loanNim.y2025), "KRW_BN", {
    sourceRef: cellPL("202508", "Sheet1!D118"),
  }),
  fig("nim_growth", "여신 이자마진 수익 증가율", Number(nimGrowth.toFixed(2)), "PCT", {
    decimals: 2,
    calc: growthTrace(
      "calc-nim-growth",
      "여신(일반)부문 이자마진 수익",
      RAW.loanNim.y2025,
      RAW.loanNim.y2026,
      cellPL("202508", "Sheet1!D118"),
      cellPL("202608", "Sheet1!D118"),
    ),
  }),
  fig("nim_share_2026", "전체 수익 중 여신 이자마진 비중", Number(nimShare2026.toFixed(2)), "PCT", {
    decimals: 2,
    calc: shareTrace("calc-nim-share-2026", RAW.loanNim.y2026, RAW.totalRevenue.y2026, "202608"),
  }),
  fig("nim_share_2025", "전년 동기 비중", Number(nimShare2025.toFixed(2)), "PCT", {
    decimals: 2,
    calc: shareTrace("calc-nim-share-2025", RAW.loanNim.y2025, RAW.totalRevenue.y2025, "202508"),
  }),
  fig("nim_share_delta", "비중 증감", Number((nimShare2026 - nimShare2025).toFixed(2)), "PP", {
    decimals: 2,
    calc: trace("calc-nim-share-delta", "SHARE_DELTA_PP", "당기 비중 − 전기 비중", [
      { key: "share1", label: "2026.08 비중", value: nimShare2026.toFixed(4), unit: "%", source: "calc-nim-share-2026" },
      { key: "share0", label: "2025.08 비중", value: nimShare2025.toFixed(4), unit: "%", source: "calc-nim-share-2025" },
    ]),
  }),
);

const comparisonRow = (
  key: string,
  label: string,
  values: { y2024: number; y2025: number; y2026: number },
  unit: Figure["unit"],
  convert: (v: number) => number,
  cell: (ym: string) => string,
): ComparisonRow => {
  const diffRaw = values.y2026 - values.y2025;
  const rate = (diffRaw / values.y2025) * 100;
  return {
    label,
    current: fig(`${key}_cur`, `${label} (2026.08)`, convert(values.y2026), unit, { sourceRef: cell("202608") }),
    prior: fig(`${key}_prior`, `${label} (2025.08)`, convert(values.y2025), unit, { sourceRef: cell("202508") }),
    prior2: fig(`${key}_prior2`, `${label} (2024.08)`, convert(values.y2024), unit, { sourceRef: cell("202408") }),
    diff: fig(`${key}_diff`, `${label} 증감액`, convert(diffRaw), unit, {
      calc: trace(`calc-${key}-diff`, "DIFF", "당기 − 전기", [
        { key: "v1", label: "당기", value: values.y2026.toLocaleString("ko-KR"), unit: "백만원", source: cell("202608") },
        { key: "v0", label: "전기", value: values.y2025.toLocaleString("ko-KR"), unit: "백만원", source: cell("202508") },
      ]),
    }),
    diffRate: fig(`${key}_rate`, `${label} 증감률`, Number(rate.toFixed(2)), "PCT", {
      decimals: 2,
      calc: growthTrace(`calc-${key}-rate`, label, values.y2025, values.y2026, cell("202508"), cell("202608")),
    }),
  };
};

const revenueRows: ComparisonRow[] = [
  comparisonRow("total_rev", "전체 수익", RAW.totalRevenue, "KRW_BN", toBn, (ym) => cellPL(ym, "Sheet1!D12")),
  comparisonRow("nim", "여신(일반)부문 이자마진 수익", RAW.loanNim, "KRW_BN", toBn, (ym) => cellPL(ym, "Sheet1!D118")),
  comparisonRow("corp_int", "기업자금대출금이자", RAW.corpInterest, "KRW_BN", toBn, (ym) => cellPL(ym, "Sheet1!D141")),
  comparisonRow("hh_int", "가계자금대출금이자", RAW.hhInterest, "KRW_BN", toBn, (ym) => cellPL(ym, "Sheet1!D147")),
];

const nimShareTrend: SeriesPoint[] = [
  { label: "2024.08", value: Number(nimShare2024.toFixed(2)) },
  { label: "2025.08", value: Number(nimShare2025.toFixed(2)) },
  { label: "2026.08", value: Number(nimShare2026.toFixed(2)) },
];

/* ═══════════════════════════════════════════════════════════════
 * 기업여신 / 가계여신
 * ═══════════════════════════════════════════════════════════════ */
const corpGrowth = ((RAW.corpBalance.y2026 - RAW.corpBalance.y2025) / RAW.corpBalance.y2025) * 100; // 4.0411
const hhGrowth = ((RAW.hhBalance.y2026 - RAW.hhBalance.y2025) / RAW.hhBalance.y2025) * 100; // 6.5036
const total2026 = RAW.corpBalance.y2026 + RAW.hhBalance.y2026;
const total2025 = RAW.corpBalance.y2025 + RAW.hhBalance.y2025;
const total2024 = RAW.corpBalance.y2024 + RAW.hhBalance.y2024;
const corpShare = [
  (RAW.corpBalance.y2024 / total2024) * 100,
  (RAW.corpBalance.y2025 / total2025) * 100,
  (RAW.corpBalance.y2026 / total2026) * 100,
];
const hhShare = [
  (RAW.hhBalance.y2024 / total2024) * 100,
  (RAW.hhBalance.y2025 / total2025) * 100,
  (RAW.hhBalance.y2026 / total2026) * 100,
];

const CORP_MONTHLY = [111_240_000, 111_860_000, 112_540_000, 113_080_000, 113_620_000, 114_260_000, 114_820_000, 115_340_000];
const HH_MONTHLY = [93_880_000, 94_520_000, 95_240_000, 96_180_000, 97_020_000, 97_860_000, 98_540_000, 99_240_000];
const MONTH_LABELS = ["1월", "2월", "3월", "4월", "5월", "6월", "7월", "8월"];

const monthlySeries = (values: number[]): SeriesPoint[] =>
  values.map((v, i) => ({ label: MONTH_LABELS[i], value: toTn(v) }));

export const CORPORATE: LoanSegmentDetail = {
  key: "corporate",
  name: "기업여신",
  balance: fig("corp_bal", "기업자금대출금 잔액(2026.08말)", toTn(RAW.corpBalance.y2026), "KRW_TN", {
    decimals: 2,
    sourceRef: cellLoan("202608", "Sheet1!J3"),
  }),
  growth: fig("corp_growth", "기업여신 증가율(전년 동기 대비)", Number(corpGrowth.toFixed(2)), "PCT", {
    decimals: 2,
    calc: growthTrace(
      "calc-corp-growth",
      "기업자금대출금",
      RAW.corpBalance.y2025,
      RAW.corpBalance.y2026,
      cellLoan("202508", "Sheet1!J3"),
      cellLoan("202608", "Sheet1!J3"),
    ),
  }),
  share: fig("corp_share", "기업여신 구성비", Number(corpShare[2].toFixed(2)), "PCT", {
    decimals: 2,
    calc: trace("calc-corp-share", "SHARE", "기업자금대출금 / (기업+가계) × 100", [
      { key: "numerator", label: "기업자금대출금", value: RAW.corpBalance.y2026.toLocaleString("ko-KR"), unit: "백만원", source: cellLoan("202608", "Sheet1!J3") },
      { key: "denominator", label: "기업+가계 합계", value: total2026.toLocaleString("ko-KR"), unit: "백만원", source: "fact.loan_balance_monthly 집계" },
    ]),
  }),
  interestRevenue: fig("corp_int_rev", "기업자금대출금이자(2026.08 누계)", toBn(RAW.corpInterest.y2026), "KRW_BN", {
    sourceRef: cellPL("202608", "Sheet1!D141"),
  }),
  monthly: monthlySeries(CORP_MONTHLY),
  yearly: [
    { label: "2024.08", value: toTn(RAW.corpBalance.y2024) },
    { label: "2025.08", value: toTn(RAW.corpBalance.y2025) },
    { label: "2026.08", value: toTn(RAW.corpBalance.y2026) },
  ],
  goalId: "goal-corp-growth",
  goalLabel: "기업여신 전년 대비 +7.0% 이상 확대",
  goalValue: fig("corp_goal", "현재 경영목표", 7.0, "PCT", { decimals: 1, dataOrigin: "actual" }),
  gap: fig("corp_gap", "목표 대비 이탈", Number((corpGrowth - 7.0).toFixed(2)), "PP", {
    decimals: 2,
    calc: trace("calc-corp-gap", "DIFF", "실적 증가율 − 목표 증가율", [
      { key: "v1", label: "실적 증가율", value: corpGrowth.toFixed(4), unit: "%", source: "calc-corp-growth" },
      { key: "v0", label: "목표 증가율", value: "7.0000", unit: "%", source: "goal.goal_version(goal-corp-growth, v3)" },
    ]),
  }),
  gapVerdict: "below",
  narrative:
    "기업여신은 2026년 8월말 [[fig:corp_bal]]으로 전년 동기 대비 [[fig:corp_growth]] 증가하며 증가세를 유지하고 있습니다. 다만 현재 설정된 성장목표 [[fig:corp_goal]]을 [[fig:corp_gap]] 하회하고 있습니다. 같은 기간 기업자금대출금이자는 [[fig:corp_int_rev]]으로, 규모 기준으로는 가계 대비 우위를 유지하고 있습니다.",
  narrativeFigures: {},
  evidence: [
    evidence("ev-corp-data", "bank_data", "2026.08말 기업자금대출금 잔액 및 3개년 추이", {
      sourceKind: "metric_value",
      tableRef: "fact.loan_balance_monthly (2020 과목별 월별 여신현황)",
      snippet: "기업자금대출금 115.34조원 · 전년 동기 110.86조원 · 증가율 4.04%",
      figureId: "corp_bal",
    }),
    evidence("ev-corp-policy", "external_policy", "생산적 금융 공급 확대 및 기업금융 활성화 방안", {
      doc: DOC.corpLoanPolicy,
      relevance: 0.86,
      snippet: "기업여신 공급 확대 기조를 유지하고 생산적 부문에 대한 자금공급을 확대한다는 정책 방향이 제시됨.",
    }),
    evidence("ev-corp-mgmt", "internal_direction", "2026년 하반기 경영전략회의 결과 — 여신 부문 운영방향", {
      doc: DOC.stratMeeting,
      relevance: 0.91,
      snippet: "기업여신은 확대, 가계여신은 증가율 관리 기조를 하반기에도 유지하기로 결정.",
    }),
  ],
};

export const HOUSEHOLD: LoanSegmentDetail = {
  key: "household",
  name: "가계여신",
  balance: fig("hh_bal", "가계자금대출금 잔액(2026.08말)", toTn(RAW.hhBalance.y2026), "KRW_TN", {
    decimals: 2,
    sourceRef: cellLoan("202608", "Sheet1!J9"),
  }),
  growth: fig("hh_growth", "가계여신 증가율(전년 동기 대비)", Number(hhGrowth.toFixed(2)), "PCT", {
    decimals: 2,
    calc: growthTrace(
      "calc-hh-growth",
      "가계자금대출금",
      RAW.hhBalance.y2025,
      RAW.hhBalance.y2026,
      cellLoan("202508", "Sheet1!J9"),
      cellLoan("202608", "Sheet1!J9"),
    ),
  }),
  share: fig("hh_share", "가계여신 구성비", Number(hhShare[2].toFixed(2)), "PCT", {
    decimals: 2,
    calc: trace("calc-hh-share", "SHARE", "가계자금대출금 / (기업+가계) × 100", [
      { key: "numerator", label: "가계자금대출금", value: RAW.hhBalance.y2026.toLocaleString("ko-KR"), unit: "백만원", source: cellLoan("202608", "Sheet1!J9") },
      { key: "denominator", label: "기업+가계 합계", value: total2026.toLocaleString("ko-KR"), unit: "백만원", source: "fact.loan_balance_monthly 집계" },
    ]),
  }),
  interestRevenue: fig("hh_int_rev", "가계자금대출금이자(2026.08 누계)", toBn(RAW.hhInterest.y2026), "KRW_BN", {
    sourceRef: cellPL("202608", "Sheet1!D147"),
  }),
  monthly: monthlySeries(HH_MONTHLY),
  yearly: [
    { label: "2024.08", value: toTn(RAW.hhBalance.y2024) },
    { label: "2025.08", value: toTn(RAW.hhBalance.y2025) },
    { label: "2026.08", value: toTn(RAW.hhBalance.y2026) },
  ],
  goalId: "goal-hh-control",
  goalLabel: "가계여신 전년 대비 +4.0% 이하 관리",
  goalValue: fig("hh_goal", "현재 관리목표", 4.0, "PCT", { decimals: 1, dataOrigin: "actual" }),
  gap: fig("hh_gap", "관리목표 대비 초과", Number((hhGrowth - 4.0).toFixed(2)), "PP", {
    decimals: 2,
    calc: trace("calc-hh-gap", "DIFF", "실적 증가율 − 관리목표 상한", [
      { key: "v1", label: "실적 증가율", value: hhGrowth.toFixed(4), unit: "%", source: "calc-hh-growth" },
      { key: "v0", label: "관리목표 상한", value: "4.0000", unit: "%", source: "goal.goal_version(goal-hh-control, v2)" },
    ]),
  }),
  gapVerdict: "breach",
  narrative:
    "가계여신은 2026년 8월말 [[fig:hh_bal]]으로 전년 동기 대비 [[fig:hh_growth]] 증가했습니다. 현재 관리목표 [[fig:hh_goal]] 이하를 [[fig:hh_gap]] 초과한 수준이며, 잔액 관리목표 100.00조원 대비 소진율은 99.2%입니다. 가계자금대출금이자는 [[fig:hh_int_rev]]으로 증가율 측면에서는 기업 대비 빠른 흐름이 확인됩니다.",
  narrativeFigures: {},
  evidence: [
    evidence("ev-hh-data", "bank_data", "2026.08말 가계자금대출금 잔액 및 월별 추이", {
      sourceKind: "metric_value",
      tableRef: "fact.loan_balance_monthly (2020 과목별 월별 여신현황)",
      snippet: "가계자금대출금 99.24조원 · 전년 동기 93.18조원 · 증가율 6.50%",
      figureId: "hh_bal",
    }),
    evidence("ev-hh-policy", "external_policy", "가계부채 관리방안(2026년)", {
      doc: DOC.householdPolicy,
      relevance: 0.89,
      snippet: "가계대출 증가율을 명목 성장률 이내로 관리하는 기조를 제시.",
    }),
    evidence("ev-hh-mgmt", "internal_direction", "2026년 사업계획(여신 부문) — 가계여신 관리목표", {
      doc: DOC.bizPlan,
      relevance: 0.84,
      snippet: "가계여신은 전년 대비 +4.0% 이하, 잔액 100조원 이하로 관리한다.",
    }),
  ],
};

/* ═══════════════════════════════════════════════════════════════
 * 여신 종합 (Overview)
 * ═══════════════════════════════════════════════════════════════ */
export const LOAN_OVERVIEW: LoanOverview = {
  asOf: AS_OF,
  generatedAt: GENERATED_AT,
  dataOrigin: "simulated",
  revenue: {
    rows: revenueRows,
    nimShare: REVENUE_FIGURES.nim_share_2026,
    nimShareTrend,
    narrative:
      "2026년 8월 누계 전체 수익은 [[fig:total_rev_2026]]으로 전년 동기 대비 [[fig:total_rev_growth]] 증가했습니다. 같은 기간 여신(일반)부문 이자마진 수익은 [[fig:nim_2026]]으로 [[fig:nim_growth]] 증가하여 전체 수익 증가율을 하회했습니다. 이에 따라 전체 수익 중 여신 이자마진 비중은 [[fig:nim_share_2026]]로 전년 동기 [[fig:nim_share_2025]] 대비 [[fig:nim_share_delta]] 낮아졌습니다. 3개년 연속 비중이 축소되는 흐름이 현재 데이터상 확인되는 주요 변화입니다.",
    narrativeFigures: REVENUE_FIGURES,
    evidence: [
      evidence("ev-rev-data", "bank_data", "2633_상품부문별손익계산서 3개년 8월 누계", {
        sourceKind: "metric_value",
        tableRef: "fact.pl_product_segment",
        snippet: "전체 수익 48,124억원 · 여신(일반)부문 이자마진 21,865억원 · 비중 45.43%",
        figureId: "nim_share_2026",
      }),
      evidence("ev-rev-plan", "internal_direction", "2026년 사업계획(여신 부문) — 수익 목표", {
        doc: DOC.bizPlan,
        relevance: 0.78,
        snippet: "여신(일반)부문 이자마진 수익 연간 3.30조원 이상 달성을 목표로 한다.",
      }),
    ],
  },
  corporate: CORPORATE,
  household: HOUSEHOLD,
};

/* ═══════════════════════════════════════════════════════════════
 * 기업·가계 비교 + 기조 괴리 탐지 (AST-08)
 * ═══════════════════════════════════════════════════════════════ */
const DIVERGENCE_FIGURES = figMap(
  CORPORATE.growth,
  HOUSEHOLD.growth,
  fig("corp_share_2026", "기업여신 구성비(2026.08)", Number(corpShare[2].toFixed(2)), "PCT", { decimals: 2 }),
  fig("corp_share_2024", "기업여신 구성비(2024.08)", Number(corpShare[0].toFixed(2)), "PCT", { decimals: 2 }),
  fig("corp_share_delta", "기업여신 구성비 증감(2024→2026)", Number((corpShare[2] - corpShare[0]).toFixed(2)), "PP", {
    decimals: 2,
    calc: trace("calc-corp-share-delta", "SHARE_DELTA_PP", "2026 구성비 − 2024 구성비", [
      { key: "share1", label: "2026.08 구성비", value: corpShare[2].toFixed(4), unit: "%", source: "calc-corp-share" },
      { key: "share0", label: "2024.08 구성비", value: corpShare[0].toFixed(4), unit: "%", source: "fact.loan_balance_monthly(202408)" },
    ]),
  }),
  fig("ros_corp", "기업여신 규모 대비 수익률", 0.945, "PCT", {
    decimals: 3,
    calc: trace("calc-ros-corp", "RETURN_ON_SCALE", "이자수익 / 잔액 × 100", [
      { key: "revenue", label: "기업자금대출금이자(8월 누계)", value: RAW.corpInterest.y2026.toLocaleString("ko-KR"), unit: "백만원", source: cellPL("202608", "Sheet1!D141") },
      { key: "balance", label: "기업자금대출금(8월말)", value: RAW.corpBalance.y2026.toLocaleString("ko-KR"), unit: "백만원", source: cellLoan("202608", "Sheet1!J3") },
    ]),
  }),
  fig("ros_hh", "가계여신 규모 대비 수익률", 0.917, "PCT", {
    decimals: 3,
    calc: trace("calc-ros-hh", "RETURN_ON_SCALE", "이자수익 / 잔액 × 100", [
      { key: "revenue", label: "가계자금대출금이자(8월 누계)", value: RAW.hhInterest.y2026.toLocaleString("ko-KR"), unit: "백만원", source: cellPL("202608", "Sheet1!D147") },
      { key: "balance", label: "가계자금대출금(8월말)", value: RAW.hhBalance.y2026.toLocaleString("ko-KR"), unit: "백만원", source: cellLoan("202608", "Sheet1!J9") },
    ]),
  }),
  fig("ros_gap", "수익률 격차(기업−가계)", 0.028, "PP", { decimals: 3 }),
);

export const DIVERGENCE_INSIGHT: Insight = {
  id: "ins-divergence",
  kind: "analysis_result",
  persona: "P1",
  domainCode: "loan",
  subDomain: "portfolio",
  title: "기조와 실제 운영의 괴리 — 가계 확대 · 기업 축소 방향",
  statement:
    "정부정책 DB와 경영 의사결정 DB에서 확인되는 현재 기조는 기업여신 확대 · 가계여신 증가율 관리입니다. 그러나 실제 운영은 기업여신 [[fig:corp_growth]], 가계여신 [[fig:hh_growth]]으로 가계가 더 빠르게 증가하고 있으며, 기업여신 구성비는 2024년 8월 [[fig:corp_share_2024]]에서 2026년 8월 [[fig:corp_share_2026]]로 [[fig:corp_share_delta]] 낮아졌습니다. 규모 대비 수익률은 기업 [[fig:ros_corp]] · 가계 [[fig:ros_hh]]로 기업이 [[fig:ros_gap]] 우위이므로, 수익성 관점에서도 현재 운영 방향과 기조 간 괴리가 확인됩니다.",
  severity: "caution",
  asOf: AS_OF,
  dataOrigin: "simulated",
  figures: DIVERGENCE_FIGURES,
  evidence: [
    evidence("ev-div-data", "bank_data", "기업·가계 잔액·구성비·수익률 3개년 비교", {
      sourceKind: "calc_run",
      tableRef: "calc.calc_run(RETURN_ON_SCALE, SHARE, GROWTH_RATE)",
      snippet: "기업 +4.04% / 가계 +6.50%, 기업 구성비 54.66% → 53.75%",
      figureId: "corp_share_delta",
    }),
    evidence("ev-div-policy-corp", "external_policy", "생산적 금융 공급 확대 방안 — 기업여신 확대", {
      doc: DOC.corpLoanPolicy,
      relevance: 0.88,
    }),
    evidence("ev-div-policy-hh", "external_policy", "가계부채 관리방안(2026년) — 증가율 관리", {
      doc: DOC.householdPolicy,
      relevance: 0.85,
    }),
    evidence("ev-div-mgmt", "internal_direction", "2026년 하반기 경영전략회의 결과 — 기업 확대 · 가계 관리", {
      doc: DOC.stratMeeting,
      relevance: 0.92,
    }),
  ],
  verifications: withAlignment(PASSED_VERIFICATIONS),
  rankScore: 88.6,
  rankBasis: "목표 이탈 폭 2.96%p × 목표 중요도(상) + 정책 정합성 영향(상)",
  relatedGoalId: "goal-corp-growth",
};

export const COMPARISON_VIEW: ComparisonView = {
  asOf: AS_OF,
  balanceSeries: [
    { name: "기업자금대출금", points: monthlySeries(CORP_MONTHLY) },
    { name: "가계자금대출금", points: monthlySeries(HH_MONTHLY) },
  ],
  shareSeries: [
    {
      name: "기업여신 구성비",
      points: ["2024.08", "2025.08", "2026.08"].map((label, i) => ({ label, value: Number(corpShare[i].toFixed(2)) })),
    },
    {
      name: "가계여신 구성비",
      points: ["2024.08", "2025.08", "2026.08"].map((label, i) => ({ label, value: Number(hhShare[i].toFixed(2)) })),
    },
  ],
  interestRows: [
    comparisonRow("cmp_corp_int", "기업자금대출금이자", RAW.corpInterest, "KRW_BN", toBn, (ym) => cellPL(ym, "Sheet1!D141")),
    comparisonRow("cmp_hh_int", "가계자금대출금이자", RAW.hhInterest, "KRW_BN", toBn, (ym) => cellPL(ym, "Sheet1!D147")),
  ],
  balanceRows: [
    comparisonRow("cmp_corp_bal", "기업자금대출금", RAW.corpBalance, "KRW_TN", toTn, (ym) => cellLoan(ym, "Sheet1!J3")),
    comparisonRow("cmp_hh_bal", "가계자금대출금", RAW.hhBalance, "KRW_TN", toTn, (ym) => cellLoan(ym, "Sheet1!J9")),
  ],
  divergence: DIVERGENCE_INSIGHT,
  proxyNote:
    "기업·가계자금대출금에 위험가중치를 적용한 RWA 데이터가 미확보되어 여신금액 현황을 대리지표로 사용했습니다. 자본 소진 관점의 해석에는 한계가 있습니다.",
};

/* ═══════════════════════════════════════════════════════════════
 * 자본·총자산 제약 (AST-01~04)
 * ═══════════════════════════════════════════════════════════════ */
export const CAPITAL_VIEW: CapitalView = {
  asOf: AS_OF,
  constraints: [
    {
      id: "cap-asset-growth",
      kind: "total_asset_growth_cap",
      label: "자회사별 총자산 최대 증가율(은행)",
      scope: "은행",
      value: fig("cap_asset_growth", "총자산 최대 증가율", 8.2, "PCT", { decimals: 1, dataOrigin: "actual" }),
      period: "2026.01.01 ~ 2026.12.31",
      issuer: "NH농협금융지주",
      doc: DOC.rwaLimit,
    },
    {
      id: "cap-rwa-net",
      kind: "rwa_net_increase_cap",
      label: "RWA 순증 관리목표(은행)",
      scope: "은행",
      value: fig("cap_rwa_net", "RWA 순증 한도", 12.4, "KRW_TN", { decimals: 1, dataOrigin: "actual" }),
      period: "2026.01.01 ~ 2026.12.31",
      issuer: "NH농협금융지주",
      doc: DOC.rwaPlan,
    },
    {
      id: "cap-rwa-dept",
      kind: "rwa_dept_allocation",
      label: "부서별 신용RWA 한도 배분 합계",
      scope: "여신 부문",
      value: fig("cap_rwa_dept", "배분 합계", 8.6, "KRW_TN", { decimals: 1, dataOrigin: "actual" }),
      period: "2026년 하반기",
      issuer: "종합기획부",
      doc: DOC.rwaDeptAlloc,
    },
  ],
  bankTarget: {
    label: "은행 목표 총자산 증가율",
    value: fig("bank_asset_target", "은행 목표 총자산 증가율", 7.4, "PCT", { decimals: 1, dataOrigin: "actual" }),
    ceiling: fig("bank_asset_ceiling", "지주 한도", 8.2, "PCT", { decimals: 1, dataOrigin: "actual" }),
    headroom: fig("bank_asset_headroom", "한도 여유", 0.8, "PP", {
      decimals: 1,
      calc: trace("calc-cap-headroom", "CAP_HEADROOM", "한도 − 설정값", [
        { key: "cap_value", label: "지주 총자산 최대 증가율", value: "8.2", unit: "%", source: "2025년 RWA 한도 및 총자산 최대 성장률 알림.pdf p.1" },
        { key: "proposed_value", label: "은행 목표 총자산 증가율", value: "7.4", unit: "%", source: "fact.capital_constraint(bank)" },
      ]),
    }),
    passed: true,
  },
  rwaAllocation: [
    {
      org: "여신(기업)",
      allocated: fig("rwa_corp_alloc", "배분", 4.9, "KRW_TN", { decimals: 1, dataOrigin: "actual" }),
      used: fig("rwa_corp_used", "사용", 3.42, "KRW_TN", { decimals: 2 }),
      usageRate: fig("rwa_corp_usage", "소진율", 69.8, "PCT", { decimals: 1 }),
    },
    {
      org: "여신(가계)",
      allocated: fig("rwa_hh_alloc", "배분", 3.1, "KRW_TN", { decimals: 1, dataOrigin: "actual" }),
      used: fig("rwa_hh_used", "사용", 2.86, "KRW_TN", { decimals: 2 }),
      usageRate: fig("rwa_hh_usage", "소진율", 92.3, "PCT", { decimals: 1 }),
    },
    {
      org: "여신(기타)",
      allocated: fig("rwa_etc_alloc", "배분", 0.6, "KRW_TN", { decimals: 1, dataOrigin: "actual" }),
      used: fig("rwa_etc_used", "사용", 0.31, "KRW_TN", { decimals: 2 }),
      usageRate: fig("rwa_etc_usage", "소진율", 51.7, "PCT", { decimals: 1 }),
    },
  ],
  bisSimulation: [
    {
      label: "BIS 총자본비율(시산)",
      value: fig("bis_total", "BIS 총자본비율", 14.8, "PCT", { decimals: 1 }),
      floor: fig("bis_floor", "우량은행 기준", 10.0, "PCT", { decimals: 1, dataOrigin: "actual" }),
      note: "최소기준 8.0% · 우량은행 기준 10.0% 대비 여유 4.8%p",
    },
    {
      label: "보통주자본비율(시산)",
      value: fig("cet1", "보통주자본비율", null, "PCT", {
        undefinedLabel: "데이터 미비로 시산 불가",
      }),
      floor: fig("cet1_floor", "관리기준", 11.0, "PCT", { decimals: 1, dataOrigin: "actual" }),
      note: "보통주자본 항목 데이터가 제공되지 않아 산출하지 않았습니다(추정치 생성 금지).",
    },
  ],
  proxyNote:
    "여신 부문 RWA 소진율은 기업·가계자금대출금 잔액을 대리지표로 환산한 값입니다. RWA 미확보로 여신금액 기준 대체 산출했습니다.",
  evidence: [
    evidence("ev-cap-limit", "internal_direction", "2025년 RWA 한도 및 총자산 최대 성장률 알림", {
      doc: DOC.rwaLimit,
      relevance: 0.95,
      snippet: "은행 총자산 최대 증가율 8.2% 이내에서 자회사가 목표를 설정한다.",
    }),
    evidence("ev-cap-plan", "internal_direction", "자본비율 관리를 위한 자회사별 RWA 순증 관리목표 설정 요청", {
      doc: DOC.rwaPlan,
      relevance: 0.9,
      snippet: "은행 RWA 순증 관리목표 12.4조원, 이행계획 수립 요청.",
    }),
    evidence("ev-cap-dept", "internal_direction", "2026년 하반기 부서별 신용RWA 한도 배분 알림", {
      doc: DOC.rwaDeptAlloc,
      relevance: 0.93,
      snippet: "여신 부문 신용RWA 한도 합계 8.6조원(기업 4.9 / 가계 3.1 / 기타 0.6).",
    }),
  ],
};

/* ═══════════════════════════════════════════════════════════════
 * 수익성 트래킹 (AST-05)
 * ═══════════════════════════════════════════════════════════════ */
export const PROFITABILITY: ProfitabilityRow[] = [
  {
    assetClass: "기업자금대출금",
    balance: fig("prof_corp_bal", "잔액", 115.34, "KRW_TN", { decimals: 2 }),
    revenue: fig("prof_corp_rev", "이자수익(8월 누계)", toBn(RAW.corpInterest.y2026), "KRW_BN"),
    returnOnScale: DIVERGENCE_FIGURES.ros_corp,
    trend: [
      { label: "2024.08", value: 0.945 },
      { label: "2025.08", value: 0.946 },
      { label: "2026.08", value: 0.945 },
    ],
    rank: 1,
    verdict: "수익 기여 상위 · 규모 확대 유리",
  },
  {
    assetClass: "가계자금대출금",
    balance: fig("prof_hh_bal", "잔액", 99.24, "KRW_TN", { decimals: 2 }),
    revenue: fig("prof_hh_rev", "이자수익(8월 누계)", toBn(RAW.hhInterest.y2026), "KRW_BN"),
    returnOnScale: DIVERGENCE_FIGURES.ros_hh,
    trend: [
      { label: "2024.08", value: 0.921 },
      { label: "2025.08", value: 0.914 },
      { label: "2026.08", value: 0.917 },
    ],
    rank: 2,
    verdict: "기여 유지 · 관리목표 상한 근접",
  },
  {
    assetClass: "기타가계자금대출",
    balance: fig("prof_etc_hh_bal", "잔액", 12.34, "KRW_TN", { decimals: 2 }),
    revenue: fig("prof_etc_hh_rev", "이자수익(8월 누계)", 1_062, "KRW_BN"),
    returnOnScale: fig("ros_etc_hh", "규모 대비 수익률", 0.861, "PCT", { decimals: 3 }),
    trend: [
      { label: "2024.08", value: 0.848 },
      { label: "2025.08", value: 0.855 },
      { label: "2026.08", value: 0.861 },
    ],
    rank: 3,
    verdict: "수익률 개선 흐름",
  },
  {
    assetClass: "주택자금대출",
    balance: fig("prof_house_bal", "잔액", 62.48, "KRW_TN", { decimals: 2 }),
    revenue: fig("prof_house_rev", "이자수익(8월 누계)", 4_860, "KRW_BN"),
    returnOnScale: fig("ros_house", "규모 대비 수익률", 0.778, "PCT", { decimals: 3 }),
    trend: [
      { label: "2024.08", value: 0.802 },
      { label: "2025.08", value: 0.789 },
      { label: "2026.08", value: 0.778 },
    ],
    rank: 4,
    verdict: "규모 대비 수익률 하락 흐름",
  },
  {
    assetClass: "공공및기타자금대출",
    balance: fig("prof_public_bal", "잔액", 18.62, "KRW_TN", { decimals: 2 }),
    revenue: fig("prof_public_rev", "이자수익(8월 누계)", 1_140, "KRW_BN"),
    returnOnScale: fig("ros_public", "규모 대비 수익률", 0.612, "PCT", { decimals: 3 }),
    trend: [
      { label: "2024.08", value: 0.634 },
      { label: "2025.08", value: 0.621 },
      { label: "2026.08", value: 0.612 },
    ],
    rank: 5,
    verdict: "저수익 자산군 · 규모 확대 후순위",
  },
];

export const FINANCE_FIGURES: Record<string, Figure> = {
  ...REVENUE_FIGURES,
  ...DIVERGENCE_FIGURES,
  corp_bal: CORPORATE.balance,
  corp_growth: CORPORATE.growth,
  corp_share: CORPORATE.share,
  corp_int_rev: CORPORATE.interestRevenue,
  corp_goal: CORPORATE.goalValue!,
  corp_gap: CORPORATE.gap!,
  hh_bal: HOUSEHOLD.balance,
  hh_growth: HOUSEHOLD.growth,
  hh_share: HOUSEHOLD.share,
  hh_int_rev: HOUSEHOLD.interestRevenue,
  hh_goal: HOUSEHOLD.goalValue!,
  hh_gap: HOUSEHOLD.gap!,
};
