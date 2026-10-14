"use client";

import { useState, type CSSProperties } from "react";
import clsx from "clsx";
import type { SeriesPoint } from "@/lib/types";

/**
 * 비중 가로 막대 — 기간마다 막대 하나, 왼쪽 보라 = 대상 비중, 오른쪽 회색 = 그 밖.
 * 오래된 기간은 옅은 보라(primary/200), 최신 기간은 진한 보라 + Bold. 기준선(관리자 [화면 설정 › 구성비 기준선])을 세로로 그린다.
 * 화면이 열릴 때 막대가 왼쪽에서 차오른다(동작 줄이기 설정이면 없음 · Phase K · ANI-01).
 * 막대에 올리거나 키보드로 옮기면 전년 대비 증감을 말풍선으로 보여 준다.
 */
export function ShareBars({
  points,
  targetName,
  otherName,
  referenceAt = null,
  decimals = 2,
}: {
  points: SeriesPoint[];
  targetName: string;
  otherName: string;
  /** 기준선 위치(%) — 없으면 그리지 않는다 */
  referenceAt?: number | null;
  decimals?: number;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const fmt = (v: number) => v.toFixed(decimals);
  const lastIndex = points.length - 1;
  const ref = typeof referenceAt === "number" && referenceAt > 0 && referenceAt < 100 ? referenceAt : null;

  return (
    <div className="relative">
      <ul className="relative flex flex-col gap-3 pl-[64px] pr-1" onMouseLeave={() => setHover(null)}>
        {ref !== null ? (
          <span aria-hidden="true" className="pointer-events-none absolute bottom-6 top-0 z-10 w-px bg-ink-deep opacity-70" style={{ left: `calc(64px + (100% - 64px - 4px) * ${ref / 100})` }} />
        ) : null}
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
                className="flex h-9 w-full overflow-hidden rounded-md bg-track text-left"
              >
                {/* 버튼 이름 = 보이는 수치 + 낭독용 시점 · 계열 이름 (보이는 글자가 이름에 그대로 — WCAG 2.5.3) */}
                <span className="sr-only">
                  {p.label} {targetName}{" "}
                </span>
                <span
                  className={clsx("flex h-full origin-left items-center px-3 text-[14px] font-bold tnum motion-safe:animate-grow-x", latest ? "bg-primary text-white" : "bg-primary-soft text-primary")}
                  style={{ width: `${v}%`, "--i": i } as CSSProperties}
                >
                  {fmt(v)}%
                </span>
                <span className="sr-only">, {otherName} </span>
                <span className="ml-auto flex items-center px-3 text-[12px] text-steel tnum">{fmt(100 - v)}%</span>
              </button>
            </li>
          );
        })}
        {ref !== null ? (
          <li aria-hidden="true" className="relative h-4">
            <span className="absolute -translate-x-1/2 text-[12px] font-bold text-ink-deep" style={{ left: `${ref}%` }}>
              {ref}%
            </span>
          </li>
        ) : null}
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
