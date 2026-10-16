import { describe, expect, it } from "vitest";
import { asOfDayDots, asOfDots, eokText, halfDividerAfter, isProvisionShareReport, isRuleStatement, joEokParts, joEokText, pct1, provisionModel, provisionOpinion, RANK_CHART, rankBarWidth, TAIL_CHART } from "./provisionShare";
import { NO_VALUE } from "./period";
import type { Figure, ReportDoc } from "./types";

const fig = (key: string, value: number | null, unit: Figure["unit"], decimals = 0): Figure => ({ id: `fig-tok-${key}`, label: key, value, unit, decimals, dataOrigin: "simulated" });
/** 25개 상품 — 1위 300, 2위부터 1씩 작아지는 값 (백만원) */
const NAMES = Array.from({ length: 25 }, (_, i) => `상품${String(i + 1).padStart(2, "0")}`);
const VALUES = NAMES.map((_, i) => (i === 0 ? 300 : 200 - i));
const TOTAL = VALUES.reduce((a, v) => a + v, 0);
const chart = (title: string, idx: number[]) => ({ type: "chart" as const, chart: { kind: "bar" as const, title, unit: "KRW_MN" as const, series: [{ name: "충당금", points: idx.map((i) => ({ label: NAMES[i], value: VALUES[i] })) }] } });
function makeReport(over: Partial<ReportDoc> = {}, figs?: Figure[]): ReportDoc {
  const figures = figs ?? [fig("total_provision", TOTAL, "KRW_MN"), fig("product_count", 25, "CNT"), fig("top1_provision", 300, "KRW_MN"), fig("top1_share", (300 / TOTAL) * 100, "PCT", 1)];
  return {
    id: "rep",
    kind: "dynamic",
    title: "소매여신 상품별 충당금 비중",
    subtitle: "",
    asOf: "2026-08",
    generatedAt: "",
    dataOrigin: "simulated",
    toc: [],
    sections: [
      // 내림차순 상위 15 · 오름차순 하위 15 (가운데 5개가 겹친다)
      { id: "s1", heading: RANK_CHART, level: 2, blocks: [chart(RANK_CHART, Array.from({ length: 15 }, (_, i) => i))] },
      { id: "s2", heading: TAIL_CHART, level: 2, blocks: [chart(TAIL_CHART, Array.from({ length: 15 }, (_, i) => 24 - i))] },
    ],
    figures: Object.fromEntries(figures.map((f) => [f.id, f])),
    opinions: [],
    evidence: [],
    limitations: [],
    ...over,
  };
}

describe("상품별 충당금 비중 — 화면 모델", () => {
  const m = provisionModel(makeReport())!;
  it("두 표를 이름으로 합쳐 중복 없이 순위 · 누적", () => {
    expect(m.rows).toHaveLength(25);
    expect(new Set(m.rows.map((r) => r.name)).size).toBe(25);
    expect(m.rows[0]).toMatchObject({ rank: 1, name: "상품01", value: 300 });
    expect(m.rows[24].rank).toBe(25);
    expect(m.complete).toBe(true);
    expect(m.rows[24].cum).toBeCloseTo(100, 6);
    expect(m.rows[1].cum).toBeCloseTo(((300 + 199) / TOTAL) * 100, 6);
  });
  it("구간 합 · 비중 · 나머지 = 전체 − 상위 20", () => {
    expect(m.bands.map((b) => b.label)).toEqual(["상위 1–5위", "6–10위", "11–20위", "나머지 5개"]);
    const top5 = VALUES.slice(0, 5).reduce((a, v) => a + v, 0);
    expect(m.bands[0].sum).toBe(top5);
    expect(m.bands[0].share.value).toBeCloseTo((top5 / TOTAL) * 100, 6);
    expect(m.bands[0].share.decimals).toBe(1);
    expect(m.bands[0].share.calc?.expression).toBe("1–5위 충당금 합 ÷ 전체 충당금 × 100");
    expect(m.bands[3].sum).toBe(TOTAL - VALUES.slice(0, 20).reduce((a, v) => a + v, 0));
    expect(m.cumulative.map((c) => c.n)).toEqual([5, 10, 20]);
  });
  it("누적 비중이 처음 절반을 넘는 순위", () => {
    const k = m.rows.find((r) => r.cum >= 50)!.rank;
    expect(m.half?.n).toBe(k);
    expect(m.half?.sum).toBe(VALUES.slice(0, k).reduce((a, v) => a + v, 0));
  });
  it("해요체 결론 · 해설 (정상 · 쏠림)", () => {
    const info = provisionOpinion(m, "info");
    expect(info.headline).toBe(`25개 상품 중 상위 ${m.half!.n}개가 충당금의 절반(${pct1(m.half!.share.value)}%)을 차지해요`);
    expect(info.body.startsWith("1위인 상품01도 비중이")).toBe(true);
    expect(info.body).toContain("쏠린 구조는 아니에요.");
    expect(info.body.endsWith("요.")).toBe(true);
    const watch = provisionOpinion(m, "watch");
    expect(watch.body).toContain("한 상품에 충당금이 쏠려 있어요.");
    expect(watch.body.endsWith("요.")).toBe(true);
  });
  it("키가 빠지면 이 화면이 아니다", () => {
    const noTop = makeReport({}, [fig("total_provision", TOTAL, "KRW_MN"), fig("product_count", 25, "CNT")]);
    expect(isProvisionShareReport(makeReport())).toBe(true);
    expect(isProvisionShareReport(noTop)).toBe(false);
    expect(isProvisionShareReport(makeReport({ kind: "inclusive_risk" }))).toBe(false);
    expect(provisionModel(makeReport({}, [fig("product_count", 25, "CNT")]))).toBeNull();
    expect(provisionModel(makeReport({}, [fig("total_provision", 0, "KRW_MN")]))).toBeNull();
  });
  it("하위 표로 다 덮지 못하면 상위 표만 (순위가 끊기지 않게)", () => {
    const r = makeReport({}, [fig("total_provision", TOTAL, "KRW_MN"), fig("product_count", 40, "CNT"), fig("top1_share", 5, "PCT", 1)]);
    const mm = provisionModel(r)!;
    expect(mm.rows).toHaveLength(15);
    expect(mm.complete).toBe(false);
  });
});

describe("상품별 충당금 비중 — 형식", () => {
  it("조 · 억 표기", () => {
    expect(joEokParts(3412180)).toEqual({ value: "3조 4,122", unit: "억원" });
    expect(joEokParts(980000)).toEqual({ value: "9,800", unit: "억원" });
    expect(joEokText(3412180)).toBe("3조 4,122억원");
    expect(eokText(198107)).toBe("1,981");
    expect(eokText(null)).toBe(NO_VALUE);
  });
  it("기준일 점 표기", () => {
    expect(asOfDots("2026-08")).toBe("2026.08");
    expect(asOfDots("2026-08-31")).toBe("2026.08.31");
  });
  it("규칙 문장 알아보기", () => {
    expect(isRuleStatement({ title: "상품별 충당금 쏠림", statement: "상품별 충당금 쏠림 — 전체 충당금 [[fig:a]]." })).toBe(true);
    expect(isRuleStatement({ title: "상품별 충당금 쏠림", statement: "상위 10개가 절반을 차지해요." })).toBe(false);
  });
});

describe("상품별 충당금 비중 — 기준일 · 막대 · 절반 구분선", () => {
  it("각주 기준일: 월 기준은 그 달 말일 · 일 기준은 그대로", () => {
    expect(asOfDayDots("2026-08")).toBe("2026.08.31");
    expect(asOfDayDots("2026-02")).toBe("2026.02.28");
    expect(asOfDayDots("2028-02")).toBe("2028.02.29");
    expect(asOfDayDots("2026-06")).toBe("2026.06.30");
    expect(asOfDayDots("2026-08-31")).toBe("2026.08.31");
    expect(asOfDayDots(null)).toBe(NO_VALUE);
  });
  // 25개 상품 — 상위 7개 100 · 다음 17개 40 · 마지막 1개 0 (백만원) → 누적 6위 43.5% · 7위 50.7%
  const names = Array.from({ length: 25 }, (_, i) => `품목${String(i + 1).padStart(2, "0")}`);
  const values: number[] = names.map((_, i) => (i < 7 ? 100 : i < 24 ? 40 : 0));
  const total = values.reduce((a, v) => a + v, 0);
  const pts = (idx: number[]) => idx.map((i) => ({ label: names[i], value: values[i] }));
  const series = (title: string, idx: number[]) => ({ type: "chart" as const, chart: { kind: "bar" as const, title, unit: "KRW_MN" as const, series: [{ name: "충당금", points: pts(idx) }] } });
  const report = makeReport(
    {
      sections: [
        { id: "s1", heading: RANK_CHART, level: 2, blocks: [series(RANK_CHART, Array.from({ length: 15 }, (_, i) => i))] },
        { id: "s2", heading: TAIL_CHART, level: 2, blocks: [series(TAIL_CHART, Array.from({ length: 15 }, (_, i) => 24 - i))] },
      ],
    },
    [fig("total_provision", total, "KRW_MN"), fig("product_count", 25, "CNT"), fig("top1_provision", 100, "KRW_MN"), fig("top1_share", (100 / total) * 100, "PCT", 1)],
  );
  const km = provisionModel(report)!;
  it("K=7 이면 7위 뒤(칸 끝이 아님)에 점선 · 칸 끝 행 · 다른 행에는 없음", () => {
    expect(km.half?.n).toBe(7);
    const firstColumnLast = km.rows[9].rank;
    const marked = km.rows.slice(0, 10).filter((r) => halfDividerAfter(r.rank, km.half?.n ?? null, firstColumnLast));
    expect(marked.map((r) => r.rank)).toEqual([7]);
    // K=10(칸 끝)이면 칸 경계가 구분선이라 점선 없음 · 절반 순위가 없으면 없음
    expect(halfDividerAfter(10, 10, 10)).toBe(false);
    expect(halfDividerAfter(7, null, 10)).toBe(false);
  });
  it("값 0 인 상품은 막대 없음(null) · 값이 있으면 1위 대비 폭", () => {
    const zero = km.rows.find((r) => r.value === 0)!;
    expect(zero.rank).toBe(25);
    expect(rankBarWidth(zero.value, km.rows[0].value, 0.88)).toBeNull();
    expect(rankBarWidth(null, 100, 0.88)).toBeNull();
    expect(rankBarWidth(100, 100, 0.88)).toBeCloseTo(88);
    expect(rankBarWidth(40, 100, 0.88)).toBeCloseTo(35.2);
    expect(rankBarWidth(40, 0, 0.88)).toBeNull();
  });
});
