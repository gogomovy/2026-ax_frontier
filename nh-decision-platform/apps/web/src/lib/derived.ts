import type { CalcInputRef, Figure } from "./types";

/**
 * 화면에서 합산 · 비율로 만든 파생 수치에 계산 추적을 붙인다.
 * 모든 수치는 눌러서 수식 · 입력값 · 원천을 볼 수 있어야 하므로 (PRIN-05), 화면이 계산한 값도 같은 모양으로 만든다.
 */
export function derivedFigure(args: {
  id: string;
  label: string;
  value: number | null;
  unit: Figure["unit"];
  decimals?: number;
  expression: string;
  inputs: CalcInputRef[];
  asOf: string;
}): Figure {
  const { id, label, value, unit, decimals, expression, inputs, asOf } = args;
  return {
    id,
    label,
    value,
    unit,
    decimals,
    dataOrigin: "mixed",
    calc: {
      calcId: `calc-${id}`,
      formulaId: "DERIVED",
      formulaVersion: 1,
      expression,
      inputs,
      executedAt: asOf,
      note: "화면에서 위 입력값으로 계산한 파생 수치입니다.",
    },
  };
}

