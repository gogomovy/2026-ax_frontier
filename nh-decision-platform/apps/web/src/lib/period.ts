/**
 * 기간 · 추세 표기 (Phase I · 하드코딩 제거) — 화면의 기간 라벨은 산출물 기준일(asOf)에서, 추세 문구는 계열 값에서 계산한다.
 * 기준일이 없거나 해석할 수 없으면 '–' 로 표시한다(업로드 전 빈 템플릿).
 * 날짜는 문자열 그대로 해석한다 — Date 객체는 서버(UTC) · 브라우저(KST)에서 값이 달라진다(format.ts 와 같은 규칙).
 */

export const NO_VALUE = "–";

export interface PeriodLabels {
  /** 기준 연월 (예: 2026.08) */
  ym: string;
  /** 기준 월 (예: 8월) */
  month: string;
  /** 기준 연도 (예: 2026) */
  year: string;
  /** 전년 동월 (예: 2025.08) */
  prevYm: string;
  /** 전전년 동월 (예: 2024.08) */
  prev2Ym: string;
  /** 기준일 (예: 2026.08.31) */
  ymDate: string;
}

const EMPTY_PERIOD: PeriodLabels = { ym: NO_VALUE, month: NO_VALUE, year: NO_VALUE, prevYm: NO_VALUE, prev2Ym: NO_VALUE, ymDate: NO_VALUE };

/** 기준일(ISO `YYYY-MM-DD…`) → 기간 라벨 · 없거나 잘못된 값이면 모두 '–' */
export function periodOf(asOf?: string | null): PeriodLabels {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(asOf ?? "");
  if (!m) return EMPTY_PERIOD;
  const [, ys, ms, ds] = m;
  const y = Number(ys);
  const mo = Number(ms);
  const d = Number(ds);
  if (mo < 1 || mo > 12 || d < 1 || d > 31) return EMPTY_PERIOD;
  return {
    ym: `${ys}.${ms}`,
    month: `${mo}월`,
    year: ys,
    prevYm: `${y - 1}.${ms}`,
    prev2Ym: `${y - 2}.${ms}`,
    ymDate: `${ys}.${ms}.${ds}`,
  };
}

/** 오늘 날짜(KST · `YYYY-MM-DD`) — 호출 시점에 계산한다 */
export function todayKst(): string {
  return new Date().toLocaleDateString("sv-SE", { timeZone: "Asia/Seoul" });
}

/** 기준 연도 — 기준일 연도. 모르면 null(올해로 대신하지 않는다 · Phase K · HC-04) */
export function baseYear(asOf?: string | null): number | null {
  const p = periodOf(asOf);
  return p.year !== NO_VALUE ? Number(p.year) : null;
}

/**
 * 경영목표 적용기간 선택지 — 기준일에서 남은 기간을 만든다: 기준 연도 연간 · 남은 반기 · 남은 분기 · 다음 해 상반기 · 연간.
 * 기준일을 모르면 빈 목록(고를 수 없음).
 */
export function goalPeriodOptions(asOf?: string | null): string[] {
  const p = periodOf(asOf);
  if (p.year === NO_VALUE) return [];
  const y = Number(p.year);
  const month = Number(p.month.replace("월", ""));
  const quarter = Math.ceil(month / 3);
  const halves = month <= 6 ? [`${y} 상반기`, `${y} 하반기`] : [`${y} 하반기`];
  const quarters = Array.from({ length: 4 - quarter + 1 }, (_, i) => `${y}.${quarter + i}Q`);
  return [`${y} 연간`, ...halves, ...quarters, `${y + 1} 상반기`, `${y + 1} 연간`];
}

/* ── 추세 문구 ─────────────────────────────────────────── */

type Num = number | null | undefined;
const isNum = (v: Num): v is number => typeof v === "number" && Number.isFinite(v);

/** 직전 대비 변화 — 값이 하나라도 없으면 null */
export function stepChange(prev: Num, curr: Num): "축소" | "확대" | "유지" | null {
  if (!isNum(prev) || !isNum(curr)) return null;
  if (curr < prev) return "축소";
  if (curr > prev) return "확대";
  return "유지";
}

/**
 * 계열 방향 — 값이 2개 이상일 때 단조 감소 '연속 축소' · 단조 증가 '연속 확대' · 그 밖 '변동'.
 * 값이 2개 미만이면 null (문구를 그리지 않는다).
 */
export function seriesTrend(values: Num[]): "연속 축소" | "연속 확대" | "변동" | null {
  const v = values.filter(isNum);
  if (v.length < 2) return null;
  const diffs = v.slice(1).map((x, i) => x - v[i]);
  if (diffs.every((d) => d < 0)) return "연속 축소";
  if (diffs.every((d) => d > 0)) return "연속 확대";
  return "변동";
}
