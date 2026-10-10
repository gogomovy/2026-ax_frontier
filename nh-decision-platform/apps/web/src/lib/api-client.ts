/**
 * 브라우저용 API 호출 — 같은 출처의 `/backend/*` (Next rewrites → api 서비스).
 * 세션 쿠키(HttpOnly)는 브라우저가 자동으로 붙인다.
 */
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public body?: unknown,
  ) {
    super(message);
  }
}

function detail(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const d = (body as { detail: unknown }).detail;
    if (typeof d === "string") return d;
    if (d && typeof d === "object" && "message" in d && typeof (d as { message: unknown }).message === "string") return (d as { message: string }).message;
    if (Array.isArray(d)) return d.map((x) => (x && typeof x === "object" && "msg" in x ? String(x.msg) : String(x))).join(", ");
  }
  return fallback;
}

export async function api<T = unknown>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const { json, headers, ...rest } = init;
  const res = await fetch(`/backend${path}`, {
    credentials: "same-origin",
    cache: "no-store",
    ...rest,
    headers: {
      ...(json !== undefined ? { "Content-Type": "application/json" } : {}),
      ...(headers ?? {}),
    },
    body: json !== undefined ? JSON.stringify(json) : rest.body,
  });
  const text = await res.text();
  let body: unknown = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = text;
  }
  if (res.status === 401 && typeof window !== "undefined" && !path.startsWith("/auth/")) {
    // 세션 만료 — 레이아웃의 세션 데이터를 비우기 위해 전체 새로고침으로 로그인 화면 이동
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.href = `/login?next=${encodeURIComponent(window.location.pathname)}`;
  }
  if (!res.ok) {
    // 서버 오류는 추적 ID 를 함께 보여준다 — 관리자 [요청 추적]에서 전 구간 조회 (작업 0.5)
    const trace = res.headers.get("X-Trace-Id");
    const msg = detail(body, `요청 실패 (${res.status})`);
    throw new ApiError(res.status, res.status >= 500 && trace ? `${msg} · 추적 ID ${trace}` : msg, body);
  }
  return body as T;
}

export const apiGetC = <T,>(path: string) => api<T>(path);
export const apiPost = <T,>(path: string, json?: unknown) => api<T>(path, { method: "POST", json: json ?? {} });
export const apiPatch = <T,>(path: string, json: unknown) => api<T>(path, { method: "PATCH", json });
export const apiPut = <T,>(path: string, json: unknown) => api<T>(path, { method: "PUT", json });
export const apiDelete = <T,>(path: string) => api<T>(path, { method: "DELETE" });
