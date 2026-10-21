/** 조직 검색 (/admin/orgs/lookup) — 검색형 조직 선택 상자 · 조직 화면이 같이 쓰는 형식과 도우미 */
export interface OrgOption {
  code: string;
  name: string;
  unitType: string | null;
  unitLabel: string;
  level: number;
  active: boolean;
  /** 최상위 → 바로 위 조직 이름 */
  path: string[];
}

export function orgLookupPath(p: { q?: string; types?: string[]; exclude?: string; codes?: string[]; inactive?: boolean; limit?: number }): string {
  const s = new URLSearchParams();
  if (p.q) s.set("q", p.q);
  if (p.types?.length) s.set("types", p.types.join(","));
  if (p.exclude) s.set("exclude", p.exclude);
  if (p.codes?.length) s.set("codes", p.codes.join(","));
  if (p.inactive) s.set("inactive", "true");
  if (p.limit) s.set("limit", String(Math.min(100, Math.max(1, p.limit))));
  const qs = s.toString();
  return `/admin/orgs/lookup${qs ? `?${qs}` : ""}`;
}

/** 목록 둘째 줄 — 상위 조직 경로 (예: '여신본부 > 기업여신부') */
export function orgOptionText(o: Pick<OrgOption, "path">): string {
  return o.path.join(" > ");
}

/** 조직 트리 — 상위 → 하위 목록을 한 번에(O(N)) 만들고, 트리 순서 · 하위 수 · 검색 일치를 계산한다 (조직 화면) */
export interface TreeOrg {
  code: string;
  name: string;
  parent: string | null;
  sort: number;
}

export function buildOrgTree<T extends TreeOrg>(orgs: T[]) {
  const by = new Map(orgs.map((o) => [o.code, o]));
  const kids = new Map<string | null, T[]>();
  for (const o of orgs) {
    const p = o.parent && o.parent !== o.code && by.has(o.parent) ? o.parent : null;
    const list = kids.get(p);
    if (list) list.push(o);
    else kids.set(p, [o]);
  }
  for (const list of kids.values()) list.sort((a, b) => a.sort - b.sort || a.code.localeCompare(b.code));
  /** 하위 조직 전체 수 (자기 제외) */
  const below = new Map<string, number>();
  const order: T[] = [];
  const seen = new Set<string>();
  const visit = (root: T) => {
    // 깊은 트리에서도 호출 스택이 넘치지 않게 반복으로
    const stack: { o: T; done: boolean }[] = [{ o: root, done: false }];
    while (stack.length) {
      const top = stack.pop()!;
      if (top.done) {
        below.set(top.o.code, (kids.get(top.o.code) ?? []).reduce((n, k) => n + 1 + (below.get(k.code) ?? 0), 0));
        continue;
      }
      if (seen.has(top.o.code)) continue;
      seen.add(top.o.code);
      order.push(top.o);
      stack.push({ o: top.o, done: true });
      const ch = kids.get(top.o.code) ?? [];
      for (let i = ch.length - 1; i >= 0; i--) if (!seen.has(ch[i].code)) stack.push({ o: ch[i], done: false });
    }
  };
  (kids.get(null) ?? []).forEach(visit);
  orgs.forEach((o) => !seen.has(o.code) && visit(o)); // 순환 고리 안에만 있는 조직
  const path = (code: string): T[] => {
    const out: T[] = [];
    const got = new Set<string>();
    let cur = by.get(code);
    while (cur && !got.has(cur.code)) {
      out.unshift(cur);
      got.add(cur.code);
      cur = cur.parent ? by.get(cur.parent) : undefined;
    }
    return out;
  };
  return { by, kids, order, below, path };
}

/** 이름 · 코드 · 상위 조직 이름에 낱말이 모두 들어 있는지 (조직 화면 검색) */
export function orgMatches(o: { name: string; code: string }, above: string[], q: string): boolean {
  const words = q.toLocaleLowerCase("ko-KR").split(/\s+/).filter(Boolean);
  if (!words.length) return true;
  const own = `${o.name} ${o.code}`.toLocaleLowerCase("ko-KR");
  const up = above.join(" ").toLocaleLowerCase("ko-KR");
  return words.every((w) => own.includes(w) || up.includes(w));
}
