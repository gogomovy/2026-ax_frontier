import "server-only";
import { cookies, headers } from "next/headers";
import { notFound, redirect } from "next/navigation";
import { SESSION_COOKIE } from "./config";

/**
 * 서버 컴포넌트용 API 호출 — 요청의 세션 쿠키를 그대로 백엔드로 전달한다.
 * 401 → 로그인 화면, 403 → 권한 없음 화면, 404 → notFound.
 */
const BASE = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export async function hasSession(): Promise<boolean> {
  return Boolean((await cookies()).get(SESSION_COOKIE)?.value);
}

/** 백엔드 응답 대기 상한(ms) — 멈춘 요청이 화면 렌더를 무한정 붙잡지 않도록 (B.32 · 환경변수 API_TIMEOUT_MS) */
const TIMEOUT_MS = Number(process.env.API_TIMEOUT_MS ?? 20000);

async function raw(path: string): Promise<Response> {
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  return fetch(`${BASE}${path}`, {
    cache: "no-store",
    headers: token ? { cookie: `${SESSION_COOKIE}=${token}` } : {},
    signal: AbortSignal.timeout(TIMEOUT_MS),
  });
}

async function pagePath(): Promise<string | null> {
  try {
    return (await headers()).get("x-pathname");
  } catch {
    return null;
  }
}

/** 화면 데이터 — 실패 시 화면 이동(로그인/권한/404) */
export async function apiGet<T>(path: string): Promise<T> {
  const res = await raw(path);
  if (res.status === 401) redirect("/login");
  // 권한 없음 — 화면 주소(proxy 가 실은 x-pathname)가 있으면 그것을, 없으면 API 경로를 넘긴다 (Phase E · NAV-03)
  if (res.status === 403) redirect(`/forbidden?from=${encodeURIComponent((await pagePath()) || path)}`);
  if (res.status === 404) notFound();
  if (!res.ok) throw new ApiError(res.status, `API ${path} → ${res.status}`);
  return (await res.json()) as T;
}

/** 선택 데이터 — 권한이 없거나 실패하면 null (레이아웃 부트스트랩 등) */
export async function apiTry<T>(path: string): Promise<T | null> {
  try {
    const res = await raw(path);
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}
