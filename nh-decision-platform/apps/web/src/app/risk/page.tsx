import { AnalysisAlertStrip } from "@/components/domain/AnalysisAlertStrip";
import { ChangeFeedPanel } from "@/components/domain/ChangeFeedPanel";
import { DefaultRatePanel } from "@/components/domain/DefaultRatePanel";
import { ModelMonitoringPanel } from "@/components/domain/ModelMonitoringPanel";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge, NextStep, RowList, SectionHead } from "@/components/ui/primitives";
import { formatDate } from "@/lib/format";
import { getAnalysisTabs, getChanges, getDefaultRateTrend, getRiskDashboard } from "@/lib/data";

const QUALITY = {
  passed: { label: "정상", tone: "success" },
  warning: { label: "주의", tone: "attention" },
  failed: { label: "미제공", tone: "critical" },
} as const;

/** STEP 1 — 신용리스크관리부 현황 (요구사항 CRM-01 ~ CRM-04, MDL-13) */
export default async function RiskDashboardPage() {
  const [dashboard, trend, { current }, changes] = await Promise.all([
    getRiskDashboard(),
    getDefaultRateTrend(),
    getAnalysisTabs(),
    getChanges(),
  ]);

  return (
    <>
      <PageHeader
        eyebrow="1단계"
        title="현황"
        description="부도율 추이와 모형 모니터링이 미리 분석되어 있습니다. 새 분석 결과는 바로 아래에서 열 수 있습니다."
      />

      <div className="shell flex flex-col gap-xxl">
        <AnalysisAlertStrip opinions={dashboard.opinions} tabs={current} generatedAt={dashboard.generatedAt} />

        <DefaultRatePanel trend={trend} />

        <div className="grid grid-cols-1 gap-xl xl:grid-cols-2">
          <section>
            <SectionHead title="현재 적용 경영목표" hint="종합기획부 확정 · Agent 판단 기준" />
            <RowList>
              {dashboard.appliedGoals.map((goal) => (
                <li key={goal.title} className="flex items-center gap-md px-base py-3">
                  <span className="min-w-0 flex-1">
                    <span className="block text-[13px] font-bold text-ink-deep">{goal.title}</span>
                    <span className="mt-0.5 block text-[11.5px] text-stone">
                      {goal.source} · {formatDate(goal.updatedAt)}
                    </span>
                  </span>
                  <span className="shrink-0 text-[13px] font-bold text-primary tnum">{goal.value}</span>
                </li>
              ))}
            </RowList>
          </section>

          <section>
            <SectionHead title="데이터 품질" hint="미제공 항목은 분석에서 제외하고 한계로 표기합니다" />
            <RowList>
              {dashboard.dataQuality.map((item) => (
                <li key={item.label} className="flex items-start gap-md px-base py-3">
                  <span className="min-w-0 flex-1">
                    <span className="block text-[13px] font-bold text-ink-deep">{item.label}</span>
                    <span className="mt-0.5 block text-[11.5px] leading-snug text-stone">{item.note}</span>
                  </span>
                  <Badge tone={QUALITY[item.status].tone}>{QUALITY[item.status].label}</Badge>
                </li>
              ))}
            </RowList>
          </section>
        </div>

        <ModelMonitoringPanel corp={dashboard.corpModels} retail={dashboard.retailModels} />
        <ChangeFeedPanel feed={changes} />

        <NextStep
          step={2}
          title="분석 결과"
          description="특이사항별 보고서를 Agent 의견부터 확인하고, 필요하면 보고서 문서로 내려받습니다."
          href={current[0] ? `/risk/analysis/${current[0].tabKey}` : "/risk/analysis"}
        />
      </div>
    </>
  );
}
