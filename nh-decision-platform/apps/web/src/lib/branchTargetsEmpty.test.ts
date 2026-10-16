import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { BranchTarget } from "@/lib/types";
/**
 * 영업점 '본부 전파 목표·가이드' — 우리 지역본부로 전파된 목표가 0건일 때의 빈 상태.
 * 지역본부 필터(c85c6ff) 뒤로 D400 · D500 아래 영업점은 목록이 비므로, 카드 자리에 안내가 떠야 한다.
 */
const targets = vi.hoisted(() => ({ list: [] as unknown[] }));
vi.mock("@/lib/data", () => ({ getBranchTargets: async () => targets.list }));
// 같은 화면의 다른 섹션은 이 검사와 무관하다 — 공급자(context)가 필요한 클라이언트 컴포넌트라 비워 둔다
vi.mock("@/components/domain/BranchGuides", () => ({ BranchGuides: () => null }));
vi.mock("@/components/domain/ReportRequestForm", () => ({ ReportRequestForm: () => null }));
vi.mock("@/components/layout/PageHeader", () => ({ PageHeader: () => null }));
// 수치 표기는 표시 단위 설정(UiProvider)을 읽는다 — 여기서는 값이 그려지는지만 본다
vi.mock("@/components/data/FigureText", async () => {
  const { createElement } = await import("react");
  return { FigureText: ({ figure }: { figure: { label: string } }) => createElement("span", null, figure.label) };
});
async function render() {
  const { default: Page } = await import("@/app/branch/targets/page");
  return renderToStaticMarkup(await Page());
}
describe("본부 전파 목표 빈 상태", () => {
  beforeEach(() => {
    targets.list = [];
  });
  it("0건이면 섹션 머리(0건)는 두고 빈 상태 안내를 status로 보인다", async () => {
    const html = await render();
    expect(html).toContain("전파된 목표");
    expect(html).toContain("0건");
    expect(html).toMatch(/role="status"[^>]*>[\s\S]*아직 전파된 본부 목표가 없어요/);
    expect(html).toContain("종합기획부가 경영목표를 확정하고 우리 지역본부로 전파하면 여기에 표시돼요.");
    // 영업점 직원에게 종합기획부 화면으로 가는 버튼은 두지 않는다
    expect(html).not.toContain("<a ");
    expect(html).not.toContain("<button");
  });
  it("목표가 있으면 빈 상태 없이 카드만 보인다", async () => {
    const t: BranchTarget = {
      id: "t1",
      orgCode: "D300",
      orgName: "수도권1지역본부",
      periodLabel: "2026 하반기",
      metricLabel: "기업여신 신규 취급액",
      title: "기업여신 신규 취급 1.24조원",
      target: { id: "f1", label: "1.24조원", value: 1.24, unit: "KRW_TN", dataOrigin: "actual" },
      guideline: "5C 이상 차주 중심 취급",
      sourceGoalTitle: "기업여신 확대",
      sourcePlanTitle: "기업여신 확대 실행방안",
    };
    targets.list = [t];
    const html = await render();
    expect(html).toContain("1건 · 수도권1지역본부");
    expect(html).toContain("기업여신 신규 취급 1.24조원");
    expect(html).not.toContain("아직 전파된 본부 목표가 없어요");
  });
});
