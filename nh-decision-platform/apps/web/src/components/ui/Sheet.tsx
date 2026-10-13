"use client";

import { useEffect, useId, useRef, type ReactNode } from "react";
import clsx from "clsx";
import { useUi } from "@/components/providers/UiProvider";
import { useFocusTrap } from "@/lib/a11y";

/**
 * 팝업 · 서랍 (가이드 G05 · 규칙 05 "결정은 팝업, 읽을거리는 서랍")
 *  - variant="popup"  : 결정. 세로 중앙, 우측 정렬, 최대 높이 80vh. 팝업 내용이 80vh 를 넘으면 본문만 스크롤하고 버튼은 내용 바로 아래에 둔다.
 *  - variant="drawer" : 읽을거리(근거 원문 · 받은 요청). 우측 전체 높이.
 * 공통
 *  - Esc 로 닫힘(근거 드로어가 위에 열려 있으면 드로어가 먼저 닫힘)
 *  - 열릴 때 패널로 포커스 이동, 닫히면 이전 포커스로 복귀
 *  - 배경 스크롤 잠금, Tab 이 패널 밖으로 나가지 않음
 */
export function Sheet({
  open,
  onClose,
  eyebrow,
  title,
  meta,
  children,
  footer,
  width = "md",
  variant = "drawer",
}: {
  open: boolean;
  onClose: () => void;
  eyebrow?: ReactNode;
  title: ReactNode;
  meta?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  width?: "md" | "lg";
  variant?: "drawer" | "popup";
}) {
  const { drawer } = useUi();
  const panelRef = useRef<HTMLElement>(null);
  const returnFocus = useRef<HTMLElement | null>(null);
  const titleId = useId();
  useFocusTrap(panelRef, open && !drawer, { autoFocus: false, restore: false });

  useEffect(() => {
    if (!open) return;
    returnFocus.current = document.activeElement as HTMLElement | null;
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const t = window.setTimeout(() => panelRef.current?.focus(), 10);
    return () => {
      window.clearTimeout(t);
      document.body.style.overflow = prevOverflow;
      returnFocus.current?.focus?.();
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !drawer) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose, drawer]);

  if (!open) return null;

  const popup = variant === "popup";

  return (
    <div
      className={clsx(
        "fixed inset-0 z-40 flex animate-fade-in no-print",
        popup ? "items-center justify-center p-4 md:justify-end md:p-7" : "justify-end",
      )}
    >
      <button type="button" aria-label="닫기" tabIndex={-1} onClick={onClose} className="absolute inset-0 cursor-default bg-scrim" />
      <section
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className={clsx(
          "relative flex w-full flex-col bg-canvas outline-none",
          popup
            ? clsx("max-h-[80vh] rounded-3xl shadow-popup animate-pop-in", width === "md" ? "max-w-[520px]" : "max-w-[560px]")
            : clsx("h-full shadow-popup animate-slide-in-right", width === "md" ? "max-w-[560px]" : "max-w-[720px]"),
        )}
      >
        <header className={clsx("flex items-start gap-base", popup ? "px-7 pb-3 pt-6" : "border-b border-hairline-soft px-7 py-5")}>
          <div className="min-w-0 flex-1">
            {eyebrow ? <div className="mb-2 flex min-h-[24px] flex-wrap items-center gap-2 text-[14px] font-bold text-primary">{eyebrow}</div> : null}
            <h2 id={titleId} className={clsx("font-bold text-ink-deep", popup ? "text-[20px] leading-[1.3]" : "text-[20px] leading-[1.3]")}>
              {title}
            </h2>
            {meta ? <p className="mt-1.5 text-[12px] leading-normal text-steel">{meta}</p> : null}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="inline-flex h-8 shrink-0 items-center rounded-md border border-hairline bg-canvas px-3 text-[13px] font-bold text-ink-deep hover:bg-surface-soft"
          >
            닫기
          </button>
        </header>

        <div className={clsx("min-h-0 flex-1 overflow-y-auto", popup ? "px-7 pb-2" : "px-7 py-5")}>{children}</div>

        {footer ? (
          <footer
            className={clsx(
              "flex flex-wrap items-center gap-xs bg-canvas px-7",
              popup ? "rounded-b-3xl pb-6 pt-3" : "border-t border-hairline-soft py-4",
            )}
          >
            {footer}
          </footer>
        ) : popup ? (
          <div className="h-5" aria-hidden="true" />
        ) : null}
      </section>
    </div>
  );
}

/** 시트 본문 블록 — 소제목(14px Bold) + 내용. 구분선은 얇게 */
export function SheetSection({
  title,
  aside,
  children,
}: {
  title: ReactNode;
  aside?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="border-b border-hairline-soft py-5 first:pt-2 last:border-0 last:pb-1">
      <div className="mb-3 flex items-baseline justify-between gap-base">
        <h3 className="text-[14px] font-bold text-ink-deep">{title}</h3>
        {aside}
      </div>
      {children}
    </section>
  );
}
