"use client";

import { usePathname } from "next/navigation";
import { useEffect, useMemo, useSyncExternalStore } from "react";
import { useGoalState } from "@/components/providers/GoalStateProvider";
import { usePlanState } from "@/components/providers/PlanStateProvider";
import { useSession } from "@/components/providers/SessionProvider";
import { officeFromSearch } from "@/lib/branchOffice";
import { activeHref, matchLength, type NavItem } from "@/lib/nav";
import { focusUnit, officeHrefOf, scopeOfPath, scopesFromMenu, toItem, type Scope, type ScopeKind, type ScopeUnit } from "@/lib/scopeModel";
import { isFresh, markSeen, readSeen, subscribeSeen } from "@/lib/seen";
import { EMPTY_CONFIG, type UiConfig } from "@/lib/uiConfig";

/**
 * 셸 내비게이션 모델 — 어떤 업무 영역(종기부 · 사업부서 · 영업점)이 있고, 지금 어느 영역의 어느 단위(부서 · 지점)의 어떤 단계에 있는지,
 * 관리자 메뉴를 보여 줄지를 한 곳에서 계산한다. 헤더 · 모바일 메뉴 · 관리자 사이드바가 같은 값을 쓴다.
 * 영역 · 단위 묶기는 lib/scopeModel(순수 함수 · Phase K · SCP-01), 여기는 주소 · 저장소 · 건수를 잇는다.
 */

export type { Scope, ScopeKind, ScopeUnit };
export { officeHrefOf };
export type CountKey = NonNullable<NavItem["countKey"]>;

export interface AdminGroup {
  label: string;
  items: NavItem[];
}

export interface NavUser {
  name: string;
  position: string;
  orgName: string;
  orgPath: string;
  empNo: string | null;
  isAdmin: boolean;
}

export interface NavModel {
  pathname: string;
  /** 로그인 정보가 없으면 셸 없이 그린다 */
  bare: boolean;
  scopes: Scope[];
  current: Scope | null;
  /** 지금 관리자 영역(/admin)을 보고 있는가 */
  inAdmin: boolean;
  /** 관리자 메뉴를 보여 줄 수 있는가 (관리자 역할 + 관리 화면 권한) */
  adminAvailable: boolean;
  adminGroups: AdminGroup[];
  /** 영역과 무관한 공통 참고 화면 (데이터베이스 제외) */
  sharedReference: NavItem[];
  knowledgeHref: string | null;
  counts: Record<CountKey, number>;
  /** 건수 키 → 그 건수를 처리하는 화면 주소 (알림 목록) */
  hrefByCount: Record<string, string>;
  user: NavUser | null;
  /** 서버 메뉴의 기준일 — 로그인 전에는 빈 문자열(화면은 '–') */
  asOf: string;
  generatedAt: string | null;
  /** 자료 성격 — 알 수 없으면 none(표시하지 않음 · Phase K · HC-05) */
  dataOrigin: "simulated" | "mixed" | "actual" | "none";
  config: UiConfig;
}

const SCOPE_KEY = "nhdip.scope";
const SCOPE_EVENT = "nhdip:scope";
/** 정보성 건수 — 봤으면 숨긴다(레드닷과 같은 규칙 · Phase K · DOT-01). 처리할 일 건수(제안 · 승인)는 그대로 */
const INFO_COUNTS: CountKey[] = ["analyses", "branchAnalyses"];

/** 마지막으로 본 영역 — 영역이 정해지지 않는 공통 화면(데이터베이스 등)에서 유지한다 */
function subscribeScope(onChange: () => void) {
  window.addEventListener("storage", onChange);
  window.addEventListener(SCOPE_EVENT, onChange);
  return () => {
    window.removeEventListener("storage", onChange);
    window.removeEventListener(SCOPE_EVENT, onChange);
  };
}
function readScope(): string | null {
  try {
    return window.localStorage.getItem(SCOPE_KEY);
  } catch {
    return null;
  }
}
const serverScope = () => null;

export function rememberScope(id: string) {
  try {
    if (window.localStorage.getItem(SCOPE_KEY) === id) return;
    window.localStorage.setItem(SCOPE_KEY, id);
  } catch {
    return;
  }
  window.dispatchEvent(new Event(SCOPE_EVENT));
}

/** 주소의 ?office= — 영업점 지점 선택은 전체 이동(a href)이라 popstate · 첫 렌더에서 읽으면 된다 */
function subscribeLocation(onChange: () => void) {
  window.addEventListener("popstate", onChange);
  return () => window.removeEventListener("popstate", onChange);
}
const readSearch = () => window.location.search;
const emptySearch = () => "";

/** 정보성 건수의 '봤음' 키 · 서명 — 건수 + 기준일 */
export const countSeenKey = (key: string) => `count.${key}`;
export const countSignature = (n: number, asOf: string) => (n > 0 ? `${asOf}|${n}` : "");

/** 사용자가 처리해야 할 건수 — 화면 메뉴와 알림이 같이 쓴다 */
function useCounts(): Record<CountKey, number> {
  const { proposalActions } = useGoalState();
  const { proposedPlans } = usePlanState();
  const { menu } = useSession();
  const emp = menu?.user.empNo ?? null;
  const seen = useSyncExternalStore(subscribeSeen, () => readSeen(emp), () => null);
  const c: Record<string, number> = menu?.counts ?? {};
  const asOf = menu?.asOf ?? "";
  const info = (key: CountKey) => {
    const n = c[`${key}Total`] ?? 0;
    return isFresh(seen, countSeenKey(key), countSignature(n, asOf)) ? n : 0;
  };
  return {
    goalProposals: Math.max(0, (c.proposalsTotal ?? 0) - Object.keys(proposalActions).length),
    analyses: info("analyses"),
    proposedPlans: proposedPlans.length,
    branchAnalyses: info("branchAnalyses"),
    // 관리자 처리 건수 — 서버가 관리자에게만 계산 (Phase E · NAV-02)
    adminTodo: c.adminTodo ?? 0,
    adminUsers: c.adminUsers ?? 0,
    adminUploads: c.adminUploads ?? 0,
    adminAnalyses: c.adminAnalyses ?? 0,
    // 데이터 책임자 승인함(에이전트 제안 · 부서 분석 요청) — 서버가 책임자 · 관리자에게만 계산 (§40 STW)
    stewardTodo: c.stewardTodo ?? 0,
  };
}

export function useNavModel(): NavModel {
  const pathname = usePathname() ?? "/";
  const { menu, generatedAt } = useSession();
  const counts = useCounts();
  const stored = useSyncExternalStore(subscribeScope, readScope, serverScope);
  const search = useSyncExternalStore(subscribeLocation, readSearch, emptySearch);
  const office = officeFromSearch(search);

  const scopes = useMemo(() => (menu ? scopesFromMenu(menu, office) : []).map((s) => focusUnit(s, pathname)), [menu, office, pathname]);
  const fromPath = useMemo(() => scopeOfPath(scopes, pathname), [scopes, pathname]);

  const fromPathId = fromPath?.id ?? null;
  useEffect(() => {
    if (fromPathId) rememberScope(fromPathId);
  }, [fromPathId]);

  // 정보성 건수(분석 결과)는 그 화면을 열면 봤음 — 건수 · 기준일이 바뀌면 다시 보인다 (DOT-01)
  useEffect(() => {
    if (!menu) return;
    for (const s of menu.sections)
      for (const i of [...s.flow, ...s.reference]) {
        const key = i.countKey as CountKey | null | undefined;
        if (!key || !INFO_COUNTS.includes(key) || matchLength(toItem(i), pathname) <= 0) continue;
        markSeen(menu.user.empNo, countSeenKey(key), countSignature(menu.counts[`${key}Total`] ?? 0, menu.asOf ?? ""));
      }
  }, [menu, pathname]);

  const current = fromPath ?? scopes.find((s) => s.id === stored) ?? scopes[0] ?? null;

  const adminGroups = useMemo<AdminGroup[]>(() => {
    if (!menu) return [];
    return menu.sections
      .filter((s) => s.admin)
      .map((s) => ({ label: s.section, items: [...s.flow, ...s.reference].map(toItem) }))
      .filter((g) => g.items.length > 0);
  }, [menu]);

  const sharedReference = useMemo<NavItem[]>(() => {
    if (!menu) return [];
    return menu.sections.filter((s) => !s.admin && s.flow.length === 0).flatMap((s) => s.reference.map(toItem));
  }, [menu]);

  const hrefByCount = useMemo<Record<string, string>>(() => {
    const out: Record<string, string> = {};
    for (const s of menu?.sections ?? []) for (const i of [...s.flow, ...s.reference]) if (i.countKey && !out[i.countKey]) out[i.countKey] = i.href;
    return out;
  }, [menu]);

  const hasKnowledge = [...sharedReference, ...(current?.reference ?? [])].some((i) => i.href === "/knowledge");
  const user = useMemo<NavUser | null>(() => {
    const u = menu?.user;
    if (!u) return null;
    return {
      name: u.name,
      position: u.position ?? "",
      orgName: u.org.name,
      orgPath: u.orgPath.map((o) => o.name).join(" > "),
      empNo: u.empNo,
      isAdmin: u.role === "admin",
    };
  }, [menu]);

  const inAdmin = pathname === "/admin" || pathname.startsWith("/admin/");
  const adminAvailable = Boolean(menu) && Boolean(user?.isAdmin) && adminGroups.length > 0;

  return {
    pathname,
    bare: !menu,
    scopes,
    current,
    inAdmin,
    adminAvailable,
    adminGroups,
    sharedReference,
    knowledgeHref: hasKnowledge ? "/knowledge" : null,
    counts,
    hrefByCount,
    user,
    asOf: menu?.asOf ?? "",
    generatedAt,
    dataOrigin: menu?.dataOrigin ?? "none",
    config: menu?.config ?? EMPTY_CONFIG,
  };
}

/** 현재 위치로 볼 수 있는 항목 하나 (가장 길게 일치하는 것) */
export function currentHref(items: NavItem[], pathname: string): string | null {
  return activeHref(items, pathname);
}
