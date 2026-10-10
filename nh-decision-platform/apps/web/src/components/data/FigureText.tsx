"use client";

import { useState } from "react";
import clsx from "clsx";
import { useUi } from "@/components/providers/UiProvider";
import { formatFigure, formatSigned } from "@/lib/format";
import type { Figure } from "@/lib/types";

/**
 * 추적 가능한 수치 (요구사항 PRIN-05 / UX-03).
 * hover·focus 로 수식 요약, click 으로 전체 계산 추적을 연다.
 * 실제 시스템에서는 metric_value_id / calc_id 를 가리키는 토큰이 이 컴포넌트로 렌더된다.
 */
export function FigureText({
  figure,
  signed,
  className,
  strong,
}: {
  figure: Figure;
  signed?: boolean;
  className?: string;
  strong?: boolean;
}) {
  const { openDrawer } = useUi();
  const [hint, setHint] = useState(false);
  const text = signed ? formatSigned(figure) : formatFigure(figure);
  const undefinedValue = figure.value === null || figure.value === undefined;

  return (
    <span className="relative inline-block">
      <button
        type="button"
        onClick={() => openDrawer({ kind: "calc", title: figure.label, figure })}
        onMouseEnter={() => setHint(true)}
        onMouseLeave={() => setHint(false)}
        onFocus={() => setHint(true)}
        onBlur={() => setHint(false)}
        aria-label={`${figure.label} ${text} — 계산 추적 보기`}
        className={clsx(
          "figure-traceable tnum text-left",
          undefinedValue ? "text-stone" : strong ? "font-bold text-ink-deep" : "font-bold text-ink",
          className,
        )}
      >
        {text}
      </button>
      {hint ? (
        <span
          role="tooltip"
          className="absolute left-0 top-[calc(100%+6px)] z-40 block w-[280px] rounded-lg border border-hairline-soft bg-canvas p-3 text-left shadow-pop"
        >
          <span className="block text-[11px] font-bold text-steel">{figure.label}</span>
          {figure.calc ? (
            <>
              <span className="mt-1 block font-mono text-[11px] leading-snug text-ink">{figure.calc.expression}</span>
              <span className="mt-1.5 block text-[10.5px] text-stone">
                {figure.calc.formulaId} v{figure.calc.formulaVersion} · 입력 {figure.calc.inputs.length}건
              </span>
            </>
          ) : figure.sourceRef ? (
            <span className="mt-1 block break-all font-mono text-[10.5px] leading-snug text-stone">
              {figure.sourceRef}
            </span>
          ) : (
            <span className="mt-1 block text-[11px] text-stone">계산 추적 정보 없음</span>
          )}
          <span className="mt-1.5 block text-[10.5px] font-bold text-primary">클릭 — 전체 계산 추적 보기</span>
        </span>
      ) : null}
    </span>
  );
}

/** 증감 방향에 따라 색을 입힌 수치 */
export function DeltaFigure({
  figure,
  positiveIsGood = true,
  className,
}: {
  figure: Figure;
  positiveIsGood?: boolean;
  className?: string;
}) {
  const value = figure.value ?? 0;
  const tone =
    value === 0
      ? "text-charcoal"
      : (value > 0 ? positiveIsGood : !positiveIsGood)
        ? "text-success"
        : "text-critical";
  return <FigureText figure={figure} signed className={clsx(tone, className)} />;
}
