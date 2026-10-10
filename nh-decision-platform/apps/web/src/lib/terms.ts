/**
 * 용어집 조회 (클라이언트 공용).
 * API 모드에서는 레이아웃이 서버에서 받은 용어집을 SessionProvider 가 등록하고,
 * 목데이터 모드에서는 목데이터 용어집을 쓴다.
 */
import { TERM_MAP } from "@/mock/terms";
import { API_MODE } from "./config";
import type { Term } from "./types";

let registry: Record<string, Term> | null = null;

export function registerTerms(terms: Term[] | null | undefined) {
  if (!terms) return;
  registry = Object.fromEntries(terms.map((t) => [t.termCode, t]));
}

export function getTermSync(code: string): Term | null {
  if (registry) return registry[code] ?? null;
  return API_MODE ? null : (TERM_MAP[code] ?? null);
}
