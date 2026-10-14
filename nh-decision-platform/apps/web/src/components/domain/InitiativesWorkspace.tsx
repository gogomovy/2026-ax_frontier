"use client";

import Link from "next/link";
import { useState } from "react";
import { PlanRowMain } from "@/components/domain/GuideWorkspace";
import { PlanSheet } from "@/components/domain/PlanSheet";
import { PageHeader } from "@/components/layout/PageHeader";
import { usePlanState } from "@/components/providers/PlanStateProvider";
import { useSession, useUiConfig } from "@/components/providers/SessionProvider";
import { IconChevron, PillTabs, RowEmpty, RowList, SectionHead } from "@/components/ui/primitives";

/**
 * 사업부서별 진행 사업 현황 (요구사항 PROP-06)
 * 사업부서가 진행사업으로 등록한 수행방안만 모인다. 등록 해제 시 이 화면에서도 즉시 빠진다.
 */
export function InitiativesWorkspace() {
  const { inProgressPlans } = usePlanState();
  const { menu } = useSession();
  const cfg = useUiConfig();
  // 사업부서 목록 = [화면 설정 › 업무 영역]의 사업부서 단위 — 화면이 있는 부서는 편입, 없는 부서는 편입 대기 (Phase K · HC-02 · SCP-02)
  const departments = (cfg.scopes.dept?.units ?? []).map((u) => ({ key: u.name, section: u.section, active: u.available }));
  const [picked, setDept] = useState<string | null>(null);
  const dept = picked ?? departments.find((d) => d.active)?.key ?? departments[0]?.key ?? "";
  const [openId, setOpenId] = useState<string | null>(null);

  const countOf = (org: string) => inProgressPlans.filter((p) => p.ownerOrg === org).length;
  const plans = inProgressPlans.filter((p) => p.ownerOrg === dept);
  const current = departments.find((d) => d.key === dept);
  const active = current?.active;
  // 수행방안 화면 — 그 부서 메뉴 묶음에서 건수 키가 수행방안(proposedPlans)인 화면(볼 권한이 있을 때만)
  const guideHref = menu?.sections.find((s) => s.section === current?.section)?.flow.find((i) => i.countKey === "proposedPlans")?.href ?? null;
  const viewing = openId ? inProgressPlans.find((p) => p.id === openId) : undefined;

  return (
    <>
      <PageHeader
        crumbs={[{ label: "현황·목표", href: "/hq/overview" }, { label: "사업부서 진행 사업" }]}
        title="사업부서 진행 사업"
        description="사업부서가 진행사업으로 등록한 수행방안입니다. 등록·해제와 영업점 참고 상태가 그대로 반영되고, 연결된 분석 보고서도 함께 볼 수 있습니다."
      >
        <PillTabs
          label="사업부서"
          items={departments.map((d) => ({ key: d.key, label: d.key, count: d.active ? countOf(d.key) : undefined }))}
          value={dept}
          onChange={(k) => {
            setDept(k);
            setOpenId(null);
          }}
        />
      </PageHeader>

      <div className="shell">
        <SectionHead
          title={`${dept} 진행사업`}
          hint={
            active
              ? `${plans.length}건 · 영업점 참고 ${plans.filter((p) => p.branchShared).length}건`
              : "플랫폼 편입 대기 부서"
          }
        />

        {!active ? (
          <RowEmpty
            title={`${dept}는 아직 플랫폼에 편입되지 않았습니다`}
            description="편입되면 같은 구조로 진행사업이 집계됩니다."
          />
        ) : plans.length === 0 ? (
          <RowEmpty
            title="등록된 진행사업이 없습니다"
            description="사업부서가 수행방안 화면에서 제안안을 진행사업으로 등록하면 이곳에 모입니다."
            action={
              guideHref ? (
                <Link href={guideHref} className="inline-flex items-center gap-1 text-[12.5px] font-bold text-primary">
                  사업부서 수행방안 화면 <IconChevron />
                </Link>
              ) : undefined
            }
          />
        ) : (
          <RowList>
            {plans.map((plan) => (
              <li key={plan.id} className="flex items-center gap-md pr-lg">
                <PlanRowMain plan={plan} onOpen={() => setOpenId(plan.id)} />
                <span className={`shrink-0 text-[12px] font-bold ${plan.branchShared ? "text-success" : "text-stone"}`}>
                  영업점 {plan.branchShared ? "참고 가능" : "참고 중단"}
                </span>
              </li>
            ))}
          </RowList>
        )}
      </div>

      {viewing ? <PlanSheet key={viewing.id} plan={viewing} tabs={[]} readOnly onClose={() => setOpenId(null)} /> : null}
    </>
  );
}
