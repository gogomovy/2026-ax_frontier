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

/** 요청마다 새 nonce (128비트 무작위, base64) */
export function newNonce(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  let s = "";
  for (const b of bytes) s += String.fromCharCode(b);
  return btoa(s);
}
