"use client";
/**
 * 신용리스크관리부 2단계 그래프 (시안 350:2 · 352:2) — 0 기준 위아래 막대 · 등급별 실제/예측 부도율 · 비중 변화 폭포 막대.
 * 값은 모두 보고서 표 · 수치에서 받아 그리기만 한다. 막대는 자라며 나온다(motion-safe). 값이 없거나 0 인 막대는 막대 없이 '0' 하나만.
 */
import { useId, useState, type CSSProperties } from "react";
import clsx from "clsx";
import { MiniTag, ZERO_LABEL, fmtNum, isBarValue, niceMax } from "@/components/analysis/report/kit";

const order = (i: number) => ({ ["--i" as string]: i }) as CSSProperties;
const at = (v: number, lo: number, hi: number) => ((v - lo) / (hi - lo)) * 100;

/** 0 기준 위아래 세로 막대 — 줄어든 칸은 회색 아래로, 늘어난 칸은 옅은 보라 위로, 강조 칸은 띠 + primary */
export function DivergingColumns({ categories, values, focus, decimals = 2, height = 200, ariaLabel }: { categories: string[]; values: (number | null)[]; focus?: number | null; decimals?: number; height?: number; ariaLabel: string }) {
  const m = niceMax(Math.max(0, ...values.map((v) => Math.abs(v ?? 0))));
  const ticks = [m, m / 2, 0, -m / 2, -m];
  return (
    <div role="img" aria-label={ariaLabel} className="flex">
      <div className="relative w-8 shrink-0" style={{ height }} aria-hidden="true">
        {ticks.map((t) => (
          <span key={t} className="tnum absolute right-2 -translate-y-1/2 text-[10px] text-steel" style={{ top: `${100 - at(t, -m, m)}%` }}>
            {t > 0 ? `+${fmtNum(t, Number.isInteger(t) ? 0 : 1)}` : fmtNum(t, Number.isInteger(t) ? 0 : 1)}
          </span>
        ))}
      </div>
      <div className="min-w-0 flex-1">
        <div className="relative" style={{ height }}>
          {ticks.map((t) => (
            <span key={t} aria-hidden="true" className={clsx("absolute inset-x-0 h-px", t === 0 ? "bg-chart-axis" : "bg-chart-grid")} style={{ top: `${100 - at(t, -m, m)}%` }} />
          ))}
          <div className="absolute inset-0 flex">
            {categories.map((c, i) => {
              const v = values[i];
              const strong = focus === i;
              const h = typeof v === "number" ? (Math.abs(v) / m) * 50 : 0;
              const pos = (v ?? 0) > 0;
              return (
                <div key={c} className={clsx("relative flex-1", strong && "rounded-t-lg bg-info-faint")}>
                  {!isBarValue(v) ? (
                    <span className={clsx("tnum absolute left-1/2 -translate-x-1/2 whitespace-nowrap text-[10px]", strong ? "font-bold text-primary-deep" : "text-steel")} style={{ bottom: "calc(50% + 3px)" }}>
                      {ZERO_LABEL}
                    </span>
                  ) : (
                    <>
                      <span
                        className={clsx(
                          "absolute inset-x-0 mx-auto w-[58%] max-w-[30px] motion-safe:animate-grow-y",
                          pos ? "bottom-1/2 origin-bottom rounded-t-[3px]" : "top-1/2 origin-top rounded-b-[3px]",
                          strong ? "bg-primary" : pos ? "bg-info-line" : "bg-hairline-soft",
                        )}
                        style={{ height: `${h}%`, ...order(i) }}
                      />
                      <span
                        className={clsx("tnum absolute left-1/2 -translate-x-1/2 whitespace-nowrap text-[10px]", strong ? "font-bold text-primary-deep" : "text-steel")}
                        style={pos ? { bottom: `calc(${50 + h}% + 3px)` } : { top: `calc(${50 + h}% + 3px)` }}
                      >
                        {pos ? "+" : ""}
                        {fmtNum(v, decimals)}
                      </span>
                    </>
                  )}
                </div>
              );
            })}
          </div>
        </div>
        <div className="flex">
          {categories.map((c, i) => (
            <span key={c} className={clsx("flex-1 pb-1 pt-1.5 text-center text-[11px]", focus === i ? "rounded-b-lg bg-info-faint font-bold text-primary-deep" : "font-medium text-ink-deep")}>
              {c}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

export interface PdRow {
  grade: string;
  /** 실제부도율 */
  dr: number | null;
  /** 예측 대표값 · 최대값 */
  mid: number | null;
  max: number | null;
  /** 툴팁 글자 — 보고서 표 칸 그대로 */
  text: { dr: string; mid: string; max: string; obs: string; defaults: string; verdict: string };
}
/** 툴팁이 왼쪽으로 펼쳐지기 시작하는 칸(전체 칸 수 대비) — 오른쪽 칸은 카드 밖으로 나가지 않게 */
const TIP_FLIP = 0.5;
/**
 * 등급별 실제 · 예측 부도율 (시안 350:2 · 379:18) — 대표값~최대값 상자 · 대표값 선 · 실제 점.
 * warm(대표값 초과) 칸은 주의 색 점, muted(서열 역전) 칸은 빈 동그라미. 칸에 마우스를 올리거나 초점을 주면 등급별 값 툴팁.
 */
export function PdRangeChart({ rows, warm, muted, height = 250, ariaLabel }: { rows: PdRow[]; warm: Set<number>; muted: Set<number>; height?: number; ariaLabel: string }) {
  const [tip, setTip] = useState<number | null>(null);
  const tipId = useId();
  const top = Math.max(0, ...rows.flatMap((r) => [r.dr ?? 0, r.max ?? 0]));
  const mag = 10 ** Math.floor(Math.log10(top || 1));
  const step = mag / 2;
  const hi = niceMax(top);
  const ticks = Array.from({ length: Math.round(hi / step) + 1 }, (_, k) => k * step);
  const y = (v: number) => (v / hi) * 100;
  const n = rows.length;
  return (
    <div role="group" aria-label={ariaLabel} className="flex">
      <div className="relative w-9 shrink-0" style={{ height }} aria-hidden="true">
        {ticks.map((t) => (
          <span key={t} className="tnum absolute right-2 translate-y-1/2 text-[10px] text-steel" style={{ bottom: `${y(t)}%` }}>
            {fmtNum(t, 0)}%
          </span>
        ))}
      </div>
      <div className="min-w-0 flex-1">
        <div className="relative" style={{ height }}>
          {ticks.map((t) => (
            <span key={t} aria-hidden="true" className={clsx("absolute inset-x-0 h-px", t === 0 ? "bg-chart-axis" : "bg-chart-grid")} style={{ bottom: `${y(t)}%` }} />
          ))}
          <div className="absolute inset-0 flex">
            {rows.map((r, i) => {
              const over = warm.has(i);
              const flip = i >= n * TIP_FLIP;
              const shown = tip === i;
              return (
                <div
                  key={r.grade}
                  tabIndex={0}
                  data-pd-point={r.grade}
                  aria-label={`${r.grade} 등급 · 실제부도율 ${r.text.dr}% · 예측 대표값 ${r.text.mid}% · 예측 최대값 ${r.text.max}% · ${r.text.verdict}`}
                  aria-describedby={shown ? tipId : undefined}
                  onMouseEnter={() => setTip(i)}
                  onMouseLeave={() => setTip((c) => (c === i ? null : c))}
                  onFocus={() => setTip(i)}
                  onBlur={() => setTip((c) => (c === i ? null : c))}
                  className="relative flex-1 rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                >
                  {r.mid !== null && r.max !== null ? (
                    <span className="absolute inset-x-0 mx-auto w-[34%] max-w-[22px] origin-bottom rounded-[2px] bg-info-line-soft motion-safe:animate-grow-y" style={{ bottom: `${y(r.mid)}%`, height: `${y(r.max) - y(r.mid)}%`, ...order(i) }} />
                  ) : null}
                  {r.mid !== null ? <span className="absolute inset-x-0 mx-auto h-[2px] w-[42%] max-w-[26px] bg-primary-deep" style={{ bottom: `${y(r.mid)}%` }} /> : null}
                  {r.dr !== null ? (
                    // 위치(가운데 · 점 중심을 값에) 는 바깥 칸, 등장 애니메이션은 안쪽 점 — animation 의 transform 이 가운데 맞춤을 덮지 않게
                    <span className="absolute inset-x-0 mx-auto h-2 w-2" style={{ bottom: `calc(${y(r.dr)}% - 4px)` }}>
                      <span
                        className={clsx(
                          "block h-2 w-2 rounded-circle motion-safe:animate-fade-up",
                          muted.has(i) ? "border-[1.5px] border-ink-deep bg-canvas" : over ? "bg-attention" : "bg-ink-deep",
                          shown && "ring-2 ring-info-line",
                        )}
                        style={order(i)}
                      />
                    </span>
                  ) : null}
                  {shown ? (
                    <div
                      id={tipId}
                      role="tooltip"
                      className={clsx("pointer-events-none absolute z-20 w-[226px] rounded-lg border border-hairline-soft bg-canvas px-3 py-2.5 shadow-tooltip", flip ? "right-1/2" : "left-1/2")}
                      style={{ bottom: `calc(${y(Math.max(r.max ?? 0, r.dr ?? 0))}% + 12px)` }}
                    >
                      <p className="flex items-center gap-1.5">
                        <span className="text-[12px] font-bold text-ink-deep">{r.grade} 등급</span>
                        {r.text.verdict ? <MiniTag tone={over ? "attention" : "neutral"}>{r.text.verdict}</MiniTag> : null}
                      </p>
                      <dl className="tnum mt-1.5 flex flex-col gap-1 text-[11px]">
                        <TipLine label="실제부도율" value={`${r.text.dr}%`} strong={over} />
                        <TipLine label="예측 대표값" value={`${r.text.mid}%`} />
                        <TipLine label="예측 최대값" value={`${r.text.max}%`} />
                        <TipLine label="건수 · 부도" value={`${r.text.obs} · ${r.text.defaults}건`} />
                      </dl>
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
        </div>
        <div className="flex" aria-hidden="true">
          {rows.map((r) => (
            <span key={r.grade} className="flex-1 pb-1 pt-1.5 text-center text-[11px] font-medium text-ink-deep">
              {r.grade}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
function TipLine({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-3 whitespace-nowrap">
      <dt className="text-steel">{label}</dt>
      <dd className={strong ? "font-bold text-attention" : "font-medium text-ink-deep"}>{value}</dd>
    </div>
  );
}

export interface WaterfallStep {
  key: string;
  label: string;
  value: number;
  kind: "start" | "delta" | "end";
}
/** 비중 변화 폭포 막대 — 처음(회색) → 항목별 증감(옅은 보라, 떠 있는 막대) → 끝(primary) */
export function Waterfall({ steps, decimals = 2, height = 200, ariaLabel }: { steps: WaterfallStep[]; decimals?: number; height?: number; ariaLabel: string }) {
  const start = steps.find((s) => s.kind === "start")?.value ?? 0;
  const end = steps.find((s) => s.kind === "end")?.value ?? start;
  const range = Math.abs(end - start) || 1;
  const mag = 10 ** Math.floor(Math.log10(range));
  const step = range / mag < 2 ? mag / 2 : mag;
  const lo = Math.floor(Math.min(start, end) / step) * step;
  const hi = Math.ceil(Math.max(start, end) / step) * step + (Math.max(start, end) % step === 0 ? step : 0);
  const ticks = Array.from({ length: Math.round((hi - lo) / step) + 1 }, (_, k) => lo + k * step);
  // 항목별 증감의 누적 — 각 막대는 앞 항목까지의 합에서 시작한다
  const prefix = steps.map((_, k) => start + steps.slice(0, k).reduce((a, x) => a + (x.kind === "delta" ? x.value : 0), 0));
  const bars = steps.map((s, k) => {
    if (s.kind !== "delta") return { s, from: lo, to: s.value, text: `${fmtNum(s.value, decimals)}%`, bar: true };
    const from = prefix[k];
    const to = from + s.value;
    // 증감이 0 이면 막대 없이 그 자리에 '0' 하나만
    return { s, from: Math.min(from, to), to: Math.max(from, to), text: isBarValue(s.value) ? fmtNum(s.value, decimals, true) : ZERO_LABEL, bar: isBarValue(s.value) };
  });
  const y = (v: number) => at(v, lo, hi);
  return (
    <div role="img" aria-label={ariaLabel} className="flex">
      <div className="relative w-9 shrink-0" style={{ height }} aria-hidden="true">
        {ticks.map((t) => (
          <span key={t} className="tnum absolute right-2 translate-y-1/2 text-[10px] text-steel" style={{ bottom: `${y(t)}%` }}>
            {fmtNum(t, 1)}
          </span>
        ))}
      </div>
      <div className="min-w-0 flex-1">
        <div className="relative" style={{ height }}>
          {ticks.map((t, k) => (
            <span key={t} aria-hidden="true" className={clsx("absolute inset-x-0 h-px", k === 0 ? "bg-chart-axis" : "bg-chart-grid")} style={{ bottom: `${y(t)}%` }} />
          ))}
          <div className="absolute inset-0 flex">
            {bars.map((b, i) => (
              <div key={b.s.key} className="relative flex-1">
                {b.bar ? (
                  <span
                    className={clsx("absolute inset-x-0 mx-auto w-[46%] max-w-[64px] origin-bottom motion-safe:animate-grow-y", y(b.from) <= 0 ? "rounded-t-[3px]" : "rounded-[3px]", b.s.kind === "start" ? "bg-icon" : b.s.kind === "end" ? "bg-primary" : "bg-info-line")}
                    style={{ bottom: `${y(b.from)}%`, height: `${Math.max(0.5, y(b.to) - y(b.from))}%`, ...order(i) }}
                  />
                ) : null}
                <span className={clsx("tnum absolute left-1/2 -translate-x-1/2 whitespace-nowrap text-[11px]", b.s.kind === "end" ? "font-bold text-primary-deep" : "text-slate")} style={{ bottom: `calc(${y(b.to)}% + 3px)` }}>
                  {b.text}
                </span>
              </div>
            ))}
          </div>
        </div>
        <div className="flex">
          {bars.map((b) => (
            <span key={b.s.key} className="flex-1 pb-1 pt-1.5 text-center text-[11px] font-medium text-ink-deep">
              {b.s.label}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
