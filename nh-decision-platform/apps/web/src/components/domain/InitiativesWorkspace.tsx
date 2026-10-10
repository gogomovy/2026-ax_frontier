"use client";

import Link from "next/link";
import { useState } from "react";
import { PlanRowMain } from "@/components/domain/GuideWorkspace";
import { PlanSheet } from "@/components/domain/PlanSheet";
import { PageHeader } from "@/components/layout/PageHeader";
import { usePlanState } from "@/components/providers/PlanStateProvider";
import { IconChevron, PillTabs, RowEmpty, RowList, SectionHead } from "@/components/ui/primitives";

/** 사업부서 목록 — 1차 범위는 신용리스크관리부, 나머지는 편입 대기 */
const DEPARTMENTS = [
  { key: "신용리스크관리부", active: true },
  { key: "여신관리부", active: false },
  { key: "수신부", active: false },
] as const;

type Dept = (typeof DEPARTMENTS)[number]["key"];

/**
 * 사업부서별 진행 사업 현황 (요구사항 PROP-06)
 * 사업부서가 진행사업으로 등록한 수행방안만 모인다. 등록 해제 시 이 화면에서도 즉시 빠진다.
 */
export function InitiativesWorkspace() {
  const { inProgressPlans } = usePlanState();
  const [dept, setDept] = useState<Dept>("신용리스크관리부");
  const [openId, setOpenId] = useState<string | null>(null);

  const countOf = (org: string) => inProgressPlans.filter((p) => p.ownerOrg === org).length;
  const plans = inProgressPlans.filter((p) => p.ownerOrg === dept);
  const active = DEPARTMENTS.find((d) => d.key === dept)?.active;
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
          items={DEPARTMENTS.map((d) => ({ key: d.key, label: d.key, count: d.active ? countOf(d.key) : undefined }))}
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
              <Link href="/risk/guides" className="inline-flex items-center gap-1 text-[12.5px] font-bold text-primary">
                사업부서 수행방안 화면 <IconChevron />
              </Link>
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
