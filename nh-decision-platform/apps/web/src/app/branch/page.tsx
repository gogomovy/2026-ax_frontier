import { BranchKpiBoard } from "@/components/domain/BranchKpiBoard";
import { BranchOfficePicker } from "@/components/domain/BranchOfficePicker";
import { BranchSegments } from "@/components/domain/BranchSegments";
import { BranchUnavailable } from "@/components/domain/BranchUnavailable";
import { ChangeFeedPanel } from "@/components/domain/ChangeFeedPanel";
import { EvidenceChips } from "@/components/evidence/EvidenceChips";
import { PageHeader } from "@/components/layout/PageHeader";
import { NextStep, SectionHead } from "@/components/ui/primitives";
import { getBranchDashboard, getBranchOffices, getChanges } from "@/lib/data";
import { officeParam, withOffice } from "@/lib/branchOffice";

// 영업점 산출물은 사용자 소속에 따라 달라지고 일 단위로 갱신되므로 요청 시 렌더링한다
export const dynamic = "force-dynamic";

/** 영업점 STEP 1 — 업적평가 득점 · 기준 변경 알림 · 사업부문 현황 (시나리오 첫 번째 화면) */
export default async function BranchHomePage(props: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const office = officeParam(await props.searchParams);
  const [dashboard, offices] = await Promise.all([getBranchDashboard(office), getBranchOffices().catch(() => ({ offices: [], default: null }))]);
  const changes = await getChanges(dashboard.workflow ?? undefined);
  const picker = <BranchOfficePicker list={offices} current={office ?? offices.default} action="/branch" />;
  if (!dashboard.available) {
    const picked = offices.offices.find((o) => o.code === (office ?? offices.default));
    const name = picked?.name ?? dashboard.viewer?.name;
    return (
      <>
        <PageHeader eyebrow="1단계 · 현황" title={`${name ?? "영업점"} 현황`} actions={picker} />
        <BranchUnavailable officeName={name} />
      </>
    );
  }

  return (
    <>
      <PageHeader
        eyebrow="1단계 · 현황"
        title={`${dashboard.office.name} 현황`}
        description={`${dashboard.periodLabel} 업적평가 득점과 사업부문 현황입니다. 상반기 대비 바뀐 평가기준은 Agent 가 분석해 영업 가이드로 정리했습니다.`}
        actions={picker}
      />

      <div className="shell flex flex-col gap-xxl">
        <section>
          <SectionHead title="업적평가 득점 현황" hint={`리테일 배점표 · ${dashboard.asOfLabel}`} right={<EvidenceChips items={dashboard.evidence} title="업적평가 기준 근거" />} />
          <BranchKpiBoard dashboard={dashboard} office={office} />
        </section>

        <BranchSegments dashboard={dashboard} office={office} />

        <ChangeFeedPanel feed={changes} />

        <NextStep step={2} title="분석 결과" description="기준 변경 항목별 포트폴리오 분석과 Agent 영업 가이드를 보고서로 확인합니다." href={withOffice("/branch/analysis", office)} />
      </div>
    </>
  );
}
