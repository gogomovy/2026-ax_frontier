/** 데이터 소스 — `api`(백엔드 연동, 로그인 필요) | `mock`(목데이터 단독 실행) */
export const DATA_SOURCE = process.env.NEXT_PUBLIC_DATA_SOURCE ?? "mock";
export const API_MODE = DATA_SOURCE === "api";
export const SESSION_COOKIE = "nhdip_session";
