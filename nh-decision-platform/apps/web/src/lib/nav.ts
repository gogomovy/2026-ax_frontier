/**
 * 사이드바 메뉴 항목 (요구사항 UX-01).
 * 메뉴 구성은 서버 메뉴(`GET /me/menu` · 조직 상속 화면 권한)에서 오고, 여기서는 항목 모양과 활성 판정만 둔다.
 */
export interface NavItem {
  label: string;
  href: string;
  /** 활성 판정용 경로 접두어 */
  match: string[];
  /** 업무 흐름 단계 번호 */
  step?: number;
  /** 사이드바에 건수를 표시할 대상 (admin* — 관리자 처리 건수 · Phase E NAV-02) */
  countKey?: "goalProposals" | "analyses" | "proposedPlans" | "branchAnalyses" | "adminTodo" | "adminUsers" | "adminUploads" | "adminAnalyses" | "stewardTodo";
  /** 경로가 정확히 같을 때만 활성 (하위 경로와 겹치는 상위 화면) */
  exact?: boolean;
}

export function isActive(item: NavItem, pathname: string) {
  return matchLength(item, pathname) > 0;
}

/** 현재 주소와 일치하는 경로 접두어의 길이(가장 긴 것) — 0 이면 일치하지 않음 */
export function matchLength(item: NavItem, pathname: string): number {
  // 하위 경로와 겹치는 상위 화면은 서버 메뉴의 정확 일치 표시(`=`, exact)로 — 주소를 코드에 두지 않는다 (Phase K)
  if (item.exact) return pathname === item.match[0] || pathname === item.href ? Math.max(item.href.length, 1) : 0;
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
