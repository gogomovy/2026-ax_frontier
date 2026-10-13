import { describe, expect, it } from "vitest";
import { lastStep, pointCount, prevStepPhrase, revenueRowsOf, trendPhrase } from "@/lib/loanView";
import type { ComparisonRow, Figure } from "@/lib/types";

const fig = (value: number | null, unit: Figure["unit"] = "KRW_BN", decimals?: number): Figure => ({ id: "f", label: "x", value, unit, decimals, dataOrigin: "simulated" });
const row = (label: string): ComparisonRow => ({ label, current: fig(1), prior: fig(1), diff: fig(0), diffRate: fig(0, "PCT") });
const pts = (...v: (number | null)[]) => v.map((value, i) => ({ label: String(2024 + i), value }));

describe("여신 종합수익 행 — 인덱스가 아니라 라벨로", () => {
  it("순서가 바뀌어도 찾는다", () => {
    const r = revenueRowsOf([row("가계자금대출금이자"), row("전체 수익"), row("기업자금대출금이자"), row("여신(일반)부문 이자마진 수익")]);
    expect(r.total?.label).toBe("전체 수익");
    expect(r.nim?.label).toBe("여신(일반)부문 이자마진 수익");
    expect(r.corporate?.label).toBe("기업자금대출금이자");
    expect(r.household?.label).toBe("가계자금대출금이자");
  });
  it("행이 없으면 undefined", () => {
    expect(revenueRowsOf([]).total).toBeUndefined();
    expect(revenueRowsOf(undefined).household).toBeUndefined();
  });
});

describe("추세 문구", () => {
  it("계열 흐름 — 값이 있는 시점 수와 방향", () => {
    expect(trendPhrase(pts(46.4, 45.9, 45.4))).toBe("3개년 연속 축소");
    expect(trendPhrase(pts(1, null, 2))).toBe("2개년 연속 확대");
    expect(trendPhrase(pts(1))).toBeNull();
    expect(trendPhrase([])).toBeNull();
    expect(pointCount(pts(1, null, 3))).toBe(2);
  });
  it("직전 대비 — 현재 수치의 단위 · 소수 자리", () => {
    expect(prevStepPhrase(pts(46.4, 45.9, 45.4), fig(45.4, "PCT", 2))).toBe("전년 45.90% → 축소");
    expect(prevStepPhrase(pts(1.5, 2), fig(2, "PCT"))).toBe("전년 1.50% → 확대");
    expect(prevStepPhrase(pts(45.4), fig(45.4, "PCT", 2))).toBeNull();
    expect(lastStep(pts(3, 3))).toBe("유지");
    expect(lastStep([])).toBeNull();
  });
});
