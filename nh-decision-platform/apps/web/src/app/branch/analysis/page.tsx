import { redirect } from "next/navigation";
import { BranchUnavailable } from "@/components/domain/BranchUnavailable";
import { PageHeader } from "@/components/layout/PageHeader";
import { getBranchTabs } from "@/lib/data";

export const dynamic = "force-dynamic";

/** 영업점 STEP 2 진입 — 첫 번째 의견 탭으로 이동 (탭은 1화면 의견 수만큼 일 단위로 재생성) */
export default async function BranchAnalysisIndex() {
  const { current } = await getBranchTabs();
  if (current.length > 0) redirect(`/branch/analysis/${current[0].tabKey}`);
  return (
    <>
      <PageHeader eyebrow="2단계 · 분석 결과" title="분석 결과" />
      <BranchUnavailable />
    </>
  );
}
