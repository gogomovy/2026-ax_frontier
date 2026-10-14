"use client";

import { useSyncExternalStore } from "react";

/*
 * 인쇄 중 여부 — 내보내기 단추가 인쇄 배치를 준비하는 동안, 또는 브라우저 인쇄(Ctrl+P)가 시작될 때 참.
 * 접어 둔 목록 · 해설처럼 "화면에서는 접혀 있어도 인쇄에는 다 나와야" 하는 곳이 읽는다 (EXP-02).
 */
let printing = false;
const subscribers = new Set<() => void>();

export function setPrinting(next: boolean): void {
  if (printing === next) return;
  printing = next;
  subscribers.forEach((f) => f());
}

function subscribe(cb: () => void): () => void {
  subscribers.add(cb);
  return () => {
    subscribers.delete(cb);
  };
}

let wired = false;
function wire(): void {
  if (wired || typeof window === "undefined") return;
  wired = true;
  // Ctrl+P · 브라우저 메뉴로 인쇄해도 접힌 곳이 펼쳐진다. 내보내기 단추가 준비하는 중이면 afterprint 에서 거기서 끈다
  window.addEventListener("beforeprint", () => setPrinting(true));
  window.addEventListener("afterprint", () => setPrinting(false));
}

export function usePrinting(): boolean {
  wire();
  return useSyncExternalStore(
    subscribe,
    () => printing,
    () => false,
  );
}
