import { notFound } from "next/navigation";
import { DynamicReport } from "@/components/analysis/report/DynamicReport";
import { ReportShell } from "@/components/analysis/report/ReportShell";
import { NextStep } from "@/components/ui/primitives";
import { getSpaceReport, getSpaceTabs } from "@/lib/data";
import { HQ_ANALYSIS_TABS } from "@/lib/hqAnalysisTabs";

export const dynamic = "force-dynamic";

/** 종합기획부 STEP 2 — 맞춤 분석 탭(분석 에이전트 보고서). [데이터 분석] 화면의 기본 탭 줄을 그대로 앞에 두고, 본문은 다른 분석 결과 화면과 같은 시안 조각으로 (Q109) */
export default async function HqCustomAnalysisPage(props: { params: Promise<{ tabKey: string }> }) {
  const { tabKey } = await props.params;
  if (!tabKey.startsWith("an-")) notFound();
  const [tabs, report] = await Promise.all([getSpaceTabs("hq"), getSpaceReport("hq", tabKey)]);
  if (!tabs || !report) notFound();
  return (
    <ReportShell
      title="데이터 분석"
      report={report}
      tabs={tabs.current}
      previous={tabs.previous}
      activeKey={tabKey}
      basePath="/hq/analysis"
      lead={HQ_ANALYSIS_TABS.map((t) => ({ href: `/hq/analysis?tab=${t.key}`, label: t.label }))}
      builderHref={tabs.builder.allowed ? "/analysis/builder?space=hq" : null}
      next={<NextStep step={3} title="경영목표 설정" description="분석 결과를 참고해 경영목표 제안을 검토하고 확정합니다." href="/hq/goals" />}
    >
      {report.kind === "dynamic" ? <DynamicReport report={report} rerun={report.workflow} /> : null}
    </ReportShell>
  );
}
