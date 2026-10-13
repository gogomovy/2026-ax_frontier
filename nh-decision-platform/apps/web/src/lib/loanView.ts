/**
 * 여신 화면 공용 계산 (Phase I · 하드코딩 제거) — 행 순서(인덱스)나 고정 문구 대신 산출물 값에서 찾고 계산한다.
 */
import { formatFigure } from "./format";
import { seriesTrend, stepChange } from "./period";
import type { ComparisonRow, Figure, SeriesPoint } from "./types";

/** 여신 종합수익 행 — 라벨로 찾는다(전체 수익 · 이자마진 · 기업 · 가계). 없으면 undefined */
export function revenueRowsOf(rows: ComparisonRow[] | null | undefined) {
  const list = rows ?? [];
  const by = (kw: string) => list.find((r) => r.label.includes(kw));
  return { total: by("전체 수익"), nim: by("이자마진"), corporate: by("기업"), household: by("가계") };
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
