import type { Persona } from "./types";

/**
 * 페르소나별 내비게이션 정의 (요구사항 UX-01).
 * 업무 흐름(3단계)과 참고 화면을 분리해 사이드바에 배치한다.
 */
export interface NavItem {
  label: string;
  href: string;
  /** 활성 판정용 경로 접두어 */
  match: string[];
  /** 업무 흐름 단계 번호 */
  step?: number;
  /** 사이드바에 건수를 표시할 대상 (admin* — 관리자 처리 건수 · Phase E NAV-02) */
  countKey?: "goalProposals" | "analyses" | "proposedPlans" | "branchAnalyses" | "adminTodo" | "adminUsers" | "adminUploads" | "adminAnalyses";
  /** 경로가 정확히 같을 때만 활성 (하위 경로와 겹치는 상위 화면) */
  exact?: boolean;
}

export interface PersonaConfig {
  code: Persona;
  org: string;
  user: string;
  role: string;
  home: string;
  flow: NavItem[];
  reference: NavItem[];
}

const KNOWLEDGE: NavItem = { label: "데이터베이스", href: "/knowledge", match: ["/knowledge"] };

export const PERSONAS: Record<Persona, PersonaConfig> = {
  P1: {
    code: "P1",
    org: "종합기획부",
    user: "이수정",
    role: "과장",
    home: "/hq/overview",
    flow: [
      { step: 1, label: "현황·목표", href: "/hq/overview", match: ["/hq/overview"] },
      { step: 2, label: "데이터 분석", href: "/hq/analysis", match: ["/hq/analysis"] },
      { step: 3, label: "경영목표 설정", href: "/hq/goals", match: ["/hq/goals"], countKey: "goalProposals" },
    ],
    reference: [
      { label: "사업부서 진행 사업", href: "/hq/initiatives", match: ["/hq/initiatives"] },
      { label: "총자산·수익성 기준", href: "/hq/capital", match: ["/hq/capital"] },
      KNOWLEDGE,
    ],
  },
  P2: {
    code: "P2",
    org: "신용리스크관리부",
    user: "박현우",
    role: "차장",
    home: "/risk",
    flow: [
      { step: 1, label: "현황", href: "/risk", match: ["/risk"] },
      {
        step: 2,
        label: "분석 결과",
        href: "/risk/analysis",
        match: ["/risk/analysis"],
        countKey: "analyses",
      },
      { step: 3, label: "수행방안", href: "/risk/guides", match: ["/risk/guides"], countKey: "proposedPlans" },
    ],
    reference: [KNOWLEDGE],
  },
  P3: {
    code: "P3",
    org: "수원영통지점",
    user: "최지훈",
    role: "대리",
    home: "/branch",
    flow: [
      { step: 1, label: "현황", href: "/branch", match: ["/branch"], exact: true },
      { step: 2, label: "분석 결과", href: "/branch/analysis", match: ["/branch/analysis"], countKey: "branchAnalyses" },
    ],
    reference: [{ label: "본부 전파 목표·가이드", href: "/branch/targets", match: ["/branch/targets"] }, KNOWLEDGE],
  },
};

/** 경로가 특정 페르소나 전용이면 그 페르소나를, 공용 화면이면 null 을 돌려준다 */
export function personaOfPath(pathname: string): Persona | null {
  if (pathname.startsWith("/risk")) return "P2";
  if (pathname.startsWith("/branch")) return "P3";
  if (pathname.startsWith("/hq") || pathname.startsWith("/domains")) return "P1";
  return null;
}

export function isActive(item: NavItem, pathname: string) {
  return matchLength(item, pathname) > 0;
}

/** 현재 주소와 일치하는 경로 접두어의 길이(가장 긴 것) — 0 이면 일치하지 않음 */
export function matchLength(item: NavItem, pathname: string): number {
  // `/risk` 는 하위 경로(/risk/analysis 등)와 겹치므로 정확히 일치할 때만 활성
  if (item.exact || item.href === "/risk") return pathname === item.match[0] || pathname === item.href ? Math.max(item.href.length, 1) : 0;
  return Math.max(0, ...item.match.filter((m) => pathname === m || pathname.startsWith(m)).map((m) => m.length));
}

/**
 * 사이드바 현재 위치 하나 (Phase E · NAV-03) — 여러 메뉴가 일치하면(예: /knowledge 와 /knowledge/upload) 가장 길게 일치하는 것.
 * 없으면 null. 같은 길이면 먼저 나온 메뉴.
 */
export function activeHref(items: NavItem[], pathname: string): string | null {
  let best: NavItem | null = null;
  let len = 0;
  for (const it of items) {
    const n = matchLength(it, pathname);
    if (n > len) {
      best = it;
      len = n;
    }
  }
  return best ? best.href : null;
}
