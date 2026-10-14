"use client";

import { useEffect, useState } from "react";
import { CascadeFlow } from "@/components/domain/CascadeFlow";
import { PlanSheet } from "@/components/domain/PlanSheet";
import { useCascadeModel } from "@/components/domain/useCascadeModel";
import { PageHeader } from "@/components/layout/PageHeader";
import { useNavModel } from "@/components/layout/nav-model";
import { usePlanState } from "@/components/providers/PlanStateProvider";
import { useSession } from "@/components/providers/SessionProvider";
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
import { api } from "@/lib/api-client";
import { ALIGNMENT_LABEL } from "@/lib/format";
import type { ActionPlan, AnalysisTab, CascadeNode, Goal, Proposal } from "@/lib/types";

type Tab = "plans" | "cascade";
const NO_GOALS: Goal[] = [];
/** 수정 제안은 종합기획부 내부 검토 — 사업부서 흐름도에는 '수정 제안' 표시를 두지 않는다 */
const NO_PROPOSALS: Proposal[] = [];
type SheetState = { kind: "view"; id: string } | { kind: "create" } | null;

/**
 * STEP 3 — 수행방안 (요구사항 CRM-06 ~ CRM-14, PROP-03)
 *  좌: 진행중인 사업 / 우: AI 제안안 — 종합기획부 목표 화면과 좌우 맥락을 맞춘다.
 *  행에서 바로 처리할 수 있는 동작(등록, 영업점 참고)은 행에 두고, 나머지는 상세 시트에서 처리한다.
 */
export function GuideWorkspace({ tabs }: { tabs: AnalysisTab[] }) {
  const { plans, proposedPlans, inProgressPlans, registerPlan, toggleBranchShare } = usePlanState();
  const { showToast } = useUi();
  const session = useSession();
  const localTree = useCascadeModel();
  const goals = session.goals ?? NO_GOALS;
  // 지금 보는 사업부서(관리자가 부서를 골라 볼 때도 그 부서) — 그 부서가 맡은 실행 사업에 '우리 부서' 표시
  const { current } = useNavModel();
  const ownOrg = current?.kind === "dept" ? current.orgName : null;
  const [tab, setTab] = useState<Tab>("plans");

  // 전파 경로 — 목표 처리 상태(/state/goals)는 종합기획부 전용이라, 사업부서는 서버가 목표 수정 · 신설 · 진행사업을 반영해 계산한
  // 현재 트리(/cascade/tree · F.16)를 쓴다. 진행사업 등록 · 영업점 참고를 바꾸면 다시 받는다. 받지 못하면 화면 모델로 그린다.
  const remote = Boolean(session.menu);
  const planKey = inProgressPlans.map((p) => `${p.id}:${p.branchShared ? 1 : 0}:${p.relatedGoalId ?? ""}:${p.title}`).join("|");
  const [serverTree, setServerTree] = useState<CascadeNode[] | null>(null);
  useEffect(() => {
    if (tab !== "cascade" || !remote) return;
    let alive = true;
    api<CascadeNode[]>("/cascade/tree")
      .then((t) => {
        if (alive) setServerTree(t);
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [tab, planKey, remote]);
  const cascade = serverTree ?? localTree;
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
        <div className="shell flex flex-col gap-5 pb-6">
          {/* 종합기획부 [목표 관리 · 전파 경로]와 같은 흐름도 — 경영목표 → 실행 사업 → 영업점 (SCP-04) */}
          <section className="rounded-xl border border-hairline-soft bg-canvas px-7 py-6" aria-label="경영목표 전파 경로">
            <header className="flex flex-wrap items-baseline gap-x-3 gap-y-1 pb-5">
              <h2 className="text-[16px] font-bold leading-[1.4] text-ink-deep">경영목표 전파 경로</h2>
              <span className="text-[12px] text-steel">
                최근 확정된 목표부터 위에 표시돼요 · 진행 사업 {inProgressPlans.length}건 · 진행사업 등록 · 영업점 참고 상태가 바로 반영돼요
              </span>
            </header>
            <CascadeFlow nodes={cascade} goals={goals} proposals={NO_PROPOSALS} highlightOrg={ownOrg} />
          </section>
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
