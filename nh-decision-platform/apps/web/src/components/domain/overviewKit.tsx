"use client";

import type { ReactNode } from "react";
import clsx from "clsx";
import { useUi } from "@/components/providers/UiProvider";
import { UNIT_LABEL, formatSignedValue, formatValue } from "@/lib/format";
import { NO_VALUE } from "@/lib/period";
import { decimalsOf, useRollingNumber } from "@/lib/useRollingNumber";
import type { Figure } from "@/lib/types";

/**
 * 1단계 현황 공용 조각 (시안 3) — 종합기획부 경영 현황·목표(/hq/overview) · 사업부서 현황(/risk)이 같이 쓴다.
 * 태그 · 큰 숫자(롤링) · 요약 타일 · 항목 상태 표시 · 띠 칸 세로 격자.
 */

export type Tone = "neutral" | "info" | "success" | "attention" | "critical";

/** 태그 — 높이 22 · 좌우 8 · 12px Bold (시안 3) */
export const TAG_TONE: Record<Tone, string> = {
  neutral: "bg-track text-steel",
  info: "bg-info-soft text-primary",
  success: "bg-track text-steel",
  attention: "bg-attention-soft text-attention",
  critical: "bg-critical-soft text-critical",
};
export function Tag({ tone, children }: { tone: Tone; children: ReactNode }) {
  return <span className={clsx("inline-flex h-[22px] items-center whitespace-nowrap rounded-pill px-2 text-[12px] font-bold", TAG_TONE[tone])}>{children}</span>;
}

/** 큰 숫자 — 숫자 Bold, 단위 60% · Bold · neutral/600. 누르면 계산 추적
 *  valueClass: 숫자 색(문제 값만 상태 색) · unitLabel: 단위 표기 바꾸기(예: '개 모형') */
export function Fig({ figure, size, signed, valueClass, unitLabel }: { figure: Figure; size: number; signed?: boolean; valueClass?: string; unitLabel?: string }) {
  const { openDrawer } = useUi();
  const missing = figure.value === null || figure.value === undefined;
  const body = signed ? formatSignedValue(figure) : formatValue(figure);
  // 큰 숫자 롤링 — 그리는 글자만 돌고, 이름 · 계산 추적은 최종 값 그대로
  const rolling = useRollingNumber(missing ? null : figure.value, decimalsOf(body));
  const shownFigure = rolling === null ? figure : { ...figure, value: rolling };
  const shownBody = missing ? body : signed ? formatSignedValue(shownFigure) : formatValue(shownFigure);
  const unit = missing ? "" : (unitLabel ?? UNIT_LABEL[figure.unit]);
  return (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation();
        openDrawer({ kind: "calc", title: figure.label, figure });
      }}
      aria-label={`${figure.label} ${body}${unit} — 계산 추적 보기`}
      className={clsx("tnum w-fit cursor-pointer text-left font-bold leading-[1.15] decoration-icon decoration-dotted decoration-1 underline-offset-4 hover:underline", missing ? "text-steel" : (valueClass ?? "text-ink-deep"))}
      style={{ fontSize: size }}
    >
      <span aria-hidden="true">{shownBody}</span>
      {unit ? (
        <span className="ml-[0.12em] font-bold text-steel" style={{ fontSize: "0.6em" }}>
          {unit}
        </span>
      ) : null}
    </button>
  );
}

/** 요약 타일 — neutral/50 · 60px · 라벨 11 · 값 18 Bold + 단위 11 */
export function SummaryTile({ label, figure, signed, valueClass }: { label: string; figure?: Figure | null; signed?: boolean; valueClass?: string }) {
  return (
    <div className="flex h-[60px] flex-col rounded-lg bg-surface-soft px-3 pt-2.5">
      <dt className="text-[11px] leading-4 text-steel">{label}</dt>
      <dd className="mt-0.5">{figure ? <Fig figure={figure} size={18} signed={signed} valueClass={valueClass} /> : <span className="text-[18px] font-bold text-steel">{NO_VALUE}</span>}</dd>
    </div>
  );
}

/** 항목별 상태 — 6px 점 + 11px 색 글자, 항목 이름 뒤에 둔다 (태그는 화면·부문 대표 판정에만) */
export type MarkTone = "neutral" | "attention" | "critical";
const MARK: Record<MarkTone, { dot: string; text: string }> = {
  neutral: { dot: "bg-hairline", text: "text-steel" },
  attention: { dot: "bg-attention", text: "text-attention" },
  critical: { dot: "bg-critical", text: "text-critical" },
};
export function StatusMark({ tone, label }: { tone: MarkTone; label: string }) {
  const m = MARK[tone] ?? MARK.neutral;
  return (
    <span className={clsx("inline-flex items-center gap-1 whitespace-nowrap text-[11px] font-bold", m.text)}>
      <span aria-hidden="true" className={clsx("h-1.5 w-1.5 rounded-circle", m.dot)} />
      {label}
    </span>
  );
}

/** 띠 칸 공통 세로 격자 — 대표 칸과 3칸이 같은 위·아래 여백(19 / 17px)과 줄 위치를 쓴다.
 *  제목 줄(22px) 위 고정 · 값은 가운데 영역(flex-1) · 막대(6px 줄) · 설명 줄(17px) 아래 고정 */
export const BAND_CELL = "flex h-full min-w-0 flex-col pb-[17px] pt-[19px]";
export const BAND_FOOT = "mt-2.5 flex h-[17px] items-baseline justify-between whitespace-nowrap text-[12px] leading-[17px] text-steel";
