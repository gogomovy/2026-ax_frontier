import { NextResponse, type NextRequest } from "next/server";

/**
 * API 모드 인증 게이트 (Next.js 16 proxy — 구 middleware) — 세션 쿠키가 없으면 로그인 화면으로 보낸다.
 * 쿠키의 유효성·화면 권한은 백엔드가 최종 판정한다(401 → 로그인, 403 → 권한 없음).
 */
const PUBLIC = ["/login", "/signup", "/forbidden", "/api/health", "/backend", "/_next", "/favicon", "/icon", "/robots.txt"];

export function proxy(req: NextRequest) {
  if ((process.env.NEXT_PUBLIC_DATA_SOURCE ?? "mock") !== "api") return NextResponse.next();
  const { pathname, search } = req.nextUrl;
  if (PUBLIC.some((p) => pathname === p || pathname.startsWith(`${p}/`) || pathname.startsWith(p + "."))) {
    return NextResponse.next();
  }
  if (!req.cookies.get("nhdip_session")?.value) {
    const url = req.nextUrl.clone();
    url.pathname = "/login";
    url.search = pathname === "/" ? "" : `?next=${encodeURIComponent(pathname + search)}`;
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
