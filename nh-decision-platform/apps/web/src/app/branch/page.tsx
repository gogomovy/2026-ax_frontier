import { BranchOfficePicker } from "@/components/domain/BranchOfficePicker";
import { BranchOverview } from "@/components/domain/BranchOverview";
import { BranchUnavailable } from "@/components/domain/BranchUnavailable";
import { ChangeFeedPanel } from "@/components/domain/ChangeFeedPanel";
import { PageHeader } from "@/components/layout/PageHeader";
import { AsOfTools, ExportButton } from "@/components/layout/PageTools";
import { NextStep } from "@/components/ui/primitives";
import { getBranchDashboard, getBranchOffices, getBranchReport, getChanges } from "@/lib/data";
import { officeParam, withOffice } from "@/lib/branchOffice";
import { guideBasis, type GuideBasis } from "@/lib/branchGuideBasis";
import type { Evidence } from "@/lib/types";

// 영업점 산출물은 사용자 소속에 따라 달라지고 일 단위로 갱신되므로 요청 시 렌더링한다
export const dynamic = "force-dynamic";

/** 영업점 STEP 1 — 업적평가 총득점 · 가점 확보 방안 · KPI별 득점 · 사업부문 (Figma 326:2) */
export default async function BranchHomePage(props: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const office = officeParam(await props.searchParams);
  const [dashboard, offices] = await Promise.all([getBranchDashboard(office), getBranchOffices().catch(() => ({ offices: [], default: null }))]);
  const picker = <BranchOfficePicker list={offices} current={office ?? offices.default} action="/branch" />;
  if (!dashboard.available) {
    const picked = offices.offices.find((o) => o.code === (office ?? offices.default));
    const name = picked?.name ?? dashboard.viewer?.name;
    return (
      <>
        <PageHeader eyebrow="1단계 · 현황" title={`${name ?? "영업점"} 현황`} actions={picker} />
        <BranchUnavailable officeName={name} reason={dashboard.reason} />
      </>
    );
  }

  // 가이드별 근거 — 분석 보고서의 AI 의견 근거 (보고서가 없으면 빈 목록)
  const [changes, reports] = await Promise.all([
    getChanges(dashboard.workflow ?? undefined),
    Promise.all(dashboard.alerts.map((a) => getBranchReport(a.tabKey, office).catch(() => null))),
  ]);
  const guideEvidence: Record<string, Evidence[]> = Object.fromEntries(
    dashboard.alerts.map((a, i) => {
      const r = reports[i];
      // 가이드와 같은 의견의 근거만 쓴다 — 못 찾으면 보고서 전체 근거(다른 가이드의 의견 근거를 빌려오지 않는다)
      const op = r?.opinions.find((o) => o.id === a.insightId);
      return [a.tabKey, op?.evidence ?? r?.evidence ?? []];
    }),
  );

  // 근거 펼침 — 지점 vs 전행 비교 · 후보 기업 / 대상 상품 (시안 358:130). 보고서가 없으면 위 근거 목록
  const guideBases: Record<string, GuideBasis | null> = Object.fromEntries(dashboard.alerts.map((a, i) => [a.tabKey, guideBasis(a, reports[i])]));
  return (
    <div className="shell flex flex-col pb-6 pt-5">
      <BranchOverview
        dashboard={dashboard}
        office={office}
        guideEvidence={guideEvidence}
        guideBases={guideBases}
        picker={picker}
        tools={
          <AsOfTools key="page-tools">
            <ExportButton />
          </AsOfTools>
        }
      >
        <>
          <div key="changes" className="mt-4">
            <ChangeFeedPanel feed={changes} compact dense />
          </div>
          <div key="next" className="mt-4">
            <NextStep step={2} title="분석 결과" description="기준 변경 항목별 포트폴리오 분석과 AI 영업 가이드를 보고서로 확인합니다." href={withOffice("/branch/analysis", office)} />
          </div>
        </>
      </BranchOverview>
    </div>
  );
}
