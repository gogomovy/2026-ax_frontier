import type { CalcTrace, Evidence, Figure, Verification } from "@/lib/types";

export const AS_OF = process.env.NEXT_PUBLIC_AS_OF ?? "2026-08-31";
export const GENERATED_AT = `${AS_OF.slice(0, 10)}T06:22:00+09:00`;
export const BATCH_LABEL = "일배치 precompute_p1_dashboard / precompute_p2_risk";

/** 목데이터 수치 생성기. 실제 시스템에서는 calc_run / metric_value 가 이 구조를 채운다. */
export function fig(
  id: string,
  label: string,
  value: number | null,
  unit: Figure["unit"],
  opts: Partial<Omit<Figure, "id" | "label" | "value" | "unit">> = {},
): Figure {
  return {
    id,
    label,
    value,
    unit,
    dataOrigin: opts.dataOrigin ?? "simulated",
    decimals: opts.decimals,
    undefinedLabel: opts.undefinedLabel,
    calc: opts.calc,
    sourceRef: opts.sourceRef,
  };
}

export function trace(
  calcId: string,
  formulaId: string,
  expression: string,
  inputs: CalcTrace["inputs"],
  note?: string,
): CalcTrace {
  return {
    calcId,
    formulaId,
    formulaVersion: 1,
    expression,
    inputs,
    executedAt: GENERATED_AT,
    note,
  };
}

export const PASSED_VERIFICATIONS: Verification[] = [
  { checkCode: "numeric_provenance", passed: true, detail: "모든 수치가 계산 결과를 참조" },
  { checkCode: "evidence_present", passed: true, detail: "근거 3범주 충족 여부 확인" },
  { checkCode: "causality_language", passed: true, detail: "인과 단정 표현 미검출" },
];

export function withAlignment(v: Verification[], passed = true): Verification[] {
  return [...v, { checkCode: "alignment", passed, detail: passed ? "상위 기준과 정합" : "충돌 확인" }];
}

export function evidence(
  id: string,
  category: Evidence["category"],
  label: string,
  opts: Partial<Omit<Evidence, "id" | "category" | "label">> = {},
): Evidence {
  return {
    id,
    category,
    label,
    sourceKind: opts.sourceKind ?? "doc_chunk",
    snippet: opts.snippet,
    relevance: opts.relevance,
    doc: opts.doc,
    figureId: opts.figureId,
    tableRef: opts.tableRef,
  };
}

export function figMap(...figures: Figure[]): Record<string, Figure> {
  return Object.fromEntries(figures.map((f) => [f.id, f]));
}
