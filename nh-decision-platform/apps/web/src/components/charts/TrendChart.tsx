"use client";

import { useId, useRef, useState, type KeyboardEvent, type MouseEvent } from "react";
import clsx from "clsx";

export interface TrendPoint {
  label: string;
  value: number | null;
}

export interface TrendTooltip {
  /** 시점 · 대상 (예: 2026.08 · 기업여신) */
  head: string;
  /** 값 본문 (단위 제외) */
  value: string;
  unit?: string;
  /** 기준값 · 차이 */
  rows?: { label: string; value: string; tone?: "warning" | "danger" }[];
}

/** 눈금을 보기 좋은 간격으로 맞춘다 */
function niceTicks(min: number, max: number, count = 4): number[] {
  const span = max - min || Math.abs(max) || 1;
  const raw = span / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const norm = raw / mag;
  const step = (norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 2.5 ? 2.5 : norm <= 5 ? 5 : 10) * mag;
  const lo = Math.floor(min / step) * step;
  const hi = Math.ceil(max / step) * step;
  const ticks: number[] = [];
  for (let v = lo; v <= hi + step / 1e6; v += step) ticks.push(Number(v.toFixed(8)));
  return ticks;
}

const W = 440;
const PAD = { l: 44, r: 84, t: 16, b: 30 };

/**
 * 추세선 — 실적(보라 실선) · 목표 경로(회색 점선) · 한도(빨간 점선).
 * 마우스를 올리거나 방향키로 시점을 옮기면 시점 · 값 · 기준값 · 차이를 말풍선으로 보여 준다 (가이드 G05 툴팁).
 * 최신 시점 값과 기준선 라벨만 상시 노출하고 나머지는 말풍선으로 옮겼다.
 */
export function TrendChart({
  points,
  target,
  limit,
  format,
  formatTick,
  tooltip,
  height = 224,
  ariaLabel,
  gapFill = false,
}: {
  points: TrendPoint[];
  target?: { name: string; values: (number | null)[] };
  limit?: { value: number; label: string };
  /** 끝 라벨 숫자 표기 */
  format: (v: number) => string;
  /** 축 눈금 숫자 표기 (기본은 format 과 같음) */
  formatTick?: (v: number) => string;
  tooltip: (index: number) => TrendTooltip;
  height?: number;
  ariaLabel: string;
  /** 실적과 목표 경로 사이(미달 폭)를 옅게 칠한다 */
  gapFill?: boolean;
}) {
  const gradId = useId();
  const wrap = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<number | null>(null);
  const n = points.length;
  const H = height;
  const innerW = W - PAD.l - PAD.r;
  const innerH = H - PAD.t - PAD.b;

  const all = [
    ...points.map((p) => p.value),
    ...(target?.values ?? []),
    ...(limit ? [limit.value] : []),
  ].filter((v): v is number => v !== null && v !== undefined);
  const lo = Math.min(...all);
  const hi = Math.max(...all);
  const pad = (hi - lo || Math.abs(hi) || 1) * 0.12;
  const ticks = niceTicks(lo - pad, hi + pad);
  const yMin = ticks[0];
  const yMax = ticks[ticks.length - 1];
  const x = (i: number) => PAD.l + (n > 1 ? (innerW * i) / (n - 1) : innerW / 2);
  const y = (v: number) => PAD.t + innerH - ((v - yMin) / (yMax - yMin)) * innerH;

  const actual = points.map((p, i) => (p.value === null ? null : ([x(i), y(p.value)] as const)));
  const actualPts = actual.filter((p): p is readonly [number, number] => p !== null);
  const targetPts = (target?.values ?? []).map((v, i) => (v === null || v === undefined ? null : ([x(i), y(v)] as const)));
  const targetOk = targetPts.filter((p): p is readonly [number, number] => p !== null);
  const line = (pts: readonly (readonly [number, number])[]) => pts.map((p) => p.join(",")).join(" ");
  const last = actualPts[actualPts.length - 1];
  const lastTarget = targetOk[targetOk.length - 1];
  const lastValue = [...points].reverse().find((p) => p.value !== null)?.value ?? null;
  const lastTargetValue = [...(target?.values ?? [])].reverse().find((v) => v !== null && v !== undefined) ?? null;

  const indexAt = (e: MouseEvent<HTMLDivElement>) => {
    const box = wrap.current?.getBoundingClientRect();
    if (!box || n === 0) return null;
    const px = ((e.clientX - box.left) / box.width) * W;
    let best = 0;
    for (let i = 1; i < n; i++) if (Math.abs(x(i) - px) < Math.abs(x(best) - px)) best = i;
    return best;
  };
  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "ArrowRight") {
      e.preventDefault();
      setHover((h) => Math.min(n - 1, (h ?? -1) + 1));
    } else if (e.key === "ArrowLeft") {
      e.preventDefault();
      setHover((h) => Math.max(0, (h ?? n) - 1));
    } else if (e.key === "Escape") setHover(null);
  };

  const tip = hover !== null ? tooltip(hover) : null;
  const hx = hover !== null ? x(hover) : 0;
  const flip = hx / W > 0.55;

  return (
    <div
      ref={wrap}
      className="relative outline-none"
      tabIndex={0}
      role="group"
      aria-label={`${ariaLabel} — 좌우 방향키로 시점을 옮겨 값을 확인`}
      onMouseMove={(e) => setHover(indexAt(e))}
      onMouseLeave={() => setHover(null)}
      onKeyDown={onKey}
      onBlur={() => setHover(null)}
    >
      <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full" role="img" aria-label={ariaLabel}>
        <defs>
          <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--color-primary)" stopOpacity="0.14" />
            <stop offset="100%" stopColor="var(--color-primary)" stopOpacity="0" />
          </linearGradient>
        </defs>

        {ticks.map((t) => (
          <g key={t}>
            <line x1={PAD.l} x2={W - PAD.r} y1={y(t)} y2={y(t)} stroke="var(--chart-grid)" strokeWidth="1" />
            <text x={PAD.l - 10} y={y(t) + 4} textAnchor="end" fontSize="11" fill="var(--color-steel)" className="tnum">
              {(formatTick ?? format)(t)}
            </text>
          </g>
        ))}
        {points.map((p, i) => (
          <text key={p.label} x={x(i)} y={H - 8} textAnchor="middle" fontSize="11" fill={hover === i ? "var(--color-ink-deep)" : "var(--color-steel)"} fontWeight={hover === i || i === n - 1 ? 700 : 400}>
            {p.label}
          </text>
        ))}

        {limit ? (
          <g>
            <line x1={PAD.l} x2={W - PAD.r} y1={y(limit.value)} y2={y(limit.value)} stroke="var(--color-critical)" strokeWidth="1.4" strokeDasharray="5 4" />
            <text x={PAD.l} y={y(limit.value) - 6} fontSize="11" fontWeight="700" fill="var(--color-critical-text)">
              {limit.label}
            </text>
          </g>
        ) : null}

        {gapFill && targetOk.length > 1 && actualPts.length > 1 ? (
          <polygon points={`${line(targetOk)} ${line([...actualPts].reverse())}`} fill="var(--color-primary-soft)" opacity="0.5" />
        ) : !target && actualPts.length > 1 ? (
          <polygon points={`${actualPts[0][0]},${y(yMin)} ${line(actualPts)} ${last[0]},${y(yMin)}`} fill={`url(#${gradId})`} />
        ) : null}

        {targetOk.length > 1 ? (
          <polyline points={line(targetOk)} fill="none" stroke="var(--chart-4)" strokeWidth="1.6" strokeDasharray="5 4" strokeLinejoin="round" />
        ) : null}
        {lastTarget ? (
          <g>
            <circle cx={lastTarget[0]} cy={lastTarget[1]} r="3.5" fill="var(--color-canvas)" stroke="var(--chart-4)" strokeWidth="1.6" />
            {lastTargetValue !== null ? (
              <text x={lastTarget[0] + 8} y={lastTarget[1] - (last && last[1] > lastTarget[1] ? 4 : 0) + 4} fontSize="11" fill="var(--color-steel)" className="tnum">
                {target?.name} {format(lastTargetValue)}
              </text>
            ) : null}
          </g>
        ) : null}

        {actualPts.length > 1 ? <polyline points={line(actualPts)} fill="none" stroke="var(--color-primary)" strokeWidth="2.4" strokeLinejoin="round" strokeLinecap="round" /> : null}
        {actual.map((p, i) =>
          p === null || i === n - 1 ? null : <circle key={i} cx={p[0]} cy={p[1]} r={hover === i ? 5 : 3} fill="var(--color-canvas)" stroke="var(--color-primary)" strokeWidth="2" />,
        )}
        {last ? (
          <g>
            <circle cx={last[0]} cy={last[1]} r={hover === n - 1 ? 7 : 5.5} fill="var(--color-primary)" />
            {lastValue !== null ? (
              <text x={last[0] + 10} y={last[1] + (lastTarget && lastTarget[1] < last[1] ? 14 : 4)} fontSize="13" fontWeight="700" fill="var(--color-primary-text)" className="tnum">
                {format(lastValue)}
              </text>
            ) : null}
          </g>
        ) : null}

        {hover !== null ? <line x1={hx} x2={hx} y1={PAD.t} y2={H - PAD.b} stroke="var(--chart-axis)" strokeWidth="1" /> : null}
        {hover !== null && hover !== n - 1 && actual[hover] ? <circle cx={actual[hover]![0]} cy={actual[hover]![1]} r="5" fill="var(--color-primary)" /> : null}
        {hover !== null && targetPts[hover] ? <circle cx={targetPts[hover]![0]} cy={targetPts[hover]![1]} r="4" fill="var(--color-canvas)" stroke="var(--chart-4)" strokeWidth="1.8" /> : null}
      </svg>

      {tip ? (
        <div
          role="status"
          className={clsx(
            "pointer-events-none absolute top-3 z-20 w-[190px] rounded-lg bg-ink-deep p-3 text-white shadow-tooltip",
            flip ? "-translate-x-full" : "",
          )}
          style={{ left: `calc(${(hx / W) * 100}% ${flip ? "- 14px" : "+ 14px"})` }}
        >
          <p className="text-[12px] text-white/75">{tip.head}</p>
          <p className="tnum mt-0.5 text-[20px] font-bold leading-[1.25]">
            {tip.value}
            {tip.unit ? <span className="ml-0.5 text-[12px] font-medium text-white/75">{tip.unit}</span> : null}
          </p>
          {tip.rows?.length ? (
            <dl className="mt-2 flex flex-col gap-1 border-t border-white/20 pt-2 text-[12px]">
              {tip.rows.map((r) => (
                <div key={r.label} className="flex items-baseline justify-between gap-3">
                  <dt className="text-white/75">{r.label}</dt>
                  <dd className={clsx("tnum font-bold", r.tone === "danger" ? "text-[#ff9b9e]" : r.tone === "warning" ? "text-[#ffc08c]" : "text-white")}>{r.value}</dd>
                </div>
              ))}
            </dl>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
