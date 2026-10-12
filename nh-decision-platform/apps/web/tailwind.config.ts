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
      fontSize: {
        caption: ["12px", { lineHeight: "1.33" }],
        "body-sm": ["14px", { lineHeight: "1.43", letterSpacing: "-0.14px" }],
        body: ["16px", { lineHeight: "1.5", letterSpacing: "-0.16px" }],
        "subtitle-md": ["18px", { lineHeight: "1.44" }],
        "heading-sm": ["24px", { lineHeight: "1.25" }],
        "heading-md": ["28px", { lineHeight: "1.21" }],
        "heading-lg": ["36px", { lineHeight: "1.28" }],
      },
      // 글자 색만 대비를 높인 값으로 (B.34) — text-primary · text-success · text-critical. bg-* · border-* 는 colors 그대로
      textColor: {
        primary: "var(--color-primary-text)",
        success: "var(--color-success-text)",
        critical: "var(--color-critical-text)",
        attention: "var(--color-attention-text)",
        warning: "var(--color-warning-text)",
      },
      boxShadow: {
        panel: "rgba(20, 22, 26, 0.12) 0px 1px 4px 0px",
        pop: "rgba(20, 22, 26, 0.22) 0px 6px 24px 0px",
      },
      maxWidth: {
        shell: "var(--shell-max)",
      },
    },
  },
  plugins: [],
};

export default config;
