/** 관리자 [사용자] 목록 조회 — 서버 페이지 · 검색 (/admin/users) */
export type UserTab = "pending" | "active" | "locked" | "disabled" | "all";

export function usersPath(p: { status: UserTab; q?: string; org?: string | null; page?: number; size?: number }): string {
  const s = new URLSearchParams({ status: p.status });
  if (p.q) s.set("q", p.q);
  if (p.org) s.set("org", p.org);
  if (p.page && p.page > 1) s.set("page", String(p.page));
  if (p.size) s.set("size", String(p.size));
  return `/admin/users?${s.toString()}`;
}

/** 지금 쪽에 보이는 순번(1부터) · 전체 쪽 수 */
export function pageRange(page: number, size: number, total: number): { from: number; to: number; pages: number } {
  const pages = Math.max(1, Math.ceil(total / Math.max(1, size)));
  const p = Math.min(Math.max(1, page), pages);
  return total ? { from: (p - 1) * size + 1, to: Math.min(total, p * size), pages } : { from: 0, to: 0, pages };
}
