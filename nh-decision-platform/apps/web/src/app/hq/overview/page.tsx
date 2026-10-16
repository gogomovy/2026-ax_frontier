import { OverviewMockup } from "@/components/domain/OverviewMockup";
import { AsOfTools, ExportButton } from "@/components/layout/PageTools";
import { getAttentions, getCapitalView, getDomains, getGoals, getLoanOverview, getProposals } from "@/lib/data";

/** STEP 1 — 경영 현황·목표 (요구사항 DASH-01/02/06, GOAL-04) · 종기부 시안 3 재설계 레이아웃 */
export const dynamic = "force-dynamic";

export default async function OverviewPage() {
  const [domains, goals, loan, capital, attentions, proposals] = await Promise.all([
    getDomains(),
    getGoals(),
    getLoanOverview(),
    getCapitalView(),
    getAttentions(),
    getProposals(),
  ]);

  return (
    <OverviewMockup
      domains={domains}
      goals={goals}
      loan={loan}
      capital={capital}
      proposals={proposals}
      attentions={attentions}
      tools={
        <AsOfTools key="page-tools">
          <ExportButton />
        </AsOfTools>
      }
    />
  );
}
