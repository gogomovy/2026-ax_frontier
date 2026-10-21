/**
 * 기간 대체 표기 — 계산 커널이 '전년 동기' 같은 달 수 비교의 그 달이 없어 가장 가까운 보관 기준일과 견줬을 때(Figure.basis),
 * 화면 글자가 여전히 '전년 동기'라고 말하지 않게 실제로 견준 기간을 쓴다. 안내 문구는 서버(calc.metrics.fallback_note)와 같은 글이다.
 */
import type { Figure, GapBasis, PeriodBasis } from "./types";

/** 202508 · 2025-08-31 → 2025.08 */
export function periodDot(v: unknown): string {
  const s = String(v ?? "").replace(/[^0-9]/g, "");
  return s.length >= 6 ? `${s.slice(0, 4)}.${s.slice(4, 6)}` : String(v ?? "");
}

/** 기간 토큰의 업무 이름 — 전년 동기 · 전년 말 · 전월 · N개월 전 */
export function tokenName(token: string): string {
  const m = /^\$(latest|earliest|prev|prev_year_end|nearest)(?:-(\d+))?$/.exec(token ?? "");
  if (!m) return token;
  const n = m[2] ? Number(m[2]) : 0;
  if (m[1] === "prev_year_end") return "전년 말";
  if (m[1] === "latest" && n) {
    const named: Record<number, string> = { 1: "전월", 12: "전년 동기", 24: "2년 전 동기" };
    return named[n] ?? (n % 12 === 0 ? `${n / 12}년 전 동기` : `${n}개월 전`);
  }
  return token;
}

/** 대체 한 건 → '전년 동기(2025.08) 자료가 없어 가장 가까운 기준일 2026.01 과 비교' */
export function basisNote(b: PeriodBasis): string {
  return `${tokenName(b.token)}(${periodDot(b.wanted)}) 자료가 없어 가장 가까운 기준일 ${periodDot(b.used)} 과 비교`;
}

/** 그 수치가 token 을 대체했으면 그 기록 — 없으면 null */
export function basisOf(f: Pick<Figure, "basis"> | null | undefined, token: string): PeriodBasis | null {
  return (f?.basis ?? []).find((b) => b.token === token && b.used) ?? null;
}

/** 수치의 대체 안내 문구 목록 — 없으면 빈 목록. 비교 기간 맞춤(목표 환산 · 기간 인자)이 있으면 그 안내도 */
export function basisNotes(f: Pick<Figure, "basis" | "align"> | null | undefined): string[] {
  const out = (f?.basis ?? [])
    .filter((b) => b.token && b.used)
    .map((b) => basisNote(b) + (b.months && b.wantedMonths && b.months !== b.wantedMonths ? ` · 비교 기간 ${b.months}개월` : ""));
  const al = f?.align;
  if (al?.goal) out.push(`경영목표를 비교 기간 ${al.months}개월로 환산(× ${al.months}/${al.wantedMonths})해 견준 값`);
  if (al?.params) out.push(`기간을 실제 비교 기간 ${al.months}개월로 맞춰 계산한 값`);
  return Array.from(new Set(out));
}

/** 목표 판정 근거 한 줄 — '7개월 환산 목표 4.08% 기준' · '판정 보류 — 비교 기간이 연 목표와 다름'. 근거가 없으면 null */
export function gapBasisText(gb: GapBasis | null | undefined, unit = ""): string | null {
  if (!gb) return null;
  const used = gb.used ? `${periodDot(gb.used)} 대비` : "";
  if (gb.held) return `판정 보류 — ${used ? `${used} ` : ""}${gb.months}개월 실적이라 연 목표와 기간이 다름`;
  if (typeof gb.aligned === "number") return `${used ? `${used} · ` : ""}${gb.months}개월 환산 목표 ${gb.aligned.toFixed(2)}${unit} 기준`;
  return used ? `${used} 실적 기준` : null;
}

/** 비교 대상 이름 — 그 수치가 token 을 대체했으면 실제 견준 기간(2026.01), 아니면 기본 이름(전년 동기) */
export function periodName(f: Pick<Figure, "basis"> | null | undefined, token: string, name: string): string {
  const b = basisOf(f, token);
  return b ? periodDot(b.used) : name;
}

/** 표 열 머리 — 그 열 수치들이 실제로 가리키는 기간. 대체가 없으면 기본 머리, 행마다 다르면 모두(2025.08 · 2026.01) */
export function columnPeriod(figs: (Pick<Figure, "basis"> | null | undefined)[], token: string, name: string): string {
  const shown = figs.filter((f) => f != null).map((f) => periodName(f, token, name));
  const uniq = Array.from(new Set(shown.length ? shown : [name]));
  return uniq.join(" · ");
}

/** 증가율 설명 한 문장 — 전년 동월 자료가 있으면 '전년 동월 말 잔액 대비', 없어 대체됐으면 실제 기준일과 그 사실 */
export function growthBasisHint(b: PeriodBasis | null | undefined): string {
  if (!b) return "증가율은 전년 동월 말 잔액 대비입니다.";
  const months = b.months && b.wantedMonths && b.months !== b.wantedMonths ? `(${b.months}개월)` : "";
  return `증가율은 ${periodDot(b.used)} 말 잔액 대비${months}입니다 — ${tokenName(b.token)}(${periodDot(b.wanted)}) 자료가 없어 가장 가까운 기준일과 견줬습니다.`;
}
