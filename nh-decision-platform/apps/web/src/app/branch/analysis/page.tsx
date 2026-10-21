import { redirect } from "next/navigation";
import { BranchOfficePicker } from "@/components/domain/BranchOfficePicker";
import { BranchUnavailable } from "@/components/domain/BranchUnavailable";
import { PageHeader } from "@/components/layout/PageHeader";
import { officeParam, withOffice } from "@/lib/branchOffice";
import { getBranchOffices, getBranchTabs } from "@/lib/data";

export const dynamic = "force-dynamic";

/** 영업점 STEP 2 진입 — 첫 번째 의견 탭으로 이동 (탭은 1화면 의견 수만큼 일 단위로 재생성) */
export default async function BranchAnalysisIndex(props: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const office = officeParam(await props.searchParams);
  const [{ current }, offices] = await Promise.all([getBranchTabs(office), getBranchOffices().catch(() => ({ offices: [], default: null }))]);
  if (current.length > 0) redirect(withOffice(`/branch/analysis/${current[0].tabKey}`, office));
  // 고른 지점(또는 기본 지점)에 분석이 아직 없어도 관리자 · 영업본부는 다른 지점을 고를 수 있다
  const name = offices.offices.find((o) => o.code === (office ?? offices.default))?.name;
  return (
    <>
      <PageHeader eyebrow="2단계 · 분석 결과" title={name ? `${name} 분석 결과` : "분석 결과"} actions={<BranchOfficePicker list={offices} current={office ?? offices.default} action="/branch/analysis" />} />
      <BranchUnavailable officeName={name} />
    </>
  );
}
