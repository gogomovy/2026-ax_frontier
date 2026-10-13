"use client";

import { useState } from "react";
import { CascadeTree } from "@/components/domain/CascadeTree";
import { PlanSheet } from "@/components/domain/PlanSheet";
import { useCascadeModel } from "@/components/domain/useCascadeModel";
import { PageHeader } from "@/components/layout/PageHeader";
import { usePlanState } from "@/components/providers/PlanStateProvider";
import { useUi } from "@/components/providers/UiProvider";
import {
  Badge,
  Button,
  IconCheck,
  IconChevron,
  IconPlus,
  PillTabs,
  RowEmpty,
  RowList,
  SectionHead,
  Switch,
} from "@/components/ui/primitives";
import { ALIGNMENT_LABEL } from "@/lib/format";
import type { ActionPlan, AnalysisTab } from "@/lib/types";

type Tab = "plans" | "cascade";
type SheetState = { kind: "view"; id: string } | { kind: "create" } | null;

/**
 * STEP 3 — 수행방안 (요구사항 CRM-06 ~ CRM-14, PROP-03)
 *  좌: 진행중인 사업 / 우: AI 제안안 — 종합기획부 목표 화면과 좌우 맥락을 맞춘다.
 *  행에서 바로 처리할 수 있는 동작(등록, 영업점 참고)은 행에 두고, 나머지는 상세 시트에서 처리한다.
 */
export function GuideWorkspace({ tabs }: { tabs: AnalysisTab[] }) {
  const { plans, proposedPlans, inProgressPlans, registerPlan, toggleBranchShare } = usePlanState();
  const { showToast } = useUi();
  const cascade = useCascadeModel();
  const [tab, setTab] = useState<Tab>("plans");
  const [sheet, setSheet] = useState<SheetState>(null);

  const viewing = sheet?.kind === "view" ? plans.find((p) => p.id === sheet.id) : undefined;
  const sharedCount = inProgressPlans.filter((p) => p.branchShared).length;

  return (
    <>
      <PageHeader
        eyebrow="3단계"
        title="수행방안"
        description="AI 제안안을 검토해 진행사업으로 등록하고, 영업점 AI가 참고할지를 정합니다. 등록된 사업은 종합기획부에서 바로 조회됩니다."
        actions={
          <Button size="sm" onClick={() => setSheet({ kind: "create" })}>
            <IconPlus /> 직접 추가
          </Button>
        }
      >
        <PillTabs
          label="수행방안 화면"
          items={[
            { key: "plans" as const, label: "진행사업·제안안", count: proposedPlans.length || undefined },
            { key: "cascade" as const, label: "전파 경로" },
          ]}
          value={tab}
          onChange={setTab}
        />
      </PageHeader>

      {tab === "plans" ? (
        <div className="shell grid grid-cols-1 gap-xl xl:grid-cols-2">
          {/* 좌 — 진행중인 사업 */}
          <section>
            <SectionHead
              title="진행중인 사업"
              hint={`${inProgressPlans.length}건 · 영업점 참고 ${sharedCount}건`}
            />
            {inProgressPlans.length === 0 ? (
              <RowEmpty
                title="등록된 진행사업이 없습니다"
                description="오른쪽 제안안에서 등록을 누르면 이곳으로 옮겨지고, AI 가 제시한 근거와 지표가 함께 유지됩니다."
              />
            ) : (
              <RowList>
                {inProgressPlans.map((plan) => (
                  <li key={plan.id} className="flex items-center gap-md pr-base">
                    <PlanRowMain plan={plan} onOpen={() => setSheet({ kind: "view", id: plan.id })} />
                    <Switch
                      checked={plan.branchShared}
                      onChange={() => {
                        toggleBranchShare(plan.id);
                        showToast(plan.branchShared ? "영업점 참고를 중단했습니다" : "영업점 AI가 참고할 수 있습니다");
                      }}
                      label="영업점"
                      description={plan.branchShared ? "참고 가능" : "중단"}
                    />
                  </li>
                ))}
              </RowList>
            )}
          </section>

          {/* 우 — AI 제안안 */}
          <section>
            <SectionHead title="제안안" hint={`${proposedPlans.length}건 · 특이사항별 가이드 · 배치 검증 후 제시`} />
            {proposedPlans.length === 0 ? (
              <RowEmpty
                title="검토할 제안안이 없습니다"
                description="일배치가 새 특이사항을 찾으면 이곳에 추가됩니다. 필요한 사업은 직접 추가할 수 있습니다."
                action={
                  <Button variant="ghost" size="sm" onClick={() => setSheet({ kind: "create" })}>
                    <IconPlus /> 직접 추가
                  </Button>
                }
              />
            ) : (
              <RowList>
                {proposedPlans.map((plan) => {
                  const blocked = plan.alignment.verdict === "conflict";
                  return (
                    <li key={plan.id} className="flex items-center gap-md pr-base">
                      <PlanRowMain plan={plan} onOpen={() => setSheet({ kind: "view", id: plan.id })} />
                      <Button
                        variant="confirm"
                        size="sm"
                        disabled={blocked}
                        title={blocked ? "상위 기준과 배치되어 등록할 수 없습니다" : undefined}
                        onClick={() => {
                          registerPlan(plan.id);
                          showToast("진행사업으로 등록했습니다 — 종합기획부에서 조회됩니다");
                        }}
                      >
                        <IconCheck /> 등록
                      </Button>
                    </li>
                  );
                })}
              </RowList>
            )}
          </section>
        </div>
      ) : (
        <div className="shell">
          <SectionHead
            title="확정 목표의 전파 경로"
            hint="목표 수정, 진행사업 등록, 영업점 참고 상태가 바로 반영됩니다"
          />
          <CascadeTree nodes={cascade} />
        </div>
      )}

      {viewing ? <PlanSheet key={viewing.id} plan={viewing} tabs={tabs} onClose={() => setSheet(null)} /> : null}
      {sheet?.kind === "create" ? <PlanSheet tabs={tabs} mode="create" onClose={() => setSheet(null)} /> : null}
    </>
  );
}

/** 행 본문 — 누르면 상세 시트가 열린다 */
export function PlanRowMain({ plan, onOpen }: { plan: ActionPlan; onOpen: () => void }) {
  const alignmentTone =
    plan.alignment.verdict === "aligned" ? "success" : plan.alignment.verdict === "conflict" ? "critical" : "neutral";
  return (
    <button type="button" onClick={onOpen} className="row-button flex min-w-0 flex-1 items-center gap-md py-3 pl-base">
      <span className="min-w-0 flex-1">
        <span className="flex flex-wrap items-center gap-1.5">
          {plan.origin === "user" ? <Badge tone="info">직접 등록</Badge> : null}
          <span className="text-[13.5px] font-bold leading-snug text-ink-deep">{plan.title}</span>
        </span>
        <span className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11.5px] text-stone">
          <span>{plan.reviewCycle} 점검</span>
          <span>· 지표 {plan.monitoringMetrics.length}</span>
          <span>· 근거 {plan.evidence.length}</span>
          <span>
            · 배치 <b className={alignmentTone === "critical" ? "text-critical" : "text-steel"}>{ALIGNMENT_LABEL[plan.alignment.verdict]}</b>
          </span>
          {plan.linkedAnalysisLabel ? <span>· 분석 연결</span> : null}
        </span>
      </span>
      <IconChevron className="shrink-0 text-stone" />
    </button>
  );
}
