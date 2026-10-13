// 자동 접근성 점검 (B.34) — axe-core 로 주요 화면의 WCAG 2.1 A · AA 자동 규칙 위반을 찾는다.
//   make a11y   (또는  cd apps/e2e && E2E_ADMIN_EMP=... E2E_ADMIN_PW=... node a11y.mjs)
//
// 자동 점검은 WCAG 준수를 판정하지 않는다 — 대비 · 이름 · 구조 같은 기계로 볼 수 있는 규칙만 본다.
// 화면 낭독기 · 키보드 전용 실사용 테스트와 전문가 검토는 별도로 필요하다.
// 기본은 serious · critical 위반이 있으면 실패. A11Y_LEVEL=moderate 로 기준을 낮출 수 있다.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createRequire } from "node:module";
import puppeteer from "puppeteer";

const require = createRequire(import.meta.url);
const AXE = fs.readFileSync(require.resolve("axe-core/axe.min.js"), "utf8");
const BASE = process.env.E2E_BASE ?? "http://localhost:3000";
const ADMIN = process.env.E2E_ADMIN_EMP;
const ADMIN_PW = process.env.E2E_ADMIN_PW;
const OUT = process.env.E2E_OUT ?? path.join(os.tmpdir(), "nhdip-e2e");
const LEVELS = { minor: 0, moderate: 1, serious: 2, critical: 3 };
const MIN = LEVELS[process.env.A11Y_LEVEL ?? "serious"] ?? 2;
const PAGES = (process.env.A11Y_PAGES ?? "").split(",").filter(Boolean).length
  ? process.env.A11Y_PAGES.split(",")
  : [
      "/hq/overview", "/hq/analysis", "/hq/goals", "/hq/capital", "/hq/initiatives",
      "/risk", "/risk/analysis/model-monitoring", "/risk/analysis/inclusive-risk", "/risk/guides",
      "/branch", "/branch/analysis/prime-corp", "/branch/analysis/seomin", "/branch/targets",
      "/knowledge", "/knowledge/gov_policy", "/domains/loan",
      "/admin", "/admin/users", "/admin/datasets", "/admin/rules", "/admin/llm", "/admin/monitor/agents", "/admin/pipeline", "/admin/contracts",
      // Phase C — 관리자 홈 · 운영 개요 · 설정 · 자료 승인 · 분석 에이전트 · 실행 상세, 업무 자료 올리기 · 분석 만들기 · 부서 분석 공간
      "/admin/monitor", "/admin/settings", "/admin/uploads", "/admin/analysis-agents", "/admin/monitor/runs", "/admin/workflows", "/admin/ontology", "/admin/knowledge",
      "/knowledge/upload", "/analysis/builder?space=risk",
      // Phase E — 자료를 고른 채 연 업로드(목록 · 기준 정보 펼침) · 권한 없음 · 없는 화면
      "/knowledge/upload?target=PROVISION_BY_PRODUCT", "/forbidden?from=/risk", "/no-such-page",
    ];
if (!ADMIN || !ADMIN_PW) {
  console.error("E2E_ADMIN_EMP · E2E_ADMIN_PW 가 필요합니다 (make a11y 는 .env 의 BOOTSTRAP_ADMIN_* 를 사용)");
  process.exit(2);
}
fs.mkdirSync(OUT, { recursive: true });

// 탭(role=tab)으로 내용이 바뀌는 화면 — 첫 탭 외의 탭도 눌러 다시 점검한다 (B.45). 쉼표로 바꿀 수 있다.
const TAB_PAGES = (process.env.A11Y_TAB_PAGES ?? "/admin/pipeline").split(",").filter(Boolean);

async function settle(page) {
  await page.waitForFunction(() => !document.body.innerText.includes("불러오는 중"), { timeout: 15000 }).catch(() => undefined);
}

async function axeRun(page) {
  await page.evaluate(AXE); // CDP 평가는 페이지 CSP 의 적용을 받지 않는다
  return page.evaluate(async () => {
    // eslint-disable-next-line no-undef
    const r = await axe.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] }, resultTypes: ["violations"] });
    return r.violations.map((v) => ({ id: v.id, impact: v.impact, help: v.help, nodes: v.nodes.slice(0, 5).map((n) => ({ target: n.target.join(" "), summary: (n.failureSummary || "").split("\n").slice(0, 3).join(" "), html: n.html.slice(0, 160) })), count: v.nodes.length }));
  });
}

async function scan(page, url) {
  process.stderr.write(`… ${url}\n`);
  await page.goto(BASE + url, { waitUntil: "networkidle2", timeout: 30000 });
  await settle(page);
  return axeRun(page);
}

/** 현재 화면에서 선택되지 않은 탭을 하나씩 눌러 점검 — 탭 이름은 화면에서 읽는다(목록을 코드에 두지 않음). */
async function scanTabs(page, url) {
  const labels = await page.$$eval('[role="tab"]', (els) => els.filter((e) => e.getAttribute("aria-selected") !== "true").map((e) => (e.textContent || "").trim()).filter(Boolean));
  const out = [];
  for (const label of labels) {
    process.stderr.write(`… ${url} [탭: ${label}]\n`);
    const clicked = await page.evaluate((l) => {
      const el = [...document.querySelectorAll('[role="tab"]')].find((e) => (e.textContent || "").trim() === l);
      if (!el) return false;
      el.click();
      return true;
    }, label);
    if (!clicked) {
      out.push({ url: `${url} [탭: ${label}]`, violations: [], note: "탭을 찾지 못함" });
      continue;
    }
    await page
      .waitForFunction((l) => [...document.querySelectorAll('[role="tab"]')].some((e) => (e.textContent || "").trim() === l && e.getAttribute("aria-selected") === "true"), { timeout: 10000 }, label)
      .catch(() => undefined);
    await new Promise((r) => setTimeout(r, 500));
    await settle(page);
    out.push({ url: `${url} [탭: ${label}]`, violations: await axeRun(page) });
  }
  return out;
}

const browser = await puppeteer.launch({ headless: true, args: ["--no-sandbox"] });
const report = [];
let bad = 0;
try {
  const page = await (await browser.createBrowserContext()).newPage();
  await page.setViewport({ width: 1440, height: 900 });
  page.setDefaultTimeout(30000);
  // 로그인 전 화면
  for (const url of ["/login", "/signup"]) report.push({ url, violations: await scan(page, url) });
  await page.goto(`${BASE}/login`, { waitUntil: "networkidle0" });
  await page.type("#emp_no", ADMIN);
  await page.type("#password", ADMIN_PW);
  await Promise.all([page.click('button[type="submit"]'), page.waitForNavigation({ waitUntil: "networkidle2" })]);
  if (page.url().includes("/login")) throw new Error("관리자 로그인 실패 — E2E_ADMIN_PW 확인");
  for (const url of PAGES) {
    report.push({ url, violations: await scan(page, url) });
    if (TAB_PAGES.includes(url)) report.push(...(await scanTabs(page, url)));
  }
} finally {
  await browser.close();
}
for (const r of report) {
  const hit = r.violations.filter((v) => (LEVELS[v.impact] ?? 0) >= MIN);
  bad += hit.length;
  console.log(`${hit.length ? "FAIL" : "PASS"}  ${r.url}${hit.length ? ` — ${hit.map((v) => `${v.id}(${v.impact}×${v.count})`).join(", ")}` : ""}${r.note ? ` (${r.note})` : ""}`);
  for (const v of hit) for (const n of v.nodes) console.log(`      ${v.id}: ${n.target} :: ${n.summary}`);
}
const below = report.reduce((n, r) => n + r.violations.filter((v) => (LEVELS[v.impact] ?? 0) < MIN).length, 0);
fs.writeFileSync(path.join(OUT, "a11y.json"), JSON.stringify(report, null, 1));
console.log(`\n${report.length} pages · 기준(${Object.keys(LEVELS)[MIN]} 이상) 위반 ${bad}종 · 기준 미만 ${below}종 · 상세 ${path.join(OUT, "a11y.json")}`);
process.exit(bad ? 1 : 0);
