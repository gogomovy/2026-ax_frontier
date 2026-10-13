"use client";

import { useState } from "react";
import { PlanRowMain } from "@/components/domain/GuideWorkspace";
import { PlanSheet } from "@/components/domain/PlanSheet";
import { usePlanState } from "@/components/providers/PlanStateProvider";
import { RowEmpty, RowList, SectionHead } from "@/components/ui/primitives";

/**
 * 사업부서 가이드 (요구사항 BR-01, CRM-08)
 * 사업부서가 `영업점 참고 가능`으로 켠 진행사업만 노출된다. 꺼지면 즉시 사라진다.
 */
export function BranchGuides() {
  const { inProgressPlans } = usePlanState();
  const [openId, setOpenId] = useState<string | null>(null);
  const shared = inProgressPlans.filter((p) => p.branchShared);
  const viewing = openId ? shared.find((p) => p.id === openId) : undefined;

  return (
    <section>
      <SectionHead title="사업부서 가이드" hint={`${shared.length}건 · 영업점 AI가 참고하는 진행사업`} />
      {shared.length === 0 ? (
        <RowEmpty
          title="참고 가능한 사업부서 가이드가 없습니다"
          description="사업부서가 진행사업의 영업점 참고를 켜면 이곳에 표시되고, 영업점 AI 판단 기준에 반영됩니다."
        />
      ) : (
        <RowList>
          {shared.map((plan) => (
            <li key={plan.id} className="flex items-center gap-md pr-lg">
              <PlanRowMain plan={plan} onOpen={() => setOpenId(plan.id)} />
              <span className="shrink-0 text-[12px] text-stone">{plan.ownerOrg}</span>
            </li>
          ))}
        </RowList>
      )}
      {viewing ? <PlanSheet key={viewing.id} plan={viewing} tabs={[]} readOnly onClose={() => setOpenId(null)} /> : null}
    </section>
  );
}
