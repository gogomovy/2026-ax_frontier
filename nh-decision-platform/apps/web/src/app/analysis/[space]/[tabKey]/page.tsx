import { notFound } from "next/navigation";
import { AnalysisReportPage } from "@/components/analysis/AnalysisReportPage";
import { NextStep } from "@/components/ui/primitives";
import { getSpaceReport, getSpaceTabs } from "@/lib/data";

export const dynamic = "force-dynamic";

/** 부서 분석 보고서 (Phase C · DAG-06 · DAG-07) — 분석 레지스트리의 탭 · 보고서를 같은 표시 단계로 */
export default async function AnalysisSpaceTabPage(props: { params: Promise<{ space: string; tabKey: string }> }) {
  const { space, tabKey } = await props.params;
  const [tabs, report] = await Promise.all([getSpaceTabs(space), getSpaceReport(space, tabKey)]);
  if (!tabs || !report) notFound();
  const others = tabs.current.filter((t) => t.tabKey !== tabKey);
  const builderHref = tabs.builder.allowed ? `/analysis/builder?space=${encodeURIComponent(space)}` : null;
  return (
    <AnalysisReportPage
      crumbs={[{ label: tabs.space.label }, { label: "분석 보고서", href: `/analysis/${space}` }, { label: report.title }]}
      report={report}
      tabs={tabs.current}
      previous={tabs.previous}
      activeKey={tabKey}
      basePath={`/analysis/${space}`}
      builderHref={builderHref}
      next={
        others.length ? (
          <NextStep step={2} title={others[0].label} description="같은 부서의 다른 분석 결과를 확인합니다." href={`/analysis/${space}/${others[0].tabKey}`} />
        ) : builderHref ? (
          <NextStep step={1} title="새 분석 만들기" description="다른 관점의 분석이 필요하면 글로 적어 분석 에이전트에게 맡기세요." href={builderHref} />
        ) : null
      }
    />
  );
}
