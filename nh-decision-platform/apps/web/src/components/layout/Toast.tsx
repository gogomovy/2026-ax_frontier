"use client";

import clsx from "clsx";
import { useUi } from "@/components/providers/UiProvider";
import { IconCheck } from "@/components/ui/primitives";

/** 알림 (Phase E · INT-02) — 성공 · 안내는 status(polite), 실패는 alert(바로 읽음) · 다른 색 · 다른 아이콘 */
export function Toast() {
  const { toast } = useUi();
  const error = toast?.tone === "error";
  return (
    <>
      <div role="status" aria-live="polite" className="pointer-events-none fixed bottom-8 left-1/2 z-[60] -translate-x-1/2 no-print">
        {toast && !error ? (
          <div key={toast.id} className="flex items-center gap-2 rounded-pill bg-ink-deep px-5 py-3 text-[13px] font-bold text-white shadow-pop" data-toast="success">
            {toast.tone === "info" ? <span aria-hidden="true">ⓘ</span> : <IconCheck />}
            {toast.message}
          </div>
        ) : null}
      </div>
      <div role="alert" className="pointer-events-none fixed bottom-8 left-1/2 z-[60] -translate-x-1/2 no-print">
        {toast && error ? (
          <div key={toast.id} className={clsx("flex max-w-[90vw] items-center gap-2 rounded-pill bg-critical-strong px-5 py-3 text-[13px] font-bold text-white shadow-pop")} data-toast="error">
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
