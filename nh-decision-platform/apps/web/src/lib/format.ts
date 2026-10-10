import type { Figure } from "./types";

/** 금액 단위 표기 규칙 — 단위 라벨을 항상 함께 노출한다 (요구사항 UX-08) */
export const UNIT_LABEL: Record<Figure["unit"], string> = {
  KRW_MN: "백만원",
  KRW_BN: "억원",
  KRW_TN: "조원",
  PCT: "%",
  PP: "%p",
  CNT: "건",
  RATIO: "",
  NONE: "",
};

const nf = (decimals: number) =>
  new Intl.NumberFormat("ko-KR", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });

export function defaultDecimals(unit: Figure["unit"]): number {
  switch (unit) {
    case "PCT":
    case "PP":
      return 1;
    case "KRW_TN":
      return 1;
    case "KRW_BN":
      return 0;
    case "RATIO":
      return 3;
    default:
      return 0;
  }
}

/** 수치 본문(단위 라벨 제외) */
export function formatValue(figure: Figure): string {
  if (figure.value === null || figure.value === undefined) {
    return figure.undefinedLabel ?? "미제공";
  }
  const decimals = figure.decimals ?? defaultDecimals(figure.unit);
  return nf(decimals).format(figure.value);
}

/** 수치 + 단위 */
export function formatFigure(figure: Figure): string {
  if (figure.value === null || figure.value === undefined) {
    return figure.undefinedLabel ?? "미제공";
  }
  const unit = UNIT_LABEL[figure.unit];
  const body = formatValue(figure);
  if (!unit) return body;
  if (unit === "%" || unit === "%p") return `${body}${unit}`;
  return `${body}${unit}`;
}

/** 증감 부호 포함 */
export function formatSigned(figure: Figure): string {
  if (figure.value === null || figure.value === undefined) {
    return figure.undefinedLabel ?? "미제공";
  }
  const sign = figure.value > 0 ? "+" : "";
  const unit = UNIT_LABEL[figure.unit];
  const decimals = figure.decimals ?? defaultDecimals(figure.unit);
  return `${sign}${nf(decimals).format(figure.value)}${unit}`;
}

export function toneOfDelta(value: number | null | undefined, positiveIsGood = true) {
  if (value === null || value === undefined || value === 0) return "neutral" as const;
  const good = value > 0 ? positiveIsGood : !positiveIsGood;
  return good ? ("good" as const) : ("bad" as const);
}

/**
 * 날짜·시각은 문자열을 그대로 파싱한다.
 * Date 객체를 쓰면 서버(컨테이너 UTC)와 브라우저(KST)에서 다른 값이 렌더되어
 * 하이드레이션 불일치와 기준시점 오표기가 발생한다.
 */
export function formatDate(iso: string): string {
  if (!iso) return "";
  const [y, m, d] = iso.slice(0, 10).split("-");
  if (!d) return iso;
  return `${y}.${m}.${d}`;
}

export function formatDateTime(iso: string): string {
  if (!iso) return "";
  const datePart = formatDate(iso);
  const timeMatch = iso.match(/T(\d{2}):(\d{2})/);
  if (!timeMatch) return datePart;
  return `${datePart} ${timeMatch[1]}:${timeMatch[2]}`;
}

export const SEVERITY_LABEL = {
  info: "정상",
  watch: "관찰",
  caution: "주의",
  critical: "긴급",
} as const;

export const EVIDENCE_CATEGORY_LABEL = {
  bank_data: "당행 Data",
  internal_direction: "내부 경영방향",
  external_policy: "외부 정책·환경",
} as const;

export const DB_CLASS_LABEL = {
  gov_policy: "정부정책 DB",
  mgmt_decision: "경영 의사결정 DB",
  model_method: "모형·방법론",
  branch_ref: "영업점 기준·공문",
  external_web: "외부 수집",
} as const;

export const GOAL_STATUS_LABEL = {
  active: "현재 적용 중",
  ai_proposed: "AI 수정 제안",
  under_review: "수정 검토 중",
  pending_confirm: "확정 대기",
  archived: "종료",
} as const;

export const ALIGNMENT_LABEL = {
  aligned: "정합",
  conflict: "배치",
  unknown: "확인 필요",
} as const;
