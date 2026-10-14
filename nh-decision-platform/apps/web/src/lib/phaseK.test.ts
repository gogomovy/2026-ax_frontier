/**
 * Phase K (요구사항 §27) — 화면 설정 판정 · 목표 역할 · 업무 영역 단위(부서 · 지점) · 레드닷 '봤음' 서명.
 * 값은 시험 입력(임의) — 화면 수치가 아니라 함수 규칙을 본다.
 */
import { describe, expect, it } from "vitest";
import type { MenuPayload, MenuSection } from "@/components/providers/SessionProvider";
import { focusUnit, officeHrefOf, scopeOfPath, scopesFromMenu } from "@/lib/scopeModel";
import { isFresh, signatureOf, tabSignature } from "@/lib/seen";
import { EMPTY_CONFIG, bandOf, goalByRole, threshold, type Band, type UiConfig } from "@/lib/uiConfig";

const BANDS: Band[] = [
  { max: 80, label: "정상", tone: "neutral" },
  { max: 95, label: "근접", tone: "attention" },
  { max: null, label: "초과", tone: "critical" },
];

describe("판정 구간 — 값이 상한 미만인 첫 구간", () => {
  it.each([
    [0, "정상"],
    [79.99, "정상"],
    [80, "근접"],
    [94.9, "근접"],
    [95, "초과"],
    [300, "초과"],
  ])("%s → %s", (v, want) => {
    expect(bandOf(v, BANDS)?.label).toBe(want);
  });
  it("값 · 구간이 없으면 판정하지 않는다(화면 기본값 없음)", () => {
    expect(bandOf(null, BANDS)).toBeNull();
    expect(bandOf(Number.NaN, BANDS)).toBeNull();
    expect(bandOf(50, undefined)).toBeNull();
    expect(bandOf(50, [])).toBeNull();
  });
  it("기준값 · 목표 역할도 설정에서만", () => {
    const cfg: UiConfig = { ...EMPTY_CONFIG, thresholds: { planPaceTolerancePp: 3 }, goalRoles: { corpGrowth: "g-2", hhLimit: null } };
    expect(threshold(cfg, "planPaceTolerancePp")).toBe(3);
    expect(threshold(cfg, "headroomAlert")).toBeNull();
    const goals = [{ id: "g-1" }, { id: "g-2" }];
    expect(goalByRole(goals, cfg, "corpGrowth")?.id).toBe("g-2");
    expect(goalByRole(goals, cfg, "hhLimit")).toBeUndefined();
    expect(goalByRole(goals, EMPTY_CONFIG, "bankRevenue")).toBeUndefined();
  });
});

const item = (label: string, href: string, extra: Partial<{ step: number; exact: boolean }> = {}) => ({ code: label, label, href, match: [extra.exact ? `=${href}` : href], step: extra.step ?? null, countKey: null });
const section = (s: Partial<MenuSection> & { section: string }): MenuSection => ({ admin: false, flow: [], reference: [], scope: null, orgCode: null, orgName: s.section, ...s });

function menuOf(sections: MenuSection[], config: Partial<UiConfig>): MenuPayload {
  return {
    user: { empNo: "1", name: "시험", role: "admin", org: { code: "X", name: "X" }, orgPath: [] },
    home: "/",
    sections,
    screens: [],
    counts: {},
    asOf: "2026-08-31",
    batchLabel: "",
    config: { ...EMPTY_CONFIG, ...config },
  };
}

describe("업무 영역 = 종류 × 단위 (SCP-01~03)", () => {
  const sections = [
    section({ section: "기획부", scope: "hq", orgCode: "H1", flow: [item("현황", "/a/overview", { step: 1 })] }),
    section({ section: "리스크부", scope: "dept", orgCode: "D1", flow: [item("현황", "/d1", { step: 1, exact: true }), item("분석", "/d1/analysis", { step: 2 })] }),
    section({ section: "여신부", scope: "dept", orgCode: "D2", flow: [item("현황", "/d2", { step: 1, exact: true })] }),
    section({ section: "영업점", scope: "branch", flow: [item("현황", "/b", { step: 1, exact: true }), item("분석", "/b/analysis", { step: 2 })] }),
    section({ section: "공통", reference: [item("데이터베이스", "/knowledge")] }),
  ];
  const config: Partial<UiConfig> = {
    scopes: {
      hq: { label: "종기", units: [{ code: "H1", name: "기획부", section: "기획부", home: "/a/overview", available: true }] },
      dept: {
        label: "부서",
        units: [
          { code: "D1", name: "리스크부", section: "리스크부", home: "/d1", available: true },
          { code: "D2", name: "여신부", section: "여신부", home: "/d2", available: true },
          { code: "D3", name: "수신부", section: "수신부", home: null, available: false },
        ],
      },
      branch: { label: "지점", units: [{ code: null, name: "영업점", section: "영업점", home: "/b", available: true }] },
    },
    offices: { offices: [{ code: "001", name: "가지점", available: true, primary: true }, { code: "002", name: "나지점", available: true, primary: false }], default: "001" },
  };

  it("같은 종류의 묶음은 한 영역의 단위로, 화면 없는 부서는 준비 중", () => {
    const scopes = scopesFromMenu(menuOf(sections, config), null);
    expect(scopes.map((s) => s.id)).toEqual(["hq", "dept", "branch"]); // 공통(흐름 없음)은 영역이 아니다
    const dept = scopes.find((s) => s.kind === "dept")!;
    expect(dept.label).toBe("부서");
    expect(dept.units.map((u) => [u.name, u.available])).toEqual([["리스크부", true], ["여신부", true], ["수신부", false]]);
    expect(dept.units[2].home).toBeNull();
  });
  it("주소로 부서를 맞춘다 — 영역 판정에 주소 접두어를 쓰지 않는다", () => {
    const scopes = scopesFromMenu(menuOf(sections, config), null).map((s) => focusUnit(s, "/d2"));
    const cur = scopeOfPath(scopes, "/d2");
    expect(cur?.kind).toBe("dept");
    expect(cur?.orgName).toBe("여신부");
    expect(cur?.flow.map((i) => i.href)).toEqual(["/d2"]);
    expect(scopeOfPath(scopes, "/knowledge")).toBeNull(); // 공통 화면 — 마지막 영역 유지
  });
  it("영업점 단위 = 지점 — 주소의 지점(없으면 기본)이 현재, 링크에 지점을 잇는다", () => {
    const b1 = scopesFromMenu(menuOf(sections, config), null).find((s) => s.kind === "branch")!;
    expect(b1.units.map((u) => u.home)).toEqual(["/b?office=001", "/b?office=002"]);
    expect(b1.orgName).toBe("가지점");
    const b2 = scopesFromMenu(menuOf(sections, config), "002").find((s) => s.kind === "branch")!;
    expect(b2.orgName).toBe("나지점");
    const href = officeHrefOf({ current: b2 });
    expect(href(b2.flow[1])).toBe("/b/analysis?office=002");
    expect(href(item("데이터베이스", "/knowledge") as never)).toBe("/knowledge"); // 영업점 화면이 아니면 잇지 않는다
  });
  it("지점이 하나뿐이면 전환 메뉴 없이", () => {
    const one = { ...config, offices: { offices: [{ code: "001", name: "가지점", available: true, primary: true }], default: "001" } };
    const b = scopesFromMenu(menuOf(sections, one), null).find((s) => s.kind === "branch")!;
    expect(b.units).toHaveLength(1);
  });
});

describe("레드닷 '봤음' 서명 (DOT-01)", () => {
  it("순서가 달라도 같은 내용이면 같은 서명, 내용이 없으면 서명 없음", () => {
    expect(signatureOf(["b", "a"], "2026-08-31")).toBe(signatureOf(["a", "b"], "2026-08-31"));
    expect(signatureOf([], "2026-08-31")).toBe("");
    expect(signatureOf(["a"], "2026-08-31")).not.toBe(signatureOf(["a"], "2026-09-30")); // 새 기준일 = 새것
  });
  it("기록이 없거나 다르면 새것, 같으면 숨김, 서버 렌더(null)에서는 그리지 않는다", () => {
    const sig = signatureOf(["i-1"], "2026-08-31");
    expect(isFresh({}, "k", sig)).toBe(true);
    expect(isFresh({ k: sig }, "k", sig)).toBe(false);
    expect(isFresh({ k: "old" }, "k", sig)).toBe(true);
    expect(isFresh(null, "k", sig)).toBe(false);
    expect(isFresh({}, "k", "")).toBe(false);
  });
  it("분석 탭 서명 — 이슈 · 심각도 · 생성 시각이 바뀌면 새것", () => {
    const t = { insightId: "i", severity: "critical", generatedAt: "2026-09-01T09:00", asOf: "2026-08-31" };
    expect(tabSignature(t)).not.toBe(tabSignature({ ...t, generatedAt: "2026-09-02T09:00" }));
    expect(tabSignature(t)).not.toBe(tabSignature({ ...t, severity: "caution" }));
  });
});
