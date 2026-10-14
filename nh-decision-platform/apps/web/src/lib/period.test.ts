import { describe, expect, it } from "vitest";
import { NO_VALUE, baseYear, goalPeriodOptions, periodOf, seriesTrend, stepChange, todayKst } from "@/lib/period";

describe("기간 라벨 — 기준일에서 계산 (Phase I · 하드코딩 제거)", () => {
  it("기준일 → 연월 · 월 · 연도 · 전년 · 전전년 · 일자", () => {
    expect(periodOf("2026-08-31")).toEqual({ ym: "2026.08", month: "8월", year: "2026", prevYm: "2025.08", prev2Ym: "2024.08", ymDate: "2026.08.31" });
  });
  it("시각이 붙은 값 · 연초 월", () => {
    const p = periodOf("2027-01-05T09:00:00+09:00");
    expect(p.ym).toBe("2027.01");
    expect(p.month).toBe("1월");
    expect(p.prevYm).toBe("2026.01");
    expect(p.prev2Ym).toBe("2025.01");
  });
  it.each([undefined, null, "", "2026-13-01", "2026-00-10", "2026-08-00", "20260831", "not-a-date"])("없거나 잘못된 값은 모두 '–': %s", (v) => {
    const p = periodOf(v as string | null | undefined);
    expect(Object.values(p).every((x) => x === NO_VALUE)).toBe(true);
  });
});

describe("기준 연도 · 목표 적용기간 선택지", () => {
  it("기준일에서 남은 기간 — 연간 · 남은 반기 · 남은 분기 · 다음 해", () => {
    expect(baseYear("2026-08-31")).toBe(2026);
    expect(goalPeriodOptions("2026-08-31")).toEqual(["2026 연간", "2026 하반기", "2026.3Q", "2026.4Q", "2027 상반기", "2027 연간"]);
    expect(goalPeriodOptions("2027-02-28")).toEqual(["2027 연간", "2027 상반기", "2027 하반기", "2027.1Q", "2027.2Q", "2027.3Q", "2027.4Q", "2028 상반기", "2028 연간"]);
    expect(goalPeriodOptions("2026-12-31")).toEqual(["2026 연간", "2026 하반기", "2026.4Q", "2027 상반기", "2027 연간"]);
  });
  it("기준일을 모르면 올해로 대신하지 않는다 (Phase K · HC-04)", () => {
    expect(baseYear(null)).toBeNull();
    expect(goalPeriodOptions(undefined)).toEqual([]);
  });
  it("오늘 날짜는 YYYY-MM-DD", () => {
    expect(todayKst()).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });
});

describe("추세 문구 — 계열 값에서 계산", () => {
  it("직전 대비 축소 · 확대 · 유지, 값이 없으면 null", () => {
    expect(stepChange(45.9, 44.1)).toBe("축소");
    expect(stepChange(1, 2)).toBe("확대");
    expect(stepChange(3, 3)).toBe("유지");
    expect(stepChange(null, 3)).toBeNull();
    expect(stepChange(3, undefined)).toBeNull();
    expect(stepChange(Number.NaN, 3)).toBeNull();
  });
  it("단조 감소 · 단조 증가 · 그 밖은 변동", () => {
    expect(seriesTrend([3, 2, 1])).toBe("연속 축소");
    expect(seriesTrend([1, 2, 3])).toBe("연속 확대");
    expect(seriesTrend([1, 3, 2])).toBe("변동");
    expect(seriesTrend([2, 2])).toBe("변동");
  });
  it("빈 값은 건너뛰고, 값이 2개 미만이면 null", () => {
    expect(seriesTrend([3, null, 1])).toBe("연속 축소");
    expect(seriesTrend([1])).toBeNull();
    expect(seriesTrend([null, undefined])).toBeNull();
    expect(seriesTrend([])).toBeNull();
  });
});
