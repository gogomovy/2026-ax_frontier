import { redirect } from "next/navigation";
import { BranchUnavailable } from "@/components/domain/BranchUnavailable";
import { PageHeader } from "@/components/layout/PageHeader";
import { officeParam, withOffice } from "@/lib/branchOffice";
import { getBranchTabs } from "@/lib/data";

export const dynamic = "force-dynamic";

/** 영업점 STEP 2 진입 — 첫 번째 의견 탭으로 이동 (탭은 1화면 의견 수만큼 일 단위로 재생성) */
export default async function BranchAnalysisIndex(props: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const office = officeParam(await props.searchParams);
  const { current } = await getBranchTabs(office);
  if (current.length > 0) redirect(withOffice(`/branch/analysis/${current[0].tabKey}`, office));
  return (
    <>
      <PageHeader eyebrow="2단계 · 분석 결과" title="분석 결과" />
      <BranchUnavailable />
    </>
  );
}
