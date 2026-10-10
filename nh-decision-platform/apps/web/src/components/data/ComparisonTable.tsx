"use client";

import { DeltaFigure, FigureText } from "@/components/data/FigureText";
import type { ComparisonRow } from "@/lib/types";

/** 현재 / 전년 / 전전년 / 증감액 / 증감률 5열 비교표 (요구사항 LOAN-03) */
export function ComparisonTable({
  rows,
  unitLabel,
  positiveIsGood = true,
}: {
  rows: ComparisonRow[];
  unitLabel: string;
  positiveIsGood?: boolean;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-[13px]">
        <caption className="mb-2 text-left text-[11.5px] text-stone">단위 {unitLabel} · 8월 누계/말 기준</caption>
        <thead>
          <tr className="border-y border-hairline-soft bg-surface-soft">
            <th scope="col" className="px-3 py-2.5 text-left font-bold text-charcoal">
              구분
            </th>
            <th scope="col" className="whitespace-nowrap px-3 py-2.5 text-right font-bold text-charcoal">
              2026.08
            </th>
            <th scope="col" className="whitespace-nowrap px-3 py-2.5 text-right font-bold text-charcoal">
              2025.08
            </th>
            <th scope="col" className="whitespace-nowrap px-3 py-2.5 text-right font-bold text-charcoal">
              2024.08
            </th>
            <th scope="col" className="whitespace-nowrap px-3 py-2.5 text-right font-bold text-charcoal">
              증감액
            </th>
            <th scope="col" className="whitespace-nowrap px-3 py-2.5 text-right font-bold text-charcoal">
              증감률
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.label}>
              <th scope="row" className="border-b border-hairline-soft px-3 py-2.5 text-left font-bold text-ink-deep">
                {row.label}
              </th>
              <td className="whitespace-nowrap border-b border-hairline-soft px-3 py-2.5 text-right">
                <FigureText figure={row.current} strong />
              </td>
              <td className="whitespace-nowrap border-b border-hairline-soft px-3 py-2.5 text-right text-charcoal">
                <FigureText figure={row.prior} />
              </td>
              <td className="whitespace-nowrap border-b border-hairline-soft px-3 py-2.5 text-right text-charcoal">
                {row.prior2 ? <FigureText figure={row.prior2} /> : "-"}
              </td>
              <td className="whitespace-nowrap border-b border-hairline-soft px-3 py-2.5 text-right">
                <DeltaFigure figure={row.diff} positiveIsGood={positiveIsGood} />
              </td>
              <td className="whitespace-nowrap border-b border-hairline-soft px-3 py-2.5 text-right">
                <DeltaFigure figure={row.diffRate} positiveIsGood={positiveIsGood} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
