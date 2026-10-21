import { describe, expect, it } from "vitest";
import { asOfText, isSharedHref, normalizeLinked, SHARED_REPORT_PATH, type LinkedAnalysisResponse } from "@/lib/linkedAnalysis";

/**
 * 수행방안 '영업점 참고' 연결 분석 — 영업점 공통(영업본부 · 영업점)은 공유 보고서 화면(/branch/shared/{수행방안})으로 열고,
 * 그 자리에서 요약도 본다.
 */
describe("연결 분석 응답", () => {
  it("공유 보고서 주소만 공유로 본다", () => {
    expect(isSharedHref(`${SHARED_REPORT_PATH}plan-inclusive-risk`)).toBe(true);
    expect(isSharedHref("/risk/analysis/inclusive-risk")).toBe(false);
    expect(isSharedHref(null)).toBe(false);
    expect(isSharedHref(undefined)).toBe(false);
  });

  it("모르는 심각도는 정상, 빈 문장 · 빈 절 · 빈 수치는 뺀다", () => {
    const r = normalizeLinked({
      plan: "p1",
      href: "/branch/shared/p1",
      analysis: {
        tabKey: "inclusive-risk",
        space: "risk",
        analysisFrom: "사업부서",
        title: "포용금융 리스크",
        severity: "bogus" as never,
        summary: [{ title: "", severity: "watch", text: "" }, { title: "충당금 비중", severity: "nope" as never, text: "비중이 높아졌습니다" }],
        keyFigures: ["", "비중 9.16%"],
        sections: [{ heading: "개요", lines: [] }, { heading: "추이", lines: ["상승"] }],
        limitations: ["", "가정 포함"],
      },
    } satisfies LinkedAnalysisResponse);
    const a = r.analysis!;
    expect(a.severity).toBe("info");
    expect(a.summary).toEqual([{ title: "충당금 비중", severity: "info", text: "비중이 높아졌습니다" }]);
    expect(a.keyFigures).toEqual(["비중 9.16%"]);
    expect(a.sections.map((s) => s.heading)).toEqual(["추이"]);
    expect(a.limitations).toEqual(["가정 포함"]);
    expect(r.href).toBe("/branch/shared/p1");
    expect(normalizeLinked({ plan: "p2", analysis: null, href: null }).analysis).toBeNull();
  });

  it("기준일 표기", () => {
    expect(asOfText("2026-08-31T00:00:00")).toBe("2026.08.31");
    expect(asOfText("2026 8월")).toBe("2026 8월");
    expect(asOfText(null)).toBe("");
  });
});
