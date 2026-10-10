import { UNIT_LABEL } from "./format";
import type { Goal } from "./types";

/** 클라이언트 상태(수정 반영)를 덮어쓴 경영목표 표시값 */
export interface GoalOverrideLike {
  status?: Goal["status"];
  targetValue?: number;
  updatedAt?: string;
  changeReason?: string;
  creationMode?: Goal["creationMode"];
}

export const GOAL_VERDICT = {
  on_track: { label: "정상 진행", tone: "success" as const },
  below: { label: "목표 하회", tone: "critical" as const },
  near_limit: { label: "한도 근접", tone: "attention" as const },
  breach: { label: "목표 초과", tone: "critical" as const },
};

export function resolveGoal(goal: Goal, override?: GoalOverrideLike) {
  const unit = UNIT_LABEL[goal.unit];
  const decimals = goal.decimals ?? 1;
  const targetValue = override?.targetValue ?? goal.targetValue;
  const changed = override?.targetValue !== undefined && override.targetValue !== goal.targetValue;
  const fmt = (v: number | null | undefined) => (v === null || v === undefined ? "-" : `${v.toFixed(decimals)}${unit}`);
  const original = fmt(goal.targetValue);
  const current = fmt(targetValue);

  return {
    title: changed ? goal.title.replace(original, current) : goal.title,
    targetLabel: current,
    originalLabel: original,
    changed,
    status: override?.status ?? goal.status,
    updatedAt: override?.updatedAt ?? goal.updatedAt,
    creationMode: override?.creationMode ?? goal.creationMode,
    changeReason: override?.changeReason,
    version: goal.version + (changed ? 1 : 0),
    verdict: goal.gapVerdict ? GOAL_VERDICT[goal.gapVerdict] : null,
  };
}
