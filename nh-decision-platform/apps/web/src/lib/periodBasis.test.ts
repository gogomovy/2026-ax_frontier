import { describe, expect, it } from "vitest";
import { monthIndexOf, targetPath, targetPathSince } from "./loanView";
import { basisNote, basisNotes, columnPeriod, gapBasisText, growthBasisHint, periodDot, periodName, tokenName } from "./periodBasis";

const yoy = { token: "$latest-12", wanted: "202508", used: "202601" };

describe("기간 대체 표기", () => {
  it("토큰 이름 · 기간 점 표기", () => {
    expect(tokenName("$latest-12")).toBe("전년 동기");
    expect(tokenName("$latest-24")).toBe("2년 전 동기");
    expect(tokenName("$latest-36")).toBe("3년 전 동기");
    expect(tokenName("$latest-1")).toBe("전월");
    expect(tokenName("$latest-3")).toBe("3개월 전");
    expect(tokenName("$prev_year_end")).toBe("전년 말");
    expect(tokenName("$prev")).toBe("$prev");
    expect(periodDot("202601")).toBe("2026.01");
    expect(periodDot("2025-12-31")).toBe("2025.12");
  });

  it("안내 문구는 서버 문구와 같다 · 중복은 한 번", () => {
    expect(basisNote(yoy)).toBe("전년 동기(2025.08) 자료가 없어 가장 가까운 기준일 2026.01 과 비교");
    expect(basisNotes({ basis: [yoy, { ...yoy, col: "ym" }] })).toHaveLength(1);
    expect(basisNotes({})).toEqual([]);
  });

  it("비교 이름 · 열 머리는 실제 견준 기간을 쓴다", () => {
    expect(periodName({ basis: [yoy] }, "$latest-12", "전년 동기")).toBe("2026.01");
    expect(periodName({ basis: [yoy] }, "$latest-24", "2024.08")).toBe("2024.08");
    expect(periodName(null, "$latest-12", "전년 동기")).toBe("전년 동기");
    expect(columnPeriod([{ basis: [yoy] }, { basis: [yoy] }], "$latest-12", "2025.08")).toBe("2026.01");
    expect(columnPeriod([{ basis: [yoy] }, {}], "$latest-12", "2025.08")).toBe("2026.01 · 2025.08");
    expect(columnPeriod([], "$latest-12", "2025.08")).toBe("2025.08");
  });
});

describe("비교 기간 맞춤 표기 (PER-05)", () => {
  const b = { token: "$latest-12", wanted: "202509", used: "202601", latest: "202609", months: 8, wantedMonths: 12 };

  it("수치 안내에 비교 기간 · 목표 환산을 함께 쓴다", () => {
    expect(basisNotes({ basis: [b] })).toEqual(["전년 동기(2025.09) 자료가 없어 가장 가까운 기준일 2026.01 과 비교 · 비교 기간 8개월"]);
    const n = basisNotes({ basis: [b], align: { months: 8, wantedMonths: 12, goal: { b: { from: "12", to: "8" } } } });
    expect(n[1]).toBe("경영목표를 비교 기간 8개월로 환산(× 8/12)해 견준 값");
  });

  it("목표 판정 근거 · 증가율 설명", () => {
    expect(gapBasisText({ months: 8, wantedMonths: 12, used: "202601", aligned: 4.6667 }, "%")).toBe("2026.01 대비 · 8개월 환산 목표 4.67% 기준");
    expect(gapBasisText({ months: 8, wantedMonths: 12, used: "202601", held: true })).toBe("판정 보류 — 2026.01 대비 8개월 실적이라 연 목표와 기간이 다름");
    expect(gapBasisText(null)).toBeNull();
    expect(growthBasisHint(null)).toBe("증가율은 전년 동월 말 잔액 대비입니다.");
    expect(growthBasisHint(b)).toBe("증가율은 2026.01 말 잔액 대비(8개월)입니다 — 전년 동기(2025.09) 자료가 없어 가장 가까운 기준일과 견줬습니다.");
  });

  it("목표 경로 — 비교 기준일부터 경과월만큼(마지막 달 = 환산 목표)", () => {
    expect(monthIndexOf("2026.03")).toBe(2026 * 12 + 2);
    expect(monthIndexOf("202601")).toBe(2026 * 12);
    expect(monthIndexOf("2026-01-31")).toBe(2026 * 12);
    expect(monthIndexOf("3월")).toBeNull();
    const labels = ["2026.01", "2026.02", "2026.09"];
    const path = targetPathSince(100, 12, labels, "202601");
    expect(path).not.toBeNull();
    expect(path![0]).toBe(100);
    expect(path![2]).toBeCloseTo(100 * (1 + 0.12 * (8 / 12)), 10);
    expect(targetPathSince(100, 12, ["3월"], "202601")).toBeNull();
    expect(targetPathSince(null, 12, labels, "202601")).toBeNull();
    // 대체가 없을 때의 기존 경로는 그대로
    const plain = targetPath(100, 12, 2) ?? [];
    expect(plain[0]).toBeCloseTo(101, 10);
    expect(plain[1]).toBeCloseTo(102, 10);
  });
});
