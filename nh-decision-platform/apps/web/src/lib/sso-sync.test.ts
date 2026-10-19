import { describe, expect, it } from "vitest";
import { buildSsoPageCsp, isSsoPagePath, ncAgentOrigin } from "@/lib/csp";
import { asRuleList, countsLine, syncActionLabel } from "@/lib/dataSync";
import { orgChain } from "@/lib/orgChain";
import { SSO_ERROR, ssoStartHref, strictestLocalLogin } from "@/lib/sso";

describe("가입 화면 — 인사 정보 소속 자동 선택 경로", () => {
  const orgs = [
    { code: "HQ", parent: null },
    { code: "D1", parent: "HQ" },
    { code: "T1", parent: "D1" },
    { code: "ORPHAN", parent: "GONE" },
    { code: "A", parent: "B" },
    { code: "B", parent: "A" },
  ];
  it("최상위 → 소속 순서", () => {
    expect(orgChain(orgs, "T1")).toEqual(["HQ", "D1", "T1"]);
    expect(orgChain(orgs, "HQ")).toEqual(["HQ"]);
  });
  it("없는 조직 · 상위가 목록에 없음 · 순환이면 빈 목록(수동 선택)", () => {
    expect(orgChain(orgs, "NOPE")).toEqual([]);
    expect(orgChain(orgs, "ORPHAN")).toEqual([]);
    expect(orgChain(orgs, "A")).toEqual([]);
  });
});

describe("사내 SSO 중계 페이지 CSP (Phase R)", () => {
  it("중계 페이지 경로만 해당", () => {
    expect(isSsoPagePath("/sso-proxy.html")).toBe(true);
    expect(isSsoPagePath("/nc/NexessDemonFunc.js")).toBe(true);
    expect(isSsoPagePath("/ncx")).toBe(false);
    expect(isSsoPagePath("/login")).toBe(false);
  });
  it("에이전트 출처만 추가로 열고 프레임 · object 는 막는다", () => {
    const csp = buildSsoPageCsp("https://127.0.0.1:13015");
    expect(csp).toContain("script-src 'self' 'unsafe-inline' https://127.0.0.1:13015");
    expect(csp).toContain("connect-src 'self' https://127.0.0.1:13015");
    expect(csp).toContain("frame-ancestors 'none'");
    expect(csp).toContain("object-src 'none'");
    expect(csp).not.toContain("unsafe-eval");
  });
  it("에이전트 출처 설정 — 출처 형식이 아니면 기본값", () => {
    expect(ncAgentOrigin(undefined)).toBe("https://127.0.0.1:13015");
    expect(ncAgentOrigin("https://localhost:14015")).toBe("https://localhost:14015");
    expect(ncAgentOrigin("https://x; script-src *")).toBe("https://127.0.0.1:13015");
  });
});

describe("로그인 화면 SSO", () => {
  it("켜진 SSO 중 가장 좁은 사번 로그인 범위", () => {
    expect(strictestLocalLogin([null, null])).toBe("all");
    expect(strictestLocalLogin([{ enabled: false, label: "", localLogin: "none" }])).toBe("all");
    expect(strictestLocalLogin([{ enabled: true, label: "", localLogin: "admin" }, { enabled: true, label: "", localLogin: "all" }])).toBe("admin");
    expect(strictestLocalLogin([{ enabled: true, label: "", localLogin: "admin" }, { enabled: true, label: "", localLogin: "none" }])).toBe("none");
  });
  it("시작 주소 · 실패 사유", () => {
    expect(ssoStartHref("/backend/auth/nc/init", null)).toBe("/backend/auth/nc/init");
    expect(ssoStartHref("/backend/auth/nc/init", "/hq/goals?a=1")).toBe("/backend/auth/nc/init?next=%2Fhq%2Fgoals%3Fa%3D1");
    for (const code of ["state", "no_ticket", "nonce", "toa", "verify_failed", "verifier_down", "user_not_found", "account", "disabled"]) expect(SSO_ERROR[code]).toBeTruthy();
  });
});

describe("조직 · 인사 동기화 표시", () => {
  it("이력 동작 이름", () => {
    expect(syncActionLabel("admin.sync.organization")).toEqual({ target: "조직", mode: "반영" });
    expect(syncActionLabel("admin.sync.employee.dry_run")).toEqual({ target: "인사", mode: "미리보기" });
    expect(syncActionLabel("admin.sync.settings")).toEqual({ target: "설정", mode: "변경" });
  });
  it("결과 한 줄 — 0 은 뺀다", () => {
    expect(countsLine({ totalProcessed: 1200, inserted: 3, updated: 0, deactivated: 2 }, "employee")).toBe("처리 1,200 · 신규 3 · 사용 중지 2");
    expect(countsLine({ deactivated: 1 }, "organization")).toBe("사용 안 함 1");
    expect(countsLine({}, "organization")).toBe("변경 없음");
    expect(countsLine(null)).toBe("-");
  });
  it("규칙 설정값 읽기", () => {
    expect(asRuleList(null)).toEqual([]);
    expect(asRuleList('[{"corpType":"1"}]')).toEqual([{ corpType: "1" }]);
    expect(asRuleList("{bad")).toBeNull();
    expect(asRuleList({ a: 1 })).toBeNull();
  });
});
