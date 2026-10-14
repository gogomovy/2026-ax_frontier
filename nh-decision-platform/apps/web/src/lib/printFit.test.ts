import { describe, expect, it } from "vitest";
import { PRINT_MAX_H, PRINT_MAX_W, PRINT_MIN_H, PRINT_MIN_W, PRINT_SAFETY, evalWidthQuery, fitPage, pageRule, printWidth } from "./printFit";

describe("한 장 내보내기 크기 (EXP-01)", () => {
  it("창이 좁아도 데스크톱 배치 폭, 아주 넓어도 상한", () => {
    expect(printWidth(800)).toBe(PRINT_MIN_W);
    expect(printWidth(1440)).toBe(1440);
    expect(printWidth(3840)).toBe(PRINT_MAX_W);
    expect(printWidth(Number.NaN)).toBe(PRINT_MIN_W);
  });

  it("높이는 내용에 여유를 더해 한 쪽으로 — 끝이 다음 쪽으로 넘어가 빈 쪽이 생기지 않게", () => {
    const p = fitPage({ width: 1280, height: 3000 }, 1280);
    expect(p).toEqual({ width: 1280, height: 3000 + PRINT_SAFETY, continues: false });
  });

  it("가로로 넘친 내용이 있으면 쪽 폭을 넓힌다 — 잘림 방지", () => {
    expect(fitPage({ width: 1712.4, height: 1000 }, 1440).width).toBe(1713);
    expect(fitPage({ width: 900, height: 1000 }, 1440).width).toBe(1440);
  });

  it("너무 짧거나 비정상인 내용은 최소 높이, 한도를 넘으면 한도까지 한 쪽 + 이어짐 표시", () => {
    expect(fitPage({ width: 1280, height: 10 }, 1280).height).toBe(PRINT_MIN_H);
    expect(fitPage({ width: Number.NaN, height: Number.NaN }, 1280)).toEqual({ width: 1280, height: PRINT_MIN_H, continues: false });
    const tall = fitPage({ width: 1280, height: PRINT_MAX_H + 5000 }, 1280);
    expect(tall.height).toBe(PRINT_MAX_H);
    expect(tall.continues).toBe(true);
  });

  it("폭 조건 미디어 쿼리를 목표 폭으로 판정 — 인쇄 용지 기본 폭에 끌려 좁은 배치가 되지 않게 (EXP-01)", () => {
    expect(evalWidthQuery("(min-width: 1280px)", 1440)).toBe(true);
    expect(evalWidthQuery("(min-width: 1280px)", 1280)).toBe(true);
    expect(evalWidthQuery("(min-width: 1536px)", 1440)).toBe(false);
    expect(evalWidthQuery("(max-width: 639px)", 1440)).toBe(false);
    expect(evalWidthQuery("(max-width: 1600px)", 1440)).toBe(true);
    expect(evalWidthQuery("(min-width: 768px) and (max-width: 1023px)", 1440)).toBe(false);
    expect(evalWidthQuery("(min-width: 768px) and (max-width: 1999px)", 1440)).toBe(true);
    expect(evalWidthQuery("(width >= 1024px)", 1440)).toBe(true);
    expect(evalWidthQuery("(width < 1024px)", 1440)).toBe(false);
    // 폭 조건이 아니거나 섞인 쿼리는 건드리지 않는다
    for (const q of ["print", "screen", "(prefers-reduced-motion: reduce)", "(hover: hover)", "(min-width: 640px), print", "screen and (min-width: 640px)", "", "(min-resolution: 2dppx)"]) {
      expect(evalWidthQuery(q, 1440), q).toBeNull();
    }
  });

  it("@page 규칙 — 쪽 크기를 px 로, 여백 0(여백은 본문 안쪽 여백)", () => {
    expect(pageRule({ width: 1280, height: 3024 })).toBe("@page { size: 1280px 3024px; margin: 0; }");
  });
});
