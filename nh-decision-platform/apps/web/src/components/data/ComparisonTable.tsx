"use client";

import { DeltaFigure, FigureText } from "@/components/data/FigureText";
import { UNIT_LABEL } from "@/lib/format";
import { NO_VALUE, periodOf } from "@/lib/period";
import type { ComparisonRow } from "@/lib/types";
import { ScrollRegion } from "@/components/ui/ScrollRegion";

/**
 * 현재 / 전년 / 전전년 / 증감액 / 증감률 5열 비교표 (요구사항 LOAN-03).
 * 열 머리(연월) · 기준 문구는 산출물 기준일(asOf)에서, 단위는 행 수치의 단위에서 정한다(Phase I).
 */
export function ComparisonTable({
  rows,
  asOf,
  unitLabel,
  positiveIsGood = true,
}: {
  rows: ComparisonRow[];
  /** 산출물 기준일 (ISO) — 없으면 열 머리를 '–' 로 */
  asOf?: string | null;
  /** 단위 라벨 — 생략하면 첫 행 수치의 단위 */
  unitLabel?: string;
  positiveIsGood?: boolean;
}) {
  const p = periodOf(asOf);
  const unit = unitLabel ?? (rows[0] ? UNIT_LABEL[rows[0].current.unit] : "");
  const basis = p.month === NO_VALUE ? `기준일 ${NO_VALUE}` : `${p.month} 누계/말 기준`;
  return (
    <ScrollRegion>
      <table className="w-full border-collapse text-[13px]">
        <caption className="mb-2 text-left text-[11.5px] text-stone">
          {unit ? `단위 ${unit} · ` : ""}
          {basis}
        </caption>
        <thead>
          <tr className="border-y border-hairline-soft bg-surface-soft">
            <th scope="col" className="px-3 py-2.5 text-left font-bold text-charcoal">
              구분
            </th>
            <th scope="col" className="whitespace-nowrap px-3 py-2.5 text-right font-bold text-charcoal">
              {p.ym}
            </th>
            <th scope="col" className="whitespace-nowrap px-3 py-2.5 text-right font-bold text-charcoal">
              {p.prevYm}
            </th>
            <th scope="col" className="whitespace-nowrap px-3 py-2.5 text-right font-bold text-charcoal">
              {p.prev2Ym}
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
          {rows.length === 0 ? (
            <tr>
              <td colSpan={6} className="border-b border-hairline-soft px-3 py-4 text-center text-[12px] text-stone">
                표시할 자료가 없습니다
              </td>
            </tr>
          ) : null}
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
    </ScrollRegion>
  );
}
