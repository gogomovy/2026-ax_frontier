/**
 * 용어집 조회 (클라이언트 공용).
 * 레이아웃이 서버에서 받은 용어집을 SessionProvider 가 등록한다 — 등록 전이거나 없는 용어는 null.
 */
import type { Term } from "./types";

let registry: Record<string, Term> | null = null;

export function registerTerms(terms: Term[] | null | undefined) {
  if (!terms) return;
  registry = Object.fromEntries(terms.map((t) => [t.termCode, t]));
}

export function getTermSync(code: string): Term | null {
  return registry?.[code] ?? null;
}
