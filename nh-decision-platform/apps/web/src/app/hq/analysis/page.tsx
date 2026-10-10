import { AnalysisWorkspace } from "@/components/domain/AnalysisWorkspace";
import { getComparisonView, getLoanOverview } from "@/lib/data";

/** STEP 2 — 여신 데이터 설명·분석 (요구사항 LOAN-01~11, AST-07/08) */
export default async function AnalysisPage() {
  const [overview, comparison] = await Promise.all([getLoanOverview(), getComparisonView()]);
  return <AnalysisWorkspace overview={overview} comparison={comparison} />;
}
