"use client";

import { useEffect, type RefObject } from "react";

/** 대화상자 안에서 Tab 으로 이동할 수 있는 요소 */
const FOCUSABLE =
  'a[href], area[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), iframe, [tabindex]:not([tabindex="-1"]), [contenteditable="true"]';

/**
 * 포커스 순환 위치 — 현재 위치(index, 없으면 -1)에서 Tab(앞으로) · Shift+Tab(뒤로) 이동할 다음 위치.
 * 처음/끝에서 반대쪽 끝으로 돌아간다. 요소가 없으면 -1.
 */
export function nextFocusIndex(index: number, count: number, backward: boolean): number {
  if (count <= 0) return -1;
  if (index < 0) return backward ? count - 1 : 0;
  return backward ? (index - 1 + count) % count : (index + 1) % count;
}

/**
 * 모달 포커스 가두기 (B.33) — 열려 있는 동안 Tab · Shift+Tab 이 대화상자 밖으로 나가지 않는다.
 * 열릴 때 대화상자로 포커스를 옮기고, 닫히면 열기 전 요소로 되돌린다.
 */
export function useFocusTrap(ref: RefObject<HTMLElement | null>, active: boolean, opts: { autoFocus?: boolean; restore?: boolean } = {}) {
  const { autoFocus = true, restore = true } = opts;
  useEffect(() => {
    if (!active) return;
    const prev = document.activeElement as HTMLElement | null;
    const t = autoFocus ? window.setTimeout(() => ref.current?.focus(), 10) : undefined;
    const onKey = (e: KeyboardEvent) => {
      const root = ref.current;
      if (e.key !== "Tab" || !root) return;
      const items = Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE)).filter((el) => el.offsetParent !== null || el === document.activeElement);
      if (!items.length) {
        e.preventDefault();
        root.focus();
        return;
      }
      const cur = items.indexOf(document.activeElement as HTMLElement);
      const inside = root.contains(document.activeElement);
      // 대화상자 안에서 처음 · 끝이 아니면 브라우저 기본 이동을 그대로 쓴다
      if (inside && cur >= 0 && !(e.shiftKey ? cur === 0 : cur === items.length - 1)) return;
      e.preventDefault();
      items[nextFocusIndex(inside ? cur : -1, items.length, e.shiftKey)]?.focus();
    };
    document.addEventListener("keydown", onKey, true);
    return () => {
      if (t !== undefined) window.clearTimeout(t);
      document.removeEventListener("keydown", onKey, true);
      if (restore) prev?.focus?.();
    };
  }, [ref, active, autoFocus, restore]);
}
