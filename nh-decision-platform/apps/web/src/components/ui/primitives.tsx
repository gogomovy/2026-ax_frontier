import clsx from "clsx";
import { ScrollRegion } from "./ScrollRegion";
import Link from "next/link";
import type { ReactNode } from "react";
import type { Severity } from "@/lib/types";

/* ── Badge ─────────────────────────────────────────────────── */
type BadgeTone = "neutral" | "info" | "success" | "attention" | "warning" | "critical" | "primary" | "dark";

/**
 * 태그 · 알약 = 상태 (누를 수 없음). 12px Bold · 연한 배경 + 진한 글자 (가이드 G04)
 *  neutral/100·600 확정·정상 · primary/100·700 AI 제안 · warning/50·700 미달·근접 · danger/50·700 한도 초과
 */
const BADGE_TONE: Record<BadgeTone, string> = {
  neutral: "bg-track text-steel",
  info: "bg-info-soft text-primary",
  success: "bg-track text-steel",
  attention: "bg-attention-soft text-attention",
  warning: "bg-warning-soft text-warning",
  critical: "bg-critical-soft text-critical",
  primary: "bg-info-soft text-primary",
  dark: "bg-track text-ink-deep",
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
        "inline-flex items-center gap-1 rounded-pill px-2.5 py-[3px] text-[12px] font-bold leading-[1.4] whitespace-nowrap",
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
type ButtonVariant = "primary" | "confirm" | "secondary" | "ghost" | "quiet" | "danger";

/**
 * 버튼 = 사각형(6px) = 누르는 것 (가이드 G04)
 *  메인(primary·confirm): primary/500 · 화면당 1개 / 보조(secondary·ghost): 흰 배경 + 테두리 / quiet: 도구 모음(hover neutral/50)
 */
const BUTTON_VARIANT: Record<ButtonVariant, string> = {
  primary: "border border-transparent bg-primary text-white hover:bg-primary-deep active:bg-primary-deep",
  confirm: "border border-transparent bg-primary text-white hover:bg-primary-deep active:bg-primary-deep",
  secondary: "border border-hairline bg-canvas text-ink-deep hover:bg-surface-soft active:bg-track",
  ghost: "border border-hairline bg-canvas text-ink-deep hover:bg-surface-soft active:bg-track",
  quiet: "border border-transparent bg-transparent text-charcoal hover:bg-surface-soft active:bg-track",
  // 되돌리기 어려운 작업 확인 (Phase E · INT-01)
  // 흰 글자 대비 4.5:1 — 레드닷 색(critical, 3.9:1)이 아니라 danger/700 을 바탕으로 쓴다 (자료 삭제 화면 접근성 점검에서 발견)
  danger: "border border-transparent bg-critical-strong text-white hover:bg-[#a52b30] active:bg-[#a52b30]",
};
// 꺼진 단추 — 변형 색과 섞이지 않게 변형 대신 쓴다(같은 bg-* 두 개면 CSS 순서로 켜진 색이 이겨 켜진 것처럼 보였다 · Phase E F4)
const BUTTON_DISABLED = "cursor-not-allowed border border-transparent bg-track text-steel opacity-70";
const BUTTON_SIZE = { md: "h-10 px-4 text-[14px]", sm: "h-8 px-3 text-[13px]" } as const;

type ButtonProps = {
  children: ReactNode;
  variant?: ButtonVariant;
  size?: "sm" | "md";
  className?: string;
  disabled?: boolean;
  onClick?: () => void;
  type?: "button" | "submit";
  title?: string;
  /** 접근성 이름 · 시험용 식별자 (aria-* · data-*) 는 그대로 넘긴다 (Phase C) */
  "aria-label"?: string;
  "aria-pressed"?: boolean;
  /** 못 누르는 이유 등 설명 연결 (Phase E · UXF-04) */
  "aria-describedby"?: string;
  [data: `data-${string}`]: string | number | boolean | undefined;
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
  ...rest
}: ButtonProps) {
  return (
    <button
      {...rest}
      type={type}
      title={title}
      disabled={disabled}
      onClick={onClick}
      className={clsx(
        "inline-flex shrink-0 items-center justify-center gap-1.5 whitespace-nowrap rounded-md font-bold transition-colors",
        BUTTON_SIZE[size],
        disabled ? BUTTON_DISABLED : BUTTON_VARIANT[variant],
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
        "inline-flex shrink-0 items-center justify-center gap-1.5 whitespace-nowrap rounded-md font-bold transition-colors",
        BUTTON_SIZE[size],
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
    <div className="mb-5 flex flex-wrap items-baseline justify-between gap-x-base gap-y-1" id={id}>
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h2 className="text-[20px] font-bold leading-[1.25] text-ink-deep">{title}</h2>
        {hint ? <p className="text-[12px] leading-normal text-steel">{hint}</p> : null}
      </div>
      {right ? <div className="flex shrink-0 items-center gap-md">{right}</div> : null}
    </div>
  );
}

/** 링크 = primary/700 + › (가이드 G04). 화면마다 버튼을 늘리지 않기 위해 섹션 우측에 둔다. */
export function TextLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Link href={href} className="inline-flex items-center gap-0.5 text-[13px] font-bold text-primary hover:underline">
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
    success: "bg-icon",
    attention: "bg-attention",
    critical: "bg-critical",
  }[tone];
  return (
    <div>
      <div className="h-2 w-full overflow-hidden rounded-pill bg-track">
        <div className={clsx("h-full origin-left rounded-pill motion-safe:animate-grow-x", toneClass)} style={{ width: `${Math.min(100, Math.max(0, value))}%` }} />
      </div>
      {label ? <p className="mt-1 text-[12px] text-steel">{label}</p> : null}
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
    <ScrollRegion label={typeof caption === "string" ? caption : undefined}>
      <table className="w-full border-collapse text-[14px]">
        {caption ? <caption className="mb-2 text-left text-[12px] text-steel">{caption}</caption> : null}
        <thead>
          <tr className="bg-surface-soft">
            {columns.map((c) => (
              <th
                key={c.key}
                scope="col"
                style={c.width ? { width: c.width } : undefined}
                className={clsx(
                  "whitespace-nowrap px-3 text-[12px] font-bold text-steel first:rounded-l-md last:rounded-r-md",
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
    </ScrollRegion>
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
    <ul className={clsx("divide-y divide-hairline-soft overflow-hidden rounded-xl border border-hairline-soft bg-canvas", className)}>
      {children}
    </ul>
  );
}

export function RowEmpty({ title, description, action }: { title: string; description?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-1.5 rounded-xl border border-dashed border-hairline bg-canvas px-xl py-xxl text-center">
      <p className="text-[14px] font-bold text-charcoal">{title}</p>
      {description ? <p className="max-w-[420px] text-[13px] leading-relaxed text-steel">{description}</p> : null}
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

/**
 * 하위 분석 탭 = 밑줄 탭 (가이드 G04): 선택 = 하단 2px 보라 밑줄 + Bold, 비선택 = 보조 글자.
 * 선택 상태는 배경 대신 보라 라인으로 알린다.
 */
export function tabClass(on: boolean, size: "sm" | "md") {
  return clsx(
    "relative inline-flex items-center gap-1.5 whitespace-nowrap border-b-2 transition-colors",
    size === "md" ? "px-0.5 pb-3 pt-2 text-[14px]" : "px-0.5 pb-2 pt-1 text-[13px]",
    on ? "border-primary font-bold text-ink-deep" : "border-transparent font-medium text-steel hover:text-ink-deep",
  );
}

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
    <div role="tablist" aria-label={label} className="flex flex-wrap items-center gap-x-6 border-b border-hairline-soft">
      {items.map((item) => {
        const on = item.key === value;
        return (
          <button
            key={item.key}
            type="button"
            role="tab"
            aria-selected={on}
            onClick={() => onChange(item.key)}
            className={clsx(tabClass(on, size), "-mb-px")}
          >
            {item.label}
            {item.count !== undefined ? (
              <span
                className={clsx(
                  "inline-flex min-w-[20px] items-center justify-center rounded-pill px-1.5 text-[12px] font-bold leading-[20px] tnum",
                  on ? "bg-info-soft text-primary" : "bg-track text-steel",
                )}
              >
                {item.count}
              </span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}

/** 링크형 밑줄 탭 — 탭마다 별도 URL 이 있는 경우. 미확인 이슈가 있는 탭에만 점(주황 · 빨강)을 단다 */
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
    <nav aria-label={label} className="flex flex-wrap items-center gap-x-6 border-b border-hairline-soft">
      {items.map((item) => {
        const on = item.href === activeHref;
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={on ? "page" : undefined}
            className={clsx(tabClass(on, "md"), "-mb-px")}
          >
            {item.label}
            {item.dot ? <StatusDot severity={item.dot} /> : null}
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
          checked ? "bg-primary" : "bg-icon",
        )}
      >
        <span
          className={clsx(
            "absolute top-0.5 h-4 w-4 rounded-circle bg-white transition-all",
            checked ? "left-[18px]" : "left-0.5",
          )}
        />
      </span>
      <span className="min-w-0">
        <span className={clsx("block text-[13px] font-bold", checked ? "text-ink-deep" : "text-steel")}>{label}</span>
        {description ? <span className="block text-[12px] text-steel">{description}</span> : null}
      </span>
    </button>
  );
}

/* ── Status dot ────────────────────────────────────────────── */
/** 레드닷 = danger/500 7px — 미확인 이슈가 있는 탭에만, 선택하면 사라지고 새 이슈가 생기면 다시 표시 (가이드 G04) */
const DOT_TONE: Record<Severity, string> = {
  info: "bg-icon",
  watch: "bg-primary",
  caution: "bg-attention",
  critical: "bg-critical",
};

export function StatusDot({ severity, className }: { severity: Severity; className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={clsx("inline-block h-[7px] w-[7px] shrink-0 rounded-circle", DOT_TONE[severity], className)}
    />
  );
}

/* ── Next step ─────────────────────────────────────────────── */
/** 화면 맨 아래에서 다음 단계 하나만 제안한다 */
/** 조사 '(으)로' — 마지막 글자에 받침이 없거나 ㄹ 받침이면 '로', 그 밖의 받침은 '으로' (결과로 · 설정으로 · 수행방안으로) */
export function withRo(word: string): string {
  const code = word.trim().charCodeAt(word.trim().length - 1) - 0xac00;
  if (code < 0 || code > 11171) return "(으)로";
  const jong = code % 28;
  return jong === 0 || jong === 8 ? "로" : "으로";
}

export function NextStep({
  step,
  title,
  description,
  href,
  cta,
}: {
  step: number;
  title: string;
  description: string;
  href: string;
  /** 버튼 문구 — 같은 목적지는 같은 버튼 이름 (가이드 규칙 04) */
  cta?: string;
}) {
  return (
    <section className="flex flex-wrap items-center gap-3 rounded-[10px] border border-hairline-soft bg-canvas py-[18px] pl-5 pr-[18px]">
      <span
        aria-hidden="true"
        className="flex h-[30px] w-[30px] shrink-0 items-center justify-center rounded-circle bg-info-soft text-[16px] font-bold text-primary-deep"
      >
        {step}
      </span>
      <div className="min-w-0 flex-1">
        <h2 className="text-[16px] font-bold leading-[1.4] text-ink-deep">다음 단계 · {title}</h2>
        <p className="mt-0.5 text-[12px] leading-[18px] text-steel">{description}</p>
      </div>
      <LinkButton href={href} className="shrink-0">
        {cta ?? `${title}${withRo(title)}`}
        <IconChevron />
      </LinkButton>
    </section>
  );
}

/** 분석 탭 줄 끝의 [+] — 분석 에이전트 만들기 (시안 304:2 · 24px 흰 바탕 · 테두리) */
export function AddAgentTab({ href }: { href: string }) {
  return (
    <Link
      href={href}
      aria-label="분석 에이전트 만들기"
      data-builder-link
      className="mt-[6.5px] inline-flex h-6 w-6 shrink-0 items-center justify-center self-start rounded-md border border-hairline-soft bg-canvas text-steel hover:bg-surface-soft hover:text-ink-deep"
    >
      <svg viewBox="0 0 12 12" width="12" height="12" aria-hidden="true">
        <path d="M6 1.5v9M1.5 6h9" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
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
