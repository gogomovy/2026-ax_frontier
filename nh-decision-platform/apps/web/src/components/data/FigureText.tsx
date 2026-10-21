"use client";

import { useRef, useState } from "react";
import clsx from "clsx";
import { useUi } from "@/components/providers/UiProvider";
import { FloatingTip } from "@/components/ui/FloatingTip";
import { formatFigure, formatSigned, formatSignedValue, formatValue } from "@/lib/format";
import { basisNotes } from "@/lib/periodBasis";
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
  plain,
  bare,
}: {
  figure: Figure;
  signed?: boolean;
  className?: string;
  strong?: boolean;
  /** 단위 없이 숫자만 (표 머리에 단위를 적은 표) */
  bare?: boolean;
  /** 점선 밑줄 없이 그린다(표 · 큰 숫자) — 누르면 계산 추적이 열리는 것은 같다 */
  plain?: boolean;
}) {
  const { openDrawer } = useUi();
  const [hint, setHint] = useState(false);
  const anchor = useRef<HTMLButtonElement>(null);
  const text = bare ? (signed ? formatSignedValue(figure) : formatValue(figure)) : signed ? formatSigned(figure) : formatFigure(figure);
  const undefinedValue = figure.value === null || figure.value === undefined;
  const notes = basisNotes(figure);

  return (
    <span className="relative inline-block">
      <button
        ref={anchor}
        type="button"
        onClick={() => openDrawer({ kind: "calc", title: figure.label, figure })}
        onMouseEnter={() => setHint(true)}
        onMouseLeave={() => setHint(false)}
        onFocus={() => setHint(true)}
        onBlur={() => setHint(false)}
        aria-label={`${figure.label} ${text}${figure.stale ? " (갱신 실패 — 이전 값)" : ""}${notes.length ? ` (${notes.join(" · ")})` : ""} — 계산 추적 보기`}
        className={clsx(
          plain ? "cursor-pointer decoration-icon decoration-dotted decoration-1 underline-offset-4 hover:underline" : "figure-traceable",
          "tnum text-left",
          undefinedValue ? "text-stone" : strong ? "font-bold text-ink-deep" : "font-bold text-ink",
          className,
        )}
      >
        {text}
        {figure.stale ? (
          <span aria-hidden className="ml-0.5 align-super text-[9px] font-bold text-critical" title="최근 계산 실패 — 이전 값">
            !
          </span>
        ) : null}
        {notes.length && !figure.stale ? (
          <span aria-hidden className="ml-0.5 align-super text-[9px] font-bold text-attention" title={notes.join(" · ")}>
            *
          </span>
        ) : null}
      </button>
      {/* 카드 · 표 밖으로 꺼내 그린다(잘리지 않게) */}
      <FloatingTip anchor={anchor} open={hint} width={280} className="block rounded-lg border border-hairline-soft bg-canvas p-3 text-left font-normal shadow-tooltip">
        <span>
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
          {notes.map((n) => (
            <span key={n} className="mt-1.5 block text-[10.5px] leading-snug text-attention">
              비교 기준 · {n}
            </span>
          ))}
          <span className="mt-1.5 block text-[10.5px] font-bold text-primary">클릭 — 전체 계산 추적 보기</span>
        </span>
      </FloatingTip>
    </span>
  );
}

/** 증감 방향에 따라 색을 입힌 수치 */
export function DeltaFigure({
  figure,
  positiveIsGood = true,
  className,
  plain,
}: {
  figure: Figure;
  positiveIsGood?: boolean;
  className?: string;
  plain?: boolean;
}) {
  const value = figure.value ?? 0;
  // 색은 문제가 되는 값에만 — 좋은 방향은 본문색, 나쁜 방향만 위험색
  const bad = value !== 0 && (value > 0 ? !positiveIsGood : positiveIsGood);
  return <FigureText figure={figure} signed plain={plain} className={clsx(bad ? "text-critical" : value === 0 ? "text-steel" : "text-ink-deep", className)} />;
}
