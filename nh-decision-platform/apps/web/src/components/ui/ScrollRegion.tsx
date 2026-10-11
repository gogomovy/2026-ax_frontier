"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";

/**
 * 가로로 넘칠 수 있는 영역 (B.34 · WCAG 2.1.1) — 내용이 넘칠 때만 키보드 포커스를 받아 화살표로 스크롤할 수 있다.
 * 넘치지 않으면 탭 정지를 만들지 않는다.
 */
export function ScrollRegion({ label, className, children }: { label?: string; className?: string; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const [over, setOver] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const check = () => setOver(el.scrollWidth > el.clientWidth + 1);
    check();
    const ro = new ResizeObserver(check);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return (
    <div
      ref={ref}
      className={className ?? "overflow-x-auto"}
      {...(over ? { tabIndex: 0, role: "region", "aria-label": label ? `${label} — 좌우로 스크롤` : "표 — 좌우로 스크롤" } : {})}
    >
      {children}
    </div>
  );
}
