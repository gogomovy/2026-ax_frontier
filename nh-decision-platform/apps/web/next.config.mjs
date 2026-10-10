const API_MODE = (process.env.NEXT_PUBLIC_DATA_SOURCE ?? "mock") === "api";
// 백엔드 내부 주소 — docker compose 에서는 http://api:8000 (빌드 인자 + 런타임 환경변수)
const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

// 보안 헤더 (B.32) — 외부 출처는 글꼴 CDN(jsdelivr · Pretendard) 하나뿐이다.
// CSP: API 모드는 proxy.ts 가 요청마다 nonce 정책을 붙인다(B.33 · src/lib/csp.ts).
//      목데이터 모드는 정적 페이지라 nonce 를 쓸 수 없어 아래 정적 정책('unsafe-inline')을 쓴다.
const DEV = process.env.NODE_ENV !== "production";
const CSP = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${DEV ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",
  "font-src 'self' data: https://cdn.jsdelivr.net",
  "img-src 'self' data: blob:",
  `connect-src 'self'${DEV ? " ws: wss:" : ""}`,
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "object-src 'none'",
].join("; ");
const SECURITY_HEADERS = [
  ...(API_MODE ? [] : [{ key: "Content-Security-Policy", value: CSP }]),
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
  async headers() {
    return [{ source: "/:path*", headers: SECURITY_HEADERS }];
  },
  async redirects() {
    // 3단계 흐름으로 재편하면서 이전 경로를 유지한다. (API 모드의 `/` 는 사용자 권한 첫 화면으로 — app/page.tsx)
    return [
      ...(API_MODE ? [] : [{ source: "/", destination: "/hq/overview", permanent: false }]),
      { source: "/hq/dashboard", destination: "/hq/overview", permanent: false },
      { source: "/hq/dashboard/loan", destination: "/hq/analysis", permanent: false },
      { source: "/hq/dashboard/loan/:path*", destination: "/hq/analysis", permanent: false },
      { source: "/hq/goals/loan", destination: "/hq/goals", permanent: false },
    ];
  },
  async rewrites() {
    // 브라우저 → 같은 출처 /backend/* → FastAPI (세션 쿠키를 같은 출처로 유지)
    return [{ source: "/backend/:path*", destination: `${API_INTERNAL_URL}/:path*` }];
  },
  env: {
    NEXT_PUBLIC_DATA_SOURCE: process.env.NEXT_PUBLIC_DATA_SOURCE ?? "mock",
    NEXT_PUBLIC_AS_OF: process.env.NEXT_PUBLIC_AS_OF ?? "2026-08-31",
  },
};
export default nextConfig;
