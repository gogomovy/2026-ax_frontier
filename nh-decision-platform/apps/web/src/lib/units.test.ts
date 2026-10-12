import { describe, expect, it } from "vitest";
import { nextFocusIndex } from "@/lib/a11y";
import { navHrefWithOffice, officeFromSearch, officeParam, withOffice } from "@/lib/branchOffice";
import { buildCsp, newNonce } from "@/lib/csp";
import { formatFigure, formatKstDateTime, formatSigned, toneOfDelta } from "@/lib/format";
import { safeNext } from "@/lib/safe-next";
import type { Figure } from "@/lib/types";

const fig = (value: number | null, unit: Figure["unit"], decimals?: number): Figure => ({ id: "f", label: "x", value, unit, decimals, dataOrigin: "simulated" });

describe("safeNext — 열린 리디렉션 차단", () => {
  it("같은 사이트 상대 경로는 그대로", () => {
    expect(safeNext("/hq/goals?tab=1")).toBe("/hq/goals?tab=1");
  });
  it.each(["//evil.example", "/\\evil.example", "https://evil.example", "/a b", "/\u0000x", "", null, undefined, "/" + "a".repeat(400)])("거부: %s", (v) => {
    expect(safeNext(v as string | null)).toBeNull();
  });
});

describe("CSP nonce", () => {
  it("요청마다 다른 128비트 nonce", () => {
    const a = newNonce();
    const b = newNonce();
    expect(a).not.toBe(b);
    expect(atob(a)).toHaveLength(16);
  });
  it("운영 정책 — nonce + strict-dynamic, unsafe-inline · unsafe-eval 없음, 프레임 금지", () => {
    const csp = buildCsp("abc", false);
    const script = csp.split("; ").find((d) => d.startsWith("script-src"));
    expect(script).toBe("script-src 'self' 'nonce-abc' 'strict-dynamic'");
    expect(csp).toContain("frame-ancestors 'none'");
    expect(csp).toContain("object-src 'none'");
    expect(buildCsp("abc", true)).toContain("'unsafe-eval'");
  });
});

describe("포커스 순환", () => {
  it("끝에서 처음으로, 처음에서 끝으로", () => {
    expect(nextFocusIndex(2, 3, false)).toBe(0);
    expect(nextFocusIndex(0, 3, true)).toBe(2);
    expect(nextFocusIndex(1, 3, false)).toBe(2);
  });
  it("대화상자 밖에서 들어오면 처음(앞으로) · 끝(뒤로)", () => {
    expect(nextFocusIndex(-1, 4, false)).toBe(0);
    expect(nextFocusIndex(-1, 4, true)).toBe(3);
  });
  it("요소가 없으면 -1", () => {
    expect(nextFocusIndex(0, 0, false)).toBe(-1);
  });
});

describe("수치 표기", () => {
  it("값이 없으면 미제공(또는 지정 문구)", () => {
    expect(formatFigure(fig(null, "PCT"))).toBe("미제공");
    expect(formatFigure({ ...fig(null, "PCT"), undefinedLabel: "데이터 미제공" })).toBe("데이터 미제공");
  });
  it("비율 · 퍼센트포인트 단위와 소수 자리", () => {
    expect(formatFigure(fig(9.1575, "PCT", 2))).toBe("9.16%");
    expect(formatSigned(fig(0.5, "PP", 1))).toBe("+0.5%p");
    expect(formatSigned(fig(-0.46, "PP", 2))).toBe("-0.46%p");
  });
  it("증감 색 방향", () => {
    expect(toneOfDelta(1)).toBe("good");
    expect(toneOfDelta(1, false)).toBe("bad");
    expect(toneOfDelta(0)).toBe("neutral");
  });
});

describe("KST 시각 표기 — 서버 · 브라우저 같은 글자 (B.41 · #418)", () => {
  it("자정 시간대는 00 시 (Node 20 Intl hour12:false 는 24 시로 그려 하이드레이션이 어긋났다)", () => {
    expect(formatKstDateTime("2026-10-11T15:11:00+00:00")).toBe("10. 12. 00:11");
    expect(formatKstDateTime("2026-10-11T15:00:59.123456+00:00")).toBe("10. 12. 00:00");
  });
  it("UTC → KST 날짜 넘김 · 월 경계 · 다른 시간대 표기", () => {
    expect(formatKstDateTime("2026-10-11T05:07:00Z")).toBe("10. 11. 14:07");
    expect(formatKstDateTime("2026-09-30T23:30:00Z")).toBe("10. 01. 08:30");
    expect(formatKstDateTime("2026-10-12T00:11:00+09:00")).toBe("10. 12. 00:11");
  });
  it("시간대 없는 시각은 UTC 로 본다 — 실행 환경 시간대와 무관", () => {
    expect(formatKstDateTime("2026-10-11T15:11:00")).toBe("10. 12. 00:11");
  });
  it("빈 값 · 해석 불가 값", () => {
    expect(formatKstDateTime("")).toBe("");
    expect(formatKstDateTime("not-a-date")).toBe("not-a-date");
  });
});

describe("영업점 지점 인자(B.47)", () => {
  it("형식이 맞는 값만 쓴다", () => {
    expect(officeParam({ office: "001068" })).toBe("001068");
    expect(officeParam({ office: ["00X_1", "b"] })).toBe("00X_1");
    expect(officeParam({ office: "../x" })).toBeNull();
    expect(officeParam({ office: "a".repeat(21) })).toBeNull();
    expect(officeParam({})).toBeNull();
    expect(officeParam(undefined)).toBeNull();
  });
  it("이동 주소에 이어 붙인다", () => {
    expect(withOffice("/branch", null)).toBe("/branch");
    expect(withOffice("/branch/analysis", "001234")).toBe("/branch/analysis?office=001234");
    expect(withOffice("/branch?x=1", "A B")).toBe("/branch?x=1&office=A%20B");
  });
  it("사이드바 — 주소의 지점을 영업점 메뉴에만", () => {
    expect(officeFromSearch("?office=001234&x=1")).toBe("001234");
    expect(officeFromSearch("?office=%3Cx%3E")).toBeNull();
    expect(officeFromSearch("")).toBeNull();
    expect(navHrefWithOffice("/branch/analysis", "001234")).toBe("/branch/analysis?office=001234");
    expect(navHrefWithOffice("/knowledge", "001234")).toBe("/knowledge");
    expect(navHrefWithOffice("/branch", null)).toBe("/branch");
  });
});
