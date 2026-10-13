"use client";

import { useId, useState } from "react";
import clsx from "clsx";
import { IconTable } from "@/components/ui/icons";
import { DataTable, Td } from "@/components/ui/primitives";
import { UNIT_LABEL, defaultDecimals } from "@/lib/format";
import type { Figure, SeriesPoint } from "@/lib/types";

/** 차트 계열 색 — 토큰 `--chart-1..6`(primary · attention · success · stone · purple · teal 순, C.1 · Q106). SVG 에서는 style 로 칠한다 */
export const PALETTE = ["var(--chart-1)", "var(--chart-2)", "var(--chart-3)", "var(--chart-4)", "var(--chart-5)", "var(--chart-6)"];

interface ChartProps {
  title?: string;
  series: { name: string; points: SeriesPoint[]; color?: string }[];
  unit: Figure["unit"];
  decimals?: number;
  height?: number;
  kind: "bar" | "line";
  caption?: string;
  className?: string;
  /** false 이면 선 차트의 Y축을 데이터 범위에 맞춘다 (기본 true) */
  zeroBased?: boolean;
}

const fmt = (v: number | null, unit: Figure["unit"], decimals?: number) => {
  if (v === null) return "-";
  const d = decimals ?? defaultDecimals(unit);
  return new Intl.NumberFormat("ko-KR", { minimumFractionDigits: d, maximumFractionDigits: d }).format(v);
};

/**
 * 의존성 없는 SVG 차트.
 * 접근성: role="img" + aria-label + 동일 데이터를 표로 전환하는 토글 제공 (요구사항 UX-07)
 */
export function Chart({ title, series, unit, decimals, height = 220, kind, caption, className, zeroBased = true }: ChartProps) {
  const [asTable, setAsTable] = useState(false);
  const gradientId = useId();
  const categories = series[0]?.points.map((p) => p.label) ?? [];
  const values = series.flatMap((s) => s.points.map((p) => p.value)).filter((v): v is number => v !== null);
  const rawMax = values.length ? Math.max(...values) : 1;
  const dataMin = values.length ? Math.min(...values) : 0;
  // 막대는 0 기준이 원칙. 추세 선은 변화폭이 보이도록 데이터 범위에 맞출 수 있다(zeroBased=false).
  const rawMin = zeroBased || kind === "bar" ? Math.min(0, dataMin) : dataMin;
  const span = rawMax - rawMin || Math.abs(rawMax) || 1;
  const max = zeroBased || kind === "bar" ? (rawMax === rawMin ? rawMax + 1 : rawMax * 1.12) : rawMax + span * 0.25;
  const min = zeroBased || kind === "bar" ? rawMin : rawMin - span * 0.25;

  const W = 720;
  const H = height;
  const padL = 56;
  const padR = 16;
  const padT = 16;
  const padB = 34;
  const innerW = W - padL - padR;
  const innerH = H - padT - padB;

  const x = (i: number) => padL + (innerW / Math.max(categories.length, 1)) * (i + 0.5);
  const y = (v: number) => padT + innerH - ((v - min) / (max - min)) * innerH;
  const ticks = Array.from({ length: 5 }, (_, i) => min + ((max - min) / 4) * i);

  const ariaLabel = `${title ?? "차트"} — ${series
    .map((s) => `${s.name}: ${s.points.map((p) => `${p.label} ${fmt(p.value, unit, decimals)}${UNIT_LABEL[unit]}`).join(", ")}`)
    .join(" / ")}`;

  return (
    <figure className={clsx("w-full", className)}>
      <div className="mb-2 flex items-start justify-between gap-base">
        <div>
          {title ? <figcaption className="text-[13px] font-bold text-charcoal">{title}</figcaption> : null}
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1">
            {series.map((s, i) => (
              <span key={s.name} className="inline-flex items-center gap-1.5 text-[11px] text-steel">
                <span
                  className="inline-block h-2 w-2 rounded-full"
                  style={{ background: s.color ?? PALETTE[i % PALETTE.length] }}
                  aria-hidden="true"
                />
                {s.name}
              </span>
            ))}
            <span className="text-[11px] text-stone">단위 {UNIT_LABEL[unit] || "지수"}</span>
          </div>
        </div>
        <button
          type="button"
          onClick={() => setAsTable((v) => !v)}
          className="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-md border border-hairline-soft bg-canvas px-3 text-[12px] font-bold text-ink-deep hover:bg-surface-soft no-print"
          aria-pressed={asTable}
        >
          <IconTable />
          {asTable ? "차트 보기" : "표 보기"}
        </button>
      </div>

      {asTable ? (
        <DataTable
          dense
          columns={[{ key: "label", label: "구분" }, ...series.map((s) => ({ key: s.name, label: s.name, align: "right" as const }))]}
        >
          {categories.map((label, i) => (
            <tr key={label}>
              <Td strong>{label}</Td>
              {series.map((s) => (
                <Td key={s.name} align="right">
                  {fmt(s.points[i]?.value ?? null, unit, decimals)}
                </Td>
              ))}
            </tr>
          ))}
        </DataTable>
      ) : (
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label={ariaLabel}>
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" style={{ stopColor: "var(--chart-1)", stopOpacity: 0.16 }} />
              <stop offset="100%" style={{ stopColor: "var(--chart-1)", stopOpacity: 0 }} />
            </linearGradient>
          </defs>

          {ticks.map((t, i) => (
            <g key={i}>
              <line x1={padL} x2={W - padR} y1={y(t)} y2={y(t)} className="stroke-hairline-soft" strokeWidth="1" />
              <text x={padL - 8} y={y(t) + 3.5} textAnchor="end" fontSize="11" className="fill-steel">
                {fmt(t, unit, decimals)}
              </text>
            </g>
          ))}

          {categories.map((label, i) => (
            <text key={label} x={x(i)} y={H - 12} textAnchor="middle" fontSize="11" className="fill-steel">
              {label}
            </text>
          ))}

          {kind === "bar"
            ? series.map((s, si) => {
                const slot = innerW / Math.max(categories.length, 1);
                const barW = Math.min(26, (slot * 0.62) / series.length);
                return (
                  <g key={s.name}>
                    {s.points.map((p, i) => {
                      if (p.value === null) return null;
                      const cx = x(i) - (barW * series.length) / 2 + barW * si;
                      const top = y(p.value);
                      return (
                        <rect
                          key={p.label}
                          x={cx}
                          y={top}
                          width={barW}
                          height={Math.max(1, y(min) - top)}
                          rx="3"
                          style={{ fill: s.color ?? PALETTE[si % PALETTE.length] }}
                          opacity={si === 0 ? 0.92 : 0.78}
                        />
                      );
                    })}
                  </g>
                );
              })
            : series.map((s, si) => {
                const pts = s.points
                  .map((p, i) => (p.value === null ? null : `${x(i)},${y(p.value)}`))
                  .filter((v): v is string => v !== null);
                return (
                  <g key={s.name}>
                    {si === 0 && pts.length > 1 ? (
                      <polygon
                        points={`${padL},${y(min)} ${pts.join(" ")} ${W - padR},${y(min)}`}
                        fill={`url(#${gradientId})`}
                      />
                    ) : null}
                    <polyline
                      points={pts.join(" ")}
                      fill="none"
                      style={{ stroke: s.color ?? PALETTE[si % PALETTE.length] }}
                      strokeWidth="2.2"
                      strokeLinejoin="round"
                      strokeLinecap="round"
                      strokeDasharray={si >= 1 && !s.color ? "5 4" : undefined}
                    />
                    {s.points.map((p, i) =>
                      p.value === null ? null : (
                        <circle
                          key={p.label}
                          cx={x(i)}
                          cy={y(p.value)}
                          r="3.2"
                          className="fill-canvas"
                          style={{ stroke: s.color ?? PALETTE[si % PALETTE.length] }}
                          strokeWidth="2"
                        />
                      ),
                    )}
                  </g>
                );
              })}

          <line x1={padL} x2={W - padR} y1={y(min)} y2={y(min)} className="stroke-hairline" strokeWidth="1" />
        </svg>
      )}

      {caption ? <p className="mt-1.5 text-[11px] text-stone">{caption}</p> : null}
    </figure>
  );
}

/** 목표 대비 실적을 한 줄로 보여주는 게이지 */
export function TargetGauge({
  actual,
  target,
  unit,
  decimals,
  tone = "primary",
  targetLabel = "목표",
}: {
  actual: number;
  target: number;
  unit: Figure["unit"];
  decimals?: number;
  tone?: "primary" | "success" | "attention" | "critical";
  targetLabel?: string;
}) {
  const scaleMax = Math.max(actual, target) * 1.15;
  const actualPct = (actual / scaleMax) * 100;
  const targetPct = (target / scaleMax) * 100;
  const toneClass = {
    primary: "bg-primary",
    success: "bg-success",
    attention: "bg-attention",
    critical: "bg-critical",
  }[tone];

  return (
    <div className="pt-4">
      <div className="relative h-2.5 w-full rounded-pill bg-surface-soft">
        <div className={clsx("absolute inset-y-0 left-0 rounded-pill", toneClass)} style={{ width: `${actualPct}%` }} />
        <div className="absolute -top-1 bottom-[-4px] w-[2px] bg-ink-deep" style={{ left: `${targetPct}%` }} aria-hidden="true" />
        <span
          className="absolute -top-5 -translate-x-1/2 whitespace-nowrap text-[10px] font-bold text-ink-deep"
          style={{ left: `${targetPct}%` }}
        >
          {targetLabel} {fmt(target, unit, decimals)}
          {UNIT_LABEL[unit]}
        </span>
      </div>
    </div>
  );
}
