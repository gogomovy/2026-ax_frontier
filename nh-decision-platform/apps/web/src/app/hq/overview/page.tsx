import { OverviewWorkspace } from "@/components/domain/OverviewWorkspace";
import { PageHeader } from "@/components/layout/PageHeader";
import {
  getAttentions,
  getCapitalView,
  getDomains,
  getGoals,
  getLoanOverview,
  getProposals,
  getReportRequests,
} from "@/lib/data";

/** STEP 1 — 사업부문 현황과 경영목표, 은행 종합목표 (요구사항 DASH-01/02/06, GOAL-04) */
export default async function OverviewPage() {
  const [domains, goals, loan, capital, attentions, requests, proposals] = await Promise.all([
    getDomains(),
    getGoals(),
    getLoanOverview(),
    getCapitalView(),
    getAttentions(),
    getReportRequests(),
    getProposals(),
  ]);

  return (
    <>
      <PageHeader
        eyebrow="1단계"
        title="현황·목표"
        description="Agent 가 사업 데이터와 현재 경영목표를 미리 분석해 두었습니다. 사업부문을 선택해 확인하세요."
      />
      <OverviewWorkspace
        domains={domains}
        goals={goals}
        loan={loan}
        capital={capital}
        pending={{
          attentions: attentions.length,
          requests: requests.filter((r) => r.status !== "done").length,
          proposals: proposals.length,
        }}
      />
    </>
  );
}
