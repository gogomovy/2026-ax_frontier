"use client";

import clsx from "clsx";
import { useUi } from "@/components/providers/UiProvider";
import { UNIT_LABEL, formatSignedValue, formatValue } from "@/lib/format";
import type { Figure } from "@/lib/types";

const SIZE = {
  hero: "text-[32px] leading-[1.2]",
  kpi: "text-[28px] leading-[1.2]",
  title: "text-[24px] leading-[1.25]",
  section: "text-[20px] leading-[1.25]",
  body: "text-[16px] leading-[1.4]",
} as const;

const TONE = {
  default: "text-ink-deep",
  primary: "text-primary",
  warning: "text-attention",
  danger: "text-critical",
  muted: "text-steel",
} as const;

/**
 * 큰 숫자 — 숫자는 Bold, 단위는 60% 크기 · neutral/600 (가이드 G02).
 * 눌러서 계산 추적을 열 수 있는 것은 FigureText 와 같다(모든 수치는 근거로 이어진다).
 */
export function BigFigure({
  figure,
  size = "title",
  tone = "default",
  signed,
  className,
}: {
  figure: Figure;
  size?: keyof typeof SIZE;
  tone?: keyof typeof TONE;
  signed?: boolean;
  className?: string;
}) {
  const { openDrawer } = useUi();
  const missing = figure.value === null || figure.value === undefined;
  const body = signed ? formatSignedValue(figure) : formatValue(figure);
  const unit = missing ? "" : UNIT_LABEL[figure.unit];
  return (
    <button
      type="button"
      onClick={() => openDrawer({ kind: "calc", title: figure.label, figure })}
      aria-label={`${figure.label} ${body}${unit} — 계산 추적 보기`}
      className={clsx(
        "tnum cursor-pointer text-left font-bold decoration-icon decoration-dotted underline-offset-[6px] hover:underline",
        SIZE[size],
        missing ? "text-steel" : TONE[tone],
        className,
      )}
    >
      {body}
      {unit ? <span className="num-unit">{unit}</span> : null}
    </button>
  );
}
