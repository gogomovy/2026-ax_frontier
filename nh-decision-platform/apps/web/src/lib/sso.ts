/** 로그인 화면의 SSO 안내 (OIDC · 사내 SSO(NC 티켓, Phase R) 공통) */

export type LocalLoginMode = "all" | "admin" | "none";

export interface SsoProvider {
  enabled: boolean;
  label: string;
  localLogin: string;
}

/** 켜진 SSO 들의 사번 · 비밀번호 로그인 허용 범위 중 가장 좁은 것 — 백엔드 local_login_allowed 와 같은 규칙 */
export function strictestLocalLogin(providers: (SsoProvider | null | undefined)[]): LocalLoginMode {
  const modes = providers.filter((p): p is SsoProvider => !!p?.enabled).map((p) => (p.localLogin || "all").toLowerCase());
  if (modes.includes("none")) return "none";
  if (modes.includes("admin")) return "admin";
  return "all";
}

/** SSO 실패 사유 (서버 → /login?sso_error=) */
export const SSO_ERROR: Record<string, string> = {
  denied: "SSO 로그인이 취소되었거나 거부되었습니다.",
  state: "로그인 요청이 만료되었습니다. 다시 시도해 주세요.",
  token: "SSO 인증 정보를 확인하지 못했습니다. 잠시 후 다시 시도해 주세요.",
  account: "SSO 계정과 연결된 사용 가능한 사번이 없습니다. 가입 신청 또는 관리자 승인을 확인해 주세요.",
  disabled: "SSO 로그인이 설정되어 있지 않습니다.",
  // 사내 SSO(NC 티켓)
  no_ticket: "통합 로그인 티켓을 받지 못했습니다. 통합 로그인(NC) 에이전트 로그인 상태를 확인한 뒤 다시 시도해 주세요.",
  nonce: "로그인 요청 정보가 일치하지 않습니다(재사용 · 위조 의심). 다시 시도해 주세요.",
  toa: "허용되지 않은 인증 방식입니다. 운영 ID/PW 또는 인증서로 통합 로그인해 주세요.",
  verify_failed: "통합 로그인 티켓 검증에 실패했습니다. 다시 시도해 주세요.",
  verifier_down: "통합 로그인 검증 서버에 연결하지 못했습니다. 잠시 후 다시 시도하거나 관리자에게 문의해 주세요.",
  user_not_found: "인사 정보에 등록되지 않은 사번입니다. 관리자에게 인사 정보 반영을 요청해 주세요.",
};

/** SSO 시작 주소 — 로그인 뒤 돌아갈 화면(next)은 같은 사이트 상대 경로만 (safeNext 를 거친 값) */
export function ssoStartHref(base: string, next: string | null): string {
  return `${base}${next ? `?next=${encodeURIComponent(next)}` : ""}`;
}
