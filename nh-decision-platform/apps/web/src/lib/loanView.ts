/**
 * 여신 화면 공용 계산 (Phase I · 하드코딩 제거) — 행 순서(인덱스)나 고정 문구 대신 산출물 값에서 찾고 계산한다.
 */
import { formatFigure } from "./format";
import { seriesTrend, stepChange } from "./period";
import type { ComparisonRow, Figure, SeriesPoint } from "./types";

/**
 * 여신 종합수익 행 — 산출물 수치 id(화면 계약: total_rev_cur · nim_cur · corp_int_cur · hh_int_cur)로 찾는다.
 * 표시 이름(라벨)은 관리자가 바꿀 수 있으므로 기준으로 쓰지 않는다 (Phase K). 없으면 undefined
 */
export const REVENUE_ROW_IDS = { total: "total_rev_cur", nim: "nim_cur", corporate: "corp_int_cur", household: "hh_int_cur" } as const;
export function revenueRowsOf(rows: ComparisonRow[] | null | undefined) {
  const list = rows ?? [];
  const by = (id: string) => list.find((r) => r.current?.id === id);
  return { total: by(REVENUE_ROW_IDS.total), nim: by(REVENUE_ROW_IDS.nim), corporate: by(REVENUE_ROW_IDS.corporate), household: by(REVENUE_ROW_IDS.household) };
}

/**
 * 목표 경로 — 전년 동기 잔액 × (1 + 연 목표 증가율 × 경과월 ÷ 12), 경과월 = 1 … n. (전년 동기 자료가 없으면 targetPathSince)
 * 화면 차트 · 표 · 툴팁이 같은 함수를 쓴다(수식은 차트 캡션에 그대로 공개). 입력이 없으면 null.
 */
export function targetPath(base: number | null | undefined, growthPct: number | null | undefined, months: number): number[] | null {
  if (!isNum(base) || !isNum(growthPct) || months <= 0) return null;
  return Array.from({ length: months }, (_, i) => base * (1 + (growthPct / 100) * ((i + 1) / 12)));
}

/** 연월 순번 — '2026.03' · '2026-03-31' · '202603' → 연×12 + 월. 읽을 수 없으면 null */
export function monthIndexOf(label: string | null | undefined): number | null {
  const m = /(\d{4})[.\-/]?(\d{1,2})(?!\d)/.exec(String(label ?? ""));
  if (!m) return null;
  const mo = Number(m[2]);
  return mo >= 1 && mo <= 12 ? Number(m[1]) * 12 + (mo - 1) : null;
}

/**
 * 목표 경로(비교 기준일부터) — 전년 동기 자료가 없어 가장 가까운 기준일과 견줬을 때(Figure.basis):
 * 그 기준일 잔액 × (1 + 연 목표 증가율 × 그 기준일부터 경과월 ÷ 12). 계산 커널이 목표를 비교 기간으로 환산하는 규칙(× 경과월 ÷ 12)과 같아
 * 마지막 달의 경로 값이 환산 목표 판정과 맞는다. 기준일보다 앞선 달은 기준일 잔액. 입력이 없거나 연월을 읽을 수 없으면 null.
 */
export function targetPathSince(base: number | null | undefined, growthPct: number | null | undefined, labels: string[], since: string | null | undefined): number[] | null {
  const s = monthIndexOf(since);
  if (!isNum(base) || !isNum(growthPct) || s === null || labels.length === 0) return null;
  const idx = labels.map(monthIndexOf);
  if (idx.some((i) => i === null)) return null;
  return idx.map((i) => base * (1 + (growthPct / 100) * (Math.max(0, (i as number) - s) / 12)));
}

/** 수치의 원천 이름 — 계산 추적 첫 입력의 원천(파일 · 표)에서 셀 위치 · 확장자를 뺀 것. 없으면 undefined */
export function sourceLabel(figure: Figure | null | undefined): string | undefined {
  const src = figure?.sourceRef ?? figure?.calc?.inputs?.find((i) => i.source)?.source;
  if (!src) return undefined;
  const name = src.split("!")[0].split("/").pop()?.replace(/\.(xlsx|xls|csv|json|pdf)$/i, "").trim();
  return name || undefined;
}

const isNum = (v: number | null | undefined): v is number => typeof v === "number" && Number.isFinite(v);

/** 값이 있는 시점 수 (예: 3개년) */
export function pointCount(points: SeriesPoint[] | null | undefined): number {
  return (points ?? []).filter((p) => isNum(p.value)).length;
}

/** 계열 흐름 문구 — 예) '3개년 연속 축소' · 값이 2개 미만이면 null */
export function trendPhrase(points: SeriesPoint[] | null | undefined): string | null {
  const t = seriesTrend((points ?? []).map((p) => p.value));
  return t ? `${pointCount(points)}개년 ${t}` : null;
}

/**
 * 직전 시점 대비 문구 — 예) '전년 45.90% → 축소'.
 * 직전 값은 현재 수치(figure)의 단위 · 소수 자리로 표기한다. 직전 · 현재 값이 없으면 null.
 */
export function prevStepPhrase(points: SeriesPoint[] | null | undefined, figure: Figure): string | null {
  const vals = (points ?? []).map((p) => p.value).filter(isNum);
  if (vals.length < 2) return null;
  const prev = vals[vals.length - 2];
  const step = stepChange(prev, vals[vals.length - 1]);
  if (!step) return null;
  return `전년 ${formatFigure({ ...figure, value: prev, decimals: figure.decimals ?? 2 })} → ${step}`;
}

/** 직전 대비 방향만 (축소 · 확대 · 유지 · null) */
export function lastStep(points: SeriesPoint[] | null | undefined) {
  const vals = (points ?? []).map((p) => p.value).filter(isNum);
  return vals.length < 2 ? null : stepChange(vals[vals.length - 2], vals[vals.length - 1]);
}
