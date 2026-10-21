import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { DefaultRateTrend, RiskDashboard } from "@/lib/types";

/**
 * 사업부서 현황 — 자료를 올리기 전(값 없는 틀). 서버는 계산 전 판정(severity)을 null 로 비워 보낸다(readiness.gate).
 * 예전에는 없는 판정을 표에서 찾다가 화면 전체가 '화면을 불러오지 못했어요'로 멈췄다 — 판정 자리는 '–' 로 그려야 한다.
 */
vi.mock("next/navigation", () => ({ usePathname: () => "/risk" }));
vi.mock("@/components/providers/SessionProvider", () => ({ useSession: () => ({ menu: null }), useUiConfig: () => ({ scopes: {}, bands: {}, thresholds: {} }) }));
vi.mock("@/components/data/FigureText", async () => {
  const { createElement: h } = await import("react");
  return { FigureText: ({ figure }: { figure: { label: string } }) => h("span", null, figure.label) };
});
// 수치 칸(Fig)은 출처 서랍(UiProvider)을 연다 — 여기서는 화면이 그려지는지만 본다
vi.mock("@/components/providers/UiProvider", () => ({ useUi: () => ({ openSource: () => undefined, showToast: () => undefined }), useConfirm: () => async () => false }));
vi.mock("@/components/data/TermText", async () => {
  const { createElement: h } = await import("react");
  return { TermText: ({ children, text }: { children?: unknown; text?: string }) => h("span", null, (text ?? children) as string) };
});

const fig = (id: string, label: string, unit = "PCT") => ({ id, label, unit, value: null, decimals: 2 });
const seg = (key: string, label: string) => ({ key, label, points: [], latest: fig(`${key}_dr`, `${label} 부도율`), deltaPP: fig(`${key}_d`, `${label} 증감(2025.09 대비)`, "PP"), severity: null });

describe("사업부서 현황 — 계산 전 틀", () => {
  it("판정이 없는(null) 규모도 화면을 그리고 판정 자리는 '–'", async () => {
    const { RiskOverview } = await import("@/components/domain/RiskOverview");
    const dashboard = { asOf: "", computed: false, opinions: [], corpModels: [], retailModels: [], appliedGoals: [] } as unknown as RiskDashboard;
    const trend = { asOf: "", generatedAt: "", computed: false, corpSegments: [seg("large", "대기업"), seg("small", "소기업")], retailPools: [] } as unknown as DefaultRateTrend;
    const html = renderToStaticMarkup(createElement(RiskOverview, { dashboard, trend, tabs: [] }));
    expect(html).toContain("대기업");
    expect(html).toContain("소기업");
    expect(html).toContain('aria-label="판정 없음"');
  });
});
