/**
 * 2단계 분석 결과 화면(시안 346 · 348 · 350 · 352)이 보고서 문서(ReportDoc)에서 값을 꺼내 쓰는 순수 함수.
 * 화면 숫자 · 글은 모두 보고서의 표 · 수치 · 목록에서 오고, 여기서는 찾고 · 나누고 · 읽기 쉽게 다듬기만 한다.
 */
import { formatFigure } from "./format";
import { toPoliteSentence } from "./sentence";
import type { Figure, ReportDoc, ReportSection, ReportTableBlock, Severity } from "./types";

/** 탭 이름 줄이기 — 앞의 원 숫자(①)를 빼고 ' · ' 로 나눈 마지막 조각만 ('핵심사업 · 우량기업여신' → '우량기업여신') */
export function shortTabLabel(label: string): string {
  const plain = label.replace(/^[\u2460-\u2473\u24f5-\u24fe\u2776-\u277f]\s*/, "").trim();
  const parts = plain.split(" · ");
  return (parts[parts.length - 1] ?? plain).trim() || plain;
}

/** 표 칸 글자 → 숫자 ('8,204' · '+6,750' · '150%' · '-24.0' · '−1.2' · '0.45'). 빈 값 · '-' 는 null */
export function num(v: string | number | null | undefined): number | null {
  if (v === null || v === undefined) return null;
  if (typeof v === "number") return Number.isFinite(v) ? v : null;
  const t = v.replace(/,/g, "").replace(/\u2212/g, "-").replace(/%p?$/, "").replace(/^\+/, "").trim();
  if (t === "" || t === "-") return null;
  const n = Number(t);
  return Number.isFinite(n) ? n : null;
}

/** 단위로 볼 괄호 말 */
const UNIT_WORDS = new Set(["억원", "백만원", "조원", "%", "%p", "건", "점"]);
/** 표 머리 '자산총계(억원)' → { text: '자산총계', unit: '억원' } · '업종(중분류)' → { text: '업종', qualifier: '중분류' } */
export function labelParts(label: string): { text: string; unit: string | null; qualifier: string | null } {
  const m = /^(.*?)\s*\(([^()]*)\)\s*$/.exec(label);
  if (!m) return { text: label.trim(), unit: null, qualifier: null };
  const inner = m[2].trim();
  return UNIT_WORDS.has(inner) ? { text: m[1].trim(), unit: inner, qualifier: null } : { text: m[1].trim(), unit: null, qualifier: inner };
}

/** 표 칸 뒤에 붙일 짧은 단위 ('억원' → '억') */
export function shortUnit(unit: string | null | undefined): string {
  if (!unit) return "";
  return unit === "억원" ? "억" : unit;
}

/** 보고서의 모든 표 (섹션 순서대로) */
export function tables(report: ReportDoc): { sectionId: string; block: ReportTableBlock }[] {
  return report.sections.flatMap((s) => s.blocks.filter((b) => b.type === "table" && b.table).map((b) => ({ sectionId: s.id, block: b.table as ReportTableBlock })));
}

/** 열 키를 모두 가진 첫 표 */
export function findTable(report: ReportDoc, keys: string[]): ReportTableBlock | null {
  return tables(report).find((t) => keys.every((k) => t.block.columns.some((c) => c.key === k)))?.block ?? null;
}

/** 섹션 찾기 */
export function sectionById(report: ReportDoc, id: string): ReportSection | null {
  return report.sections.find((s) => s.id === id) ?? null;
}

/** 섹션의 목록 항목 (여러 목록이면 이어서) */
export function listItems(section: ReportSection | null | undefined): string[] {
  return (section?.blocks ?? []).flatMap((b) => (b.type === "ul" ? (b.items ?? []) : []));
}

/** 섹션의 이름-값 항목 */
export function kvOf(section: ReportSection | null | undefined): { label: string; value: string; term?: string }[] {
  return (section?.blocks ?? []).flatMap((b) => (b.type === "kv" ? (b.kv ?? []) : []));
}

/** 섹션의 첫 표 · 첫 그래프 · 강조 글 */
export function tableOf(section: ReportSection | null | undefined): ReportTableBlock | null {
  return section?.blocks.find((b) => b.type === "table" && b.table)?.table ?? null;
}
export function chartOf(section: ReportSection | null | undefined) {
  return section?.blocks.find((b) => b.type === "chart" && b.chart)?.chart ?? null;
}
export function calloutOf(section: ReportSection | null | undefined): string | null {
  return section?.blocks.find((b) => b.type === "callout")?.text ?? null;
}

/** 글 안 수치 표식 [[fig:ID]] 의 ID (나온 순서) */
export function figureIds(text: string): string[] {
  return [...text.matchAll(/\[\[fig:([a-zA-Z0-9_-]+)\]\]/g)].map((m) => m[1]);
}

/** 글에 나온 첫 지점 수치(br_X) 와 짝이 되는 전행 수치(bank_X) */
export function branchBankPair(text: string, figures: Record<string, Figure>): { ours: Figure; bank: Figure } | null {
  for (const id of figureIds(text)) {
    if (!id.startsWith("br_")) continue;
    const ours = figures[id];
    const bank = figures[`bank_${id.slice(3)}`];
    if (ours && bank) return { ours, bank };
  }
  return null;
}

/** '(주)' · '㈜' · '주식회사' 빼기 */
export function stripCorp(name: string): string {
  return name.replace(/\(주\)|㈜|주식회사/g, "").replace(/\s+/g, " ").trim();
}

/** 상세 데이터 줄 제목 — 앞 번호('1.' · '2.1' · '①')를 빼고 ' — ' 를 ' · ' 로 ('2.1 등급 분포 및 PSI' → '등급 분포 및 PSI') */
export function detailTitle(text: string): string {
  return text
    .replace(/^\s*(?:\d+(?:\.\d+)*\.?|[①-⑳])\s*/, "")
    .replace(/\s+—\s+/g, " · ")
    .trim();
}

/** 나란한 표 제목 — 모든 제목이 같은 앞말(' — ' 앞)을 가지면 그 앞말과 표별 뒷말, 아니면 null */
export function sharedCaption(captions: (string | null | undefined)[]): { title: string; parts: string[] } | null {
  const split = captions.map((c) => {
    const i = (c ?? "").indexOf(" — ");
    return i > 0 ? { head: (c ?? "").slice(0, i).trim(), tail: (c ?? "").slice(i + 3).trim() } : null;
  });
  if (split.length < 2 || split.some((s) => !s) || split.some((s) => s!.head !== split[0]!.head)) return null;
  return { title: split[0]!.head, parts: split.map((s) => s!.tail) };
}

/** 근거 문서 칸 — 이름의 ' — ' 앞은 제목, 뒤는 보조 말 (없으면 문서 쪽 · 데이터 요약) */
export function evidenceParts(e: { label: string; snippet?: string; doc?: { title?: string; page?: number | string | null } }): { title: string; sub: string | null } {
  const i = e.label.indexOf(" — ");
  if (i > 0) return { title: e.label.slice(0, i).trim(), sub: e.label.slice(i + 3).trim() };
  if (e.doc?.title && e.doc.title !== e.label) return { title: e.label, sub: `${e.doc.title}${e.doc.page ? ` · ${e.doc.page}p` : ""}` };
  return { title: e.label, sub: e.snippet?.trim() || null };
}

/** 끝의 괄호 말 빼기 ('충당금 증가 허용액 (시뮬레이션 가정)' → '충당금 증가 허용액') */
export function stripTrailingParen(text: string): string {
  return text.replace(/\s*\([^()]*\)\s*$/, "").trim();
}

/** 심각도 글자('주의') → 심각도 — 화면의 심각도 글자표를 거꾸로 */
export function severityFromText(text: string, labels: Record<Severity, string>): Severity | null {
  const hit = (Object.keys(labels) as Severity[]).find((k) => labels[k] === text.trim());
  return hit ?? null;
}

/** 한글 음절에 받침이 있는가 */
function hasBatchim(ch: string): boolean {
  const code = ch.charCodeAt(0) - 0xac00;
  return code >= 0 && code <= 11171 && code % 28 !== 0;
}

/** 해요체로 다듬고 끝 마침표를 뺀다. '…[[fig:X]]입니다' 는 수치 글자의 받침으로 '이에요/예요' 를 고른다 */
export function politeTitle(text: string, figures?: Record<string, Figure>): string {
  const t = text.replace(/\s+/g, " ").trim().replace(/[.!?。]+$/, "");
  const m = /^(.*\[\[fig:([a-zA-Z0-9_-]+)\]\])입니다$/.exec(t);
  if (m) {
    const f = figures?.[m[2]];
    const last = f ? formatFigure(f).slice(-1) : "";
    return `${m[1]}${last && !hasBatchim(last) ? "예요" : "이에요"}`;
  }
  return toPoliteSentence(t).replace(/\.$/, "");
}

/**
 * 목록 한 줄 → 제목 · 설명 (영업 유의사항 · 관리방안)
 *  (a) ' — ' 가 있으면 뒤가 제목, 앞이 설명
 *  (b) 첫 문장(…다. / …요.) 뒤에 글이 더 있으면 첫 문장이 제목, 나머지가 설명
 *  (c) 끝에 '(…)' 가 붙으면 앞이 제목, 괄호 안이 설명
 *  (d) 그 밖에는 제목만
 */
export function splitGuideItem(text: string, figures?: Record<string, Figure>): { title: string; detail: string | null } {
  const t = text.replace(/\s+/g, " ").trim();
  const dash = t.indexOf(" — ");
  if (dash > 0) return { title: politeTitle(t.slice(dash + 3), figures), detail: politeTitle(t.slice(0, dash), figures) };
  const sentence = /^(.+?[다요]\.)\s+(\S.*)$/.exec(t);
  if (sentence) return { title: politeTitle(sentence[1], figures), detail: politeTitle(sentence[2], figures) };
  const paren = /^(.+?)\s*\(([^()]+)\)\s*\.?$/.exec(t);
  if (paren) return { title: politeTitle(paren[1], figures), detail: paren[2].trim() };
  return { title: politeTitle(t, figures), detail: null };
}
