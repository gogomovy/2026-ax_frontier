"use client";

import { useMemo } from "react";
import { useGoalState } from "@/components/providers/GoalStateProvider";
import { usePlanState } from "@/components/providers/PlanStateProvider";
import { useSession } from "@/components/providers/SessionProvider";
import { UNIT_LABEL } from "@/lib/format";
import type { CascadeNode, Goal } from "@/lib/types";

const NO_NODES: CascadeNode[] = [];
const NO_GOALS: Goal[] = [];

/**
 * 전파 경로 트리를 현재 상태로 다시 계산한다 (요구사항 PROP-01 ~ PROP-04).
 *
 * 기준은 레이아웃이 서버에서 받은 전파 트리 · 경영목표(session.cascade · session.goals) — 없으면 빈 트리.
 * 그 위에 현재 목표 · 수행방안 처리 상태를 반영한다.
 *
 * 반영 대상
 *  - 종합기획부에서 수정·신설한 경영목표 → 목표 노드 라벨·신규 노드
 *  - 사업부서에서 진행사업으로 등록한 수행방안 → 목표 하위 노드로 편입
 *  - 영업점 참고 토글 → 영업점 노드 노출 여부
 */
export function useCascadeModel(): CascadeNode[] {
  const { overrides, addedGoals } = useGoalState();
  const { inProgressPlans } = usePlanState();
  const session = useSession();
  const CASCADE = session.cascade ?? NO_NODES;
  const GOALS = session.goals ?? NO_GOALS;
  const userOrg = session.menu?.user.org.name ?? "";

  return useMemo(() => {
    /* 1) 목표 노드 라벨을 현재 목표값으로 갱신 */
    const nodes: CascadeNode[] = CASCADE.map((node) => {
      const goal = GOALS.find((g) => g.id === node.id);
      const override = overrides[node.id];
      if (!goal || !override?.targetValue || override.targetValue === goal.targetValue) return { ...node };

      const unit = UNIT_LABEL[goal.unit];
      const decimals = goal.decimals ?? 1;
      // 기존 목표값이 없으면(빈 템플릿) 라벨은 그대로 두고 변경 내용만 덧붙인다
      const before = goal.targetValue != null ? `${goal.targetValue.toFixed(decimals)}${unit}` : null;
      const after = `${override.targetValue.toFixed(decimals)}${unit}`;
      return {
        ...node,
        label: before ? node.label.replace(before, after) : node.label,
        detail: `${node.detail ?? ""} · 목표 변경 ${before ?? "–"} → ${after}`.replace(/^ · /, ""),
      };
    });

    /* 2) 종합기획부에서 신설한 목표 추가 */
    addedGoals.forEach((added) => {
      if (nodes.some((n) => n.id === added.id || n.label === added.title)) return;
      // 담당조직 — 목표에 적힌 조직, 없으면 로그인 사용자 소속
      const org = added.ownerOrg || userOrg || "–";
      nodes.push({
        id: added.id,
        kind: "goal",
        label: added.title,
        detail: `${org} · 신규 확정 · 목표 ${added.targetLabel}`,
        org,
        children: [],
      });
    });

    /* 3) 진행사업으로 등록된 수행방안을 목표 하위에 편입 */
    const attach = (plan: (typeof inProgressPlans)[number]): CascadeNode => ({
      id: plan.id,
      kind: "plan",
      label: plan.title,
      detail: [
        `${plan.ownerOrg} · 진행사업`,
        plan.branchShared ? "영업점 Agent 참고 가능" : "영업점 참고 중단",
        plan.linkedAnalysisLabel ? `연결 분석 ${plan.linkedAnalysisLabel}` : null,
      ]
        .filter(Boolean)
        .join(" · "),
      org: plan.ownerOrg,
      children: plan.branchShared
        ? [
            {
              id: `${plan.id}-branch`,
              kind: "branch_target",
              label: "영업점 가이드로 전파됨",
              detail: `모니터링 지표 ${plan.monitoringMetrics.slice(0, 2).join(" · ") || "미지정"}`,
              org: "전 영업점",
            },
          ]
        : undefined,
    });

    const unmatched: CascadeNode[] = [];
    inProgressPlans.forEach((plan) => {
      const node = attach(plan);
      const parent = plan.relatedGoalId
        ? nodes.find((n) => n.id === plan.relatedGoalId)
        : plan.relatedGoalTitle
          ? nodes.find((n) => n.label.includes(plan.relatedGoalTitle!.replace("(제안) ", "")))
          : undefined;
      if (parent) {
        // 기본 트리에 같은 수행방안이 있으면 현재 상태 노드로 바꾼다(중복 노드 방지)
        parent.children = [...(parent.children ?? []).filter((c) => c.id !== node.id), node];
      } else {
        unmatched.push(node);
      }
    });

    /* 4) 연결 목표가 없는 진행사업도 누락 없이 보여준다 */
    if (unmatched.length > 0) {
      nodes.push({
        id: "plan-unlinked",
        kind: "goal",
        label: "연결 경영목표 없음",
        detail: "상위 목표가 지정되지 않은 진행사업입니다. 목표 연결 후 전파 범위가 확정됩니다.",
        org: "—",
        children: unmatched,
      });
    }

    return nodes;
  }, [overrides, addedGoals, inProgressPlans, CASCADE, GOALS, userOrg]);
}
