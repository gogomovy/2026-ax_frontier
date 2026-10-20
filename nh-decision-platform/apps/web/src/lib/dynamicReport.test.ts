import { describe, expect, it } from "vitest";
import { barRows, bodySections, isCompareChart, kpiFigureIds, sectionParts, severityTone, uniqueFigureIds } from "@/lib/dynamicReport";
import { hqAnalysisTab, HQ_ANALYSIS_TABS } from "@/lib/hqAnalysisTabs";
import type { Figure, ReportBlock, ReportDoc } from "@/lib/types";

const fig = (id: string, value: number): Figure => ({ id, label: id.toUpperCase(), value, unit: "KRW_MN", dataOrigin: "actual" });
const chart = (points: [string, number | null][], kind: "bar" | "line" = "bar"): NonNullable<ReportBlock["chart"]> => ({
  kind,
  title: "상품별 잔액",
  unit: "KRW_MN",
  series: [{ name: "잔액", points: points.map(([label, value]) => ({ label, value })) }],
});
const table = { caption: "상품별 잔액", columns: [{ key: "group", label: "상품" }, { key: "value", label: "잔액(백만원)", align: "right" as const }], rows: [{ group: "A", value: "1,000" }] };

function doc(over: Partial<ReportDoc> = {}): ReportDoc {
  return {
    id: "rep-an-x",
    kind: "dynamic",
    title: "맞춤 분석",
    subtitle: "",
    asOf: "2026-08-31",
    generatedAt: "",
    dataOrigin: "actual",
    toc: [],
    sections: [
      { id: "sec-1", heading: "주요 지표", level: 2, blocks: [{ type: "metrics", figures: ["a", "b", "c", "d", "missing"] }] },
      { id: "sec-2", heading: "상품별 잔액", level: 2, blocks: [{ type: "table", table }, { type: "chart", chart: chart([["A", 1000], ["B", 2500]]) }] },
      { id: "sec-3", heading: "빈 절", level: 2, blocks: [] },
      { id: "sec-team", heading: "참고한 팀 데이터", level: 2, blocks: [{ type: "p", text: "팀" }] },
    ],
    figures: { a: fig("a", 1), b: fig("b", 2), c: fig("c", 3), d: fig("d", 4) },
    opinions: [],
    evidence: [],
    limitations: [],
    ...over,
  };
}

describe("분석 에이전트 보고서 → 시안 화면 배치", () => {
  it("본문 절 — 팀 데이터 · 빈 절 제외", () => {
    expect(bodySections(doc()).map((s) => s.id)).toEqual(["sec-1", "sec-2"]);
  });
  it("의견 상자 지표 — 의견 수치 우선, 없으면 첫 지표 묶음 · 있는 수치만 · 최대 3개", () => {
    expect(kpiFigureIds(doc())).toEqual(["a", "b", "c"]);
    const op = { id: "o", title: "t", statement: "s", severity: "info", figures: { d: fig("d", 4), nope: fig("nope", 0) } } as unknown as ReportDoc["opinions"][number];
    expect(kpiFigureIds(doc({ opinions: [op], figures: { ...doc().figures } }))).toEqual(["d"]);
  });
  it("절 나누기 — 같은 제목 그래프와 짝인 표는 '표로 보기' 쪽", () => {
    const d = doc();
    const p = sectionParts(d.sections[1], d.figures);
    expect(p.charts).toHaveLength(1);
    expect(p.chartTables).toHaveLength(1);
    expect(p.tables).toHaveLength(0);
    const m = sectionParts(d.sections[0], d.figures);
    expect(m.metrics).toEqual(["a", "b", "c", "d"]);
  });
  it("이름 · 값 · 단위가 같은 수치는 한 번만 (에이전트가 같은 지표를 여러 번 정의)", () => {
    const figures = { a: fig("a", 1), a2: { ...fig("a", 1), id: "a2" }, a3: { ...fig("a", 2), id: "a3" }, b: fig("b", 2) };
    expect(uniqueFigureIds(["a", "a2", "a3", "b", "zz"], figures)).toEqual(["a", "a3", "b"]);
    const d = doc({ figures, sections: [{ id: "s", heading: "h", level: 2, blocks: [{ type: "metrics", figures: ["a", "a2", "b"] }] }] });
    expect(kpiFigureIds(d)).toEqual(["a", "b"]);
    expect(sectionParts(d.sections[0], figures).metrics).toEqual(["a", "b"]);
  });
  it("비교 막대 — 가장 큰 값 하나만 강조 · 정수면 소수 없이 · 단위", () => {
    const rows = barRows(chart([["A", 1000], ["B", 2500], ["C", 2500], ["D", null]]));
    expect(rows.map((r) => r.strong)).toEqual([false, true, false, false]);
    expect(rows[1].text).toBe("2,500백만원");
    expect(rows[3].text).toBe("–");
    expect(barRows(chart([["A", 1.25]]))[0].text).toBe("1.3백만원");
  });
  it("비교 막대로 그릴 수 있는 그래프 — 막대 · 계열 1개 · 음수 없음", () => {
    expect(isCompareChart(chart([["A", 1]]))).toBe(true);
    expect(isCompareChart(chart([["A", 1]], "line"))).toBe(false);
    expect(isCompareChart(chart([["A", -1]]))).toBe(false);
  });
  it("의견 위험도 → 태그 색", () => {
    expect([severityTone("critical"), severityTone("caution"), severityTone("watch"), severityTone("info")]).toEqual(["critical", "attention", "info", "neutral"]);
  });
});

describe("종합기획부 데이터 분석 기본 탭", () => {
  it("?tab= → 탭 키 (모르면 첫 탭)", () => {
    expect(HQ_ANALYSIS_TABS.map((t) => t.key)).toEqual(["revenue", "corporate", "household", "comparison"]);
    expect(hqAnalysisTab("household")).toBe("household");
    expect(hqAnalysisTab(["comparison"])).toBe("comparison");
    expect(hqAnalysisTab("x")).toBe("revenue");
    expect(hqAnalysisTab(undefined)).toBe("revenue");
  });
});
