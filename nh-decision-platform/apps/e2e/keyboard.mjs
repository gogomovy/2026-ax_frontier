// AI 어시스턴트 패널 키보드 전용 점검 (ASK-04 · 접근성) — 마우스 없이 Tab · Shift+Tab · Enter · Space · Esc · Alt+Q 만으로 쓸 수 있는지 확인한다.
//   make keyboard   (또는  cd apps/e2e && E2E_ADMIN_EMP=... E2E_ADMIN_PW=... node keyboard.mjs)
//
// 보는 것: ① 로그인 폼을 키보드로 제출 ② 화면 어디서든 Tab 만으로 'AI 어시스턴트' 버튼에 닿고 포커스 표시가 보임 ③ Enter 로 열면 포커스가 패널 안으로 들어감
//          ④ Tab · Shift+Tab 이 패널 밖으로 나가지 않음(포커스 가둠) ⑤ 질문을 키보드로 입력 · 제출하면 답이 나오고 피드백 버튼에 Tab 으로 닿음
//          ⑥ Esc 로 닫히고 포커스가 'AI 어시스턴트' 버튼으로 돌아옴 ⑦ Space 로도 다시 열림, 단축키 Alt+Q 로 어디서든 열고 닫음 ⑧ Shift+Enter 줄바꿈 · 다시 생성도 키보드로
// 화면 낭독기로 읽히는지는 자동으로 알 수 없다 — 낭독기 실사용은 별도로 필요하다. 이 점검은 키보드 흐름이 끊기지 않는지만 본다.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import puppeteer from "puppeteer";

const BASE = process.env.E2E_BASE ?? "http://localhost:3000";
const ADMIN = process.env.E2E_ADMIN_EMP;
const ADMIN_PW = process.env.E2E_ADMIN_PW;
const START = process.env.KEYBOARD_PAGE ?? "/hq/overview";
const OUT = process.env.E2E_OUT ?? path.join(os.tmpdir(), "nhdip-e2e");
if (!ADMIN || !ADMIN_PW) {
  console.error("E2E_ADMIN_EMP · E2E_ADMIN_PW 가 필요합니다 (make keyboard 는 .env 의 BOOTSTRAP_ADMIN_* 를 사용)");
  process.exit(2);
}
fs.mkdirSync(OUT, { recursive: true });

const results = [];
const ok = (name, cond, detail = "") => {
  results.push({ name, pass: !!cond, detail });
  console.log(`${cond ? "PASS" : "FAIL"}  ${name}${detail ? " — " + detail : ""}`);
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const browser = await puppeteer.launch({ headless: true, args: ["--no-sandbox"] });
const errors = [];
try {
  const page = await (await browser.createBrowserContext()).newPage();
  await page.setViewport({ width: 1440, height: 900 });
  page.on("pageerror", (e) => errors.push(`${page.url()} ${e.message}`));
  /** 키 입력 — "Shift+Tab" · "Alt+KeyQ" 처럼 수식키 조합도 받는다 */
  const press = async (key, n = 1) => {
    const parts = key.split("+");
    const last = parts.pop();
    for (let i = 0; i < n; i++) {
      for (const m of parts) await page.keyboard.down(m);
      await page.keyboard.press(last);
      for (const m of parts.reverse()) await page.keyboard.up(m);
      parts.reverse();
    }
  };
  /** 지금 포커스가 있는 요소의 설명 — 이름 · 역할 · 패널 안 여부 · 포커스 표시 */
  const focused = () =>
    page.evaluate(() => {
      const el = document.activeElement;
      if (!el || el === document.body) return { none: true };
      const cs = getComputedStyle(el);
      const dlg = document.querySelector('[role="dialog"]');
      const label = (el.getAttribute("aria-label") || el.innerText || el.getAttribute("placeholder") || el.id || el.tagName).trim().replace(/\s+/g, " ").slice(0, 60);
      return {
        tag: el.tagName, id: el.id, label, inDialog: !!dlg && dlg.contains(el), isDialog: el === dlg,
        // 포커스 표시: 외곽선이 있거나 그림자 링이 있어야 한다(둘 다 없으면 키보드 사용자가 위치를 잃는다)
        indicator: (cs.outlineStyle !== "none" && parseFloat(cs.outlineWidth) > 0) || (cs.boxShadow && cs.boxShadow !== "none"),
      };
    });
  /** Tab 을 최대 max 번 눌러 조건에 맞는 요소에 닿는다 — 닿은 횟수를 돌려준다(못 닿으면 -1) */
  const tabUntil = async (pred, max = 80, key = "Tab") => {
    for (let i = 1; i <= max; i++) {
      await press(key);
      const f = await focused();
      if (!f.none && pred(f)) return { n: i, f };
    }
    return { n: -1, f: await focused() };
  };

  // ① 로그인 — 키보드만
  await page.goto(`${BASE}/login?next=${START}`, { waitUntil: "networkidle0" });
  await page.focus("#emp_no"); // 시작 위치만 잡는다(첫 입력칸) — 이후는 모두 키보드
  await page.keyboard.type(ADMIN);
  await press("Tab");
  await page.keyboard.type(ADMIN_PW);
  await Promise.all([press("Enter"), page.waitForNavigation({ waitUntil: "networkidle0", timeout: 30000 })]);
  ok("로그인: 키보드(Tab · Enter)로 제출", page.url().endsWith(START), page.url());

  // ② AI 어시스턴트 버튼까지 Tab 만으로 — 뒤로(Shift+Tab)로 바로 닿는 위치(문서 끝)가 아니라 앞에서부터
  await page.evaluate(() => {
    document.activeElement?.blur?.();
    window.scrollTo(0, 0);
  });
  const toBtn = await tabUntil((f) => f.label.includes("AI 어시스턴트") && f.tag === "BUTTON", 120);
  ok("AI 어시스턴트 버튼: Tab 으로 닿음", toBtn.n > 0, toBtn.n > 0 ? `${toBtn.n}번째 Tab` : `닿지 못함 (마지막 포커스: ${toBtn.f.label})`);
  ok("AI 어시스턴트 버튼: 포커스 표시가 보임", toBtn.f.indicator === true);

  // ③ Enter 로 열기 → 포커스가 패널 안으로
  await press("Enter");
  await page.waitForSelector('[role="dialog"]', { timeout: 5000 });
  await sleep(300); // 시트가 열린 직후 포커스를 옮긴다(10ms 지연)
  const afterOpen = await focused();
  ok("Enter 로 열림: 포커스가 패널 안으로 이동", afterOpen.inDialog === true, afterOpen.label);
  ok("패널: 대화상자 이름이 있음(aria-labelledby)", await page.evaluate(() => {
    const d = document.querySelector('[role="dialog"]');
    const id = d?.getAttribute("aria-labelledby");
    return !!id && (document.getElementById(id)?.innerText || "").trim().length > 0 && d.getAttribute("aria-modal") === "true";
  }));

  // ④ 포커스 가둠 — Tab 40번 · Shift+Tab 10번 모두 패널 안
  let leaked = 0;
  for (let i = 0; i < 40; i++) {
    await press("Tab");
    const f = await focused();
    if (f.none || !f.inDialog) leaked++;
  }
  for (let i = 0; i < 10; i++) {
    await press("Shift+Tab");
    const f = await focused();
    if (f.none || !f.inDialog) leaked++;
  }
  ok("Tab · Shift+Tab: 포커스가 패널 밖으로 나가지 않음", leaked === 0, `이탈 ${leaked}회 / 50회`);

  // ⑤ 질문 입력 · 제출 · 피드백 — 전부 키보드
  const toInput = await tabUntil((f) => f.id === "assist-q", 40);
  ok("질문 입력칸: Tab 으로 닿음", toInput.n > 0, toInput.n > 0 ? `${toInput.n}번째 Tab` : "닿지 못함");
  // Shift+Enter 는 줄바꿈이고 전송하지 않는다 (Enter 만 전송)
  await page.keyboard.type("줄");
  await press("Shift+Enter");
  await page.keyboard.type("바꿈");
  ok("Shift+Enter: 줄바꿈이 들어가고 전송되지 않음", (await page.$eval("#assist-q", (e) => e.value)) === "줄\n바꿈" && !(await page.$('[role="dialog"] article')));
  await press("Control+KeyA");
  await press("Backspace");
  await page.keyboard.type("기업여신 증가율과 목표 대비 이탈은?");
  await press("Tab");
  const submitBtn = await focused();
  ok("입력칸 다음 Tab: 질문 버튼(활성)", submitBtn.label === "질문" && submitBtn.tag === "BUTTON", submitBtn.label);
  ok("질문 버튼: 포커스 표시가 보임", submitBtn.indicator === true);
  await press("Enter");
  await page.waitForSelector('[role="dialog"] article[data-status="done"]', { timeout: 60000 });
  const answer = await page.$eval('[role="dialog"] article', (a) => a.innerText);
  const asked = await page.$eval('[role="dialog"] [data-role="user"]', (a) => a.innerText);
  ok("Enter 로 제출: 내 질문 말풍선 + 답변이 나옴", asked.includes("기업여신 증가율") && answer.includes("기업여신 증가율"), answer.slice(0, 80).replace(/\n/g, " | "));
  ok("대화 영역 · 상태 안내 영역이 있음(role=log · role=status)", await page.evaluate(() => !!document.querySelector('[role="dialog"] [role="log"]') && !!document.querySelector('[role="dialog"] [role="status"][aria-live="polite"]')));
  // 제출하면 포커스가 입력칸으로 돌아와 이어서 물을 수 있다(ChatGPT 와 같음)
  const afterAnswer = await focused();
  ok("제출 뒤 포커스가 입력칸에 있음", afterAnswer.id === "assist-q", afterAnswer.label ?? "(없음)");
  const toFeedback = await tabUntil((f) => f.label === "도움이 됨", 60);
  ok("피드백 버튼: Tab 으로 닿음", toFeedback.n > 0, toFeedback.n > 0 ? `${toFeedback.n}번째 Tab` : "닿지 못함");
  await press("Enter");
  await page.waitForFunction(() => document.querySelector('[role="dialog"]')?.innerText.includes("의견을 남겼습니다"), { timeout: 10000 }).catch(() => undefined);
  ok("Enter 로 피드백: 확인 문구가 나옴", await page.evaluate(() => document.querySelector('[role="dialog"]')?.innerText.includes("의견을 남겼습니다")));
  const afterFeedback = await focused();
  ok("피드백 뒤 포커스가 패널 안(눌렀던 버튼)에 남음", afterFeedback.inDialog === true, afterFeedback.label ?? "(없음)");
  // 다시 생성 — 키보드로 닿고 Enter 로 새 답이 만들어진다
  const toRegen = await tabUntil((f) => f.label === "다시 생성", 40, "Shift+Tab").then((r) => (r.n > 0 ? r : tabUntil((f) => f.label === "다시 생성", 60)));
  ok("다시 생성 버튼: 키보드로 닿음", toRegen.n > 0, toRegen.n > 0 ? `${toRegen.n}번째 이동` : "닿지 못함");
  await press("Enter");
  await page.waitForFunction(() => document.querySelectorAll('[role="dialog"] article[data-status="done"]').length === 1 && document.querySelectorAll('[role="dialog"] article').length === 1, { timeout: 60000 }).catch(() => undefined);
  ok("Enter 로 다시 생성: 답이 새로 만들어짐(답 1개 유지)", await page.evaluate(() => document.querySelectorAll('[role="dialog"] article[data-status="done"]').length === 1 && document.querySelectorAll('[role="dialog"] [data-role="user"]').length === 1));

  // ⑥ Esc 로 닫기 → 포커스가 AI 어시스턴트 버튼으로 복귀
  await press("Escape");
  await sleep(300);
  const closed = await page.evaluate(() => !document.querySelector('[role="dialog"]'));
  ok("Esc: 패널이 닫힘", closed);
  const back = await focused();
  ok("닫힌 뒤 포커스가 'AI 어시스턴트' 버튼으로 복귀", back.label?.includes("AI 어시스턴트") === true && back.tag === "BUTTON", back.label ?? "(없음)");

  // ⑦ Space 로 다시 열기 · Esc · 단축키 Alt+Q 로 열고 닫기(어디서든)
  await press("Space");
  await page.waitForSelector('[role="dialog"]', { timeout: 5000 }).catch(() => undefined);
  ok("Space 로도 열림", await page.evaluate(() => !!document.querySelector('[role="dialog"]')));
  await press("Escape");
  await sleep(200);
  ok("다시 Esc: 닫힘", await page.evaluate(() => !document.querySelector('[role="dialog"]')));
  await page.evaluate(() => document.activeElement?.blur?.());
  await press("Alt+KeyQ");
  await page.waitForSelector('[role="dialog"]', { timeout: 5000 }).catch(() => undefined);
  ok("Alt+Q: 어디서든 열림 + 입력칸으로 포커스", (await page.evaluate(() => !!document.querySelector('[role="dialog"]'))) && (await sleep(200), (await focused()).id === "assist-q"));
  await press("Alt+KeyQ");
  await sleep(250);
  ok("Alt+Q: 다시 누르면 닫히고 포커스가 버튼으로", (await page.evaluate(() => !document.querySelector('[role="dialog"]'))) && (await focused()).label?.includes("AI 어시스턴트") === true);

  ok("페이지 오류 없음", errors.length === 0, errors.slice(0, 2).join(" | "));
  await page.screenshot({ path: path.join(OUT, "keyboard-final.png") });
} catch (e) {
  ok("키보드 점검 실행", false, String(e?.message ?? e).slice(0, 300));
} finally {
  await browser.close();
}
const failed = results.filter((r) => !r.pass);
console.log(`\n${results.length - failed.length}/${results.length} 통과`);
process.exit(failed.length ? 1 : 0);
