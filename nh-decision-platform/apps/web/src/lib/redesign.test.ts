import { describe, expect, it } from "vitest";
import { derivedFigure, monthOf } from "@/lib/derived";
import { formatKstShort, formatSignedValue, formatYearMonth, formatValue } from "@/lib/format";
import { GOAL_VERDICT, directionSuffix, proposalRange } from "@/lib/goalView";
import { CORPORATE } from "@/mock/finance";
import { GOALS, PROPOSALS } from "@/mock/goals";
import type { Figure } from "@/lib/types";

const fig = (value: number | null, unit: Figure["unit"], decimals?: number): Figure => ({ id: "f", label: "x", value, unit, decimals, dataOrigin: "simulated" });

describe("기준일 → 월 · 연월 표기", () => {
  it("기준일에서 월을 뽑아 연간 경과율에 쓴다", () => {
    expect(monthOf("2026-08-31")).toBe(8);
    expect(monthOf("2026-12-01")).toBe(12);
  });
  it("읽을 수 없으면 12개월(연말)로 본다", () => {
    expect(monthOf("")).toBe(12);
    expect(monthOf("abcd-ef-gh")).toBe(12);
  });
  it("2026-08-31 → 2026년 8월", () => {
    expect(formatYearMonth("2026-08-31")).toBe("2026년 8월");
  });
});

describe("최종 분석 시각 — KST MM.DD HH:mm", () => {
  it("시간대가 있는 ISO 를 KST 로 바꾼다", () => {
    expect(formatKstShort("2026-08-31T06:22:00+09:00")).toBe("08.31 06:22");
    expect(formatKstShort("2026-10-13T00:11:00Z")).toBe("10.13 09:11");
  });
  it("자정도 00 으로 표기한다(24 로 나오지 않는다)", () => {
    expect(formatKstShort("2026-10-12T15:05:00Z")).toBe("10.13 00:05");
  });
  it("시간대 표기가 없으면 UTC 로 본다 — 서버 · 브라우저 시간대와 무관", () => {
    expect(formatKstShort("2026-10-13T00:11:00")).toBe("10.13 09:11");
  });
});

describe("큰 숫자 — 단위를 떼고 본문만", () => {
  it("부호 없는 본문", () => {
    expect(formatValue(fig(115.34, "KRW_TN", 2))).toBe("115.34");
  });
  it("양수에만 + 를 붙인다", () => {
    expect(formatSignedValue(fig(4.54, "PCT", 2))).toBe("+4.54");
    expect(formatSignedValue(fig(-0.46, "PP", 2))).toBe("-0.46");
    expect(formatSignedValue(fig(0, "PP", 1))).toBe("0.0");
  });
  it("값이 없으면 미제공 문구", () => {
    expect(formatSignedValue(fig(null, "PCT"))).toBe("미제공");
  });
});

describe("추천 범위 표기", () => {
  it("모든 목데이터 제안이 표기로 바뀐다", () => {
    for (const p of PROPOSALS) expect(proposalRange(p).length).toBeGreaterThan(0);
  });
  it("범위 제안은 `하한 ~ 상한` 형식", () => {
    const p = PROPOSALS.find((x) => x.recommendation.mode === "range");
    expect(p).toBeTruthy();
    expect(proposalRange(p!)).toMatch(/^[\d.]+\S* ~ [\d.]+\S*$/);
  });
  it("방향 꼬리말 — 이상 · 이하 · 없음", () => {
    expect(directionSuffix({ direction: "increase" })).toBe("이상");
    expect(directionSuffix({ direction: "decrease" })).toBe("이하");
    expect(directionSuffix({ direction: "maintain" })).toBe("");
    expect(directionSuffix(undefined)).toBe("");
  });
});

describe("목표 판정 태그 — 정상은 무채색, 미달 · 근접은 주황, 초과는 빨강", () => {
  it("라벨과 톤", () => {
    expect(GOAL_VERDICT.on_track).toEqual({ label: "정상", tone: "success" });
    expect(GOAL_VERDICT.below.tone).toBe("attention");
    expect(GOAL_VERDICT.near_limit.tone).toBe("attention");
    expect(GOAL_VERDICT.breach.tone).toBe("critical");
  });
  it("모든 목데이터 목표의 판정이 정의돼 있다", () => {
    for (const g of GOALS) if (g.gapVerdict) expect(GOAL_VERDICT[g.gapVerdict]).toBeTruthy();
  });
});

describe("기업여신 목표 경로 — 전년 동기 잔액 × (1 + 연 목표 증가율 × 경과월 ÷ 12)", () => {
  const base = CORPORATE.yearly.find((p) => p.label === "2025.08")?.value ?? NaN;
  const goal = GOALS.find((g) => g.id === "goal-corp-growth");
  const path = (month: number) => base * (1 + ((goal?.targetValue ?? 0) / 100) * (month / 12));

  it("8월 목표 경로는 116.03조원, 실적 115.34조원과의 차이는 -0.69조원", () => {
    expect(base).toBeCloseTo(110.86, 2);
    expect(path(8)).toBeCloseTo(116.03, 2);
    const actual = CORPORATE.monthly[7].value ?? NaN;
    expect(actual - path(8)).toBeCloseTo(-0.69, 2);
  });
  it("달이 갈수록 목표 경로가 일정하게 늘어난다", () => {
    const steps = [1, 2, 3, 4, 5, 6, 7, 8].map(path);
    for (let i = 1; i < steps.length; i++) expect(steps[i]).toBeGreaterThan(steps[i - 1]);
    expect(steps[1] - steps[0]).toBeCloseTo(steps[7] - steps[6], 6);
  });
});

describe("화면 파생 수치 — 계산 추적이 붙는다", () => {
  it("합계 · 비율은 수식과 입력값을 가진다", () => {
    const f = derivedFigure({
      id: "t",
      label: "신용RWA 잔여",
      value: 2.01,
      unit: "KRW_TN",
      decimals: 2,
      expression: "배분 − 사용",
      inputs: [
        { key: "a", label: "배분", value: "8.60", unit: "조원", source: "x" },
        { key: "u", label: "사용", value: "6.59", unit: "조원", source: "y" },
      ],
      asOf: "2026-08-31",
    });
    expect(f.calc?.expression).toBe("배분 − 사용");
    expect(f.calc?.inputs).toHaveLength(2);
    expect(f.value).toBe(2.01);
    expect(f.dataOrigin).toBe("mixed");
  });
});
