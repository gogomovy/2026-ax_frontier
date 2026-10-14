import { describe, expect, it } from "vitest";
import { qualityLabel, runStatusLabel, statusLabel } from "@/lib/labels";
import { activeHref, type NavItem } from "@/lib/nav";
import { passwordRuleError } from "@/lib/password";
import { acceptsFile, confidentSuggestion, formatBytes, kindOf, suggestDatasets, titleFromFile } from "@/lib/upload-match";

/* Phase E — 업로드 추천 · 현재 위치 · 표기 */
const DS = [
  { code: "PROVISION_BY_PRODUCT", name: "7790 상품별 충당금", filePattern: String.raw`\((\d{6})\)7790_상품별_충당금\.(xlsx|csv|json)` },
  { code: "PL_PRODUCT_SEGMENT", name: "2633 상품부문별 손익계산서", filePattern: String.raw`\((\d{6})\)2633_상품부문별손익계산서\.(xlsx|csv|json)` },
  { code: "LOAN_BALANCE_MONTHLY", name: "2020 과목별 월별 여신현황", filePattern: String.raw`\((\d{6})\)2020 과목별 월별 여신현황\.(xlsx|csv|json)` },
  { code: "OBLG_GRD_DEF", name: "기업 익스포저 차주별 현황 (Oblg_grd_def)", filePattern: String.raw`Oblg_grd_def_(\d{6})\.(xlsx|csv|json)` },
  { code: "PEER_BANK_STATS", name: "타행 비교 통계 (외부)", filePattern: null },
  { code: "BROKEN", name: "깨진 규칙", filePattern: "(?P<ym>\\d{6})" },
];
const ACCEPT = { dataset: ".csv,.tsv,.xlsx,.json", document: ".pdf,.hwpx,.hwp,.txt,.md,.html" };

describe("파일 이름 → 자료 추천 (UXF-02)", () => {
  it("이름 규칙 + 보고서 번호가 맞으면 1순위 · 확실", () => {
    const s = suggestDatasets("(202608)7790_상품별_충당금.xlsx", DS);
    expect(s[0].code).toBe("PROVISION_BY_PRODUCT");
    expect(s[0].reasons.join(" ")).toContain("파일 이름 규칙 일치");
    expect(s[0].reasons.join(" ")).toContain("7790");
    expect(confidentSuggestion(s)?.code).toBe("PROVISION_BY_PRODUCT");
  });
  it("규칙과 다른 이름이어도 보고서 번호로 찾는다", () => {
    const s = suggestDatasets("2633 손익 8월 정정본.xlsx", DS);
    expect(s[0].code).toBe("PL_PRODUCT_SEGMENT");
    expect(confidentSuggestion(s)).not.toBeNull();
  });
  it("코드가 들어 있으면(대소문자 · 밑줄 무시) 찾는다", () => {
    expect(suggestDatasets("oblg_grd_def_202609.csv", DS)[0].code).toBe("OBLG_GRD_DEF");
    expect(suggestDatasets("PEER-BANK-STATS 2026Q3.csv", DS)[0].code).toBe("PEER_BANK_STATS");
  });
  it("낱말만 겹치면 확실하지 않음 · 맞는 게 없으면 빈 목록", () => {
    const s = suggestDatasets("상품별 정리.xlsx", DS);
    expect(s.length).toBeGreaterThan(0);
    expect(confidentSuggestion(s)).toBeNull();
    expect(suggestDatasets("회의록.xlsx", DS)).toEqual([]);
  });
  it("브라우저에서 못 읽는 정규식은 건너뛴다", () => {
    expect(() => suggestDatasets("202608.xlsx", DS)).not.toThrow();
  });
  it("확장자로 정형 · 문서 구분, 제목 · 크기 표기", () => {
    expect(kindOf("a.XLSX", ACCEPT)).toBe("dataset");
    expect(kindOf("정책.hwpx", ACCEPT)).toBe("document");
    expect(kindOf("사진.png", ACCEPT)).toBeNull();
    expect(acceptsFile("x.tsv", ACCEPT.dataset)).toBe(true);
    expect(acceptsFile("x.pdf", ACCEPT.dataset)).toBe(false);
    expect(titleFromFile("2026_하반기_경영전략회의 결과.pdf")).toBe("2026 하반기 경영전략회의 결과");
    expect(formatBytes(512)).toBe("512B");
    expect(formatBytes(1536)).toBe("1.5KB");
    expect(formatBytes(3 * 1024 * 1024)).toBe("3.0MB");
  });
});

describe("사이드바 현재 위치 하나 (NAV-03)", () => {
  const items: NavItem[] = [
    { label: "데이터베이스", href: "/knowledge", match: ["/knowledge"] },
    { label: "자료 올리기", href: "/knowledge/upload", match: ["/knowledge/upload"] },
    { label: "현황", href: "/risk", match: ["/risk"], exact: true },
    { label: "분석 결과", href: "/risk/analysis", match: ["/risk/analysis"] },
    { label: "관리자 홈", href: "/admin", match: ["/admin"], exact: true },
    { label: "운영 개요", href: "/admin/monitor", match: ["/admin/monitor"], exact: true },
    { label: "데이터 흐름", href: "/admin/monitor/flow", match: ["/admin/monitor/flow"] },
  ];
  it.each([
    ["/knowledge/upload", "/knowledge/upload"],
    ["/knowledge", "/knowledge"],
    ["/knowledge/gov_policy", "/knowledge"],
    ["/risk", "/risk"],
    ["/risk/analysis/abc", "/risk/analysis"],
    ["/admin", "/admin"],
    ["/admin/monitor/flow", "/admin/monitor/flow"],
    ["/hq/overview", null],
  ])("%s → %s", (path, want) => {
    expect(activeHref(items, path)).toBe(want);
  });
});

describe("상태 표기 (TXT-01)", () => {
  it("실행 · 품질 상태를 한국어로, 모르는 값은 그대로", () => {
    expect(runStatusLabel("degraded")).toBe("축소 동작");
    expect(runStatusLabel("succeeded")).toBe("성공");
    expect(runStatusLabel("failed")).toBe("실패");
    expect(runStatusLabel(null)).toBe("-");
    expect(qualityLabel("passed")).toBe("통과");
    expect(qualityLabel("warning")).toBe("주의");
    expect(qualityLabel("weird")).toBe("weird");
  });
  it("관리 화면 상태 배지 기본 표기", () => {
    expect(statusLabel("committed")).toBe("확정");
    expect(statusLabel("rolled_back")).toBe("되돌림");
    expect(statusLabel("running")).toBe("실행 중");
    expect(statusLabel("active")).toBe("사용");
    expect(statusLabel(undefined)).toBe("-");
    expect(statusLabel("custom_x")).toBe("custom_x");
  });
});

describe("비밀번호 정책 (INT-01 · 서버 password_policy_error 와 같음)", () => {
  it.each([
    ["abc123", "8자 이상이어야 합니다"],
    ["abcdefgh", "영문과 숫자를 함께 넣으세요"],
    ["12345678", "영문과 숫자를 함께 넣으세요"],
    ["abcd1234", null],
    ["가".repeat(30) + "a1", "너무 깁니다(72바이트 이하)"],
  ])("%s → %s", (pw, want) => {
    expect(passwordRuleError(pw)).toBe(want);
  });
});
