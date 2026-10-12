/** 주소의 지점 인자(`?office=`, B.47) — 서버가 같은 형식만 받으므로 여기서도 형식이 맞을 때만 쓴다 */
export function officeParam(sp: Record<string, string | string[] | undefined> | undefined): string | null {
  const v = sp?.office;
  const s = Array.isArray(v) ? v[0] : v;
  return s && /^[A-Za-z0-9_-]{1,20}$/.test(s) ? s : null;
}

/** 영업점 화면 사이 이동에 지점 인자를 이어 붙인다 */
export function withOffice(href: string, office: string | null | undefined): string {
  if (!office) return href;
  return `${href}${href.includes("?") ? "&" : "?"}office=${encodeURIComponent(office)}`;
}
