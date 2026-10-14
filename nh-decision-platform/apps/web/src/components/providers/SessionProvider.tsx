"use client";

import { createContext, useContext, useMemo, type ReactNode } from "react";
import type { NavItem } from "@/lib/nav";
import { registerTerms } from "@/lib/terms";
import type { ActionPlan, CascadeNode, Goal, Term } from "@/lib/types";
import { EMPTY_CONFIG, type UiConfig } from "@/lib/uiConfig";

/** 서버 메뉴 (`GET /me/menu`) — 조직 상속 화면 권한 기준 */
export interface MenuItem {
  code: string;
  label: string;
  href: string;
  match: string[];
  step?: number | null;
  countKey?: NavItem["countKey"] | null;
}
export interface MenuSection {
  section: string;
  admin: boolean;
  flow: MenuItem[];
  reference: MenuItem[];
  /** 업무 영역 (Phase K · SCP-01) — 설정 ui.scopes 의 단위와 이름이 같은 묶음. 공통 · 관리자 묶음은 null */
  scope?: "hq" | "dept" | "branch" | null;
  orgCode?: string | null;
  orgName?: string;
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
  /** 데이터 관리자 — 업로드 자료 삭제 권한 (Phase J · DEL-01 · Q143) */
  dataAdmin?: boolean;
}
export interface MenuPayload {
  user: SessionUser;
  home: string;
  sections: MenuSection[];
  screens: string[];
  counts: Record<string, number>;
  asOf: string;
  batchLabel: string;
  /** 현재 버전 자료의 성격 (Phase E · NAV-05) — 없으면 알 수 없음(none) */
  dataOrigin?: "simulated" | "mixed" | "actual" | "none";
  /** 화면 설정 (Phase K · Q148) — 관리자 [화면 설정] */
  config?: UiConfig;
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

/** 화면 설정 — 없으면 빈 설정(판정 · 강조 없음) */
export function useUiConfig(): UiConfig {
  const { menu } = useSession();
  return menu?.config ?? EMPTY_CONFIG;
}

/** 로그인 사용자와 서버 메뉴 */
export function useApiSession() {
  const s = useSession();
  return { user: s.menu?.user ?? null, menu: s.menu };
}
