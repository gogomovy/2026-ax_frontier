import type { CascadeNode, ConstraintCheck, Goal, Proposal, ReviewQueueItem } from "@/lib/types";
import { AS_OF, PASSED_VERIFICATIONS, evidence, fig, figMap, trace, withAlignment } from "./helpers";
import { DOC } from "./knowledge";
import { CORPORATE, HOUSEHOLD, FINANCE_FIGURES } from "./finance";

/* ═══════════════════════════════════════════════════════════════
 * 현재 경영목표 (GOAL-04)
 * ═══════════════════════════════════════════════════════════════ */
export const GOALS: Goal[] = [
  {
    id: "goal-q3-revenue",
    domainCode: "loan",
    subDomain: "revenue",
    title: "3분기 여신 수익 1.75조원 이상",
    targetType: "amount",
    direction: "increase",
    targetValue: 1.75,
    unit: "KRW_TN",
    decimals: 2,
    periodLabel: "2026.3Q",
    status: "active",
    creationMode: "existing",
    updatedAt: "2026-06-30",
    version: 1,
    metricLabel: "여신 수익(분기)",
    actual: fig("g1_actual", "3분기 진행 실적(8월까지)", 1.21, "KRW_TN", { decimals: 2 }),
    gap: fig("g1_gap", "목표까지 잔여", -0.54, "KRW_TN", { decimals: 2 }),
    gapLabel: "목표까지",
    gapVerdict: "on_track",
    history: [
      {
        version: 1,
        at: "2026-06-30",
        actor: "종합기획부 김민수",
        to: "1.75조원 이상",
        reason: "하반기 사업계획 확정에 따른 신규 설정",
        creationMode: "existing",
        evidenceIds: ["ev-goal-bizplan"],
      },
    ],
  },
  {
    id: "goal-annual-revenue",
    domainCode: "loan",
    subDomain: "revenue",
    title: "2026년 여신(일반)부문 이자마진 수익 3.30조원 이상",
    targetType: "amount",
    direction: "increase",
    targetValue: 3.3,
    unit: "KRW_TN",
    decimals: 2,
    periodLabel: "2026 연간",
    status: "active",
    creationMode: "existing",
    updatedAt: "2025-12-27",
    version: 1,
    metricLabel: "여신(일반)부문 이자마진 수익",
    actual: fig("g2_actual", "8월 누계 실적", 2.19, "KRW_TN", { decimals: 2 }),
    gap: fig("g2_gap", "목표 진행률", 66.3, "PCT", { decimals: 1 }),
    gapLabel: "진행률",
    gapSigned: false,
    gapVerdict: "on_track",
    history: [
      {
        version: 1,
        at: "2025-12-27",
        actor: "종합기획부 김민수",
        to: "3.30조원 이상",
        reason: "2026년 사업계획 반영",
        creationMode: "existing",
        evidenceIds: ["ev-goal-bizplan"],
      },
    ],
  },
  {
    id: "goal-corp-growth",
    domainCode: "loan",
    subDomain: "corporate",
    title: "기업여신 전년 대비 +7.0% 이상 확대",
    targetType: "growth",
    direction: "increase",
    targetValue: 7.0,
    unit: "PCT",
    decimals: 1,
    periodLabel: "2026 연간",
    status: "ai_proposed",
    creationMode: "existing",
    updatedAt: "2026-07-03",
    version: 3,
    metricLabel: "기업자금대출금 증가율",
    actual: CORPORATE.growth,
    gap: CORPORATE.gap,
    gapLabel: "목표 이탈",
    gapVerdict: "below",
    history: [
      {
        version: 1,
        at: "2025-12-27",
        actor: "종합기획부 김민수",
        to: "+6.0% 이상",
        reason: "2026년 사업계획 초안",
        creationMode: "existing",
        evidenceIds: ["ev-goal-bizplan"],
      },
      {
        version: 2,
        at: "2026-02-24",
        actor: "종합기획부 김민수",
        from: "+6.0% 이상",
        to: "+6.5% 이상",
        reason: "정부 생산적 금융 공급 확대 방안 발표 반영",
        creationMode: "user_manual",
        evidenceIds: ["ev-corp-policy"],
      },
      {
        version: 3,
        at: "2026-07-03",
        actor: "종합기획부 이수정",
        from: "+6.5% 이상",
        to: "+7.0% 이상",
        reason: "하반기 경영전략회의 기업여신 확대 기조 강화",
        creationMode: "ai_proposed",
        evidenceIds: ["ev-corp-mgmt"],
      },
    ],
  },
  {
    id: "goal-hh-control",
    domainCode: "loan",
    subDomain: "household",
    title: "가계여신 전년 대비 +4.0% 이하 관리",
    targetType: "limit",
    direction: "decrease",
    targetValue: 4.0,
    unit: "PCT",
    decimals: 1,
    periodLabel: "2026 연간",
    status: "ai_proposed",
    creationMode: "existing",
    updatedAt: "2026-03-10",
    version: 2,
    metricLabel: "가계자금대출금 증가율",
    actual: HOUSEHOLD.growth,
    gap: HOUSEHOLD.gap,
    gapLabel: "관리목표 초과",
    gapVerdict: "breach",
    history: [
      {
        version: 1,
        at: "2025-12-27",
        actor: "종합기획부 김민수",
        to: "+4.5% 이하",
        reason: "2026년 사업계획 반영",
        creationMode: "existing",
        evidenceIds: ["ev-goal-bizplan"],
      },
      {
        version: 2,
        at: "2026-03-10",
        actor: "종합기획부 이수정",
        from: "+4.5% 이하",
        to: "+4.0% 이하",
        reason: "2026년 가계부채 관리방안 발표 반영",
        creationMode: "user_manual",
        evidenceIds: ["ev-hh-policy"],
      },
    ],
  },
  {
    id: "goal-hh-balance",
    domainCode: "loan",
    subDomain: "household",
    title: "가계여신 잔액 100.00조원 이하 관리",
    targetType: "limit",
    direction: "maintain",
    targetValue: 100.0,
    unit: "KRW_TN",
    decimals: 2,
    periodLabel: "2026 연간",
    status: "active",
    creationMode: "existing",
    updatedAt: "2025-12-27",
    version: 1,
    metricLabel: "가계자금대출금 잔액",
    actual: HOUSEHOLD.balance,
    gap: fig("g5_gap", "한도 여유", 0.76, "KRW_TN", {
      decimals: 2,
      calc: trace("calc-hh-balance-headroom", "CAP_HEADROOM", "관리 한도 − 현재 잔액", [
        { key: "cap_value", label: "잔액 관리 한도", value: "100,000,000", unit: "백만원", source: "2026년 사업계획(여신 부문).pdf p.11" },
        { key: "proposed_value", label: "2026.08말 잔액", value: "99,240,000", unit: "백만원", source: "(202608)2020 과목별 월별 여신현황.xlsx!Sheet1!J9" },
      ]),
    }),
    gapVerdict: "near_limit",
  },
  {
    id: "goal-grade-5c",
    domainCode: "loan",
    subDomain: "quality",
    title: "신용등급 5C 이상 차주 비중 62%대 유지",
    targetType: "ratio",
    direction: "maintain",
    targetValue: 62.0,
    unit: "PCT",
    decimals: 1,
    periodLabel: "2026 연간",
    status: "active",
    creationMode: "existing",
    updatedAt: "2025-12-27",
    version: 1,
    metricLabel: "5C 이상 차주 비중",
    actual: fig("g6_actual", "2026.08말 실적", 61.4, "PCT", { decimals: 1 }),
    gap: fig("g6_gap", "목표 대비 차이", -0.6, "PP", { decimals: 1 }),
    gapLabel: "목표 대비",
    gapVerdict: "near_limit",
  },
];

/* ═══════════════════════════════════════════════════════════════
 * 제약 검증 (AST-02/03, GOAL-15)
 * ═══════════════════════════════════════════════════════════════ */
const corpConstraints: ConstraintCheck[] = [
  {
    label: "지주 총자산 최대 증가율 환산 상한",
    ceiling: fig("cc_corp_ceiling", "환산 상한", 8.0, "PCT", { decimals: 1, dataOrigin: "actual" }),
    proposed: fig("cc_corp_proposed", "추천 상한", 8.0, "PCT", { decimals: 1 }),
    headroom: fig("cc_corp_headroom", "여유", 0.0, "PP", {
      decimals: 1,
      calc: trace("calc-corp-ceiling", "CAP_HEADROOM", "한도 − 제안값", [
        { key: "cap_asset", label: "지주 총자산 최대 증가율", value: "8.2", unit: "%", source: "2025년 RWA 한도 및 총자산 최대 성장률 알림.pdf p.1" },
        { key: "safety_margin", label: "안전 마진(설정값)", value: "0.2", unit: "%p", source: "rule_engine.settings.safety_margin" },
        { key: "ceiling", label: "환산 상한", value: "8.0", unit: "%", source: "calc-corp-ceiling" },
      ]),
    }),
    passed: true,
    basisDoc: DOC.rwaLimit,
  },
  {
    label: "기업 부문 신용RWA 한도 소진율",
    ceiling: fig("cc_rwa_corp_ceiling", "한도", 100.0, "PCT", { decimals: 1, dataOrigin: "actual" }),
    proposed: fig("cc_rwa_corp_proposed", "제안 반영 후 소진율", 86.4, "PCT", { decimals: 1 }),
    headroom: fig("cc_rwa_corp_headroom", "여유", 13.6, "PP", { decimals: 1 }),
    passed: true,
    basisDoc: DOC.rwaDeptAlloc,
  },
];

const hhConstraints: ConstraintCheck[] = [
  {
    label: "가계여신 잔액 관리 한도",
    ceiling: fig("cc_hh_ceiling", "관리 한도", 100.0, "KRW_TN", { decimals: 2, dataOrigin: "actual" }),
    proposed: fig("cc_hh_proposed", "제안 반영 시 연말 추정 잔액", 99.86, "KRW_TN", { decimals: 2 }),
    headroom: fig("cc_hh_headroom", "여유", 0.14, "KRW_TN", { decimals: 2 }),
    passed: true,
    basisDoc: DOC.bizPlan,
  },
  {
    label: "가계 부문 신용RWA 한도 소진율",
    ceiling: fig("cc_rwa_hh_ceiling", "한도", 100.0, "PCT", { decimals: 1, dataOrigin: "actual" }),
    proposed: fig("cc_rwa_hh_proposed", "제안 반영 후 소진율", 94.1, "PCT", { decimals: 1 }),
    headroom: fig("cc_rwa_hh_headroom", "여유", 5.9, "PP", { decimals: 1 }),
    passed: true,
    basisDoc: DOC.rwaDeptAlloc,
  },
];

/* ═══════════════════════════════════════════════════════════════
 * Agent 제안 (GOAL-06~12, AST-09/10)
 * ═══════════════════════════════════════════════════════════════ */
export const PROPOSALS: Proposal[] = [
  {
    id: "prop-corp-growth",
    kind: "goal_modify",
    targetGoalId: "goal-corp-growth",
    domainCode: "loan",
    title: "기업여신 확대 목표 상향 검토",
    judgement:
      "기업여신은 현재 [[fig:corp_growth]]로 목표 [[fig:corp_goal]]을 [[fig:corp_gap]] 하회하고 있습니다. 동시에 정부 정책과 내부 경영 의사결정은 모두 기업여신 확대 기조를 유지·강화하는 방향이며, 규모 대비 수익률도 기업이 가계보다 [[fig:ros_gap]] 우위입니다. 기업여신 구성비가 3개년 연속 축소([[fig:corp_share_delta]])된 점을 함께 고려하면, 목표 수준 자체를 상향하고 실행 강도를 높이는 검토가 필요합니다.",
    recommendation: {
      mode: "range",
      low: 7.5,
      high: 8.0,
      unit: "PCT",
      decimals: 1,
      currentValue: 7.0,
      text: "기존 +7.0% 대비 상향 검토. 추천범위 +7.5% ~ +8.0%",
    },
    ruleId: "GOAL_RANGE_REC / POLICY_ALIGNED_EXPANSION v1",
    ruleInputs: [
      { label: "① 지주 총자산 최대 증가율", value: "8.2%", source: "2025년 RWA 한도 및 총자산 최대 성장률 알림.pdf p.1" },
      { label: "① 안전 마진(설정값)", value: "0.2%p", source: "rule_engine.settings.safety_margin" },
      { label: "① 환산 상한(ceiling)", value: "8.0%", source: "calc-corp-ceiling" },
      { label: "② 규모 대비 수익률 격차(기업−가계)", value: "+0.028%p", source: "calc-ros-corp / calc-ros-hh" },
      { label: "③ 기조(정책·의사결정)", value: "기업여신 확대(expand)", source: "know.policy_theme(corp_loan_expansion).stance" },
      { label: "④ 기존 목표", value: "+7.0%", source: "goal.goal_version(goal-corp-growth, v3)" },
      { label: "④ 기조 강화 시 상향 폭(설정값)", value: "+0.5 ~ +1.0%p", source: "rule_engine.rules.POLICY_ALIGNED_EXPANSION.delta" },
      { label: "⑤ 최종 추천범위", value: "+7.5% ~ +8.0% (상한 clamp 적용)", source: "calc-goal-range-corp" },
    ],
    figures: figMap(
      FINANCE_FIGURES.corp_growth,
      FINANCE_FIGURES.corp_goal,
      FINANCE_FIGURES.corp_gap,
      FINANCE_FIGURES.ros_gap,
      FINANCE_FIGURES.corp_share_delta,
    ),
    evidence: [
      evidence("ev-prop-corp-data", "bank_data", "기업여신 실적·구성비·수익률(3개년)", {
        sourceKind: "calc_run",
        tableRef: "calc.calc_run(GROWTH_RATE, SHARE, RETURN_ON_SCALE)",
        snippet: "증가율 4.04% · 구성비 53.75%(2024년 대비 −0.91%p) · 규모 대비 수익률 0.945%",
        figureId: "corp_growth",
      }),
      evidence("ev-prop-corp-policy", "external_policy", "생산적 금융 공급 확대 및 기업금융 활성화 방안", {
        doc: DOC.corpLoanPolicy,
        relevance: 0.88,
        snippet: "생산적 부문에 대한 기업여신 공급 확대를 지속 추진한다는 정책 방향.",
      }),
      evidence("ev-prop-corp-mgmt", "internal_direction", "2026년 하반기 경영전략회의 결과", {
        doc: DOC.stratMeeting,
        relevance: 0.93,
        snippet: "기업여신 확대 기조 유지, 하반기 취급 목표 상향 검토 지시.",
      }),
      evidence("ev-prop-corp-limit", "internal_direction", "지주 총자산 최대 증가율 한도", {
        doc: DOC.rwaLimit,
        relevance: 0.9,
        snippet: "은행 총자산 최대 증가율 8.2% — 목표는 한도 이내에서 설정한다.",
      }),
    ],
    constraintChecks: corpConstraints,
    alignment: {
      verdict: "aligned",
      matched: [
        "정부정책 DB — 생산적 금융 공급 확대 방안(기업여신 확대)",
        "경영 의사결정 DB — 2026년 하반기 경영전략회의(기업여신 확대)",
        "종합기획부 경영계획 — 2026년 사업계획(여신 부문)",
      ],
      conflicts: [],
    },
    verifications: withAlignment([
      ...PASSED_VERIFICATIONS,
      { checkCode: "goal_consistency", passed: true, detail: "다른 활성 목표·상위 제약과 충돌 없음" },
    ]),
    asOf: AS_OF,
  },
  {
    id: "prop-hh-control",
    kind: "goal_modify",
    targetGoalId: "goal-hh-control",
    domainCode: "loan",
    title: "가계여신 관리목표 강화 검토",
    judgement:
      "가계여신 증가율은 [[fig:hh_growth]]로 관리목표 [[fig:hh_goal]] 이하를 [[fig:hh_gap]] 초과했습니다. 잔액 기준으로도 관리 한도 100.00조원의 99.2%를 소진했고, 가계 부문 신용RWA 소진율은 92.3%입니다. 정부 가계부채 관리 기조와 내부 경영 의사결정 모두 증가율 관리 방향이므로, 관리목표 수준을 낮추고 월별 취급 한도 관리를 강화하는 검토가 필요합니다.",
    recommendation: {
      mode: "range",
      low: 3.0,
      high: 3.5,
      unit: "PCT",
      decimals: 1,
      currentValue: 4.0,
      text: "기존 +4.0% 이하 대비 하향 검토. 추천범위 +3.0% ~ +3.5% 이하",
    },
    ruleId: "GOAL_RANGE_REC / HOUSEHOLD_CONTROL_TIGHTEN v1",
    ruleInputs: [
      { label: "① 잔액 관리 한도", value: "100.00조원", source: "2026년 사업계획(여신 부문).pdf p.11" },
      { label: "① 현재 잔액 / 소진율", value: "99.24조원 / 99.2%", source: "(202608)2020 과목별 월별 여신현황.xlsx" },
      { label: "① 가계 신용RWA 소진율", value: "92.3%", source: "2026년 하반기 부서별 신용RWA 한도 배분 알림.pdf p.2" },
      { label: "② 규모 대비 수익률", value: "0.917%(기업 대비 −0.028%p)", source: "calc-ros-hh" },
      { label: "③ 기조(정책·의사결정)", value: "가계여신 증가율 관리(control)", source: "know.policy_theme(household_loan_control).stance" },
      { label: "④ 기존 목표", value: "+4.0% 이하", source: "goal.goal_version(goal-hh-control, v2)" },
      { label: "⑤ 최종 추천범위", value: "+3.0% ~ +3.5% 이하", source: "calc-goal-range-hh" },
    ],
    figures: figMap(
      FINANCE_FIGURES.hh_growth,
      FINANCE_FIGURES.hh_goal,
      FINANCE_FIGURES.hh_gap,
      FINANCE_FIGURES.ros_hh,
    ),
    evidence: [
      evidence("ev-prop-hh-data", "bank_data", "가계여신 실적·잔액 소진율·RWA 소진율", {
        sourceKind: "calc_run",
        tableRef: "calc.calc_run(GROWTH_RATE, CAP_HEADROOM)",
        snippet: "증가율 6.50% · 잔액 99.24조원(한도 대비 99.2%) · 가계 RWA 소진율 92.3%",
        figureId: "hh_growth",
      }),
      evidence("ev-prop-hh-policy", "external_policy", "가계부채 관리방안(2026년)", {
        doc: DOC.householdPolicy,
        relevance: 0.91,
        snippet: "가계대출 증가율을 명목 성장률 이내로 관리하도록 요구.",
      }),
      evidence("ev-prop-hh-mgmt", "internal_direction", "2026년 하반기 경영전략회의 결과", {
        doc: DOC.stratMeeting,
        relevance: 0.87,
        snippet: "가계여신은 증가율 관리 기조를 유지하고 취급 기준을 재점검한다.",
      }),
    ],
    constraintChecks: hhConstraints,
    alignment: {
      verdict: "aligned",
      matched: [
        "정부정책 DB — 가계부채 관리방안(2026년)",
        "경영 의사결정 DB — 2026년 하반기 경영전략회의",
        "종합기획부 경영계획 — 잔액 100조원 이하 관리",
      ],
      conflicts: [],
    },
    verifications: withAlignment([
      ...PASSED_VERIFICATIONS,
      { checkCode: "goal_consistency", passed: true, detail: "기업여신 확대 목표와 상충하지 않음(부문 분리)" },
    ]),
    asOf: AS_OF,
  },
  {
    id: "prop-inclusive-new",
    kind: "goal_new",
    domainCode: "loan",
    title: "신규 경영목표 제안 — 포용금융 공급 확대",
    judgement:
      "정부의 포용금융 확대 기조와 지주 성과평가 기준(생산적·포용적 금융 부문 배점 반영)을 고려할 때, 현재 여신 경영목표에는 포용금융 공급에 대한 별도 관리목표가 없습니다. 당행 개인여신 중 중·저신용자 비중은 [[fig:mid_low_share]]로 타행 평균 [[fig:peer_share]] 대비 낮은 수준이며, 중·저신용자 여신 공급액은 [[fig:mid_low_supply]]으로 전년 동기 대비 [[fig:mid_low_growth]] 증가했습니다. 신규 관리목표 설정을 검토할 필요가 있습니다.",
    recommendation: {
      mode: "range",
      low: 3.1,
      high: 3.3,
      unit: "KRW_TN",
      decimals: 1,
      text: "중·저신용자 여신 공급액 2026년 3.1조 ~ 3.3조원 이상 (병행 지표: 개인여신 중 중·저신용자 비중 18.0% 이상)",
    },
    ruleId: "INCLUSIVE_SUPPLY_BASELINE v1",
    ruleInputs: [
      { label: "① 8월 누계 공급액", value: "2.64조원", source: "fact.provision_by_product / 여신 공급 집계" },
      { label: "① 연환산(8→12개월)", value: "3.96조원", source: "calc-inclusive-annualize" },
      { label: "② 전년 실적", value: "3.02조원", source: "2025년 실적" },
      { label: "③ 지주 성과평가 배점", value: "포용금융 1.3점(연도말 평가 50%)", source: "(붙임) 2026년도 생산적 포용적 금융 부문 자회사 성과평가 방안.pdf p.1" },
      { label: "④ 추천 하한", value: "전년 실적 × 1.03 = 3.11조원", source: "rule_engine.rules.INCLUSIVE_SUPPLY_BASELINE" },
      { label: "④ 추천 상한", value: "전년 실적 × 1.09 = 3.29조원", source: "rule_engine.rules.INCLUSIVE_SUPPLY_BASELINE" },
      { label: "⑤ 리스크 제약", value: "충당금 비중 상승 국면 → 상한 보수적 적용", source: "agentic.finding(inclusive-provision-share)" },
    ],
    figures: figMap(
      fig("mid_low_share", "개인여신 중 중·저신용자 비중", 15.8, "PCT", { decimals: 1 }),
      fig("peer_share", "타행 평균 비중(참고)", 17.2, "PCT", { decimals: 1 }),
      fig("mid_low_supply", "중·저신용자 여신 공급액(8월 누계)", 2.64, "KRW_TN", { decimals: 2 }),
      fig("mid_low_growth", "공급액 증가율(전년 동기 대비)", 14.3, "PCT", {
        decimals: 1,
        calc: trace("calc-inclusive-supply-growth", "GROWTH_RATE", "(당기 − 전기) / |전기| × 100", [
          { key: "v0", label: "2025.08 누계 공급액", value: "2,310,000", unit: "백만원", source: "(202508) 여신 공급 집계" },
          { key: "v1", label: "2026.08 누계 공급액", value: "2,640,000", unit: "백만원", source: "(202608) 여신 공급 집계" },
        ]),
      }),
    ),
    evidence: [
      evidence("ev-prop-inc-data", "bank_data", "중·저신용자 여신 공급 현황 및 신용등급 분포", {
        sourceKind: "metric_value",
        tableRef: "fact.provision_by_product / 개인여신 등급 분포",
        snippet: "공급액 2.64조원(8월 누계, +14.3%) · 개인여신 중 비중 15.8% · 타행 평균 17.2%(참고)",
        figureId: "mid_low_supply",
      }),
      evidence("ev-prop-inc-policy", "external_policy", "포용금융 확대방안(금융위원회)", {
        doc: DOC.inclusivePolicy,
        relevance: 0.94,
        snippet: "서민·취약계층에 대한 금융공급 확대와 공급 목표의 명시적 설정을 요구.",
      }),
      evidence("ev-prop-inc-news", "external_policy", "금융당국, 서민금융 공급 목표 상향 주문(보조자료)", {
        doc: DOC.newsInclusive,
        relevance: 0.61,
        snippet: "공식 자료를 보조하는 참고 기사. 판단의 주된 근거로는 사용하지 않았습니다.",
      }),
      evidence("ev-prop-inc-mgmt", "internal_direction", "지주 성과평가 방안 — 포용금융 배점 및 실적 인정 기준", {
        doc: DOC.groupPerfEval,
        relevance: 0.92,
        snippet: "포용금융 추진 배점 1.3점, 은행 해당 (취약계층) 상품 기준으로 실적을 인정.",
      }),
      evidence("ev-prop-inc-strat", "internal_direction", "2026년 하반기 경영전략회의 — 포용금융 확대", {
        doc: DOC.stratMeeting,
        relevance: 0.86,
        snippet: "포용금융 대상 상품 적극 추진을 하반기 과제로 포함.",
      }),
    ],
    constraintChecks: [
      {
        label: "가계 부문 신용RWA 한도 소진율(포용금융 포함)",
        ceiling: fig("cc_inc_ceiling", "한도", 100.0, "PCT", { decimals: 1, dataOrigin: "actual" }),
        proposed: fig("cc_inc_proposed", "제안 반영 후 소진율", 96.2, "PCT", { decimals: 1 }),
        headroom: fig("cc_inc_headroom", "여유", 3.8, "PP", { decimals: 1 }),
        passed: true,
        basisDoc: DOC.rwaDeptAlloc,
      },
    ],
    alignment: {
      verdict: "aligned",
      matched: [
        "정부정책 DB — 포용금융 확대방안",
        "경영 의사결정 DB — 포용금융 대상 상품 운영기준 / 성과평가 방안",
        "종합기획부 경영계획 — 포용금융 확대",
      ],
      conflicts: [],
    },
    verifications: withAlignment([
      ...PASSED_VERIFICATIONS,
      { checkCode: "goal_consistency", passed: true, detail: "가계여신 관리목표와 병행 가능(대상 상품 한정)" },
    ]),
    asOf: AS_OF,
  },
];

/* ═══════════════════════════════════════════════════════════════
 * 경영목표 검토 필요사항 (DASH-05 / GOAL-17)
 * ═══════════════════════════════════════════════════════════════ */
export const REVIEW_QUEUE: ReviewQueueItem[] = [
  {
    id: "rq-1",
    title: "기업여신 성장목표 미달 (−2.96%p)",
    sourceKind: "attention",
    sourceLabel: "AI 주요 Attention",
    domainCode: "loan",
    registeredAt: "2026-09-08",
  },
  {
    id: "rq-2",
    title: "가계여신 관리 강화 필요 (잔액 한도 99.2% 소진)",
    sourceKind: "attention",
    sourceLabel: "AI 주요 Attention",
    domainCode: "loan",
    registeredAt: "2026-09-08",
  },
  {
    id: "rq-3",
    title: "정부 포용금융 확대 정책 발표에 따른 목표 신설 검토",
    sourceKind: "agent_scan",
    sourceLabel: "goal_review_scan 일배치",
    domainCode: "loan",
    registeredAt: "2026-09-12",
  },
  {
    id: "rq-4",
    title: "포용금융 확대에 따른 충당금 비중 상승 — 신용리스크관리부 보고",
    sourceKind: "report_request",
    sourceLabel: "확인·보고 요청",
    domainCode: "loan",
    registeredAt: "2026-09-15",
  },
];

/* ═══════════════════════════════════════════════════════════════
 * 전파 트리 (PROP-03)
 * ═══════════════════════════════════════════════════════════════ */
export const CASCADE: CascadeNode[] = [
  {
    id: "goal-corp-growth",
    kind: "goal",
    label: "기업여신 전년 대비 +7.0% 이상 확대",
    detail: "종합기획부 · 2026 연간 · v3",
    org: "종합기획부",
    children: [
      {
        id: "plan-corp-expand",
        kind: "plan",
        label: "기업여신 확대 실행방안(하반기)",
        detail: "우량 중소기업 신규 발굴, 정책자금 연계 취급 확대",
        org: "여신관리부",
        children: [
          {
            id: "bt-corp-metro1",
            kind: "branch_target",
            label: "수도권1지역본부 — 기업여신 신규 취급 1.24조원",
            detail: "가이드: 5C 이상 차주 중심, 정책자금 연계 우선",
            org: "수도권1지역본부",
          },
          {
            id: "bt-corp-central",
            kind: "branch_target",
            label: "중부지역본부 — 기업여신 신규 취급 0.86조원",
            org: "중부지역본부",
          },
        ],
      },
    ],
  },
  {
    id: "goal-hh-control",
    kind: "goal",
    label: "가계여신 전년 대비 +4.0% 이하 관리",
    detail: "종합기획부 · 2026 연간 · v2",
    org: "종합기획부",
    children: [
      {
        id: "plan-hh-control",
        kind: "plan",
        label: "가계여신 증가율 관리 강화방안",
        detail: "월별 취급 한도 배분, 고DSR 구간 취급 기준 강화",
        org: "여신관리부",
        children: [
          {
            id: "bt-hh-metro1",
            kind: "branch_target",
            label: "수도권1지역본부 — 가계여신 월 취급 한도 2,400억원",
            detail: "가이드: 잔액 한도 소진율 99.2% — 신규 취급 사전승인",
            org: "수도권1지역본부",
          },
        ],
      },
    ],
  },
  {
    id: "goal-inclusive-new",
    kind: "goal",
    label: "(제안) 포용금융 공급 확대",
    detail: "AI 제안 · 확정 전",
    org: "종합기획부",
    children: [
      {
        id: "plan-inclusive-risk",
        kind: "plan",
        label: "포용금융 확대에 따른 신용리스크 중점관리방안",
        detail: "충당금 비중 상승 국면 — 해당 풀 연체 발생·연체율 모니터링",
        org: "신용리스크관리부",
        children: [
          {
            id: "bt-inclusive-metro1",
            kind: "branch_target",
            label: "수도권1지역본부 — 포용금융 상품 취급 후 3개월 연체 모니터링",
            org: "수도권1지역본부",
          },
        ],
      },
    ],
  },
];
