import { describe, expect, it } from "vitest";
import { scrubText } from "@/lib/scrubText";

describe("scrubText — 삭제 알림에 붙는 정리 건수", () => {
  it("정리한 것이 없거나 결과가 없으면 아무것도 붙이지 않는다", () => {
    expect(scrubText(undefined)).toBe("");
    expect(scrubText(null)).toBe("");
    expect(scrubText({})).toBe("");
    expect(scrubText({ llmCalls: 0, nodeRuns: 0, evidenceRemoved: 0, generationsRemoved: 0 })).toBe("");
  });
  it("0 이 아닌 항목만 순서대로 이어 붙인다", () => {
    expect(scrubText({ llmCalls: 2, evidenceRemoved: 1 })).toBe(" · 복사돼 남은 내용 정리: AI 호출 기록 2건, 보고서 근거 1건");
    expect(scrubText({ llmCalls: 1, nodeRuns: 3, evidenceRemoved: 4, generationsRemoved: 5 })).toBe(
      " · 복사돼 남은 내용 정리: AI 호출 기록 1건, 실행 기록 3건, 보고서 근거 4건, 옛 산출물 세대 5건",
    );
  });
  it("서버가 republished 같은 다른 키를 함께 보내도 건수 항목만 쓴다", () => {
    expect(scrubText({ generationsRemoved: 2, republished: ["report.x"] } as never)).toBe(" · 복사돼 남은 내용 정리: 옛 산출물 세대 2건");
  });
});