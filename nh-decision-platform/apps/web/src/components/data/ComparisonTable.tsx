"use client";
import { useState } from "react";
import clsx from "clsx";
import { DeltaFigure, FigureText } from "@/components/data/FigureText";
import { IconSort } from "@/components/ui/icons";
import { ScrollRegion } from "@/components/ui/ScrollRegion";
import { UNIT_LABEL } from "@/lib/format";
import { NO_VALUE, periodOf } from "@/lib/period";
import type { ComparisonRow } from "@/lib/types";

/**
 * 현재 / 전년 / 전전년 / 증감액 / 증감률 5열 비교표 (요구사항 LOAN-03)
 * 열 머리(연월) · 기준 문구는 산출물 기준일(asOf)에서, 단위는 행 수치의 단위에서 정한다(Phase I · 하드코딩 없음).
 * 헤더는 neutral/50, 강조할 행은 primary/50 + Bold, 증감률 머리글을 눌러 정렬할 수 있다. 컨테이너 폭은 고정하고 스크롤바 자리를 미리 잡는다(scrollbar-gutter).
 */
export function ComparisonTable({
  rows,
  asOf,
  unitLabel,
  positiveIsGood = true,
  highlight,
  sortable = false,
}: {
  rows: ComparisonRow[];
  /** 산출물 기준일 (ISO) — 없으면 열 머리를 '–' 로 */
  asOf?: string | null;
  /** 단위 라벨 — 생략하면 첫 행 수치의 단위 */
  unitLabel?: string;
  positiveIsGood?: boolean;
  /** true 를 돌려주는 행을 강조 */
  highlight?: (row: ComparisonRow) => boolean;
  sortable?: boolean;
}) {
  const [dir, setDir] = useState<"none" | "asc" | "desc">("none");
  const p = periodOf(asOf);
  const unit = unitLabel ?? (rows[0] ? UNIT_LABEL[rows[0].current.unit] : "");
  const basis = p.month === NO_VALUE ? `기준일 ${NO_VALUE}` : `${p.month} 누계/말 기준`;
  const sorted =
    dir === "none" ? rows : [...rows].sort((a, b) => ((a.diffRate.value ?? 0) - (b.diffRate.value ?? 0)) * (dir === "asc" ? 1 : -1));
  const head = "whitespace-nowrap px-3 py-2.5 text-right text-[12px] font-bold text-steel";
  return (
    <ScrollRegion label={`비교표${unit ? ` · 단위 ${unit}` : ""}`} className="overflow-x-auto [scrollbar-gutter:stable]">
      <table className="w-full min-w-[560px] border-collapse text-[14px]">
        <caption className="sr-only">
          {unit ? `단위 ${unit} · ` : ""}
          {basis}
        </caption>
        <thead>
          <tr className="bg-surface-soft">
            <th scope="col" className="rounded-l-md px-3 py-2.5 text-left text-[12px] font-bold text-steel">
              구분
            </th>
            <th scope="col" className={head}>
              {p.ym}
            </th>
            <th scope="col" className={head}>
              {p.prevYm}
            </th>
            <th scope="col" className={head}>
              {p.prev2Ym}
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
          {sorted.length === 0 ? (
            <tr>
              <td colSpan={6} className="border-b border-hairline-soft px-3 py-4 text-center text-[12px] text-steel">
                표시할 자료가 없습니다
              </td>
            </tr>
          ) : null}
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
