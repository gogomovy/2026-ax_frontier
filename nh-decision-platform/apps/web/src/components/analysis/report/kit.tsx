"use client";
/**
 * 2단계 분석 결과 화면 공용 조각 (시안 346 · 348 · 350 · 352) — 영업점 · 신용리스크관리부가 같이 쓴다.
 * Agent 의견 상자 · 전후 숫자 · 섹션 카드 · 그래프 틀 · 묶음 막대 · 비교 막대 · 쌓인 진행 막대 · 유의사항 · 근거 · 상세 데이터 · 보고서 다운로드.
 * 숫자 · 글은 모두 보고서 문서에서 오고, 여기서는 그리기만 한다.
 */
import { useEffect, useId, useRef, useState, type CSSProperties, type ReactNode } from "react";
import clsx from "clsx";
import { OnDemandAnalysis } from "@/components/agent/AgentProgress";
import { RichText } from "@/components/data/RichText";
import { politeNode, toPoliteText } from "@/lib/sentence";
import { Fig, TAG_TONE, type Tone } from "@/components/domain/overviewKit";
import { TermText } from "@/components/data/TermText";
import { ToolButton } from "@/components/layout/PageTools";
import { useUi } from "@/components/providers/UiProvider";
import { IconChevronDown, IconSparkle } from "@/components/ui/icons";
import { IconCheck, IconChevron, IconDownload } from "@/components/ui/primitives";
import { detailTitle, evidenceParts, politeTitle, sharedCaption } from "@/lib/analysisReport";
import { api } from "@/lib/api-client";
import { derivedFigure } from "@/lib/derived";
import { UNIT_LABEL, formatSignedValue, formatValue } from "@/lib/format";
import { NO_VALUE } from "@/lib/period";
import { downloadServerReport, EXPORT_FORMAT_LABEL } from "@/lib/reportExport";
import type { Evidence, Figure, Insight, ReportBlock, ReportDoc, ReportSection, ReportTableBlock } from "@/lib/types";

/* ── 공통 ─────────────────────────────────────────────────── */
/** 숫자 표기 — 소수 자리 고정 */
export function fmtNum(n: number | null | undefined, decimals = 0, signed = false): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return NO_VALUE;
  const body = new Intl.NumberFormat("ko-KR", { minimumFractionDigits: decimals, maximumFractionDigits: decimals }).format(Math.abs(n));
  const sign = n < 0 ? "-" : signed && n > 0 ? "+" : "";
  return `${sign}${body}`;
}
/** 수치 글자 — 없으면 '–'. unit 을 주면 그 단위로 ('' = 단위 없음) */
export function figText(f: Figure | null | undefined, unit?: string, signed = false): string {
  if (!f || f.value === null || f.value === undefined) return NO_VALUE;
  return `${signed ? formatSignedValue(f) : formatValue(f)}${unit ?? UNIT_LABEL[f.unit]}`;
}
/** 두 수치의 합 · 비율 같은 화면 파생 수치 — 입력이 없으면 null (계산 추적 포함) */
export function combine(args: { id: string; label: string; inputs: (Figure | null | undefined)[]; calc: (v: number[]) => number; expression: string; unit: Figure["unit"]; decimals?: number; asOf: string }): Figure | null {
  const ins = args.inputs;
  if (ins.some((f) => !f || f.value === null || f.value === undefined)) return null;
  const vals = ins.map((f) => f!.value as number);
  return derivedFigure({
    id: args.id,
    label: args.label,
    value: args.calc(vals),
    unit: args.unit,
    decimals: args.decimals,
    expression: args.expression,
    inputs: ins.map((f) => ({ key: f!.id, label: f!.label, value: formatValue(f!), unit: UNIT_LABEL[f!.unit], source: f!.id })),
    asOf: args.asOf,
    from: ins,
  });
}
/** 값이 없을 때 — 회색 '–' */
export function NoValue({ className }: { className?: string }) {
  return <span className={clsx("tnum font-bold text-steel", className)}>{NO_VALUE}</span>;
}
/** 섹션 · 상자 안 글자 링크 — 13px · primary/700 · › */
export const TEXT_LINK = "inline-flex shrink-0 items-center gap-0.5 rounded-sm text-[13px] font-medium leading-[1.4] text-primary-deep hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary";
/** 작은 판정 태그 — 11px Bold (KPI 카드 · 표 · 특이사항) */
export function MiniTag({ tone, children, className }: { tone: Tone; children: ReactNode; className?: string }) {
  return <span className={clsx("inline-flex h-[18px] shrink-0 items-center whitespace-nowrap rounded-pill px-[7px] text-[11px] font-bold leading-none", TAG_TONE[tone], className)}>{children}</span>;
}
/** 막대 등장 순서 */
const order = (i: number) => ({ ["--i" as string]: i }) as CSSProperties;

/* ── Agent 의견 ───────────────────────────────────────────── */
export interface KpiCardItem {
  key: string;
  label: ReactNode;
  /** 이름 옆 보조 말 (PSI · AR 하락률) */
  qualifier?: ReactNode;
  tag?: ReactNode;
  value: ReactNode;
  sub?: ReactNode;
}
/** Agent 의견 — 옅은 보라 판: 배지(· 다시 분석) → 결론 → 해설 → 전후 숫자 카드 → 오른쪽 아래 근거 보기 (시안 346:59) */
export function AgentOpinionBox({
  opinion,
  headline,
  evidence,
  evidenceTitle,
  rerun,
  kpis,
  connectors,
}: {
  opinion: Insight;
  headline: string;
  evidence: Evidence[];
  evidenceTitle: string;
  rerun?: string | null;
  kpis: KpiCardItem[];
  /** 카드 사이 → (판정 단계 순서) */
  connectors?: boolean;
}) {
  const { openDrawer } = useUi();
  return (
    <section aria-label="Agent 의견" className="rounded-[10px] bg-info-soft px-6 pb-6 pt-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span className="inline-flex h-[23px] items-center gap-1 rounded-pill bg-canvas px-2 text-[12px] font-bold text-primary-deep">
          <IconSparkle size={12} className="h-3 w-3 shrink-0" />
          Agent 의견
        </span>
        {rerun ? <OnDemandAnalysis workflow={rerun} variant="link" /> : null}
      </div>
      <h2 className="mt-3 text-[18px] font-bold leading-[1.3] text-ink-deep">{toPoliteText(headline)}</h2>
      <RichText text={toPoliteText(opinion.statement)} figures={opinion.figures} className="mt-2 max-w-[1120px] text-[13px] leading-[1.6] text-slate" />
      <dl className={clsx("mt-5 grid grid-cols-1 gap-3", connectors ? "lg:grid-cols-[1fr_auto_1fr_auto_1fr_auto_1fr] lg:items-stretch lg:gap-x-2" : "md:grid-cols-3")}>
        {kpis.map((k, i) => (
          <KpiCardCell key={k.key} item={k} arrow={connectors && i > 0} />
        ))}
      </dl>
      {evidence.length > 0 ? (
        <div className="mt-3 flex justify-end">
          <button type="button" className={TEXT_LINK} onClick={() => openDrawer({ kind: "evidence", title: evidenceTitle, items: evidence, statement: headline })}>
            근거 {evidence.length}건 보기
            <IconChevron className="h-3 w-3" />
          </button>
        </div>
      ) : null}
    </section>
  );
}
function KpiCardCell({ item, arrow }: { item: KpiCardItem; arrow?: boolean }) {
  return (
    <>
      {arrow ? (
        <span aria-hidden="true" className="hidden items-center justify-center text-icon lg:flex">
          <svg viewBox="0 0 16 16" width="14" height="14">
            <path d="M3 8h10m0 0L9 4m4 4-4 4" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </span>
      ) : null}
      <div className="flex min-w-0 flex-col rounded-lg bg-canvas px-4 pb-3.5 pt-3">
        <dt className="flex items-center justify-between gap-2">
          <span className="flex min-w-0 items-baseline gap-1.5">
            <span className="truncate text-[12px] font-medium leading-[1.4] text-steel">{item.label}</span>
            {item.qualifier ? <span className="truncate text-[11px] leading-[1.4] text-steel">{item.qualifier}</span> : null}
          </span>
          {item.tag}
        </dt>
        <dd className="mt-1.5">{item.value}</dd>
        {item.sub ? <dd className="tnum mt-1 text-[11px] leading-[1.4] text-steel">{item.sub}</dd> : null}
      </div>
    </>
  );
}

/** 전 → 후 숫자 (전: 회색 · 후: primary/700 + 단위) — 누르면 계산 추적 */
export function BeforeAfter({ before, after, unit }: { before?: Figure | null; after?: Figure | null; unit?: string }) {
  const u = unit ?? (after ? UNIT_LABEL[after.unit] : "");
  return (
    <p className="flex flex-wrap items-baseline gap-x-2">
      {before ? <Fig figure={before} size={22} valueClass="text-steel" unitLabel="" /> : <NoValue className="text-[22px]" />}
      <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" className="self-center text-steel">
        <path d="M3 8h10m0 0L9 4m4 4-4 4" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      {after ? (
        <span className="inline-flex items-baseline gap-1">
          <Fig figure={after} size={22} valueClass="text-primary-deep" unitLabel="" />
          {u && after.value !== null ? <span className="text-[12px] font-bold text-primary-deep">{u}</span> : null}
        </span>
      ) : (
        <NoValue className="text-[22px]" />
      )}
    </p>
  );
}

/* ── 섹션 카드 · 그래프 틀 ───────────────────────────────── */
/** 흰 카드 — 제목 18px(기본 · 시안이 16px 인 보고서는 titleSize={16}) + 12px 보조 말 · 오른쪽 링크 */
export function SectionCard({ id, title, hint, right, children, className, titleSize = 18 }: { id?: string; title: ReactNode; hint?: ReactNode; right?: ReactNode; children: ReactNode; className?: string; titleSize?: 16 | 18 }) {
  const auto = useId();
  const headId = id ? `${id}-title` : auto;
  return (
    <section id={id} aria-labelledby={headId} className={clsx("min-w-0 scroll-mt-[88px] rounded-[10px] border border-hairline-soft bg-canvas px-6 pb-6 pt-5", className)}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <div className="flex min-w-0 flex-wrap items-baseline gap-x-2.5 gap-y-1">
          <h2 id={headId} className={clsx("font-bold leading-[1.4] text-ink-deep", titleSize === 16 ? "text-[16px]" : "text-[18px]")}>
            {title}
          </h2>
          {hint ? <p className="tnum text-[12px] leading-[1.4] text-steel">{hint}</p> : null}
        </div>
        {right ? <div className="flex shrink-0 items-center gap-3">{right}</div> : null}
      </div>
      <div className="mt-4">{children}</div>
    </section>
  );
}
/** 두 칸 나눔 — 가운데 세로 구분선 */
export function TwoColumns({ children, ratio }: { children: ReactNode; ratio?: "half" | "wide-left" }) {
  return (
    <div className={clsx("grid grid-cols-1 gap-y-8 lg:gap-x-6", ratio === "wide-left" ? "lg:grid-cols-[minmax(0,1.9fr)_1px_minmax(0,1fr)]" : "lg:grid-cols-[minmax(0,1fr)_1px_minmax(0,1fr)]")}>
      {children}
    </div>
  );
}
export function ColumnRule() {
  return <span aria-hidden="true" className="hidden bg-track lg:block" />;
}
export interface LegendItem {
  label: string;
  swatch: string;
  /** 동그라미 · 빈 동그라미 · 선 */
  shape?: "square" | "dot" | "ring" | "line";
}
export function Legend({ items }: { items: LegendItem[] }) {
  return (
    <ul className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] leading-[1.4] text-steel">
      {items.map((l) => (
        <li key={l.label} className="inline-flex items-center gap-1.5">
          <span aria-hidden="true" className={clsx("shrink-0", l.shape === "dot" ? "h-2 w-2 rounded-circle" : l.shape === "ring" ? "h-2 w-2 rounded-circle border-[1.5px] bg-canvas" : l.shape === "line" ? "h-[2px] w-3" : "h-2.5 w-2.5 rounded-[2px]", l.swatch)} />
          {l.label}
        </li>
      ))}
    </ul>
  );
}
/** 그래프 제목 — 11px Medium · steel (시안 neutral/600) */
export const CHART_TITLE = "text-[11px] font-medium leading-[1.4] text-steel";
/** 그래프 한 칸 — 11px 제목 · 범례/보조 말 · 그림 · 12px 해설 */
export function ChartBlock({ title, right, caption, children, className }: { title: ReactNode; right?: ReactNode; caption?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <figure className={clsx("flex min-w-0 flex-col", className)}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <figcaption className={CHART_TITLE}>{title}</figcaption>
        {right ? <div className="text-[11px] leading-[1.4] text-steel">{right}</div> : null}
      </div>
      <div className="mt-4 flex-1">{children}</div>
      {caption ? <p className="tnum mt-4 text-[12px] leading-[1.5] text-slate">{politeNode(caption)}</p> : null}
    </figure>
  );
}

/* ── 그래프 ───────────────────────────────────────────────── */
/** 값이 없거나 0 인 막대 — 막대 없이 값 글자 자리에 '0' 하나만 */
export const ZERO_LABEL = "0";
/** 막대를 그릴 값인가 (없음 · 0 이 아님) */
export function isBarValue(v: number | null | undefined): v is number {
  return typeof v === "number" && Number.isFinite(v) && v !== 0;
}
/** 눈금 최댓값 — 맨 앞 자리 단위로 올림(앞 자리가 1이면 그 5분의 1 단위) · 60.1 → 70 · 48 → 50 · 151,480 → 160,000 */
export function niceMax(v: number): number {
  if (!(v > 0)) return 1;
  const mag = 10 ** Math.floor(Math.log10(v));
  const unit = v / mag < 2 ? mag / 5 : mag;
  return Math.ceil(v / unit - 1e-9) * unit;
}
/** 좁은 화면에서도 지킬 칸 너비(px) — 모자라면 그래프 안에서 가로로 넘긴다 */
const MIN_COLUMN = 64;
/** 막대 수가 이 이하이면 넓은 막대 */
const WIDE_BAR_LIMIT = 6;
export interface ColumnSeries {
  name: string;
  values: (number | null)[];
  /** 막대 색 (bg-*) */
  tone: string;
  /** 강조 칸의 막대 색 */
  strongTone?: string;
}
/** 묶음 세로 막대 — 칸마다 계열 막대 · 값 글자 · 눈금 3줄 · 강조 칸은 옅은 띠 + 굵은 이름 */
export function GroupedColumns({
  categories,
  series,
  highlight,
  footer,
  decimals = 1,
  tickUnit = "",
  tickFormat,
  height = 190,
  ariaLabel,
  strong: strongAt,
}: {
  categories: string[];
  series: ColumnSeries[];
  /** 옅은 띠 + 굵은 이름 칸 */
  highlight?: number | null;
  /** 강조 색(strongTone) 막대를 쓸 칸 — 없으면 highlight 칸 */
  strong?: number | null;
  footer?: (i: number) => ReactNode;
  decimals?: number;
  tickUnit?: string;
  tickFormat?: (v: number) => string;
  height?: number;
  ariaLabel: string;
}) {
  const all = series.flatMap((s) => s.values).filter((v): v is number => typeof v === "number");
  const max = niceMax(Math.max(0, ...all));
  const ticks = [max, max / 2, 0];
  // 칸이 적으면 막대를 넓게 (값 글자가 옆 막대와 겹치지 않게)
  const wide = categories.length * Math.max(1, series.length) <= WIDE_BAR_LIMIT;
  const tick = tickFormat ?? ((v: number) => `${fmtNum(v, Number.isInteger(v) ? 0 : 1)}${tickUnit}`);
  return (
    // 좁은 화면에서는 그래프 안에서만 가로로 넘긴다
    <div role="group" aria-label={ariaLabel} className="thin-scroll flex overflow-x-auto pt-2">
      <div className="relative w-9 shrink-0" style={{ height }} aria-hidden="true">
        {ticks.map((t, i) => (
          <span key={i} className="tnum absolute right-2 -translate-y-1/2 text-[10px] text-steel" style={{ top: `${(1 - t / max) * 100}%` }}>
            {tick(t)}
          </span>
        ))}
      </div>
      <div className="flex-1" style={{ minWidth: categories.length * MIN_COLUMN }}>
        <div className="relative" style={{ height }}>
          {ticks.map((t, i) => (
            <span key={i} aria-hidden="true" className={clsx("absolute inset-x-0 h-px", t === 0 ? "bg-chart-axis" : "bg-chart-grid")} style={{ top: `${(1 - t / max) * 100}%` }} />
          ))}
          <div className="absolute inset-0 flex">
            {categories.map((c, ci) => {
              const band = highlight === ci;
              const strong = (strongAt ?? highlight) === ci;
              return (
                <div key={c} className={clsx("relative flex flex-1 items-end justify-center px-1", wide ? "gap-2" : "gap-1.5", band && "rounded-t-lg bg-info-faint")}>
                  {series.map((s, si) => {
                    const v = s.values[ci];
                    const has = isBarValue(v);
                    const h = has ? Math.max(0, (v / max) * 100) : 0;
                    return (
                      <div key={s.name} className={clsx("relative flex h-full w-full flex-col justify-end", wide ? "max-w-[56px]" : "max-w-[29px]")}>
                        <span className={clsx("tnum mb-1 whitespace-nowrap text-center text-[11px] leading-none", strong && s.strongTone ? "font-bold text-primary-deep" : "text-steel")}>{has ? fmtNum(v, decimals) : ZERO_LABEL}</span>
                        {has ? (
                          <span
                            className={clsx("block w-full origin-bottom rounded-t-[3px] motion-safe:animate-grow-y", strong && s.strongTone ? s.strongTone : s.tone)}
                            style={{ height: `${h}%`, minHeight: 1, ...order(ci) }}
                          />
                        ) : null}
                      </div>
                    );
                  })}
                </div>
              );
            })}
          </div>
        </div>
        <div className="flex">
          {categories.map((c, ci) => (
            <div key={c} className={clsx("flex flex-1 flex-col items-center gap-1 px-1 pb-1 pt-1.5", highlight === ci && "rounded-b-lg bg-info-faint")}>
              <span className={clsx("text-center text-[11px] leading-[1.3]", highlight === ci ? "font-bold text-primary-deep" : "font-medium text-ink-deep")}>{c}</span>
              {footer ? footer(ci) : null}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/** 비교 막대가 쓰는 폭(나머지는 값 글자 자리) */
const BAR_ROOM = 0.82;
export interface CompareRow {
  key: string;
  label: ReactNode;
  value: number | null;
  /** 값 글자 */
  text: ReactNode;
  strong?: boolean;
  /** 막대 색 (strong 이 아닐 때) */
  tone?: string;
}
/** 가로 비교 막대 — 같은 눈금(가장 큰 값 = 끝). 강조 줄은 primary + 굵은 값, 나머지는 회색 + steel 값 */
export function CompareBars({ rows, max, labelWidth = 88, thickness = 8, i0 = 0, hideLabels }: { rows: CompareRow[]; max?: number; labelWidth?: number; thickness?: number; i0?: number; hideLabels?: boolean }) {
  const top = max ?? Math.max(0, ...rows.map((r) => r.value ?? 0));
  return (
    <ul className="flex flex-col gap-2">
      {rows.map((r, i) => {
        const has = isBarValue(r.value);
        const w = top > 0 && has ? Math.max(0, Math.min(100, ((r.value as number) / top) * 100)) : 0;
        return (
          <li key={r.key} className="flex items-center gap-3">
            {hideLabels ? (
              <span className="sr-only">{r.label}</span>
            ) : (
              <span className={clsx("shrink-0 truncate text-[12px] leading-[1.4]", r.strong ? "font-bold text-primary-deep" : "text-steel")} style={{ width: labelWidth }}>
                {r.label}
              </span>
            )}
            <span className="flex min-w-0 flex-1 items-center gap-2">
              {has ? (
                <span
                  className={clsx("block shrink-0 origin-left rounded-pill motion-safe:animate-grow-x", r.strong ? "bg-primary" : (r.tone ?? "bg-hairline-soft"))}
                  style={{ width: `${w * BAR_ROOM}%`, height: thickness, ...order(i0 + i) }}
                />
              ) : null}
              <span className={clsx("tnum shrink-0 whitespace-nowrap text-[12px]", r.strong ? "font-bold text-primary-deep" : "text-steel")}>{has ? r.text : ZERO_LABEL}</span>
            </span>
          </li>
        );
      })}
    </ul>
  );
}

/** 쌓인 진행 막대 — 현재(회색) + 더할 몫(옅은 보라) / 만점, 아래에 세 글자 */
export function StackProgress({ now, add, max, leftLabel, addLabel, rightLabel }: { now: number | null; add: number | null; max: number | null; leftLabel: ReactNode; addLabel: ReactNode; rightLabel: ReactNode }) {
  const pct = (v: number | null) => (typeof v === "number" && max ? Math.max(0, Math.min(100, (v / max) * 100)) : 0);
  const nowPct = pct(now);
  const addPct = Math.min(100 - nowPct, pct(add));
  return (
    <div>
      <div className="relative h-2 overflow-hidden rounded-pill bg-track" role="presentation">
        <span className="absolute inset-y-0 left-0 origin-left bg-slate motion-safe:animate-grow-x" style={{ width: `${nowPct}%` }} />
        <span className="absolute inset-y-0 origin-left bg-info-line motion-safe:animate-grow-x" style={{ left: `${nowPct}%`, width: `${addPct}%`, ...order(1) }} />
      </div>
      <div className="tnum relative mt-1.5 h-4 text-[11px] leading-4 text-steel">
        <span className="absolute left-0">{leftLabel}</span>
        <span className="absolute -translate-x-1/2 whitespace-nowrap font-medium text-primary-deep" style={{ left: `${nowPct + addPct / 2}%` }}>
          {addLabel}
        </span>
        <span className="absolute right-0">{rightLabel}</span>
      </div>
    </div>
  );
}

/* ── 목록 ─────────────────────────────────────────────────── */
export interface GuideLine {
  key: string;
  title: string;
  detail: string | null;
}
/** 확인 목록 — 2열, 체크 동그라미 · 14px 제목 · 12px 설명 */
export function ChecklistGrid({ items, figures }: { items: GuideLine[]; figures: Record<string, Figure> }) {
  return (
    <ul className="grid grid-cols-1 gap-x-10 gap-y-5 md:grid-cols-2">
      {items.map((it) => (
        <li key={it.key} className="flex items-start gap-2.5">
          <span aria-hidden="true" className="mt-[2px] flex h-4 w-4 shrink-0 items-center justify-center rounded-circle bg-info-soft text-primary">
            <IconCheck className="h-2.5 w-2.5" />
          </span>
          <div className="min-w-0">
            <RichText text={it.title} figures={figures} className="text-[14px] font-bold leading-[1.4] text-ink-deep" />
            {it.detail ? <RichText text={it.detail} figures={figures} className="mt-1 text-[12px] leading-[1.5] text-steel" /> : null}
          </div>
        </li>
      ))}
    </ul>
  );
}
/** 번호 목록 — 가로 3칸 (관리방안) */
export function NumberedGrid({ items, figures }: { items: GuideLine[]; figures: Record<string, Figure> }) {
  return (
    <ol className="grid grid-cols-1 gap-x-8 gap-y-5 md:grid-cols-3">
      {items.map((it, i) => (
        <li key={it.key} className="flex items-start gap-2.5">
          <span aria-hidden="true" className="tnum mt-[1px] flex h-5 w-5 shrink-0 items-center justify-center rounded-circle bg-info-soft text-[11px] font-bold text-primary-deep">
            {i + 1}
          </span>
          <div className="min-w-0">
            <RichText text={it.title} figures={figures} className="text-[14px] font-bold leading-[1.4] text-ink-deep" />
            {it.detail ? <RichText text={it.detail} figures={figures} className="mt-1 text-[12px] leading-[1.5] text-steel" /> : null}
          </div>
        </li>
      ))}
    </ol>
  );
}

/* ── 근거 · 상세 데이터 ───────────────────────────────────── */
const OPEN_EVENT = "report-detail-open";
/** 다른 곳(후보 전체 명세 ›)에서 상세 데이터 줄 하나를 펼치고 그 줄로 이동 */
export function openDetailRow(sectionId: string) {
  window.dispatchEvent(new CustomEvent(OPEN_EVENT, { detail: sectionId }));
}
const EVIDENCE_ROW = "__evidence";
/** 표 한 칸이 지킬 너비(px) — 표는 칸 수만큼만 넓어지고 카드 폭을 넘지 않는다 */
const DETAIL_COLUMN = 120;
/** 합계 줄 첫 칸 글자 */
const TOTAL_ROW = "합계";
/** 상세 데이터 한 줄 — 보고서 섹션에서 무엇을 보일지 (시안 380 · 381 · 383 근거 펼침) */
export interface DetailRowSpec {
  /** 보고서 섹션 id */
  section: string;
  /** 줄 제목 — heading: 섹션 제목(기본) · caption: 표 제목 */
  title?: "heading" | "caption";
  /** 보일 표(섹션 안 표 순서) — 없으면 모두. 둘 이상이고 제목 앞말이 같으면 나란히 */
  tables?: number[];
  /** 항목 묶음(kv) — 기본 보임 · steps: 단계 사슬(1단계 → 2단계 → 3단계) · false: 안 보임 */
  kv?: boolean | "steps";
  /** 알림 상자(callout)를 아래 주석으로 — 기본 보임 */
  notes?: boolean;
  /** 강조 행에서 주의 색으로 칠할 칸 — 없으면 강조 행 전체를 옅은 바탕 + 굵게 */
  attentionKeys?: string[];
}
interface DetailRow {
  key: string;
  spec: DetailRowSpec;
  title: string;
  section: ReportSection;
  tables: ReportTableBlock[];
  /** 나란한 표의 표별 보조 제목 */
  parts: string[] | null;
  kv: NonNullable<ReportBlock["kv"]>;
  notes: string[];
}
function buildRows(report: ReportDoc, specs: DetailRowSpec[]): DetailRow[] {
  const rows: DetailRow[] = [];
  for (const spec of specs) {
    const section = report.sections.find((s) => s.id === spec.section);
    if (!section) continue;
    const all = section.blocks.filter((b) => b.type === "table" && b.table).map((b) => b.table as ReportTableBlock);
    const tables = spec.tables ? spec.tables.map((i) => all[i]).filter((t): t is ReportTableBlock => Boolean(t)) : all;
    const kv = spec.kv === false ? [] : section.blocks.filter((b) => b.type === "kv").flatMap((b) => b.kv ?? []);
    const notes = spec.notes === false ? [] : section.blocks.filter((b) => b.type === "callout" && b.text).map((b) => b.text as string);
    if (tables.length === 0 && kv.length === 0) continue;
    const shared = tables.length > 1 ? sharedCaption(tables.map((t) => t.caption)) : null;
    const title = shared ? shared.title : spec.title === "caption" && tables[0]?.caption ? tables[0].caption : section.heading;
    rows.push({ key: `${spec.section}#${spec.tables?.join(",") ?? "all"}`, spec, title: detailTitle(title), section, tables, parts: shared?.parts ?? null, kv, notes });
  }
  return rows;
}
/** 근거 · 상세 데이터 — 보고서 표 · 항목 묶음을 줄마다 펼치고, 근거 문서는 2열 칸. 기본은 모두 접힘 · 접힌 내용도 인쇄에는 나온다 */
export function DetailAccordion({ report, rows: specs }: { report: ReportDoc; rows: DetailRowSpec[] }) {
  const { openDrawer } = useUi();
  const rows = buildRows(report, specs);
  const keys = [...rows.map((r) => r.key), ...(report.evidence.length > 0 ? [EVIDENCE_ROW] : [])];
  const [open, setOpen] = useState<Set<string>>(new Set());
  const allOpen = keys.length > 0 && keys.every((k) => open.has(k));
  const base = useId();
  const toggle = (k: string) =>
    setOpen((cur) => {
      const next = new Set(cur);
      if (next.has(k)) next.delete(k);
      else next.add(k);
      return next;
    });
  useEffect(() => {
    const onOpen = (e: Event) => {
      const id = (e as CustomEvent<string>).detail;
      const r = rows.find((x) => x.spec.section === id);
      if (!r) return;
      setOpen((cur) => new Set(cur).add(r.key));
      window.setTimeout(() => document.getElementById(`detail-${r.spec.section}`)?.scrollIntoView({ behavior: "smooth", block: "start" }), 30);
    };
    window.addEventListener(OPEN_EVENT, onOpen);
    return () => window.removeEventListener(OPEN_EVENT, onOpen);
  });
  // 같은 섹션이 두 줄로 나뉘면 이동 위치(id)는 첫 줄에만
  const anchored = new Set<string>();
  return (
    <SectionCard
      title="근거 · 상세 데이터"
      hint="보고서 원문의 표와 근거 문서"
      right={
        <button type="button" className={clsx(TEXT_LINK, "no-print")} onClick={() => setOpen(allOpen ? new Set() : new Set(keys))}>
          {allOpen ? "모두 접기" : "모두 펼치기"}
          <IconChevronDown size={12} className={clsx("transition-transform", allOpen && "rotate-180")} />
        </button>
      }
    >
      <ul>
        {rows.map((r) => {
          const on = open.has(r.key);
          const panel = `${base}-${r.key}`;
          const anchor = anchored.has(r.spec.section) ? undefined : `detail-${r.spec.section}`;
          anchored.add(r.spec.section);
          return (
            <li key={r.key} id={anchor} className="scroll-mt-[88px] border-t border-track">
              <AccordionHead on={on} panel={panel} onClick={() => toggle(r.key)}>
                {r.title}
              </AccordionHead>
              <div id={panel} className={clsx("flex-col gap-3 pb-5", on ? "flex" : "hidden print:flex")}>
                <DetailBody row={r} report={report} />
              </div>
            </li>
          );
        })}
        {report.evidence.length > 0 ? (
          <li className="border-t border-track">
            <AccordionHead on={open.has(EVIDENCE_ROW)} panel={`${base}-ev`} onClick={() => toggle(EVIDENCE_ROW)}>
              근거 문서 {report.evidence.length}건
            </AccordionHead>
            <ul id={`${base}-ev`} className={clsx("grid-cols-1 gap-x-6 gap-y-2 pb-5 md:grid-cols-2", open.has(EVIDENCE_ROW) ? "grid" : "hidden print:grid")}>
              {report.evidence.map((e) => {
                const p = evidenceParts(e);
                const isDoc = e.sourceKind === "doc_chunk" || e.sourceKind === "external";
                return (
                  <li key={e.id} className="min-w-0">
                    <button
                      type="button"
                      onClick={() => openDrawer({ kind: "evidence", title: `${report.title} 근거`, items: report.evidence, selectedId: e.id })}
                      className="flex h-full w-full items-center gap-3 rounded-md bg-page px-3 py-2.5 text-left hover:bg-surface-soft focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                    >
                      <span className={clsx("inline-flex h-[17px] shrink-0 items-center rounded-pill px-[6px] text-[10px] font-bold leading-none", isDoc ? "bg-info-soft text-primary-deep" : "bg-track text-slate")}>{isDoc ? "문서" : "데이터"}</span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-[11px] font-medium leading-[1.4] text-ink-deep">{p.title}</span>
                        {p.sub ? <span className="block truncate text-[10px] leading-[1.4] text-steel">{p.sub}</span> : null}
                      </span>
                      <span className="inline-flex shrink-0 items-center gap-0.5 text-[11px] font-medium text-primary-deep">
                        원문 보기
                        <IconChevron className="h-2.5 w-2.5" />
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </li>
        ) : null}
      </ul>
    </SectionCard>
  );
}
function AccordionHead({ on, panel, onClick, children }: { on: boolean; panel: string; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      aria-expanded={on}
      aria-controls={panel}
      onClick={onClick}
      className={clsx(
        "flex w-full items-center justify-between gap-3 py-3 text-left text-[14px] leading-[1.4] text-ink-deep hover:text-primary-deep focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary",
        on ? "font-bold" : "font-medium",
      )}
    >
      <span className="min-w-0">{children}</span>
      <IconChevronDown size={14} className={clsx("shrink-0 text-steel transition-transform", on && "rotate-180")} />
    </button>
  );
}
/** 펼친 줄 내용 — 항목 묶음(2열 칸 · 단계 사슬) → 표(나란히 가능) + 표 주석 → 알림 주석 */
function DetailBody({ row, report }: { row: DetailRow; report: ReportDoc }) {
  const f = report.figures;
  const steps = row.spec.kv === "steps";
  return (
    <>
      {row.kv.length > 0 && steps ? (
        <ol className="grid grid-cols-1 gap-2 lg:auto-cols-fr lg:grid-flow-col">
          {row.kv.map((k, i) => (
            <li key={k.label} className="flex min-w-0 items-center gap-2">
              {i > 0 ? (
                <svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true" className="hidden shrink-0 text-icon lg:block">
                  <path d="M3 8h10m0 0L9 4m4 4-4 4" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              ) : null}
              <div className="min-w-0 flex-1 rounded-md bg-page px-3 py-2">
                <p className="text-[10px] font-bold leading-[1.4] text-primary-deep">{k.label.replace(/^\[|\]$/g, "")}</p>
                <RichText text={k.value} figures={f} className="mt-0.5 text-[11px] font-bold leading-[1.4] text-ink-deep" />
              </div>
            </li>
          ))}
        </ol>
      ) : row.kv.length > 0 ? (
        <dl className="grid grid-cols-1 gap-x-6 gap-y-2 md:grid-cols-2">
          {row.kv.map((k) => (
            <div key={k.label} className="flex min-h-[34px] items-center gap-3 rounded-md bg-page px-3 py-2">
              <dt className="w-[116px] shrink-0 text-[11px] font-medium leading-[1.4] text-steel">{k.term ? <TermText code={k.term} label={k.label} /> : k.label}</dt>
              <dd className="min-w-0 text-[11px] font-medium leading-[1.4] text-ink-deep">
                <RichText as="span" text={k.value} figures={f} />
              </dd>
            </div>
          ))}
        </dl>
      ) : null}
      {row.tables.length > 0 ? (
        <div className={clsx("grid grid-cols-1 gap-6", row.parts && "lg:grid-cols-2")}>
          {row.tables.map((t, i) => (
            <div key={i} className="min-w-0">
              {row.parts ? <p className="mb-2 text-[11px] font-medium leading-[1.4] text-steel">{row.parts[i]}</p> : null}
              <DetailTable table={t} attentionKeys={row.spec.attentionKeys} fill={Boolean(row.parts)} />
              {t.note ? <RichText text={t.note} figures={f} className="mt-2 text-[10px] leading-[1.5] text-steel" /> : null}
            </div>
          ))}
        </div>
      ) : null}
      {row.notes.map((n, i) => (
        <RichText key={i} text={politeTitle(n.replace(/\s+—\s+/g, " · "), f)} figures={f} className="text-[10px] leading-[1.5] text-steel" />
      ))}
    </>
  );
}
/** 상세 표 — 옅은 머리줄 · 1px 행 구분 · 강조 행(옅은 바탕 + 굵게, 또는 지정 칸만 주의 색) · 합계 행 굵게 */
export function DetailTable({ table: t, attentionKeys, fill }: { table: ReportTableBlock; attentionKeys?: string[]; fill?: boolean }) {
  const first = t.columns[0]?.key;
  return (
    <div className="thin-scroll overflow-x-auto">
      <table className={clsx("tnum border-separate border-spacing-0 text-[11px] leading-[1.4]", fill ? "w-full" : "w-auto")} style={fill ? undefined : { minWidth: `min(100%, ${t.columns.length * DETAIL_COLUMN}px)` }}>
        {t.caption ? <caption className="sr-only">{t.caption}</caption> : null}
        <thead>
          <tr>
            {t.columns.map((c, ci) => (
              <th
                key={c.key}
                scope="col"
                className={clsx(
                  "whitespace-nowrap bg-surface-soft px-2.5 py-1.5 text-[10px] font-bold text-steel",
                  c.align === "right" ? "text-right" : "text-left",
                  ci === 0 && "rounded-l-md",
                  ci === t.columns.length - 1 && "rounded-r-md",
                )}
              >
                {c.term ? <TermText code={c.term} label={c.label} /> : c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {t.rows.map((row, ri) => {
            const hl = Boolean(t.highlightRowKey && String(row[t.highlightRowKey]) === String(t.highlightRowValue));
            const total = first ? String(row[first] ?? "").trim() === TOTAL_ROW : false;
            const rowStrong = (hl && !attentionKeys) || total;
            return (
              <tr key={ri} className={clsx(hl && !attentionKeys && "bg-page")}>
                {t.columns.map((c) => {
                  const v = row[c.key];
                  const warm = hl && attentionKeys?.includes(c.key);
                  return (
                    <td
                      key={c.key}
                      className={clsx(
                        "whitespace-nowrap border-b border-track px-2.5 py-1.5",
                        c.align === "right" ? "text-right" : "text-left",
                        warm ? "font-bold text-attention" : rowStrong ? "font-bold text-ink-deep" : "text-ink-deep",
                      )}
                    >
                      {v === null || v === undefined || v === "" ? <span className="text-steel">{NO_VALUE}</span> : String(v)}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/* ── 보고서 다운로드 (서버 변환 형식) ─────────────────────── */
/** 탭 줄 오른쪽 '보고서 다운로드' — 관리자가 켠 형식만 메뉴에 보인다 */
export function ReportDownload({ tabKey, office }: { tabKey: string; office?: string | null }) {
  const { showToast } = useUi();
  const [formats, setFormats] = useState<string[] | null>(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    api<string[]>("/reports/formats")
      .then(setFormats)
      .catch(() => setFormats([]));
  }, []);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey, true);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey, true);
    };
  }, [open]);
  const download = (format: string) => {
    setOpen(false);
    setBusy(true);
    downloadServerReport(tabKey, format, office)
      .then((fileName) => showToast(`보고서를 내려받았습니다 — ${fileName}`))
      .catch((e: Error) => showToast(`보고서를 내려받지 못했습니다 — ${e.message}`))
      .finally(() => setBusy(false));
  };
  const usable = Boolean(formats && formats.length > 0);
  return (
    <div ref={box} className="relative no-print" data-report-export>
      <ToolButton icon={<IconDownload />} onClick={usable && !busy ? () => setOpen((v) => !v) : undefined} data-tool="report-download">
        {busy ? "변환 중…" : "보고서 다운로드"}
      </ToolButton>
      {open && formats && formats.length > 0 ? (
        <ul aria-label="내려받을 형식" className="absolute right-0 z-30 mt-1 min-w-[160px] overflow-hidden rounded-xl border border-hairline bg-canvas py-1 shadow-pop">
          {formats.map((f) => (
            <li key={f}>
              <button type="button" data-format={f} className="block w-full px-4 py-2 text-left text-[13px] hover:bg-surface-soft focus-visible:bg-surface-soft" onClick={() => download(f)}>
                {EXPORT_FORMAT_LABEL[f] ?? f.toUpperCase()}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
