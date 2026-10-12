import { notFound } from "next/navigation";
import { AnalysisReportPage } from "@/components/analysis/AnalysisReportPage";
import { NextStep } from "@/components/ui/primitives";
import { getSpaceReport, getSpaceTabs } from "@/lib/data";

export const dynamic = "force-dynamic";

/** 종합기획부 STEP 2 — 맞춤 분석 탭(분석 에이전트 보고서). 같은 [데이터 분석] 화면의 탭으로 이어진다 (Q109) */
export default async function HqCustomAnalysisPage(props: { params: Promise<{ tabKey: string }> }) {
  const { tabKey } = await props.params;
  if (!tabKey.startsWith("an-")) notFound();
  const [tabs, report] = await Promise.all([getSpaceTabs("hq"), getSpaceReport("hq", tabKey)]);
  if (!tabs || !report) notFound();
  return (
    <AnalysisReportPage
      eyebrow="2단계 · 데이터 분석 · 맞춤 분석"
      report={report}
      tabs={tabs.current}
      previous={tabs.previous}
      activeKey={tabKey}
      basePath="/hq/analysis"
      lead={[{ href: "/hq/analysis", label: "여신 실적 분석" }]}
      builderHref={tabs.builder.allowed ? "/analysis/builder?space=hq" : null}
      next={<NextStep step={3} title="경영목표 설정" description="분석 결과를 참고해 경영목표 제안을 검토하고 확정합니다." href="/hq/goals" />}
    />
  );
}
