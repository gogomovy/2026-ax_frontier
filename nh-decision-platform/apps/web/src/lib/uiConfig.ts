/**
 * 화면 설정 (Phase K · 요구사항 §27 HC-01~03 · Q148~Q151) — 판정 구간 · 기준값 · 목표 역할 · 업무 영역 · 예시 질문 · 알림.
 * 값은 서버(`/me/menu.config` ← 관리자 [화면 설정] `ui.*`)에서만 온다. 화면 코드에는 기본값을 두지 않는다 —
 * 설정이 없으면(로그인 전 · 이전 서버) 판정하지 않고 '자료 없음'처럼 중립으로 둔다.
 */
import type { BranchOfficeList } from "./types";

export type Tone = "neutral" | "info" | "positive" | "attention" | "critical";
export interface Band {
  /** 이 값 미만이면 이 구간 — 마지막 구간은 null(그 이상 전부) */
  max: number | null;
  label: string;
  tone: Tone;
}
export type BandKey = "limitUsage" | "rwaUsage" | "targetProgress" | "evidenceRelevance";
export type ThresholdKey = "planPaceTolerancePp" | "headroomAlert" | "shareReferencePct" | "proposalReasonMin";
export type GoalRole = "bankRevenue" | "corpGrowth" | "hhLimit" | "hhControl";
export type ScopeKindCfg = "hq" | "dept" | "branch";

export interface ScopeUnitCfg {
  /** 조직 코드 — 영업점 묶음처럼 조직이 없으면 null */
  code: string | null;
  name: string;
  /** 메뉴 묶음(section) 이름 */
  section: string;
  /** 첫 화면 주소 — 화면이 없으면 null(준비 중) */
  home: string | null;
  available: boolean;
}

export interface UiConfig {
  bands: Partial<Record<BandKey, Band[]>>;
  thresholds: Partial<Record<ThresholdKey, number>>;
  goalRoles: Partial<Record<GoalRole, string | null>>;
  examples: { assist?: { q: string; hint: string }[] };
  notices: { countKey: string; label: string; fallback?: boolean }[];
  issueOrder: string[];
  /** 표시 이름 — subDomain: 하위 영역 코드 → 이름 */
  labels: { subDomain?: Record<string, string>; subDomainHref?: Record<string, string> };
  scopes: Partial<Record<ScopeKindCfg, { label: string; units: ScopeUnitCfg[] }>>;
  ownerOrgs: string[];
  offices: BranchOfficeList;
}

export const EMPTY_CONFIG: UiConfig = {
  bands: {},
  thresholds: {},
  goalRoles: {},
  examples: {},
  notices: [],
  issueOrder: [],
  labels: {},
  scopes: {},
  ownerOrgs: [],
  offices: { offices: [], default: null },
};

/** 값이 속한 구간 — 값이나 구간이 없으면 null(판정하지 않음) */
export function bandOf(value: number | null | undefined, bands: Band[] | undefined): Band | null {
  if (typeof value !== "number" || !Number.isFinite(value) || !bands?.length) return null;
  return bands.find((b) => b.max === null || value < b.max) ?? bands[bands.length - 1];
}

/** 역할로 지정된 목표 — 지정이 없거나 목표가 없으면 undefined */
export function goalByRole<T extends { id: string }>(goals: T[], cfg: UiConfig, role: GoalRole): T | undefined {
  const id = cfg.goalRoles[role];
  return id ? goals.find((g) => g.id === id) : undefined;
}

/** 기준값 — 설정이 없으면 null(그 판정 · 강조를 하지 않음) */
export function threshold(cfg: UiConfig, key: ThresholdKey): number | null {
  const v = cfg.thresholds[key];
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

/** 구간 색 → 화면 요소 */
export const TONE_BADGE: Record<Tone, "neutral" | "info" | "success" | "attention" | "critical"> = {
  neutral: "neutral",
  info: "info",
  positive: "success",
  attention: "attention",
  critical: "critical",
};
export const TONE_BAR: Record<Tone, string> = {
  neutral: "bg-primary",
  info: "bg-primary",
  positive: "bg-success",
  attention: "bg-attention",
  critical: "bg-critical",
};
export const TONE_GAUGE: Record<Tone, "primary" | "warning" | "danger"> = {
  neutral: "primary",
  info: "primary",
  positive: "primary",
  attention: "warning",
  critical: "danger",
};
export const TONE_PROGRESS: Record<Tone, "primary" | "success" | "attention" | "critical"> = {
  neutral: "primary",
  info: "primary",
  positive: "success",
  attention: "attention",
  critical: "critical",
};
