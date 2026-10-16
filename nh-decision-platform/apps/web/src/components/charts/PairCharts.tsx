"use client";

/**
 * 기업 · 가계 두 계열 비교 차트 (시안 304:2 · 2단계 기업·가계 비교).
 * 색 — 주 계열(기업) primary/500 · 비교 계열(가계) 옅은 보라(chart-5). 지난 시점 막대는 더 옅은 톤(primary/200 · primary/100), 마지막 시점만 값 · 라벨을 진하게.
 * SVG 좌표는 카드 폭(807 · 470)에 맞춰 글자가 커지지 않게 한다.
 */

export const PAIR = {
  a: "var(--color-primary)",
  aText: "var(--color-primary-deep)",
  b: "var(--chart-5)",
  bText: "var(--chart-5)",
  /** 지난 시점 막대 톤 */
  aPast: "var(--color-primary-soft)",
  bPast: "var(--color-info-soft)",
} as const;

const STEEL = "var(--color-steel)";
const INK = "var(--color-ink-deep)";
const GRID = "var(--chart-grid)";
const BASE = "var(--chart-axis)";
const CANVAS = "var(--color-canvas)";
/** 위쪽 두 모서리만 둥근 세로 막대 */
function topRounded(x: number, y: number, w: number, h: number, r: number): string {
  const rr = Math.min(r, w / 2, h);
  return `M${x},${y + h}V${y + rr}Q${x},${y} ${x + rr},${y}H${x + w - rr}Q${x + w},${y} ${x + w},${y + rr}V${y + h}Z`;
}
/** 오른쪽 두 모서리만 둥근 가로 막대 */
function rightRounded(x: number, y: number, w: number, h: number, r: number): string {
  const rr = Math.min(r, h / 2, w);
  return `M${x},${y}H${x + w - rr}Q${x + w},${y} ${x + w},${y + rr}V${y + h - rr}Q${x + w},${y + h} ${x + w - rr},${y + h}H${x}Z`;
}

function niceMax(v: number, steps = 3): { max: number; step: number } {
  const raw = v / steps;
  const mag = 10 ** Math.floor(Math.log10(raw || 1));
  const n = raw / mag;
  const s = (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 4 ? 4 : n <= 5 ? 5 : 10) * mag;
  return { max: Math.ceil(v / s) * s, step: s };
}

/** 두 계열 꺾은선 — 월별 잔액. 끝점 값 라벨 */
export function PairLine({
  labels,
  a,
  b,
  decimals = 2,
  ariaLabel,
}: {
  labels: string[];
  a: (number | null)[];
  b: (number | null)[];
  decimals?: number;
  ariaLabel: string;
}) {
  const W = 807;
  const H = 214;
  const L = 75;
  const R = 710;
  const T = 19;
  const B = 183;
  const all = [...a, ...b].filter((v): v is number => v !== null);
  if (!all.length) return null;
  const lo = Math.min(...all);
  const hi = Math.max(...all);
  const span = hi - lo || 1;
  const { step } = niceMax(span * 1.2, 3);
  const yMin = Math.floor((lo - span * 0.1) / step) * step;
  const ticks: number[] = [];
  for (let v = yMin; ticks.length < 4; v += step) ticks.push(Number(v.toFixed(6)));
  const yMax = ticks[ticks.length - 1];
  const n = labels.length;
  const x = (i: number) => L + ((R - L) * i) / Math.max(1, n - 1);
  const y = (v: number) => B - ((v - yMin) / (yMax - yMin)) * (B - T);
  const line = (s: (number | null)[]) =>
    s
      .map((v, i) => (v === null ? null : `${x(i).toFixed(1)},${y(v).toFixed(1)}`))
      .filter(Boolean)
      .join(" ");
  const lastIdx = (s: (number | null)[]) => s.reduce<number>((m, v, i) => (v === null ? m : i), -1);
  const series = [
    { s: a, c: PAIR.a, t: PAIR.aText },
    { s: b, c: PAIR.b, t: PAIR.bText },
  ];
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full" role="img" aria-label={ariaLabel}>
      {ticks.map((t) => (
        <g key={t}>
          <line x1={L} x2={R + 49} y1={y(t)} y2={y(t)} stroke={GRID} />
          <text x={L - 14} y={y(t) + 4} textAnchor="end" fontSize="11" fill={STEEL} className="tnum">
            {Number.isInteger(t) ? t : t.toFixed(1)}
          </text>
        </g>
      ))}
      {labels.map((l, i) => (
        <text key={l + i} x={x(i)} y={H - 4} textAnchor="middle" fontSize="11" fontWeight={i === n - 1 ? 700 : 400} fill={i === n - 1 ? INK : STEEL}>
          {l}
        </text>
      ))}
      {series.map(({ s, c, t }, k) => {
        const li = lastIdx(s);
        return (
          <g key={k}>
            <polyline points={line(s)} fill="none" stroke={c} strokeWidth="1.8" strokeLinejoin="round" />
            {s.map((v, i) =>
              v === null ? null : i === li ? (
                <circle key={i} cx={x(i)} cy={y(v)} r="6.5" fill={c} />
              ) : (
                <circle key={i} cx={x(i)} cy={y(v)} r="4.5" fill={CANVAS} stroke={c} strokeWidth="1.6" />
              ),
            )}
            {li >= 0 && s[li] !== null ? (
              <text x={x(li) + 16} y={y(s[li] as number) + 5} fontSize="14" fontWeight="700" fill={t} className="tnum">
                {(s[li] as number).toFixed(decimals)}
              </text>
            ) : null}
          </g>
        );
      })}
    </svg>
  );
}

/** 두 계열 세로 막대 — 시점별 (예: 3개년 8월 누계 이자수익) */
export function PairColumns({ labels, a, b, ariaLabel, format }: { labels: string[]; a: (number | null)[]; b: (number | null)[]; ariaLabel: string; format: (v: number) => string }) {
  const W = 807;
  const H = 214;
  const L = 75;
  const R = 710;
  const T = 19;
  const B = 183;
  const all = [...a, ...b].filter((v): v is number => v !== null);
  if (!all.length) return null;
  const { max, step } = niceMax(Math.max(...all), 3);
  const ticks = [0, step, step * 2, step * 3].filter((t) => t <= max + 1e-9);
  const top = ticks[ticks.length - 1] || max;
  const y = (v: number) => B - (v / top) * (B - T);
  const n = labels.length;
  const gw = (R - L) / n;
  const bw = 55;
  const last = n - 1;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full" role="img" aria-label={ariaLabel}>
      {ticks.map((t) => (
        <g key={t}>
          <line x1={L} x2={R + 49} y1={y(t)} y2={y(t)} stroke={t === 0 ? BASE : GRID} />
          <text x={L - 14} y={y(t) + 4} textAnchor="end" fontSize="11" fill={STEEL} className="tnum">
            {t.toLocaleString("ko-KR")}
          </text>
        </g>
      ))}
      {labels.map((l, i) => {
        const cx = L + gw * i + gw / 2 + 24;
        const bars = [
          { v: a[i], c: i === last ? PAIR.a : PAIR.aPast, t: PAIR.aText, x: cx - bw - 4 },
          { v: b[i], c: i === last ? PAIR.b : PAIR.bPast, t: PAIR.bText, x: cx + 4 },
        ];
        return (
          <g key={l}>
            {bars.map((bar, k) =>
              bar.v === null || bar.v === undefined ? null : (
                <g key={k}>
                  <path d={topRounded(bar.x, y(bar.v), bw, B - y(bar.v), 6)} fill={bar.c} />
                  <text
                    x={bar.x + bw / 2}
                    y={y(bar.v) - 7}
                    textAnchor="middle"
                    fontSize={i === last ? 13 : 11}
                    fontWeight={i === last ? 700 : 500}
                    fill={i === last ? bar.t : STEEL}
                    className="tnum"
                  >
                    {format(bar.v)}
                  </text>
                </g>
              ),
            )}
            <text x={cx} y={H - 4} textAnchor="middle" fontSize="11" fontWeight={i === last ? 700 : 400} fill={i === last ? INK : STEEL}>
              {l}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

/** 두 계열 가로 막대 — 항목별 증가율(%) */
export function PairHBars({ rows, ariaLabel }: { rows: { label: string; a: number | null; b: number | null }[]; ariaLabel: string }) {
  const W = 470;
  const L = 75;
  const R = 395;
  const BH = 24;
  const PAIR_GAP = 6;
  const GROUP = 74;
  const all = rows.flatMap((r) => [r.a, r.b]).filter((v): v is number => v !== null);
  if (!all.length) return null;
  const max = Math.max(2, Math.ceil(Math.max(...all) / 2) * 2);
  const ticks: number[] = [];
  for (let t = 0; t <= max; t += 2) ticks.push(t);
  const x = (v: number) => L + (Math.max(0, v) / max) * (R - L);
  const H = rows.length * GROUP + 40;
  const plotB = rows.length * GROUP + 2;
  const sign = (v: number) => `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full" role="img" aria-label={ariaLabel}>
      {ticks.map((t) => (
        <g key={t}>
          <line x1={x(t)} x2={x(t)} y1={3} y2={plotB} stroke={t === 0 ? BASE : GRID} />
          <text x={x(t)} y={plotB + 18} textAnchor="middle" fontSize="11" fill={STEEL} className="tnum">
            {t}%
          </text>
        </g>
      ))}
      {rows.map((r, i) => {
        const y0 = 10 + i * GROUP;
        const bars = [
          { v: r.a, c: PAIR.a, t: PAIR.aText, y: y0 },
          { v: r.b, c: PAIR.b, t: PAIR.bText, y: y0 + BH + PAIR_GAP },
        ];
        return (
          <g key={r.label}>
            <text x={0} y={y0 + BH + PAIR_GAP / 2 + 4} fontSize="12" fontWeight="500" fill={INK}>
              {r.label}
            </text>
            {bars.map((bar, k) =>
              bar.v === null ? null : (
                <g key={k}>
                  <path d={rightRounded(L + 1, bar.y, Math.max(2, x(bar.v) - L - 1), BH, 6)} fill={bar.c} />
                  <text x={x(bar.v) + 7} y={bar.y + 16} fontSize="12" fontWeight="700" fill={bar.t} className="tnum">
                    {sign(bar.v)}
                  </text>
                </g>
              ),
            )}
          </g>
        );
      })}
    </svg>
  );
}
