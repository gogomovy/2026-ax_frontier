import { GuideWorkspace } from "@/components/domain/GuideWorkspace";
import { getAnalysisTabs } from "@/lib/data";

/** STEP 3 — 수행방안 (요구사항 CRM-06 ~ CRM-14, PROP-03) */
export default async function RiskGuidesPage() {
  const { current } = await getAnalysisTabs();
  return <GuideWorkspace tabs={current} />;
}
