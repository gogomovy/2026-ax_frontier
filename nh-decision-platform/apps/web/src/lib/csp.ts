/**
 * 콘텐츠 보안 정책 (B.33) — proxy.ts 가 요청마다 nonce 를 만들어 스크립트를 nonce + strict-dynamic 으로만 허용한다.
 * 외부 출처는 글꼴 CDN(jsdelivr · Pretendard) 하나뿐이다. 스타일은 React 의 style 속성 때문에 'unsafe-inline' 을 유지한다.
 */
export function buildCsp(nonce: string, dev = process.env.NODE_ENV !== "production"): string {
  return [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${dev ? " 'unsafe-eval'" : ""}`,
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",
    "font-src 'self' data: https://cdn.jsdelivr.net",
    "img-src 'self' data: blob:",
    `connect-src 'self'${dev ? " ws: wss:" : ""}`,
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "object-src 'none'",
  ].join("; ");
}

/** 사내 SSO 중계 페이지 경로 — 정적 sso-proxy.html · 벤더 NC 스크립트(/nc/*) (Phase R) */
export const SSO_PAGE_PATHS = ["/sso-proxy.html", "/sso-proxy.js", "/nc"];

export function isSsoPagePath(pathname: string): boolean {
  return SSO_PAGE_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`));
}

/** NC 에이전트 출처 — 기본 https://127.0.0.1:13015, 출처 형식(https?://host[:port])만 받는다 */
export function ncAgentOrigin(raw: string | undefined = process.env.NC_SSO_AGENT_ORIGIN): string {
  const v = (raw ?? "").trim();
  return /^https?:\/\/[A-Za-z0-9.-]+(:\d{1,5})?$/.test(v) ? v : "https://127.0.0.1:13015";
}

/**
 * SSO 중계 페이지 전용 정책 — 벤더 스크립트는 nonce 를 붙일 수 없어 'self' 스크립트를 허용하고,
 * PC 의 NC 에이전트(로컬 출처)와의 통신(ajax · script 삽입)만 추가로 연다. 나머지는 기본 정책과 같다.
 */
export function buildSsoPageCsp(agent: string = ncAgentOrigin()): string {
  return [
    "default-src 'self'",
    `script-src 'self' 'unsafe-inline' ${agent}`,
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",
    "font-src 'self' data: https://cdn.jsdelivr.net",
    "img-src 'self' data:",
    `connect-src 'self' ${agent}`,
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "object-src 'none'",
  ].join("; ");
}

/** 요청마다 새 nonce (128비트 무작위, base64) */
export function newNonce(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  let s = "";
  for (const b of bytes) s += String.fromCharCode(b);
  return btoa(s);
}
