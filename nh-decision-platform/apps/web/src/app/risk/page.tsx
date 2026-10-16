import { ChangeFeedPanel } from "@/components/domain/ChangeFeedPanel";
import { RiskOverview } from "@/components/domain/RiskOverview";
import { AsOfTools, ExportButton } from "@/components/layout/PageTools";
import { NextStep } from "@/components/ui/primitives";
import { getAnalysisTabs, getChanges, getDefaultRateTrend, getRiskDashboard } from "@/lib/data";

/** STEP 1 — 신용리스크관리부 현황 (요구사항 CRM-01 ~ CRM-04, MDL-13) · 종기부 시안 3 구조 */
export default async function RiskDashboardPage() {
  const [dashboard, trend, { current }, changes] = await Promise.all([
    getRiskDashboard(),
    getDefaultRateTrend(),
    getAnalysisTabs(),
    getChanges(),
  ]);

  return (
    <div className="shell flex flex-col pb-6 pt-5">
      {dashboard.computed === false ? (
        // 자료 업로드 전(값 없는 틀) 안내 — 시안 반영 전 화면과 같은 문구
        <p className="mb-4 rounded-lg bg-surface-soft px-4 py-3 text-[13px] text-steel" data-risk-not-computed>
          아직 계산된 자료가 없습니다. 모형 등급별 집계 · 월별 부도율 자료를 올리면 부도율 추이와 모형 모니터링이 계산되고, 새 분석 결과가 이곳에 나타납니다.
        </p>
      ) : null}
      <RiskOverview
        dashboard={dashboard}
        trend={trend}
        tabs={current}
        tools={
          <AsOfTools key="page-tools">
            <ExportButton />
          </AsOfTools>
        }
      >
        <div className="mt-4">
          <ChangeFeedPanel feed={changes} compact />
        </div>
        <div className="mt-4">
          <NextStep
            step={2}
            title="분석 결과"
            description="특이사항별 보고서를 AI 의견부터 확인하고, 필요하면 보고서 문서로 내려받습니다."
            href={current[0] ? `/risk/analysis/${current[0].tabKey}` : "/risk/analysis"}
          />
        </div>
      </RiskOverview>
    </div>
  );
}
