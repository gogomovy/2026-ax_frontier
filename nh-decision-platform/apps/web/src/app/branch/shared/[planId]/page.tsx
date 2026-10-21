import { notFound } from "next/navigation";
import { ReportView } from "@/components/domain/ReportView";
import { PageHeader } from "@/components/layout/PageHeader";
import { Notice } from "@/components/ui/Layout";
import { NextStep } from "@/components/ui/primitives";
import { getSharedPlanReport } from "@/lib/data";
import { asOfText } from "@/lib/linkedAnalysis";

// 사업부서가 다시 계산하면 같은 보고서의 새 세대를 보여 준다 — 요청 때마다 그린다
export const dynamic = "force-dynamic";

/**
 * 영업점 공통 공유 보고서 — 사업부서가 수행방안 '영업점 참고'를 켠 진행사업의 연결 분석 보고서.
 * 복사본이 아니라 사업부서 보고서의 지금 세대 그대로(다시 계산하면 따라 바뀐다). 참고를 끄면 더 이상 열리지 않는다(404).
 * 다시 실행 · 내려받기는 사업부서 화면에서만 — 여기서는 보고서 · 근거 문서를 본다.
 */
export default async function BranchSharedReportPage(props: { params: Promise<{ planId: string }> }) {
  const { planId } = await props.params;
  const report = await getSharedPlanReport(planId);
  if (!report) notFound();
  const plan = report.sharedPlan;
  const from = [report.analysisFrom, plan.ownerOrg && plan.ownerOrg !== report.analysisFrom ? plan.ownerOrg : null].filter(Boolean).join(" · ");
  return (
    <>
      <PageHeader
        compact
        crumbs={[{ label: "본부 전파 목표·가이드", href: "/branch/targets" }, { label: plan.title ?? "수행방안" }]}
        eyebrow={plan.scope}
        title={report.title}
        description={
          <>
            {from ? `${from}의 분석 결과` : "사업부서 분석 결과"}
            {report.asOf ? ` · ${asOfText(report.asOf)} 기준` : ""}
            {plan.title ? ` — 수행방안 '${plan.title}'에 연결된 보고서입니다.` : ""}
          </>
        }
      />
      <div className="shell mb-lg">
        <Notice tone="info" title="사업부서가 영업점 참고로 공유한 분석입니다">
          사업부서 보고서의 지금 결과를 그대로 보여 줍니다. 사업부서가 다시 계산하면 이 화면도 바뀌고, 영업점 참고를 끄면 더 이상 볼 수 없습니다. 수치는 사업부서 기준이라 우리 지점 수치와 다를 수 있습니다.
        </Notice>
      </div>
      <ReportView report={report} />
      <div className="shell mt-section pb-6">
        <NextStep step={1} title="본부 전파 목표·가이드" description="공유된 수행방안과 본부 목표를 함께 확인합니다." href="/branch/targets" />
      </div>
    </>
  );
}
