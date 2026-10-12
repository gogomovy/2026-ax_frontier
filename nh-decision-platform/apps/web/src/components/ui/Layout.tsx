"use client";

import clsx from "clsx";
import Link from "next/link";
import { useId, useState, type ReactNode } from "react";
import { IconChevron } from "./primitives";

/* 화면 구성 공통 요소 (C.1 · UX-20) — 위치 표시 · 빈 상태 · 고급(접기) · 항목 목록 · 안내 */

export interface Crumb {
  label: string;
  href?: string;
}

/** 위치 표시 — 마지막 항목이 현재 화면 */
export function Breadcrumbs({ items, className }: { items: Crumb[]; className?: string }) {
  if (!items.length) return null;
  return (
    <nav aria-label="현재 위치" className={clsx("text-[12px]", className)}>
      <ol className="flex flex-wrap items-center gap-1 text-steel">
        {items.map((c, i) => {
          const last = i === items.length - 1;
          return (
            <li key={`${c.label}-${i}`} className="flex items-center gap-1">
              {c.href && !last ? (
                <Link href={c.href} className="font-bold text-steel underline-offset-2 hover:underline">
                  {c.label}
                </Link>
              ) : (
                <span aria-current={last ? "page" : undefined} className={clsx(last ? "font-bold text-primary" : "font-bold")}>
                  {c.label}
                </span>
              )}
              {!last ? <IconChevron className="h-3 w-3 text-stone" /> : null}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

/** 빈 상태 — 무엇이 없는지 · 왜 · 다음에 할 일 */
export function EmptyState({ title, description, action, icon, compact }: { title: string; description?: ReactNode; action?: ReactNode; icon?: ReactNode; compact?: boolean }) {
  return (
    <div className={clsx("flex flex-col items-center gap-1.5 rounded-2xl border border-dashed border-hairline text-center", compact ? "px-lg py-xl" : "px-xl py-xxl")}>
      {icon ? <span className="mb-1 flex h-10 w-10 items-center justify-center rounded-circle bg-surface-soft text-steel">{icon}</span> : null}
      <p className="text-[13.5px] font-bold text-charcoal">{title}</p>
      {description ? <p className="max-w-[460px] text-[12.5px] leading-relaxed text-steel">{description}</p> : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}

/** 고급(접기) — 원시 JSON · 세부 설정처럼 평소에는 숨겨 두는 내용. 펼침 상태는 aria-expanded 로 알린다 */
export function Advanced({ label = "고급 — 원본 보기", children, defaultOpen = false, hint }: { label?: ReactNode; children: ReactNode; defaultOpen?: boolean; hint?: ReactNode }) {
  const [open, setOpen] = useState(defaultOpen);
  const id = useId();
  return (
    <div className="rounded-xl border border-hairline-soft">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-md py-2 text-left text-[12px] font-bold text-steel"
      >
        <IconChevron className={clsx("transition-transform", open && "rotate-90")} />
        <span className="flex-1">{label}</span>
        {hint ? <span className="font-medium text-stone">{hint}</span> : null}
      </button>
      {open ? (
        <div id={id} className="border-t border-hairline-soft p-md">
          {children}
        </div>
      ) : null}
    </div>
  );
}

/** 항목 목록(정의 목록) — 라벨 : 값. 설정 · 규칙 요약에 쓴다 */
export function KeyValueList({ items, columns = 2, dense }: { items: { label: ReactNode; value: ReactNode; hint?: ReactNode }[]; columns?: 1 | 2 | 3; dense?: boolean }) {
  return (
    <dl className={clsx("grid grid-cols-1 gap-x-xl", dense ? "gap-y-1" : "gap-y-2", columns >= 2 && "md:grid-cols-2", columns === 3 && "xl:grid-cols-3")}>
      {items.map((it, i) => (
        <div key={i} className="flex min-w-0 gap-2 border-b border-hairline-soft pb-1.5">
          <dt className="w-[140px] shrink-0 text-[12px] text-steel">{it.label}</dt>
          <dd className="min-w-0 flex-1 break-words text-[12.5px] font-medium text-ink">
            {it.value}
            {it.hint ? <span className="ml-1.5 text-[11.5px] font-normal text-stone">{it.hint}</span> : null}
          </dd>
        </div>
      ))}
    </dl>
  );
}

/** 안내 상자 — 정보 · 주의 · 위험 · 완료 (색 + 글로 함께 알린다) */
export function Notice({ tone = "info", title, children }: { tone?: "info" | "attention" | "critical" | "success"; title?: ReactNode; children?: ReactNode }) {
  return (
    <div
      role={tone === "critical" ? "alert" : undefined}
      className={clsx(
        "rounded-xl px-base py-3 text-[12.5px] leading-relaxed text-charcoal",
        tone === "info" && "bg-info-faint",
        tone === "attention" && "bg-attention-faint",
        tone === "critical" && "bg-critical-faint",
        tone === "success" && "bg-success-faint",
      )}
    >
      {title ? <p className={clsx("mb-0.5 font-bold", tone === "critical" ? "text-critical" : tone === "attention" ? "text-attention" : tone === "success" ? "text-success" : "text-primary")}>{title}</p> : null}
      {children}
    </div>
  );
}
