"use client";

import { useState } from "react";
import clsx from "clsx";
import type { SeriesPoint } from "@/lib/types";

/**
 * 비중 가로 막대 — 기간마다 막대 하나, 왼쪽 보라 = 대상 비중, 오른쪽 회색 = 그 밖.
 * 오래된 기간은 옅은 보라(primary/200), 최신 기간은 진한 보라 + Bold. 50% 기준선을 세로로 그린다.
 * 막대에 올리거나 키보드로 옮기면 전년 대비 증감을 말풍선으로 보여 준다.
 */
export function ShareBars({
  points,
  targetName,
  otherName,
  referenceAt = 50,
  decimals = 2,
}: {
  points: SeriesPoint[];
  targetName: string;
  otherName: string;
  /** 기준선 위치(%) */
  referenceAt?: number;
  decimals?: number;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const fmt = (v: number) => v.toFixed(decimals);
  const lastIndex = points.length - 1;

  return (
    <div className="relative">
      <ul className="relative flex flex-col gap-3 pl-[64px] pr-1" onMouseLeave={() => setHover(null)}>
        {/* 50% 기준선 */}
        <span aria-hidden="true" className="pointer-events-none absolute bottom-6 top-0 z-10 w-px bg-ink-deep opacity-70" style={{ left: `calc(64px + (100% - 64px - 4px) * ${referenceAt / 100})` }} />
        {points.map((p, i) => {
          const v = p.value ?? 0;
          const latest = i === lastIndex;
          return (
            <li key={p.label} className="relative">
              <span className={clsx("absolute -left-[64px] top-1/2 w-[56px] -translate-y-1/2 text-right text-[12px] tnum", latest ? "font-bold text-ink-deep" : "text-steel")}>{p.label}</span>
              <button
                type="button"
                onMouseEnter={() => setHover(i)}
                onFocus={() => setHover(i)}
                onBlur={() => setHover(null)}
                aria-label={`${p.label} ${targetName} ${fmt(v)}%, ${otherName} ${fmt(100 - v)}%`}
                className="flex h-9 w-full overflow-hidden rounded-md bg-track text-left"
              >
                <span
                  className={clsx("flex h-full items-center px-3 text-[14px] font-bold tnum", latest ? "bg-primary text-white" : "bg-primary-soft text-primary")}
                  style={{ width: `${v}%` }}
                >
                  {fmt(v)}%
                </span>
                <span className="ml-auto flex items-center px-3 text-[12px] text-steel tnum">{fmt(100 - v)}%</span>
              </button>
            </li>
          );
        })}
        <li aria-hidden="true" className="relative h-4">
          <span className="absolute -translate-x-1/2 text-[12px] font-bold text-ink-deep" style={{ left: `${referenceAt}%` }}>
            {referenceAt}%
          </span>
        </li>
      </ul>

      {hover !== null ? (
        <div role="status" className="pointer-events-none absolute right-2 z-20 w-[210px] rounded-lg bg-ink-deep p-3 text-white shadow-tooltip" style={{ top: `${hover * 48 + 40}px` }}>
          <p className="text-[12px] text-white/75">
            {points[hover].label} · {targetName}
          </p>
          <p className="tnum mt-0.5 text-[20px] font-bold leading-[1.25]">
            {fmt(points[hover].value ?? 0)}
            <span className="ml-0.5 text-[12px] font-medium text-white/75">%</span>
          </p>
          {hover > 0 ? (
            <dl className="mt-2 flex flex-col gap-1 border-t border-white/20 pt-2 text-[12px]">
              <div className="flex justify-between gap-3">
                <dt className="text-white/75">전기 대비</dt>
                <dd className="tnum font-bold">
                  {((points[hover].value ?? 0) - (points[hover - 1].value ?? 0)) > 0 ? "+" : ""}
                  {((points[hover].value ?? 0) - (points[hover - 1].value ?? 0)).toFixed(decimals)}%p
                </dd>
              </div>
              {hover === lastIndex && points.length > 2 ? (
                <div className="flex justify-between gap-3">
                  <dt className="text-white/75">{points.length}개 시점</dt>
                  <dd className="tnum font-bold">
                    {fmt(points[0].value ?? 0)} → {fmt(points[lastIndex].value ?? 0)}
                  </dd>
                </div>
              ) : null}
            </dl>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
