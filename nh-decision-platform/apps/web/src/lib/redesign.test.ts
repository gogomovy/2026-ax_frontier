import { describe, expect, it } from "vitest";
import { derivedFigure, originOf } from "@/lib/derived";
import { formatKstShort, formatSignedValue, formatYearMonth, formatValue } from "@/lib/format";
import { GOAL_VERDICT, directionSuffix, proposalRange } from "@/lib/goalView";
import { targetPath } from "@/lib/loanView";
import { NO_VALUE, periodOf } from "@/lib/period";
import type { Figure, Proposal } from "@/lib/types";

const fig = (value: number | null, unit: Figure["unit"], decimals?: number): Figure => ({ id: "f", label: "x", value, unit, decimals, dataOrigin: "simulated" });

/** 추천 범위 표기를 시험하는 최소 제안 (목데이터 없이 직접 만든다) */
const proposal = (recommendation: Partial<Proposal["recommendation"]> & Pick<Proposal["recommendation"], "mode" | "unit">): Proposal =>
  ({ id: "p", recommendation: { text: "", ...recommendation } }) as unknown as Proposal;

describe("기준일 → 월 · 연월 표기", () => {
  it("기준일에서 월을 뽑아 연간 경과율에 쓴다", () => {
    expect(periodOf("2026-08-31").month).toBe("8월");
    expect(periodOf("2026-12-01").month).toBe("12월");
  });
  it("읽을 수 없으면 값을 지어내지 않고 '–' 로 둔다", () => {
    expect(periodOf("").month).toBe(NO_VALUE);
    expect(periodOf("abcd-ef-gh").month).toBe(NO_VALUE);
    expect(periodOf(null).ym).toBe(NO_VALUE);
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
  it("범위 제안은 `하한 ~ 상한` 형식", () => {
    const p = proposal({ mode: "range", low: 7.5, high: 8, unit: "PCT", decimals: 1 });
    expect(proposalRange(p)).toMatch(/^[\d.]+\S* ~ [\d.]+\S*$/);
    expect(proposalRange(p)).toBe("7.5% ~ 8.0%");
  });
  it("단일 값 제안은 값 하나", () => {
    expect(proposalRange(proposal({ mode: "point", value: 3.1, unit: "KRW_TN", decimals: 1 }))).toBe("3.1조원");
  });
  it("방향만 있는 제안은 수치를 만들지 않는다", () => {
    expect(proposalRange(proposal({ mode: "direction_only", unit: "NONE" }))).toBe("방향성만 제시");
  });
  it("상한 · 하한이 없으면 '-' 로 둔다", () => {
    expect(proposalRange(proposal({ mode: "range", low: 3, unit: "PCT", decimals: 1 }))).toBe("3.0% ~ -%");
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
  it("서버가 줄 수 있는 모든 판정이 정의돼 있다", () => {
    for (const v of ["on_track", "below", "near_limit", "breach"] as const) expect(GOAL_VERDICT[v]).toBeTruthy();
  });
});

describe("기업여신 목표 경로 — 화면이 쓰는 targetPath 함수 (전년 동기 잔액 × (1 + 연 목표 증가율 × 경과월 ÷ 12))", () => {
  // 시험 입력(임의 값) — 화면 수치가 아니라 함수 동작을 본다
  const base = 100;
  const growthPct = 12;

  it("경과월마다 연 증가율의 1/12 씩 — 12개월이면 연 목표에 닿는다", () => {
    const p = targetPath(base, growthPct, 12)!;
    expect(p).toHaveLength(12);
    expect(p[0]).toBeCloseTo(101, 6);
    expect(p[11]).toBeCloseTo(112, 6);
  });
  it("달이 갈수록 목표 경로가 일정하게 늘어난다", () => {
    const steps = targetPath(base, growthPct, 8)!;
    for (let i = 1; i < steps.length; i++) expect(steps[i]).toBeGreaterThan(steps[i - 1]);
    expect(steps[1] - steps[0]).toBeCloseTo(steps[7] - steps[6], 6);
  });
  it("입력이 없으면 경로를 그리지 않는다", () => {
    expect(targetPath(null, growthPct, 8)).toBeNull();
    expect(targetPath(base, undefined, 8)).toBeNull();
    expect(targetPath(base, growthPct, 0)).toBeNull();
  });
  it("전년 동월 라벨은 기준일에서 계산한다", () => {
    expect(periodOf("2026-08-31").prevYm).toBe("2025.08");
  });
});

describe("화면 파생 수치 — 계산 추적이 붙는다", () => {
  it("합계 · 비율은 수식과 입력값을 가진다", () => {
    const f = derivedFigure({
      id: "t",
      label: "연간 경과율",
      value: 66.7,
      unit: "PCT",
      decimals: 1,
      expression: "기준월 ÷ 12개월 × 100",
      inputs: [{ key: "month", label: "기준월", value: "8", unit: "월", source: "기준일 2026-08-31" }],
      asOf: "2026-08-31",
    });
    expect(f.calc?.expression).toBe("기준월 ÷ 12개월 × 100");
    expect(f.calc?.inputs).toHaveLength(1);
    expect(f.value).toBe(66.7);
    // 입력이 수치가 아니면(기준월) 자료 성격은 알 수 없음 — 꾸며 넣지 않는다 (Phase K · HC-05)
    expect(f.dataOrigin).toBe("unknown");
    expect(f.calc?.executedAt).toBe("");
  });
  it("자료 성격은 입력 수치에서 물려받는다", () => {
    const a = { ...fig(1, "PCT"), dataOrigin: "actual" as const };
    const s = { ...fig(1, "PCT"), dataOrigin: "simulated" as const };
    expect(originOf([a, a])).toBe("actual");
    expect(originOf([a, s])).toBe("mixed");
    expect(originOf([])).toBe("unknown");
  });
});
