"use client";

import { useLayoutEffect, useRef, useState, type ReactNode, type RefObject } from "react";
import { createPortal } from "react-dom";

/**
 * 떠 있는 도움말 상자 — 카드 · 표 · 띠처럼 넘침을 자르는(overflow-hidden) 상자 안에서도 잘리지 않게
 * 문서 맨 위(body)에 그리고, 화면 좌표(fixed)로 기준 요소 옆에 붙인다.
 * - 아래 공간이 모자라면 위로 뒤집고, 좌우는 화면 안(여백 8px)으로 밀어 넣는다.
 * - 스크롤 · 창 크기 변경 때 위치를 다시 잰다.
 */
export function FloatingTip({
  anchor,
  open,
  width,
  align = "start",
  className,
  children,
}: {
  anchor: RefObject<HTMLElement | null>;
  open: boolean;
  width: number;
  /** start = 기준 왼쪽 끝에 맞춤 · center = 가운데 맞춤 */
  align?: "start" | "center";
  className?: string;
  children: ReactNode;
}) {
  const box = useRef<HTMLSpanElement>(null);
  const [pos, setPos] = useState<{ left: number; top: number } | null>(null);

  useLayoutEffect(() => {
    if (!open) return;
    const place = () => {
      const a = anchor.current?.getBoundingClientRect();
      if (!a) return;
      const h = box.current?.offsetHeight ?? 0;
      const gap = 6;
      const margin = 8;
      const vw = window.innerWidth;
      const vh = window.innerHeight;
      let left = align === "center" ? a.left + a.width / 2 - width / 2 : a.left;
      left = Math.min(Math.max(margin, left), vw - width - margin);
      const below = a.bottom + gap;
      const top = below + h > vh - margin && a.top - gap - h > margin ? a.top - gap - h : below;
      setPos({ left, top });
    };
    place();
    // 높이를 잰 뒤 한 번 더 — 처음엔 상자 높이를 몰라 뒤집기 판단이 늦다
    const raf = requestAnimationFrame(place);
    window.addEventListener("scroll", place, true);
    window.addEventListener("resize", place);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("scroll", place, true);
      window.removeEventListener("resize", place);
    };
  }, [open, anchor, width, align]);

  if (!open || typeof document === "undefined") return null;
  return createPortal(
    <span
      ref={box}
      role="tooltip"
      className={className}
      style={{ position: "fixed", zIndex: 70, width, left: pos?.left ?? -9999, top: pos?.top ?? -9999, pointerEvents: "none" }}
    >
      {children}
    </span>,
    document.body,
  );
}
