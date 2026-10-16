import { UNIT_LABEL } from "./format";
import type { Goal, Proposal } from "./types";

/** AI 추천값 표기 — 범위면 `7.5% ~ 8.0%`, 단일 값이면 `7.8%`, 방향만이면 문구 */
export function proposalRange(p: Proposal): string {
  const unit = UNIT_LABEL[p.recommendation.unit];
  const dec = p.recommendation.decimals ?? 1;
  const n = (v?: number | null) => (v === undefined || v === null ? "-" : v.toFixed(dec));
  const none = (v?: number | null) => v === undefined || v === null;
  // 자료가 올라와 계산되기 전에는 추천값이 없다 — '- ~ -' 대신 문구로
  if (p.recommendation.mode === "range" && none(p.recommendation.low) && none(p.recommendation.high)) return "산출 전";
  if (p.recommendation.mode === "point" && none(p.recommendation.value)) return "산출 전";
  if (p.recommendation.mode === "range") return `${n(p.recommendation.low)}${unit} ~ ${n(p.recommendation.high)}${unit}`;
  if (p.recommendation.mode === "point") return `${n(p.recommendation.value)}${unit}`;
  return "방향성만 제시";
}

/** 목표 방향에 맞는 꼬리말 (이상 · 이하) */
export function directionSuffix(goal?: Pick<Goal, "direction">): string {
  return goal?.direction === "increase" ? "이상" : goal?.direction === "decrease" ? "이하" : "";
}

/** 클라이언트 상태(수정 반영)를 덮어쓴 경영목표 표시값 */
export interface GoalOverrideLike {
  status?: Goal["status"];
  targetValue?: number;
  /** 서버가 기록한 현재 버전 (되돌리기 · 다시 수정 · 삭제도 새 버전) */
  version?: number;
  updatedAt?: string;
  changeReason?: string;
  creationMode?: Goal["creationMode"];
}

/** 목표 판정 태그 (가이드 G04: 정상 = 무채색, 미달 · 근접 = 주황, 한도 초과 = 빨강) */
export const GOAL_VERDICT = {
  on_track: { label: "정상", tone: "success" as const },
  below: { label: "목표 미달", tone: "attention" as const },
  near_limit: { label: "한도 근접", tone: "attention" as const },
  breach: { label: "한도 초과", tone: "critical" as const },
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
    version: override?.version ?? goal.version + (changed ? 1 : 0),
    verdict: goal.gapVerdict ? GOAL_VERDICT[goal.gapVerdict] : null,
  };
}
