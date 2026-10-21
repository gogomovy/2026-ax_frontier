// 백엔드 내부 주소 — docker compose 에서는 http://api:8000 (빌드 인자 + 런타임 환경변수)
const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

// 보안 헤더 (B.32) — 외부 출처는 열지 않는다(폐쇄망 · 글꼴도 pretendard 패키지로 앱이 직접 낸다).
// CSP 는 proxy.ts 가 요청마다 nonce 정책을 붙인다(B.33 · src/lib/csp.ts) — 화면 데이터는 항상 백엔드 API 에서 온다(Phase I).
const SECURITY_HEADERS = [
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=()" },
  ...(process.env.COOKIE_SECURE === "true" ? [{ key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" }] : []),
];

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  reactStrictMode: true,
  poweredByHeader: false,
  // /backend 프록시 대기 상한 — 기본 30초면 LLM 을 부르는 요청(분석 정제 · 질의)이 끊긴다(실 LLM 시험에서 발견). 백엔드가 LLM 대기 상한을 따로 둔다
  experimental: { proxyTimeout: 180_000 },
  async headers() {
    return [{ source: "/:path*", headers: SECURITY_HEADERS }];
  },
  async redirects() {
    // 3단계 흐름으로 재편하면서 이전 경로를 유지한다. (`/` 는 사용자 권한 첫 화면으로 — app/page.tsx)
    return [
      { source: "/hq/dashboard", destination: "/hq/overview", permanent: false },
      { source: "/hq/dashboard/loan", destination: "/hq/analysis", permanent: false },
      { source: "/hq/dashboard/loan/:path*", destination: "/hq/analysis", permanent: false },
      { source: "/hq/goals/loan", destination: "/hq/goals", permanent: false },
    ];
  },
  async rewrites() {
    // 브라우저 → 같은 출처 /backend/* → FastAPI (세션 쿠키를 같은 출처로 유지)
    // /nc/* → 벤더 NC 스크립트(사내 SSO 중계 페이지용 · API 가 배포 폴더에서 내준다, Phase R)
    return [
      { source: "/backend/:path*", destination: `${API_INTERNAL_URL}/:path*` },
      { source: "/nc/:name", destination: `${API_INTERNAL_URL}/auth/nc/assets/:name` },
    ];
  },
};
export default nextConfig;
