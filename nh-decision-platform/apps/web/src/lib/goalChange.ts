/**
 * 확정한 경영목표 되돌리기 · 다시 수정 · 삭제 — 화면 공통 규칙 (서버 `/state/goals/revert|edit|delete` 와 같은 규칙).
 *  - 사유는 필수 · 최소 글자 수 = [화면 설정 › 기준값 › 제안 사유 최소 글자 수] (서버도 같은 값으로 검사)
 *  - 버전 사슬 = [기준(산출물) 버전, 확정 버전 …] — 서버 `_versions` 와 같다. 이력은 지우지 않고 덧붙이기만 한다
 */
import type { Goal } from "./types";

export interface GoalVersion {
  version: number;
  value: number | null;
  base?: boolean;
}

export interface VersionedOverride {
  status?: Goal["status"];
  targetValue?: number;
  version?: number;
  versions?: { version: number; value: number | null }[];
}

/** 서버가 아직 새 경로를 모를 때(예전 API 이미지) — FastAPI 의 경로 없음(404 "Not Found") · 405 */
export function isMissingRoute(status: number, message: string): boolean {
  return status === 405 || (status === 404 && message.trim() === "Not Found");
}

export const MISSING_ROUTE_MESSAGE = "서버가 아직 이 기능을 지원하지 않아요 — API를 다시 배포해 주세요";

/** 사유 검사 — 통과하면 null, 아니면 안내 문구 */
export function reasonError(reason: string, min: number): string | null {
  const n = reason.trim().length;
  if (n === 0) return "사유를 입력해 주세요";
  if (n < min) return `사유를 ${min}자 이상 입력해 주세요 (지금 ${n}자)`;
  return null;
}

/** 목표값 입력 검사 — ProposalPopup 직접 수정과 같은 기준(빈 값 불가) + 숫자여야 함 */
export function valueError(raw: string): string | null {
  if (!raw.trim()) return "목표값을 입력해 주세요";
  if (!Number.isFinite(Number(raw))) return "숫자로 입력해 주세요";
  return null;
}

export function goalVersions(goal: Pick<Goal, "version" | "targetValue">, override?: VersionedOverride): GoalVersion[] {
  const base: GoalVersion = { version: goal.version, value: goal.targetValue, base: true };
  if (override?.versions?.length) return [base, ...override.versions.map((v) => ({ version: v.version, value: v.value }))];
  const tv = override?.targetValue;
  if (tv !== undefined && tv !== null && tv !== goal.targetValue) return [base, { version: goal.version + 1, value: tv }];
  return [base];
}

/** 기본 되돌리기 대상 — 바로 앞 버전(확정 변경이 '유지'뿐이면 기준 버전) */
export function defaultRevertTarget(goal: Pick<Goal, "version" | "targetValue">, override?: VersionedOverride): GoalVersion {
  const chain = goalVersions(goal, override);
  return chain.length > 1 ? chain[chain.length - 2] : chain[0];
}

/** 되돌릴 확정 변경이 있는지 — 서버에 처리 기록(override)이 있어야 한다 */
export function canRevert(override?: VersionedOverride): boolean {
  return Boolean(override);
}

export function isArchived(override?: { status?: Goal["status"] }): boolean {
  return override?.status === "archived";
}
