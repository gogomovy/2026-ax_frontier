import { describe, expect, it } from "vitest";
import { barWidths, fmt1, fmtPts, groupOf, opportunityNote, pendingNote, ratePct, regionMax, regionParam, scoreGroups, shortBranchName, signed1, upliftNote } from "@/lib/regionView";
import { NO_VALUE } from "@/lib/period";
import type { RegionKpi, RegionKpiBranch } from "@/lib/types";

const branch = (over: Partial<RegionKpiBranch> = {}): RegionKpiBranch => ({
  code: "B1",
  name: "서초지점",
  orgCode: "B1",
  available: true,
  total: 593.7,
  max: 1000,
  rate: 59.4,
  adjustments: 2,
  totalAfter: 620.3,
  uplift: 26.7,
  groups: [],
  avgGrade: null,
  alerts: [],
  alertCount: 0,
  ...over,
});
const summary = (over: Partial<RegionKpi["summary"]> = {}): RegionKpi["summary"] => ({ branches: 4, computed: 2, ...over });

describe("지역 인자", () => {
  it("형식이 맞을 때만", () => {
    expect(regionParam({ region: "D300" })).toBe("D300");
    expect(regionParam({ region: ["D400", "D500"] })).toBe("D400");
    expect(regionParam({ region: "bad!" })).toBeNull();
    expect(regionParam({ region: "x".repeat(21) })).toBeNull();
    expect(regionParam({})).toBeNull();
    expect(regionParam(undefined)).toBeNull();
  });
});

describe("짧은 지점 이름 · 자료 대기 안내", () => {
  it("끝말을 뗀다", () => {
    expect(shortBranchName("서초지점")).toBe("서초");
    expect(shortBranchName("강남금융센터")).toBe("강남");
    expect(shortBranchName("역삼역지점")).toBe("역삼역");
    expect(shortBranchName("본점영업점")).toBe("본점");
    expect(shortBranchName("지점")).toBe("지점");
    expect(shortBranchName("수원영통")).toBe("수원영통");
  });
  it("대기 지점만 조직표 순서대로", () => {
    expect(pendingNote([branch(), branch({ name: "서초지점", available: false }), branch({ name: "역삼역지점", available: false })])).toBe("서초 · 역삼역 자료 대기");
    expect(pendingNote([branch()])).toBeNull();
    expect(pendingNote([])).toBeNull();
  });
});

describe("그룹 · 막대 폭", () => {
  it("가 · 감점은 뺀다", () => {
    const g = scoreGroups({ groups: [{ code: "CUST", label: "고객", kind: "kpi" }, { code: "ADJ", label: "가감", kind: "adjustment" }, { code: "X", label: "종류 없음" }] });
    expect(g.map((x) => x.code)).toEqual(["CUST", "X"]);
    expect(scoreGroups({})).toEqual([]);
  });
  it("득점률은 0–100 으로 자르고 만점이 없으면 0", () => {
    expect(ratePct(137, 200)).toBeCloseTo(68.5);
    expect(ratePct(250, 200)).toBe(100);
    expect(ratePct(-5, 200)).toBe(0);
    expect(ratePct(10, null)).toBe(0);
    expect(ratePct(10, 0)).toBe(0);
    expect(ratePct(null, 200)).toBe(0);
  });
  it("두 겹 막대 — 추가분은 음수면 0, 합은 100 이하", () => {
    const w = barWidths(branch());
    expect(w.now).toBeCloseTo(59.37);
    expect(w.extra).toBeCloseTo(2.66);
    expect(barWidths(branch({ totalAfter: 580 })).extra).toBe(0);
    expect(barWidths(branch({ max: null }))).toEqual({ now: 0, extra: 0 });
    expect(barWidths(branch({ totalAfter: null })).extra).toBe(0);
    const full = barWidths(branch({ total: 990, totalAfter: 1100 }));
    expect(full.now + full.extra).toBeCloseTo(100);
  });
});

describe("숫자 글자", () => {
  it("소수 1자리 · 없으면 대시", () => {
    expect(fmt1(137)).toBe("137.0");
    expect(fmt1(1234.56)).toBe("1,234.6");
    expect(fmt1(null)).toBe(NO_VALUE);
    expect(fmt1(undefined)).toBe(NO_VALUE);
    expect(fmtPts(1000)).toBe("1,000");
    expect(fmtPts(null)).toBe(NO_VALUE);
    expect(signed1(26.7)).toBe("+26.7");
    expect(signed1(-3)).toBe("−3.0");
    expect(signed1(0)).toBe("0.0");
  });
  it("평균 상향 · 향상 기회 보조 줄", () => {
    expect(upliftNote(summary({ avgUplift: 20.6, changeTypes: ["신설"] }))).toBe("+20.6점 · 신설 평가항목 대응");
    expect(upliftNote(summary({ avgUplift: 20.6, changeTypes: [] }))).toBe("+20.6점");
    expect(upliftNote(summary({ avgUplift: null }))).toBeNull();
    expect(opportunityNote(summary({ opportunityBranches: 2, changeTypes: ["신설", "변경"] }))).toBe("2개 영업점 · 신설 · 변경 평가기준");
    expect(opportunityNote(summary({}))).toBe("0개 영업점");
  });
  it("지역 만점 — 계산된 지점 만점이 모두 같을 때만", () => {
    expect(regionMax([branch(), branch({ code: "B2" }), branch({ available: false, max: null })])).toBe(1000);
    expect(regionMax([branch(), branch({ max: 900 })])).toBeNull();
    expect(regionMax([branch({ available: false })])).toBeNull();
  });
  it("그룹 득점 찾기", () => {
    const b = branch({ groups: [{ code: "CUST", label: "고객", score: 137, max: 200 }] });
    expect(groupOf(b, "CUST")?.score).toBe(137);
    expect(groupOf(b, "BIZ")).toBeUndefined();
  });
});
