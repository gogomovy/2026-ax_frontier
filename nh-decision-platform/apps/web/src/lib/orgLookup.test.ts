import { describe, expect, it } from "vitest";
import { buildOrgTree, orgLookupPath, orgMatches, orgOptionText } from "./orgLookup";
import { pageRange, usersPath } from "./usersQuery";

const org = (code: string, parent: string | null, sort = 0, name = code) => ({ code, name, parent, sort });

describe("조직 검색 · 트리 (대량 조직)", () => {
  it("검색 주소 — 빈 값은 빼고, limit 은 1~100", () => {
    expect(orgLookupPath({})).toBe("/admin/orgs/lookup");
    expect(orgLookupPath({ q: "강남 지점", types: ["DEPT", "REGION"], exclude: "R1", inactive: true, limit: 500 })).toBe(
      "/admin/orgs/lookup?q=%EA%B0%95%EB%82%A8+%EC%A7%80%EC%A0%90&types=DEPT%2CREGION&exclude=R1&inactive=true&limit=100",
    );
    expect(orgLookupPath({ codes: ["A", "B"], limit: 2 })).toBe("/admin/orgs/lookup?codes=A%2CB&limit=2");
    expect(orgOptionText({ path: ["여신본부", "기업여신부"] })).toBe("여신본부 > 기업여신부");
  });

  it("트리 순서 · 하위 수 · 경로 — 상위가 없거나 순환하는 조직도 빠지지 않는다", () => {
    const t = buildOrgTree([org("B2", "R", 2), org("R", null), org("B1", "R", 1), org("T", "B1"), org("X", "GONE"), org("C1", "C2"), org("C2", "C1")]);
    expect(t.order.map((o) => o.code)).toEqual(["R", "B1", "T", "B2", "X", "C1", "C2"]);
    expect(t.below.get("R")).toBe(3);
    expect(t.below.get("B1")).toBe(1);
    expect(t.below.get("T")).toBe(0);
    expect(t.path("T").map((o) => o.code)).toEqual(["R", "B1", "T"]);
    expect(t.kids.get(null)?.map((o) => o.code)).toEqual(["R", "X"]);
  });

  it("수천 곳도 한 번에 — 깊은 트리에서 호출 스택이 넘치지 않는다", () => {
    const deep = Array.from({ length: 20000 }, (_, i) => org(`N${i}`, i ? `N${i - 1}` : null));
    const t = buildOrgTree(deep);
    expect(t.order).toHaveLength(20000);
    expect(t.below.get("N0")).toBe(19999);
  });

  it("검색 — 낱말마다 이름 · 코드 · 상위 조직 이름 어딘가에", () => {
    const o = { name: "강남지점", code: "BR301" };
    expect(orgMatches(o, ["서울지역본부"], "")).toBe(true);
    expect(orgMatches(o, ["서울지역본부"], "서울 강남")).toBe(true);
    expect(orgMatches(o, ["서울지역본부"], "br301")).toBe(true);
    expect(orgMatches(o, ["서울지역본부"], "부산 강남")).toBe(false);
  });
});

describe("사용자 목록 조회 (서버 페이지)", () => {
  it("주소 — 첫 쪽 · 빈 검색어는 빼고", () => {
    expect(usersPath({ status: "pending", size: 50 })).toBe("/admin/users?status=pending&size=50");
    expect(usersPath({ status: "all", q: "홍길동", org: "D100", page: 3, size: 50 })).toBe("/admin/users?status=all&q=%ED%99%8D%EA%B8%B8%EB%8F%99&org=D100&page=3&size=50");
  });

  it("보이는 순번 · 쪽 수", () => {
    expect(pageRange(1, 50, 0)).toEqual({ from: 0, to: 0, pages: 1 });
    expect(pageRange(1, 50, 35)).toEqual({ from: 1, to: 35, pages: 1 });
    expect(pageRange(3, 50, 120)).toEqual({ from: 101, to: 120, pages: 3 });
    expect(pageRange(9, 50, 120)).toEqual({ from: 101, to: 120, pages: 3 });
  });
});
