/**
 * 분석 에이전트 보고서(kind "dynamic") → 2단계 분석 결과 시안 화면(kit) 배치 — 순수 함수.
 * 보고서 블록(metrics · p · table · chart)을 화면 조각(지표 카드 · 해설 · 비교 막대 · 상세 표)으로 나눈다. 숫자 · 글은 보고서 그대로.
 */
import { UNIT_LABEL } from "./format";
import type { Figure, ReportBlock, ReportDoc, ReportSection, ReportTableBlock, Severity } from "./types";

/** 참고한 팀 데이터 절 — ReportShell 이 본문 아래에 따로 그린다 */
export const TEAM_SECTION = "sec-team";
/** 의견 상자 지표 카드 수 (시안 3칸) */
export const KPI_MAX = 3;

/** 본문으로 그릴 절 (팀 데이터 절 · 빈 절 제외) */
export function bodySections(report: ReportDoc): ReportSection[] {
  return report.sections.filter((s) => s.id !== TEAM_SECTION && s.blocks.length > 0);
}

/** 보고서에 있는 수치만 · 이름 · 값 · 단위가 같은 수치는 한 번만 (에이전트가 같은 지표를 여러 번 정의한 경우) */
export function uniqueFigureIds(ids: string[], figures: Record<string, Figure>): string[] {
  const seen = new Set<string>();
  return ids.filter((id) => {
    const f = figures[id];
    if (!f) return false;
    const k = `${f.label}|${f.value}|${f.unit}`;
    if (seen.has(k)) return false;
    seen.add(k);
    return true;
  });
}

/** 의견 상자 지표 — 첫 의견의 수치, 없으면 첫 지표 묶음. 보고서에 있는 수치만 · 최대 3개 */
export function kpiFigureIds(report: ReportDoc): string[] {
  const fromOpinion = uniqueFigureIds(Object.keys(report.opinions[0]?.figures ?? {}), report.figures);
  if (fromOpinion.length > 0) return fromOpinion.slice(0, KPI_MAX);
  const metrics = report.sections.flatMap((s) => s.blocks).find((b) => b.type === "metrics");
  return uniqueFigureIds(metrics?.figures ?? [], report.figures).slice(0, KPI_MAX);
}

export interface SectionParts {
  metrics: string[];
  texts: string[];
  charts: NonNullable<ReportBlock["chart"]>[];
  /** 같은 제목의 그래프가 없는 표 — 카드에 바로 보인다(그래프가 있으면 '근거 · 상세 데이터' 와 '표로 보기' 로) */
  tables: ReportTableBlock[];
  /** 그래프와 짝인 표 (같은 제목) */
  chartTables: ReportTableBlock[];
  /** 그 밖의 블록(목록 · 알림 · 항목 묶음) — 기존 블록 그리기로 */
  others: ReportBlock[];
}

/** 절 하나를 화면 조각으로 나눈다 */
export function sectionParts(section: ReportSection, figures: Record<string, Figure>): SectionParts {
  const out: SectionParts = { metrics: [], texts: [], charts: [], tables: [], chartTables: [], others: [] };
  const chartTitles = new Set(section.blocks.filter((b) => b.type === "chart" && b.chart).map((b) => b.chart!.title));
  for (const b of section.blocks) {
    if (b.type === "metrics") out.metrics = uniqueFigureIds([...out.metrics, ...(b.figures ?? [])], figures);
    else if (b.type === "p" && b.text) out.texts.push(b.text);
    else if (b.type === "chart" && b.chart) out.charts.push(b.chart);
    else if (b.type === "table" && b.table) (b.table.caption && chartTitles.has(b.table.caption) ? out.chartTables : out.tables).push(b.table);
    else out.others.push(b);
  }
  return out;
}

export interface BarRow {
  key: string;
  label: string;
  value: number | null;
  text: string;
  strong: boolean;
}

/** 그래프 값 글자 — 모두 정수면 소수 없이, 아니면 1자리 · 단위 붙임 */
export function barText(value: number | null, decimals: number, unit: Figure["unit"]): string {
  if (value === null || !Number.isFinite(value)) return "–";
  const body = new Intl.NumberFormat("ko-KR", { minimumFractionDigits: decimals, maximumFractionDigits: decimals }).format(value);
  const u = UNIT_LABEL[unit] ?? "";
  return `${body}${u}`;
}

/** 막대 그래프 → 비교 막대 줄(첫 계열) · 가장 큰 값 강조 */
export function barRows(chart: NonNullable<ReportBlock["chart"]>): BarRow[] {
  const points = chart.series[0]?.points ?? [];
  const vals = points.map((p) => (typeof p.value === "number" && Number.isFinite(p.value) ? p.value : null));
  const decimals = vals.every((v) => v === null || Number.isInteger(v)) ? 0 : 1;
  const max = Math.max(...vals.filter((v): v is number => v !== null), Number.NEGATIVE_INFINITY);
  let strongDone = false;
  return points.map((p, i) => {
    const v = vals[i];
    const strong = !strongDone && v !== null && v === max && max > 0;
    if (strong) strongDone = true;
    return { key: `${i}-${p.label}`, label: String(p.label), value: v, text: barText(v, decimals, chart.unit), strong };
  });
}

/** 막대로 그릴 수 있는 그래프인가 — 막대(또는 비중) · 계열 1개 · 음수 없음 (아니면 일반 그래프) */
export function isCompareChart(chart: NonNullable<ReportBlock["chart"]>): boolean {
  if (chart.kind === "line" || chart.series.length !== 1) return false;
  return chart.series[0].points.every((p) => p.value === null || (typeof p.value === "number" && p.value >= 0));
}

/** 의견 위험도 → 작은 태그 색 */
export function severityTone(s: Severity): "neutral" | "info" | "attention" | "critical" {
  return s === "critical" ? "critical" : s === "caution" ? "attention" : s === "watch" ? "info" : "neutral";
}
