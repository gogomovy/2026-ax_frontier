"use client";

import { usePathname } from "next/navigation";
import { useEffect, useMemo, useSyncExternalStore } from "react";
import { useGoalState } from "@/components/providers/GoalStateProvider";
import { usePlanState } from "@/components/providers/PlanStateProvider";
import { useSession, type MenuItem, type MenuPayload } from "@/components/providers/SessionProvider";
import { activeHref, matchLength, type NavItem } from "@/lib/nav";

/**
 * 셸 내비게이션 모델 — 어떤 업무 영역(종기부 · 사업부서 · 영업점)이 있고, 지금 어느 영역의 어떤 단계에 있는지,
 * 관리자 메뉴를 보여 줄지를 한 곳에서 계산한다. 헤더 · 모바일 메뉴 · 관리자 사이드바가 같은 값을 쓴다.
 * 영역과 메뉴는 서버 메뉴(`/me/menu`)의 화면 권한 그대로다 — 관리자는 모든 영역이 보인다(목데이터 없음 · Phase I).
 */

export type ScopeKind = "hq" | "dept" | "branch" | "other";
export type CountKey = NonNullable<NavItem["countKey"]>;

export interface Scope {
  /** 안정적인 식별자 — 같은 종류가 둘 이상이면 구역 이름이 붙는다 */
  id: string;
  kind: ScopeKind;
  /** 전환 컨트롤에 쓰는 짧은 이름 */
  label: string;
  /** 실제 조직 · 구역 이름 (예: 종합기획부) */
  orgName: string;
  home: string;
  flow: NavItem[];
  reference: NavItem[];
}

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
  user: NavUser | null;
  /** 서버 메뉴의 기준일 — 로그인 전에는 빈 문자열(화면은 '–') */
  asOf: string;
  generatedAt: string | null;
  dataOrigin: "simulated" | "mixed" | "actual" | "none";
}

const KIND_LABEL: Record<ScopeKind, string> = { hq: "종기부", dept: "사업부서", branch: "영업점", other: "" };
const KIND_ORDER: ScopeKind[] = ["hq", "dept", "branch", "other"];
const SCOPE_KEY = "nhdip.scope";
const SCOPE_EVENT = "nhdip:scope";

/** 화면 경로가 속한 영역 (주소만으로 알 수 있는 경우) */
export function kindOfPath(pathname: string): ScopeKind | null {
  if (pathname.startsWith("/hq") || pathname.startsWith("/domains")) return "hq";
  if (pathname.startsWith("/risk")) return "dept";
  if (pathname.startsWith("/branch")) return "branch";
  return null;
}

function kindOfHref(href: string): ScopeKind {
  return kindOfPath(href) ?? "other";
}

function toItem(i: MenuItem): NavItem {
  return {
    label: i.label,
    href: i.href,
    match: i.match.map((m) => m.replace(/^=/, "")),
    step: i.step ?? undefined,
    countKey: i.countKey ?? undefined,
    exact: i.match.some((m) => m.startsWith("=")),
  };
}

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

/** 사용자가 처리해야 할 건수 — 화면 메뉴와 알림이 같이 쓴다 */
function useCounts(): Record<CountKey, number> {
  const { proposalActions } = useGoalState();
  const { proposedPlans } = usePlanState();
  const { menu } = useSession();
  const c: Record<string, number> = menu?.counts ?? {};
  const proposals = c.proposalsTotal ?? 0;
  const analyses = c.analysesTotal ?? 0;
  const branchAnalyses = c.branchAnalysesTotal ?? 0;
  return {
    goalProposals: Math.max(0, proposals - Object.keys(proposalActions).length),
    analyses,
    proposedPlans: proposedPlans.length,
    branchAnalyses,
    // 관리자 처리 건수 — 서버가 관리자에게만 계산 (Phase E · NAV-02)
    adminTodo: c.adminTodo ?? 0,
    adminUsers: c.adminUsers ?? 0,
    adminUploads: c.adminUploads ?? 0,
    adminAnalyses: c.adminAnalyses ?? 0,
  };
}

function scopesFromMenu(menu: MenuPayload): Scope[] {
  const withFlow = menu.sections.filter((s) => !s.admin && s.flow.length > 0);
  const scopes = withFlow.map((s): Scope => {
    const flow = s.flow.map(toItem);
    const kind = kindOfHref(flow[0].href);
    return {
      id: kind === "other" ? `other:${s.section}` : kind,
      kind,
      label: kind === "other" ? s.section : KIND_LABEL[kind],
      orgName: s.section,
      home: flow[0].href,
      flow,
      reference: s.reference.map(toItem),
    };
  });
  return scopes.sort((a, b) => KIND_ORDER.indexOf(a.kind) - KIND_ORDER.indexOf(b.kind));
}

export function useNavModel(): NavModel {
  const pathname = usePathname() ?? "/";
  const { menu, generatedAt } = useSession();
  const counts = useCounts();
  const stored = useSyncExternalStore(subscribeScope, readScope, serverScope);

  const scopes = useMemo(() => (menu ? scopesFromMenu(menu) : []), [menu]);

  const fromPath = useMemo(() => {
    // 공통 화면(데이터베이스 등)은 어느 영역에나 있으므로, 그 영역 고유 주소의 화면만 영역 판정에 쓴다
    const own = (s: Scope) => [...s.flow, ...s.reference].filter((it) => s.kind === "other" || kindOfPath(it.href) === s.kind);
    const byItem = scopes.find((s) => own(s).some((it) => matchLength(it, pathname) > 0));
    if (byItem) return byItem;
    const kind = kindOfPath(pathname);
    return kind ? (scopes.find((s) => s.kind === kind) ?? null) : null;
  }, [scopes, pathname]);

  const fromPathId = fromPath?.id ?? null;
  useEffect(() => {
    if (fromPathId) rememberScope(fromPathId);
  }, [fromPathId]);

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
    user,
    asOf: menu?.asOf ?? "",
    generatedAt,
    dataOrigin: menu?.dataOrigin ?? "simulated",
  };
}

/** 현재 위치로 볼 수 있는 항목 하나 (가장 길게 일치하는 것) */
export function currentHref(items: NavItem[], pathname: string): string | null {
  return activeHref(items, pathname);
}
