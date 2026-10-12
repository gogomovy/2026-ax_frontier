"use client";

import { createContext, useContext, useMemo, type ReactNode } from "react";
import { API_MODE } from "@/lib/config";
import { registerTerms } from "@/lib/terms";
import type { ActionPlan, CascadeNode, Goal, Term } from "@/lib/types";

/** 서버 메뉴 (`GET /me/menu`) — 조직 상속 화면 권한 기준 */
export interface MenuItem {
  code: string;
  label: string;
  href: string;
  match: string[];
  step?: number | null;
  countKey?: "goalProposals" | "analyses" | "proposedPlans" | "branchAnalyses" | null;
}
export interface MenuSection {
  section: string;
  admin: boolean;
  flow: MenuItem[];
  reference: MenuItem[];
}
export interface SessionUser {
  empNo: string;
  name: string;
  position?: string | null;
  role: "admin" | "user";
  org: { code: string; name: string };
  orgPath: { code: string; name: string; level: number; levelLabel: string }[];
  /** 부서 데이터 책임자 (UPL-04 · Q107) */
  dataSteward?: boolean;
  stewardScope?: { code: string; name: string } | null;
}
export interface MenuPayload {
  user: SessionUser;
  home: string;
  sections: MenuSection[];
  screens: string[];
  counts: Record<string, number>;
  asOf: string;
  batchLabel: string;
}
export interface Bootstrap {
  menu: MenuPayload | null;
  terms: Term[] | null;
  actionPlans: ActionPlan[] | null;
  cascade: CascadeNode[] | null;
  goals: Goal[] | null;
  generatedAt: string | null;
}

const EMPTY: Bootstrap = { menu: null, terms: null, actionPlans: null, cascade: null, goals: null, generatedAt: null };
const SessionContext = createContext<Bootstrap>(EMPTY);

export function SessionProvider({ value, children }: { value: Bootstrap | null; children: ReactNode }) {
  const v = value ?? EMPTY;
  // 용어 도움말은 렌더 중 동기 조회하므로 첫 렌더 전에 등록한다
  registerTerms(v.terms);
  const memo = useMemo(() => v, [v]);
  return <SessionContext.Provider value={memo}>{children}</SessionContext.Provider>;
}

export function useSession() {
  return useContext(SessionContext);
}

/** API 모드 여부와 로그인 여부 */
export function useApiSession() {
  const s = useSession();
  return { apiMode: API_MODE, user: s.menu?.user ?? null, menu: s.menu };
}
