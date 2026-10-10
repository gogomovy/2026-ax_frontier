import { notFound } from "next/navigation";
import { DynamicTabBar } from "@/components/domain/DynamicTabBar";
import { ReportActions, ReportView } from "@/components/domain/ReportView";
import { PageHeader } from "@/components/layout/PageHeader";
import { NextStep } from "@/components/ui/primitives";
import { getAnalysisTabs, getReport } from "@/lib/data";

// 데이터(분석 탭·문서)가 실행 시점에 바뀌므로 요청 시 렌더링한다
export const dynamic = "force-dynamic";

/** STEP 2 — 분석 결과. 모든 탭은 Agent 의견에서 시작해 보고서 본문으로 이어진다. */
export default async function AnalysisTabPage(props: { params: Promise<{ tabKey: string }> }) {
  const params = await props.params;
  const [{ current, previous }, report] = await Promise.all([getAnalysisTabs(), getReport(params.tabKey)]);
  if (!report) notFound();

  return (
    <>
      <PageHeader
        eyebrow="2단계 · 분석 결과"
        title={report.title}
        description={report.subtitle}
        actions={<ReportActions report={report} tabKey={params.tabKey} />}
      >
        <DynamicTabBar tabs={current} previous={previous} activeKey={params.tabKey} />
      </PageHeader>

      <ReportView report={report} />

      <div className="shell mt-section">
        <NextStep
          step={3}
          title="수행방안"
          description="분석에서 도출된 가이드를 검토해 진행사업으로 등록하고, 영업점 참고 여부를 정합니다."
          href="/risk/guides"
        />
      </div>
    </>
  );
}
