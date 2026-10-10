import { redirect } from "next/navigation";
import { PageHeader } from "@/components/layout/PageHeader";
import { RowEmpty } from "@/components/ui/primitives";
import { getAnalysisTabs } from "@/lib/data";

export const dynamic = "force-dynamic";

/** STEP 2 진입 — 현재 세대의 첫 번째 분석 탭으로 이동 (탭은 의견 수만큼 일 단위로 재생성) */
export default async function RiskAnalysisIndex() {
  const { current } = await getAnalysisTabs();
  if (current.length > 0) redirect(`/risk/analysis/${current[0].tabKey}`);
  return (
    <>
      <PageHeader eyebrow="2단계 · 분석 결과" title="분석 결과" />
      <div className="shell">
        <RowEmpty title="현재 분석 탭이 없습니다" description="데이터가 바뀌거나 정기 실행이 끝나면 의견 수만큼 탭이 생깁니다." />
      </div>
    </>
  );
}
