import clsx from "clsx";
import Link from "next/link";
import type { ReactNode } from "react";
import type { Severity } from "@/lib/types";

/* ── Badge ─────────────────────────────────────────────────── */
type BadgeTone = "neutral" | "info" | "success" | "attention" | "warning" | "critical" | "primary" | "dark";

const BADGE_TONE: Record<BadgeTone, string> = {
  neutral: "bg-surface-soft text-steel",
  info: "bg-[rgba(0,100,224,0.1)] text-primary",
  success: "bg-[rgba(49,162,76,0.12)] text-success",
  attention: "bg-[rgba(242,169,24,0.16)] text-[#8a5d00]",
  warning: "bg-[rgba(247,185,40,0.2)] text-[#7a5600]",
  critical: "bg-[rgba(228,30,63,0.1)] text-critical",
  primary: "bg-primary text-white",
  dark: "bg-ink-deep text-white",
};

export function Badge({
  children,
  tone = "neutral",
  className,
  icon,
}: {
  children: ReactNode;
  tone?: BadgeTone;
  className?: string;
  icon?: ReactNode;
}) {
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 rounded-pill px-2.5 py-1 text-[11px] font-bold leading-none whitespace-nowrap",
        BADGE_TONE[tone],
        className,
      )}
    >
      {icon}
      {children}
    </span>
  );
}

export const SEVERITY_TONE: Record<Severity, BadgeTone> = {
  info: "success",
  watch: "info",
  caution: "attention",
  critical: "critical",
};

export const SEVERITY_TEXT: Record<Severity, string> = {
  info: "정상",
  watch: "관찰",
  caution: "주의",
  critical: "긴급",
};

export function SeverityBadge({ severity }: { severity: Severity }) {
  return <Badge tone={SEVERITY_TONE[severity]}>{SEVERITY_TEXT[severity]}</Badge>;
}

/* ── Button ────────────────────────────────────────────────── */
type ButtonVariant = "primary" | "confirm" | "secondary" | "ghost" | "quiet";

const BUTTON_VARIANT: Record<ButtonVariant, string> = {
  // 마케팅 primary(검정 pill) → 일반 주요 액션
  primary: "bg-ink-button text-white active:bg-charcoal",
  // commerce CTA(코발트) → 확정·승인 액션
  confirm: "bg-primary text-white active:bg-primary-deep",
  secondary: "bg-transparent text-ink-deep border-2 border-ink-deep",
  ghost: "bg-transparent text-ink-deep border-2 border-[rgba(10,19,23,0.12)]",
  quiet: "bg-surface-soft text-charcoal",
};

type ButtonProps = {
  children: ReactNode;
  variant?: ButtonVariant;
  size?: "sm" | "md";
  className?: string;
  disabled?: boolean;
  onClick?: () => void;
  type?: "button" | "submit";
  title?: string;
};

export function Button({
  children,
  variant = "primary",
  size = "md",
  className,
  disabled,
  onClick,
  type = "button",
  title,
}: ButtonProps) {
  return (
    <button
      type={type}
      title={title}
      disabled={disabled}
      onClick={onClick}
      className={clsx(
        "inline-flex items-center justify-center gap-1.5 rounded-pill font-bold transition-colors",
        size === "md" ? "px-6 py-2.5 text-[13px]" : "px-4 py-2 text-[12px]",
        BUTTON_VARIANT[variant],
        disabled && "cursor-not-allowed bg-disabled text-white border-transparent",
        className,
      )}
    >
      {children}
    </button>
  );
}

export function LinkButton({
  href,
  children,
  variant = "primary",
  size = "md",
  className,
}: {
  href: string;
  children: ReactNode;
  variant?: ButtonVariant;
  size?: "sm" | "md";
  className?: string;
}) {
  return (
    <Link
      href={href}
      className={clsx(
        "inline-flex items-center justify-center gap-1.5 rounded-pill font-bold transition-colors",
        size === "md" ? "px-6 py-2.5 text-[13px]" : "px-4 py-2 text-[12px]",
        BUTTON_VARIANT[variant],
        className,
      )}
    >
      {children}
    </Link>
  );
}

/**
 * 작업 화면용 섹션 머리말. 제목·보조설명을 한 줄에 두고 우측에 링크 하나만 허용한다.
 * (설명 문단을 별도 줄로 늘리지 않아 화면 밀도를 낮춘다)
 */
export function SectionHead({
  title,
  hint,
  right,
  id,
}: {
  title: ReactNode;
  hint?: ReactNode;
  right?: ReactNode;
  id?: string;
}) {
  return (
    <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-base gap-y-1" id={id}>
      <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
        <h2 className="text-[16px] font-bold leading-snug text-ink-deep">{title}</h2>
        {hint ? <p className="text-[12px] leading-snug text-stone">{hint}</p> : null}
      </div>
      {right ? <div className="flex shrink-0 items-center gap-md">{right}</div> : null}
    </div>
  );
}

/** 섹션 우측의 텍스트 링크. 화면마다 버튼을 늘리지 않기 위해 사용한다. */
export function TextLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Link href={href} className="inline-flex items-center gap-1 text-[12px] font-bold text-primary">
      {children}
      <IconChevron />
    </Link>
  );
}


export function ProgressBar({
  value,
  tone = "primary",
  label,
}: {
  value: number;
  tone?: "primary" | "success" | "attention" | "critical";
  label?: string;
}) {
  const toneClass = {
    primary: "bg-primary",
    success: "bg-success",
    attention: "bg-attention",
    critical: "bg-critical",
  }[tone];
  return (
    <div>
      <div className="h-2 w-full overflow-hidden rounded-pill bg-surface-soft">
        <div className={clsx("h-full rounded-pill", toneClass)} style={{ width: `${Math.min(100, Math.max(0, value))}%` }} />
      </div>
      {label ? <p className="mt-1 text-[11px] text-steel">{label}</p> : null}
    </div>
  );
}

/* ── Table ─────────────────────────────────────────────────── */
export function DataTable({
  columns,
  children,
  caption,
  dense,
}: {
  columns: { key: string; label: ReactNode; align?: "left" | "right" | "center"; width?: string }[];
  children: ReactNode;
  caption?: ReactNode;
  dense?: boolean;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-[13px]">
        {caption ? <caption className="mb-2 text-left text-[12px] text-steel">{caption}</caption> : null}
        <thead>
          <tr className="border-y border-hairline-soft bg-surface-soft">
            {columns.map((c) => (
              <th
                key={c.key}
                scope="col"
                style={c.width ? { width: c.width } : undefined}
                className={clsx(
                  "whitespace-nowrap px-3 font-bold text-charcoal",
                  dense ? "py-2" : "py-2.5",
                  c.align === "right" && "text-right",
                  c.align === "center" && "text-center",
                  (!c.align || c.align === "left") && "text-left",
                )}
              >
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

export function Td({
  children,
  align = "left",
  className,
  strong,
}: {
  children: ReactNode;
  align?: "left" | "right" | "center";
  className?: string;
  strong?: boolean;
}) {
  return (
    <td
      className={clsx(
        "border-b border-hairline-soft px-3 py-2.5",
        align === "right" && "text-right tnum",
        align === "center" && "text-center",
        strong ? "font-bold text-ink-deep" : "text-charcoal",
        className,
      )}
    >
      {children}
    </td>
  );
}

/* ── Row list ──────────────────────────────────────────────── */
/** 목록 컨테이너 — 1겹 테두리 + 행 구분선. 행은 `.row-button` 버튼을 권장한다 */
export function RowList({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <ul className={clsx("divide-y divide-hairline-soft overflow-hidden rounded-2xl border border-hairline-soft", className)}>
      {children}
    </ul>
  );
}

export function RowEmpty({ title, description, action }: { title: string; description?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-1.5 rounded-2xl border border-dashed border-hairline px-xl py-xxl text-center">
      <p className="text-[13.5px] font-bold text-charcoal">{title}</p>
      {description ? <p className="max-w-[420px] text-[12.5px] leading-relaxed text-steel">{description}</p> : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}

/* ── Pill Tabs (button-pill-tab) ───────────────────────────── */
export interface PillTabItem<K extends string> {
  key: K;
  label: ReactNode;
  count?: number;
}

/** 화면 내부 탭. 비활성 = canvas + hairline, 활성 = ink-deep 채움 (디자인 시스템 button-pill-tab) */
export function PillTabs<K extends string>({
  items,
  value,
  onChange,
  label,
  size = "md",
}: {
  items: PillTabItem<K>[];
  value: K;
  onChange: (key: K) => void;
  label: string;
  size?: "sm" | "md";
}) {
  return (
    <div role="tablist" aria-label={label} className="flex flex-wrap items-center gap-1.5">
      {items.map((item) => {
        const on = item.key === value;
        return (
          <button
            key={item.key}
            type="button"
            role="tab"
            aria-selected={on}
            onClick={() => onChange(item.key)}
            className={clsx(
              "inline-flex items-center gap-1.5 rounded-pill font-bold transition-colors",
              size === "md" ? "px-4 py-2 text-[13px]" : "px-3 py-1.5 text-[12px]",
              on ? "bg-ink-deep text-white" : "border border-hairline bg-canvas text-ink",
            )}
          >
            {item.label}
            {item.count !== undefined ? (
              <span className={clsx("tnum text-[11px]", on ? "text-white/70" : "text-stone")}>{item.count}</span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}

/** 링크형 Pill Tabs — 탭마다 별도 URL 이 있는 경우 */
export function PillTabLinks({
  items,
  activeHref,
  label,
}: {
  items: { href: string; label: ReactNode; dot?: Severity }[];
  activeHref: string;
  label: string;
}) {
  return (
    <nav aria-label={label} className="flex flex-wrap items-center gap-1.5">
      {items.map((item) => {
        const on = item.href === activeHref;
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={on ? "page" : undefined}
            className={clsx(
              "inline-flex items-center gap-2 rounded-pill px-4 py-2 text-[13px] font-bold transition-colors",
              on ? "bg-ink-deep text-white" : "border border-hairline bg-canvas text-ink",
            )}
          >
            {item.dot ? <StatusDot severity={item.dot} /> : null}
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}

/* ── Switch ────────────────────────────────────────────────── */
export function Switch({
  checked,
  onChange,
  label,
  description,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  label: string;
  description?: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={(e) => {
        e.stopPropagation();
        onChange(!checked);
      }}
      className="inline-flex items-center gap-2.5 text-left"
    >
      <span
        aria-hidden="true"
        className={clsx(
          "relative inline-block h-5 w-9 shrink-0 rounded-pill transition-colors",
          checked ? "bg-success" : "bg-hairline",
        )}
      >
        <span
          className={clsx(
            "absolute top-0.5 h-4 w-4 rounded-circle bg-white shadow-panel transition-all",
            checked ? "left-[18px]" : "left-0.5",
          )}
        />
      </span>
      <span className="min-w-0">
        <span className={clsx("block text-[12.5px] font-bold", checked ? "text-ink-deep" : "text-steel")}>{label}</span>
        {description ? <span className="block text-[11px] text-stone">{description}</span> : null}
      </span>
    </button>
  );
}

/* ── Status dot ────────────────────────────────────────────── */
const DOT_TONE: Record<Severity, string> = {
  info: "bg-success",
  watch: "bg-primary",
  caution: "bg-attention",
  critical: "bg-critical",
};

export function StatusDot({ severity, className }: { severity: Severity; className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={clsx("inline-block h-2 w-2 shrink-0 rounded-circle", DOT_TONE[severity], className)}
    />
  );
}

/* ── Next step ─────────────────────────────────────────────── */
/** 화면 맨 아래에서 다음 단계 하나만 제안한다 */
export function NextStep({
  step,
  title,
  description,
  href,
}: {
  step: number;
  title: string;
  description: string;
  href: string;
}) {
  return (
    <Link
      href={href}
      className="group flex items-center gap-base rounded-2xl bg-ink-deep px-xl py-lg text-white"
    >
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-circle bg-white/15 text-[13px] font-bold">
        {step}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-[11.5px] font-bold text-white/60">다음 단계</span>
        <span className="block text-[15px] font-bold">{title}</span>
        <span className="mt-0.5 block text-[12.5px] text-white/70">{description}</span>
      </span>
      <IconArrowRight className="shrink-0 text-white/80" />
    </Link>
  );
}

/* ── Icons (inline SVG, 의존성 없음) ───────────────────────── */
export function IconArrowRight({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" width="16" height="16" className={className} aria-hidden="true">
      <path d="M3 8h10m0 0L9 4m4 4-4 4" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function IconClose({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" width="16" height="16" className={className} aria-hidden="true">
      <path d="M4 4l8 8M12 4l-8 8" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  );
}

export function IconMenu({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" width="18" height="18" className={className} aria-hidden="true">
      <path d="M2.5 4.5h11M2.5 8h11M2.5 11.5h11" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

export function IconPlus({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" width="14" height="14" className={className} aria-hidden="true">
      <path d="M8 3v10M3 8h10" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

export function IconDownload({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" width="14" height="14" className={className} aria-hidden="true">
      <path d="M8 2.5v8m0 0L4.8 7.3M8 10.5l3.2-3.2M3 13.5h10" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function IconChevron({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" width="14" height="14" className={className} aria-hidden="true">
      <path d="M6 3l5 5-5 5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function IconInfo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" width="13" height="13" className={className} aria-hidden="true">
      <circle cx="8" cy="8" r="6.6" fill="none" stroke="currentColor" strokeWidth="1.4" />
      <path d="M8 7.2v4M8 4.9v.9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

export function IconDoc({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" width="13" height="13" className={className} aria-hidden="true">
      <path d="M4 2h5l3 3v9H4z" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
      <path d="M9 2v3h3M6 8.5h4M6 11h4" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
    </svg>
  );
}

export function IconCalc({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" width="13" height="13" className={className} aria-hidden="true">
      <rect x="3" y="2" width="10" height="12" rx="1.6" fill="none" stroke="currentColor" strokeWidth="1.3" />
      <path d="M5.5 5.5h5M5.8 8.6h1.2M5.8 11h1.2M9.3 8.6h1.2M9.3 11h1.2" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
    </svg>
  );
}

export function IconArrowUp({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" width="13" height="13" className={className} aria-hidden="true">
      <path d="M8 13V4m0 0L4.5 7.5M8 4l3.5 3.5" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function IconCheck({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" width="13" height="13" className={className} aria-hidden="true">
      <path d="M3.5 8.5l3 3 6-7" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function IconWarn({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" width="13" height="13" className={className} aria-hidden="true">
      <path d="M8 2.5l5.5 10h-11z" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
      <path d="M8 6.4v3M8 10.9v.8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}
