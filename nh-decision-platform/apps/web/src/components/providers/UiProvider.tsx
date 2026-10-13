"use client";

import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";
import { ConfirmDialog, type ConfirmOptions, type ConfirmRequest } from "@/components/ui/Confirm";
import type { CalcTrace, Evidence, Figure, Term } from "@/lib/types";

/** 우측 Source Drawer 에 표시할 대상 */
export type DrawerPayload =
  | { kind: "evidence"; title: string; items: Evidence[]; selectedId?: string }
  | { kind: "calc"; title: string; figure: Figure; trace?: CalcTrace }
  | { kind: "term"; title: string; term: Term };

/** 알림 종류 (Phase E · INT-02) — 실패는 아이콘 · 색 · 읽기 방식(role=alert)이 다르다 */
export type ToastTone = "success" | "error" | "info";
export interface ToastState {
  message: string;
  tone: ToastTone;
  id: number;
}

interface UiContextValue {
  drawer: DrawerPayload | null;
  openDrawer: (payload: DrawerPayload) => void;
  closeDrawer: () => void;
  toast: ToastState | null;
  /** tone 을 비우면 '실패' 로 시작하는 문장은 실패 알림, 그 밖은 성공 알림 */
  showToast: (message: string, tone?: ToastTone) => void;
  /** 확인 대화상자 (INT-01) — 확인 true · 취소 false, input 이 있으면 입력 문자열 · 취소 null */
  confirm: (opts: ConfirmOptions) => Promise<boolean | string | null>;
}

const UiContext = createContext<UiContextValue | null>(null);

export function UiProvider({ children }: { children: ReactNode }) {
  const [drawer, setDrawer] = useState<DrawerPayload | null>(null);
  const [toast, setToast] = useState<ToastState | null>(null);
  const [req, setReq] = useState<ConfirmRequest | null>(null);
  const seq = useRef(0);
  const timer = useRef<number | undefined>(undefined);

  const openDrawer = useCallback((payload: DrawerPayload) => setDrawer(payload), []);
  const closeDrawer = useCallback(() => setDrawer(null), []);
  const showToast = useCallback((message: string, tone?: ToastTone) => {
    const t: ToastTone = tone ?? (/^\s*실패/.test(message) ? "error" : "success");
    seq.current += 1;
    setToast({ message, tone: t, id: seq.current });
    window.clearTimeout(timer.current);
    // 실패는 읽을 시간을 더 준다
    timer.current = window.setTimeout(() => setToast(null), t === "error" ? 6000 : 3200);
  }, []);
  const confirm = useCallback(
    (opts: ConfirmOptions) =>
      new Promise<boolean | string | null>((resolve) => {
        setReq({ ...opts, resolve });
      }),
    [],
  );

  const value = useMemo(
    () => ({ drawer, openDrawer, closeDrawer, toast, showToast, confirm }),
    [drawer, openDrawer, closeDrawer, toast, showToast, confirm],
  );

  return (
    <UiContext.Provider value={value}>
      {children}
      {req ? <ConfirmDialog key={req.title} req={req} onDone={() => setReq(null)} /> : null}
    </UiContext.Provider>
  );
}

export function useUi() {
  const ctx = useContext(UiContext);
  if (!ctx) throw new Error("useUi must be used within UiProvider");
  return ctx;
}

/** 확인 대화상자 — `if (await confirm({...})) …` */
export function useConfirm() {
  return useUi().confirm;
}
