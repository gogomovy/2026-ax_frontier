// NHDIP 브라우저 E2E (QA-04 · 요구사항 B.11)
//   make e2e   (또는  cd apps/e2e && npm install && E2E_ADMIN_EMP=... E2E_ADMIN_PW=... node e2e.mjs)
//
// 시나리오: 가입(본부>부>국>팀) → 승인 → 로그인 → 소속 권한 메뉴 → 다른 부서 403 → 영업점 사용자(지역본부 상속)
//          → 7790 정정본 업로드 → 관련 워크플로우만 실행 → 화면 재계산 → 실행 모니터링 → 되돌리기 → 질의 패널 → 관리자 화면 → 로그아웃
// 실행 중 만든 사용자는 끝에 '중지' 처리하고, 데이터·설정은 원래대로 되돌린다.
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
if (!ADMIN || !ADMIN_PW) {
  console.error("E2E_ADMIN_EMP · E2E_ADMIN_PW 가 필요합니다 (make e2e 는 .env 의 BOOTSTRAP_ADMIN_* 를 사용)");
  process.exit(2);
}
fs.mkdirSync(OUT, { recursive: true });
const EMP = String(20260000 + Math.floor(Math.random() * 9999));
const BR_EMP = String(20270000 + Math.floor(Math.random() * 9999));
const PW = "Plan2026ok";
const results = [];
const ok = (name, cond, detail = "") => {
  results.push({ name, pass: !!cond, detail });
  console.log(`${cond ? "PASS" : "FAIL"}  ${name}${detail ? " — " + detail : ""}`);
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const shot = (page, name, fullPage = false) => page.screenshot({ path: path.join(OUT, `${name}.png`), fullPage });

const browser = await puppeteer.launch({ headless: true, args: ["--no-sandbox"] });
const errors = [];
async function newPage(ctx) {
  const page = await ctx.newPage();
  await page.setViewport({ width: 1440, height: 900 });
  page.on("pageerror", (e) => errors.push(`${page.url()} ${e.message}`));
  page.on("console", (m) => m.type() === "error" && !/Failed to load resource/.test(m.text()) && errors.push(`${page.url()} console: ${m.text()}`));
  return page;
}
const text = (p) => p.evaluate(() => document.body.innerText);
async function pickOrg(page, idx, code) {
  await page.waitForFunction((i, c) => document.querySelectorAll("fieldset select")[i]?.querySelector(`option[value="${c}"]`), {}, idx, code);
  await page.evaluate(
    (i, c) => {
      const s = document.querySelectorAll("fieldset select")[i];
      Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value").set.call(s, c);
      s.dispatchEvent(new Event("change", { bubbles: true }));
    },
    idx,
    code,
  );
}
async function signup(page, emp, name, orgPath) {
  await page.goto(`${BASE}/signup`, { waitUntil: "networkidle0" });
  await page.type("#emp_no", emp);
  await page.type("#name", name);
  for (let i = 0; i < orgPath.length; i++) await pickOrg(page, i, orgPath[i]);
  await page.type("#password", PW);
  await page.type("#confirm", PW);
  await page.click('button[type="submit"]');
  await page.waitForFunction(() => document.body.innerText.includes("가입 신청 완료"), { timeout: 15000 });
}
async function login(page, emp, pw, next = "") {
  await page.goto(`${BASE}/login${next}`, { waitUntil: "networkidle0" });
  await page.type("#emp_no", emp);
  await page.type("#password", pw);
  await Promise.all([page.click('button[type="submit"]'), page.waitForNavigation({ waitUntil: "networkidle0" })]);
}

let restore = async () => {};
try {
  // 1) 미로그인 → 로그인
  const u = await newPage(await browser.createBrowserContext());
  await u.goto(`${BASE}/hq/overview`, { waitUntil: "networkidle0" });
  ok("미로그인 → 로그인 화면", u.url().includes("/login?next="), u.url());
  await shot(u, "01-login");

  // 2) 가입 (본부 > 부 > 국 > 팀)
  await signup(u, EMP, "E2E기획", ["H100", "D100", "B110", "T111"]);
  ok("가입 → 승인 대기", (await text(u)).includes("관리자 승인 후"));
  await u.goto(`${BASE}/signup`, { waitUntil: "networkidle0" });
  await pickOrg(u, 0, "H100");
  const labels = await u.evaluate(() => [...document.querySelectorAll("fieldset select")].map((s) => s.getAttribute("aria-label")));
  ok("가입 단계 라벨 = 조직 유형", labels[0].includes("본부") && labels[0].includes("지역본부") && labels[1] === "부", labels.join(" / "));

  // 3) 관리자 승인
  const a = await newPage(await browser.createBrowserContext());
  await login(a, ADMIN, ADMIN_PW, "?next=/admin/users");
  ok("관리자 로그인", a.url().endsWith("/admin/users"), a.url());
  await a.waitForFunction((emp) => document.body.innerText.includes(emp), {}, EMP);
  const approved = await a.evaluate((emp) => {
    const row = [...document.querySelectorAll("tr")].find((tr) => tr.innerText.includes(emp));
    const btn = row && [...row.querySelectorAll("button")].find((b) => b.innerText.trim() === "승인");
    btn?.click();
    return !!btn;
  }, EMP);
  await sleep(1500);
  ok("관리자 화면에서 승인", approved);
  await shot(a, "02-admin-users");
  const api = (p, init = {}) =>
    a.evaluate(
      async (p, init) => {
        const r = await fetch(`/backend${p}`, { ...init, headers: { "Content-Type": "application/json" } });
        return { status: r.status, body: await r.json().catch(() => null) };
      },
      p,
      init,
    );

  // 4) 사용자 로그인 · 권한
  await login(u, EMP, PW);
  ok("승인 후 로그인 → 첫 화면", u.url().endsWith("/hq/overview"), u.url());
  // 사용자 카드는 헤더의 사용자 메뉴(눌러서 펼침)에 있다
  const userCard = async (p) => {
    await p.evaluate(() => document.querySelector("[data-user-menu]")?.click());
    await sleep(250);
    const t = await p.evaluate(() => document.querySelector("[data-user-menu]")?.parentElement?.innerText ?? "");
    await p.keyboard.press("Escape");
    return t;
  };
  ok("사용자 카드: 본부 > 부 > 국 > 팀", (await userCard(u)).includes("경영기획본부 > 종합기획부 > 경영기획국 > 경영목표팀"));
  // 헤더 = 소속 영역의 단계 + 공통(데이터베이스 아이콘). 다른 영역의 단계(수행방안)는 보이지 않는다
  const head = await u.evaluate(() => ({ text: document.querySelector("header")?.innerText ?? "", db: !!document.querySelector('header a[aria-label="데이터베이스"]'), admin: !!document.querySelector('header a[href="/admin"]') }));
  ok("헤더 = 소속 부서 단계 + 공통", head.text.includes("경영목표 설정") && head.db && !head.text.includes("수행방안") && !head.admin, head.text.replace(/\n+/g, " | "));
  await shot(u, "03-user-overview");
  for (const p of ["/hq/analysis", "/hq/goals", "/hq/capital", "/hq/initiatives", "/knowledge", "/knowledge/gov_policy", "/knowledge/upload", "/analysis/builder", "/domains/loan"]) {
    await u.goto(BASE + p, { waitUntil: "networkidle0" });
    ok(`업무 화면 ${p}`, !u.url().includes("forbidden") && !(await text(u)).includes("찾는 화면이 없습니다"), u.url());
  }
  await u.goto(`${BASE}/risk`, { waitUntil: "networkidle0" });
  ok("다른 부서 화면 → 권한 없음", u.url().includes("/forbidden"), u.url());
  // Phase E (NAV-03) — 어느 화면인지 · 누구에게 요청하는지
  const fb = await u.evaluate(() => ({ screen: document.querySelector("[data-forbidden-screen]")?.textContent ?? "", h1: document.querySelector("h1")?.textContent ?? "" }));
  ok("권한 없음: 요청한 화면 이름 · 메뉴 위치", u.url().includes("from=%2Frisk") && fb.screen.includes("신용리스크") && fb.h1.startsWith("["), JSON.stringify(fb));
  await u.goto(`${BASE}/admin`, { waitUntil: "networkidle0" });
  ok("관리자 화면 → 권한 없음", u.url().includes("/forbidden"), u.url());

  // 5) 질의 패널 (LLM 미연결이면 수치·근거만, 권한 밖 지표 제외)
  await u.goto(`${BASE}/hq/overview`, { waitUntil: "networkidle0" });
  await u.evaluate(() => [...document.querySelectorAll("button")].find((b) => b.innerText.includes("AI 어시스턴트")).click());
  await u.waitForSelector("#assist-q");
  await u.type("#assist-q", "기업여신 증가율과 목표 대비 이탈은?");
  await u.evaluate(() => [...document.querySelectorAll("form button")].find((b) => b.innerText.trim() === "질문").click());
  await u.waitForSelector('[role="dialog"] article[data-status="done"]', { timeout: 60000 }); // 답은 스트리밍으로 나오므로 끝난 답을 기다린다
  const ans = await u.evaluate(() => document.querySelector('[role="dialog"] article')?.innerText ?? "");
  const asked = await u.evaluate(() => document.querySelector('[role="dialog"] [data-role="user"]')?.innerText ?? "");
  ok("질의 패널: 내 질문이 말풍선으로, 답변에 확정 수치(커널)", asked.includes("기업여신 증가율") && /기업여신 증가율[^\n]*\n?\s*4\.04%/.test(ans) && ans.includes("목표 대비 이탈") && ans.includes("GROWTH_RATE"), ans.slice(0, 200).replace(/\n/g, " | "));
  ok("질의 패널: 수치 출처 확인 배지", ans.includes("수치 출처 확인"));
  await shot(u, "04-assist");

  // 6) 영업점 사용자 (지역본부 > 영업점)
  const b = await newPage(await browser.createBrowserContext());
  await signup(b, BR_EMP, "E2E지점", ["D300", "BR301"]);
  await api(`/admin/users/${BR_EMP}/approve`, { method: "POST" });
  await login(b, BR_EMP, PW);
  ok("영업점 사용자 → /branch (지역본부 권한 상속)", b.url().endsWith("/branch"), b.url());
  ok("영업점 사용자 카드: 지역본부 > 영업점", (await userCard(b)).includes("수도권1지역본부 > 강남금융센터"));
  ok("다른 영업점 분석은 보이지 않음(자기 영업점만)", (await text(b)).includes("업적평가 분석은 아직 준비 중"));
  await b.goto(`${BASE}/branch/targets`, { waitUntil: "networkidle0" });
  ok("영업점 참고: 본부 전파 목표·가이드", (await text(b)).includes("전파된 목표"));

  // 6-2) 영업점 시나리오 (B.29) — 수원영통지점 업적평가 대시보드 → 의견 탭(보고서)
  await a.goto(`${BASE}/branch`, { waitUntil: "networkidle0" });
  const bt = await text(a);
  ok("영업점 1화면: 업적평가 득점 · 기준 변경 알림 · 사업부문", bt.includes("업적평가 득점 현황") && bt.includes("우량기업여신") && bt.includes("서민금융") && bt.includes("사업부문") && bt.includes("수원영통지점"));
  await shot(a, "05a-branch-dashboard");
  await Promise.all([a.waitForNavigation({ waitUntil: "networkidle0" }).catch(() => undefined), a.evaluate(() => [...document.querySelectorAll('a[href="/branch/analysis/prime-corp"]')][0]?.click())]);
  await a.waitForFunction(() => location.pathname === "/branch/analysis/prime-corp", { timeout: 15000 }).catch(() => undefined);
  const bp = await text(a);
  ok("영업점 2화면: 알림 → 우량기업여신 보고서(마케팅 후보)", a.url().endsWith("/branch/analysis/prime-corp") && bp.includes("마케팅 후보") && bp.includes("신동에너지(주)"), a.url());
  await shot(a, "05b-branch-prime-corp");
  await a.goto(`${BASE}/branch/analysis/seomin`, { waitUntil: "networkidle0" });
  const bs = await text(a);
  ok("영업점 3화면: 서민금융 신규 유치 적정 규모", bs.includes("신규 유치 규모 산정") && bs.includes("19건") && bs.includes("35백만원"));
  await shot(a, "05c-branch-seomin");

  // 7) 업로드 → 관련 워크플로우만
  const debounce = (await api("/admin/settings")).body.find((s) => s.key === "workflow.debounce_default_sec")?.value ?? 60;
  await api("/admin/settings/workflow.debounce_default_sec", { method: "PUT", body: JSON.stringify({ value: 3 }) });
  const prov = (await api("/admin/datasets")).body.find((d) => d.code === "PROVISION_BY_PRODUCT");
  const cur = prov.versions.find((v) => v.isCurrent && v.asOf === "2026-08-31");
  const rollback = () => api(`/admin/datasets/PROVISION_BY_PRODUCT/versions/${cur.id}/rollback`, { method: "POST" });
  const restoreDebounce = () => api("/admin/settings/workflow.debounce_default_sec", { method: "PUT", body: JSON.stringify({ value: debounce }) });
  restore = async () => {
    await rollback();
    await sleep(8000); // 되돌리기 이벤트가 짧은 디바운스로 디스패치된 뒤에 설정을 원복
    await restoreDebounce();
  };
  const rows = (await api(`/admin/datasets/PROVISION_BY_PRODUCT/versions/${cur.id}/rows`)).body.rows;
  const csv = ["ym,product_code,product_name,provision,is_total,src_ref", ...rows.map((r) => `${r.ym},${r.product_code},${r.product_name},${r.provision + (r.product_code === "2001107820007" ? 10000 : 0) - (r.product_code === "OTHERS" ? 10000 : 0)},${r.is_total ? 1 : 0},${r.src_ref ?? ""}`)].join("\n");
  const csvPath = path.join(OUT, "(202608)7790_상품별_충당금_정정.csv");
  fs.writeFileSync(csvPath, csv);
  const before = (await api("/admin/monitor/flow?limit=1")).body[0]?.id ?? 0;
  await a.goto(`${BASE}/admin/datasets`, { waitUntil: "networkidle0" });
  await a.waitForFunction(() => [...document.querySelectorAll("tr")].some((tr) => tr.innerText.includes("PROVISION_BY_PRODUCT")));
  // Phase E (UXF-03) — 머리 '파일로 업로드' 에 파일을 놓으면 이름으로 데이터셋을 찾아 상세 양식(파일 채움)을 연다
  ok("관리자 데이터셋: 머리 파일 놓기 영역", (await a.$('[data-file-drop="admin-dataset"]')) !== null);
  await (await a.$('[data-file-drop="admin-dataset"] input[type="file"]')).uploadFile(csvPath);
  await a.waitForSelector('[data-dataset-detail="PROVISION_BY_PRODUCT"] [data-file-chosen]', { timeout: 10000 });
  const focusedDetail = await a.evaluate(() => document.activeElement?.getAttribute("data-dataset-detail") ?? document.activeElement?.closest("[data-dataset-detail]")?.getAttribute("data-dataset-detail") ?? "");
  ok("관리자 데이터셋: 파일 이름 → 7790 상세 열림 · 초점 이동", focusedDetail === "PROVISION_BY_PRODUCT", focusedDetail);
  // 즉시 확정 업로드는 확인 대화상자 — 취소하면 아무 일도 없다
  await a.click('[data-dataset-detail="PROVISION_BY_PRODUCT"] [data-admin-upload]');
  await a.waitForSelector("[data-confirm-dialog]", { timeout: 5000 });
  const dlgFocus = await a
    .waitForFunction(() => document.activeElement?.hasAttribute("data-confirm-cancel") ?? false, { timeout: 3000 })
    .then(() => true)
    .catch(() => false);
  ok("확정 업로드: 확인 대화상자(초점 = 취소)", dlgFocus);
  await a.keyboard.press("Escape");
  await a.waitForFunction(() => !document.querySelector("[data-confirm-dialog]"), { timeout: 5000 });
  await a.click('[data-dataset-detail="PROVISION_BY_PRODUCT"] [data-admin-upload]');
  await a.waitForSelector("[data-confirm-ok]", { timeout: 5000 });
  await a.click("[data-confirm-ok]");
  await a.waitForFunction(() => document.body.innerText.includes("업로드했습니다"), { timeout: 15000 });
  ok("관리자 화면 업로드(당행)", true);
  let ev = null;
  for (let i = 0; i < 45; i++) {
    await sleep(2000);
    ev = (await api("/admin/monitor/flow?limit=10")).body.find((e) => e.id > before && e.type === "dataset.committed" && e.payload.dataset === "PROVISION_BY_PRODUCT");
    if (ev && ev.runs.length >= 2 && ev.runs.every((r) => r.status !== "running")) break;
  }
  const matched = (ev?.matched ?? []).map((m) => m.workflow).sort();
  ok("관련 워크플로우만 매칭", JSON.stringify(matched) === JSON.stringify(["wf_graph_projection", "wf_inclusive_risk"]), matched.join(", "));
  ok("매칭 워크플로우 실행 완료", ev && ev.runs.length >= 2 && ev.runs.every((r) => ["succeeded", "degraded"].includes(r.status)), (ev?.runs ?? []).map((r) => `${r.workflow}:${r.status}`).join(", "));
  await a.goto(`${BASE}/admin/monitor/flow`, { waitUntil: "networkidle0" });
  await shot(a, "05-admin-flow");
  await a.goto(`${BASE}/risk/analysis/inclusive-risk`, { waitUntil: "networkidle0" });
  ok("업무 화면 재계산 반영 9.45%", (await text(a)).includes("9.45"));
  // 판단 에이전트 (B.30) — 변화 감지 피드 · 에이전트 결정 화면
  await a.goto(`${BASE}/risk`, { waitUntil: "networkidle0" });
  const feedText = await a.evaluate(() => document.querySelector("[data-change-feed]")?.innerText ?? "");
  ok("변화 감지: 정정본 업로드 → 최근 감지된 변화", feedText.includes("포용금융 충당금 비중"), feedText.slice(0, 120).replace(/\n/g, " | "));
  await a.goto(`${BASE}/admin/monitor/agents`, { waitUntil: "networkidle0" });
  await a.waitForSelector("[data-agent-topology]", { timeout: 15000 }).catch(() => undefined);
  await a.waitForFunction(() => document.body.innerText.includes("변화 판정"), { timeout: 15000 }).catch(() => undefined);
  const agt = await text(a);
  ok("에이전트 결정: 배치 · 의존 · 결정 기록", agt.includes("변화 감지(에이전트)") && agt.includes("실행 계획(플래너)") && agt.includes("wf_graph_projection") && agt.includes("변화 판정"));
  await shot(a, "06b-admin-agents");
  await a.goto(`${BASE}/admin/monitor/runs`, { waitUntil: "networkidle0" });
  await a.waitForFunction(() => [...document.querySelectorAll("button.row-button")].some((x) => x.innerText.includes("wf_inclusive_risk")), { timeout: 15000 });
  await a.evaluate(() => [...document.querySelectorAll("button.row-button")].find((x) => x.innerText.includes("wf_inclusive_risk")).click());
  await a.waitForFunction(() => /커널 계산 \d+건/.test(document.body.innerText), { timeout: 15000 });
  ok("실행 모니터링(노드·LLM·계산)", (await text(a)).includes("narrate"));
  await shot(a, "06-admin-runs");

  // 8) 되돌리기
  await rollback();
  restore = restoreDebounce;
  let back = false;
  for (let i = 0; i < 60 && !back; i++) {
    await sleep(2000);
    back = (await api("/screens/inclusive")).body?.shareNow?.value === 9.16;
  }
  ok("되돌리기 → 9.16 복원", back);
  await restoreDebounce();
  restore = async () => {};

  // 8-0) 온디맨드 분석 (F.9) — 버튼 → SSE 단계 진행 → 완료
  await a.goto(`${BASE}/risk/analysis/model-monitoring`, { waitUntil: "networkidle0" });
  await a.evaluate(() => document.querySelector("[data-on-demand] button")?.click());
  const progressDone = await a
    .waitForFunction(
      () => {
        const steps = [...document.querySelectorAll("[data-agent-progress] [data-step]")];
        return steps.length > 3 && steps.every((s) => !["pending", "running"].includes(s.getAttribute("data-status")));
      },
      { timeout: 90000 },
    )
    .then(() => true)
    .catch(() => false);
  const stepCount = await a.evaluate(() => document.querySelectorAll("[data-agent-progress] [data-step]").length);
  ok("온디맨드 분석: SSE 단계 진행 → 완료", progressDone, `단계 ${stepCount}개`);
  await shot(a, "07b-on-demand");

  // 8-1) 보고서 서버 변환 (F.17) — 형식 메뉴 · PDF/HWPX 바이트
  await a.goto(`${BASE}/risk/analysis/model-monitoring`, { waitUntil: "networkidle0" });
  await a.waitForFunction(() => !document.querySelector("[data-report-export] button")?.disabled, { timeout: 15000 });
  await a.evaluate(() => document.querySelector("[data-report-export] button").click());
  await a.waitForSelector("[data-report-export] [data-format]");
  const fmts = await a.evaluate(() => [...document.querySelectorAll("[data-report-export] [data-format]")].map((x) => x.dataset.format));
  ok("보고서 내려받기 형식 메뉴", JSON.stringify(fmts) === JSON.stringify(["pdf", "hwpx", "hwp", "html"]), fmts.join(", "));
  await shot(a, "08-report-export");
  await a.keyboard.press("Escape");
  const files = await a.evaluate(async () => {
    const out = {};
    for (const f of ["pdf", "hwpx"]) {
      const r = await fetch(`/backend/reports/model-monitoring/export?format=${f}`);
      const b = new Uint8Array(await r.arrayBuffer());
      out[f] = { status: r.status, head: String.fromCharCode(...b.slice(0, 4)), name: decodeURIComponent((r.headers.get("content-disposition") ?? "").split("UTF-8''")[1] ?? "") };
    }
    return out;
  });
  ok("서버 변환 PDF", files.pdf.status === 200 && files.pdf.head === "%PDF" && files.pdf.name.endsWith("_보고서.pdf"), files.pdf.name);
  ok("서버 변환 HWPX(zip)", files.hwpx.status === 200 && files.hwpx.head.startsWith("PK"), files.hwpx.name);

  // 8-2) 전파 경로 서버 계산 (F.16)
  const tree = (await api("/cascade/tree")).body ?? [];
  ok("전파 경로 서버 트리", tree.some((n) => n.id === "goal-corp-growth" && n.kind === "goal"), tree.map((n) => n.id).join(", "));
  await a.goto(`${BASE}/hq/goals`, { waitUntil: "networkidle0" });
  await a.evaluate(() => [...document.querySelectorAll("button, [role=tab]")].find((x) => x.innerText.trim() === "전파 경로")?.click());
  await a.waitForFunction(() => document.body.innerText.includes("기업여신 확대 실행방안"), { timeout: 15000 }).catch(() => undefined);
  ok("전파 경로 탭 표시", (await text(a)).includes("기업여신 확대 실행방안"));

  // 8-2b) 경영목표 정합성 검증 (6.4.7) — 상한 초과 직접 수정 → 경고 · 사유 입력 요구 (확정하지 않고 취소)
  await api("/state/goals/reset", { method: "POST", body: "{}" });
  await a.goto(`${BASE}/hq/goals`, { waitUntil: "networkidle0" });
  await a.evaluate(() => [...document.querySelectorAll("button.row-button")].find((x) => x.innerText.includes("목표 수정 제안") && x.innerText.includes("기업여신"))?.click());
  await a.waitForFunction(() => [...document.querySelectorAll("button")].some((x) => x.innerText.trim() === "직접 수정"), { timeout: 15000 }).catch(() => undefined);
  await a.evaluate(() => [...document.querySelectorAll("button")].find((x) => x.innerText.trim() === "직접 수정")?.click());
  await a.waitForSelector('input[aria-label="직접 입력 목표값"]', { timeout: 10000 }).catch(() => undefined);
  await a.evaluate(() => {
    const el = document.querySelector('input[aria-label="직접 입력 목표값"]');
    if (!el) return;
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(el, "9.0");
    el.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await a.evaluate(() => [...document.querySelectorAll("button")].find((x) => x.innerText.trim() === "반영")?.click());
  const consistency = await a.waitForSelector("[data-consistency]", { timeout: 15000 }).then(() => a.evaluate(() => document.querySelector("[data-consistency]").innerText)).catch(() => "");
  ok("경영목표 정합성 검증: 상한 초과 경고 · 사유 입력", consistency.includes("상한") && consistency.includes("사유"), consistency.slice(0, 80).replace(/\n/g, " | "));
  await shot(a, "08b-goal-consistency");
  await a.evaluate(() => [...document.querySelectorAll("[data-consistency] button")].find((x) => x.innerText.trim() === "취소")?.click());

  // 8-3) 원본 문서 뷰어 (F.12) — 근거 드로어 '원본 열기' 주소 → 인용 면 · 하이라이트
  await a.goto(`${BASE}/risk/analysis/model-monitoring`, { waitUntil: "networkidle0" });
  await a.evaluate(() => [...document.querySelectorAll("button")].find((x) => /근거 \d+건/.test(x.innerText))?.click());
  await a.waitForSelector('[role="dialog"]', { timeout: 15000 }).catch(() => undefined);
  // 문서 근거(면 번호가 있는 항목)를 골라 상세를 연다
  await a.evaluate(() => [...document.querySelectorAll('[role="dialog"] li button')].find((x) => / · p\.\d+/.test(x.innerText))?.click());
  await a.waitForSelector("[data-doc-open]", { timeout: 15000 }).catch(() => undefined);
  const docHref = await a.evaluate(() => document.querySelector("[data-doc-open]")?.getAttribute("href") ?? "");
  ok("근거 드로어: 원본 열기 링크", docHref.startsWith("/knowledge/doc?"), docHref.slice(0, 120));
  await a.keyboard.press("Escape");
  if (docHref) {
    await a.goto(BASE + docHref, { waitUntil: "networkidle0" });
    const marks = await a.evaluate(() => document.querySelectorAll("mark[data-highlight]").length);
    const cur = await a.evaluate(() => document.querySelector('nav[aria-label="면 목록"] [aria-current="page"]')?.innerText ?? "");
    ok("원본 뷰어: 인용 면 · 하이라이트", marks > 0 && cur.startsWith("p."), `${cur.replace(/\n/g, " ")} · mark ${marks}`);
    await shot(a, "09-doc-viewer");
  }
  await a.goto(`${BASE}/knowledge/gov_policy`, { waitUntil: "networkidle0" });
  const listHref = await a.evaluate(() => document.querySelector("[data-doc-link]")?.getAttribute("href") ?? "");
  await a.goto(BASE + listHref, { waitUntil: "networkidle0" });
  ok("문서 목록 → 뷰어", listHref.includes("/knowledge/doc?id=") && (await a.evaluate(() => document.querySelectorAll("[data-doc-page]").length)) === 1, listHref);

  // 8-4) 요청 추적 (0.5) — 변경 요청의 X-Trace-Id → HTTP · 감사 · 이벤트 · 워크플로우 구간
  const traced = await a.evaluate(async () => {
    const r = await fetch("/backend/admin/workflows/wf_model_monitoring/run", { method: "POST" });
    return { status: r.status, trace: r.headers.get("x-trace-id") };
  });
  let spanKinds = [];
  for (let i = 0; i < 30 && traced.trace; i++) {
    await sleep(2000);
    spanKinds = ((await api(`/admin/monitor/trace/${traced.trace}`)).body?.spans ?? []).map((s) => s.kind);
    if (spanKinds.includes("run")) break;
  }
  ok("요청 추적: HTTP → 이벤트 → 워크플로우", traced.status === 200 && spanKinds[0] === "http" && spanKinds.includes("event") && spanKinds.includes("run"), `${traced.trace} · ${spanKinds.join(" > ")}`);
  if (traced.trace) {
    await a.goto(`${BASE}/admin/monitor/trace?id=${traced.trace}`, { waitUntil: "networkidle0" });
    await a.waitForSelector("[data-trace-spans] li", { timeout: 15000 }).catch(() => undefined);
    ok("요청 추적 화면", (await a.evaluate(() => document.querySelectorAll("[data-trace-spans] li").length)) >= 3);
    await shot(a, "10-admin-trace");
  }

  // 8-5) 다지점 영업점 (B.47) — 가상 지점 자료 업로드 + 규칙 목록 추가 → 지점 선택 상자 · ?office= 화면 · 접근성, 끝나면 원상 복구
  {
    const dsAll = (await api("/admin/datasets")).body;
    const cur = (code) =>
      dsAll
        .find((d) => d.code === code)
        .versions.filter((v) => v.isCurrent)
        .sort((x, y) => String(y.asOf ?? "").localeCompare(String(x.asOf ?? "")))[0];
    const rowsOf = async (code) => (await api(`/admin/datasets/${code}/versions/${cur(code).id}/rows?limit=2000`)).body.rows;
    // 차주 명세에 있는 다른 사무소 하나 — 시드 기업 · 소매 명세는 같은 지점 목록이라 계산이 된다
    const X = (await rowsOf("OBLG_GRD_DEF")).map((r) => String(r.SUVMN_BRC)).find((c) => c !== "001068");
    const NAME = "E2E가상지점";
    const scope = (await api("/admin/rules")).body.find((r) => r.code === "BRANCH_SCOPE");
    const body0 = scope.versions.find((v) => v.version === scope.activeVersion).body;
    const debounce0 = (await api("/admin/settings")).body.find((s) => s.key === "workflow.debounce_default_sec")?.value ?? 60;
    await api("/admin/settings/workflow.debounce_default_sec", { method: "PUT", body: JSON.stringify({ value: 3 }) });
    const prev = {};
    const upload = (code, rows) =>
      a.evaluate(
        async (code, rows) => {
          const fd = new FormData();
          fd.append("file", new File([JSON.stringify(rows)], `${code}_e2e_multi_office.json`, { type: "application/json" }));
          fd.append("origin", "bank");
          fd.append("data_origin", "simulated");
          fd.append("note", "E2E 다지점(B.47) — 끝나면 되돌림");
          const r = await fetch(`/backend/admin/datasets/${code}/upload`, { method: "POST", body: fd });
          return { status: r.status, body: await r.json().catch(() => null) };
        },
        code,
        rows,
      );
    const offices = async () => (await api("/screens/branch/offices")).body ?? { offices: [] };
    const restoreOffices = async () => {
      await api("/admin/rules/BRANCH_SCOPE/versions", { method: "POST", body: JSON.stringify({ body: body0, note: "E2E 다지점 복원" }) });
      for (const [code, vid] of Object.entries(prev)) await api(`/admin/datasets/${code}/versions/${vid}/rollback`, { method: "POST" });
      await sleep(8000); // 되돌리기 · 규칙 이벤트가 짧은 디바운스로 디스패치된 뒤에 설정을 원복
      for (let i = 0; i < 45; i++) {
        const runs = (await api("/admin/monitor/runs?workflow=wf_branch_kpi&limit=3")).body ?? [];
        if (!runs.some((x) => x.status === "running")) break;
        await sleep(2000);
      }
      await api("/admin/settings/workflow.debounce_default_sec", { method: "PUT", body: JSON.stringify({ value: debounce0 }) });
    };
    restore = restoreOffices;
    const add = {
      BRANCH_OFFICE_MASTER: (r) => [{ ...r, office_cd: X, office_nm: NAME, org_code: "" }],
      BRANCH_KPI_SCORE: (r) => [{ ...r, office_cd: X, score: r.score == null ? r.score : Math.round(Number(r.score) * 9) / 10 }],
      BRANCH_BIZ_BALANCE: (r) => [{ ...r, office_cd: X, amount: Math.round(Number(r.amount) / 2) }],
    };
    const ups = [];
    for (const code of Object.keys(add)) {
      prev[code] = cur(code).id;
      const all = (await rowsOf(code)).filter((r) => String(r.office_cd) !== X); // 같은 구획의 다른 지점 행은 그대로
      const res = await upload(code, [...all, ...all.filter((r) => String(r.office_cd) === "001068").flatMap(add[code])]);
      ups.push(`${code}:${res.status}/${res.body?.status ?? res.body?.detail ?? ""}`);
    }
    ok("다지점: 가상 지점 자료 업로드(마스터 · 득점 · 잔액)", ups.every((u) => u.includes(":201/committed")), ups.join(", "));
    const r = await api("/admin/rules/BRANCH_SCOPE/versions", { method: "POST", body: JSON.stringify({ body: { ...body0, office_codes: ["001068", X] }, note: "E2E 다지점(B.47)" }) });
    let ready = false;
    for (let i = 0; i < 60 && !ready && r.status === 201; i++) {
      await sleep(2000);
      ready = (await offices()).offices.some((o) => o.code === X && o.available);
    }
    ok("다지점: 규칙 목록 추가 → 같은 워크플로우가 지점 x 계산", ready, `${X} · 규칙 ${r.status}`);

    await a.goto(`${BASE}/branch`, { waitUntil: "networkidle0" });
    const opts = await a.$$eval("#branch_office option", (os) => os.map((o) => o.value)).catch(() => []);
    ok("다지점: 지점 선택 상자(볼 수 있는 지점 2곳)", JSON.stringify(opts) === JSON.stringify(["001068", X]), opts.join(", "));
    const h0 = await a.evaluate(() => document.querySelector("h1")?.innerText ?? "");
    await a.select("#branch_office", X).catch(() => undefined);
    await Promise.all([a.waitForNavigation({ waitUntil: "networkidle0" }).catch(() => undefined), a.evaluate(() => document.querySelector("[data-office-picker] button[type=submit]")?.click())]);
    const h1 = await a.evaluate(() => document.querySelector("h1")?.innerText ?? "");
    const bx = await text(a);
    ok("다지점: 지점 바꾸기 → 같은 화면 구조 · 그 지점 산출물", a.url().endsWith(`/branch?office=${X}`) && h1.includes(NAME) && h0.includes("수원영통지점") && bx.includes("업적평가 득점 현황") && bx.includes("사업부문"), `${a.url()} · ${h0} → ${h1}`);
    const next = `/branch/analysis?office=${X}`;
    await a.waitForFunction((n) => document.querySelector(`aside a[href="${n}"]`), { timeout: 10000 }, next).catch(() => undefined);
    const links = await a.evaluate(() => [...document.querySelectorAll("a")].map((x) => ({ href: x.getAttribute("href") ?? "", side: !!x.closest("aside") })).filter((x) => x.href.startsWith("/branch")));
    const step = links.filter((x) => !x.side && x.href.startsWith("/branch/analysis")).map((x) => x.href);
    const side = links.filter((x) => x.side).map((x) => x.href);
    const keep = (hs) => hs.every((h) => h.endsWith(`?office=${X}`));
    ok("다지점: 화면 이동(다음 단계 · 득점표 알림 · 사이드바)에 지점 인자 유지", step.includes(next) && keep(step) && side.length >= 2 && keep(side), `${[...new Set(step)].join(" ")} | ${side.join(" ")}`);
    await shot(a, "05d-branch-multi-office");
    const axeRun = async () => {
      await a.evaluate(AXE);
      return a.evaluate(async () => {
        // eslint-disable-next-line no-undef
        // preload: false — axe 가 외부 글꼴 CSS 를 fetch 하려다 CSP(connect-src 'self')에 막혀 콘솔 오류를 남기지 않도록(어차피 막혀 결과는 같다)
        const r = await axe.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] }, resultTypes: ["violations"], preload: false });
        return r.violations.filter((v) => ["serious", "critical"].includes(v.impact)).map((v) => `${v.id}(${v.impact}×${v.nodes.length})`);
      });
    };
    const v1 = await axeRun();
    ok("다지점 접근성: 지점 선택 화면 serious · critical 위반 0", v1.length === 0, v1.join(", "));
    await a.goto(`${BASE}${next}`, { waitUntil: "networkidle0" });
    await a.waitForFunction(() => location.pathname.startsWith("/branch/analysis/"), { timeout: 15000 }).catch(() => undefined);
    const rp = await text(a);
    const tabs = await a.evaluate(() => [...document.querySelectorAll("a")].map((x) => x.getAttribute("href") ?? "").filter((h) => /^\/branch\/analysis\/[a-z-]+/.test(h)));
    ok("다지점: 지점 x 분석 보고서 · 탭 주소에 지점 인자", a.url().includes(`office=${X}`) && rp.includes("마케팅 후보") && rp.includes(NAME) && tabs.length > 0 && tabs.every((h) => h.endsWith(`?office=${X}`)), `${a.url()} · ${tabs.join(" ")}`);
    const v2 = await axeRun();
    ok("다지점 접근성: 지점 x 분석 보고서 serious · critical 위반 0", v2.length === 0, v2.join(", "));
    const ex = await a.evaluate(async (x) => (await fetch(`/backend/reports/branch-prime-corp/export?format=html&office=${x}`)).status, X);
    ok("다지점: 지점 x 보고서 내려받기", ex === 200, String(ex));

    await restoreOffices();
    restore = async () => {};
    const back = await offices();
    const d0 = (await api("/screens/branch/dashboard")).body;
    ok("다지점: 원상 복구(규칙 · 자료) → 지점 1곳 · 001068 그대로", back.offices.length === 1 && d0?.available && d0.office?.code === "001068", `${back.offices.map((o) => o.code).join(", ")} · ${d0?.office?.code}`);
  }

  // 9) 관리자 화면
  for (const p of ["/admin", "/admin/orgs", "/admin/screens", "/admin/llm", "/admin/agents", "/admin/workflows", "/admin/metrics", "/admin/contracts", "/admin/ontology", "/admin/knowledge", "/admin/rules", "/admin/settings", "/admin/audit", "/admin/monitor", "/admin/monitor/flow", "/admin/pipeline", "/admin/monitor/calc", "/admin/monitor/trace", "/admin/monitor/evals", "/admin/monitor/alerts", "/admin/uploads", "/admin/analysis-agents"]) {
    await a.goto(BASE + p, { waitUntil: "networkidle0" });
    await a.waitForFunction(() => !document.body.innerText.includes("불러오는 중"), { timeout: 15000 }).catch(() => undefined);
    const t = await text(a);
    const fail = t.indexOf("요청 실패");
    ok(`관리자 ${p}`, t.includes("관리자") && fail < 0, fail >= 0 ? t.slice(Math.max(0, fail - 120), fail + 60).replace(/\n/g, " | ") : a.url());
    if (p === "/admin/workflows") ok("워크플로우: 정기 실행(cron) 다음 시각 표시", t.includes("다음 "));
    if (p === "/admin/llm") ok("LLM 연동: 외부 LiteLLM 간단 설정(주소 · 키 · 모델)", t.includes("LiteLLM 연결 (간단 설정)") && (await a.$("[data-llm-setup]")) !== null);
    if (p === "/admin/contracts") {
      ok("컬럼 정의서: T01~T03 대조 결과", t.includes("T01 현황") && t.includes("T03 목표설정") && t.includes("mart.hq_t01") && t.includes("일치"));
      await shot(a, "07-admin-contracts");
    }
  }

  // 9-00) 3-way 검색 구성 (Phase H · TW-01~10) — PostgreSQL 원장 · Elasticsearch 키워드/의미 · Neo4j 그래프.
  // E2E_EXPECT_ES=1(CI 의 compose 스택)이면 분석 결과 · 문서 모두 Elasticsearch 로 찾아야 한다. 아니면 상태 표시만 확인(축소 구성)
  {
    const expectEs = process.env.E2E_EXPECT_ES === "1";
    const st = await api("/admin/knowledge/status");
    const sb = st.body?.searchBackend ?? {};
    const eng = sb.engines ?? {};
    ok(
      "3-way: 검색 엔진 상태(분석 결과 · 문서 · 그래프)",
      st.status === 200 && ["es", "pg"].includes(eng.analysis) && ["es", "pg"].includes(eng.documents) && ["neo4j", "postgres"].includes(eng.graph) &&
        (!expectEs || (sb.configured && sb.es?.up && eng.analysis === "es" && eng.documents === "es" && (sb.es?.documents?.es_docs ?? 0) > 0 && sb.es?.state?.analyzer === "nori")),
      JSON.stringify({ setting: sb.setting, eng, up: sb.es?.up, kb: sb.es?.es_docs, doc: sb.es?.documents?.es_docs, analyzer: sb.es?.state?.analyzer }),
    );
    const r = await api("/assist", { method: "POST", body: JSON.stringify({ question: "포용금융 확대방안 정책 기조 근거는?" }) });
    const re = r.body?.retrieval?.engines ?? {};
    ok(
      "3-way: AI 어시스턴트 답의 문서 근거 · 검색 엔진",
      r.status === 200 && (r.body?.evidence?.length ?? 0) > 0 && (!expectEs || (re.documents === "es" && re.analysis === "es")),
      JSON.stringify({ engines: re, evidence: r.body?.evidence?.length }),
    );
    await a.goto(`${BASE}/admin/knowledge`, { waitUntil: "networkidle0" });
    const cards = await a.evaluate(() => ["pg", "es", "neo4j"].map((k) => document.querySelector(`[data-stat="kb-3way-${k}"]`)?.innerText ?? ""));
    ok("3-way: 관리자 구성 카드(PostgreSQL · Elasticsearch · Neo4j)", cards.every(Boolean) && cards[0].includes("원장") && (!expectEs || cards[1].includes("사용 중")), cards.join(" | ").replace(/\n/g, " "));
  }

  // 9-0) 온톨로지 구성 지도 (Phase G · OV-01~05) — 원장 기준 3D 군집 지도 · 찾기 → 상세 · 구조도 · 표
  {
    await a.goto(`${BASE}/admin/ontology`, { waitUntil: "networkidle0" });
    await a.waitForSelector("[data-ontology-map] canvas[data-map-canvas]", { timeout: 30000 });
    await sleep(800);
    const drawn = await a.evaluate(() => {
      const cv = document.querySelector("[data-map-canvas]");
      const ctx = cv.getContext("2d");
      const { width, height } = cv;
      const img = ctx.getImageData(0, 0, width, height).data;
      let lit = 0;
      for (let i = 0; i < img.length; i += 4 * 37) if (img[i] + img[i + 1] + img[i + 2] > 200) lit++;
      return { lit, legend: document.querySelectorAll("[data-map-legend] button").length, clusters: document.querySelectorAll("[data-map-clusters] li").length, label: cv.getAttribute("aria-label") ?? "" };
    });
    ok("온톨로지 지도: 3D 군집 지도가 그려짐 · 범례 · 군집 목록", drawn.lit > 20 && drawn.legend >= 5 && drawn.clusters >= 2 && drawn.label.includes("군집"), JSON.stringify({ ...drawn, label: drawn.label.slice(0, 60) }));
    await a.type("[data-map-search]", "햇살");
    await a.waitForSelector("[data-map-hits] button", { timeout: 5000 }).catch(() => undefined);
    await a.evaluate(() => document.querySelector("[data-map-hits] button")?.click());
    await a.waitForSelector("[data-map-detail]", { timeout: 5000 }).catch(() => undefined);
    const det = await a.evaluate(() => document.querySelector("[data-map-detail]")?.innerText ?? "");
    ok("온톨로지 지도: 찾기 → 상세(출처 · 관계별 이웃)", det.includes("출처") && det.includes("관계") && det.includes("햇살"), det.slice(0, 120).replace(/\n/g, " | "));
    await shot(a, "07c-admin-ontology-map");
    await a.evaluate(() => [...document.querySelectorAll('[role="tab"]')].find((x) => x.innerText.trim() === "구조도")?.click());
    await a.waitForSelector("[data-schema-map] svg", { timeout: 5000 }).catch(() => undefined);
    const schemaArrows = await a.$$eval("[data-schema-map] path[marker-end]", (els) => els.length).catch(() => 0);
    ok("온톨로지 구조도: 클래스 ↔ 관계 유형 화살표", schemaArrows >= 5, `화살표 ${schemaArrows}`);
    await a.evaluate(() => [...document.querySelectorAll('[role="tab"]')].find((x) => x.innerText.trim() === "표")?.click());
    await a.waitForSelector("[data-ontology-tables] table", { timeout: 5000 }).catch(() => undefined);
    const tables = await a.$$eval("[data-ontology-tables] table", (els) => els.length).catch(() => 0);
    ok("온톨로지 표 보기: 군집 · 관계 구조 · 클래스 표", tables >= 3, `표 ${tables}`);
  }

  // 9-1) 관리자 홈 · 운영 개요 (Phase C · ADM-02 · MON-01) — 처리할 일 · 시스템 상태 · 시간대별 그래프(표로 보기)
  {
    await a.goto(`${BASE}/admin`, { waitUntil: "networkidle0" });
    await a.waitForFunction(() => !document.body.innerText.includes("불러오는 중"), { timeout: 15000 }).catch(() => undefined);
    const t = await text(a);
    ok("관리자 홈: 처리할 일 · 시스템 상태", t.includes("처리할 일") && t.includes("시스템 상태") && t.includes("워커") && t.includes("데이터베이스"), t.slice(0, 200).replace(/\n/g, " | "));
    const crumbs = await a.evaluate(() => document.querySelector('nav[aria-label="현재 위치"]')?.innerText ?? "");
    ok("관리자 홈: 위치 표시", crumbs.includes("관리자"), crumbs);
    // Phase E (NAV-01 · NAV-04 · Q122) — 관리자 첫 화면 = 관리자 홈, 관리 묶음이 먼저, 처리 대기 건수
    const me = (await api("/me")).body;
    const mm = (await api("/me/menu")).body;
    ok("관리자 첫 화면 = /admin · 처리 대기 건수", me?.home === "/admin" && typeof mm?.counts?.adminTodo === "number" && mm.counts.adminTodo === mm.counts.adminUsers + mm.counts.adminUploads + mm.counts.adminAnalyses, JSON.stringify({ home: me?.home, todo: mm?.counts?.adminTodo }));
    // [관리] 로 들어온 관리자 영역 = 공통 헤더 + 관리자 전용 사이드바(업무 화면 메뉴는 섞이지 않는다)
    const firstGroup = await a.evaluate(() => document.querySelector('aside nav[aria-label="관리자 메뉴"]')?.innerText.trim().split("\n")[0] ?? "");
    ok("관리자 사이드바: 관리 묶음만 · 관리자 홈이 먼저", firstGroup.startsWith("관리자 홈") && !(await a.evaluate(() => document.querySelector('aside nav[aria-label="관리자 메뉴"]')?.innerText ?? "")).includes("경영목표 설정"), firstGroup);
    await a.goto(`${BASE}/hq/overview`, { waitUntil: "networkidle0" });
    ok("관리자 헤더: [관리] 메뉴 + 세 영역 전환(종기부 · 사업부서 · 영업점)", await a.evaluate(() => !!document.querySelector('header a[href="/admin"]') && ["종기부", "사업부서", "영업점"].every((n) => [...document.querySelectorAll('header nav[aria-label="업무 영역 전환"] a')].some((x) => x.innerText.includes(n)))));
    await a.goto(`${BASE}/admin`, { waitUntil: "networkidle0" });
    // 역할 변경 = 확인 대화상자, 취소하면 그대로 (INT-01 · Q123)
    await a.goto(`${BASE}/admin/users`, { waitUntil: "networkidle0" });
    await a.evaluate(() => [...document.querySelectorAll('[role="tab"]')].find((x) => x.innerText.startsWith("전체"))?.click());
    await a.waitForFunction((emp) => [...document.querySelectorAll("tr")].some((tr) => tr.innerText.includes(emp)), { timeout: 10000 }, EMP);
    await a.evaluate((emp) => {
      const row = [...document.querySelectorAll("tr")].find((tr) => tr.innerText.includes(emp));
      const s = row && [...row.querySelectorAll("select")].find((x) => (x.getAttribute("aria-label") ?? "").endsWith("역할"));
      if (!s) return;
      Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value").set.call(s, "admin");
      s.dispatchEvent(new Event("change", { bubbles: true }));
    }, EMP);
    await a.waitForSelector("[data-confirm-dialog]", { timeout: 5000 }).catch(() => undefined);
    const dlg = await a.evaluate(() => document.querySelector("[data-confirm-dialog]")?.innerText ?? "");
    await a.click("[data-confirm-cancel]").catch(() => undefined);
    await sleep(500);
    const role = (await api("/admin/users")).body?.find((x) => x.empNo === EMP)?.role;
    const shown = await a.evaluate((emp) => {
      const row = [...document.querySelectorAll("tr")].find((tr) => tr.innerText.includes(emp));
      return row && [...row.querySelectorAll("select")].find((x) => (x.getAttribute("aria-label") ?? "").endsWith("역할"))?.value;
    }, EMP);
    ok("사용자 역할 → 관리자: 확인 대화상자 · 취소 시 그대로", dlg.includes("관리자 권한을 줄까요") && role === "user" && shown === "user", `${dlg.slice(0, 40).replace(/\n/g, " ")} / ${role} / ${shown}`);
    await shot(a, "07a-admin-users");
    await a.goto(`${BASE}/admin`, { waitUntil: "networkidle0" });
    await a.goto(`${BASE}/admin/monitor`, { waitUntil: "networkidle0" });
    await a.waitForFunction(() => !document.body.innerText.includes("불러오는 중"), { timeout: 15000 }).catch(() => undefined);
    const toggled = await a.evaluate(() => {
      const b = [...document.querySelectorAll("button")].find((x) => x.innerText.trim() === "표로 보기");
      b?.click();
      return Boolean(b);
    });
    await sleep(300);
    ok("운영 개요: 그래프 → 표로 보기", toggled && (await a.$$("figure table")).length >= 1);
    const crumbM = await a.evaluate(() => document.querySelector('nav[aria-label="현재 위치"]')?.innerText ?? "");
    ok("운영 개요: 위치(관리자 > 운영 모니터링 > 운영 개요)", crumbM.includes("운영 모니터링") && crumbM.includes("운영 개요"), crumbM.replace(/\n/g, " "));
    await shot(a, "07b-admin-monitor");
  }

  // 9-2) 업무 자료 요청 → 관리자 승인 (Phase C · UPL-01~03)
  {
    const title = `E2E 업무 자료 ${EMP}`;
    // 부서 데이터 책임자 지정 (UPL-04 · Q107) — 승인할 자료 화면 확인 후 해제
    const st = await api(`/admin/users/${EMP}`, { method: "PATCH", body: JSON.stringify({ data_steward: true }) });
    ok("관리자: 부서 데이터 책임자 지정", st.status === 200 && st.body?.dataSteward === true && st.body?.stewardScope?.code === "D100", JSON.stringify(st.body?.stewardScope));
    await u.goto(`${BASE}/knowledge`, { waitUntil: "networkidle0" });
    ok("데이터베이스: 자료 올리기 버튼(권한 있는 부서)", (await u.$("[data-upload-cta]")) !== null);
    ok("데이터베이스: 승인할 자료 버튼(데이터 책임자)", (await u.$("[data-steward-cta]")) !== null);
    // Phase E (UXF-05) — 표 행의 '새 버전 올리기' → 그 자료를 고른 채 [자료 올리기]
    ok("데이터베이스: 행마다 '새 버전 올리기'", (await u.$('[data-dataset-upload="PROVISION_BY_PRODUCT"]')) !== null);
    await Promise.all([u.waitForNavigation({ waitUntil: "networkidle0" }), u.click('[data-dataset-upload="PROVISION_BY_PRODUCT"]')]);
    await u.waitForSelector('[data-upload-selected="PROVISION_BY_PRODUCT"]', { timeout: 10000 }).catch(() => undefined);
    const deep = await u.evaluate(() => ({
      url: location.pathname + location.search,
      selected: document.querySelector('[data-upload-target="PROVISION_BY_PRODUCT"]')?.getAttribute("aria-checked"),
      blocker: document.querySelector("[data-upload-blocker]")?.textContent ?? "",
      disabled: document.querySelector("[data-upload-submit]")?.disabled ?? false,
    }));
    ok("자료 올리기 깊은 링크: 자료 미리 선택 · 못 누르는 이유(파일)", deep.url.includes("target=PROVISION_BY_PRODUCT") && deep.selected === "true" && deep.blocker.includes("파일") && deep.disabled, JSON.stringify(deep));
    // 파일 먼저 → 파일 이름으로 추천 (Q121 — 골라 두기만, 확정은 사용자)
    await u.goto(`${BASE}/knowledge/upload`, { waitUntil: "networkidle0" });
    ok("자료 올리기: 파일 놓기 영역이 첫 단계", (await u.$('[data-file-drop="upload"] input[type="file"]')) !== null);
    await (await u.$('[data-file-drop="upload"] input[type="file"]')).uploadFile(csvPath);
    await u.waitForSelector("[data-upload-suggestion]", { timeout: 10000 }).catch(() => undefined);
    const sug = await u.evaluate(() => ({
      text: document.querySelector("[data-upload-suggestion]")?.textContent ?? "",
      checked: document.querySelector('[data-upload-target="PROVISION_BY_PRODUCT"]')?.getAttribute("aria-checked"),
      reason: document.querySelector('[data-upload-target="PROVISION_BY_PRODUCT"]')?.textContent ?? "",
      enabled: !(document.querySelector("[data-upload-submit]")?.disabled ?? true),
    }));
    ok("자료 올리기: 파일 이름 → 7790 추천 · 근거 · 요청 가능", sug.checked === "true" && sug.text.includes("7790") && sug.reason.includes("보고서 번호 7790") && sug.enabled, JSON.stringify(sug).slice(0, 220));
    await shot(u, "08a-upload-suggest");
    // 문서 — 파일 없이 본문 붙여 넣기
    await u.goto(`${BASE}/knowledge/upload`, { waitUntil: "networkidle0" });
    await u.click("[data-upload-text-mode]");
    await u.waitForFunction(() => [...document.querySelectorAll('[role="radio"]')].some((x) => x.innerText.includes("참고")), { timeout: 10000 });
    await u.evaluate(() => [...document.querySelectorAll('[role="radio"]')].find((x) => x.innerText.includes("참고"))?.click());
    await u.waitForSelector("#up-title");
    await u.type("#up-title", title);
    await u.type("#up-text", "E2E 시험 문서 — 업무 부서가 올린 참고 자료입니다.");
    await u.click("[data-upload-submit]");
    await u.waitForSelector("[data-upload-last]", { timeout: 20000 });
    const last = await u.evaluate(() => document.querySelector("[data-upload-last]")?.innerText ?? "");
    ok("자료 올리기: 검사 후 승인 대기 요청", last.includes("승인 대기") && last.includes("본문"), last.replace(/\n/g, " | "));
    await shot(u, "08-knowledge-upload");
    await u.goto(`${BASE}/knowledge/upload?tab=review`, { waitUntil: "networkidle0" });
    await u.waitForFunction((t) => document.querySelector("[data-steward-review]")?.innerText.includes(t), { timeout: 15000 }, title).catch(() => undefined);
    const rv = await u.evaluate(() => document.querySelector("[data-steward-review]")?.innerText ?? "");
    ok("승인할 자료(데이터 책임자): 부서 요청 · 본인 요청은 다른 사람이", rv.includes(title) && rv.includes("본인이 올린 자료") && rv.includes("종합기획부 데이터 책임자"), rv.slice(0, 160).replace(/\n/g, " | "));
    await shot(u, "08c-steward-review");
    await a.goto(`${BASE}/admin/uploads`, { waitUntil: "networkidle0" });
    await a.waitForFunction((t) => document.body.innerText.includes(t), { timeout: 15000 }, title);
    const clicked = await a.evaluate((t) => {
      const card = [...document.querySelectorAll("section")].find((s) => s.innerText.includes(t) && s.querySelector("[data-upload-review]"));
      const btn = card && [...card.querySelectorAll("button")].find((b) => b.innerText.includes("승인하고 반영"));
      btn?.click();
      return Boolean(btn);
    }, title);
    await a.waitForFunction(() => document.body.innerText.includes("승인했습니다"), { timeout: 20000 }).catch(() => undefined);
    ok("자료 승인: 관리자 승인 → 반영", clicked && (await text(a)).includes("승인했습니다"));
    await shot(a, "08b-admin-uploads");
    await u.goto(`${BASE}/knowledge/upload`, { waitUntil: "networkidle0" });
    await u.waitForSelector("[data-my-uploads]", { timeout: 15000 });
    const mine = await u.evaluate(() => document.querySelector("[data-my-uploads] li")?.innerText ?? "");
    ok("내 요청: 승인 · 반영 표시", mine.includes("승인") && mine.includes(title.slice(0, 10)), mine.replace(/\n/g, " | "));
    await api(`/admin/users/${EMP}`, { method: "PATCH", body: JSON.stringify({ data_steward: false }) });
  }

  // 9-3) 분석 만들기 → 관리자 승인 → 부서 분석 탭 (Phase C · DAG-01~07)
  {
    await u.goto(`${BASE}/hq/analysis`, { waitUntil: "networkidle0" });
    ok("데이터 분석(종합기획부): 탭 줄에 '분석 만들기'", (await u.$("[data-custom-tabs] [data-builder-link]")) !== null);
    await u.goto(`${BASE}/analysis/builder?space=hq`, { waitUntil: "networkidle0" });
    await u.type("[data-builder-text]", "7790 상품별 충당금 자료로 상품명별 충당금 합계와 충당금이 많은 상위 상품을 보고 싶습니다.");
    await u.click("[data-builder-refine]");
    await u.waitForSelector("[data-builder-spec]", { timeout: 60000 });
    const specText = await u.evaluate(() => document.querySelector("[data-builder-spec]")?.innerText ?? "");
    ok("분석 만들기: 정제 → 명세(지표 · 표 · 의견)", specText.includes("지표") && specText.includes("SUM") && specText.includes("검증 통과"), specText.slice(0, 200).replace(/\n/g, " | "));
    await u.click("[data-builder-preview]");
    await u.waitForSelector("[data-builder-report]", { timeout: 60000 });
    const pv = await u.evaluate(() => document.querySelector("[data-builder-report]")?.innerText ?? "");
    ok("분석 만들기: 미리보기(계산 · 표 · 기본 의견)", pv.includes("저장되지 않았습니다") && (await u.$$("[data-builder-report] [data-report-metrics] li")).length >= 1, pv.slice(0, 160).replace(/\n/g, " | "));
    await shot(u, "09-analysis-builder");
    await u.click("[data-builder-request]");
    await u.waitForFunction(() => document.body.innerText.includes("승인 요청을 보냈습니다"), { timeout: 30000 });
    ok("분석 만들기: 승인 요청", (await text(u)).includes("승인 요청을 보냈습니다"));
    const pend = (await api("/admin/analysis-agents?status=pending")).body?.items ?? [];
    const agent = pend.find((x) => x.space === "hq");
    await a.goto(`${BASE}/admin/analysis-agents`, { waitUntil: "networkidle0" });
    await a.waitForSelector("button.row-button", { timeout: 15000 });
    await a.evaluate((title) => [...document.querySelectorAll("button.row-button")].find((b) => b.innerText.includes(title))?.click(), agent?.title ?? "");
    await a.waitForSelector("[data-analysis-review]", { timeout: 15000 });
    ok("분석 에이전트(관리자): 명세 · 미리보기 · 승인 기준(주기 · LLM)", (await text(a)).includes("미리보기 계산 결과") && (await text(a)).includes("지표") && (await a.$("[data-approval-options]")) !== null);
    await shot(a, "09b-admin-analysis-agents");
    await a.evaluate(() => [...document.querySelectorAll("[data-analysis-review] button")].find((b) => b.innerText.includes("승인하고 만들기"))?.click());
    await a.waitForFunction(() => document.body.innerText.includes("승인했습니다"), { timeout: 20000 }).catch(() => undefined);
    ok("분석 에이전트: 승인 → 생성", (await text(a)).includes("승인했습니다"));
    let tab = null;
    for (let i = 0; i < 60 && !tab; i++) {
      const tabs = await u.evaluate(async () => (await (await fetch("/backend/screens/analysis/hq/tabs")).json()).current ?? []);
      tab = tabs.find((t) => t.dynamic) ?? null;
      if (!tab) await sleep(2000);
    }
    ok("분석 에이전트: 첫 실행 → 부서 분석 탭", Boolean(tab), JSON.stringify(tab));
    if (tab) {
      await u.goto(`${BASE}/hq/analysis`, { waitUntil: "networkidle0" });
      ok("데이터 분석: 기존 탭 줄에 맞춤 분석 탭", (await u.$(`[data-custom-tab="${tab.tabKey}"]`)) !== null);
      await Promise.all([u.waitForNavigation({ waitUntil: "networkidle0" }), u.click(`[data-custom-tab="${tab.tabKey}"]`)]);
      const t = await text(u);
      ok("맞춤 분석 탭: 보고서(의견 · 지표 묶음) · 여신 실적 분석으로 돌아가는 탭", u.url().endsWith(`/hq/analysis/${tab.tabKey}`) && t.includes("맞춤") && t.includes("여신 실적 분석") && (await u.$$("[data-report-metrics] li")).length >= 1, u.url());
      await u.goto(`${BASE}/analysis/hq/${tab.tabKey}`, { waitUntil: "networkidle0" });
      ok("이전 주소 /analysis/hq/<탭> → /hq/analysis/<탭>", u.url().endsWith(`/hq/analysis/${tab.tabKey}`), u.url());
      await u.addScriptTag({ content: AXE });
      // preload: false — 외부 글꼴 CSS fetch 가 CSP(connect-src)에 막혀 콘솔 오류를 남기지 않도록 (8-5 와 같은 옵션)
      const ax = await u.evaluate(async () =>
        (await window.axe.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] }, resultTypes: ["violations"], preload: false })).violations
          .filter((v) => ["serious", "critical"].includes(v.impact))
          .map((v) => `${v.id}(${v.nodes.map((n) => n.target.join(" ")).slice(0, 3).join(" ; ")})`),
      );
      ok("부서 분석 화면: 접근성(axe serious · critical 0)", ax.length === 0, ax.join(","));
      await shot(u, "09c-analysis-hq");
      const code = tab.agent;
      if (code) await api(`/admin/analysis-agents/${code}/retire`, { method: "POST" });
    }
  }

  // 10) 로그아웃 · 정리
  await u.goto(`${BASE}/hq/overview`, { waitUntil: "networkidle0" });
  await u.evaluate(() => document.querySelector("[data-user-menu]")?.click());
  await sleep(250);
  await u.evaluate(() => [...document.querySelectorAll("button")].find((x) => x.innerText.includes("로그아웃"))?.click());
  await u.waitForNavigation({ waitUntil: "networkidle0" });
  await u.goto(`${BASE}/hq/goals`, { waitUntil: "networkidle0" });
  ok("로그아웃 후 접근 차단", u.url().includes("/login"), u.url());
  for (const emp of [EMP, BR_EMP]) await api(`/admin/users/${emp}/disable`, { method: "POST" });
  ok("브라우저 오류 없음", errors.length === 0, errors.slice(0, 5).join(" || "));
} catch (e) {
  ok("시나리오 실행", false, e.stack ?? String(e));
} finally {
  await restore().catch(() => undefined);
  await browser.close();
}
const failed = results.filter((r) => !r.pass);
console.log(`\n${results.length - failed.length}/${results.length} passed · 스크린샷 ${OUT}`);
fs.writeFileSync(path.join(OUT, "result.json"), JSON.stringify({ emp: EMP, brEmp: BR_EMP, results, errors }, null, 1));
process.exit(failed.length ? 1 : 0);
