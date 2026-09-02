import { describe, expect, it } from "vitest";
import { toArticleDto } from "./dto.ts";

describe("toArticleDto", () => {
  it("maps confirmed article fields", () => {
    const dto = toArticleDto({
      id: "a1",
      title: "보도",
      url: "https://www.fsc.go.kr/x",
      fileRelPath: null,
      source: "seed",
      confirmed: true,
      confirmedAt: new Date("2026-01-01T00:00:00.000Z"),
      sectors: ["loan"],
      tags: ["포용금융"],
      summary: "요약",
    });
    expect(dto.hasFile).toBe(false);
    expect(dto.confirmed).toBe(true);
    expect(dto.source).toBe("seed");
  });
});
