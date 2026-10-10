"use client";

import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import type { CalcTrace, Evidence, Figure, Term } from "@/lib/types";

/** 우측 Source Drawer 에 표시할 대상 */
export type DrawerPayload =
  | { kind: "evidence"; title: string; items: Evidence[]; selectedId?: string }
  | { kind: "calc"; title: string; figure: Figure; trace?: CalcTrace }
  | { kind: "term"; title: string; term: Term };

interface UiContextValue {
  drawer: DrawerPayload | null;
  openDrawer: (payload: DrawerPayload) => void;
  closeDrawer: () => void;
  toast: string | null;
  showToast: (message: string) => void;
}

const UiContext = createContext<UiContextValue | null>(null);

export function UiProvider({ children }: { children: ReactNode }) {
  const [drawer, setDrawer] = useState<DrawerPayload | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  const openDrawer = useCallback((payload: DrawerPayload) => setDrawer(payload), []);
  const closeDrawer = useCallback(() => setDrawer(null), []);
  const showToast = useCallback((message: string) => {
    setToast(message);
    window.setTimeout(() => setToast(null), 3200);
  }, []);

  const value = useMemo(
    () => ({ drawer, openDrawer, closeDrawer, toast, showToast }),
    [drawer, openDrawer, closeDrawer, toast, showToast],
  );

  return <UiContext.Provider value={value}>{children}</UiContext.Provider>;
}

export function useUi() {
  const ctx = useContext(UiContext);
  if (!ctx) throw new Error("useUi must be used within UiProvider");
  return ctx;
}
