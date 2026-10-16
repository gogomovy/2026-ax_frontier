"use client";

import { useCallback, useId, useRef, useState, useSyncExternalStore } from "react";
import clsx from "clsx";
import { IconCheck2, IconChevronDown } from "@/components/ui/icons";
import { useDismiss } from "@/lib/useDismiss";
import type { DomainCardInfo } from "@/lib/types";

/**
 * 선택한 사업부문 — 1 · 2 · 3단계 모든 화면에서 유지한다 (가이드 G05 "선택한 부문은 모든 단계에서 유지").
 * 브라우저에 기억해 두고, 기억한 부문이 없거나 사라졌으면 첫 번째 활성 부문을 쓴다.
 */
const SECTOR_KEY = "nhdip.sector";
const SECTOR_EVENT = "nhdip:sector";

function subscribe(onChange: () => void) {
  window.addEventListener("storage", onChange);
  window.addEventListener(SECTOR_EVENT, onChange);
  return () => {
    window.removeEventListener("storage", onChange);
    window.removeEventListener(SECTOR_EVENT, onChange);
  };
}
const read = () => {
  try {
    return window.localStorage.getItem(SECTOR_KEY);
  } catch {
    return null;
  }
};
const readServer = () => null;

export function useSector(domains: DomainCardInfo[]) {
  const stored = useSyncExternalStore(subscribe, read, readServer);
  const fallback = domains.find((d) => d.status === "active")?.domainCode ?? domains[0]?.domainCode ?? "";
  const code = domains.some((d) => d.domainCode === stored) ? (stored as string) : fallback;
  const select = useCallback((next: string) => {
    try {
      window.localStorage.setItem(SECTOR_KEY, next);
    } catch {
      return;
    }
    window.dispatchEvent(new Event(SECTOR_EVENT));
  }, []);
  return { code, domain: domains.find((d) => d.domainCode === code) ?? null, select };
}

/**
 * 페이지 제목 — "여신 ⌄ 데이터 분석". 부문 이름이 보라색 칩이고, 누르면 부문 목록이 열린다.
 * 메뉴에는 부문 이름과 레드닷(미확인 이슈)만 둔다. 데이터는 화면에서 확인한다.
 */
export function SectorTitle({ domains, title, flagged }: { domains: DomainCardInfo[]; title: string; flagged?: Record<string, boolean> }) {
  const { code, domain, select } = useSector(domains);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const id = useId();
  const close = useCallback(() => setOpen(false), []);
  useDismiss(ref, open, close);

  return (
    <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
      <div ref={ref} className="relative">
        <button
          type="button"
          aria-haspopup="listbox"
          aria-expanded={open}
          aria-controls={id}
          onClick={() => setOpen((v) => !v)}
          className={clsx(
            // 1 · 2 · 3단계 화면 제목 — 현황·목표 '경영 현황·목표'와 같은 22px
            "-ml-2 inline-flex items-center gap-1 rounded-lg px-2 py-0.5 text-[22px] font-bold leading-[1.25] text-primary transition-colors hover:bg-info-faint",
            open && "bg-info-soft",
          )}
        >
          {domain?.name ?? "부문"}
          <IconChevronDown size={14} className={clsx("transition-transform", open && "rotate-180")} />
        </button>
        {open ? (
          <ul
            id={id}
            role="listbox"
            aria-label="사업부문 선택"
            className="absolute left-0 top-[calc(100%+6px)] z-40 w-[200px] animate-pop-in rounded-xl border border-hairline-soft bg-canvas p-1.5 shadow-tooltip"
          >
            {domains.map((d) => {
              const on = d.domainCode === code;
              return (
                <li key={d.domainCode} role="option" aria-selected={on}>
                  <button
                    type="button"
                    onClick={() => {
                      select(d.domainCode);
                      close();
                    }}
                    className={clsx(
                      "flex h-9 w-full items-center gap-2 rounded-md px-2.5 text-left text-[14px] transition-colors hover:bg-surface-soft",
                      on ? "bg-info-faint font-bold text-primary" : "font-medium text-ink",
                    )}
                  >
                    <span className="flex w-4 justify-center">{on ? <IconCheck2 /> : null}</span>
                    <span className="flex-1">{d.name}</span>
                    {flagged?.[d.domainCode] && !on ? <span aria-label="확인하지 않은 이슈" className="h-[7px] w-[7px] rounded-circle bg-critical" /> : null}
                    {d.status !== "active" ? <span className="text-[12px] font-normal text-steel">준비 중</span> : null}
                  </button>
                </li>
              );
            })}
          </ul>
        ) : null}
      </div>
      <span className="text-[22px] font-bold leading-[1.25] text-ink-deep">{title}</span>
    </div>
  );
}
