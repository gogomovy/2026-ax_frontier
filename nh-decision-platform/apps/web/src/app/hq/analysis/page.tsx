import { AnalysisWorkspace } from "@/components/domain/AnalysisWorkspace";
import { getAttentions, getComparisonView, getDomains, getGoals, getLoanOverview, getProducer, getSpaceTabsOptional } from "@/lib/data";

export const dynamic = "force-dynamic";

/** STEP 2 — 여신 데이터 설명·분석 (요구사항 LOAN-01~11, AST-07/08) + 맞춤 분석 탭(분석 에이전트 · Q109) */
export default async function AnalysisPage() {
  const [overview, comparison, workflow, space, domains, goals, attentions] = await Promise.all([
    getLoanOverview(),
    getComparisonView(),
    getProducer("loan_overview"),
    getSpaceTabsOptional("hq"),
    getDomains(),
    getGoals(),
    getAttentions(),
  ]);
  return (
    <AnalysisWorkspace
      overview={overview}
      comparison={comparison}
      domains={domains}
      goals={goals}
      headline={attentions.find((a) => a.subDomain === "revenue") ?? null}
      workflow={workflow}
      custom={space?.current ?? []}
      builderHref={space?.builder.allowed ? "/analysis/builder?space=hq" : null}
    />
  );
}
