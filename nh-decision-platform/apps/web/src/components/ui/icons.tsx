import type { ReactNode } from "react";

/**
 * 새 화면용 아이콘 — 의존성 없는 인라인 SVG. 선 아이콘은 currentColor, 두께 1.6.
 * 아이콘 색은 neutral/400(비활성) 또는 상태 색을 text-* 로 지정한다. 장식이므로 aria-hidden.
 */
interface IconProps {
  className?: string;
  size?: number;
}

function Svg({ className, size = 16, children, fill = "none" }: IconProps & { children: ReactNode; fill?: string }) {
  return (
    <svg
      viewBox="0 0 16 16"
      width={size}
      height={size}
      fill={fill}
      stroke={fill === "none" ? "currentColor" : "none"}
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}

/** ✦ AI 표식 — 네 꼭짓점 별 */
export function IconSparkle({ className, size = 12 }: IconProps) {
  return (
    <Svg className={className} size={size} fill="currentColor">
      <path d="M8 0.8c.5 3.3 1.9 5.9 5.2 7.2-3.3 1.3-4.7 3.9-5.2 7.2-.5-3.3-1.9-5.9-5.2-7.2C6.1 6.7 7.5 4.1 8 .8z" />
    </Svg>
  );
}

export function IconDb({ className, size = 18 }: IconProps) {
  return (
    <Svg className={className} size={size}>
      <ellipse cx="8" cy="3.8" rx="5" ry="2.1" />
      <path d="M3 3.8v8.4c0 1.2 2.2 2.1 5 2.1s5-.9 5-2.1V3.8M3 8c0 1.2 2.2 2.1 5 2.1S13 9.2 13 8" />
    </Svg>
  );
}

export function IconBell({ className, size = 18 }: IconProps) {
  return (
    <Svg className={className} size={size}>
      <path d="M3.6 11.2V7.4a4.4 4.4 0 0 1 8.8 0v3.8l1.1 1.4H2.5l1.1-1.4zM6.5 14a1.6 1.6 0 0 0 3 0" />
    </Svg>
  );
}

export function IconCalendar({ className, size = 16 }: IconProps) {
  return (
    <Svg className={className} size={size}>
      <rect x="2.2" y="3.2" width="11.6" height="10.6" rx="1.8" />
      <path d="M2.2 6.6h11.6M5.4 1.8v2.6M10.6 1.8v2.6" />
    </Svg>
  );
}

export function IconRefresh({ className, size = 14 }: IconProps) {
  return (
    <Svg className={className} size={size}>
      <path d="M13.2 6.2A5.4 5.4 0 0 0 3.5 4.6M2.8 9.8a5.4 5.4 0 0 0 9.7 1.6M13.4 2.6v3.6H9.8M2.6 13.4V9.8h3.6" />
    </Svg>
  );
}

export function IconHistory({ className, size = 16 }: IconProps) {
  return (
    <Svg className={className} size={size}>
      <path d="M2.4 8a5.6 5.6 0 1 0 1.8-4.1M2.4 2.6v3h3M8 4.8V8l2.2 1.4" />
    </Svg>
  );
}

export function IconTable({ className, size = 14 }: IconProps) {
  return (
    <Svg className={className} size={size}>
      <rect x="2" y="2.6" width="12" height="10.8" rx="1.6" />
      <path d="M2 6.4h12M2 10h12M6.2 6.4v7" />
    </Svg>
  );
}

export function IconInbox({ className, size = 22 }: IconProps) {
  return (
    <Svg className={className} size={size}>
      <path d="M2.4 9.4 4 3.6a1 1 0 0 1 1-.8h6a1 1 0 0 1 1 .8l1.6 5.8v3a1 1 0 0 1-1 1H3.4a1 1 0 0 1-1-1v-3zM2.4 9.4h3.2l.8 1.8h3.2l.8-1.8h3.2" />
    </Svg>
  );
}

export function IconAlertCircle({ className, size = 22 }: IconProps) {
  return (
    <Svg className={className} size={size}>
      <circle cx="8" cy="8" r="6" />
      <path d="M8 4.8v3.8M8 11v.2" />
    </Svg>
  );
}

export function IconCheckCircle({ className, size = 16 }: IconProps) {
  return (
    <Svg className={className} size={size}>
      <circle cx="8" cy="8" r="6" />
      <path d="m5.4 8.2 1.8 1.8 3.4-3.8" />
    </Svg>
  );
}

export function IconTarget({ className, size = 16 }: IconProps) {
  return (
    <Svg className={className} size={size}>
      <circle cx="8" cy="8" r="5.6" />
      <circle cx="8" cy="8" r="2.8" />
      <circle cx="8" cy="8" r=".6" fill="currentColor" />
    </Svg>
  );
}

export function IconBriefcase({ className, size = 16 }: IconProps) {
  return (
    <Svg className={className} size={size}>
      <rect x="2" y="5" width="12" height="8.4" rx="1.6" />
      <path d="M5.8 5V3.8a1 1 0 0 1 1-1h2.4a1 1 0 0 1 1 1V5M2 8.6h12" />
    </Svg>
  );
}

export function IconBuilding({ className, size = 16 }: IconProps) {
  return (
    <Svg className={className} size={size}>
      <rect x="3.2" y="2" width="9.6" height="12" rx="1.4" />
      <path d="M6 5h1M9 5h1M6 8h1M9 8h1M6.6 14v-2.4h2.8V14" />
    </Svg>
  );
}

export function IconExternal({ className, size = 12 }: IconProps) {
  return (
    <Svg className={className} size={size}>
      <path d="M6 3H3.6A1.4 1.4 0 0 0 2.2 4.4v8A1.4 1.4 0 0 0 3.6 13.8h8a1.4 1.4 0 0 0 1.4-1.4V10M9 2.2h4.8V7M13.6 2.4 7.4 8.6" />
    </Svg>
  );
}

export function IconClip({ className, size = 14 }: IconProps) {
  return (
    <Svg className={className} size={size}>
      <path d="m12.8 7.4-5 5a3.2 3.2 0 0 1-4.5-4.6l5.2-5.1a2.1 2.1 0 0 1 3 3L6.2 10.6a1 1 0 0 1-1.5-1.4l4.6-4.6" />
    </Svg>
  );
}

export function IconDots({ className, size = 16 }: IconProps) {
  return (
    <Svg className={className} size={size} fill="currentColor">
      <circle cx="3.4" cy="8" r="1.2" />
      <circle cx="8" cy="8" r="1.2" />
      <circle cx="12.6" cy="8" r="1.2" />
    </Svg>
  );
}

export function IconChevronDown({ className, size = 14 }: IconProps) {
  return (
    <Svg className={className} size={size}>
      <path d="m4 6 4 4 4-4" />
    </Svg>
  );
}

export function IconChevronLeft({ className, size = 14 }: IconProps) {
  return (
    <Svg className={className} size={size}>
      <path d="M10 3 5 8l5 5" />
    </Svg>
  );
}

export function IconTriangleDown({ className, size = 10 }: IconProps) {
  return (
    <Svg className={className} size={size} fill="currentColor">
      <path d="M2 4.5h12L8 12z" />
    </Svg>
  );
}

export function IconTriangleUp({ className, size = 10 }: IconProps) {
  return (
    <Svg className={className} size={size} fill="currentColor">
      <path d="M2 11.5h12L8 4z" />
    </Svg>
  );
}

export function IconSort({ className, size = 12 }: IconProps) {
  return (
    <Svg className={className} size={size}>
      <path d="M5 13V3M5 3 2.8 5.2M5 3l2.2 2.2M11 3v10M11 13l-2.2-2.2M11 13l2.2-2.2" />
    </Svg>
  );
}

export function IconInfoCircle({ className, size = 14 }: IconProps) {
  return (
    <Svg className={className} size={size}>
      <circle cx="8" cy="8" r="6" />
      <path d="M8 7.4V11M8 5v.3" />
    </Svg>
  );
}

export function IconGear({ className, size = 16 }: IconProps) {
  return (
    <Svg className={className} size={size}>
      <circle cx="8" cy="8" r="2.2" />
      <path d="M8 1.8v1.6M8 12.6v1.6M1.8 8h1.6M12.6 8h1.6M3.6 3.6l1.1 1.1M11.3 11.3l1.1 1.1M3.6 12.4l1.1-1.1M11.3 4.7l1.1-1.1" />
    </Svg>
  );
}

export function IconShield({ className, size = 16 }: IconProps) {
  return (
    <Svg className={className} size={size}>
      <path d="M8 1.8 3 3.6v4c0 3 2 5.1 5 6.6 3-1.5 5-3.6 5-6.6v-4L8 1.8z" />
      <path d="m6 8 1.5 1.5L10.2 6.6" />
    </Svg>
  );
}

export function IconUsers({ className, size = 16 }: IconProps) {
  return (
    <Svg className={className} size={size}>
      <circle cx="6" cy="5.6" r="2.4" />
      <path d="M1.8 13.4c.3-2.4 2-3.8 4.2-3.8s3.9 1.4 4.2 3.8M10.6 3.6a2.3 2.3 0 0 1 0 4.4M12.4 9.9c1 .6 1.6 1.7 1.8 3.1" />
    </Svg>
  );
}

export function IconSearch({ className, size = 14 }: IconProps) {
  return (
    <Svg className={className} size={size}>
      <circle cx="7" cy="7" r="4.4" />
      <path d="m10.4 10.4 3.2 3.2" />
    </Svg>
  );
}

export function IconLogout({ className, size = 14 }: IconProps) {
  return (
    <Svg className={className} size={size}>
      <path d="M6.4 2.6H4a1.4 1.4 0 0 0-1.4 1.4v8A1.4 1.4 0 0 0 4 13.4h2.4M10.2 5.4 12.8 8l-2.6 2.6M12.6 8H6.2" />
    </Svg>
  );
}

export function IconLayers({ className, size = 16 }: IconProps) {
  return (
    <Svg className={className} size={size}>
      <path d="m8 2 6 3.2L8 8.4 2 5.2 8 2zM2 8.2l6 3.2 6-3.2M2 11l6 3.2 6-3.2" />
    </Svg>
  );
}

export function IconCheck2({ className, size = 14 }: IconProps) {
  return (
    <Svg className={className} size={size}>
      <path d="m3.4 8.4 3 3 6.2-7" />
    </Svg>
  );
}
