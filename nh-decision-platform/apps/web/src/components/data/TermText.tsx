"use client";

import { useState } from "react";
import clsx from "clsx";
import { useUi } from "@/components/providers/UiProvider";
import { getTermSync } from "@/lib/terms";

/**
 * 용어 도움말 (요구사항 UX-04 / MDL-09).
 * hover · focus · click 3경로를 모두 지원한다(UX-10).
 */
export function TermText({
  code,
  label,
  className,
}: {
  code: string;
  label?: string;
  className?: string;
}) {
  const { openDrawer } = useUi();
  const [open, setOpen] = useState(false);
  const term = getTermSync(code);

  if (!term) return <span className={className}>{label ?? code}</span>;

  return (
    <span className="relative inline-block">
      <button
        type="button"
        onClick={() => openDrawer({ kind: "term", title: `용어 — ${term.prefLabel}`, term })}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        aria-label={`${label ?? term.prefLabel} — 용어 설명 보기`}
        className={clsx("term-marked font-medium text-ink", className)}
      >
        {label ?? term.prefLabel}
      </button>
      {open ? (
        <span
          role="tooltip"
          className="absolute left-0 top-[calc(100%+6px)] z-40 block w-[320px] rounded-lg border border-hairline-soft bg-canvas p-3 text-left shadow-pop"
        >
          <span className="flex items-center gap-1.5">
            <span className="text-[12px] font-bold text-ink-deep">{term.prefLabel}</span>
            <span className="rounded-pill bg-info-soft px-1.5 py-0.5 text-[9.5px] font-bold text-primary">
              용어집
            </span>
          </span>
          <span className="mt-1 block text-[11.5px] leading-snug text-charcoal">{term.definition}</span>
          {term.formula ? (
            <span className="mt-1.5 block font-mono text-[10.5px] leading-snug text-steel">{term.formula}</span>
          ) : null}
          <span className="mt-1.5 block text-[10.5px] text-stone">
            근거 · {term.src.title} p.{term.src.page}
          </span>
          <span className="mt-1 block text-[10.5px] font-bold text-primary">클릭 — 판단방법·예시·근거문서 보기</span>
        </span>
      ) : null}
    </span>
  );
}
