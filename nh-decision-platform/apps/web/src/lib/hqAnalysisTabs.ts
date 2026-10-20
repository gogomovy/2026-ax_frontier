/** 종합기획부 [데이터 분석] 기본 탭 — 화면 안 탭(AnalysisWorkspace)과 맞춤 분석 탭 화면의 앞쪽 링크가 같은 목록을 쓴다 (Q109) */
export type HqAnalysisTabKey = "revenue" | "corporate" | "household" | "comparison";

export const HQ_ANALYSIS_TABS: { key: HqAnalysisTabKey; label: string }[] = [
  { key: "revenue", label: "여신 종합수익" },
  { key: "corporate", label: "기업여신" },
  { key: "household", label: "가계여신" },
  { key: "comparison", label: "기업·가계 비교" },
];

/** 주소의 ?tab= → 기본 탭 키 (모르는 값이면 첫 탭) */
export function hqAnalysisTab(v: string | string[] | undefined): HqAnalysisTabKey {
  const s = Array.isArray(v) ? v[0] : v;
  return HQ_ANALYSIS_TABS.some((t) => t.key === s) ? (s as HqAnalysisTabKey) : "revenue";
}
