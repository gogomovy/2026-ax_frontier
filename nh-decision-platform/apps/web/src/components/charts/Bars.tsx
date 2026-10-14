"use client";

import clsx from "clsx";
import { useState, type CSSProperties, type ReactNode } from "react";
import { DataTable, Td } from "@/components/ui/primitives";

/*
 * 막대 시각화 (C.1 · MON-01 · Q105) — 외부 그래프 라이브러리 없이 HTML/CSS 막대로 그린다.
 * 모든 그래프는 '표로 보기' 로 같은 수치를 표로 제공한다(WCAG — 그래프만으로 정보 전달 금지).
 */

type Tone = "primary" | "success" | "attention" | "critical" | "neutral" | "info";
const BG: Record<Tone, string> = {
  primary: "bg-chart-1",
  info: "bg-primary",
  success: "bg-success",
  attention: "bg-attention",
  critical: "bg-critical",
  neutral: "bg-chart-4",
};

function TableToggle({ table, children, title }: { table: ReactNode; children: ReactNode; title: string }) {
  const [asTable, setAsTable] = useState(false);
  return (
    <figure>
      <div className="mb-2 flex items-center justify-between gap-2">
        <figcaption className="text-[12.5px] font-bold text-charcoal">{title}</figcaption>
        <button type="button" onClick={() => setAsTable((v) => !v)} aria-pressed={asTable} className="text-[11.5px] font-bold text-primary">
          {asTable ? "그래프로 보기" : "표로 보기"}
        </button>
      </div>
      {asTable ? table : children}
    </figure>
  );
}

/** 가로 막대 순위 — 값이 큰 순서로 보여 주는 목록(예: 노드별 평균 소요 · 에이전트별 토큰) */
export function BarList({ title, items, max, unit = "" }: { title: string; items: { label: ReactNode; value: number; display?: string; tone?: Tone; hint?: ReactNode }[]; max?: number; unit?: string }) {
  const top = max ?? Math.max(1, ...items.map((i) => i.value));
  const fmt = (i: (typeof items)[number]) => i.display ?? `${i.value.toLocaleString("ko-KR")}${unit}`;
  return (
    <TableToggle
      title={title}
      table={
        <DataTable dense columns={[{ key: "l", label: "항목" }, { key: "v", label: "값", align: "right" }]}>
          {items.map((i, k) => (
            <tr key={k}>
              <Td>{i.label}</Td>
              <Td align="right">{fmt(i)}</Td>
            </tr>
          ))}
        </DataTable>
      }
    >
      {items.length === 0 ? (
        <p className="text-[12px] text-stone">자료 없음</p>
      ) : (
        <ul className="flex flex-col gap-2" aria-hidden="true">
          {items.map((i, k) => (
            <li key={k} className="grid grid-cols-[minmax(0,180px)_1fr_auto] items-center gap-2 text-[12px]">
              <span className="truncate text-charcoal">{i.label}</span>
              <span className="h-2.5 overflow-hidden rounded-pill bg-surface-soft">
                <span className={clsx("block h-full origin-left rounded-pill motion-safe:animate-grow-x", BG[i.tone ?? "primary"])} style={{ width: `${Math.max(2, (i.value / top) * 100)}%`, "--i": k } as CSSProperties} />
              </span>
              <span className="tnum font-bold text-ink-deep">{fmt(i)}</span>
            </li>
          ))}
        </ul>
      )}
    </TableToggle>
  );
}

export interface StackSeries {
  key: string;
  label: string;
  tone: Tone;
}

/** 시간대별 누적 막대 — 예: 시간대별 실행 상태(성공 · 축소 · 실패) */
export function StackedBars({ title, buckets, series, height = 120 }: { title: string; buckets: { label: string; values: Record<string, number> }[]; series: StackSeries[]; height?: number }) {
  const totals = buckets.map((b) => series.reduce((n, s) => n + (b.values[s.key] ?? 0), 0));
  const top = Math.max(1, ...totals);
  const every = Math.max(1, Math.ceil(buckets.length / 8));
  return (
    <TableToggle
      title={title}
      table={
        <DataTable dense columns={[{ key: "t", label: "시간" }, ...series.map((s) => ({ key: s.key, label: s.label, align: "right" as const })), { key: "n", label: "합계", align: "right" }]}>
          {buckets.map((b, i) => (
            <tr key={b.label}>
              <Td>{b.label}</Td>
              {series.map((s) => (
                <Td key={s.key} align="right">
                  {b.values[s.key] ?? 0}
                </Td>
              ))}
              <Td align="right" strong>
                {totals[i]}
              </Td>
            </tr>
          ))}
        </DataTable>
      }
    >
      <div aria-hidden="true">
        <div className="flex items-end gap-[3px]" style={{ height }}>
          {buckets.map((b, i) => (
            <div key={b.label} className="flex h-full min-w-0 flex-1 origin-bottom flex-col-reverse motion-safe:animate-grow-y" style={{ "--i": Math.min(i, 24) } as CSSProperties} title={`${b.label} · ${totals[i]}건`}>
              {series.map((s) => {
                const v = b.values[s.key] ?? 0;
                return v ? <span key={s.key} className={clsx("block w-full first:rounded-b-sm last:rounded-t-sm", BG[s.tone])} style={{ height: `${(v / top) * 100}%` }} /> : null;
              })}
            </div>
          ))}
        </div>
        <div className="mt-1 flex gap-[3px] text-[10px] text-stone">
          {buckets.map((b, i) => (
            <span key={b.label} className="min-w-0 flex-1 truncate text-center">
              {i % every === 0 ? b.label : ""}
            </span>
          ))}
        </div>
      </div>
      <ul className="mt-2 flex flex-wrap gap-x-base gap-y-1 text-[11.5px] text-charcoal">
        {series.map((s) => (
          <li key={s.key} className="flex items-center gap-1.5">
            <span aria-hidden="true" className={clsx("h-2 w-2 rounded-sm", BG[s.tone])} />
            {s.label} {buckets.reduce((n, b) => n + (b.values[s.key] ?? 0), 0)}
          </li>
        ))}
      </ul>
    </TableToggle>
  );
}

/** 노드 타임라인 — 실행 안 노드의 시작 · 소요를 가로 막대로(간트). 실패 · 축소는 색 + 글자로 */
export function Timeline({ title, items }: { title: string; items: { key: string; label: string; status: string; startMs: number; durationMs: number }[] }) {
  const end = Math.max(1, ...items.map((i) => i.startMs + i.durationMs));
  const tone = (s: string): Tone => (s === "failed" ? "critical" : s === "degraded" ? "attention" : s === "skipped" ? "neutral" : "success");
  const ms = (v: number) => (v < 1000 ? `${v}ms` : `${(v / 1000).toFixed(1)}s`);
  return (
    <TableToggle
      title={title}
      table={
        <DataTable dense columns={[{ key: "n", label: "노드" }, { key: "s", label: "상태" }, { key: "a", label: "시작", align: "right" }, { key: "d", label: "소요", align: "right" }]}>
          {items.map((i) => (
            <tr key={i.key}>
              <Td>{i.label}</Td>
              <Td>{i.status}</Td>
              <Td align="right">{ms(i.startMs)}</Td>
              <Td align="right">{ms(i.durationMs)}</Td>
            </tr>
          ))}
        </DataTable>
      }
    >
      <ul className="flex flex-col gap-1" data-timeline>
        {items.map((i) => (
          <li key={i.key} className="grid grid-cols-[minmax(0,170px)_1fr_64px] items-center gap-2 text-[11.5px]">
            <span className="truncate font-mono text-charcoal" title={i.label}>
              {i.label}
            </span>
            <span className="relative h-3 rounded-sm bg-surface-soft" aria-hidden="true">
              <span
                className={clsx("absolute inset-y-0 origin-left rounded-sm motion-safe:animate-grow-x", BG[tone(i.status)])}
                style={{ left: `${(i.startMs / end) * 100}%`, width: `${Math.max(0.6, (i.durationMs / end) * 100)}%` }}
              />
            </span>
            <span className={clsx("text-right tnum", i.status === "failed" ? "font-bold text-critical" : i.status === "degraded" ? "font-bold text-attention" : "text-steel")}>
              {i.status === "failed" ? "실패 " : i.status === "degraded" ? "축소 " : ""}
              {ms(i.durationMs)}
            </span>
          </li>
        ))}
      </ul>
    </TableToggle>
  );
}
