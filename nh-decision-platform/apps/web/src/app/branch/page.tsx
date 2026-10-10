import { BranchKpiBoard } from "@/components/domain/BranchKpiBoard";
import { BranchSegments } from "@/components/domain/BranchSegments";
import { BranchUnavailable } from "@/components/domain/BranchUnavailable";
import { ChangeFeedPanel } from "@/components/domain/ChangeFeedPanel";
import { EvidenceChips } from "@/components/evidence/EvidenceChips";
import { PageHeader } from "@/components/layout/PageHeader";
import { NextStep, SectionHead } from "@/components/ui/primitives";
import { getBranchDashboard, getChanges } from "@/lib/data";

// 영업점 산출물은 사용자 소속에 따라 달라지고 일 단위로 갱신되므로 요청 시 렌더링한다
export const dynamic = "force-dynamic";

/** 영업점 STEP 1 — 업적평가 득점 · 기준 변경 알림 · 사업부문 현황 (시나리오 첫 번째 화면) */
export default async function BranchHomePage() {
  const dashboard = await getBranchDashboard();
  const changes = await getChanges(dashboard.workflow ?? undefined);
  if (!dashboard.available) {
    return (
      <>
        <PageHeader eyebrow="1단계 · 현황" title={`${dashboard.viewer?.name ?? "영업점"} 현황`} />
        <BranchUnavailable officeName={dashboard.viewer?.name} />
      </>
    );
  }

  return (
    <>
      <PageHeader
        eyebrow="1단계 · 현황"
        title={`${dashboard.office.name} 현황`}
        description={`${dashboard.periodLabel} 업적평가 득점과 사업부문 현황입니다. 상반기 대비 바뀐 평가기준은 Agent 가 분석해 영업 가이드로 정리했습니다.`}
      />

      <div className="shell flex flex-col gap-xxl">
        <section>
          <SectionHead title="업적평가 득점 현황" hint={`리테일 배점표 · ${dashboard.asOfLabel}`} right={<EvidenceChips items={dashboard.evidence} title="업적평가 기준 근거" />} />
          <BranchKpiBoard dashboard={dashboard} />
        </section>

        <BranchSegments dashboard={dashboard} />

        <ChangeFeedPanel feed={changes} />

        <NextStep step={2} title="분석 결과" description="기준 변경 항목별 포트폴리오 분석과 Agent 영업 가이드를 보고서로 확인합니다." href="/branch/analysis" />
      </div>
    </>
  );
}
