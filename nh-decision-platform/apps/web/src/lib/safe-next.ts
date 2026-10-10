/** 같은 사이트의 상대 경로만 허용 — 열린 리디렉션 차단(`//`, `/\\`, 제어 문자 · 공백 거부). 서버 oidc._safe_next 와 같은 규칙 (B.32) */
export function safeNext(n: string | null | undefined): string | null {
  return n && n.startsWith("/") && !n.startsWith("//") && !n.includes("\\") && /^[\x21-\x7e]{1,300}$/.test(n) ? n : null;
}
