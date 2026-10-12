import clsx from "clsx";
import Link from "next/link";
import type { ReactNode } from "react";

/**
 * 통계 카드 (C.1 · UX-20) — 값 하나와 보조 설명. 관리자 홈 · 모니터링 개요 · 처리할 일에 쓴다.
 * tone 은 값의 상태(정상 · 주의 · 위험)를 왼쪽 띠와 값 색으로만 알린다(색만으로 의미를 전하지 않도록 hint 에 글로도 쓴다).
 */
export type StatTone = "default" | "success" | "attention" | "critical" | "info";

const TONE_BAR: Record<StatTone, string> = {
  default: "bg-hairline",
  info: "bg-primary",
  success: "bg-success",
  attention: "bg-attention",
  critical: "bg-critical",
};
const TONE_TEXT: Record<StatTone, string> = {
  default: "text-ink-deep",
  info: "text-primary",
  success: "text-success",
  attention: "text-attention",
  critical: "text-critical",
};

export function StatCard({
  label,
  value,
  unit,
  hint,
  tone = "default",
  href,
  footer,
  dataKey,
}: {
  label: ReactNode;
  value: ReactNode;
  unit?: ReactNode;
  hint?: ReactNode;
  tone?: StatTone;
  href?: string;
  footer?: ReactNode;
  /** 시험 · 자동화용 식별자 (data-stat) */
  dataKey?: string;
}) {
  const body = (
    <>
      <span aria-hidden="true" className={clsx("absolute inset-y-3 left-0 w-1 rounded-r-pill", TONE_BAR[tone])} />
      <span className="block text-[12px] font-bold text-steel">{label}</span>
      <span className="mt-1.5 flex items-baseline gap-1">
        <span className={clsx("text-[26px] font-bold leading-none tnum", TONE_TEXT[tone])}>{value}</span>
        {unit ? <span className="text-[12.5px] font-bold text-steel">{unit}</span> : null}
      </span>
      {hint ? <span className="mt-1.5 block text-[12px] leading-snug text-stone">{hint}</span> : null}
      {footer ? <span className="mt-2 block">{footer}</span> : null}
    </>
  );
  const cls = "relative block overflow-hidden rounded-2xl border border-hairline-soft bg-canvas py-base pl-lg pr-base";
  return href ? (
    <Link href={href} className={clsx(cls, "transition-colors active:bg-surface-soft")} data-stat={dataKey}>
      {body}
    </Link>
  ) : (
    <div className={cls} data-stat={dataKey}>
      {body}
    </div>
  );
}

/** 통계 카드 묶음 — 화면 폭에 따라 2 · 3 · 4 · 6 열 */
export function StatGrid({ children, columns = 4, label }: { children: ReactNode; columns?: 2 | 3 | 4 | 6; label?: string }) {
  return (
    <section
      aria-label={label}
      className={clsx(
        "grid grid-cols-1 gap-md sm:grid-cols-2",
        columns === 3 && "lg:grid-cols-3",
        columns === 4 && "lg:grid-cols-4",
        columns === 6 && "lg:grid-cols-3 xl:grid-cols-6",
      )}
    >
      {children}
    </section>
  );
}
