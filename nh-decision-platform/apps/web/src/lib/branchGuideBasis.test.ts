import { describe, expect, it } from "vitest";
import { guideBasis, MAX_CHIPS } from "./branchGuideBasis";
import type { Figure, ReportDoc } from "./types";

const fig = (id: string, label: string, value: number): Figure => ({ id, label, value, unit: "NONE", decimals: 2, dataOrigin: "unknown" });
const doc = (figures: Record<string, Figure>, table: object): ReportDoc => ({ figures, sections: [{ id: "s", heading: "s", level: 2, blocks: [{ type: "table", table }] }] }) as unknown as ReportDoc;

describe("영업점 가점 확보 방안 — 근거 펼침", () => {
  const figures = { br_avg_grade: fig("br_avg_grade", "지점 평균 신용등급(대출잔액 가중, 1~16)", 8.39), bank_avg_grade: fig("bank_avg_grade", "전행 평균 신용등급(대출잔액 가중, 1~16)", 6.16) };
  const summary = "신용등급 가중 실적으로 평가 — 지점 평균 등급 [[fig:br_avg_grade]]단계(전행 [[fig:bank_avg_grade]]단계)";
  it("지점 vs 전행 비교 + 후보 기업 알약 (상한 넘으면 +N)", () => {
    const rows = Array.from({ length: MAX_CHIPS + 2 }, (_, i) => ({ corp: `기업${i}(주)`, grade: "2A" }));
    const b = guideBasis({ summary }, doc(figures, { caption: "마케팅 후보 기업 — 본부 추천", columns: [{ key: "corp", label: "기업명" }, { key: "grade", label: "등급" }], rows }));
    expect(b?.compare?.label).toBe("평균 신용등급(대출잔액 가중, 1~16)");
    expect(b?.compare?.ours.value).toBe(8.39);
    expect(b?.compare?.bank.value).toBe(6.16);
    expect(b?.chips?.title).toBe(`마케팅 후보 기업 ${MAX_CHIPS + 2}곳`);
    expect(b?.chips?.items[0]).toBe("기업0 2A");
    expect(b?.chips?.items).toHaveLength(MAX_CHIPS);
    expect(b?.chips?.overflow).toBe(2);
  });
  it("서민금융 인정 Pool → 대상 상품", () => {
    const b = guideBasis({ summary: "지점 비중" }, doc({}, { columns: [{ key: "pool", label: "Pool" }, { key: "name", label: "Pool 명" }, { key: "seomin", label: "서민금융" }], rows: [{ pool: "P07", name: "NH새희망홀씨대출", seomin: "인정" }, { pool: "P08", name: "햇살론", seomin: "-" }] }));
    expect(b?.compare).toBeNull();
    expect(b?.chips).toEqual({ title: "대상 상품", items: ["NH새희망홀씨대출"], overflow: 0, unit: "개" });
  });
  it("보고서가 없으면 null", () => {
    expect(guideBasis({ summary }, null)).toBeNull();
  });
});
