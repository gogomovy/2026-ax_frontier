"use client";

import { useState } from "react";
import clsx from "clsx";
import { DeltaFigure, FigureText } from "@/components/data/FigureText";
import { IconSort } from "@/components/ui/icons";
import { ScrollRegion } from "@/components/ui/ScrollRegion";
import type { ComparisonRow } from "@/lib/types";

/**
 * 현재 / 전년 / 전전년 / 증감액 / 증감률 5열 비교표 (요구사항 LOAN-03)
 * 헤더는 neutral/50, 강조할 행은 primary/50 + Bold, 증감률 머리글을 눌러 정렬할 수 있다. 컨테이너 폭은 고정하고 스크롤바 자리를 미리 잡는다(scrollbar-gutter).
 */
export function ComparisonTable({
  rows,
  unitLabel,
  positiveIsGood = true,
  highlight,
  sortable = false,
}: {
  rows: ComparisonRow[];
  unitLabel: string;
  positiveIsGood?: boolean;
  /** true 를 돌려주는 행을 강조 */
  highlight?: (row: ComparisonRow) => boolean;
  sortable?: boolean;
}) {
  const [dir, setDir] = useState<"none" | "asc" | "desc">("none");
  const sorted =
    dir === "none" ? rows : [...rows].sort((a, b) => ((a.diffRate.value ?? 0) - (b.diffRate.value ?? 0)) * (dir === "asc" ? 1 : -1));
  const head = "whitespace-nowrap px-3 py-2.5 text-right text-[12px] font-bold text-steel";

  return (
    <ScrollRegion label={`비교표 · 단위 ${unitLabel}`} className="overflow-x-auto [scrollbar-gutter:stable]">
      <table className="w-full min-w-[560px] border-collapse text-[14px]">
        <caption className="sr-only">단위 {unitLabel} · 8월 누계/말 기준</caption>
        <thead>
          <tr className="bg-surface-soft">
            <th scope="col" className="rounded-l-md px-3 py-2.5 text-left text-[12px] font-bold text-steel">
              구분
            </th>
            <th scope="col" className={head}>
              2026.08
            </th>
            <th scope="col" className={head}>
              2025.08
            </th>
            <th scope="col" className={head}>
              2024.08
            </th>
            <th scope="col" className={head}>
              증감액
            </th>
            <th scope="col" className={clsx(head, "rounded-r-md")} aria-sort={dir === "none" ? "none" : dir === "asc" ? "ascending" : "descending"}>
              {sortable ? (
                <button
                  type="button"
                  onClick={() => setDir((d) => (d === "none" ? "desc" : d === "desc" ? "asc" : "none"))}
                  className="inline-flex items-center gap-1 font-bold hover:text-ink-deep"
                  aria-label="증감률로 정렬"
                >
                  증감률
                  <IconSort className={dir === "none" ? "text-icon" : "text-primary"} />
                </button>
              ) : (
                "증감률"
              )}
            </th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((row) => {
            const on = highlight?.(row);
            const cell = clsx("whitespace-nowrap border-b border-hairline-soft px-3 py-3.5 text-right", on && "bg-info-faint");
            return (
              <tr key={row.label}>
                <th scope="row" className={clsx("border-b border-hairline-soft px-3 py-3.5 text-left", on ? "bg-info-faint font-bold text-ink-deep" : "font-bold text-ink-deep")}>
                  {row.label}
                </th>
                <td className={cell}>
                  <FigureText figure={row.current} strong plain />
                </td>
                <td className={clsx(cell, "text-steel")}>
                  <FigureText figure={row.prior} plain className="!font-medium !text-steel" />
                </td>
                <td className={clsx(cell, "text-steel")}>{row.prior2 ? <FigureText figure={row.prior2} plain className="!font-medium !text-steel" /> : "-"}</td>
                <td className={cell}>
                  <DeltaFigure figure={row.diff} positiveIsGood={positiveIsGood} plain />
                </td>
                <td className={cell}>
                  <DeltaFigure figure={row.diffRate} positiveIsGood={positiveIsGood} plain />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </ScrollRegion>
  );
}
