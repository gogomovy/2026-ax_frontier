import type { Config } from "tailwindcss";

/**
 * 디자인 시스템 단일 출처: designsys/DESIGN-meta.md
 * 토큰 값은 globals.css 의 CSS 변수로 정의하고, 여기서는 변수만 참조한다.
 * (요구사항 UX-09 — 하드코딩 색상·폰트 금지)
 */
const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        primary: "var(--color-primary)",
        "primary-deep": "var(--color-primary-deep)",
        "primary-soft": "var(--color-primary-soft)",
        "on-primary": "var(--color-on-primary)",
        "ink-button": "var(--color-ink-button)",
        "on-ink-button": "var(--color-on-ink-button)",
        ink: "var(--color-ink)",
        "ink-deep": "var(--color-ink-deep)",
        charcoal: "var(--color-charcoal)",
        slate: "var(--color-slate)",
        steel: "var(--color-steel)",
        stone: "var(--color-stone)",
        hairline: "var(--color-hairline)",
        "hairline-soft": "var(--color-hairline-soft)",
        canvas: "var(--color-canvas)",
        page: "var(--color-page)",
        track: "var(--color-track)",
        icon: "var(--color-icon)",
        "surface-soft": "var(--color-surface-soft)",
        success: "var(--color-success)",
        attention: "var(--color-attention)",
        warning: "var(--color-warning)",
        critical: "var(--color-critical)",
        "critical-strong": "var(--color-critical-strong)",
        disabled: "var(--color-disabled-text)",
        // 상태 옅은 배경 · 선 (C.1 · Q106)
        "info-faint": "var(--color-info-faint)",
        "info-soft": "var(--color-info-soft)",
        "info-line-soft": "var(--color-info-line-soft)",
        "info-line": "var(--color-info-line)",
        "success-faint": "var(--color-success-faint)",
        "success-soft": "var(--color-success-soft)",
        "success-line": "var(--color-success-line)",
        "attention-faint": "var(--color-attention-faint)",
        "attention-soft": "var(--color-attention-soft)",
        "warning-soft": "var(--color-warning-soft)",
        "critical-faint": "var(--color-critical-faint)",
        "critical-soft": "var(--color-critical-soft)",
        "critical-line": "var(--color-critical-line)",
        highlight: "var(--color-highlight)",
        "line-strong": "var(--color-line-strong)",
        scrim: "var(--color-scrim)",
        "chart-1": "var(--chart-1)",
        "chart-2": "var(--chart-2)",
        "chart-3": "var(--chart-3)",
        "chart-4": "var(--chart-4)",
        "chart-5": "var(--chart-5)",
        "chart-6": "var(--chart-6)",
        "chart-grid": "var(--chart-grid)",
        "chart-axis": "var(--chart-axis)",
      },
      borderRadius: {
        sm: "var(--radius-sm)",
        md: "var(--radius-md)",
        lg: "var(--radius-lg)",
        xl: "var(--radius-xl)",
        "2xl": "var(--radius-xxl)",
        "3xl": "var(--radius-xxxl)",
        pill: "var(--radius-full)",
        circle: "var(--radius-circle)",
      },
      spacing: {
        xxs: "var(--space-xxs)",
        xs: "var(--space-xs)",
        sm: "var(--space-sm)",
        md: "var(--space-md)",
        base: "var(--space-base)",
        lg: "var(--space-lg)",
        xl: "var(--space-xl)",
        xxl: "var(--space-xxl)",
        xxxl: "var(--space-xxxl)",
        section: "var(--space-section)",
      },
      fontFamily: {
        sans: "var(--font-display)",
      },
      // 타이포 (가이드 G02): 캡션 12 · 본문 14 · 카드 제목 16 · 섹션 제목 20 · KPI 24 · 핵심 수치 28~32
      fontSize: {
        axis: ["11px", { lineHeight: "1.4" }],
        caption: ["12px", { lineHeight: "1.5" }],
        "body-sm": ["14px", { lineHeight: "1.5" }],
        body: ["16px", { lineHeight: "1.4" }],
        "subtitle-md": ["20px", { lineHeight: "1.25" }],
        "heading-sm": ["24px", { lineHeight: "1.25" }],
        "heading-md": ["28px", { lineHeight: "1.2" }],
        "heading-lg": ["32px", { lineHeight: "1.2" }],
      },
      // 글자 색만 대비를 높인 값으로 (B.34) — text-primary · text-success · text-critical. bg-* · border-* 는 colors 그대로
      textColor: {
        primary: "var(--color-primary-text)",
        success: "var(--color-success-text)",
        critical: "var(--color-critical-text)",
        attention: "var(--color-attention-text)",
        warning: "var(--color-warning-text)",
      },
      // 그림자는 떠 있는 요소에만 (G03): 툴팁 · 팝업 · 토스트
      boxShadow: {
        panel: "var(--shadow-tooltip)",
        tooltip: "var(--shadow-tooltip)",
        pop: "var(--shadow-popup)",
        popup: "var(--shadow-popup)",
        toast: "var(--shadow-toast)",
      },
      keyframes: {
        "fade-in": { from: { opacity: "0" }, to: { opacity: "1" } },
        "slide-in-right": { from: { transform: "translateX(24px)", opacity: "0" }, to: { transform: "none", opacity: "1" } },
        "pop-in": { from: { transform: "translateY(8px) scale(0.98)", opacity: "0" }, to: { transform: "none", opacity: "1" } },
        "toast-in": { from: { transform: "translate(-50%, 8px)", opacity: "0" }, to: { transform: "translate(-50%, 0)", opacity: "1" } },
        shimmer: { "0%,100%": { opacity: "1" }, "50%": { opacity: "0.55" } },
      },
      animation: {
        "fade-in": "fade-in 140ms ease-out both",
        "slide-in-right": "slide-in-right 200ms cubic-bezier(0.2, 0.7, 0.2, 1) both",
        "pop-in": "pop-in 180ms cubic-bezier(0.2, 0.7, 0.2, 1) both",
        "toast-in": "toast-in 180ms ease-out both",
        shimmer: "shimmer 1.4s ease-in-out infinite",
      },
      maxWidth: {
        shell: "var(--shell-max)",
      },
      height: {
        header: "var(--header-h)",
      },
    },
  },
  plugins: [],
};

export default config;
