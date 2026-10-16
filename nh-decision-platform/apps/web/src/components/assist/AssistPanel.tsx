"use client";

import clsx from "clsx";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { useApiSession } from "@/components/providers/SessionProvider";
import { useFocusTrap } from "@/lib/a11y";
import { ChatWorkspace } from "./ChatWorkspace";
import { ASSIST_HINT, ASSIST_NAME } from "./brand";
import { useAssistChat } from "./useAssistChat";

/**
 * 질문하기 (UX-06 · ASK) — 화면 오른쪽 아래 버튼으로 여는 ChatGPT 형 대화 패널.
 * 확정 수치(계산 커널) · 우리 팀 분석 결과 · 근거 문서만으로 답하고, 답은 스트리밍으로 나온다.
 * 대화 상태는 패널 바깥(이 컴포넌트)에 두어 패널을 닫아도 진행 중인 답이 이어진다. 대화는 이 브라우저 탭에만 저장한다(서버 저장 없음).
 */
export function AssistPanel() {
  const pathname = usePathname() || "/";
  const { user } = useApiSession();
  const chat = useAssistChat(user?.empNo ?? null, pathname);
  const [open, setOpen] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const launcherRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLElement>(null);
  const titleId = useId();
  const { load } = chat;

  // 데스크톱(1024px 이상)에서는 우측 드로어(가이드 440px)로 붙여 본문을 밀어내고, 좁은 화면 · 크게 보기에서는 위에 덮는다
  const [wide, setWide] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia?.("(min-width: 1024px)");
    if (!mq) return;
    const sync = () => setWide(mq.matches);
    sync();
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);
  const docked = open && wide && !expanded;
  const modal = open && !docked;

  useFocusTrap(panelRef, modal, { autoFocus: false, restore: false });

  const close = useCallback(() => {
    setOpen(false);
    window.setTimeout(() => launcherRef.current?.focus(), 0); // 닫으면 열었던 버튼으로
  }, []);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, close]);

  // 덮는 패널일 때만 뒤 화면 스크롤을 막는다
  useEffect(() => {
    if (!modal) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [modal]);

  // 붙는 드로어일 때 셸 본문(.assist-push)이 드로어 폭만큼 줄어든다 (globals.css)
  useEffect(() => {
    if (!docked) return;
    const root = document.documentElement;
    root.setAttribute("data-assist-open", "");
    return () => root.removeAttribute("data-assist-open");
  }, [docked]);

  // 단축키 Alt+Q — 버튼이 화면 끝(Tab 순서 맨 뒤)에 있어 키보드만으로는 멀리 돌아가야 하므로 어디서든 열고 닫는다
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.altKey && !e.ctrlKey && !e.metaKey && !e.shiftKey && e.code === "KeyQ") {
        e.preventDefault();
        if (open) close();
        else {
          load();
          setOpen(true);
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, close, load]);

  const working = chat.busyId !== null;

  // 버튼 글자 — 'AI 어시스턴트' ↔ 안내 문구를 번갈아 보여 주고, 버튼 폭은 글자에 맞춰 늘었다 줄었다 한다(시안 안 1-A).
  // 한 번 열어 본 뒤 · 답변 중 · 패널이 열려 있을 때 · 움직임 줄이기 설정이면 이름만 보여 준다.
  const [hint, setHint] = useState(false);
  // 이 탭에서 한 번 열어 봤는지 — 효과는 애니메이션에만 쓰므로 첫 렌더 차이는 화면에 영향이 없다
  const [used, setUsed] = useState(() => {
    try {
      return typeof window !== "undefined" && window.sessionStorage.getItem("assist.launcher.used") === "1";
    } catch {
      return false;
    }
  });
  const nameRef = useRef<HTMLSpanElement>(null);
  const hintRef = useRef<HTMLSpanElement>(null);
  const [widths, setWidths] = useState<{ name: number; hint: number } | null>(null);
  useEffect(() => {
    const measure = () => setWidths({ name: nameRef.current?.offsetWidth ?? 0, hint: hintRef.current?.offsetWidth ?? 0 });
    measure();
    document.fonts?.ready.then(measure).catch(() => undefined);
  }, []);
  useEffect(() => {
    if (open || working || used) return;
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
    let t = 0;
    let shown = 0;
    const MAX_HINTS = 3; // 안내 문구는 세 번까지만 — 그 뒤엔 이름으로 고정(계속 움직이면 거슬린다)
    const loop = (next: boolean) => {
      if (next && shown >= MAX_HINTS) return;
      t = window.setTimeout(() => {
        if (next) shown += 1;
        setHint(next);
        loop(!next);
      }, next ? 8000 : 4000); // 이름 8초 → 안내 4초
    };
    loop(true);
    return () => window.clearTimeout(t);
  }, [open, working, used]);
  const showHint = hint && !open && !working && !used;
  const markUsed = () => {
    setUsed(true);
    try {
      window.sessionStorage.setItem("assist.launcher.used", "1");
    } catch {
      /* 무시 */
    }
  };

  return (
    <>
      <button
        ref={launcherRef}
        type="button"
        onClick={() => {
          load();
          markUsed();
          setOpen(true);
        }}
        className="fixed bottom-4 right-4 z-40 flex h-[52px] min-w-[52px] items-center justify-center gap-2 rounded-pill border border-info-line bg-canvas px-4 text-[15px] font-bold text-primary-deep shadow-[0_4px_14px_rgba(59,63,184,0.10),0_1px_2px_rgba(30,31,46,0.05)] transition-colors duration-300 hover:border-primary hover:bg-info-faint no-print sm:bottom-12 sm:right-8 sm:pl-4 sm:pr-5"
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-keyshortcuts="Alt+Q"
        aria-label={`${ASSIST_NAME} (Alt+Q)`}
      >
        {/* 말풍선 + ✦ — 챗봇임을 바로 알 수 있게 */}
        <svg aria-hidden="true" viewBox="0 0 24 24" width="22" height="22" className="shrink-0 text-primary">
          <path d="M4 5.5C4 4.4 4.9 3.5 6 3.5H18C19.1 3.5 20 4.4 20 5.5V14.5C20 15.6 19.1 16.5 18 16.5H10.5L6.6 19.9C6.2 20.2 5.6 19.9 5.6 19.4V16.5H6C4.9 16.5 4 15.6 4 14.5V5.5Z" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
          <path d="M12 6.4C12.3 8.6 13.4 9.7 15.6 10C13.4 10.3 12.3 11.4 12 13.6C11.7 11.4 10.6 10.3 8.4 10C10.6 9.7 11.7 8.6 12 6.4Z" fill="currentColor" />
        </svg>
        {/* 글자 칸 — 폭이 이름 ↔ 안내 문구 길이로 부드럽게 바뀐다 */}
        <span
          aria-hidden="true"
          className="relative h-[22px] overflow-hidden whitespace-nowrap transition-[width] duration-[1400ms] ease-in-out max-sm:hidden"
          style={widths ? { width: showHint ? widths.hint : widths.name } : undefined}
        >
          <span className={clsx("absolute left-0 top-0 leading-[22px] transition-opacity duration-[900ms]", showHint ? "opacity-0" : "opacity-100 delay-[600ms]")}>{ASSIST_NAME}</span>
          <span className={clsx("absolute left-0 top-0 leading-[22px] transition-opacity duration-[900ms]", showHint ? "opacity-100 delay-[600ms]" : "opacity-0")}>{ASSIST_HINT}</span>
          {/* 폭 재기용(보이지 않음) */}
          <span ref={nameRef} className="invisible absolute leading-[22px]">
            {ASSIST_NAME}
          </span>
          <span ref={hintRef} className="invisible absolute leading-[22px]">
            {ASSIST_HINT}
          </span>
        </span>
        {working && !open ? (
          <span className="flex items-center gap-1 rounded-pill bg-info-soft px-2 py-0.5 text-[11px] font-medium text-primary-deep">
            <span aria-hidden="true" className="h-1.5 w-1.5 rounded-circle bg-primary motion-safe:animate-pulse" />
            <span className="max-sm:sr-only">답변 중</span>
          </span>
        ) : null}
      </button>
      {open ? (
        <div className={clsx("fixed z-40 flex justify-end no-print", docked ? "bottom-0 right-0 top-[var(--header-h)] w-[var(--assist-drawer-w)]" : "inset-0")}>
          {docked ? null : <button type="button" aria-label="닫기" tabIndex={-1} onClick={close} className="flex-1 bg-scrim" />}
          <section
            ref={panelRef}
            role="dialog"
            aria-modal={modal ? "true" : undefined}
            aria-labelledby={titleId}
            tabIndex={-1}
            className={clsx(
              "relative flex h-full w-full flex-col bg-canvas outline-none",
              docked ? "border-l border-hairline-soft" : clsx("shadow-pop", expanded ? "max-w-none" : "max-w-[880px]"),
            )}
          >
            <ChatWorkspace chat={chat} pathname={pathname} expanded={expanded} onToggleExpand={() => setExpanded((v) => !v)} onClose={close} titleId={titleId} />
          </section>
        </div>
      ) : null}
    </>
  );
}
