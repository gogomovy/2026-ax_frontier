import type { ChangeFeed } from "@/lib/types";
import { GENERATED_AT } from "./helpers";

/**
 * 변화 감지 에이전트 결과 예시 (목데이터 모드 전용 · 시뮬레이션).
 * API 모드에서는 워크플로우의 detect_changes 노드가 직전 확정값 대비 유의 변화만 산출물 change_feed 에 쌓는다.
 */
export const CHANGE_FEED: ChangeFeed = {
  updatedAt: GENERATED_AT,
  items: [
    { id: "mock-inc-share", at: GENERATED_AT, workflow: "wf_inclusive_risk", workflowName: "포용금융 신용리스크", kind: "metric", code: "share_now", label: "포용금융 충당금 비중(최근월)", unit: "PCT", decimals: 2, before: 7.97, after: 9.16, delta: 1.19, deltaPct: 14.93, level: "major", direction: "up" },
    { id: "mock-inc-data", at: GENERATED_AT, workflow: "wf_inclusive_risk", workflowName: "포용금융 신용리스크", kind: "data", code: "PROVISION_BY_PRODUCT", label: "7790 상품별 충당금", unit: "CNT", decimals: 0, before: 23, after: 46, delta: 23, deltaPct: 100, level: "major", direction: "up", files: ["(202608)7790_상품별_충당금.xlsx"] },
    { id: "mock-corp-bal", at: GENERATED_AT, workflow: "wf_hq_goal_review", workflowName: "종합기획부 경영목표 검토", kind: "metric", code: "corp_bal", label: "기업자금대출금 잔액(2026.08말)", unit: "KRW_TN", decimals: 2, before: 110.86, after: 115.34, delta: 4.48, deltaPct: 4.04, level: "major", direction: "up" },
    { id: "mock-br-deposit", at: GENERATED_AT, workflow: "wf_branch_kpi", workflowName: "영업점 업적평가 영업 가이드", kind: "metric", code: "br_seg_deposit", label: "수신 평잔", unit: "KRW_BN", decimals: 1, before: 1398.2, after: 1420.6, delta: 22.4, deltaPct: 1.6, level: "minor", direction: "up", scope: { office: "001068" } },
  ],
};
