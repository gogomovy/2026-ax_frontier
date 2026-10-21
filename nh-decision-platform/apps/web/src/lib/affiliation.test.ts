import { describe, expect, it } from "vitest";
import { defaultPick, orgLine, screensLine, switchGroup, type AffGroup, type AffOption } from "./affiliation";

const opt = (code: string, name: string, path: string[] = []): AffOption => ({ code, name, unitType: null, unitLabel: "조직", active: true, path });
const GROUPS: AffGroup[] = [
  { key: "hq", label: "종합기획부", options: [opt("D100", "종합기획부", ["경영본부"])], search: null },
  { key: "dept", label: "사업부서", options: [opt("D200", "신용리스크관리부"), opt("D300", "여신기획부")], search: null },
  { key: "region", label: "영업본부", options: [opt("R1", "서울영업본부")], search: null },
  { key: "branch", label: "영업점", options: [], search: { types: ["BRANCH"] } },
];

describe("업무 소속 — 승인 대화상자", () => {
  it("처음 값 — 추천 단위, 없으면 신청 소속(직접 선택)", () => {
    expect(defaultPick(null)).toBeNull();
    expect(defaultPick({ suggested: { group: "dept", label: "사업부서", code: "D200" }, current: opt("T201", "리스크팀") })).toEqual({ group: "dept", code: "D200" });
    expect(defaultPick({ suggested: null, current: opt("X9", "인사조직") })).toEqual({ group: "custom", code: "X9" });
  });

  it("영역 바꾸기 — 그 영역에 지금 단위가 있으면 유지, 하나뿐이면 그것, 여럿 · 검색이면 고르게 비움", () => {
    expect(switchGroup(GROUPS, { group: "custom", code: "D300" }, "dept")).toEqual({ group: "dept", code: "D300" });
    expect(switchGroup(GROUPS, { group: "dept", code: "D200" }, "hq")).toEqual({ group: "hq", code: "D100" });
    expect(switchGroup(GROUPS, { group: "hq", code: "D100" }, "dept")).toEqual({ group: "dept", code: "D200" });
    expect(switchGroup(GROUPS, { group: "hq", code: "D100" }, "branch")).toEqual({ group: "branch", code: "" });
    expect(switchGroup(GROUPS, { group: "dept", code: "D200" }, "custom")).toEqual({ group: "custom", code: "D200" });
  });

  it("표시 — 조직 경로 · 화면 줄", () => {
    expect(orgLine(opt("T1", "기업금융팀", ["여신본부", "기업여신부"]))).toBe("여신본부 > 기업여신부 > 기업금융팀");
    expect(orgLine(null)).toBe("-");
    const s = ["현황", "분석", "목표", "보고", "실행", "검증", "알림"].map((label) => ({ label }));
    expect(screensLine(s)).toBe("현황 · 분석 · 목표 · 보고 · 실행 · 검증 외 1개");
    expect(screensLine(s.slice(0, 2))).toBe("현황 · 분석");
    expect(screensLine([])).toBe("");
  });
});
