import { notFound } from "next/navigation";
import { ReportShell } from "@/components/analysis/report/ReportShell";
import { InclusiveRiskReport } from "@/components/analysis/report/risk/InclusiveRiskReport";
import { ModelMonitoringReport } from "@/components/analysis/report/risk/ModelMonitoringReport";
import { ProvisionShareReport } from "@/components/analysis/report/risk/ProvisionShareReport";
import { NextStep } from "@/components/ui/primitives";
import { getAnalysisTabs, getReport, getRiskDashboard } from "@/lib/data";
import { isProvisionShareReport } from "@/lib/provisionShare";
import type { ModelSummaryRow, ReportDoc } from "@/lib/types";
// 데이터(분석 탭·문서)가 실행 시점에 바뀌므로 요청 시 렌더링한다
export const dynamic = "force-dynamic";
/** 보고서 수치와 같은 모형의 현황 판정 행 (PSI · AR 수치 id 로 찾는다) */
function modelRowOf(report: ReportDoc, rows: ModelSummaryRow[]): ModelSummaryRow | null {
  return rows.find((r) => (r.psi && report.figures[r.psi.id]) || report.figures[r.ar.id]) ?? null;
}
/** STEP 2 — 분석 결과 (시안 350:2 모형 모니터링 · 352:2 포용금융 · 389:2 상품별 충당금 비중(분석 에이전트 탭)). 시안이 없는 탭(그 밖의 분석 에이전트 · 이전 세대)은 기존 보고서 보기 */
export default async function AnalysisTabPage(props: { params: Promise<{ tabKey: string }> }) {
  const params = await props.params;
  const [tabs, report] = await Promise.all([getAnalysisTabs(), getReport(params.tabKey)]);
  if (!report) notFound();
  // 모형 판정(조건부 적정 등)은 현황의 모형 행에서 — 없으면 '–'
  const model = report.kind === "model_monitoring" && tabs.current.some((t) => t.tabKey === params.tabKey) ? await getRiskDashboard().then((d) => modelRowOf(report, [...d.corpModels, ...(d.retailModels ?? [])])).catch(() => null) : null;
  // 시안 본문은 현재 세대 탭만 — 이전 세대(열람 전용)는 기존 보고서 보기
  const current = tabs.current.some((t) => t.tabKey === params.tabKey);
  const body = !current
    ? null
    : report.kind === "model_monitoring" ? (
      <ModelMonitoringReport report={report} model={model} rerun={report.workflow} />
    ) : report.kind === "inclusive_risk" ? (
      <InclusiveRiskReport report={report} rerun={report.workflow} />
    ) : report.kind === "dynamic" && isProvisionShareReport(report) ? (
      <ProvisionShareReport report={report} />
    ) : null;
  return (
    <ReportShell
      title={tabs.space?.label ? `${tabs.space.label} 분석 결과` : "분석 결과"}
      report={report}
      tabs={tabs.current}
      previous={tabs.previous}
      activeKey={params.tabKey}
      basePath="/risk/analysis"
      builderHref={tabs.builder?.allowed ? "/analysis/builder?space=risk" : null}
      next={
        <NextStep
          step={3}
          title="수행방안"
          description="분석에서 도출된 가이드를 검토해 진행사업으로 등록하고, 영업점 참고 여부를 정합니다."
          href="/risk/guides"
        />
      }
    >
      {body}
    </ReportShell>
  );
}
