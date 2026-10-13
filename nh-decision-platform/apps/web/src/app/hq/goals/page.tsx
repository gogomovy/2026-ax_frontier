import { GoalsWorkspace } from "@/components/domain/GoalsWorkspace";
import { getAttentions, getDomains, getGoals, getProposals, getReportRequests, getReviewQueue } from "@/lib/data";

/** STEP 3 — 경영목표 설정 (요구사항 DASH-03/04/05, GOAL-01~17, PROP-01~04) */
export default async function GoalsPage() {
  const [domains, attentions, requests, goals, proposals, reviewQueue] = await Promise.all([
    getDomains(),
    getAttentions(),
    getReportRequests(),
    getGoals(),
    getProposals(),
    getReviewQueue(),
  ]);

  return <GoalsWorkspace domains={domains} attentions={attentions} requests={requests} goals={goals} proposals={proposals} reviewQueue={reviewQueue} />;
}
