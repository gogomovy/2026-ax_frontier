/*
 * 화면 내보내기(PDF) — 한 장 맞춤 크기 계산 (Phase J 후속 · EXP-01~03)
 * DOM 에 의존하지 않는 순수 함수라 vitest(node)로 시험한다. 브라우저 쪽 흐름은 `printPage.ts`.
 *
 * 생각: 용지(A4)에 화면을 줄여 끼우지 않고, "화면 내용 크기 그대로의 한 쪽"을 만든다.
 *  - 폭: 데스크톱 배치가 유지되도록 화면 폭 근처(최소 1280)로 고정한다. 인쇄 때 뷰포트가 용지 폭이 되므로,
 *        쪽 폭을 이만큼 잡으면 lg: · xl: 배치가 그대로 적용된다.
 *  - 높이: 인쇄 배치로 미리 그려 본 내용 높이에 맞춘다 → 잘리지도, 여러 쪽으로 쪼개지지도 않는다.
 */
export const PRINT_MIN_W = 1280;
export const PRINT_MAX_W = 1600;
/** 쪽 높이 상한(px) — 브라우저가 PDF 쪽 크기에 두는 한도(약 200인치 = 19200px)보다 낮게. 넘으면 한도까지 한 쪽, 나머지는 다음 쪽 */
export const PRINT_MAX_H = 14400;
export const PRINT_MIN_H = 480;
/** 소수점 레이아웃 오차로 맨 끝이 다음 쪽으로 넘어가 빈 쪽이 생기지 않게 두는 여유(px) */
export const PRINT_SAFETY = 24;

export interface PageSize {
  width: number;
  height: number;
  /** 내용이 쪽 높이 한도를 넘어 다음 쪽으로 이어진다 */
  continues: boolean;
}

/** 현재 창 폭 → 인쇄 배치 폭. 창이 좁아도 데스크톱 배치(1280)로, 아주 넓어도 1600 까지만 */
export function printWidth(viewportWidth: number): number {
  const w = Number.isFinite(viewportWidth) ? Math.round(viewportWidth) : PRINT_MIN_W;
  return Math.min(PRINT_MAX_W, Math.max(PRINT_MIN_W, w));
}

/**
 * 내용 크기(px) → 쪽 크기.
 * 가로로 넘친 내용이 있으면 쪽 폭을 그만큼 넓혀 잘리지 않게 하고(상한 없음 — 잘림이 더 나쁘다), 높이는 내용에 여유를 더해 맞춘다.
 */
export function fitPage(content: { width: number; height: number }, baseWidth: number): PageSize {
  const width = Math.max(Math.round(baseWidth), Math.ceil(Number.isFinite(content.width) ? content.width : 0));
  const wanted = Math.ceil(Number.isFinite(content.height) ? content.height : 0) + PRINT_SAFETY;
  const height = Math.min(PRINT_MAX_H, Math.max(PRINT_MIN_H, wanted));
  return { width, height, continues: wanted > PRINT_MAX_H };
}

/**
 * 폭 조건 미디어 쿼리(`(min-width: 1280px)` 등)가 폭 `width`(px)에서 참인가.
 * 인쇄에서는 이런 규칙이 `@page` 로 정한 폭이 아니라 용지 기본 폭으로 판정돼 좁은 화면 배치가 된다 —
 * 그래서 인쇄 준비 동안 이 판정으로 규칙을 켜고 꺼서 항상 같은 폭의 배치가 나오게 한다 (EXP-01).
 * 폭 조건만으로 이뤄진 쿼리가 아니면(print · screen · hover · prefers-* · 쉼표 목록 …) null — 건드리지 않는다.
 */
export function evalWidthQuery(mediaText: string, width: number): boolean | null {
  const text = mediaText.trim();
  if (!text || text.includes(",")) return null;
  const parts = text.split(/\s+and\s+/i);
  for (const part of parts) {
    const classic = /^\(\s*(min|max)-width\s*:\s*(-?[\d.]+)px\s*\)$/i.exec(part);
    const range = /^\(\s*width\s*(>=|<=|>|<)\s*(-?[\d.]+)px\s*\)$/i.exec(part);
    let ok: boolean;
    if (classic) ok = classic[1].toLowerCase() === "min" ? width >= Number(classic[2]) : width <= Number(classic[2]);
    else if (range) {
      const n = Number(range[2]);
      ok = range[1] === ">=" ? width >= n : range[1] === "<=" ? width <= n : range[1] === ">" ? width > n : width < n;
    } else return null;
    if (!ok) return false;
  }
  return true;
}

/** `<style>` 에 넣을 @page 규칙 — 여백은 body 안쪽 여백(CSS)으로 준다 */
export function pageRule(p: Pick<PageSize, "width" | "height">): string {
  return `@page { size: ${p.width}px ${p.height}px; margin: 0; }`;
}
