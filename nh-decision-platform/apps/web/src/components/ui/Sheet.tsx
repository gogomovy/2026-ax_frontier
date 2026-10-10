"use client";

import { useEffect, useRef, type ReactNode } from "react";
import clsx from "clsx";
import { useUi } from "@/components/providers/UiProvider";
import { IconClose } from "@/components/ui/primitives";

/**
 * 우측 상세 시트.
 * 목록에서는 요약만 보여주고, 판단 문장·근거·검증·액션은 시트에서 다룬다.
 *  - Esc 로 닫힘(근거 드로어가 위에 열려 있으면 드로어가 먼저 닫힘)
 *  - 열릴 때 시트로 포커스 이동, 닫히면 이전 포커스로 복귀
 *  - 배경 스크롤 잠금
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
}: {
  open: boolean;
  onClose: () => void;
  eyebrow?: ReactNode;
  title: ReactNode;
  meta?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  width?: "md" | "lg";
}) {
  const { drawer } = useUi();
  const panelRef = useRef<HTMLElement>(null);
  const returnFocus = useRef<HTMLElement | null>(null);

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

  return (
    <div className="fixed inset-0 z-40 flex justify-end no-print">
      <button
        type="button"
        aria-label="닫기"
        tabIndex={-1}
        onClick={onClose}
        className="flex-1 bg-[rgba(10,19,23,0.28)]"
      />
      <section
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        tabIndex={-1}
        className={clsx(
          "flex h-full w-full flex-col bg-canvas shadow-pop outline-none",
          width === "md" ? "max-w-[600px]" : "max-w-[760px]",
        )}
      >
        <header className="flex items-start gap-base border-b border-hairline-soft px-xl py-lg">
          <div className="min-w-0 flex-1">
            {eyebrow ? <div className="mb-1.5 flex flex-wrap items-center gap-1.5">{eyebrow}</div> : null}
            <h2 className="text-[18px] font-bold leading-snug text-ink-deep">{title}</h2>
            {meta ? <p className="mt-1 text-[12px] text-steel">{meta}</p> : null}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="닫기"
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-circle bg-surface-soft text-charcoal"
          >
            <IconClose />
          </button>
        </header>

        <div className="flex-1 overflow-y-auto px-xl py-lg">{children}</div>

        {footer ? (
          <footer className="flex flex-wrap items-center gap-xs border-t border-hairline-soft bg-canvas px-xl py-base">
            {footer}
          </footer>
        ) : null}
      </section>
    </div>
  );
}

/** 시트 본문 블록 — 소제목 + 내용 */
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
    <section className="border-b border-hairline-soft py-lg first:pt-0 last:border-0 last:pb-0">
      <div className="mb-2.5 flex items-baseline justify-between gap-base">
        <h3 className="text-[12px] font-bold text-steel">{title}</h3>
        {aside}
      </div>
      {children}
    </section>
  );
}
