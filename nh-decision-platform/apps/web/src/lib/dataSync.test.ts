import { describe, expect, it } from "vitest";
import { MIN_FIELDS, countsLine, pasteStats, syncActionLabel } from "./dataSync";

describe("조직 · 인사 동기화 표기", () => {
  it("붙여 넣은 본문 — 빈 줄 제외 줄 수 · 첫 줄 칸 수 · 칸 수가 다른 줄 (CRLF · CR · LF)", () => {
    expect(pasteStats("")).toEqual({ lines: 0, fields: 0, ragged: 0 });
    expect(pasteStats("a|b|c\r\nd|e|f\r\n\r\n")).toEqual({ lines: 2, fields: 3, ragged: 0 });
    expect(pasteStats("a|b|c||\rd|e\n  \ng|h|i||")).toEqual({ lines: 3, fields: 5, ragged: 1 });
    expect(MIN_FIELDS.employee).toBe(21);
    expect(MIN_FIELDS.organization).toBe(15);
  });

  it("이력 동작 · 결과 한 줄", () => {
    expect(syncActionLabel("admin.sync.employee.dry_run")).toEqual({ target: "인사", mode: "미리보기" });
    expect(syncActionLabel("admin.sync.organization")).toEqual({ target: "조직", mode: "반영" });
    expect(countsLine({ totalProcessed: 2, inserted: 2, deactivated: 0 }, "employee")).toBe("처리 2 · 신규 2");
    expect(countsLine({}, "organization")).toBe("변경 없음");
  });
});
