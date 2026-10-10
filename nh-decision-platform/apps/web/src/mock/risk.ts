import type {
  ActionPlan,
  AnalysisTab,
  BranchTarget,
  DefaultRateSeries,
  DefaultRateTrend,
  Figure,
  InclusiveAnalysis,
  InclusiveProductRow,
  Insight,
  ModelGradeRow,
  ModelSummaryRow,
  PsiBucketRow,
  ReportDoc,
  RiskDashboard,
  Severity,
} from "@/lib/types";
import { AS_OF, BATCH_LABEL, GENERATED_AT, PASSED_VERIFICATIONS, evidence, fig, figMap, trace, withAlignment } from "./helpers";
import { DOC } from "./knowledge";

/* ═══════════════════════════════════════════════════════════════
 * 1. 일반기업 신용평가모형 / 소매여신모형 요약
 * ═══════════════════════════════════════════════════════════════ */
const modelFig = (id: string, label: string, value: number, unit: Figure["unit"], decimals: number) =>
  fig(id, label, value, unit, { decimals });

export const CORP_MODELS: ModelSummaryRow[] = [
  {
    modelCode: "CORP_LARGE",
    name: "일반기업 대기업 모형",
    portfolio: "corp",
    segment: "대기업",
    psi: modelFig("psi_large", "PSI", 0.024, "RATIO", 3),
    ar: modelFig("ar_large", "AR", 62.31, "PCT", 2),
    arDecline: modelFig("ard_large", "AR 하락률", 8.4, "PCT", 1),
    ks: modelFig("ks_large", "K-S", 48.2, "PCT", 1),
    auroc: modelFig("auroc_large", "AUROC", 0.812, "RATIO", 3),
    verdict: "적정",
    verdictSeverity: "info",
    verdictBasis: "PSI 0.024(안정) · AR 하락률 8.4%(유사수준 유지) · 등급계량화 검정 통과",
    dataOrigin: "simulated",
  },
  {
    modelCode: "CORP_MID",
    name: "일반기업 중견기업 모형",
    portfolio: "corp",
    segment: "중견기업",
    psi: modelFig("psi_mid", "PSI", 0.038, "RATIO", 3),
    ar: modelFig("ar_mid", "AR", 58.74, "PCT", 2),
    arDecline: modelFig("ard_mid", "AR 하락률", 12.6, "PCT", 1),
    ks: modelFig("ks_mid", "K-S", 44.1, "PCT", 1),
    auroc: modelFig("auroc_mid", "AUROC", 0.794, "RATIO", 3),
    verdict: "적정",
    verdictSeverity: "info",
    verdictBasis: "PSI 0.038(안정) · AR 하락률 12.6%(하락 주의 진입 전 구간)",
    dataOrigin: "simulated",
  },
  {
    modelCode: "CORP_SMALL",
    name: "일반기업 중소기업 모형",
    portfolio: "corp",
    segment: "중소기업",
    psi: modelFig("psi_small", "PSI", 0.061, "RATIO", 3),
    ar: modelFig("ar_small", "AR", 54.18, "PCT", 2),
    arDecline: modelFig("ard_small", "AR 하락률", 19.3, "PCT", 1),
    ks: modelFig("ks_small", "K-S", 40.6, "PCT", 1),
    auroc: modelFig("auroc_small", "AUROC", 0.771, "RATIO", 3),
    verdict: "조건부 적정",
    verdictSeverity: "watch",
    verdictBasis: "PSI 0.061(관찰) · AR 하락률 19.3%(하락 주의) → 분기 점검 주기 유지",
    dataOrigin: "simulated",
  },
  {
    modelCode: "CORP_MICRO",
    name: "일반기업 소기업 모형",
    portfolio: "corp",
    segment: "소기업",
    psi: modelFig("psi_micro", "PSI", 0.082, "RATIO", 3),
    ar: modelFig("ar_micro", "AR", 49.62, "PCT", 2),
    arDecline: modelFig("ard_micro", "AR 하락률", 23.8, "PCT", 1),
    ks: modelFig("ks_micro", "K-S", 37.4, "PCT", 1),
    auroc: modelFig("auroc_micro", "AUROC", 0.748, "RATIO", 3),
    verdict: "조건부 적정",
    verdictSeverity: "caution",
    verdictBasis: "PSI 0.082(관찰 상단) · AR 하락률 23.8%(하락 주의) · 6B 등급 실제부도율이 대표값 초과",
    dataOrigin: "simulated",
  },
];

export const RETAIL_MODELS: ModelSummaryRow[] = [
  {
    modelCode: "RETAIL_AS",
    name: "개인여신 저신용자 AS모형",
    portfolio: "retail",
    segment: "저신용자",
    ar: modelFig("ar_as", "AR", 35.52, "PCT", 2),
    arDecline: modelFig("ard_as", "AR 하락률", 34.7, "PCT", 1),
    ks: modelFig("ks_as", "K-S", 27.6, "PCT", 1),
    auroc: modelFig("auroc_as", "AUROC", 0.678, "RATIO", 3),
    verdict: "미흡 — 재개발 검토",
    verdictSeverity: "caution",
    verdictBasis: "AR 35.52%(보통) · AR 하락률 34.7%(30% 초과, 큰 하락) · 5-6등급·8-9등급 서열화 균열",
    dataOrigin: "simulated",
  },
  {
    modelCode: "RETAIL_BS",
    name: "개인여신 BS모형",
    portfolio: "retail",
    segment: "개인 전체",
    ar: modelFig("ar_bs", "AR", 83.84, "PCT", 2),
    arDecline: modelFig("ard_bs", "AR 하락률", 2.06, "PCT", 2),
    ks: modelFig("ks_bs", "K-S", 70.2, "PCT", 1),
    auroc: modelFig("auroc_bs", "AUROC", 0.919, "RATIO", 3),
    verdict: "양호",
    verdictSeverity: "info",
    verdictBasis: "AR 83.84%(양호) · AR 하락률 2.06%(개발시점과 유사) · 등급별 불량률 서열화 유지",
    dataOrigin: "simulated",
  },
];

/* ═══════════════════════════════════════════════════════════════
 * 2. 소기업 모형 등급별 결과 (6B 특이사항 포함)
 * ═══════════════════════════════════════════════════════════════ */
export const MICRO_GRADES: ModelGradeRow[] = [
  { gradeCode: "3A", obsCount: 1842, obsShare: 4.18, defaultCount: 3, defaultRate: 0.163, pdMid: 0.24, pdMax: 0.3, ks: 5.2, auroc: 0.004, sdrRank: 12, breach: "within_mid" },
  { gradeCode: "3B", obsCount: 3104, obsShare: 7.04, defaultCount: 9, defaultRate: 0.29, pdMid: 0.41, pdMax: 0.52, ks: 11.4, auroc: 0.011, sdrRank: 11, breach: "within_mid" },
  { gradeCode: "4A", obsCount: 5271, obsShare: 11.96, defaultCount: 27, defaultRate: 0.512, pdMid: 0.68, pdMax: 0.86, ks: 19.6, auroc: 0.028, sdrRank: 10, breach: "within_mid" },
  { gradeCode: "4B", obsCount: 6940, obsShare: 15.75, defaultCount: 62, defaultRate: 0.893, pdMid: 1.12, pdMax: 1.41, ks: 27.8, auroc: 0.061, sdrRank: 9, breach: "within_mid" },
  { gradeCode: "5A", obsCount: 7382, obsShare: 16.75, defaultCount: 118, defaultRate: 1.598, pdMid: 1.84, pdMax: 2.26, ks: 34.1, auroc: 0.104, sdrRank: 8, breach: "within_mid" },
  { gradeCode: "5B", obsCount: 6517, obsShare: 14.79, defaultCount: 171, defaultRate: 2.624, pdMid: 2.91, pdMax: 3.48, ks: 37.4, auroc: 0.138, sdrRank: 7, breach: "within_mid" },
  { gradeCode: "5C", obsCount: 4983, obsShare: 11.31, defaultCount: 196, defaultRate: 3.933, pdMid: 4.22, pdMax: 4.95, ks: 35.6, auroc: 0.142, sdrRank: 6, breach: "within_mid" },
  { gradeCode: "6A", obsCount: 3468, obsShare: 7.87, defaultCount: 199, defaultRate: 5.738, pdMid: 5.96, pdMax: 6.87, ks: 28.9, auroc: 0.131, sdrRank: 5, breach: "within_mid" },
  {
    gradeCode: "6B",
    obsCount: 2472,
    obsShare: 5.61,
    defaultCount: 196,
    defaultRate: 7.929,
    pdMid: 7.733,
    pdMax: 8.933,
    ks: 19.4,
    auroc: 0.108,
    sdrRank: 4,
    breach: "above_mid_within_max",
  },
  { gradeCode: "7A", obsCount: 1286, obsShare: 2.92, defaultCount: 132, defaultRate: 10.264, pdMid: 10.98, pdMax: 12.64, ks: 11.2, auroc: 0.072, sdrRank: 3, breach: "within_mid" },
  { gradeCode: "7B", obsCount: 624, obsShare: 1.42, defaultCount: 79, defaultRate: 12.66, pdMid: 14.22, pdMax: 16.38, ks: 5.1, auroc: 0.042, sdrRank: 1, breach: "within_mid" },
  {
    gradeCode: "8",
    obsCount: 178,
    obsShare: 0.4,
    defaultCount: 21,
    defaultRate: 11.798,
    pdMid: 18.9,
    pdMax: 22.4,
    ks: 0.0,
    auroc: 0.012,
    sdrRank: 2,
    breach: "within_mid",
    monotonicBreak: true,
  },
];

export const MICRO_TOTAL = { obsCount: 44067, obsShare: 100.0, defaultCount: 1213, defaultRate: 2.753, auroc: 0.748 };

export const MICRO_PSI_BUCKETS: PsiBucketRow[] = [
  { bucket: "3A", baseShare: 7.8, currentShare: 4.18, contribution: 0.0226 },
  { bucket: "3B", baseShare: 10.4, currentShare: 7.04, contribution: 0.0131 },
  { bucket: "4A", baseShare: 14.6, currentShare: 11.96, contribution: 0.0053 },
  { bucket: "4B", baseShare: 17.2, currentShare: 15.75, contribution: 0.0013 },
  { bucket: "5A", baseShare: 17.0, currentShare: 16.75, contribution: 0.0000 },
  { bucket: "5B", baseShare: 12.6, currentShare: 14.79, contribution: 0.0035 },
  { bucket: "5C", baseShare: 8.4, currentShare: 11.31, contribution: 0.0087 },
  { bucket: "6A", baseShare: 5.2, currentShare: 7.87, contribution: 0.0111 },
  { bucket: "6B", baseShare: 3.4, currentShare: 5.61, contribution: 0.0111 },
  { bucket: "7A", baseShare: 2.0, currentShare: 2.92, contribution: 0.0035 },
  { bucket: "7B", baseShare: 1.0, currentShare: 1.42, contribution: 0.0015 },
  { bucket: "8", baseShare: 0.4, currentShare: 0.4, contribution: 0.0000 },
];

/* ═══════════════════════════════════════════════════════════════
 * 3. 의견 ① — 소기업 6B 등급 (MDL-05)
 * ═══════════════════════════════════════════════════════════════ */
const MODEL_OPINION_FIGURES = figMap(
  fig("dr_6b", "소기업 6B 등급 실제부도율", 7.929, "PCT", {
    decimals: 3,
    calc: trace(
      "calc-dr-6b",
      "DEFAULT_RATE",
      "부도건수 / 전체건수 × 100",
      [
        { key: "default_count", label: "부도건수", value: "196", unit: "건", source: "fact.model_monitoring_grade(CORP_MICRO, 6B).default_count" },
        { key: "obs_count", label: "전체건수", value: "2,472", unit: "건", source: "fact.model_monitoring_grade(CORP_MICRO, 6B).obs_count" },
      ],
      "표시 3자리, 내부 6자리 보존",
    ),
  }),
  fig("pd_mid_6b", "예측부도율 대표값", 7.733, "PCT", {
    decimals: 3,
    dataOrigin: "actual",
    sourceRef: "md.model_grade(CORP_MICRO, 6B).pd_mid — PD Master Scale",
  }),
  fig("pd_max_6b", "예측부도율 최대값", 8.933, "PCT", {
    decimals: 3,
    dataOrigin: "actual",
    sourceRef: "md.model_grade(CORP_MICRO, 6B).pd_max — PD Master Scale",
  }),
  fig("breach_gap_6b", "대표값 초과 폭", 0.196, "PP", {
    decimals: 3,
    calc: trace("calc-breach-6b", "PD_BREACH_CHECK", "실제부도율 − 예측부도율 대표값 (판정: within_mid / above_mid_within_max / above_max)", [
      { key: "actual_dr", label: "실제부도율", value: "7.929000", unit: "%", source: "calc-dr-6b" },
      { key: "pd_mid", label: "예측부도율 대표값", value: "7.733000", unit: "%", source: "md.model_grade(CORP_MICRO, 6B)" },
      { key: "pd_max", label: "예측부도율 최대값", value: "8.933000", unit: "%", source: "md.model_grade(CORP_MICRO, 6B)" },
      { key: "verdict", label: "판정", value: "above_mid_within_max", unit: "", source: "rule_engine.MDL_PD_BREACH" },
    ]),
  }),
  fig("exposure_6b", "6B 등급 익스포저 금액", 4.82, "KRW_TN", { decimals: 2 }),
);

export const MODEL_OPINION: Insight = {
  id: "ins-model-6b",
  kind: "analysis_result",
  persona: "P2",
  domainCode: "loan",
  subDomain: "model_risk",
  title: "소기업 6B 등급 부도율 특이사항",
  statement:
    "소기업 6B 등급은 실제부도율([[fig:dr_6b]])이 예측부도율 대표값([[fig:pd_mid_6b]])을 [[fig:breach_gap_6b]] 초과하나, 최대값([[fig:pd_max_6b]]) 이내 관리 중입니다. 해당 등급 익스포저는 [[fig:exposure_6b]] 규모이며, 동시적 {{term:CHI_SQUARE|카이제곱 검정}}에서는 예측부도율과 실제부도율이 동일하다는 귀무가설이 채택되었습니다.",
  severity: "watch",
  asOf: AS_OF,
  dataOrigin: "simulated",
  figures: MODEL_OPINION_FIGURES,
  evidence: [
    evidence("ev-6b-data", "bank_data", "소기업 모형 등급별 모니터링 결과(2026.08말)", {
      sourceKind: "metric_value",
      tableRef: "fact.model_monitoring_grade(CORP_MICRO)",
      snippet: "6B 등급 전체건수 2,472건 · 부도건수 196건 · 실제부도율 7.929%",
      figureId: "dr_6b",
    }),
    evidence("ev-6b-master", "bank_data", "PD Master Scale — 6B 등급 추정치", {
      sourceKind: "metric_value",
      tableRef: "md.model_grade(CORP_MICRO, 6B)",
      snippet: "최소 6.412% / 대표값 7.733% / 최대 8.933%",
      figureId: "pd_mid_6b",
    }),
    evidence("ev-6b-report", "internal_direction", "2025_일반기업모형 모니터링 보고서 — 지표 체계 및 판정 기준", {
      doc: DOC.corpModelReport,
      relevance: 0.89,
      snippet: "안정성(PSI)·변별력(AR)·등급계량화 검증 순서로 모형 적정성을 판정한다.",
    }),
    evidence("ev-6b-stat", "internal_direction", "붙임. 통계방법론 및 용어 해설 — 등급계량화 검증", {
      doc: DOC.statMethod,
      relevance: 0.84,
      snippet: "실제부도율이 대표값을 초과하더라도 최대값 이내이면 관리 범위 내로 본다.",
    }),
  ],
  verifications: withAlignment(PASSED_VERIFICATIONS),
  reportKind: "model_monitoring",
  reportAnchor: "s4-calibration",
  tabKey: "model-monitoring",
  rankScore: 84.2,
  rankBasis: "심각도(주의) × 익스포저 규모(4.82조) × 목표연관성(5C 이상 비중 목표)",
};

/* ═══════════════════════════════════════════════════════════════
 * 4. 포용금융 충당금 분석 (INC-01~05)
 * ═══════════════════════════════════════════════════════════════ */
const PROVISION_TOTAL_BASE = 3_284_600;
const PROVISION_TOTAL_NOW = 3_412_180;

const rawProducts: Array<[string, string, string, number, number]> = [
  ["2001108220001", "새희망홀씨대출(일반)", "새희망홀씨대출", 28_420, 33_180],
  ["2001108220005", "새희망홀씨대출(생계자금)", "새희망홀씨대출", 19_860, 23_940],
  ["2001108220006", "새희망홀씨대출(사업자금)", "새희망홀씨대출", 12_340, 14_020],
  ["2001109050001", "새희망홀씨대출Ⅱ(일반)", "새희망홀씨대출", 9_780, 11_260],
  ["2001109050002", "새희망홀씨대출Ⅱ(생계자금)", "새희망홀씨대출", 7_420, 8_640],
  ["2001109050003", "새희망홀씨대출Ⅱ(전환대출)", "새희망홀씨대출", 5_260, 6_180],
  ["2001107820007", "햇살론(근로자)", "햇살론", 21_340, 25_620],
  ["2001107820008", "햇살론(자영업자)", "햇살론", 18_760, 22_180],
  ["2001107820010", "햇살론(생계자금)", "햇살론", 15_420, 18_340],
  ["2001107820011", "햇살론(사업운영자금)", "햇살론", 13_280, 15_860],
  ["2001107820012", "햇살론(창업자금)", "햇살론", 11_640, 13_720],
  ["2001107820013", "햇살론(전환대출)", "햇살론", 9_820, 11_480],
  ["2001109000001", "햇살론youth", "햇살론", 8_640, 10_260],
  ["2001109000002", "햇살론뱅크", "햇살론", 7_320, 8_740],
  ["2001109000003", "햇살론카드", "햇살론", 6_180, 7_420],
  ["2001109000004", "근로자햇살론(신규)", "햇살론", 5_240, 6_180],
  ["2001109060003", "햇살론(특례보증)", "햇살론", 4_180, 4_920],
  ["2001109670001", "햇살론15", "햇살론", 3_260, 3_840],
  ["2001109670002", "햇살론17", "햇살론", 2_480, 2_920],
  ["2001109170001", "사잇돌중금리대출", "사잇돌", 30_420, 36_240],
  ["2001109170002", "사잇돌중금리대출Ⅱ", "사잇돌", 20_780, 27_530],
];

const INCLUSIVE_BASE_SUM = rawProducts.reduce((acc, r) => acc + r[3], 0); // 261,840
const INCLUSIVE_NOW_SUM = rawProducts.reduce((acc, r) => acc + r[4], 0); // 312,470

export const INCLUSIVE_PRODUCTS: InclusiveProductRow[] = rawProducts
  .map(([code, name, group, base, now]) => ({
    productCode: code,
    productName: name,
    productGroup: group,
    provisionBase: base,
    provisionNow: now,
    diff: now - base,
    contribution: Number((((now - base) / (INCLUSIVE_NOW_SUM - INCLUSIVE_BASE_SUM)) * 100).toFixed(1)),
  }))
  .sort((a, b) => b.diff - a.diff);

const shareBase = (INCLUSIVE_BASE_SUM / PROVISION_TOTAL_BASE) * 100; // 7.9717
const shareNow = (INCLUSIVE_NOW_SUM / PROVISION_TOTAL_NOW) * 100; // 9.1575 → 9.16 (사사오입, Q9)
const shareDeltaPP = shareNow - shareBase; // 1.1828
const shareDeltaPct = (shareDeltaPP / shareBase) * 100; // 14.837

const provisionShareTrace = (calcId: string, num: number, den: number, ym: string) =>
  trace(calcId, "PROVISION_SHARE", "포용금융 상품 충당금 합계 / 전체 충당금(합계 row) × 100", [
    {
      key: "numerator",
      label: "포용금융 상품 충당금 합계(21개 상품코드)",
      value: num.toLocaleString("ko-KR"),
      unit: "백만원",
      source: `(${ym})7790_상품별_충당금.xlsx · 손실충당금 및 충당부채 총계(X열) 21행 합계`,
    },
    {
      key: "denominator",
      label: "전체 충당금(합계 row)",
      value: den.toLocaleString("ko-KR"),
      unit: "백만원",
      source: `(${ym})7790_상품별_충당금.xlsx!X${ym === "202601" ? "314" : "318"} (합계 row)`,
    },
  ]);

const INCLUSIVE_FIGURES = figMap(
  fig("share_base", "포용금융 충당금 비중(2026.01)", Number(shareBase.toFixed(2)), "PCT", {
    decimals: 2,
    calc: provisionShareTrace("calc-share-base", INCLUSIVE_BASE_SUM, PROVISION_TOTAL_BASE, "202601"),
  }),
  fig("share_now", "포용금융 충당금 비중(2026.08)", Number(shareNow.toFixed(2)), "PCT", {
    decimals: 2,
    calc: provisionShareTrace("calc-share-now", INCLUSIVE_NOW_SUM, PROVISION_TOTAL_NOW, "202608"),
  }),
  fig("share_delta_pp", "비중 증감", Number(shareDeltaPP.toFixed(2)), "PP", {
    decimals: 2,
    calc: trace("calc-share-delta-pp", "SHARE_DELTA_PP", "비교시점 비중 − 기준시점 비중", [
      { key: "share1", label: "2026.08 비중", value: shareNow.toFixed(4), unit: "%", source: "calc-share-now" },
      { key: "share0", label: "2026.01 비중", value: shareBase.toFixed(4), unit: "%", source: "calc-share-base" },
    ]),
  }),
  fig("share_delta_pct", "비중 증가율", Number(shareDeltaPct.toFixed(1)), "PCT", {
    decimals: 1,
    calc: trace("calc-share-delta-pct", "GROWTH_RATE", "(비교시점 비중 − 기준시점 비중) / 기준시점 비중 × 100", [
      { key: "v0", label: "2026.01 비중", value: shareBase.toFixed(4), unit: "%", source: "calc-share-base" },
      { key: "v1", label: "2026.08 비중", value: shareNow.toFixed(4), unit: "%", source: "calc-share-now" },
    ]),
  }),
  fig("prov_inclusive_now", "포용금융 상품 충당금(2026.08)", INCLUSIVE_NOW_SUM, "KRW_MN", {
    sourceRef: "(202608)7790_상품별_충당금.xlsx · X열 21행 합계",
  }),
  fig("prov_total_now", "전체 충당금(2026.08)", PROVISION_TOTAL_NOW, "KRW_MN", {
    sourceRef: "(202608)7790_상품별_충당금.xlsx!X318 (합계 row)",
  }),
  fig("prov_inclusive_base", "포용금융 상품 충당금(2026.01)", INCLUSIVE_BASE_SUM, "KRW_MN", {
    sourceRef: "(202601)7790_상품별_충당금.xlsx · X열 21행 합계",
  }),
  fig("prov_total_base", "전체 충당금(2026.01)", PROVISION_TOTAL_BASE, "KRW_MN", {
    sourceRef: "(202601)7790_상품별_충당금.xlsx!X314 (합계 row)",
  }),
  fig("inc_exposure_cnt_now", "포용금융 익스포저 건수(2026.08)", 213_480, "CNT", {
    calc: trace("calc-inc-cnt", "SUM", "포용금융 상품코드 21건 익스포저 건수 합계", [
      { key: "base", label: "2026.01 건수", value: "184,260", unit: "건", source: "(202601) 여신 익스포저 집계" },
      { key: "now", label: "2026.08 건수", value: "213,480", unit: "건", source: "(202608) 여신 익스포저 집계" },
    ]),
  }),
  fig("inc_exposure_cnt_growth", "익스포저 건수 증가율", 15.9, "PCT", { decimals: 1 }),
  fig("inc_exposure_amt_now", "포용금융 익스포저 규모(2026.08)", 3.42, "KRW_TN", { decimals: 2 }),
  fig("inc_avg_grade", "해당 풀 평균 신용등급(소매 기준)", 6.8, "RATIO", { decimals: 1 }),
  fig("retail_avg_grade", "소매 익스포저 전체 평균 신용등급", 4.9, "RATIO", { decimals: 1 }),
  fig("inc_delinquency", "해당 풀 연체율", null, "PCT", { undefinedLabel: "데이터 미제공" }),
);

export const INCLUSIVE: InclusiveAnalysis = {
  asOf: AS_OF,
  baseYm: "2026.01",
  nowYm: "2026.08",
  shareBase: INCLUSIVE_FIGURES.share_base,
  shareNow: INCLUSIVE_FIGURES.share_now,
  shareDeltaPP: INCLUSIVE_FIGURES.share_delta_pp,
  shareDeltaPct: INCLUSIVE_FIGURES.share_delta_pct,
  provisionInclusiveNow: INCLUSIVE_FIGURES.prov_inclusive_now,
  provisionTotalNow: INCLUSIVE_FIGURES.prov_total_now,
  verdict: "증가",
  severity: "caution",
  products: INCLUSIVE_PRODUCTS,
  groupSummary: [
    { group: "새희망홀씨대출", codes: 6, base: 83_080, now: 97_220, deltaPP: 0.32 },
    { group: "햇살론", codes: 13, base: 127_560, now: 151_480, deltaPP: 0.56 },
    { group: "사잇돌", codes: 2, base: 51_200, now: 63_770, deltaPP: 0.31 },
  ],
  unmatchedCodes: [],
  exposure: [
    { label: "익스포저 건수(2026.08)", figure: INCLUSIVE_FIGURES.inc_exposure_cnt_now },
    { label: "건수 증가율(1월 대비)", figure: INCLUSIVE_FIGURES.inc_exposure_cnt_growth },
    { label: "익스포저 규모(2026.08)", figure: INCLUSIVE_FIGURES.inc_exposure_amt_now },
    { label: "해당 풀 평균 신용등급", figure: INCLUSIVE_FIGURES.inc_avg_grade },
    { label: "소매 전체 평균 신용등급", figure: INCLUSIVE_FIGURES.retail_avg_grade },
    { label: "해당 풀 연체율", figure: INCLUSIVE_FIGURES.inc_delinquency },
  ],
  limitations: [
    "해당 풀의 연체율 데이터가 제공되지 않아 산출하지 않았습니다(추정치 생성 금지).",
    "부도율 영향 분석은 익스포저 단위 부도여부 데이터 확보 후 수행 예정입니다.",
    "(202608)7790 파일에 마스터 미등록 신규 상품 2건이 있으나 포용금융 대상 코드에는 해당하지 않습니다(충당금 영향 0.03%).",
  ],
  ruleId: "INC_PROVISION_SHARE_TREND v1",
};

export const INCLUSIVE_OPINION: Insight = {
  id: "ins-inclusive-provision",
  kind: "analysis_result",
  persona: "P2",
  domainCode: "loan",
  subDomain: "inclusive_finance",
  title: "포용금융 확대 관련 신용리스크 분석 결과",
  statement:
    "포용금융 확대 관련 신용리스크 분석 결과 : 충당금 비중이 [[fig:share_base]] → [[fig:share_now]]로 [[fig:share_delta_pp]] 상승([[fig:share_delta_pct]] 증가)하여 주의가 필요합니다. 해당 풀의 익스포저 건수는 [[fig:inc_exposure_cnt_now]]으로 [[fig:inc_exposure_cnt_growth]] 증가했고, 평균 신용등급은 [[fig:inc_avg_grade]]로 소매 익스포저 평균 [[fig:retail_avg_grade]] 대비 낮습니다. 해당 풀의 연체 발생 및 연체율 증가 여부를 소매모형 관점에서 모니터링할 필요가 있습니다.",
  severity: "caution",
  asOf: AS_OF,
  dataOrigin: "simulated",
  figures: INCLUSIVE_FIGURES,
  evidence: [
    evidence("ev-inc-data", "bank_data", "상품별 충당금 2시점 비교(2026.01 / 2026.08)", {
      sourceKind: "calc_run",
      tableRef: "calc.calc_run(PROVISION_SHARE, SHARE_DELTA_PP)",
      snippet: "포용금융 312,470백만원 / 전체 3,412,180백만원 = 9.16% (1월 7.97%)",
      figureId: "share_now",
    }),
    evidence("ev-inc-products", "internal_direction", "포용금융 대상 상품 운영기준 — 대상 상품코드 21건", {
      doc: DOC.inclusiveProducts,
      relevance: 0.95,
      snippet: "새희망홀씨대출 6건 · 햇살론 13건 · 사잇돌 2건을 포용금융 대상 상품으로 규정.",
    }),
    evidence("ev-inc-perfeval", "internal_direction", "지주 성과평가 방안 5p — 은행 해당 (취약계층) 상품 실적 인정 기준", {
      doc: DOC.groupPerfEval,
      relevance: 0.93,
      snippet: "실적 인정 기준 중 은행에 해당하는 취약계층 상품을 포용금융 대상으로 본다.",
    }),
    evidence("ev-inc-policy", "external_policy", "포용금융 확대방안(금융위원회)", {
      doc: DOC.inclusivePolicy,
      relevance: 0.9,
      snippet: "2026년 1월 이후 서민·취약계층 금융공급 확대 기조가 제시됨.",
    }),
  ],
  verifications: withAlignment(PASSED_VERIFICATIONS),
  reportKind: "inclusive_risk",
  reportAnchor: "i3-share",
  tabKey: "inclusive-risk",
  rankScore: 81.2,
  rankBasis: "심각도(주의) × 충당금 비중 증가 폭 1.18%p × 경영목표 연관성(포용금융 제안)",
};

/* ═══════════════════════════════════════════════════════════════
 * 5. HTML 기반 보고서 — 일반기업 신용평가모형 모니터링 (MDL-07/08)
 * ═══════════════════════════════════════════════════════════════ */
const gradeTableRows = MICRO_GRADES.map((g) => ({
  grade: g.gradeCode,
  obsCount: g.obsCount.toLocaleString("ko-KR"),
  obsShare: g.obsShare.toFixed(2),
  defaultCount: g.defaultCount.toLocaleString("ko-KR"),
  defaultRate: g.defaultRate.toFixed(3),
  pdMid: g.pdMid?.toFixed(3) ?? "-",
  pdMax: g.pdMax?.toFixed(3) ?? "-",
  ks: g.ks?.toFixed(1) ?? "-",
  sdrRank: g.sdrRank ?? "-",
  verdict:
    g.breach === "above_mid_within_max"
      ? "대표값 초과 · 최대값 이내"
      : g.monotonicBreak
        ? "서열화 균열"
        : "예측 범위 내",
}));

export const MODEL_REPORT: ReportDoc = {
  id: "rep-model-monitoring-202608",
  kind: "model_monitoring",
  title: "일반기업 신용평가모형 모니터링 결과",
  subtitle: "소기업 모형 중심 · 분석 기준일 2026.08.31",
  asOf: AS_OF,
  generatedAt: GENERATED_AT,
  dataOrigin: "simulated",
  toc: [
    { id: "s1-overview", label: "1. 개요", level: 2 },
    { id: "s2-stability", label: "2. 안정성 분석", level: 2 },
    { id: "s2-psi", label: "2.1 등급 분포 및 PSI", level: 3 },
    { id: "s3-discrimination", label: "3. 변별력 분석", level: 2 },
    { id: "s3-grade", label: "3.1 등급별 부도율 및 서열화", level: 3 },
    { id: "s4-calibration", label: "4. 등급계량화 검증", level: 2 },
    { id: "s5-findings", label: "5. 특이사항 및 가이드", level: 2 },
  ],
  figures: {
    ...MODEL_OPINION_FIGURES,
    psi_micro: CORP_MODELS[3].psi!,
    ar_micro: CORP_MODELS[3].ar,
    ard_micro: CORP_MODELS[3].arDecline,
    ks_micro: CORP_MODELS[3].ks,
    auroc_micro: CORP_MODELS[3].auroc,
    chi_stat: fig("chi_stat", "카이제곱 통계량", 18.42, "RATIO", {
      decimals: 2,
      calc: trace("calc-chi-micro", "CHI_SQUARE_PD", "χ² = Σ (rᵢ − nᵢ·pᵢ)² / ( nᵢ·pᵢ·(1 − pᵢ) )", [
        { key: "grades", label: "검정 대상 등급 수(k)", value: "12", unit: "개", source: "fact.model_monitoring_grade(CORP_MICRO)" },
        { key: "df", label: "자유도", value: "12", unit: "", source: "k" },
        { key: "confidence", label: "신뢰수준", value: "95%", unit: "", source: "rule_engine.settings.chi_confidence" },
      ]),
    }),
    chi_critical: fig("chi_critical", "임계값(자유도 12, 95%)", 21.03, "RATIO", { decimals: 2, dataOrigin: "actual" }),
    total_obs: fig("total_obs", "소기업 모형 전체 익스포저 건수", MICRO_TOTAL.obsCount, "CNT"),
    total_dr: fig("total_dr", "소기업 모형 전체 실제부도율", MICRO_TOTAL.defaultRate, "PCT", { decimals: 3 }),
  },
  opinions: [MODEL_OPINION],
  evidence: MODEL_OPINION.evidence,
  limitations: [
    "관련 보고서는 2025년 기준이나, 분석 기준일을 2026년 8월말로 설정한 가상 분석 결과입니다.",
    "실제 익스포저 단위 데이터 수령 시 동일 스키마로 교체됩니다(코드 변경 없음).",
    "PSI·AR 하락률 판정 임계값은 행내 확정 전 잠정값입니다.",
  ],
  sections: [
    {
      id: "s1-overview",
      heading: "1. 개요",
      level: 2,
      blocks: [
        {
          type: "p",
          text: "본 보고서는 행 내 일반기업 규모별 신용평가모형에 대해 2026년 8월말 기준 익스포저의 건수·금액·모형등급·부도여부를 활용하여 {{term:PSI|안정성}}과 {{term:AR|부도예측력}}을 측정하고, 모형 적정성을 점검한 결과입니다. 소기업 모형은 전체 익스포저 [[fig:total_obs]], 전체 실제부도율 [[fig:total_dr]] 수준입니다.",
        },
        {
          type: "kv",
          kv: [
            { label: "대상 모형", value: "대기업 · 중견기업 · 중소기업 · 소기업 (4개 규모별 모형)" },
            { label: "분석 기준일", value: "2026.08.31" },
            { label: "비교 기준시점", value: "2025.08.31 (PSI 기준 분포)" },
            { label: "판정 체계", value: "안정성 → 변별력 → 등급계량화 → 종합 적정성" },
          ],
        },
        {
          type: "callout",
          tone: "info",
          text: "판정 임계값은 설정값으로 관리되며, 과거 판정은 당시 임계값 버전으로 보존됩니다.",
        },
      ],
    },
    {
      id: "s2-stability",
      heading: "2. 안정성 분석",
      level: 2,
      blocks: [
        {
          type: "p",
          text: "소기업 모형의 {{term:PSI|PSI}}는 [[fig:psi_micro]]로 관찰 구간입니다. 등급 분포가 상위 등급(3A~4A)에서 하위 등급(5C~6B)으로 이동하는 흐름이 확인되며, 6B 등급 구성비는 기준시점 3.40%에서 5.61%로 상승했습니다.",
        },
      ],
    },
    {
      id: "s2-psi",
      heading: "2.1 등급 분포 및 PSI",
      level: 3,
      blocks: [
        {
          type: "table",
          table: {
            caption: "등급별 분포 비교 및 PSI 기여도",
            columns: [
              { key: "bucket", label: "등급" },
              { key: "baseShare", label: "기준시점 비중(%)", align: "right" },
              { key: "currentShare", label: "비교시점 비중(%)", align: "right" },
              { key: "diff", label: "증감(%p)", align: "right" },
              { key: "contribution", label: "PSI 기여도", align: "right", term: "PSI" },
            ],
            rows: MICRO_PSI_BUCKETS.map((b) => ({
              bucket: b.bucket,
              baseShare: b.baseShare.toFixed(2),
              currentShare: b.currentShare.toFixed(2),
              diff: (b.currentShare - b.baseShare).toFixed(2),
              contribution: b.contribution.toFixed(4),
            })),
            note: "기여도 합계 0.0817 → PSI 0.082 (표시 3자리). 비중 0 구간은 ε=0.0001 보정 규칙 적용 대상이나 해당 구간 없음.",
          },
        },
        {
          type: "chart",
          chart: {
            kind: "bar",
            title: "등급별 구성비 — 기준시점 vs 비교시점",
            unit: "PCT",
            series: [
              { name: "2025.08(기준)", points: MICRO_PSI_BUCKETS.map((b) => ({ label: b.bucket, value: b.baseShare })) },
              { name: "2026.08(비교)", points: MICRO_PSI_BUCKETS.map((b) => ({ label: b.bucket, value: b.currentShare })) },
            ],
          },
        },
      ],
    },
    {
      id: "s3-discrimination",
      heading: "3. 변별력 분석",
      level: 2,
      blocks: [
        {
          type: "p",
          text: "소기업 모형의 {{term:AR|AR}}은 [[fig:ar_micro]]이며 개발시점 대비 {{term:AR_DECLINE|AR 하락률}}은 [[fig:ard_micro]]로 하락 주의 구간입니다. {{term:KS|K-S 통계량}}은 [[fig:ks_micro]], {{term:AUROC|AUROC}}는 [[fig:auroc_micro]] 수준입니다.",
        },
        {
          type: "ul",
          items: [
            "AR 하락률이 30%를 초과하지는 않았으나, 전기(15.2%) 대비 확대되는 흐름이 확인됩니다.",
            "K-S 최대 격차는 5B 등급 구간(37.4)에서 발생했습니다.",
            "7B·8 등급 구간에서 {{term:SDR|서열화}} 균열이 확인되어 해당 구간 표본 수(624건 / 178건)를 함께 점검할 필요가 있습니다.",
          ],
        },
      ],
    },
    {
      id: "s3-grade",
      heading: "3.1 등급별 부도율 및 서열화",
      level: 3,
      blocks: [
        {
          type: "table",
          table: {
            caption: "소기업 모형 등급별 모니터링 결과 (2026.08.31)",
            columns: [
              { key: "grade", label: "등급" },
              { key: "obsCount", label: "전체건수", align: "right" },
              { key: "obsShare", label: "구성비(%)", align: "right" },
              { key: "defaultCount", label: "부도건수", align: "right" },
              { key: "defaultRate", label: "실제부도율(%)", align: "right" },
              { key: "pdMid", label: "예측 대표값(%)", align: "right", term: "PD_MASTER_SCALE" },
              { key: "pdMax", label: "예측 최대값(%)", align: "right", term: "PD_MASTER_SCALE" },
              { key: "ks", label: "K-S", align: "right", term: "KS" },
              { key: "sdrRank", label: "SDR", align: "right", term: "SDR" },
              { key: "verdict", label: "판정" },
            ],
            rows: gradeTableRows,
            highlightRowKey: "grade",
            highlightRowValue: "6B",
            note: "합계 44,067건 / 부도 1,213건 / 전체 실제부도율 2.753%",
          },
        },
        {
          type: "chart",
          chart: {
            kind: "line",
            title: "등급별 실제부도율 vs 예측부도율 대표값·최대값",
            unit: "PCT",
            series: [
              { name: "실제부도율", points: MICRO_GRADES.map((g) => ({ label: g.gradeCode, value: g.defaultRate })) },
              { name: "예측 대표값", points: MICRO_GRADES.map((g) => ({ label: g.gradeCode, value: g.pdMid ?? null })) },
              { name: "예측 최대값", points: MICRO_GRADES.map((g) => ({ label: g.gradeCode, value: g.pdMax ?? null })) },
            ],
          },
        },
      ],
    },
    {
      id: "s4-calibration",
      heading: "4. 등급계량화 검증",
      level: 2,
      blocks: [
        {
          type: "p",
          text: "{{term:CALIBRATION|등급계량화}} 적정성은 등급별 실제부도율과 {{term:PD_MASTER_SCALE|PD 추정치}} 비교 및 {{term:CHI_SQUARE|카이제곱 검정}}으로 확인했습니다. 검정통계량은 [[fig:chi_stat]]로 임계값 [[fig:chi_critical]]을 초과하지 않아 예측부도율과 실제부도율이 동일하다는 귀무가설이 채택되었습니다.",
        },
        {
          type: "callout",
          tone: "attention",
          text: "다만 개별 등급 기준으로는 6B 등급의 실제부도율([[fig:dr_6b]])이 예측부도율 대표값([[fig:pd_mid_6b]])을 [[fig:breach_gap_6b]] 초과했습니다. 최대값([[fig:pd_max_6b]]) 이내이므로 관리 범위 내로 판정하되, 재계량화 필요성은 차기 모니터링에서 재확인 대상입니다.",
        },
        {
          type: "kv",
          kv: [
            { label: "[1단계]", value: "χ² = 18.42 < 임계값 21.03" },
            { label: "[2단계]", value: "귀무가설 채택" },
            { label: "[3단계]", value: "예측부도율과 실제부도율은 동일하다고 판단" },
          ],
        },
      ],
    },
    {
      id: "s5-findings",
      heading: "5. 특이사항 및 가이드",
      level: 2,
      blocks: [
        {
          type: "table",
          table: {
            caption: "탐지된 특이사항",
            columns: [
              { key: "no", label: "No" },
              { key: "item", label: "특이사항" },
              { key: "severity", label: "심각도" },
              { key: "guide", label: "가이드" },
            ],
            rows: [
              {
                no: 1,
                item: "소기업 6B 등급 실제부도율이 예측부도율 대표값 초과(최대값 이내)",
                severity: "주의",
                guide: "해당 등급 표본 구성 점검 및 등급계량화 재검토 필요성 차기 확인",
              },
              {
                no: 2,
                item: "소기업 모형 PSI 0.082 — 등급 하향 이동 누적",
                severity: "관찰",
                guide: "분기 점검 주기 유지, 하위 등급 신규 취급 구성 점검",
              },
              {
                no: 3,
                item: "7B·8 등급 서열화 균열(12.660% > 11.798%)",
                severity: "관찰",
                guide: "해당 구간 표본 수 부족 여부 확인 후 등급 병합 검토",
              },
              {
                no: 4,
                item: "소매 AS모형 AR 하락률 34.7% — 큰 하락 구간",
                severity: "주의",
                guide: "저신용자 모형 재개발 검토 및 대체 변수 발굴",
              },
            ],
          },
        },
        {
          type: "callout",
          tone: "info",
          text: "가이드는 정부정책 DB · 경영 의사결정 DB · 종합기획부 경영계획과의 배치 여부를 검증한 결과 충돌이 확인되지 않았습니다. 반영한 기준은 근거로 함께 제시됩니다.",
        },
      ],
    },
  ],
};

/* ═══════════════════════════════════════════════════════════════
 * 6. HTML 기반 보고서 — 포용금융 신용리스크
 * ═══════════════════════════════════════════════════════════════ */
export const INCLUSIVE_REPORT: ReportDoc = {
  id: "rep-inclusive-202608",
  kind: "inclusive_risk",
  title: "포용금융 확대 관련 신용리스크 분석",
  subtitle: "2026.01 대비 2026.08 충당금 변화 · 대상 상품코드 21건",
  asOf: AS_OF,
  generatedAt: GENERATED_AT,
  dataOrigin: "simulated",
  toc: [
    { id: "i1-scope", label: "1. 분석 대상 정의", level: 2 },
    { id: "i2-data", label: "2. 데이터 및 산출 기준", level: 2 },
    { id: "i3-share", label: "3. 충당금 비중 변화", level: 2 },
    { id: "i3-group", label: "3.1 상품군별 분해", level: 3 },
    { id: "i3-product", label: "3.2 상품별 기여도", level: 3 },
    { id: "i4-exposure", label: "4. 익스포저 및 건전성", level: 2 },
    { id: "i5-opinion", label: "5. 의견 및 관리방안", level: 2 },
  ],
  figures: INCLUSIVE_FIGURES,
  opinions: [INCLUSIVE_OPINION],
  evidence: INCLUSIVE_OPINION.evidence,
  limitations: INCLUSIVE.limitations,
  sections: [
    {
      id: "i1-scope",
      heading: "1. 분석 대상 정의",
      level: 2,
      blocks: [
        {
          type: "p",
          text: "포용금융 대상은 「포용금융 대상 상품 대상자」로 규정하고, 경영 의사결정 DB의 포용금융 대상 상품 운영기준과 지주 성과평가 방안 5p 실적 인정 기준(은행 해당 취약계층 상품)을 근거로 상품코드 21건을 식별했습니다.",
        },
        {
          type: "table",
          table: {
            caption: "포용금융 대상 상품군",
            columns: [
              { key: "group", label: "상품군" },
              { key: "codes", label: "상품코드 수", align: "right" },
              { key: "base", label: "2026.01 충당금(백만원)", align: "right" },
              { key: "now", label: "2026.08 충당금(백만원)", align: "right" },
              { key: "deltaPP", label: "비중 증감(%p)", align: "right" },
            ],
            rows: INCLUSIVE.groupSummary.map((g) => ({
              group: g.group,
              codes: g.codes,
              base: g.base.toLocaleString("ko-KR"),
              now: g.now.toLocaleString("ko-KR"),
              deltaPP: `+${g.deltaPP.toFixed(2)}`,
            })),
            note: "상품코드 21건 전건 매칭(미매칭 0건).",
          },
        },
      ],
    },
    {
      id: "i2-data",
      heading: "2. 데이터 및 산출 기준",
      level: 2,
      blocks: [
        {
          type: "kv",
          kv: [
            { label: "기준시점 데이터", value: "(202601)7790_상품별_충당금.xlsx" },
            { label: "비교시점 데이터", value: "(202608)7790_상품별_충당금.xlsx" },
            { label: "기준 값", value: "손실충당금 및 충당부채 총계 (원천 X열)" },
            { label: "분모", value: "전체 충당금 — 합계 row" },
            { label: "산출식", value: "포용금융 상품 충당금 합계 / 전체 충당금 × 100", term: "PROVISION_SHARE" },
          ],
        },
        {
          type: "callout",
          tone: "info",
          text: "2026년 1월 이후 포용금융 확대 정부기조를 반영한 당행 운영 이후의 변화를 보기 위해 1월을 기준시점으로 설정했습니다.",
        },
      ],
    },
    {
      id: "i3-share",
      heading: "3. 충당금 비중 변화",
      level: 2,
      blocks: [
        {
          type: "p",
          text: "포용금융 상품 충당금은 [[fig:prov_inclusive_base]] → [[fig:prov_inclusive_now]]으로 증가했고, 전체 충당금은 [[fig:prov_total_base]] → [[fig:prov_total_now]]입니다. 이에 따라 비중은 [[fig:share_base]] → [[fig:share_now]]로 [[fig:share_delta_pp]] 상승했습니다(증가율 [[fig:share_delta_pct]]).",
        },
        {
          type: "chart",
          chart: {
            kind: "bar",
            title: "포용금융 충당금 비중 — 2026.01 vs 2026.08",
            unit: "PCT",
            series: [
              {
                name: "충당금 비중",
                points: [
                  { label: "2026.01", value: Number(shareBase.toFixed(2)) },
                  { label: "2026.08", value: Number(shareNow.toFixed(2)) },
                ],
              },
            ],
          },
        },
      ],
    },
    {
      id: "i3-group",
      heading: "3.1 상품군별 분해",
      level: 3,
      blocks: [
        {
          type: "chart",
          chart: {
            kind: "bar",
            title: "상품군별 충당금 — 2026.01 vs 2026.08 (백만원)",
            unit: "KRW_MN",
            series: [
              { name: "2026.01", points: INCLUSIVE.groupSummary.map((g) => ({ label: g.group, value: g.base })) },
              { name: "2026.08", points: INCLUSIVE.groupSummary.map((g) => ({ label: g.group, value: g.now })) },
            ],
          },
        },
        {
          type: "p",
          text: "비중 상승 기여는 햇살론(+0.56%p) · 새희망홀씨대출(+0.32%p) · 사잇돌(+0.31%p) 순으로 확인됩니다. 특정 상품군에 집중된 흐름이 아니라 대상 상품 전반의 취급 확대와 함께 나타난 변화입니다.",
        },
      ],
    },
    {
      id: "i3-product",
      heading: "3.2 상품별 기여도",
      level: 3,
      blocks: [
        {
          type: "table",
          table: {
            caption: "상품별 충당금 증감 및 기여도 (상위 10건)",
            columns: [
              { key: "code", label: "상품코드" },
              { key: "name", label: "상품명" },
              { key: "group", label: "상품군" },
              { key: "base", label: "2026.01", align: "right" },
              { key: "now", label: "2026.08", align: "right" },
              { key: "diff", label: "증감", align: "right" },
              { key: "contribution", label: "기여도(%)", align: "right" },
            ],
            rows: INCLUSIVE_PRODUCTS.slice(0, 10).map((p) => ({
              code: p.productCode,
              name: p.productName,
              group: p.productGroup,
              base: p.provisionBase.toLocaleString("ko-KR"),
              now: p.provisionNow.toLocaleString("ko-KR"),
              diff: `+${p.diff.toLocaleString("ko-KR")}`,
              contribution: p.contribution.toFixed(1),
            })),
            note: "단위 백만원. 기여도 = 상품 증감 / 포용금융 전체 증감 × 100",
          },
        },
      ],
    },
    {
      id: "i4-exposure",
      heading: "4. 익스포저 및 건전성",
      level: 2,
      blocks: [
        {
          type: "p",
          text: "해당 풀 익스포저 건수는 [[fig:inc_exposure_cnt_now]]으로 기준시점 대비 [[fig:inc_exposure_cnt_growth]] 증가했고, 규모는 [[fig:inc_exposure_amt_now]]입니다. 평균 신용등급은 [[fig:inc_avg_grade]]로 소매 익스포저 전체 평균 [[fig:retail_avg_grade]] 대비 낮은 수준입니다.",
        },
        {
          type: "callout",
          tone: "attention",
          text: "해당 풀의 연체율은 [[fig:inc_delinquency]] 상태로, 데이터 확보 후 연체 발생 및 연체율 증가 여부를 확인할 필요가 있습니다.",
        },
      ],
    },
    {
      id: "i5-opinion",
      heading: "5. 의견 및 관리방안",
      level: 2,
      blocks: [
        {
          type: "p",
          text: "충당금 비중이 상승하고 있으므로 주의를 요합니다. 익스포저 건수가 증가하고 해당 풀의 평균 건전성이 소매 익스포저 평균 대비 낮으므로, 해당 풀에서의 연체 발생 및 연체율 증가 여부를 소매모형 관점에서 모니터링하는 방안을 제시합니다.",
        },
        {
          type: "ul",
          items: [
            "월 단위 연체 발생 건수·금액 및 연체율 추이 모니터링(소매모형 스코어 구간별)",
            "신규 취급 후 3·6개월 경과 시점의 초기 연체(Vintage) 지표 관리",
            "충당금 비중 임계(설정값 +0.5%p) 초과 시 중점관리사항으로 상향 보고",
          ],
        },
        {
          type: "callout",
          tone: "info",
          text: "본 관리방안은 정부정책 DB(포용금융 확대방안) · 경영 의사결정 DB(포용금융 대상 상품 운영기준, 성과평가 방안) · 종합기획부 경영계획(포용금융 확대)과 배치되지 않으며, 반영한 기준을 근거로 제시했습니다. 공급 축소를 함의하는 방향은 제안하지 않았습니다.",
        },
      ],
    },
  ],
};

export const REPORTS: Record<string, ReportDoc> = {
  "model-monitoring": MODEL_REPORT,
  "inclusive-risk": INCLUSIVE_REPORT,
};

/* ═══════════════════════════════════════════════════════════════
 * 7. 동적 탭 (CRM-05)
 * ═══════════════════════════════════════════════════════════════ */
export const ANALYSIS_TABS: AnalysisTab[] = [
  {
    tabKey: "model-monitoring",
    label: "① 소기업 6B 등급 부도율 특이사항",
    reportKind: "model_monitoring",
    insightId: "ins-model-6b",
    severity: "watch",
    generation: "current",
    asOf: AS_OF,
    generatedAt: GENERATED_AT,
  },
  {
    tabKey: "inclusive-risk",
    label: "② 포용금융 확대 관련 신용리스크",
    reportKind: "inclusive_risk",
    insightId: "ins-inclusive-provision",
    severity: "caution",
    generation: "current",
    asOf: AS_OF,
    generatedAt: GENERATED_AT,
  },
];

export const PREVIOUS_TABS: AnalysisTab[] = [
  {
    tabKey: "model-monitoring-prev",
    label: "소기업 모형 PSI 관찰 구간 진입",
    reportKind: "model_monitoring",
    insightId: "ins-model-psi-prev",
    severity: "watch",
    generation: "previous",
    asOf: "2026-08-30",
    generatedAt: "2026-08-31T06:20:00+09:00",
  },
];

/* ═══════════════════════════════════════════════════════════════
 * 8. 수행방안 / 중점관리사항 (CRM-06)
 * ═══════════════════════════════════════════════════════════════ */
export const ACTION_PLANS: ActionPlan[] = [
  {
    id: "plan-inclusive-risk",
    title: "포용금융 확대에 따른 신용리스크 중점관리방안",
    body:
      "포용금융 대상 상품 풀의 익스포저 건수가 증가하고 평균 건전성이 소매 익스포저 평균 대비 낮으므로, 해당 풀의 연체 발생 및 연체율 증가 여부를 소매모형 관점에서 모니터링한다. 충당금 비중이 설정 임계(+0.5%p)를 추가 초과하는 경우 중점관리사항으로 상향 보고한다.",
    ownerOrg: "신용리스크관리부",
    monitoringMetrics: ["포용금융 충당금 비중", "포용금융 풀 연체율", "포용금융 익스포저 건수", "소매모형 스코어 구간별 불량률"],
    reviewCycle: "월",
    relatedGoalTitle: "(제안) 포용금융 공급 확대",
    alignment: {
      verdict: "aligned",
      matched: [
        "정부정책 DB — 포용금융 확대방안",
        "경영 의사결정 DB — 포용금융 대상 상품 운영기준 / 지주 성과평가 방안",
        "종합기획부 경영계획 — 포용금융 확대",
      ],
      conflicts: [],
    },
    evidence: INCLUSIVE_OPINION.evidence,
    status: "proposed",
    branchShared: false,
    origin: "agent",
    relatedGoalId: "goal-inclusive-new",
    sourceInsightId: "ins-inclusive-provision",
    linkedTabKey: "inclusive-risk",
    linkedAnalysisLabel: "② 포용금융 확대 관련 신용리스크",
    guideRuleId: "GUIDE_RETAIL_POOL_WATCH",
  },
  {
    id: "plan-micro-recalibration",
    title: "소기업 모형 6B 등급 등급계량화 재검토",
    body:
      "6B 등급의 실제부도율이 예측부도율 대표값을 초과(최대값 이내)한 상태이므로, 해당 등급 표본 구성과 최근 신규 취급 구성을 점검한다. 차기 모니터링에서 초과가 지속되면 등급계량화 재산출을 모형위원회에 상정한다.",
    ownerOrg: "신용리스크관리부",
    monitoringMetrics: ["6B 등급 실제부도율", "6B 등급 구성비", "소기업 모형 PSI"],
    reviewCycle: "분기",
    relatedGoalTitle: "신용등급 5C 이상 차주 비중 62%대 유지",
    alignment: {
      verdict: "aligned",
      matched: [
        "경영 의사결정 DB — 2026년 하반기 경영전략회의(건전성 관리 강화)",
        "종합기획부 경영계획 — 5C 이상 차주 비중 유지",
      ],
      conflicts: [],
    },
    evidence: MODEL_OPINION.evidence,
    status: "proposed",
    branchShared: false,
    origin: "agent",
    relatedGoalId: "goal-grade-5c",
    sourceInsightId: "ins-model-6b",
    linkedTabKey: "model-monitoring",
    linkedAnalysisLabel: "① 소기업 6B 등급 부도율 특이사항",
    guideRuleId: "GUIDE_RECALIBRATION",
  },
  {
    id: "plan-as-model-redev",
    title: "개인여신 저신용자 AS모형 재개발 검토",
    body:
      "AS모형 AR 하락률이 34.7%로 큰 하락 구간에 해당한다. 대체 변수 발굴 및 재개발 필요성을 검토하고, 재개발 이전에는 스코어 컷오프 운영 기준을 보수적으로 적용한다.",
    ownerOrg: "신용리스크관리부",
    monitoringMetrics: ["AS모형 AR", "AS모형 AR 하락률", "저신용자 풀 불량률"],
    reviewCycle: "분기",
    alignment: {
      verdict: "unknown",
      matched: [],
      conflicts: [],
    },
    evidence: [
      evidence("ev-as-report", "internal_direction", "'25년 3분기 소매여신모형 모니터링 결과 보고서", {
        doc: DOC.retailModelReport,
        relevance: 0.9,
        snippet: "개인여신 저신용자 AS모형 AR 35.52%, 개발시점 대비 AR 하락률 34.7%로 비교적 큼.",
      }),
    ],
    status: "proposed",
    branchShared: false,
    origin: "agent",
    sourceInsightId: "ins-model-6b",
    guideRuleId: "GUIDE_MODEL_REDEV",
  },
];

/* ═══════════════════════════════════════════════════════════════
 * 9. 영업점 목표 (BR-01)
 * ═══════════════════════════════════════════════════════════════ */
export const BRANCH_TARGETS: BranchTarget[] = [
  {
    id: "bt-corp-metro1",
    orgCode: "R001",
    orgName: "수도권1지역본부",
    title: "기업여신 신규 취급 1.24조원",
    guideline: "5C 이상 차주 중심 취급, 정책자금 연계 상품 우선. 6B 이하 신규 취급은 본부 사전 협의.",
    metricLabel: "기업여신 신규 취급액",
    target: fig("bt1_target", "목표", 1.24, "KRW_TN", { decimals: 2, dataOrigin: "actual" }),
    actual: fig("bt1_actual", "8월말 실적", 0.78, "KRW_TN", { decimals: 2 }),
    progress: 62.9,
    periodLabel: "2026 하반기",
    sourcePlanTitle: "기업여신 확대 실행방안(하반기)",
    sourceGoalTitle: "기업여신 전년 대비 +7.0% 이상 확대",
  },
  {
    id: "bt-hh-metro1",
    orgCode: "R001",
    orgName: "수도권1지역본부",
    title: "가계여신 월 취급 한도 2,400억원",
    guideline: "잔액 관리 한도 소진율 99.2% — 월 한도 내 취급, 초과 시 사전승인 필수.",
    metricLabel: "가계여신 월 취급액",
    target: fig("bt2_target", "월 한도", 2_400, "KRW_BN", { dataOrigin: "actual" }),
    actual: fig("bt2_actual", "8월 취급액", 2_286, "KRW_BN"),
    progress: 95.3,
    periodLabel: "2026.08",
    sourcePlanTitle: "가계여신 증가율 관리 강화방안",
    sourceGoalTitle: "가계여신 전년 대비 +4.0% 이하 관리",
  },
  {
    id: "bt-inclusive-metro1",
    orgCode: "R001",
    orgName: "수도권1지역본부",
    title: "포용금융 상품 취급 후 연체 모니터링",
    guideline: "새희망홀씨·햇살론·사잇돌 취급 후 3·6개월 초기 연체 점검 결과를 월별 보고.",
    metricLabel: "초기 연체 점검 이행률",
    target: fig("bt3_target", "목표", 100, "PCT", { decimals: 0, dataOrigin: "actual" }),
    actual: fig("bt3_actual", "8월 이행률", 84, "PCT", { decimals: 0 }),
    progress: 84,
    periodLabel: "2026 하반기",
    sourcePlanTitle: "포용금융 확대에 따른 신용리스크 중점관리방안",
    sourceGoalTitle: "(제안) 포용금융 공급 확대",
  },
];

/* ═══════════════════════════════════════════════════════════════
 * 10. 리스크 Dashboard (CRM-01~04)
 * ═══════════════════════════════════════════════════════════════ */
export const RISK_DASHBOARD: RiskDashboard = {
  asOf: AS_OF,
  generatedAt: GENERATED_AT,
  batchLabel: BATCH_LABEL,
  degradedSources: ["graph", "vector"],
  corpModels: CORP_MODELS,
  retailModels: RETAIL_MODELS,
  appliedGoals: [
    { title: "기업여신 전년 대비 +7.0% 이상 확대", value: "+7.0%", source: "종합기획부 확정 · v3", updatedAt: "2026-07-03" },
    { title: "가계여신 전년 대비 +4.0% 이하 관리", value: "+4.0% 이하", source: "종합기획부 확정 · v2", updatedAt: "2026-03-10" },
    { title: "신용등급 5C 이상 차주 비중 62%대 유지", value: "62.0%", source: "종합기획부 확정 · v1", updatedAt: "2025-12-27" },
  ],
  opinions: [MODEL_OPINION, INCLUSIVE_OPINION],
  dataQuality: [
    { label: "(202608)7790_상품별_충당금", status: "warning", note: "마스터 미등록 신규 상품 2건(포용금융 대상 아님)" },
    { label: "소기업 모형 익스포저 집계", status: "passed", note: "합계 검증 통과 · 등급 12구간 전건 매칭" },
    { label: "포용금융 상품코드 매칭", status: "passed", note: "21건 전건 매칭(미매칭 0건)" },
    { label: "해당 풀 연체율", status: "failed", note: "데이터 미제공 — 분석에서 제외하고 한계로 표기" },
  ],
};

/* ═══════════════════════════════════════════════════════════════
 * 월별 부도율 추이 (신용리스크관리부 1화면 상단)
 *  - 기업: 규모 구분 5종 (대기업 / 외감 / 비외감 / 소기업 / 기업형소호)
 *  - 개인: 풀 구분 5종 — 풀 정의는 확정 전 임시 구분
 *  실제 시스템에서는 fact.default_rate_monthly 를 DEFAULT_RATE 수식으로 집계한다.
 * ═══════════════════════════════════════════════════════════════ */
const DR_MONTHS = ["2025.09", "2025.10", "2025.11", "2025.12", "2026.01", "2026.02", "2026.03", "2026.04", "2026.05", "2026.06", "2026.07", "2026.08"];

function drSeries(
  key: string,
  label: string,
  values: number[],
  severity: Severity,
  note?: string,
): DefaultRateSeries {
  const points = DR_MONTHS.map((label, i) => ({ label, value: values[i] ?? null }));
  const latest = values[values.length - 1];
  const first = values[0];
  return {
    key,
    label,
    points,
    latest: fig(`dr_${key}_latest`, `${label} 부도율(2026.08)`, latest, "PCT", {
      decimals: 3,
      calc: trace(
        `calc_dr_${key}`,
        "DEFAULT_RATE",
        "부도건수 ÷ 관측건수 × 100",
        [
          { key: "default_count", label: "부도건수", value: "집계값", source: "fact.default_rate_monthly" },
          { key: "obs_count", label: "관측건수", value: "집계값", source: "fact.default_rate_monthly" },
        ],
        "월별 신규 부도 발생 기준 · 12개월 이동",
      ),
    }),
    deltaPP: fig(`dr_${key}_delta`, `${label} 부도율 증감(2025.09 대비)`, Number((latest - first).toFixed(3)), "PP", {
      decimals: 3,
      calc: trace(`calc_dr_${key}_d`, "DIFF", "당월 부도율 − 기준월 부도율", [
        { key: "now", label: "2026.08", value: `${latest}%`, source: "calc.metric_value" },
        { key: "base", label: "2025.09", value: `${first}%`, source: "calc.metric_value" },
      ]),
    }),
    severity,
    note,
  };
}

export const DEFAULT_RATE_TREND: DefaultRateTrend = {
  asOf: AS_OF,
  generatedAt: GENERATED_AT,
  corpSegments: [
    drSeries("corp_large", "대기업", [0.412, 0.408, 0.401, 0.396, 0.389, 0.392, 0.388, 0.381, 0.377, 0.374, 0.371, 0.368], "info"),
    drSeries("corp_audited", "외감", [0.884, 0.891, 0.902, 0.918, 0.931, 0.944, 0.958, 0.971, 0.986, 1.004, 1.021, 1.038], "watch"),
    drSeries("corp_unaudited", "비외감", [1.642, 1.668, 1.701, 1.736, 1.772, 1.814, 1.858, 1.901, 1.947, 1.994, 2.041, 2.088], "caution"),
    drSeries("corp_micro", "소기업", [2.481, 2.523, 2.571, 2.618, 2.664, 2.702, 2.738, 2.761, 2.774, 2.781, 2.766, 2.753], "caution", "6B 등급 특이사항 발생 구간"),
    drSeries("corp_soho", "기업형소호", [3.128, 3.182, 3.246, 3.311, 3.384, 3.462, 3.541, 3.618, 3.694, 3.768, 3.841, 3.912], "critical"),
  ],
  retailPools: [
    drSeries("pool_1", "풀 1 (임시)", [1.214, 1.228, 1.241, 1.259, 1.272, 1.288, 1.301, 1.318, 1.332, 1.347, 1.361, 1.374], "watch"),
    drSeries("pool_2", "풀 2 (임시)", [0.682, 0.679, 0.674, 0.671, 0.668, 0.664, 0.661, 0.658, 0.654, 0.651, 0.648, 0.644], "info"),
    drSeries("pool_3", "풀 3 (임시)", [2.341, 2.388, 2.442, 2.501, 2.564, 2.628, 2.691, 2.758, 2.822, 2.889, 2.954, 3.018], "critical"),
    drSeries("pool_4", "풀 4 (임시)", [1.882, 1.901, 1.918, 1.934, 1.951, 1.962, 1.974, 1.981, 1.988, 1.994, 1.998, 2.004], "caution"),
    drSeries("pool_5", "풀 5 (임시)", [0.944, 0.951, 0.958, 0.962, 0.971, 0.978, 0.984, 0.991, 0.998, 1.004, 1.011, 1.018], "watch"),
  ],
  corpNote: "기업 규모 구분은 외부감사 여부와 자산 규모 기준입니다. 구분 기준은 경영 의사결정 DB 의 신용평가 운영기준을 따릅니다.",
  retailNote: "개인 풀 5종은 확정 전 임시 구분입니다. 풀 정의가 확정되면 동일 화면 구조에 코드만 교체해 반영합니다.",
  evidence: [
    evidence("ev-dr-data", "bank_data", "월별 부도율 집계(기업 규모별 · 개인 풀별)", {
      sourceKind: "calc_run",
      tableRef: "calc.calc_run(DEFAULT_RATE)",
      snippet: "최근 12개월 월별 신규 부도 발생 기준",
      figureId: "dr_corp_micro_latest",
    }),
    evidence("ev-dr-method", "internal_direction", "신용평가모형 모니터링 기준(부도율 산출)", {
      doc: DOC.statMethod,
      relevance: 0.82,
    }),
  ],
};
