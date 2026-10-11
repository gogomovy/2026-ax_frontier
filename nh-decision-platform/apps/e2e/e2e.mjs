// NHDIP 브라우저 E2E (QA-04 · 요구사항 B.11)
//   make e2e   (또는  cd apps/e2e && npm install && E2E_ADMIN_EMP=... E2E_ADMIN_PW=... node e2e.mjs)
//
// 시나리오: 가입(본부>부>국>팀) → 승인 → 로그인 → 소속 권한 메뉴 → 다른 부서 403 → 영업점 사용자(지역본부 상속)
//          → 7790 정정본 업로드 → 관련 워크플로우만 실행 → 화면 재계산 → 실행 모니터링 → 되돌리기 → 질의 패널 → 관리자 화면 → 로그아웃
// 실행 중 만든 사용자는 끝에 '중지' 처리하고, 데이터·설정은 원래대로 되돌린다.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import puppeteer from "puppeteer";

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
  ok("사용자 카드: 본부 > 부 > 국 > 팀", (await u.evaluate(() => document.querySelector("aside")?.innerText ?? "")).includes("경영기획본부 > 종합기획부 > 경영기획국 > 경영목표팀"));
  const side = await u.evaluate(() => document.querySelector("aside nav")?.innerText ?? "");
  ok("사이드바 = 소속 부서 + 공통", side.includes("경영목표 설정") && side.includes("데이터베이스") && !side.includes("수행방안"), side.replace(/\n+/g, " | "));
  await shot(u, "03-user-overview");
  for (const p of ["/hq/analysis", "/hq/goals", "/hq/capital", "/hq/initiatives", "/knowledge", "/knowledge/gov_policy", "/domains/loan"]) {
    await u.goto(BASE + p, { waitUntil: "networkidle0" });
    ok(`업무 화면 ${p}`, !u.url().includes("forbidden") && !(await text(u)).includes("찾는 화면이 없습니다"), u.url());
  }
  await u.goto(`${BASE}/risk`, { waitUntil: "networkidle0" });
  ok("다른 부서 화면 → 권한 없음", u.url().includes("/forbidden"), u.url());
  await u.goto(`${BASE}/admin`, { waitUntil: "networkidle0" });
  ok("관리자 화면 → 권한 없음", u.url().includes("/forbidden"), u.url());

  // 5) 질의 패널 (LLM 미연결이면 수치·근거만, 권한 밖 지표 제외)
  await u.goto(`${BASE}/hq/overview`, { waitUntil: "networkidle0" });
  await u.evaluate(() => [...document.querySelectorAll("button")].find((b) => b.innerText.includes("질문하기")).click());
  await u.waitForSelector("#assist-q");
  await u.type("#assist-q", "기업여신 증가율과 목표 대비 이탈은?");
  await u.evaluate(() => [...document.querySelectorAll("form button")].find((b) => b.innerText.trim() === "질문").click());
  await u.waitForSelector('[role="dialog"] article', { timeout: 30000 });
  const ans = await u.evaluate(() => document.querySelector('[role="dialog"] article')?.innerText ?? "");
  ok("질의 패널: 답변 카드에 확정 수치(커널)", ans.startsWith("Q. 기업여신 증가율") && /기업여신 증가율[^\n]*\n?\s*4\.04%/.test(ans) && ans.includes("목표 대비 이탈") && ans.includes("GROWTH_RATE"), ans.slice(0, 200).replace(/\n/g, " | "));
  ok("질의 패널: 수치 출처 확인 배지", ans.includes("수치 출처 확인"));
  await shot(u, "04-assist");

  // 6) 영업점 사용자 (지역본부 > 영업점)
  const b = await newPage(await browser.createBrowserContext());
  await signup(b, BR_EMP, "E2E지점", ["D300", "BR301"]);
  await api(`/admin/users/${BR_EMP}/approve`, { method: "POST" });
  await login(b, BR_EMP, PW);
  ok("영업점 사용자 → /branch (지역본부 권한 상속)", b.url().endsWith("/branch"), b.url());
  ok("영업점 사용자 카드: 지역본부 > 영업점", (await b.evaluate(() => document.querySelector("aside")?.innerText ?? "")).includes("수도권1지역본부 > 강남금융센터"));
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
  await a.evaluate(() => {
    const row = [...document.querySelectorAll("tr")].find((tr) => tr.innerText.includes("PROVISION_BY_PRODUCT"));
    [...row.querySelectorAll("button")].find((x) => x.innerText.includes("열기")).click();
  });
  await a.waitForSelector('input[type="file"]');
  await (await a.$('input[type="file"]')).uploadFile(csvPath);
  await a.evaluate(() => [...document.querySelectorAll("button")].find((x) => x.innerText.trim() === "업로드").click());
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

  // 9) 관리자 화면
  for (const p of ["/admin", "/admin/orgs", "/admin/screens", "/admin/llm", "/admin/agents", "/admin/workflows", "/admin/metrics", "/admin/contracts", "/admin/ontology", "/admin/rules", "/admin/audit", "/admin/monitor/flow", "/admin/pipeline", "/admin/monitor/calc", "/admin/monitor/trace", "/admin/monitor/evals", "/admin/monitor/alerts"]) {
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

  // 10) 로그아웃 · 정리
  await u.goto(`${BASE}/hq/overview`, { waitUntil: "networkidle0" });
  await u.evaluate(() => [...document.querySelectorAll("aside button")].find((x) => x.innerText.includes("로그아웃"))?.click());
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
