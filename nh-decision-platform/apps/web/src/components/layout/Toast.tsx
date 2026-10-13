"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import clsx from "clsx";
import { useUi } from "@/components/providers/UiProvider";
import { IconCheck, IconChevron } from "@/components/ui/primitives";

/**
 * 알림 토스트 (Phase E · INT-02 · 가이드 G05) — 하단 중앙, 3~4초 뒤 사라지고 이동 링크는 1개.
 * 성공 · 안내는 status(polite), 실패는 alert(바로 읽음) · 다른 색 · 다른 아이콘.
 */
export function Toast() {
  const { toast } = useUi();
  const pathname = usePathname();
  const error = toast?.tone === "error";
  return (
    <>
      <div role="status" aria-live="polite" className="pointer-events-none fixed bottom-8 left-1/2 z-[60] -translate-x-1/2 no-print">
        {toast && !error ? (
          <div
            key={toast.id}
            className="pointer-events-auto flex animate-toast-in items-center gap-3 rounded-xl bg-ink-deep px-5 py-3 text-[14px] font-medium text-white shadow-toast"
            data-toast="success"
          >
            {toast.tone === "info" ? <span aria-hidden="true">ⓘ</span> : <IconCheck className="shrink-0 text-white" />}
            <span>{toast.message}</span>
            {toast.action && pathname !== toast.action.href ? (
              <>
                <span aria-hidden="true" className="h-4 w-px bg-white/30" />
                <Link href={toast.action.href} className="inline-flex shrink-0 items-center gap-0.5 font-bold text-white">
                  {toast.action.label}
                  <IconChevron />
                </Link>
              </>
            ) : null}
          </div>
        ) : null}
      </div>
      <div role="alert" className="pointer-events-none fixed bottom-8 left-1/2 z-[60] -translate-x-1/2 no-print">
        {toast && error ? (
          <div
            key={toast.id}
            className={clsx("flex max-w-[90vw] animate-toast-in items-center gap-2 rounded-xl bg-critical-strong px-5 py-3 text-[14px] font-bold text-white shadow-toast")}
            data-toast="error"
          >
            <span aria-hidden="true" className="flex h-5 w-5 items-center justify-center rounded-circle bg-white/20 text-[12px]">
              !
            </span>
            {toast.message}
          </div>
        ) : null}
      </div>
    </>
  );
}
