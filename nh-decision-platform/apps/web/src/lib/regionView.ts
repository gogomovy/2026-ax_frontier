/**
 * 영업본부 통합 업적평가(/region) 표시 계산 — React 없음, 단위 시험 대상.
 * 점수 · 만점 · 순위 · 평균은 모두 화면 API(/screens/region/kpi) 값이고, 여기서는 글자 · 막대 폭만 만든다.
 */
import { NO_VALUE } from "@/lib/period";
import type { RegionKpi, RegionKpiBranch, RegionKpiGroup } from "@/lib/types";

type SearchParams = Record<string, string | string[] | undefined> | undefined;

/** 주소의 지역 인자(`?region=`) — 서버와 같은 형식만 받는다 */
export function regionParam(sp: SearchParams): string | null {
  const v = sp?.region;
  const s = Array.isArray(v) ? v[0] : v;
  return s && /^[A-Za-z0-9_-]{1,20}$/.test(s) ? s : null;
}

/** 짧은 지점 이름 — 끝의 '지점 · 금융센터 · 영업점'을 뗀다('서초지점' → '서초'). 남는 글자가 없으면 원래 이름 */
export function shortBranchName(name: string): string {
  const short = name.replace(/(지점|금융센터|영업점)$/, "").trim();
  return short || name;
}

/** 자료 대기 지점 안내 — '서초 · 역삼역 자료 대기'. 대기 지점이 없으면 null */
export function pendingNote(branches: RegionKpiBranch[]): string | null {
  const pending = branches.filter((b) => !b.available).map((b) => shortBranchName(b.name));
  return pending.length ? `${pending.join(" · ")} 자료 대기` : null;
}

/** 득점 그룹 — 가 · 감점(adjustment)은 만점이 없어 막대 · 열로 그리지 않는다 */
export function scoreGroups(data: Pick<RegionKpi, "groups">): RegionKpiGroup[] {
  return (data.groups ?? []).filter((g) => g.kind !== "adjustment");
}

/** 0–1 로 자른 비율 */
const clamp01 = (x: number) => Math.min(1, Math.max(0, x));

/** 배점 대비 득점률(%) — 막대 폭용, 0–100 으로 자른다. 값 · 만점이 없으면 0 */
export function ratePct(score: number | null | undefined, max: number | null | undefined): number {
  if (typeof score !== "number" || typeof max !== "number" || !max) return 0;
  return clamp01(score / max) * 100;
}

/** 총득점 두 겹 막대 폭(%) — now = 현재 득점, extra = AI 가이드 반영 시 추가 득점(음수면 0). 둘의 합은 100을 넘지 않는다 */
export function barWidths(b: Pick<RegionKpiBranch, "total" | "totalAfter" | "max">): { now: number; extra: number } {
  const now = ratePct(b.total, b.max);
  if (typeof b.total !== "number" || typeof b.totalAfter !== "number" || !b.max) return { now, extra: 0 };
  const extra = clamp01(Math.max(0, b.totalAfter - b.total) / b.max) * 100;
  return { now, extra: Math.min(extra, Math.max(0, 100 - now)) };
}

const one = new Intl.NumberFormat("ko-KR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const upToOne = new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 1 });

/** 득점 · 득점률 — 소수 1자리 고정('137.0'). 값이 없으면 '–' */
export function fmt1(v: number | null | undefined): string {
  return typeof v === "number" && Number.isFinite(v) ? one.format(v) : NO_VALUE;
}

/** 만점 · 건수 — 정수는 정수로('1,000'), 소수는 1자리까지 */
export function fmtPts(v: number | null | undefined): string {
  return typeof v === "number" && Number.isFinite(v) ? upToOne.format(v) : NO_VALUE;
}

/** 부호 붙인 득점 — '+26.7' · '−3.0'(수학 기호) · '0.0' */
export function signed1(v: number | null | undefined): string {
  if (typeof v !== "number" || !Number.isFinite(v)) return NO_VALUE;
  if (v > 0) return `+${fmt1(v)}`;
  if (v < 0) return `−${fmt1(-v)}`;
  return fmt1(v);
}

const typesText = (types: string[] | undefined) => (types ?? []).filter(Boolean).join(" · ");

/** AI 가이드 반영 시 평균 보조 줄 — '+20.6점 · 신설 평가항목 대응'. 평균 상향이 없으면 null */
export function upliftNote(summary: RegionKpi["summary"]): string | null {
  if (typeof summary.avgUplift !== "number") return null;
  const t = typesText(summary.changeTypes);
  return `${signed1(summary.avgUplift)}점${t ? ` · ${t} 평가항목 대응` : ""}`;
}

/** 득점 향상 기회 보조 줄 — '2개 영업점 · 신설 평가기준' */
export function opportunityNote(summary: RegionKpi["summary"]): string {
  const t = typesText(summary.changeTypes);
  return `${fmtPts(summary.opportunityBranches ?? 0)}개 영업점${t ? ` · ${t} 평가기준` : ""}`;
}

/** 지역 만점 — 계산된 지점의 만점이 모두 같을 때만 그 값(평균 득점 '/ 1,000점'). 다르거나 없으면 null */
export function regionMax(branches: RegionKpiBranch[]): number | null {
  const maxes = [...new Set(branches.filter((b) => b.available && typeof b.max === "number").map((b) => b.max as number))];
  return maxes.length === 1 ? maxes[0] : null;
}

/** 지점의 그룹 득점 (그룹 코드로 찾는다) */
export function groupOf(b: RegionKpiBranch, code: string): RegionKpiGroup | undefined {
  return b.groups.find((g) => String(g.code) === String(code));
}

const mean = (xs: (number | null | undefined)[]): number | null => {
  const v = xs.filter((x): x is number => typeof x === "number" && Number.isFinite(x));
  return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null;
};
const round1 = (v: number | null) => (v === null ? null : Math.round(v * 10) / 10);

/**
 * 화면 보조 값 채우기 — 화면 API 가 주지 않은 값만, 받은 지점 값(득점률 · 상향 점수 · 알림 수)에서 평균 · 합만 센다.
 * 순위 · 득점 · 만점 · 평균 득점은 서버 값 그대로(여기서 다시 매기지 않는다). 서버가 값을 주면 그 값을 쓴다.
 */
export function withRegionDerived(data: RegionKpi): RegionKpi {
  const done = data.branches.filter((b) => b.available);
  const groups = (data.groups ?? []).map((g) => {
    if (g.avgRate !== undefined) return g;
    const rate = mean(done.map((b) => groupOf(b, String(g.code))?.rate));
    return { ...g, avgRate: round1(rate) };
  });
  if (!groups.some((g) => g.lowest !== undefined && g.lowest)) {
    const rated = groups.filter((g) => g.kind !== "adjustment" && typeof g.avgRate === "number");
    const low = rated.length ? rated.reduce((a, b) => ((b.avgRate as number) < (a.avgRate as number) ? b : a)) : null;
    for (const g of groups) g.lowest = low !== null && g.code === low.code;
  }
  const s = data.summary;
  const opportunities = s.opportunities ?? s.alerts ?? done.reduce((n, b) => n + (b.alertCount ?? 0), 0);
  return {
    ...data,
    groups,
    branches: data.branches.map((b) => (b.changeTypes ? b : { ...b, changeTypes: Array.from(new Set(b.alerts.map((a) => a.changeType).filter((t): t is string => Boolean(t)))) })),
    summary: {
      ...s,
      avgUplift: s.avgUplift !== undefined ? s.avgUplift : round1(mean(done.map((b) => b.uplift))),
      opportunities,
      opportunityBranches: s.opportunityBranches ?? done.filter((b) => (b.alertCount ?? 0) > 0).length,
      changeTypes: s.changeTypes ?? Array.from(new Set(done.flatMap((b) => b.alerts.map((a) => a.changeType)).filter((t): t is string => Boolean(t)))),
    },
  };
}
