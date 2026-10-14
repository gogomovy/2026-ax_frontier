import { describe, expect, it } from "vitest";
import { lastStep, pointCount, prevStepPhrase, revenueRowsOf, sourceLabel, trendPhrase } from "@/lib/loanView";
import type { ComparisonRow, Figure } from "@/lib/types";

const fig = (value: number | null, unit: Figure["unit"] = "KRW_BN", decimals?: number, id = "f"): Figure => ({ id, label: "x", value, unit, decimals, dataOrigin: "simulated" });
const row = (label: string, id: string): ComparisonRow => ({ label, current: fig(1, "KRW_BN", undefined, id), prior: fig(1), diff: fig(0), diffRate: fig(0, "PCT") });
const pts = (...v: (number | null)[]) => v.map((value, i) => ({ label: String(2024 + i), value }));

describe("여신 종합수익 행 — 인덱스 · 라벨이 아니라 수치 id 로", () => {
  it("순서 · 표시 이름이 바뀌어도 찾는다", () => {
    const r = revenueRowsOf([row("가계 이자", "hh_int_cur"), row("총수익", "total_rev_cur"), row("기업 이자", "corp_int_cur"), row("이름 바꾼 NIM", "nim_cur")]);
    expect(r.total?.label).toBe("총수익");
    expect(r.nim?.label).toBe("이름 바꾼 NIM");
    expect(r.corporate?.label).toBe("기업 이자");
    expect(r.household?.label).toBe("가계 이자");
  });
  it("원천 이름 — 계산 추적의 파일 · 표에서", () => {
    const f: Figure = { ...fig(1), calc: { calcId: "c", formulaId: "VALUE", formulaVersion: 1, expression: "", inputs: [{ key: "v", label: "v", value: "1", source: "(202608)2633_상품부문별손익계산서.xlsx!D12" }], executedAt: "" } };
    expect(sourceLabel(f)).toBe("(202608)2633_상품부문별손익계산서");
    expect(sourceLabel(fig(1))).toBeUndefined();
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
