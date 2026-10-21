import { describe, expect, it } from "vitest";
import { groupByKind, previewValue, reasonError, scoreText, type ProposalItem } from "./stewardProposals";

const base = { status: "pending" as const, canReview: true };

describe("데이터 책임자 승인함 표기 (§40 STW)", () => {
  it("미리 계산한 값은 정수 · 소수 · 단위 · 갱신 실패를 구분해 쓴다", () => {
    expect(previewValue({ id: "a", value: 400, unit: "NONE" })).toBe("400");
    expect(previewValue({ id: "b", value: 14.2857, unit: "PCT" })).toBe("14.29%");
    expect(previewValue({ id: "c", value: "35", unit: "CNT" })).toBe("35건");
    expect(previewValue({ id: "d", value: null, unit: "PCT" })).toBe("–");
    expect(previewValue({ id: "e", value: 3, unit: "PCT", stale: true })).toBe("–");
    expect(previewValue({ id: "f", value: 7, unit: "UNKNOWN" })).toBe("7");
  });

  it("종류 순서(분석 화면 → 추적 지표 → 개념 연결) · 처리할 것 먼저로 묶는다", () => {
    const items: ProposalItem[] = [
      { ...base, kind: "concept", id: "c1", datasetName: "나" },
      { ...base, kind: "metric", id: "m1", datasetName: "가" },
      { ...base, kind: "analysis", id: "a1", datasetName: "다", canReview: false },
      { ...base, kind: "analysis", id: "a2", datasetName: "라" },
    ];
    const g = groupByKind(items);
    expect(g.map((x) => x.kind)).toEqual(["analysis", "metric", "concept"]);
    expect(g[0].items.map((x) => x.id)).toEqual(["a2", "a1"]);
    expect(groupByKind([])).toEqual([]);
  });

  it("점수 · 사유 점검", () => {
    expect(scoreText(0.953)).toBe("95%");
    expect(scoreText(null)).toBe("–");
    expect(reasonError(" ")).not.toBeNull();
    expect(reasonError("관련 없음")).toBeNull();
  });
});
