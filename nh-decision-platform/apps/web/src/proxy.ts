import { NextResponse, type NextRequest } from "next/server";
import { buildCsp, newNonce } from "@/lib/csp";

/**
 * API 모드 인증 게이트 (Next.js 16 proxy — 구 middleware) — 세션 쿠키가 없으면 로그인 화면으로 보낸다.
 * 쿠키의 유효성·화면 권한은 백엔드가 최종 판정한다(401 → 로그인, 403 → 권한 없음).
 * 요청마다 CSP nonce 를 만들어 요청 · 응답 헤더에 싣는다 — Next 가 렌더링 때 프레임워크 스크립트에 nonce 를 붙인다 (B.33).
 */
const PUBLIC = ["/login", "/signup", "/forbidden", "/api/health", "/backend", "/_next", "/favicon", "/icon", "/robots.txt"];

function withCsp(res: NextResponse, csp: string): NextResponse {
  res.headers.set("Content-Security-Policy", csp);
  return res;
}

export function proxy(req: NextRequest) {
  if ((process.env.NEXT_PUBLIC_DATA_SOURCE ?? "mock") !== "api") return NextResponse.next();
  const nonce = newNonce();
  const csp = buildCsp(nonce);
  const headers = new Headers(req.headers);
  // 전달 헤더(X-Forwarded-For)는 시작점(server-entry.cjs)이 실제 접속 주소로 바로잡아 둔다 (B.33)
  headers.set("x-nonce", nonce);
  headers.set("Content-Security-Policy", csp);
  const { pathname, search } = req.nextUrl;
  // 서버 컴포넌트가 권한 없음(403)으로 보낼 때 '어느 화면' 이었는지 알리려고 화면 주소를 싣는다 (Phase E · NAV-03)
  headers.set("x-pathname", pathname);
  const pass = () => withCsp(NextResponse.next({ request: { headers } }), csp);

  if (PUBLIC.some((p) => pathname === p || pathname.startsWith(`${p}/`) || pathname.startsWith(p + "."))) {
    return pass();
  }
  if (!req.cookies.get("nhdip_session")?.value) {
    const url = req.nextUrl.clone();
    url.pathname = "/login";
    url.search = pathname === "/" ? "" : `?next=${encodeURIComponent(pathname + search)}`;
    return withCsp(NextResponse.redirect(url), csp);
  }
  return pass();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
