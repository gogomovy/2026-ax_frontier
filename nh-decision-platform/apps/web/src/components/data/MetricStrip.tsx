"use client";

import clsx from "clsx";
import { DeltaFigure, FigureText } from "@/components/data/FigureText";
import type { Figure } from "@/lib/types";

export interface MetricStripItem {
  label: string;
  figure: Figure;
  caption?: string;
  /** 전년 동기 대비 등 증감 수치 */
  delta?: Figure;
  positiveIsGood?: boolean;
  /** 부호를 붙여 표시할지 */
  signed?: boolean;
  tone?: "default" | "attention" | "critical";
}

/**
 * 핵심 지표 스트립.
 * 카드를 여러 장 나열하는 대신 한 덩어리로 묶어 화면 밀도를 낮춘다(전 화면 공통 패턴).
 * 주의·위험 지표는 라벨 앞 점과 값 색으로만 구분한다.
 */
export function MetricStrip({ items, columns = 4 }: { items: MetricStripItem[]; columns?: 3 | 4 }) {
  return (
    <div
      className={clsx(
        "grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-hairline-soft bg-hairline-soft",
        columns === 4 ? "lg:grid-cols-4" : "lg:grid-cols-3",
      )}
    >
      {items.map((item) => (
        <div key={item.label} className="bg-canvas px-6 py-5">
          <p className="flex items-center gap-1.5 text-[14px] text-steel">
            {item.tone === "attention" || item.tone === "critical" ? (
              <span aria-hidden="true" className={clsx("h-[7px] w-[7px] rounded-circle", item.tone === "critical" ? "bg-critical" : "bg-attention")} />
            ) : null}
            {item.label}
          </p>
          <p className={clsx("mt-2 text-[24px] font-bold leading-[1.25]", item.tone === "critical" ? "text-critical" : "text-ink-deep")}>
            <FigureText figure={item.figure} signed={item.signed} strong plain className={item.tone === "critical" ? "!text-critical" : undefined} />
          </p>
          <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[12px] text-steel">
            {item.delta ? (
              <span>
                전년 동기 <DeltaFigure figure={item.delta} positiveIsGood={item.positiveIsGood ?? true} plain />
              </span>
            ) : null}
            {item.caption ? <span>{item.caption}</span> : null}
          </div>
        </div>
      ))}
    </div>
  );
}
