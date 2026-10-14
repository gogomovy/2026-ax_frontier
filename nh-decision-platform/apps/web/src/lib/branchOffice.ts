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

/** 주소 검색 문자열(`?office=…`)의 지점 인자 */
export function officeFromSearch(search: string): string | null {
  return officeParam(Object.fromEntries(new URLSearchParams(search)));
}

/* 메뉴 링크에 지점을 잇는 규칙은 업무 영역 모델(lib/scopeModel · officeHrefOf)로 옮겼다 — 주소 접두어로 영업점 화면을 판정하지 않는다 (Phase K) */
