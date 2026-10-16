import { describe, expect, it } from "vitest";
import { toPoliteSentence } from "./sentence";

describe("toPoliteSentence — Agent 해설 결론을 해요체 + 마침표로", () => {
  it("…있습니다 → …있어요.", () => {
    expect(toPoliteSentence("여신 이자마진 비중이 3개년 연속 축소되고 있습니다")).toBe("여신 이자마진 비중이 3개년 연속 축소되고 있어요.");
  });
  it("…확인됩니다. → …확인돼요.", () => {
    expect(toPoliteSentence("증가율 측면에서는 기업 대비 빠른 흐름이 확인됩니다.")).toBe("증가율 측면에서는 기업 대비 빠른 흐름이 확인돼요.");
  });
  it("…합니다 → …해요.", () => {
    expect(toPoliteSentence("가계 관리를 강화합니다")).toBe("가계 관리를 강화해요.");
  });
  it("…입니다 → 받침에 따라 이에요 / 예요", () => {
    expect(toPoliteSentence("현재 기조는 기업여신 확대입니다")).toBe("현재 기조는 기업여신 확대예요.");
    expect(toPoliteSentence("현재 기조는 가계여신 관리 방향입니다")).toBe("현재 기조는 가계여신 관리 방향이에요.");
  });
  it("…낮아졌습니다 → …낮아졌어요.", () => {
    expect(toPoliteSentence("기업여신 구성비가 낮아졌습니다.")).toBe("기업여신 구성비가 낮아졌어요.");
  });
  it("이미 해요체면 마침표만 맞춘다", () => {
    expect(toPoliteSentence("가계가 더 빠르게 늘고 있어요")).toBe("가계가 더 빠르게 늘고 있어요.");
    expect(toPoliteSentence("가계가 더 빠르게 늘고 있어요.")).toBe("가계가 더 빠르게 늘고 있어요.");
  });
  it("빈 문자열은 그대로", () => {
    expect(toPoliteSentence("  ")).toBe("");
  });
});
