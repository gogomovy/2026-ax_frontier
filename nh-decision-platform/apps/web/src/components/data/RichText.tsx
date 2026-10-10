"use client";

import type { ReactNode } from "react";
import clsx from "clsx";
import { FigureText } from "./FigureText";
import { TermText } from "./TermText";
import type { Figure } from "@/lib/types";

/**
 * 인라인 마커 렌더러.
 *   [[fig:ID]]            → 추적 가능한 수치 (PRIN-05)
 *   {{term:CODE|표시어}}  → 용어 도움말 (UX-04)
 *
 * Agent 서술문은 리터럴 숫자를 쓰지 않고 이 마커만 생성한다.
 * 마커에 대응하는 Figure 가 없으면 경고 형태로 표시해 누락을 드러낸다.
 */
const TOKEN = /(\[\[fig:[a-zA-Z0-9_\-]+\]\]|\{\{term:[A-Z_0-9]+(?:\|[^}]+)?\}\})/g;

export function RichText({
  text,
  figures,
  className,
  as = "p",
}: {
  text: string;
  figures?: Record<string, Figure>;
  className?: string;
  as?: "p" | "span" | "div";
}) {
  const Tag = as;
  return <Tag className={className}>{renderRich(text, figures)}</Tag>;
}

export function renderRich(text: string, figures?: Record<string, Figure>): ReactNode[] {
  const parts = text.split(TOKEN).filter((p) => p !== "");
  return parts.map((part, index) => {
    const figMatch = part.match(/^\[\[fig:([a-zA-Z0-9_\-]+)\]\]$/);
    if (figMatch) {
      const figure = figures?.[figMatch[1]];
      if (!figure) {
        return (
          <span
            key={index}
            className="rounded-sm bg-[rgba(228,30,63,0.1)] px-1 text-[11px] font-bold text-critical"
            title="참조된 수치를 찾을 수 없습니다(검증 실패 대상)"
          >
            수치 참조 누락: {figMatch[1]}
          </span>
        );
      }
      return <FigureText key={index} figure={figure} />;
    }

    const termMatch = part.match(/^\{\{term:([A-Z_0-9]+)(?:\|([^}]+))?\}\}$/);
    if (termMatch) {
      return <TermText key={index} code={termMatch[1]} label={termMatch[2]} />;
    }

    return <span key={index}>{part}</span>;
  });
}

/** 본문 단락용 기본 스타일 */
export function Prose({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={clsx("text-[13.5px] leading-relaxed text-charcoal", className)}>{children}</div>;
}
