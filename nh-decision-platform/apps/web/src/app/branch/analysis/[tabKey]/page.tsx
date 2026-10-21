import { notFound } from "next/navigation";
import { PrimeCorpReport } from "@/components/analysis/report/branch/PrimeCorpReport";
import { SeominReport } from "@/components/analysis/report/branch/SeominReport";
import { ReportShell } from "@/components/analysis/report/ReportShell";
import { DynamicReport } from "@/components/analysis/report/DynamicReport";
import { NextStep } from "@/components/ui/primitives";
import { officeParam, withOffice } from "@/lib/branchOffice";
import { BranchOfficePicker } from "@/components/domain/BranchOfficePicker";
import { getBranchOffices, getBranchReport, getBranchTabs } from "@/lib/data";
import type { ReportDoc } from "@/lib/types";
export const dynamic = "force-dynamic";
/** 시안대로 그린 본문 (보고서 종류별) — 그 밖의 종류는 기존 보고서 보기 */
function bodyOf(report: ReportDoc) {
  if (report.kind === "branch_prime_corp") return <PrimeCorpReport report={report} rerun={report.workflow} />;
  if (report.kind === "branch_seomin") return <SeominReport report={report} rerun={report.workflow} />;
  if (report.kind === "dynamic") return <DynamicReport report={report} rerun={report.workflow} />;
  return null;
}
/** 영업점 STEP 2 — 기준 변경 항목별 분석 결과 (시안 346:2 우량기업여신 · 348:2 서민금융) */
export default async function BranchAnalysisTabPage(props: { params: Promise<{ tabKey: string }>; searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const params = await props.params;
  const office = officeParam(await props.searchParams);
  const [tabs, report, offices] = await Promise.all([getBranchTabs(office), getBranchReport(params.tabKey, office), getBranchOffices().catch(() => ({ offices: [], default: null }))]);
  if (!report) notFound();
  // 지점 선택은 분석 첫 화면으로 — 고른 지점의 첫 분석 탭으로 이동한다
  const picker = <BranchOfficePicker list={offices} current={office ?? report.office?.code ?? offices.default} action="/branch/analysis" />;
  const others = tabs.current.filter((t) => t.tabKey !== params.tabKey);
  const officeName = report.office?.name ?? tabs.office?.name;
  return (
    <ReportShell
      title={officeName ? `${officeName} 분석 결과` : "분석 결과"}
      report={report}
      tabs={tabs.current}
      previous={tabs.previous}
      activeKey={params.tabKey}
      basePath="/branch/analysis"
      query={office ? `?office=${encodeURIComponent(office)}` : ""}
      exportKey={`branch-${params.tabKey}`}
      office={office}
      picker={picker}
      next={
        others.length > 0 ? (
          <NextStep step={2} title={others[0].label} description="다음 기준 변경 항목의 분석과 AI 영업 가이드를 확인합니다." href={withOffice(`/branch/analysis/${others[0].tabKey}`, office)} />
        ) : (
          <NextStep step={1} title="현황으로 돌아가기" description="업적평가 득점과 사업부문 현황을 다시 확인합니다." href={withOffice("/branch", office)} />
        )
      }
    >
      {bodyOf(report)}
    </ReportShell>
  );
}
