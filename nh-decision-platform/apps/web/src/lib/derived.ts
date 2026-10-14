import type { CalcInputRef, DataOrigin, Figure } from "./types";

/**
 * 화면에서 합산 · 비율로 만든 파생 수치에 계산 추적을 붙인다.
 * 모든 수치는 눌러서 수식 · 입력값 · 원천을 볼 수 있어야 하므로 (PRIN-05), 화면이 계산한 값도 같은 모양으로 만든다.
 * 자료 성격은 입력 수치에서 물려받는다 — 모두 같으면 그 값, 섞이면 mixed, 입력이 수치가 아니면(기준월 등) unknown (Phase K · HC-05).
 * 계산 시각은 알 수 없으므로 비우고, 기준일만 남긴다.
 */
export function originOf(figures: (Figure | null | undefined)[]): DataOrigin {
  const kinds = new Set(figures.filter((f): f is Figure => Boolean(f)).map((f) => f.dataOrigin).filter((k) => k && k !== "unknown"));
  if (kinds.size === 0) return "unknown";
  if (kinds.size === 1) return [...kinds][0];
  return "mixed";
}

export function derivedFigure(args: {
  id: string;
  label: string;
  value: number | null;
  unit: Figure["unit"];
  decimals?: number;
  expression: string;
  inputs: CalcInputRef[];
  asOf: string;
  /** 입력 수치 — 자료 성격을 물려받는다 */
  from?: (Figure | null | undefined)[];
}): Figure {
  const { id, label, value, unit, decimals, expression, inputs, asOf, from = [] } = args;
  return {
    id,
    label,
    value,
    unit,
    decimals,
    dataOrigin: originOf(from),
    calc: {
      calcId: `calc-${id}`,
      formulaId: "DERIVED",
      formulaVersion: 1,
      expression,
      inputs,
      executedAt: "",
      note: `화면에서 위 입력값으로 계산한 파생 수치입니다${asOf ? ` (기준일 ${asOf})` : ""}.`,
    },
  };
}
