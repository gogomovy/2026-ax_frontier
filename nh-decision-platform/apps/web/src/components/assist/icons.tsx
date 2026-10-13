/** 채팅 화면용 작은 아이콘 — 장식이므로 모두 aria-hidden (이름은 버튼의 aria-label 이 맡는다) */
import type { ReactNode } from "react";

const base = { viewBox: "0 0 20 20", width: 18, height: 18, fill: "none", stroke: "currentColor", strokeWidth: 1.6, strokeLinecap: "round", strokeLinejoin: "round", "aria-hidden": true } as const;
const Svg = ({ children, size = 18 }: { children: ReactNode; size?: number }) => (
  <svg {...base} width={size} height={size}>
    {children}
  </svg>
);

export const IconChat = ({ size }: { size?: number }) => (
  <Svg size={size}>
    <path d="M4 5.5A2.5 2.5 0 0 1 6.5 3h7A2.5 2.5 0 0 1 16 5.5v5a2.5 2.5 0 0 1-2.5 2.5H9l-3.5 3v-3H6.5A2.5 2.5 0 0 1 4 10.5z" />
  </Svg>
);
/** AI 챗봇 얼굴 — 안테나 · 둥근 머리 · 눈 · 귀, 오른쪽 위의 작은 반짝임(AI) */
export const IconBot = ({ size }: { size?: number }) => (
  <Svg size={size}>
    <path d="M10 5V3.4" />
    <circle cx="10" cy="2.7" r="0.9" fill="currentColor" stroke="none" />
    <rect x="3.6" y="5" width="12.8" height="10.4" rx="3.6" />
    <path d="M2 8.8v3.4M18 8.8v3.4" />
    <circle cx="7.4" cy="10.1" r="1.15" fill="currentColor" stroke="none" />
    <circle cx="12.6" cy="10.1" r="1.15" fill="currentColor" stroke="none" />
    <path d="M8.2 12.9c.5.5 1.1.7 1.8.7s1.3-.2 1.8-.7" />
    <path d="M7 15.4l-.9 2.3 3-1.7" />
  </Svg>
);
export const IconSend = ({ size }: { size?: number }) => (
  <Svg size={size}>
    <path d="M10 16V4M5 9l5-5 5 5" strokeWidth={2} />
  </Svg>
);
export const IconStop = ({ size }: { size?: number }) => (
  <svg viewBox="0 0 20 20" width={size ?? 18} height={size ?? 18} fill="currentColor" aria-hidden="true">
    <rect x="5" y="5" width="10" height="10" rx="2" />
  </svg>
);
export const IconCopy = ({ size }: { size?: number }) => (
  <Svg size={size}>
    <rect x="7" y="7" width="9" height="9" rx="2" />
    <path d="M13 7V5.5A1.5 1.5 0 0 0 11.5 4h-6A1.5 1.5 0 0 0 4 5.5v6A1.5 1.5 0 0 0 5.5 13H7" />
  </Svg>
);
export const IconCheck = ({ size }: { size?: number }) => (
  <Svg size={size}>
    <path d="M4.5 10.5l3.5 3.5 7.5-8" strokeWidth={2} />
  </Svg>
);
export const IconRefresh = ({ size }: { size?: number }) => (
  <Svg size={size}>
    <path d="M16 10a6 6 0 1 1-1.8-4.3M16 3.5v3h-3" />
  </Svg>
);
export const IconThumbUp = ({ size, filled }: { size?: number; filled?: boolean }) => (
  <Svg size={size}>
    <path d="M7 9l3-5.5a1.6 1.6 0 0 1 2.9 1.2L12.4 8H16a1.5 1.5 0 0 1 1.5 1.8l-1 5A2 2 0 0 1 14.5 16.5H7zM7 9H4.5v7.5H7" fill={filled ? "currentColor" : "none"} />
  </Svg>
);
export const IconThumbDown = ({ size, filled }: { size?: number; filled?: boolean }) => (
  <Svg size={size}>
    <path d="M13 11l-3 5.5a1.6 1.6 0 0 1-2.9-1.2L7.6 12H4a1.5 1.5 0 0 1-1.5-1.8l1-5A2 2 0 0 1 5.5 3.5H13zM13 11h2.5V3.5H13" fill={filled ? "currentColor" : "none"} />
  </Svg>
);
export const IconExpand = ({ size }: { size?: number }) => (
  <Svg size={size}>
    <path d="M12 4h4v4M8 16H4v-4M16 4l-4.5 4.5M4 16l4.5-4.5" />
  </Svg>
);
export const IconCollapse = ({ size }: { size?: number }) => (
  <Svg size={size}>
    <path d="M16 8h-4V4M4 12h4v4M12 8l4.5-4.5M8 12l-4.5 4.5" />
  </Svg>
);
export const IconList = ({ size }: { size?: number }) => (
  <Svg size={size}>
    <path d="M4 5.5h12M4 10h12M4 14.5h8" />
  </Svg>
);
export const IconPlus = ({ size }: { size?: number }) => (
  <Svg size={size}>
    <path d="M10 4v12M4 10h12" strokeWidth={1.9} />
  </Svg>
);
export const IconTrash = ({ size }: { size?: number }) => (
  <Svg size={size}>
    <path d="M4.5 6h11M8 6V4.5h4V6M6 6l.6 9.5h6.8L14 6M8.5 9v4M11.5 9v4" />
  </Svg>
);
export const IconClose = ({ size }: { size?: number }) => (
  <Svg size={size}>
    <path d="M5 5l10 10M15 5L5 15" strokeWidth={1.8} />
  </Svg>
);
export const IconChevron = ({ size, open }: { size?: number; open?: boolean }) => (
  <svg viewBox="0 0 20 20" width={size ?? 16} height={size ?? 16} fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={{ transform: open ? "rotate(90deg)" : undefined, transition: "transform .15s" }}>
    <path d="M8 5l5 5-5 5" />
  </svg>
);
export const IconArrowDown = ({ size }: { size?: number }) => (
  <Svg size={size}>
    <path d="M10 4v12M5 11l5 5 5-5" strokeWidth={1.9} />
  </Svg>
);
export const IconDoc = ({ size }: { size?: number }) => (
  <Svg size={size}>
    <path d="M6 3h5.5L15 6.5V16a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1zM11 3v4h4M7.5 11h5M7.5 14h5" />
  </Svg>
);
export const IconSpark = ({ size }: { size?: number }) => (
  <Svg size={size}>
    <path d="M10 3l1.6 4.4L16 9l-4.4 1.6L10 15l-1.6-4.4L4 9l4.4-1.6zM15.5 14.5l.6 1.4 1.4.6-1.4.6-.6 1.4-.6-1.4-1.4-.6 1.4-.6z" />
  </Svg>
);
