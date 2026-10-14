"use client";

import { evalWidthQuery, fitPage, pageRule, printWidth } from "@/lib/printFit";
import { setPrinting } from "@/lib/printState";

/*
 * 화면 내보내기 — 한 장 PDF (EXP-01~03)
 * 1) html.printing 으로 화면에서 먼저 인쇄 배치를 만든다(고정 폭 · 도구 숨김 · 스크롤 영역 펼침 · 애니메이션 끝 상태 · 접힌 곳 펼침).
 * 2) 그 배치의 실제 크기를 재서 @page 크기를 정한다 → 내용 크기 그대로의 한 쪽.
 * 3) window.print() — 사용자는 "PDF 로 저장"을 고른다. 끝나면(afterprint) 원래 화면으로 되돌린다.
 */
const STYLE_ID = "print-page-style";
let running = false;

const frame = () => new Promise<void>((r) => requestAnimationFrame(() => requestAnimationFrame(() => r())));
const wait = (ms: number) => new Promise<void>((r) => window.setTimeout(r, ms));

interface Pinned {
  media: MediaList;
  original: string;
}

/**
 * 스타일시트의 폭 조건(min-width · max-width) 규칙을 목표 폭 기준으로 켜고 끈다(참이면 `all`, 거짓이면 `not all`).
 * 인쇄에서는 이 조건이 `@page` 로 정한 폭이 아니라 용지 기본 폭으로 판정돼 좁은 화면 배치가 되기 때문이다.
 * 같은 규칙으로 미리 재므로 측정할 때의 배치와 인쇄 결과가 같다. 끝나면 원래 조건으로 되돌린다.
 */
function pinWidthQueries(width: number): Pinned[] {
  const pinned: Pinned[] = [];
  const visit = (rules: CSSRuleList) => {
    for (const rule of Array.from(rules)) {
      if (typeof CSSMediaRule !== "undefined" && rule instanceof CSSMediaRule) {
        const verdict = evalWidthQuery(rule.media.mediaText, width);
        if (verdict !== null) {
          pinned.push({ media: rule.media, original: rule.media.mediaText });
          rule.media.mediaText = verdict ? "all" : "not all";
        }
      }
      const inner = (rule as CSSGroupingRule).cssRules;
      if (inner) visit(inner);
    }
  };
  for (const sheet of Array.from(document.styleSheets)) {
    try {
      visit(sheet.cssRules);
    } catch {
      // 다른 출처의 스타일시트(글꼴 CDN 등)는 규칙을 읽을 수 없다 — 건너뛴다
    }
  }
  return pinned;
}

function unpin(pinned: Pinned[]): void {
  for (const { media, original } of pinned) media.mediaText = original;
}

function measure(): { width: number; height: number } {
  const root = document.documentElement;
  const body = document.body;
  return { width: Math.max(root.scrollWidth, body.scrollWidth), height: Math.max(root.scrollHeight, body.scrollHeight) };
}

export async function printFitOnePage(): Promise<void> {
  if (running || typeof window === "undefined") return;
  running = true;
  const root = document.documentElement;
  let done = false;
  let pinned: Pinned[] = [];
  const cleanup = () => {
    if (done) return;
    done = true;
    unpin(pinned);
    document.getElementById(STYLE_ID)?.remove();
    root.classList.remove("printing");
    root.style.removeProperty("--print-w");
    setPrinting(false);
    window.removeEventListener("afterprint", cleanup);
    running = false;
  };
  try {
    const base = printWidth(window.innerWidth);
    pinned = pinWidthQueries(base);
    root.style.setProperty("--print-w", `${base}px`);
    root.classList.add("printing");
    setPrinting(true); // 접힌 곳을 펼친다(React 가 바로 다시 그린다)
    if (document.fonts?.ready) await document.fonts.ready;
    await frame();
    await wait(150); // 펼친 내용 · 차트가 자리 잡을 시간
    let content = measure();
    if (content.width > base) {
      // 가로로 넘치는 내용이 있으면 폭을 넓혀 다시 잰다 — 잘리는 것보다 넓은 쪽이 낫다
      unpin(pinned);
      pinned = pinWidthQueries(content.width);
      root.style.setProperty("--print-w", `${content.width}px`);
      await frame();
      content = measure();
    }
    const page = fitPage(content, base);
    const style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = pageRule(page);
    document.head.appendChild(style);
    window.addEventListener("afterprint", cleanup);
    window.setTimeout(cleanup, 120_000); // afterprint 가 오지 않는 브라우저를 위한 안전장치
    window.print();
  } catch (e) {
    cleanup();
    throw e;
  }
}
