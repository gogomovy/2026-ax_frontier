"use client";

import { useState, type ReactNode } from "react";
import { IconTable } from "@/components/ui/icons";
import { DataTable, Td } from "@/components/ui/primitives";

export interface ChartTable {
  columns: { key: string; label: string; align?: "left" | "right" }[];
  rows: Record<string, ReactNode>[];
}

/**
 * 차트 카드 — 제목 · 범례 · 우측 [표 보기] · 하단 기준(기간 · 단위).
 * 모든 차트는 같은 데이터를 표로 바꿔 볼 수 있다 (UX-07).
 */
export function ChartCard({
  title,
  legend,
  caption,
  table,
  children,
  className,
}: {
  title: string;
  legend?: { label: string; color: string; dashed?: boolean; muted?: boolean; dot?: boolean }[];
  caption?: ReactNode;
  table: ChartTable;
  children: ReactNode;
  className?: string;
}) {
  const [asTable, setAsTable] = useState(false);
  return (
    <figure className={`flex min-w-0 flex-col rounded-xl border border-hairline-soft bg-canvas p-6 ${className ?? ""}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <figcaption className="text-[16px] font-bold leading-[1.4] text-ink-deep">{title}</figcaption>
          {legend?.length ? (
            <ul className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px] text-steel">
              {legend.map((l) => (
                <li key={l.label} className="inline-flex items-center gap-1.5">
                  {l.dot ? (
                    <span aria-hidden="true" className="inline-block h-2 w-2 rounded-circle" style={{ background: l.color }} />
                  ) : (
                    <span
                      aria-hidden="true"
                      className="inline-block h-0 w-4 border-t-2"
                      style={{ borderColor: l.color, borderStyle: l.dashed ? "dashed" : "solid", opacity: l.muted ? 0.6 : 1 }}
                    />
                  )}
                  {l.label}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
        <button
          type="button"
          onClick={() => setAsTable((v) => !v)}
          aria-pressed={asTable}
          className="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-md border border-hairline-soft bg-canvas px-3 text-[12px] font-bold text-ink-deep hover:bg-surface-soft no-print"
        >
          <IconTable />
          {asTable ? "차트 보기" : "표 보기"}
        </button>
      </div>

      <div className="mt-4 min-h-0 flex-1">
        {asTable ? (
          <DataTable dense columns={table.columns.map((c) => ({ key: c.key, label: c.label, align: c.align }))}>
            {table.rows.map((row, i) => (
              <tr key={i}>
                {table.columns.map((c, ci) => (
                  <Td key={c.key} align={c.align} strong={ci === 0}>
                    {row[c.key]}
                  </Td>
                ))}
              </tr>
            ))}
          </DataTable>
        ) : (
          children
        )}
      </div>

      {caption ? <figcaption className="mt-3 text-[12px] leading-normal text-steel">{caption}</figcaption> : null}
    </figure>
  );
}
