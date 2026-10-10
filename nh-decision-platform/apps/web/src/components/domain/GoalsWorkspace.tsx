"use client";

import { useState } from "react";
import clsx from "clsx";
import { CascadeTree } from "@/components/domain/CascadeTree";
import {
  AttentionSheet,
  GoalSheet,
  NewGoalSheet,
  ProposalSheet,
  RequestSheet,
  SUB_LABEL,
  proposalRange,
} from "@/components/domain/GoalSheets";
import { useCascadeModel } from "@/components/domain/useCascadeModel";
import { PageHeader } from "@/components/layout/PageHeader";
import { useGoalState } from "@/components/providers/GoalStateProvider";
import { usePlanState } from "@/components/providers/PlanStateProvider";
import {
  Badge,
  IconCheck,
  IconChevron,
  IconPlus,
  PillTabs,
  RowList,
  SectionHead,
  StatusDot,
  TextLink,
} from "@/components/ui/primitives";
import { formatDate } from "@/lib/format";
import { resolveGoal } from "@/lib/goalView";
import type { Goal, Insight, Proposal, ReportRequest, ReviewQueueItem } from "@/lib/types";

type Tab = "goals" | "cascade";
type SheetState =
  | { kind: "attention"; id: string }
  | { kind: "request"; id: string }
  | { kind: "goal"; id: string }
  | { kind: "proposal"; id: string }
  | { kind: "newGoal" }
  | null;

const ACTION_DONE = {
  keep: "기존 유지",
  adopt: "제안 반영",
  manual_edit: "직접 수정",
  added: "목표 추가",
} as const;

/**
 * STEP 3 — 경영목표 설정 (요구사항 DASH-03/04/05, GOAL-03~17, PROP-01~04)
 *  검토 사유(AI Attention · 확인·보고 요청) → 좌 현재 목표 / 우 AI 제안 → 상세 시트에서 처리
 *  전파 경로는 같은 화면의 내부 탭으로 둔다.
 */
export function GoalsWorkspace({
  attentions,
  requests,
  goals,
  proposals,
  reviewQueue,
}: {
  attentions: Insight[];
  requests: ReportRequest[];
  goals: Goal[];
  proposals: Proposal[];
  reviewQueue: ReviewQueueItem[];
}) {
  const { overrides, proposalActions, addedGoals, reviewItems } = useGoalState();
  const { inProgressPlans } = usePlanState();
  const cascade = useCascadeModel();
  const [tab, setTab] = useState<Tab>("goals");
  const [sheet, setSheet] = useState<SheetState>(null);
  const close = () => setSheet(null);

  const pendingProposals = proposals.filter((p) => !proposalActions[p.id]);
  const proposalOf = (goalId: string) => proposals.find((p) => p.targetGoalId === goalId);

  const activeAttention = sheet?.kind === "attention" ? attentions.find((a) => a.id === sheet.id) : undefined;
  const activeRequest = sheet?.kind === "request" ? requests.find((r) => r.id === sheet.id) : undefined;
  const activeGoal = sheet?.kind === "goal" ? goals.find((g) => g.id === sheet.id) : undefined;
  const activeProposal = sheet?.kind === "proposal" ? proposals.find((p) => p.id === sheet.id) : undefined;

  return (
    <>
      <PageHeader
        eyebrow="3단계"
        title="경영목표 설정"
        description="검토 사유를 확인하고 AI 의 수정·신규 제안을 처리합니다. 확정된 목표는 사업부서와 영업점의 판단 기준으로 전파됩니다."
      >
        <PillTabs
          label="경영목표 설정 화면"
          items={[
            { key: "goals" as const, label: "목표 검토", count: pendingProposals.length || undefined },
            { key: "cascade" as const, label: "전파 경로" },
          ]}
          value={tab}
          onChange={setTab}
        />
      </PageHeader>

      {tab === "goals" ? (
        <div className="shell flex flex-col gap-xxl">
          {/* ── 검토 사유 ───────────────────────────────── */}
          <section>
            <SectionHead
              title="검토 사유"
              hint={`AI 가 선제 탐지한 변화와 타 조직 요청입니다${reviewItems.length ? ` · 검토 대상 저장 ${reviewItems.length}건` : ""}`}
            />
            <div className="grid grid-cols-1 gap-xl xl:grid-cols-2">
              <div>
                <p className="mb-2 text-[12px] font-bold text-steel">AI Attention · {attentions.length}건</p>
                <RowList>
                  {[...attentions].sort((x, y) => (y.rankScore ?? 0) - (x.rankScore ?? 0)).map((a) => (
                    <li key={a.id}>
                      <button
                        type="button"
                        onClick={() => setSheet({ kind: "attention", id: a.id })}
                        className="row-button flex items-start gap-md px-base py-3"
                      >
                        <StatusDot severity={a.severity} className="mt-[7px]" />
                        <span className="min-w-0 flex-1">
                          <span className="block text-[13.5px] font-bold leading-snug text-ink-deep">{a.title}</span>
                          <span className="mt-0.5 block text-[11.5px] text-stone">
                            {a.subDomain ? SUB_LABEL[a.subDomain] : "여신"} · 우선순위 {a.rankScore?.toFixed(1)}
                          </span>
                        </span>
                        <RowTail saved={reviewItems.includes(a.title)} />
                      </button>
                    </li>
                  ))}
                </RowList>
              </div>

              <div>
                <p className="mb-2 text-[12px] font-bold text-steel">확인·보고 요청 · {requests.length}건</p>
                <RowList>
                  {requests.map((r) => (
                    <li key={r.id}>
                      <button
                        type="button"
                        onClick={() => setSheet({ kind: "request", id: r.id })}
                        className="row-button flex items-start gap-md px-base py-3"
                      >
                        <span
                          aria-hidden="true"
                          className={clsx(
                            "mt-[7px] h-2 w-2 shrink-0 rounded-circle",
                            r.status === "open" ? "bg-attention" : r.status === "reviewing" ? "bg-primary" : "bg-success",
                          )}
                        />
                        <span className="min-w-0 flex-1">
                          <span className="block text-[13.5px] font-bold leading-snug text-ink-deep">{r.title}</span>
                          <span className="mt-0.5 block text-[11.5px] text-stone">
                            {r.fromOrg} · {r.reqTypeLabel}
                            {r.dueDate ? ` · 기한 ${formatDate(r.dueDate)}` : ""}
                          </span>
                        </span>
                        <RowTail saved={reviewItems.includes(r.title)} />
                      </button>
                    </li>
                  ))}
                </RowList>
              </div>
            </div>
          </section>

          {/* ── 좌: 현재 목표 / 우: AI 제안 ─────────────────── */}
          <section className="grid grid-cols-1 gap-xl xl:grid-cols-2">
            <div>
              <SectionHead
                title="현재 경영목표"
                hint={`${goals.length + addedGoals.length}건 · 확정`}
                right={
                  <button
                    type="button"
                    onClick={() => setSheet({ kind: "newGoal" })}
                    className="inline-flex items-center gap-1 text-[12px] font-bold text-primary"
                  >
                    <IconPlus /> 직접 추가
                  </button>
                }
              />
              <RowList>
                {goals.map((goal) => {
                  const view = resolveGoal(goal, overrides[goal.id]);
                  const proposal = proposalOf(goal.id);
                  const hasPending = proposal && !proposalActions[proposal.id];
                  return (
                    <li key={goal.id}>
                      <button
                        type="button"
                        onClick={() => setSheet({ kind: "goal", id: goal.id })}
                        className="row-button flex items-center gap-md px-base py-3"
                      >
                        <span className="min-w-0 flex-1">
                          <span className="block text-[13.5px] font-bold leading-snug text-ink-deep">{view.title}</span>
                          <span className="mt-0.5 block text-[11.5px] text-stone">
                            {goal.periodLabel} · {goal.metricLabel}
                          </span>
                        </span>
                        <span className="flex shrink-0 items-center gap-1.5">
                          {view.changed ? <Badge tone="primary">수정됨</Badge> : null}
                          {hasPending ? <Badge tone="info">AI 제안</Badge> : null}
                          {view.verdict && view.verdict.tone !== "success" ? (
                            <Badge tone={view.verdict.tone}>{view.verdict.label}</Badge>
                          ) : null}
                        </span>
                        <IconChevron className="shrink-0 text-stone" />
                      </button>
                    </li>
                  );
                })}
                {addedGoals.map((g) => (
                  <li key={g.id} className="flex items-center gap-md px-base py-3">
                    <span className="min-w-0 flex-1">
                      <span className="block text-[13.5px] font-bold leading-snug text-ink-deep">{g.title}</span>
                      <span className="mt-0.5 block text-[11.5px] text-stone">
                        {g.periodLabel ?? "2026 연간"} · 목표 {g.targetLabel}
                        {g.metricLabel ? ` · ${g.metricLabel}` : ""}
                      </span>
                    </span>
                    <Badge tone="primary">{g.creationMode === "ai_proposed" ? "AI 제안 기반 신규" : "직접 추가"}</Badge>
                  </li>
                ))}
              </RowList>

              {reviewQueue.length + reviewItems.length > 0 ? (
                <details className="mt-md rounded-2xl border border-hairline-soft">
                  <summary className="flex cursor-pointer list-none items-center justify-between px-base py-3 text-[12.5px] font-bold text-charcoal">
                    검토 필요사항 {reviewQueue.length + reviewItems.length}건
                    <span className="text-[11.5px] font-normal text-stone">일배치 스캔 + 저장한 항목</span>
                  </summary>
                  <ul className="flex flex-col gap-1.5 border-t border-hairline-soft px-base py-3">
                    {reviewItems.map((t) => (
                      <li key={t} className="flex items-start gap-2 text-[12.5px] text-ink">
                        <Badge tone="primary">방금 저장</Badge>
                        <span className="leading-snug">{t}</span>
                      </li>
                    ))}
                    {reviewQueue.map((q) => (
                      <li key={q.id} className="flex items-start gap-2 text-[12.5px] text-charcoal">
                        <Badge tone="neutral">{q.sourceLabel}</Badge>
                        <span className="min-w-0 flex-1 leading-snug">{q.title}</span>
                        <span className="shrink-0 text-[11px] text-stone">{formatDate(q.registeredAt)}</span>
                      </li>
                    ))}
                  </ul>
                </details>
              ) : null}
            </div>

            <div>
              <SectionHead
                title="AI 제안"
                hint={`수정 ${proposals.filter((p) => p.kind === "goal_modify").length} · 신규 ${
                  proposals.filter((p) => p.kind === "goal_new").length
                } · 상위 제약 이내에서만 산출`}
                right={<TextLink href="/hq/capital">제약 기준</TextLink>}
              />
              <RowList>
                {proposals.map((p) => {
                  const done = proposalActions[p.id];
                  return (
                    <li key={p.id}>
                      <button
                        type="button"
                        onClick={() => setSheet({ kind: "proposal", id: p.id })}
                        className="row-button flex items-center gap-md px-base py-3.5"
                      >
                        <span className="min-w-0 flex-1">
                          <span className="block text-[11.5px] font-bold text-steel">
                            {p.kind === "goal_new" ? "신규 목표 제안" : "목표 수정 제안"}
                          </span>
                          <span className="mt-0.5 block text-[13.5px] font-bold leading-snug text-ink-deep">{p.title}</span>
                          <span className="mt-1 block text-[12px] text-charcoal">
                            추천 <b className="tnum text-primary">{proposalRange(p)}</b>
                          </span>
                        </span>
                        {done ? (
                          <Badge tone="success">
                            <IconCheck />
                            {ACTION_DONE[done]}
                          </Badge>
                        ) : (
                          <Badge tone="primary">검토 필요</Badge>
                        )}
                        <IconChevron className="shrink-0 text-stone" />
                      </button>
                    </li>
                  );
                })}
              </RowList>
              <p className="mt-md text-[11.5px] leading-relaxed text-stone">
                목표값은 Rule 이 산출한 범위로만 제시됩니다. 처리 결과와 사유·근거 ID 는 변경 이력에 남습니다.
              </p>
            </div>
          </section>
        </div>
      ) : (
        <div className="shell">
          <SectionHead
            title="확정 목표의 전파 경로"
            hint={`경영목표 → 사업부서 진행사업 ${inProgressPlans.length}건 → 영업점`}
            right={<TextLink href="/hq/initiatives">사업부서 진행 사업</TextLink>}
          />
          <CascadeTree nodes={cascade} />
        </div>
      )}

      {/* ── 상세 시트 ─────────────────────────────────── */}
      {activeAttention ? (
        <AttentionSheet
          insight={activeAttention}
          onClose={close}
          onOpenGoal={(id) => setSheet({ kind: "goal", id })}
        />
      ) : null}
      {activeRequest ? (
        <RequestSheet request={activeRequest} onClose={close} onOpenGoal={(id) => setSheet({ kind: "goal", id })} />
      ) : null}
      {activeGoal ? (
        <GoalSheet
          goal={activeGoal}
          proposal={proposalOf(activeGoal.id)}
          onClose={close}
          onOpenProposal={(id) => setSheet({ kind: "proposal", id })}
        />
      ) : null}
      {activeProposal ? (
        <ProposalSheet
          proposal={activeProposal}
          goal={activeProposal.targetGoalId ? goals.find((g) => g.id === activeProposal.targetGoalId) : undefined}
          onClose={close}
        />
      ) : null}
      {sheet?.kind === "newGoal" ? <NewGoalSheet onClose={close} /> : null}
    </>
  );
}

function RowTail({ saved }: { saved: boolean }) {
  return saved ? (
    <span className="mt-0.5 inline-flex shrink-0 items-center gap-1 text-[11.5px] font-bold text-success">
      <IconCheck /> 저장됨
    </span>
  ) : (
    <IconChevron className="mt-1 shrink-0 text-stone" />
  );
}
