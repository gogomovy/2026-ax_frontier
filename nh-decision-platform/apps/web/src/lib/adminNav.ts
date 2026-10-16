/** 관리자 메뉴 찾기 (Phase P · ADM2-03) — 이름(공백 · 대소문자 무시) 또는 묶음 이름이 맞는 항목만. 빈 묶음은 뺀다 */
export function filterAdminGroups<G extends { label: string; items: { label: string }[] }>(groups: G[], query: string): G[] {
  const norm = (s: string) => s.replace(/\s+/g, "").toLowerCase();
  const q = norm(query);
  if (!q) return groups;
  return groups
    .map((g) => (norm(g.label).includes(q) ? g : { ...g, items: g.items.filter((i) => norm(i.label).includes(q)) }))
    .filter((g) => g.items.length > 0);
}
