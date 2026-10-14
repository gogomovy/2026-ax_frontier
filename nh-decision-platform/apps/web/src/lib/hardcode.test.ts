/**
 * 화면 하드코딩 감시 (Phase K · 요구사항 §27 HC-06) — 화면 코드(apps/web/src, 시험 제외)에
 * 연도 · 반기 · 분기 · 개년 문구, 목표 id, 판정 숫자, 업무 영역 주소 판정, 규칙 판을 다시 넣으면 실패한다.
 * 그런 값은 산출물(기준일 · 계열 · 라벨)이나 관리자 [화면 설정](ui.*)에서 와야 한다. 예외는 아래 허용 목록에 이유와 함께.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { describe, expect, it } from "vitest";

const ROOT = join(__dirname, "..");

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) return walk(p);
    return /\.(ts|tsx)$/.test(name) && !/\.test\.ts$/.test(name) ? [p] : [];
  });
}

interface Rule {
  name: string;
  re: RegExp;
  /** 허용 — 파일(src 기준 경로) → 이유 */
  allow?: Record<string, string>;
}

const RULES: Rule[] = [
  {
    name: "연도가 박힌 기간 문구 (예: 2025년 · '25년 · 2026 연간)",
    re: /["'`][^"'`\n]*(?:\b20\d\d\s?(?:년|연간|상반기|하반기|\.\dQ)|'\d\d년)/,
  },
  {
    name: "반기 · 분기 고정 문구 (상반기 · 하반기 대비 등)",
    re: /["'`][^"'`\n]*(?:상반기 대비|하반기 업적|\d분기 보고서)/,
  },
  {
    name: "고정 비교 기간 (3개년 · 최근 12개월)",
    re: /["'`>][^"'`\n<]*(?:\b\d+개년|최근 \d+개월)/,
  },
  {
    name: "목표 id 직접 지정 (goal-…)",
    re: /["'`]goal-[a-z][a-z0-9-]*["'`]/,
  },
  {
    name: "판정 경계 숫자 비교 (≥ 75 · 85 · 90 · 100 등) — [화면 설정 › 판정 구간]",
    re: /(?<!length\s?)(?:>=?|<=?)\s*(?:75|85|90|100)\b/,
    allow: {
      [`components${sep}charts${sep}SemiGauge.tsx`]: "게이지 그리기 범위(0~100%) 자르기 — 판정 아님",
      [`components${sep}ui${sep}primitives.tsx`]: "진행 막대 그리기 범위(0~100%) 자르기 — 판정 아님",
      [`components${sep}charts${sep}ShareBars.tsx`]: "기준선 그리기 범위(0~100%) 검사 — 판정 아님",
    },
  },
  {
    name: "주소 접두어로 업무 영역 판정 (startsWith('/risk' · '/hq' · '/branch'))",
    re: /startsWith\(\s*["'`]\/(?:risk|hq|branch|domains)/,
  },
  {
    name: "규칙 코드 · 판 고정 표기 (ATTENTION_SCORE v1 등)",
    re: /[A-Z_]{4,}\s+v\d\b/,
  },
  {
    name: "자료 성격 꾸며 넣기 (dataOrigin: \"simulated\" · ?? \"simulated\")",
    re: /dataOrigin(?:\s*:\s*|\s*\?\?\s*)["'](?:simulated|mixed|actual)["'](?!\s*\|)/,
  },
];

/** 규칙이 비어 있지 않은지 — 예전에 있던 하드코딩 그대로를 잡아야 한다 */
const SAMPLES: string[] = [
  "hint=\"소매여신모형 · '25년 3분기 보고서 지표 체계\"",
  "<p>하반기 업적평가 기준 변경</p> \"상반기 대비 신설\"",
  "<span>3개년 누계</span> hint=\"최근 12개월 · 선행 지표\"",
  "goals.find((g) => g.id === \"goal-corp-growth\")",
  "if (pct >= 85) return warn",
  "if (pathname.startsWith(\"/risk\")) return \"dept\"",
  "<p>ATTENTION_SCORE v1 · 가중합 규칙</p>",
  "dataOrigin: \"simulated\" }",
];

describe("화면 하드코딩 감시 (HC-06)", () => {
  const files = walk(ROOT);
  it("규칙마다 예전 하드코딩 표본을 잡는다", () => {
    for (const rule of RULES) expect(SAMPLES.some((x) => rule.re.test(x)), rule.name).toBe(true);
  });
  it("검사할 화면 코드가 있다", () => {
    expect(files.length).toBeGreaterThan(50);
  });
  for (const rule of RULES) {
    it(rule.name, () => {
      const hits: string[] = [];
      for (const f of files) {
        const rel = relative(ROOT, f);
        if (rule.allow?.[rel]) continue;
        const lines = readFileSync(f, "utf8").split(/\r?\n/);
        lines.forEach((line, i) => {
          const code = line.replace(/\/\/.*$/, "").replace(/\/\*.*?\*\//g, "");
          if (/^\s*(\*|\/\/|\/\*)/.test(line)) return; // 주석 줄
          if (rule.re.test(code)) hits.push(`${rel}:${i + 1}: ${line.trim().slice(0, 160)}`);
        });
      }
      expect(hits, hits.join("\n")).toEqual([]);
    });
  }
});
