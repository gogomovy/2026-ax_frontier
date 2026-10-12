import { notFound } from "next/navigation";
import { DynamicTabBar } from "@/components/domain/DynamicTabBar";
import { ReportActions, ReportView } from "@/components/domain/ReportView";
import { PageHeader } from "@/components/layout/PageHeader";
import { NextStep } from "@/components/ui/primitives";
import { officeParam, withOffice } from "@/lib/branchOffice";
import { getBranchReport, getBranchTabs } from "@/lib/data";

export const dynamic = "force-dynamic";

/** 영업점 STEP 2 — 기준 변경 항목별 분석 보고서(2 · 3화면). Agent 의견 → 보고서 본문 순서 */
export default async function BranchAnalysisTabPage(props: { params: Promise<{ tabKey: string }>; searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const params = await props.params;
  const office = officeParam(await props.searchParams);
  const [tabs, report] = await Promise.all([getBranchTabs(office), getBranchReport(params.tabKey, office)]);
  if (!report) notFound();
  const others = tabs.current.filter((t) => t.tabKey !== params.tabKey);

  return (
    <>
      <PageHeader
        eyebrow={`2단계 · 분석 결과${report.office ? ` · ${report.office.name}` : ""}`}
        title={report.title}
        description={report.subtitle}
        actions={<ReportActions report={report} tabKey={`branch-${params.tabKey}`} office={office} />}
      >
        <DynamicTabBar tabs={tabs.current} previous={tabs.previous} activeKey={params.tabKey} basePath="/branch/analysis" query={office ? `?office=${encodeURIComponent(office)}` : ""} />
      </PageHeader>

      <ReportView report={report} />

      <div className="shell mt-section">
        {others.length > 0 ? (
          <NextStep step={2} title={others[0].label} description="다음 기준 변경 항목의 분석과 Agent 영업 가이드를 확인합니다." href={withOffice(`/branch/analysis/${others[0].tabKey}`, office)} />
        ) : (
          <NextStep step={1} title="현황으로 돌아가기" description="업적평가 득점과 사업부문 현황을 다시 확인합니다." href={withOffice("/branch", office)} />
        )}
      </div>
    </>
  );
}
