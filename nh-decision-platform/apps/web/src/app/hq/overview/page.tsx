import { ChangeFeedPanel } from "@/components/domain/ChangeFeedPanel";
import { OverviewWorkspace } from "@/components/domain/OverviewWorkspace";
import { AsOfTools, ExportButton } from "@/components/layout/PageTools";
import { PageHeader } from "@/components/layout/PageHeader";
import { getAttentions, getCapitalView, getChanges, getDomains, getGoals, getLoanOverview, getProposals } from "@/lib/data";

/** STEP 1 — 경영 현황·목표 (요구사항 DASH-01/02/06, GOAL-04) */
export default async function OverviewPage() {
  const [domains, goals, loan, capital, attentions, proposals, changes] = await Promise.all([
    getDomains(),
    getGoals(),
    getLoanOverview(),
    getCapitalView(),
    getAttentions(),
    getProposals(),
    getChanges(),
  ]);

  return (
    <>
      <PageHeader
        title="경영 현황·목표"
        actions={
          <AsOfTools>
            <ExportButton />
          </AsOfTools>
        }
      />
      <OverviewWorkspace
        domains={domains}
        goals={goals}
        loan={loan}
        capital={capital}
        proposals={proposals}
        attentions={attentions}
        aside={<ChangeFeedPanel feed={changes} />}
      />
    </>
  );
}
