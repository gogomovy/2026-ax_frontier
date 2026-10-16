/**
 * 영업점 1단계 가점 확보 방안 카드의 '근거 보기' 펼침 내용 (시안 358:130).
 * 가이드 요약에 나온 지점 수치와 같은 전행 수치(비교 막대) + 분석 보고서의 후보 기업 · 대상 상품(알약).
 */
import { branchBankPair, findTable, stripCorp } from "./analysisReport";
import type { BranchKpiAlert, Figure, ReportDoc } from "./types";

/** 알약을 이 개수까지 보이고 나머지는 '+N곳' */
export const MAX_CHIPS = 5;
/** 표 열 키 — 후보 기업 · 소매 Pool */
const PROSPECT_KEYS = ["corp", "grade"];
const POOL_KEYS = ["pool", "name", "seomin"];
/** 서민금융으로 인정되는 Pool 표기 */
const RECOGNIZED = "인정";

export interface GuideBasis {
  compare: { label: string; ours: Figure; bank: Figure } | null;
  chips: { title: string; items: string[]; overflow: number; unit: string } | null;
}

/** 보고서가 없거나 보일 내용이 없으면 null (기존 근거 목록을 보인다) */
export function guideBasis(alert: Pick<BranchKpiAlert, "summary">, report: ReportDoc | null): GuideBasis | null {
  if (!report) return null;
  const pair = branchBankPair(alert.summary, report.figures);
  const compare = pair ? { label: pair.ours.label.replace(/^지점\s*/, ""), ours: pair.ours, bank: pair.bank } : null;
  let chips: GuideBasis["chips"] = null;
  const prospects = findTable(report, PROSPECT_KEYS);
  const pool = findTable(report, POOL_KEYS);
  if (prospects && prospects.rows.length > 0) {
    const items = prospects.rows.map((r) => `${stripCorp(String(r.corp ?? ""))} ${String(r.grade ?? "")}`.trim());
    const head = (prospects.caption ?? "").split(" — ")[0] || "후보 기업";
    chips = { title: `${head} ${items.length}곳`, items: items.slice(0, MAX_CHIPS), overflow: Math.max(0, items.length - MAX_CHIPS), unit: "곳" };
  } else if (pool) {
    const items = pool.rows.filter((r) => String(r.seomin) === RECOGNIZED).map((r) => String(r.name ?? ""));
    if (items.length > 0) chips = { title: "대상 상품", items: items.slice(0, MAX_CHIPS), overflow: Math.max(0, items.length - MAX_CHIPS), unit: "개" };
  }
  if (!compare && !chips) return null;
  return { compare, chips };
}
