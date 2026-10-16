"use client";

import Link from "next/link";
import clsx from "clsx";
import { useEffect, type ReactNode } from "react";
import type { Severity } from "@/lib/types";
import { StatusDot, tabClass } from "./primitives";
import { useSeen } from "./useSeen";

export interface SeenTabItem {
  href: string;
  label: ReactNode;
  /** 점 색 — 없으면 점 없음 */
  dot?: Severity;
  /** '봤음' 키 · 내용 서명 (Phase K · DOT-01) — 서명이 바뀌면 다시 점 */
  seenKey?: string;
  signature?: string;
}

/**
 * 링크형 밑줄 탭 + 레드닷 '봤음' 상태 — 열려 있는 탭은 점이 없고 봤음으로 기록, 다른 탭은 확인하지 않은 새 내용이 있을 때만 점.
 * 원래의 PillTabLinks 와 같은 모양(가이드 G04).
 */
export function SeenTabLinks({ items, activeHref, label, after }: { items: SeenTabItem[]; activeHref: string; label: string; after?: ReactNode }) {
  const seen = useSeen();
  const { mark } = seen;
  const active = items.find((i) => i.href === activeHref);
  const activeKey = active?.seenKey;
  const activeSig = active?.signature;
  useEffect(() => {
    if (activeKey && activeSig) mark(activeKey, activeSig);
  }, [activeKey, activeSig, mark]);
  return (
    <nav aria-label={label} className="flex flex-wrap items-center gap-x-6 border-b border-hairline-soft">
      {items.map((item) => {
        const on = item.href === activeHref;
        const showDot = Boolean(item.dot) && !on && (item.seenKey ? seen.fresh(item.seenKey, item.signature) : true);
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={on ? "page" : undefined}
            onClick={() => (item.seenKey ? seen.mark(item.seenKey, item.signature) : undefined)}
            className={clsx(tabClass(on, "md"), "-mb-px")}
          >
            {item.label}
            {showDot && item.dot ? <StatusDot severity={item.dot} /> : null}
          </Link>
        );
      })}
      {after}
    </nav>
  );
}
