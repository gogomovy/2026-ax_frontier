import { AnalysisWorkspace } from "@/components/domain/AnalysisWorkspace";
import { getComparisonView, getLoanOverview, getProducer, getSpaceTabsOptional } from "@/lib/data";

export const dynamic = "force-dynamic";

/** STEP 2 — 여신 데이터 설명·분석 (요구사항 LOAN-01~11, AST-07/08) + 맞춤 분석 탭(분석 에이전트 · Q109) */
export default async function AnalysisPage() {
  const [overview, comparison, workflow, space] = await Promise.all([getLoanOverview(), getComparisonView(), getProducer("loan_overview"), getSpaceTabsOptional("hq")]);
  return (
    <AnalysisWorkspace
      overview={overview}
      comparison={comparison}
      workflow={workflow}
      custom={space?.current ?? []}
      builderHref={space?.builder.allowed ? "/analysis/builder?space=hq" : null}
    />
  );
}
