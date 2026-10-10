"use client";

import { useUi } from "@/components/providers/UiProvider";
import { IconCheck } from "@/components/ui/primitives";

export function Toast() {
  const { toast } = useUi();
  if (!toast) return null;
  return (
    <div
      role="status"
      aria-live="polite"
      className="pointer-events-none fixed bottom-8 left-1/2 z-[60] -translate-x-1/2 no-print"
    >
      <div className="flex items-center gap-2 rounded-pill bg-ink-deep px-5 py-3 text-[13px] font-bold text-white shadow-pop">
        <IconCheck />
        {toast}
      </div>
    </div>
  );
}
