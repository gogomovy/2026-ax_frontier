/**
 * 수행방안의 연결 분석 (/screens/plans/{id}/linked-analysis) — 사업부서가 '영업점 참고'를 켠 진행사업은
 * 영업점도 연결 분석을 원본 보고서 대신 요약으로 본다(부서 보고서 화면 권한 없이). 요약은 지금 보고서 기준.
 */
import type { Severity } from "@/lib/types";

export interface LinkedAnalysis {
  tabKey: string;
  space: string;
  /** 분석한 부서(분석 공간 이름 — 화면 설정 · 조직에서) */
  analysisFrom: string;
  title: string;
  subtitle?: string;
  asOf?: string | null;
  severity: Severity;
  summary: { title: string; severity: Severity; text: string }[];
  keyFigures: string[];
  sections: { heading: string; lines: string[] }[];
  limitations: string[];
}

export interface LinkedAnalysisResponse {
  plan: string;
  analysis: LinkedAnalysis | null;
  /** 보고서 화면 주소 — 부서 보고서 화면을 열 수 있으면 그 화면, 영업점 공통(영업본부 · 영업점)이면 공유 보고서 화면, 아니면 없음(요약만) */
  href: string | null;
}

/** 영업점 공통 공유 보고서 화면 주소 (/branch/shared/{수행방안}) — 서버 plan_share.SHARED_PATH 와 같다 */
export const SHARED_REPORT_PATH = "/branch/shared/";

/** 공유 보고서 화면 주소인지 — 그때는 링크와 함께 요약도 그 자리에서 보여 준다 */
export function isSharedHref(href: string | null | undefined): boolean {
  return Boolean(href && href.startsWith(SHARED_REPORT_PATH));
}

const SEVERITIES: Severity[] = ["info", "watch", "caution", "critical"];

/** 서버 값을 화면이 믿고 쓸 수 있게 — 모르는 심각도는 정상(info), 빈 문장 · 빈 절은 뺀다 */
export function normalizeLinked(r: LinkedAnalysisResponse): LinkedAnalysisResponse {
  const a = r.analysis;
  if (!a) return { ...r, analysis: null };
  const sev = (s: unknown): Severity => (SEVERITIES.includes(s as Severity) ? (s as Severity) : "info");
  return {
    ...r,
    analysis: {
      ...a,
      severity: sev(a.severity),
      summary: (a.summary ?? []).filter((s) => s && (s.title || s.text)).map((s) => ({ ...s, severity: sev(s.severity) })),
      keyFigures: (a.keyFigures ?? []).filter(Boolean),
      sections: (a.sections ?? []).filter((s) => s && s.lines?.length),
      limitations: (a.limitations ?? []).filter(Boolean),
    },
  };
}

/** 'YYYY-MM-DD…' → 'YYYY.MM.DD' (다른 형식은 그대로) */
export function asOfText(v?: string | null): string {
  if (!v) return "";
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(v);
  return m ? `${m[1]}.${m[2]}.${m[3]}` : v;
}
