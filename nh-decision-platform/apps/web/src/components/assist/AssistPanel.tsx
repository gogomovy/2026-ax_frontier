"use client";

import clsx from "clsx";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { useApiSession } from "@/components/providers/SessionProvider";
import { useFocusTrap } from "@/lib/a11y";
import { ChatWorkspace } from "./ChatWorkspace";
import { IconChat } from "./icons";
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

  useFocusTrap(panelRef, open, { autoFocus: false, restore: false });

  const close = useCallback(() => {
    setOpen(false);
    window.setTimeout(() => launcherRef.current?.focus(), 0); // 닫으면 열었던 버튼으로
  }, []);

  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = prev;
      window.removeEventListener("keydown", onKey);
    };
  }, [open, close]);

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

  return (
    <>
      <button
        ref={launcherRef}
        type="button"
        onClick={() => {
          load();
          setOpen(true);
        }}
        className="fixed bottom-6 right-6 z-40 flex items-center gap-2 rounded-pill bg-ink-deep px-5 py-3 text-[13px] font-bold text-white shadow-pop no-print"
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-keyshortcuts="Alt+Q"
        title="질문하기 (Alt+Q)"
      >
        <IconChat size={18} /> 질문하기
        {working && !open ? (
          <span className="flex items-center gap-1 rounded-pill bg-white/20 px-2 py-0.5 text-[11px] font-medium">
            <span aria-hidden="true" className="h-1.5 w-1.5 rounded-circle bg-white motion-safe:animate-pulse" />
            답변 중
          </span>
        ) : null}
      </button>
      {open ? (
        <div className="fixed inset-0 z-40 flex justify-end no-print">
          <button type="button" aria-label="닫기" tabIndex={-1} onClick={close} className="flex-1 bg-scrim" />
          <section
            ref={panelRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
            tabIndex={-1}
            className={clsx("relative flex h-full w-full flex-col bg-canvas shadow-pop outline-none", expanded ? "max-w-none" : "max-w-[880px]")}
          >
            <ChatWorkspace chat={chat} pathname={pathname} expanded={expanded} onToggleExpand={() => setExpanded((v) => !v)} onClose={close} titleId={titleId} />
          </section>
        </div>
      ) : null}
    </>
  );
}
