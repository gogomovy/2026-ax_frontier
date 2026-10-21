/**
 * 데이터 책임자 승인함(§40 STW) — 에이전트 제안(분석 화면 · 추적 지표 · 개념 연결 · 온톨로지 변경)과 부서 사용자 분석 요청을 묶고 표시 글자를 만든다.
 * 값 · 이름 · 단위는 모두 서버 응답에서 오고, 여기서는 묶음 · 정렬 · 표기만 한다.
 */
import { UNIT_LABEL } from "./format";
import type { Figure } from "./types";

export type ProposalKind = "analysis" | "metric" | "concept" | "ontology";
export type ProposalStatus = "pending" | "approved" | "rejected" | "superseded";

export interface PreviewFigure {
  id: string;
  label?: string | null;
  value?: number | string | null;
  unit?: string | null;
  stale?: boolean | null;
}

export interface ProposalItem {
  kind: ProposalKind;
  id: string;
  status: ProposalStatus;
  canReview: boolean;
  dataset?: string | null;
  datasetName?: string | null;
  // 분석 화면
  agent?: string;
  version?: number;
  title?: string;
  purpose?: string;
  auto?: boolean;
  by?: string | null;
  periods?: number | null;
  space?: string;
  spaceLabel?: string;
  spaceLocked?: boolean;
  metrics?: { key: string; label: string; formula: string; unit: string }[];
  tables?: { key: string; caption: string }[];
  preview?: { figures: PreviewFigure[]; opinions: { id?: string; severity?: string; statement?: string }[] };
  issues?: string[];
  sourceText?: string;
  requestedBy?: string;
  requestedByName?: string | null;
  createdAt?: string | null;
  reviewedByName?: string | null;
  reviewedAt?: string | null;
  reviewNote?: string | null;
  href?: string | null;
  // 추적 지표
  code?: string;
  label?: string;
  formula?: string;
  unit?: string;
  reason?: string | null;
  // 개념 연결
  labelKo?: string;
  key?: string;
  name?: string;
  score?: number | null;
  evidence?: string[];
  note?: string | null;
  decidedAt?: string | null;
  // 온톨로지 변경
  pid?: number;
  summary?: string;
  source?: string;
  datasets?: { code: string; name: string }[];
  /** 링크가 잇는 기존 객체 유형의 원천 자료 */
  linkedDatasets?: { code: string; name: string }[];
  scoped?: boolean;
  ops?: OntologyOpItem[];
  opCount?: number;
  impact?: OntologyImpact;
  warnings?: string[];
  baseVersion?: number | null;
  appliedVersion?: number | null;
  createdBy?: string | null;
  createdByName?: string | null;
  decidedBy?: string | null;
  decidedByName?: string | null;
}

export interface OntologyOpItem {
  op: Record<string, unknown> & { op: string };
  key: string;
  why?: string | null;
  confidence?: number | null;
  by?: string | null;
}

export interface OntologyImpact {
  nodes?: Record<string, { before: number; after: number }>;
  relations?: Record<string, { before: number; after: number }>;
  dangling?: Record<string, number>;
  nodesDelta?: number;
  relationsDelta?: number;
  error?: string;
}

export interface ProposalsData {
  scope: { code: string | null; name: string } | null;
  admin: boolean;
  items: ProposalItem[];
  counts: { analysis: number; metric: number; concept: number; ontology?: number; total: number };
  spaces: { key: string; label: string }[];
}

export const KIND_LABEL: Record<ProposalKind, string> = { analysis: "분석 화면", metric: "추적 지표", concept: "개념 연결", ontology: "온톨로지 변경" };

/** 제안이 닿는 자료 이름 — 온톨로지 변경은 여러 자료일 수 있다 */
export function itemDatasetName(it: ProposalItem): string {
  return it.datasetName ?? (it.datasets ?? []).map((d) => d.name || d.code).join(", ");
}

function signed(n: number): string {
  return `${n > 0 ? "+" : ""}${new Intl.NumberFormat("ko-KR").format(n)}`;
}

/** 적용하면 그래프가 어떻게 바뀌는지 — '개체 +12 · 관계 +30 · 끊긴 관계 2' (계산 실패면 그 사실을) */
export function impactText(imp?: OntologyImpact | null): string {
  if (!imp) return "–";
  if (imp.error) return "영향 계산 실패";
  const dangling = Object.values(imp.dangling ?? {}).reduce((a, b) => a + (Number(b) || 0), 0);
  const parts = [
    typeof imp.nodesDelta === "number" ? `개체 ${signed(imp.nodesDelta)}` : "",
    typeof imp.relationsDelta === "number" ? `관계 ${signed(imp.relationsDelta)}` : "",
    dangling ? `끊긴 관계 ${new Intl.NumberFormat("ko-KR").format(dangling)}` : "",
  ].filter(Boolean);
  return parts.length ? parts.join(" · ") : "–";
}
export const STATUS_LABEL: Record<ProposalStatus, string> = { pending: "승인 대기", approved: "승인", rejected: "반려", superseded: "이전 버전" };

/** 미리 계산한 값 — 정수면 소수 없이, 아니면 2자리 · 단위 붙임. 값이 없거나 갱신 실패면 '–' */
export function previewValue(f: PreviewFigure): string {
  const n = typeof f.value === "number" ? f.value : typeof f.value === "string" && f.value.trim() !== "" ? Number(f.value) : NaN;
  if (f.stale || !Number.isFinite(n)) return "–";
  const decimals = Number.isInteger(n) ? 0 : 2;
  const body = new Intl.NumberFormat("ko-KR", { minimumFractionDigits: decimals, maximumFractionDigits: decimals }).format(n);
  const unit = (UNIT_LABEL as Record<string, string>)[(f.unit ?? "NONE") as Figure["unit"]] ?? "";
  return `${body}${unit}`;
}

/** 종류별로 나눈다 — 분석 화면 · 추적 지표 · 개념 연결 · 온톨로지 변경 순, 각 종류 안에서는 처리할 것(승인 가능) 먼저 · 자료 이름 순 */
export function groupByKind(items: ProposalItem[]): { kind: ProposalKind; items: ProposalItem[] }[] {
  const order: ProposalKind[] = ["analysis", "metric", "concept", "ontology"];
  return order
    .map((kind) => ({
      kind,
      items: items
        .filter((i) => i.kind === kind)
        .slice()
        .sort((a, b) => Number(b.canReview) - Number(a.canReview) || itemDatasetName(a).localeCompare(itemDatasetName(b), "ko")),
    }))
    .filter((g) => g.items.length > 0);
}

/** 개념 연결 점수(0~1) → 백분율 글자 */
export function scoreText(score?: number | null): string {
  return typeof score === "number" && Number.isFinite(score) ? `${Math.round(score * 100)}%` : "–";
}

/** 반려 사유 점검 — 두 글자 이상 */
export function reasonError(v: string): string | null {
  return v.trim().length < 2 ? "사유를 두 글자 이상 입력하세요" : null;
}
