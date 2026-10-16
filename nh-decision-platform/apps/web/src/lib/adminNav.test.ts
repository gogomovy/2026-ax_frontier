import { describe, expect, it } from "vitest";
import { filterAdminGroups } from "./adminNav";
import { refreshConditions, stateLabel } from "./refreshStatus";

const groups = [
  { label: "데이터 반영", items: [{ label: "자료 승인" }, { label: "데이터셋·문서" }] },
  { label: "에이전트 · 자동화", items: [{ label: "자동 실행 · 변경 감지" }, { label: "분석 에이전트" }] },
];

describe("filterAdminGroups (ADM2-03)", () => {
  it("빈 검색어면 그대로", () => {
    expect(filterAdminGroups(groups, "  ")).toBe(groups);
  });
  it("항목 이름 — 공백 무시", () => {
    const out = filterAdminGroups(groups, "변경감지");
    expect(out).toHaveLength(1);
    expect(out[0].items.map((i) => i.label)).toEqual(["자동 실행 · 변경 감지"]);
  });
  it("묶음 이름이 맞으면 묶음 전체", () => {
    expect(filterAdminGroups(groups, "데이터 반영")[0].items).toHaveLength(2);
  });
  it("맞는 것이 없으면 빈 목록", () => {
    expect(filterAdminGroups(groups, "없는메뉴")).toEqual([]);
  });
});

const base = { data: [], team: null, common: false, events: [], rules: [], docClasses: [], any: [], cron: [], upstream: [], downstream: 0 };

describe("refreshConditions (AGW-08)", () => {
  it("정기 실행 · 자료 · 팀 · 공통 · 상위 · 목표 순", () => {
    const out = refreshConditions({
      triggers: { ...base, cron: [{ expr: "40 6 * * *", label: "매일 06:40", next: "", lastFiredAt: null }], data: ["상품별 충당금"], team: "D200", common: true, upstream: ["경영목표 점검"], events: ["경영목표 확정 · 수정"] },
    });
    expect(out).toEqual(["매일 06:40", "자료 변경 시(상품별 충당금)", "우리 팀 새 자료 반영 시", "공통 통합 DB 변경 시", "상위 분석 결과 변경 시(경영목표 점검)", "경영목표 확정 · 수정 시"]);
  });
  it("자료가 많으면 줄인다", () => {
    expect(refreshConditions({ triggers: { ...base, data: ["a", "b", "c", "d"] } })).toEqual(["자료 변경 시(a · b 외 2)"]);
  });
  it("상태 문구", () => {
    expect(stateLabel("held")).toBe("상위 분석 완료 대기 중");
    expect(stateLabel("idle")).toBe("최신 상태");
  });
});
