/** 조직 경로 — 최상위 → 해당 조직 순서의 코드 목록 (가입 화면 계층 선택 자동 채우기 · Phase R). 없거나 순환이면 빈 목록 */
export function orgChain(orgs: { code: string; parent: string | null }[], code: string): string[] {
  const byCode = new Map(orgs.map((o) => [o.code, o]));
  const out: string[] = [];
  const seen = new Set<string>();
  let cur = byCode.get(code);
  while (cur) {
    if (seen.has(cur.code)) return [];
    seen.add(cur.code);
    out.unshift(cur.code);
    cur = cur.parent ? byCode.get(cur.parent) : undefined;
    if (!cur && out.length && byCode.get(out[0])?.parent) return []; // 상위가 목록에 없음(사용 안 함 등)
  }
  return out;
}
