"use client";

import { useCallback, useId, useRef, useState } from "react";
import clsx from "clsx";
import { CascadeFlow } from "@/components/domain/CascadeFlow";
import { AttentionSheet, GoalSheet, NewGoalSheet } from "@/components/domain/GoalSheets";
import { HistorySheet } from "@/components/domain/HistorySheet";
import { ProposalPopup } from "@/components/domain/ProposalPopup";
import { RequestDrawer } from "@/components/domain/RequestDrawer";
import { SectorTitle, useSector } from "@/components/domain/SectorTitle";
import { useCascadeModel } from "@/components/domain/useCascadeModel";
import { PageHeader } from "@/components/layout/PageHeader";
import { AsOfTools, ToolButton } from "@/components/layout/PageTools";
import { useGoalState } from "@/components/providers/GoalStateProvider";
import { usePlanState } from "@/components/providers/PlanStateProvider";
import { useUi } from "@/components/providers/UiProvider";
import { IconCheckCircle, IconDots, IconHistory, IconSparkle } from "@/components/ui/icons";
import { EmptyCard } from "@/components/ui/StateViews";
import { Badge, Button, IconArrowRight, IconChevron, IconPlus, PillTabs, TextLink } from "@/components/ui/primitives";
import { formatDate, formatKstShort } from "@/lib/format";
import { GOAL_VERDICT, directionSuffix, proposalRange, resolveGoal } from "@/lib/goalView";
import { useDismiss } from "@/lib/useDismiss";
import type { DomainCardInfo, Goal, Insight, Proposal, ReportRequest, ReviewQueueItem } from "@/lib/types";

type Tab = "goals" | "cascade";
type SheetState =
  | { kind: "attention"; id: string }
  | { kind: "request"; id: string }
  | { kind: "goal"; id: string }
  | { kind: "history"; goalId: string | null }
  | { kind: "proposal"; id: string }
  | { kind: "newGoal" }
  | null;

const DONE_LABEL = { keep: "기존 유지", adopt: "제안 반영", manual_edit: "직접 수정", added: "목표 추가" } as const;
const REQ_STATUS = { open: null, reviewing: "검토 중", done: "완료" } as const;

/**
 * 3단계 — 경영목표 설정 (가이드 7159 · 7161 · 7162 · 7163 · 7164)
 *  목표 검토: 현재 경영목표 ↔ AI 수정 제안(한 줄에 하나) → 신규 목표 제안 → 받은 요청 → 하단 [조정안 확정]
 *  전파 경로: 경영목표 → 실행 사업 → 영업점 흐름도
 * AI 제안은 "목표 수정" 한 종류뿐이다. 제안은 팝업에서 검토해 조정안에 담고, 확정은 이 화면 하단에서 한꺼번에 한다.
 * 확정하면 실행방안 · 영업점 기준은 AI가 자동으로 보완해 전파한다.
 */
export function GoalsWorkspace({
  domains,
  attentions,
  requests,
  goals,
  proposals,
  reviewQueue,
}: {
  domains: DomainCardInfo[];
  attentions: Insight[];
  requests: ReportRequest[];
  goals: Goal[];
  proposals: Proposal[];
  reviewQueue: ReviewQueueItem[];
}) {
  const { overrides, proposalActions, addedGoals, reviewItems, staged, unstageProposal, confirmStaged, lastConfirmed } = useGoalState();
  const { inProgressPlans } = usePlanState();
  const { showToast, confirm } = useUi();
  const cascade = useCascadeModel();
  const { code, domain } = useSector(domains);
  const [tab, setTab] = useState<Tab>("goals");
  const [sheet, setSheet] = useState<SheetState>(null);
  const [busy, setBusy] = useState(false);
  const close = () => setSheet(null);

  const ready = domain?.status === "active";
  const domainGoals = goals.filter((g) => g.domainCode === code);
  const stagedCount = Object.keys(staged).length;
  const proposalOf = (goalId: string) => proposals.find((p) => p.targetGoalId === goalId);
  const modifyPending = proposals.filter((p) => p.kind === "goal_modify" && !proposalActions[p.id]);
  const newProposals = proposals.filter((p) => p.kind === "goal_new" && p.domainCode === code);
  const pendingTotal = proposals.filter((p) => !proposalActions[p.id]).length;
  const attentionOf = (goalId: string) => [...attentions].filter((a) => a.relatedGoalId === goalId).sort((a, b) => (b.rankScore ?? 0) - (a.rankScore ?? 0))[0];
  const looseAttentions = attentions.filter((a) => !a.relatedGoalId || !goals.some((g) => g.id === a.relatedGoalId));
  const sortedRequests = [...requests].sort((a, b) => (a.dueDate ?? "9").localeCompare(b.dueDate ?? "9"));

  const activeAttention = sheet?.kind === "attention" ? attentions.find((a) => a.id === sheet.id) : undefined;
  const activeRequest = sheet?.kind === "request" ? requests.find((r) => r.id === sheet.id) : undefined;
  const activeGoal = sheet?.kind === "goal" ? goals.find((g) => g.id === sheet.id) : undefined;
  const activeProposal = sheet?.kind === "proposal" ? proposals.find((p) => p.id === sheet.id) : undefined;

  const onConfirm = async () => {
    const ok = await confirm({
      title: `조정안 ${stagedCount}건을 확정할까요?`,
      body: "확정하면 AI가 실행방안과 영업점 기준을 자동으로 보완해 전파해요. 확정 직전에 서버가 상위 제약과 정합성을 한 번 더 검증해요.",
      confirmLabel: "조정안 확정",
    });
    if (ok !== true) return;
    setBusy(true);
    try {
      const r = await confirmStaged();
      if (r.confirmed > 0) {
        setTab("cascade");
        showToast(r.failed ? `조정안 ${r.confirmed}건을 확정했어요. ${r.failed}건은 확정하지 못해 조정안에 남겨 두었어요.` : `조정안 ${r.confirmed}건을 확정했어요. 전파 경로에서 반영 결과를 확인할 수 있어요.`);
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <PageHeader
        title={<SectorTitle domains={domains} title="경영목표 설정" />}
        actions={
          <AsOfTools>
            <ToolButton icon={<IconHistory />} onClick={() => setSheet({ kind: "history", goalId: null })}>
              변경 이력
            </ToolButton>
          </AsOfTools>
        }
      >
        <PillTabs
          label="경영목표 설정 화면"
          items={[
            { key: "goals" as const, label: "목표 검토", count: pendingTotal || undefined },
            { key: "cascade" as const, label: "전파 경로" },
          ]}
          value={tab}
          onChange={setTab}
        />
      </PageHeader>

      {!ready ? (
        <div className="shell">
          <EmptyCard
            title="이 부문에 적용된 경영목표가 없어요"
            description="1차 범위는 여신 부문이에요. 부문 데이터와 지표를 등록하면 같은 구조로 목표를 설정할 수 있어요."
            actionLabel="현황·목표로 돌아가기"
            href="/hq/overview"
          />
        </div>
      ) : tab === "goals" ? (
        <div className="shell flex flex-col gap-5 pb-6">
          {/* 현재 경영목표 ↔ AI 수정 제안 */}
          <section className="rounded-xl border border-hairline-soft bg-canvas px-7 py-6" aria-label="현재 경영목표">
            <header className="flex flex-wrap items-center justify-between gap-3 pb-4">
              <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <h2 className="text-[16px] font-bold leading-[1.4] text-ink-deep">현재 경영목표</h2>
                <span className="text-[12px] text-steel tnum">{domainGoals.length + addedGoals.length}건 · 확정</span>
                <button type="button" onClick={() => setSheet({ kind: "newGoal" })} className="inline-flex items-center gap-1 text-[13px] font-bold text-primary hover:underline">
                  <IconPlus /> 직접 추가
                </button>
              </div>
              <p className="inline-flex flex-wrap items-center gap-2 text-[12px] text-steel">
                <span className="inline-flex h-7 items-center gap-1.5 rounded-pill bg-info-soft px-3 font-bold text-primary">
                  <IconSparkle />
                  AI 수정 제안 {modifyPending.length}건
                </span>
                상위 제약 이내에서만 산출
              </p>
            </header>

            <ul className="divide-y divide-hairline-soft border-t border-hairline-soft">
              {domainGoals.map((goal) => {
                const view = resolveGoal(goal, overrides[goal.id]);
                const proposal = proposalOf(goal.id);
                const attention = attentionOf(goal.id);
                const verdict = goal.gapVerdict && goal.gapVerdict !== "on_track" ? GOAL_VERDICT[goal.gapVerdict] : null;
                return (
                  <li key={goal.id} className="grid grid-cols-1 gap-x-3 gap-y-3 py-5 lg:grid-cols-[minmax(0,1fr)_32px_20px_minmax(0,460px)] lg:items-center">
                    <div className="min-w-0">
                      <p className="flex flex-wrap items-center gap-x-2 gap-y-1">
                        <span className="text-[16px] font-bold leading-[1.4] text-ink-deep">{view.title}</span>
                        {verdict ? <Badge tone={verdict.tone}>{verdict.label}</Badge> : null}
                        {view.changed ? <Badge tone="info">방금 수정</Badge> : null}
                      </p>
                      <p className="mt-0.5 text-[12px] text-steel">
                        {goal.periodLabel} · {goal.metricLabel}
                      </p>
                      {attention ? (
                        <button
                          type="button"
                          onClick={() => setSheet({ kind: "attention", id: attention.id })}
                          className="mt-1.5 inline-flex max-w-full items-center gap-1.5 text-left text-[12px] text-steel hover:text-ink-deep"
                        >
                          <IconSparkle className="shrink-0 text-primary" />
                          <span className="truncate">
                            {attention.title}
                            {attention.rankScore != null ? ` · 우선순위 ${attention.rankScore.toFixed(1)}` : ""}
                          </span>
                        </button>
                      ) : null}
                    </div>
                    <GoalMenu onDetail={() => setSheet({ kind: "goal", id: goal.id })} onHistory={() => setSheet({ kind: "history", goalId: goal.id })} />
                    <span aria-hidden="true" className="hidden text-icon lg:block">
                      {proposal ? <IconArrowRight /> : null}
                    </span>
                    {proposal ? (
                      <ProposalCell
                        proposal={proposal}
                        goal={goal}
                        acted={proposalActions[proposal.id]}
                        inBasket={Boolean(staged[proposal.id])}
                        onReview={() => setSheet({ kind: "proposal", id: proposal.id })}
                        onUnstage={() => {
                          unstageProposal(proposal.id);
                          showToast("조정안에서 뺐어요");
                        }}
                      />
                    ) : (
                      <p className="text-[13px] text-steel lg:pl-2">변경 제안 없음</p>
                    )}
                  </li>
                );
              })}
              {addedGoals.map((g) => (
                <li key={g.id} className="flex flex-wrap items-center gap-3 py-5">
                  <div className="min-w-0 flex-1">
                    <p className="text-[16px] font-bold leading-[1.4] text-ink-deep">{g.title}</p>
                    <p className="mt-0.5 text-[12px] text-steel">
                      {g.periodLabel || "–"} · 목표 {g.targetLabel}
                      {g.metricLabel ? ` · ${g.metricLabel}` : ""}
                    </p>
                  </div>
                  <Badge tone="info">{g.creationMode === "ai_proposed" ? "AI 제안 기반 신규" : "직접 추가"}</Badge>
                </li>
              ))}
              {domainGoals.length + addedGoals.length === 0 ? (
                <li className="py-8">
                  <EmptyCard className="border-0" title="이 부문에 적용된 경영목표가 없어요" description="직접 추가하거나 AI 신규 목표 제안을 검토해 목표를 만들어요." />
                </li>
              ) : null}
            </ul>
          </section>

          {/* AI 신규 목표 제안 — AI 영역 */}
          {newProposals.length ? (
            <section className="rounded-xl bg-info-soft p-3" aria-label="AI 신규 목표 제안">
              <p className="flex flex-wrap items-center gap-3 px-2 pb-3 pt-1">
                <span className="inline-flex h-7 items-center gap-1.5 rounded-pill bg-canvas px-3 text-[12px] font-bold text-primary">
                  <IconSparkle />
                  AI 신규 목표 제안 {newProposals.length}건
                </span>
                <span className="text-[12px] text-steel">현재 경영목표에 없는 항목</span>
              </p>
              <ul className="flex flex-col gap-3">
                {newProposals.map((p) => {
                  const acted = proposalActions[p.id];
                  const inBasket = Boolean(staged[p.id]);
                  return (
                    <li key={p.id} className="flex flex-wrap items-center gap-x-6 gap-y-3 rounded-lg bg-canvas px-6 py-5">
                      <div className="min-w-0 flex-1">
                        <p className="text-[16px] font-bold leading-[1.4] text-ink-deep">{p.title.replace("신규 경영목표 제안 — ", "")}</p>
                        <p className="mt-1 flex items-center gap-1.5 text-[12px] text-steel">
                          <IconSparkle className="shrink-0 text-primary" />
                          <span className="line-clamp-1">{p.recommendation.text}</span>
                        </p>
                      </div>
                      <div className="flex flex-wrap items-center gap-3">
                        <span className="text-[12px] text-steel">
                          추천 <b className="tnum ml-1 text-[20px] font-bold text-primary">{proposalRange(p)}</b>
                        </span>
                        <StateTag acted={acted} inBasket={inBasket} />
                        {acted ? null : (
                          <Button variant="ghost" size="sm" onClick={() => setSheet({ kind: "proposal", id: p.id })}>
                            제안 검토
                          </Button>
                        )}
                        {inBasket && !acted ? (
                          <button type="button" onClick={() => unstageProposal(p.id)} className="text-[12px] text-steel underline underline-offset-2 hover:text-ink-deep">
                            담기 취소
                          </button>
                        ) : null}
                      </div>
                    </li>
                  );
                })}
              </ul>
            </section>
          ) : null}

          {/* 받은 요청 */}
          <section className="rounded-xl border border-hairline-soft bg-canvas px-7 py-6" aria-label="받은 요청">
            <header className="flex flex-wrap items-baseline gap-x-3 gap-y-1 pb-4">
              <h2 className="text-[16px] font-bold leading-[1.4] text-ink-deep">받은 요청</h2>
              <span className="text-[12px] text-steel">다른 부서 · 본부의 확인 · 보고 요청 {requests.length}건</span>
            </header>
            {requests.length === 0 ? (
              <p className="border-t border-hairline-soft py-8 text-center text-[14px] text-steel">받은 요청이 없어요.</p>
            ) : (
              <ul className="divide-y divide-hairline-soft border-t border-hairline-soft">
                {sortedRequests.map((r) => (
                  <li key={r.id}>
                    <button type="button" onClick={() => setSheet({ kind: "request", id: r.id })} className="row-button flex items-center gap-4 py-4 text-[14px]">
                      <span className="min-w-0 flex-1 font-medium text-ink-deep">{r.title}</span>
                      {REQ_STATUS[r.status] ? <Badge tone="neutral">{REQ_STATUS[r.status]}</Badge> : null}
                      <span className="hidden shrink-0 text-[12px] text-steel sm:inline">{r.fromOrg}</span>
                      <span className="shrink-0 text-[12px] text-steel tnum">{r.dueDate ? `기한 ${formatDate(r.dueDate)}` : ""}</span>
                      <IconChevron className="shrink-0 text-icon" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {/* 그 밖의 검토 사유 — 관련 목표가 없는 주목 사항 · 검토 필요사항 */}
          {looseAttentions.length + reviewQueue.length + reviewItems.length > 0 ? (
            <details className="group rounded-xl border border-hairline-soft bg-canvas">
              <summary className="flex cursor-pointer list-none items-center justify-between px-7 py-4 text-[14px] font-bold text-ink-deep">
                그 밖의 검토 사유 {looseAttentions.length + reviewQueue.length + reviewItems.length}건
                <span className="flex items-center gap-1 text-[12px] font-normal text-steel">
                  일배치 스캔 · 저장한 항목
                  <IconChevron className="transition-transform group-open:rotate-90" />
                </span>
              </summary>
              <ul className="flex flex-col gap-2 border-t border-hairline-soft px-7 py-4 text-[13px]">
                {looseAttentions.map((a) => (
                  <li key={a.id} className="flex items-start gap-2">
                    <Badge tone="info">AI 주목 사항</Badge>
                    <span className="min-w-0 flex-1">
                      <button type="button" onClick={() => setSheet({ kind: "attention", id: a.id })} className="text-left font-medium leading-snug text-ink-deep hover:underline">
                        {a.title}
                      </button>
                      {a.rankReason ? <span className="mt-0.5 block text-[12px] leading-snug text-steel">{a.rankReason}</span> : null}
                    </span>
                    {a.rankScore != null ? <span className="shrink-0 text-[12px] text-steel tnum">우선순위 {a.rankScore.toFixed(1)}</span> : null}
                  </li>
                ))}
                {reviewItems.map((t) => (
                  <li key={t} className="flex items-start gap-2">
                    <Badge tone="info">방금 저장</Badge>
                    <span className="leading-snug text-ink-deep">{t}</span>
                  </li>
                ))}
                {reviewQueue.map((q) => (
                  <li key={q.id} className="flex items-start gap-2 text-charcoal">
                    <Badge tone="neutral">{q.sourceLabel}</Badge>
                    <span className="min-w-0 flex-1 leading-snug">{q.title}</span>
                    <span className="shrink-0 text-[12px] text-steel tnum">{formatDate(q.registeredAt)}</span>
                  </li>
                ))}
              </ul>
            </details>
          ) : null}

          <ConfirmBar count={stagedCount} confirmed={lastConfirmed} busy={busy} onConfirm={onConfirm} onViewCascade={() => setTab("cascade")} />
        </div>
      ) : (
        <div className="shell flex flex-col gap-5 pb-6">
          <section className="rounded-xl border border-hairline-soft bg-canvas px-7 py-6" aria-label="경영목표 전파 경로">
            <header className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 pb-5">
              <div className="flex flex-wrap items-baseline gap-x-3">
                <h2 className="text-[16px] font-bold leading-[1.4] text-ink-deep">경영목표 전파 경로</h2>
                <span className="text-[12px] text-steel">최근 확정된 목표부터 위에 표시돼요 · 진행 사업 {inProgressPlans.length}건</span>
              </div>
              <TextLink href="/hq/initiatives">사업부서 진행 사업</TextLink>
            </header>
            <CascadeFlow nodes={cascade} goals={goals} proposals={proposals} />
          </section>
          <ConfirmBar count={stagedCount} confirmed={lastConfirmed} busy={busy} onConfirm={onConfirm} onViewCascade={() => setTab("cascade")} onHistory={() => setSheet({ kind: "history", goalId: null })} />
        </div>
      )}

      {/* ── 시트: 결정 = 팝업, 읽을거리 = 서랍 ── */}
      {activeProposal ? <ProposalPopup proposal={activeProposal} goal={activeProposal.targetGoalId ? goals.find((g) => g.id === activeProposal.targetGoalId) : undefined} onClose={close} inGoalStep /> : null}
      {activeRequest ? (
        <RequestDrawer
          request={activeRequest}
          goal={activeRequest.relatedGoalId ? goals.find((g) => g.id === activeRequest.relatedGoalId) : undefined}
          proposal={activeRequest.relatedGoalId ? proposalOf(activeRequest.relatedGoalId) : undefined}
          onClose={close}
          onOpenProposal={(id) => setSheet({ kind: "proposal", id })}
        />
      ) : null}
      {activeAttention ? <AttentionSheet insight={activeAttention} onClose={close} onOpenGoal={(id) => setSheet({ kind: "goal", id })} /> : null}
      {activeGoal ? <GoalSheet goal={activeGoal} proposal={proposalOf(activeGoal.id)} onClose={close} onOpenProposal={(id) => setSheet({ kind: "proposal", id })} /> : null}
      {sheet?.kind === "history" ? <HistorySheet goals={goals} focusGoalId={sheet.goalId} onClose={close} /> : null}
      {sheet?.kind === "newGoal" ? <NewGoalSheet onClose={close} /> : null}
    </>
  );
}

/** 오른쪽 칸 — AI 추천 범위 + 상태 + [제안 검토] */
function ProposalCell({
  proposal,
  goal,
  acted,
  inBasket,
  onReview,
  onUnstage,
}: {
  proposal: Proposal;
  goal: Goal;
  acted?: keyof typeof DONE_LABEL;
  inBasket: boolean;
  onReview: () => void;
  onUnstage: () => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-lg bg-info-faint px-5 py-3">
      <div className="min-w-0 flex-1">
        <p className="text-[12px] text-steel">
          추천{" "}
          <b className="tnum ml-1 text-[20px] font-bold text-primary">
            {proposalRange(proposal)}
            <span className="num-unit">{directionSuffix(goal)}</span>
          </b>
        </p>
        <p className="mt-1 flex flex-wrap items-center gap-2 text-[12px] text-steel">
          <StateTag acted={acted} inBasket={inBasket} />
          {inBasket && !acted ? (
            <>
              <span>1단계 · 3단계에서 담음</span>
              <button type="button" onClick={onUnstage} className="underline underline-offset-2 hover:text-ink-deep">
                담기 취소
              </button>
            </>
          ) : null}
        </p>
      </div>
      {acted ? null : (
        <Button variant="ghost" size="sm" onClick={onReview}>
          제안 검토
        </Button>
      )}
    </div>
  );
}

function StateTag({ acted, inBasket }: { acted?: keyof typeof DONE_LABEL; inBasket: boolean }) {
  if (acted) return <Badge tone="neutral">{DONE_LABEL[acted]} 완료</Badge>;
  if (inBasket) return <Badge tone="info" icon={<IconCheckCircle size={13} />}>조정안에 담김</Badge>;
  return <Badge tone="neutral">검토 필요</Badge>;
}

/** 목표 줄의 … 메뉴 — 목표 상세 · 변경 이력 */
function GoalMenu({ onDetail, onHistory }: { onDetail: () => void; onHistory: () => void }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const id = useId();
  const closeMenu = useCallback(() => setOpen(false), []);
  useDismiss(ref, open, closeMenu);
  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={id}
        aria-label="목표 메뉴"
        onClick={() => setOpen((v) => !v)}
        className={clsx("inline-flex h-8 w-8 items-center justify-center rounded-md text-steel hover:bg-surface-soft hover:text-ink-deep", open && "bg-surface-soft")}
      >
        <IconDots />
      </button>
      {open ? (
        <ul id={id} role="menu" className="absolute left-0 top-[calc(100%+4px)] z-30 w-[136px] animate-pop-in rounded-lg border border-hairline-soft bg-canvas p-1 shadow-tooltip">
          {[
            ["목표 상세", onDetail],
            ["변경 이력", onHistory],
          ].map(([label, fn]) => (
            <li key={label as string} role="none">
              <button
                type="button"
                role="menuitem"
                onClick={() => {
                  closeMenu();
                  (fn as () => void)();
                }}
                className="flex h-9 w-full items-center rounded-md px-3 text-left text-[13px] font-medium text-ink hover:bg-surface-soft"
              >
                {label as string}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

/** 하단 확정 바 — 담긴 조정안이 있으면 [조정안 확정], 방금 확정했으면 완료 안내 */
function ConfirmBar({
  count,
  confirmed,
  busy,
  onConfirm,
  onViewCascade,
  onHistory,
}: {
  count: number;
  confirmed: { count: number; at: string } | null;
  busy: boolean;
  onConfirm: () => void;
  onViewCascade: () => void;
  onHistory?: () => void;
}) {
  if (count > 0) {
    return (
      <section className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-hairline-soft bg-canvas px-7 py-5" aria-live="polite">
        <div>
          <h2 className="text-[16px] font-bold leading-[1.4] text-ink-deep">조정안 {count}건이 확정을 기다리고 있어요</h2>
          <p className="mt-0.5 text-[12px] text-steel">확정하면 AI가 실행방안과 영업점 기준을 자동으로 보완해 전파합니다.</p>
        </div>
        <Button onClick={onConfirm} disabled={busy}>
          {busy ? "확정하는 중…" : "조정안 확정"}
        </Button>
      </section>
    );
  }
  if (confirmed) {
    return (
      <section className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-hairline-soft bg-info-faint px-7 py-5" aria-live="polite">
        <div>
          <h2 className="flex items-center gap-2 text-[16px] font-bold leading-[1.4] text-ink-deep">
            <IconCheckCircle className="text-primary" />
            <span>
              조정안 {confirmed.count}건 확정 완료 · <span className="tnum">{formatKstShort(confirmed.at)}</span>
            </span>
          </h2>
          <p className="mt-0.5 text-[12px] text-steel">AI가 실행방안과 영업점 기준을 보완했고, 변경 알림을 보냈어요.</p>
        </div>
        {onHistory ? (
          <Button variant="ghost" onClick={onHistory}>
            변경 이력 보기
          </Button>
        ) : (
          <Button variant="ghost" onClick={onViewCascade}>
            전파 경로 보기
          </Button>
        )}
      </section>
    );
  }
  return (
    <section className="rounded-xl border border-dashed border-hairline bg-transparent px-7 py-5">
      <h2 className="text-[14px] font-bold text-ink-deep">확정할 조정안이 없어요</h2>
      <p className="mt-0.5 text-[12px] leading-normal text-steel">[제안 검토]에서 [조정안에 담기]를 누르면 여기서 한꺼번에 확정할 수 있어요.</p>
    </section>
  );
}
