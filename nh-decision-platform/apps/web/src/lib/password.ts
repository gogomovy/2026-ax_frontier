/** 비밀번호 정책 — 서버 `password_policy_error` 와 같은 순서 · 규칙(8자 이상 · 72바이트 이하 · 영문 + 숫자). 맞으면 null */
export function passwordRuleError(v: string): string | null {
  if (v.length < 8) return "8자 이상이어야 합니다";
  if (new TextEncoder().encode(v).length > 72) return "너무 깁니다(72바이트 이하)";
  if (!/[A-Za-z]/.test(v) || !/\d/.test(v)) return "영문과 숫자를 함께 넣으세요";
  return null;
}
