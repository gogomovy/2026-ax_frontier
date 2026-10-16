/**
 * 신용리스크관리부 2단계 · 상품별 충당금 비중 (시안 389:2) — 분석 에이전트 보고서(dynamic)를 화면 모델로 읽는다.
 * 숫자는 모두 보고서의 커널 값(전체 충당금 · 상품 수 · 1위 비중 · 순위 표)이고, 순위 구간 합 · 누적 비중 · '절반을 넘는 순위'는
 * 커널 수식으로 낼 수 없어 여기서 계산하고 계산 추적(derivedFigure)을 붙인다. 서버 page 에서도 쓰므로 순수 TS 로 둔다.
 */
import { derivedFigure } from "./derived";
import { NO_VALUE } from "./period";
import type { Figure, Insight, ReportDoc, Severity } from "./types";

/** 분석 명세(spec.json)의 지표 key — 그림 id 는 `fig-<token>-<key>` */
export const PROVISION_KEYS = { total: "total_provision", count: "product_count", top1: "top1_provision", top1Share: "top1_share" } as const;
/** 분석 명세의 표 제목 — 내림차순 상위 · 오름차순 하위 (둘을 이름으로 합쳐 전체 상품을 덮는다) */
export const RANK_CHART = "상품별 충당금 순위";
export const TAIL_CHART = "충당금 하위 상품";
/** 시안 순위 구간 끝 (1–5 · 6–10 · 11–20 · 나머지) — 판정 숫자가 아니라 시안이 정한 묶음 */
export const BAND_ENDS = [5, 10, 20] as const;
/** '절반' 정의 — 누적 비중이 처음 이 값 이상이 되는 순위 */
export const HALF_SHARE = 50;
/** 단위 환산 — 1억원 = 100백만원 · 1조원 = 10,000억원 */
export const MN_PER_EOK = 100;
export const EOK_PER_JO = 10000;
/** 순위 표 두 칸 — 왼쪽 상위 1–10위 · 오른쪽 11–20위 (시안) */
export const COLUMN_SIZE = 10;
/** 문구의 금액 범위 반올림 단위(억원) — '1,500억~1,900억원대' */
const RANGE_STEP_EOK = 100;
/** 비중 소수 자리 */
const SHARE_DECIMALS = 1;

const nf = (decimals = 0) => new Intl.NumberFormat("ko-KR", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });

/** id 가 `-<key>` 로 끝나는 수치 */
export function figureByKey(report: ReportDoc, key: string): Figure | undefined {
  return Object.values(report.figures).find((f) => f.id.endsWith(`-${key}`));
}
function chartByTitle(report: ReportDoc, title: string) {
  for (const s of report.sections) for (const b of s.blocks) if (b.type === "chart" && b.chart?.title === title) return b.chart;
  return null;
}
/** 이 화면으로 그릴 보고서인가 — 명세 계약(지표 key · 순위 표)에 맞는 분석 에이전트 보고서 */
export function isProvisionShareReport(report: ReportDoc): boolean {
  return (
    report.kind === "dynamic" &&
    Boolean(figureByKey(report, PROVISION_KEYS.total)) &&
    Boolean(figureByKey(report, PROVISION_KEYS.count)) &&
    Boolean(figureByKey(report, PROVISION_KEYS.top1Share)) &&
    Boolean(chartByTitle(report, RANK_CHART)) &&
    // 그릴 수 있어야(전체 충당금 > 0 · 순위 행 있음) 이 화면 — 아니면 기존 보고서 보기
    provisionModel(report) !== null
  );
}

export interface ProvisionRow {
  rank: number;
  name: string;
  /** 백만원 */
  value: number;
  /** 억원(반올림) */
  eok: number;
  /** 전체 대비 % */
  share: number;
  /** 누적 % */
  cum: number;
}
export interface ProvisionBand {
  key: string;
  label: string;
  from: number;
  to: number;
  /** 백만원 */
  sum: number;
  share: Figure;
}
export interface ProvisionModel {
  total: Figure;
  count: Figure | undefined;
  top1: Figure | undefined;
  top1Share: Figure | undefined;
  /** 상품 수 (커널 값 · 없으면 행 수) */
  n: number;
  rows: ProvisionRow[];
  /** 모든 상품의 순위를 알고 있는가 */
  complete: boolean;
  bands: ProvisionBand[];
  cumulative: { n: number; share: number }[];
  /** 누적 비중이 처음 절반 이상이 되는 순위 K */
  half: { n: number; sum: number; share: Figure } | null;
}

const fmtMn = (v: number) => nf().format(v);
/** 순위 구간 합 → 비중 수치 (계산 추적 포함) */
function shareFigure(report: ReportDoc, total: Figure, id: string, label: string, sum: number, sumLabel: string): Figure {
  return derivedFigure({
    id,
    label,
    value: ((sum / (total.value as number)) * 100),
    unit: "PCT",
    decimals: SHARE_DECIMALS,
    expression: `${sumLabel} ÷ 전체 충당금 × 100`,
    inputs: [
      { key: `${id}_sum`, label: sumLabel, value: fmtMn(sum), unit: "백만원", source: `${RANK_CHART} 표` },
      { key: total.id, label: total.label, value: fmtMn(total.value as number), unit: "백만원", source: total.id },
    ],
    asOf: report.asOf,
    from: [total],
  });
}

/** 보고서 → 화면 모델. 전체 충당금이 없거나 0 이거나 순위 행이 없으면 null */
export function provisionModel(report: ReportDoc): ProvisionModel | null {
  const total = figureByKey(report, PROVISION_KEYS.total);
  if (!total || typeof total.value !== "number" || !(total.value > 0)) return null;
  const count = figureByKey(report, PROVISION_KEYS.count);
  const rank = chartByTitle(report, RANK_CHART);
  const tail = chartByTitle(report, TAIL_CHART);
  const pts = (c: typeof rank) => (c?.series[0]?.points ?? []).filter((p): p is { label: string; value: number } => typeof p.value === "number" && Number.isFinite(p.value));
  const merged = new Map<string, number>();
  for (const p of pts(rank)) merged.set(p.label, p.value);
  const countN = typeof count?.value === "number" ? Math.round(count.value) : null;
  // 하위 표를 더해 전체를 덮을 때만 합친다 — 덮지 못하면 상위 표만(순위가 끊기지 않게)
  const withTail = new Map(merged);
  for (const p of pts(tail)) if (!withTail.has(p.label)) withTail.set(p.label, p.value);
  const pool = countN !== null && withTail.size >= countN ? withTail : merged;
  if (pool.size === 0) return null;
  const t = total.value;
  const sorted = [...pool.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], "ko"));
  let run = 0;
  const rows: ProvisionRow[] = sorted.map(([name, value], i) => {
    run += value;
    return { rank: i + 1, name, value, eok: Math.round(value / MN_PER_EOK), share: (value / t) * 100, cum: (run / t) * 100 };
  });
  const n = countN ?? rows.length;
  const complete = rows.length >= n;
  const sumTo = (k: number) => rows.slice(0, k).reduce((a, r) => a + r.value, 0);
  const bands: ProvisionBand[] = [];
  let from = 1;
  for (const end of BAND_ENDS) {
    if (from > n) break;
    const to = Math.min(end, n);
    if (rows.length < to) break;
    const sum = sumTo(to) - sumTo(from - 1);
    const label = from === 1 ? `상위 ${from}–${to}위` : `${from}–${to}위`;
    bands.push({ key: `${from}-${to}`, label, from, to, sum, share: shareFigure(report, total, `prov_band_${from}_${to}`, `${from}–${to}위 충당금 비중`, sum, `${from}–${to}위 충당금 합`) });
    from = to + 1;
  }
  const last = BAND_ENDS[BAND_ENDS.length - 1];
  if (n > last && rows.length >= last && bands.length === BAND_ENDS.length) {
    const sum = t - sumTo(last);
    const rest = n - last;
    bands.push({ key: "rest", label: `나머지 ${rest}개`, from: last + 1, to: n, sum, share: shareFigure(report, total, "prov_band_rest", `나머지 ${rest}개 상품 충당금 비중`, sum, `전체 충당금 − 상위 ${last}개 합`) });
  }
  const cumulative = BAND_ENDS.filter((k) => k <= n && k <= rows.length).map((k) => ({ n: k, share: rows[k - 1].cum }));
  const hit = rows.find((r) => r.cum >= HALF_SHARE);
  const half = hit ? { n: hit.rank, sum: sumTo(hit.rank), share: shareFigure(report, total, "prov_half_share", `상위 ${hit.rank}개 상품 비중`, sumTo(hit.rank), `상위 ${hit.rank}개 충당금 합`) } : null;
  return { total, count, top1: figureByKey(report, PROVISION_KEYS.top1), top1Share: figureByKey(report, PROVISION_KEYS.top1Share), n, rows, complete, bands, cumulative, half };
}

/* ── 형식 ─────────────────────────────────────────────────── */
/** 백만원 → 억원 글자 '1,981' */
export function eokText(mn: number | null | undefined): string {
  if (typeof mn !== "number" || !Number.isFinite(mn)) return NO_VALUE;
  return nf().format(Math.round(mn / MN_PER_EOK));
}
/** 백만원 → { '3조 4,122', '억원' } · 조가 없으면 '9,800' · 억 자리가 0 이면 '3조' */
export function joEokParts(mn: number): { value: string; unit: string } {
  const eok = Math.round(mn / MN_PER_EOK);
  const jo = Math.floor(eok / EOK_PER_JO);
  const rest = eok % EOK_PER_JO;
  if (jo === 0) return { value: nf().format(rest), unit: "억원" };
  if (rest === 0) return { value: `${nf().format(jo)}조`, unit: "원" };
  return { value: `${nf().format(jo)}조 ${nf().format(rest)}`, unit: "억원" };
}
/** 백만원 → '3조 4,122억원' */
export function joEokText(mn: number | null | undefined): string {
  if (typeof mn !== "number" || !Number.isFinite(mn)) return NO_VALUE;
  const p = joEokParts(mn);
  return `${p.value}${p.unit}`;
}
/** 기준일 '2026-08' → '2026.08' · '2026-08-31' → '2026.08.31' */
export function asOfDots(asOf: string | null | undefined): string {
  if (!asOf) return NO_VALUE;
  return asOf.slice(0, 10).replace(/-/g, ".");
}
/** 각주 기준일 — 월 기준 '2026-08' 은 그 달 말일 '2026.08.31'(달력 사실) · 일 기준은 그대로 · 형식이 다르면 asOfDots */
export function asOfDayDots(asOf: string | null | undefined): string {
  if (!asOf) return NO_VALUE;
  const m = /^(\d{4})-(\d{2})$/.exec(asOf.trim());
  if (!m) return asOfDots(asOf);
  const year = Number(m[1]);
  const month = Number(m[2]);
  if (month < 1 || month > 12) return asOfDots(asOf);
  // Date.UTC(y, month, 0) = 다음 달 0일 = 이 달 말일
  const lastDay = new Date(Date.UTC(year, month, 0)).getUTCDate();
  return `${m[1]}.${m[2]}.${String(lastDay).padStart(2, "0")}`;
}

/* ── 순위 막대 · 절반 구분선 (화면 규칙) ───────────────────── */
/** 막대 폭 % — 값이 0 · 없음이면 null(막대 없이 '0' 표시) · 1위 막대 = room × 100% */
export function rankBarWidth(value: number | null | undefined, max: number, room: number): number | null {
  if (typeof value !== "number" || !Number.isFinite(value) || value <= 0 || !(max > 0)) return null;
  return (value / max) * room * 100;
}
/** 이 행 뒤에 '누적 절반' 점선을 긋는가 — 칸 끝 행이면 칸 경계가 구분선이라 긋지 않는다 */
export function halfDividerAfter(rank: number, half: number | null, columnLastRank: number): boolean {
  return half !== null && half === rank && rank !== columnLastRank;
}

/** 비중 글자 '50.3' */
export function pct1(v: number | null | undefined): string {
  if (typeof v !== "number" || !Number.isFinite(v)) return NO_VALUE;
  return nf(SHARE_DECIMALS).format(v);
}

/* ── 의견 문장 ───────────────────────────────────────────── */
/** 규칙 경로(render.default_statement)가 만든 문장인가 — '{제목} — 라벨 [[fig:…]], ….' */
export function isRuleStatement(op: Pick<Insight, "title" | "statement">): boolean {
  return op.statement.startsWith(`${op.title} — `);
}
/** 규칙 문장 대신 보일 해요체 결론 · 해설 — 숫자는 모두 모델 값. 절반 순위가 없으면 headline null */
export function provisionOpinion(model: ProvisionModel, severity: Severity): { headline: string | null; body: string } {
  const top = model.rows[0];
  const topName = top?.name ?? NO_VALUE;
  const topShare = model.top1Share?.value ?? top?.share ?? null;
  const shareText = `${pct1(topShare)}%`;
  const k = model.half;
  const headline = k ? `${nf().format(model.n)}개 상품 중 상위 ${k.n}개가 충당금의 절반(${pct1(k.share.value)}%)을 차지해요` : null;
  const tailNote = "이번 분석은 한 시점 비교라 늘고 있는지는 아직 알 수 없어요.";
  if (severity === "info") {
    const group = k ? model.rows.slice(0, k.n) : [];
    const floor = (eok: number) => nf().format(Math.floor(eok / RANGE_STEP_EOK) * RANGE_STEP_EOK);
    const range = group.length ? `${floor(Math.min(...group.map((r) => r.eok)))}억~${floor(Math.max(...group.map((r) => r.eok)))}억원대로` : "";
    const second = k && range ? ` 대신 상위 ${k.n}개가 ${range} 촘촘하게 몰려 있어서, 개별 상품보다 이 묶음 전체를 함께 지켜보는 편이 좋아요.` : "";
    return { headline, body: `1위인 ${topName}도 비중이 ${shareText}라, 한 상품에 쏠린 구조는 아니에요.${second} ${tailNote}` };
  }
  const group = k ? ` 이 상품을 따로 지켜보면서 상위 ${k.n}개 묶음도 함께 보는 편이 좋아요.` : " 이 상품을 따로 지켜보는 편이 좋아요.";
  return { headline, body: `1위인 ${topName} 비중이 ${shareText}로, 한 상품에 충당금이 쏠려 있어요.${group} ${tailNote}` };
}
