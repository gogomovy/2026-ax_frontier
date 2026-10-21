import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { describe, expect, it } from "vitest";
import { buildCsp, buildSsoPageCsp } from "@/lib/csp";

/**
 * 폐쇄망 — 브라우저가 외부 인터넷 주소(CDN · 글꼴 · 분석 스크립트)를 부르지 않게 지킨다.
 * 화면 코드 · 스타일 · 정적 파일에 외부 주소가 들어오면 실패한다. 아래는 부르지 않는 글자(이름공간 · 입력 예시)만 허용.
 */
const ALLOWED_HOSTS = [
  "www.w3.org", // SVG · XHTML 이름공간(요청하지 않음)
  "localhost",
  "127.0.0.1",
];
const ALLOWED_SUFFIX = [".example", ".example.com"]; // 입력칸 예시 · 시험 문자열
const ROOTS = ["src", "public"];
const EXT = /\.(tsx?|css|html|js|mjs|json)$/;
const SKIP = /\.test\.tsx?$/;

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const p = join(dir, name);
    return statSync(p).isDirectory() ? files(p) : EXT.test(p) && !SKIP.test(p) ? [p] : [];
  });
}

/** 점이 없는 이름(예: http://elasticsearch:9200 · http://vllm:8000)은 클러스터 안 서비스 이름이라 인터넷이 아니다 */
const allowed = (host: string) => !host.includes(".") || ALLOWED_HOSTS.includes(host) || ALLOWED_SUFFIX.some((s) => host.endsWith(s));

describe("폐쇄망 — 외부 주소 없음", () => {
  it("화면 코드 · 스타일 · 정적 파일에 외부 인터넷 주소가 없다", () => {
    const found: string[] = [];
    for (const root of ROOTS) {
      for (const f of files(root)) {
        const text = readFileSync(f, "utf8");
        for (const m of text.matchAll(/https?:\/\/([A-Za-z0-9.-]+)/g)) {
          if (!allowed(m[1].toLowerCase())) found.push(`${relative(".", f)} → ${m[0]}`);
        }
      }
    }
    expect(found).toEqual([]);
  });

  it("CSP 는 외부 출처를 열지 않는다(SSO 중계 페이지는 PC 의 NC 에이전트만)", () => {
    const hosts = (csp: string) => Array.from(csp.matchAll(/https?:\/\/[^\s;]+/g)).map((m) => m[0]);
    expect(hosts(buildCsp("n", false))).toEqual([]);
    expect(hosts(buildSsoPageCsp("https://127.0.0.1:13015"))).toEqual(["https://127.0.0.1:13015", "https://127.0.0.1:13015"]);
  });
});
