"use client";

import { useCallback, useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import clsx from "clsx";
import { RichText } from "@/components/data/RichText";
import { CascadeFlow } from "@/components/domain/CascadeFlow";
import { GoalChangeDialog, type GoalChangeRequest } from "@/components/domain/GoalChangeDialog";
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
import { IconCheckCircle, IconChevronDown, IconDots, IconHistory } from "@/components/ui/icons";
import { EmptyCard } from "@/components/ui/StateViews";
import { Badge, Button, IconChevron, IconPlus, PillTabs, TextLink } from "@/components/ui/primitives";
import { UNIT_LABEL, formatDate, formatKstShort } from "@/lib/format";
import { isArchived } from "@/lib/goalChange";
import { GOAL_VERDICT, proposalRange, resolveGoal } from "@/lib/goalView";
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
  | { kind: "change"; req: GoalChangeRequest }
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
  // AI 신규 목표 제안 — 제안별 내용 펼침 상태
  const [openProposals, setOpenProposals] = useState<Record<string, boolean>>({});
  const [busy, setBusy] = useState(false);
  const close = () => setSheet(null);

  const ready = domain?.status === "active";
  // 삭제(보관)한 목표는 목록에서 빼고 변경 이력에서만 보인다
  const domainGoals = goals.filter((g) => g.domainCode === code && !isArchived(overrides[g.id]));
  const liveAdded = addedGoals.filter((g) => g.status !== "archived");
  const stagedCount = Object.keys(staged).length;
  const proposalOf = (goalId: string) => proposals.find((p) => p.targetGoalId === goalId);
  // 삭제한 목표를 겨냥한 제안은 검토 건수에서 뺀다
  const live = (p: Proposal) => !p.targetGoalId || !isArchived(overrides[p.targetGoalId]);
  const modifyPending = proposals.filter((p) => p.kind === "goal_modify" && !proposalActions[p.id] && live(p));
  // 이미 목표로 추가한 신규 제안은 아래 제안 목록에서 뺀다 — 추가한 목표를 삭제하면 다시 보인다
  const addedFrom = new Set(liveAdded.map((g) => g.sourceProposalId).filter(Boolean));
  const newProposals = proposals.filter((p) => p.kind === "goal_new" && p.domainCode === code && !addedFrom.has(p.id));
  const pendingTotal = proposals.filter((p) => !proposalActions[p.id] && live(p)).length;
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
        compact
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
        <div className="shell flex flex-col gap-6 pb-6">
          {/* 현재 경영목표 ↔ AI 수정 제안 */}
          <section className="rounded-[10px] border border-hairline-soft bg-canvas px-6 pb-4 pt-6" aria-label="현재 경영목표">
            <header className="grid grid-cols-1 items-center gap-3 pb-3 pt-[13px] lg:grid-cols-[minmax(0,1fr)_62px_minmax(0,500px)] lg:gap-0">
              <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <h2 className="text-[16px] font-bold leading-[1.4] text-ink-deep">현재 경영목표</h2>
                <span className="text-[12px] text-steel tnum">{domainGoals.length + liveAdded.length}건 · 확정</span>
              </div>
              <span aria-hidden="true" className="hidden lg:block" />
              <p className="inline-flex flex-wrap items-center gap-2 text-[12px] text-steel">
                <span className="inline-flex h-[23px] items-center rounded-pill bg-info-soft px-2 font-bold text-primary-deep">✦ AI 수정 제안 {modifyPending.length}건</span>
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
                  <li key={goal.id} className="grid grid-cols-1 gap-y-3 py-3 lg:grid-cols-[minmax(0,1fr)_26px_36px_minmax(0,500px)] lg:items-center">
                    <div className="min-w-0">
                      <p className="flex flex-wrap items-center gap-x-2 gap-y-1">
                        <span className="text-[14px] font-bold leading-[21px] text-ink-deep">{view.title}</span>
                        {verdict ? <Badge tone={verdict.tone}>{verdict.label}</Badge> : null}
                        {view.changed ? <Badge tone="info">방금 수정</Badge> : null}
                      </p>
                      <p className="mt-1 text-[12px] leading-[18px] text-steel">
                        {goal.periodLabel} · {goal.metricLabel}
                      </p>
                      {attention ? (
                        <button
                          type="button"
                          onClick={() => setSheet({ kind: "attention", id: attention.id })}
                          className="group mt-1 inline-flex max-w-full items-center gap-[5px] text-left text-[12px] font-medium leading-[18px] text-steel hover:text-ink-deep"
                        >
                          <span aria-hidden="true" className="shrink-0 font-bold text-primary">
                            ✦
                          </span>
                          {/* 눌러서 주목 사항 상세를 여는 줄 — 점선 밑줄 + › 로 '열 수 있음'을 늘 보이게 한다 */}
                          <span className="truncate underline decoration-hairline decoration-dotted underline-offset-[3px] group-hover:decoration-solid group-hover:decoration-current">
                            {attention.title}
                            {attention.rankScore != null ? ` · 우선순위 ${attention.rankScore.toFixed(1)}` : ""}
                          </span>
                          <IconChevron className="shrink-0 text-icon group-hover:text-ink-deep" />
                        </button>
                      ) : null}
                    </div>
                    <GoalMenu
                      items={[
                        { label: "목표 수정", onSelect: () => setSheet({ kind: "change", req: { mode: "edit", goalId: goal.id } }) },
                        { label: "변경 이력", onSelect: () => setSheet({ kind: "history", goalId: goal.id }) },
                        { label: "목표 삭제", danger: true, onSelect: () => setSheet({ kind: "change", req: { mode: "delete", goalId: goal.id } }) },
                      ]}
                    />
                    <span aria-hidden="true" className="hidden text-center text-[16px] font-bold text-icon lg:block">
                      {proposal ? "→" : ""}
                    </span>
                    {proposal ? (
                      <ProposalCell
                        proposal={proposal}
                        goal={goal}
                        acted={proposalActions[proposal.id]}
                        inBasket={Boolean(staged[proposal.id])}
                        onReview={() => setSheet({ kind: "proposal", id: proposal.id })}
                        onRevert={() => setSheet({ kind: "change", req: { mode: "revert", goalId: goal.id } })}
                        onUnstage={() => {
                          unstageProposal(proposal.id);
                          showToast("조정안에서 뺐어요");
                        }}
                      />
                    ) : (
                      <p className="text-[12px] text-steel lg:pl-4">변경 제안 없음</p>
                    )}
                  </li>
                );
              })}
              {/* 추가한 목표도 위 목표 줄과 같은 칸 구성 — 제목 옆 태그로 출처만 구분한다 */}
              {liveAdded.map((g) => (
                <li key={g.id} className="grid grid-cols-1 gap-y-3 py-3 lg:grid-cols-[minmax(0,1fr)_26px_36px_minmax(0,500px)] lg:items-center">
                  <div className="min-w-0">
                    <p className="flex flex-wrap items-center gap-x-2 gap-y-1">
                      <span className="text-[14px] font-bold leading-[21px] text-ink-deep">{g.title}</span>
                      <Badge tone="info">{g.creationMode === "ai_proposed" ? "AI 제안 기반 신규" : "직접 추가"}</Badge>
                    </p>
                    <p className="mt-1 text-[12px] leading-[18px] text-steel">
                      {g.periodLabel || "–"} · 목표 {g.targetLabel}
                      {g.metricLabel ? ` · ${g.metricLabel}` : ""}
                    </p>
                  </div>
                  <GoalMenu items={[{ label: "목표 삭제", danger: true, onSelect: () => setSheet({ kind: "change", req: { mode: "delete", goalId: g.id } }) }]} />
                  <span aria-hidden="true" className="hidden lg:block" />
                  <p className="text-[12px] text-steel lg:pl-4">변경 제안 없음</p>
                </li>
              ))}
              {domainGoals.length + liveAdded.length === 0 ? (
                <li className="py-8">
                  <EmptyCard className="border-0" title="이 부문에 적용된 경영목표가 없어요" description="직접 추가하거나 AI 신규 목표 제안을 검토해 목표를 만들어요." />
                </li>
              ) : null}
            </ul>

            {/* 목록 끝에 붙는 추가 영역 — 목록을 이어 쓰는 동작이라 헤더가 아니라 마지막 행 아래에 둔다 */}
            <div className="border-t border-hairline-soft pt-3">
              <button
                type="button"
                onClick={() => setSheet({ kind: "newGoal" })}
                className="flex h-10 w-full items-center justify-center gap-1 rounded-lg text-[13px] font-bold text-primary-deep transition-colors hover:bg-info-faint"
              >
                <IconPlus /> 경영목표 직접 추가
              </button>
            </div>
          </section>

          {/* AI 신규 목표 제안 — AI 영역 */}
          {newProposals.length ? (
            <section className="flex flex-col gap-3 rounded-[10px] bg-info-soft p-4" aria-label="AI 신규 목표 제안">
              <p className="flex flex-wrap items-center gap-2 pl-0.5">
                <span className="inline-flex h-[23px] items-center rounded-pill bg-canvas px-2 text-[12px] font-bold text-primary-deep">✦ AI 신규 목표 제안 {newProposals.length}건</span>
                <span className="text-[12px] text-steel">현재 경영목표에 없는 항목</span>
              </p>
              <ul className="flex flex-col gap-3">
                {newProposals.map((p) => {
                  const acted = proposalActions[p.id];
                  const inBasket = Boolean(staged[p.id]);
                  const open = Boolean(openProposals[p.id]);
                  const bodyId = `new-proposal-body-${p.id}`;
                  return (
                    <li key={p.id} className="flex flex-wrap items-start gap-4 rounded-lg bg-canvas py-4 pl-5 pr-4">
                      <div className="flex min-w-0 flex-1 flex-col gap-1">
                        <p className="text-[16px] font-bold leading-[24px] text-ink-deep">{p.title.replace("신규 경영목표 제안 — ", "")}</p>
                        {/* 접힘: 한 줄씩 자름 · 펼침: 추천 근거와 판단 문장 전문 (해설 전문 보기와 같은 제자리 펼침) */}
                        <div id={bodyId} className="flex flex-col gap-1">
                          <p className={clsx("text-[12px] leading-[18px] text-steel", !open && "line-clamp-1")}>{p.recommendation.text}</p>
                          {p.judgement ? (
                            <p className={clsx("flex gap-[5px] text-[12px] font-medium leading-[18px] text-steel", open ? "items-start" : "items-center")}>
                              <span aria-hidden="true" className="shrink-0 font-bold text-primary">
                                ✦
                              </span>
                              {/* 판단 문장에 [[fig:…]] 수치 표식이 들어 있어 RichText 로 채워 그린다 (그대로 찍으면 표식 원문이 보였다) */}
                              <RichText as="span" text={p.judgement} figures={p.figures} className={clsx(!open && "line-clamp-1")} />
                            </p>
                          ) : null}
                        </div>
                        <button
                          type="button"
                          aria-expanded={open}
                          aria-controls={bodyId}
                          onClick={() => setOpenProposals((prev) => ({ ...prev, [p.id]: !prev[p.id] }))}
                          className="mt-0.5 inline-flex w-fit items-center gap-0.5 text-[12px] font-bold text-primary-deep hover:underline"
                        >
                          {open ? "접기" : "제안 내용 펼쳐 보기"}
                          <IconChevronDown className={clsx("transition-transform", open && "rotate-180")} />
                        </button>
                      </div>
                      <div className="flex flex-wrap items-center gap-4 pt-0.5">
                        <RangeText proposal={p} />
                        {/* 신규 목표 제안은 [제안 검토] 단추가 이미 '검토할 일'을 말하므로 기본 '검토 필요' 태그는 두지 않는다 — 담김 · 완료 상태만 표시 */}
                        {acted || inBasket ? <StateTag acted={acted} inBasket={inBasket} /> : null}
                        {acted ? null : <ReviewButton onClick={() => setSheet({ kind: "proposal", id: p.id })} />}
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
          <section className="rounded-[10px] border border-hairline-soft bg-canvas px-6 pb-3 pt-[22px]" aria-label="받은 요청">
            <header className="flex flex-wrap items-baseline gap-x-2 gap-y-1 pb-2">
              <h2 className="text-[16px] font-bold leading-[1.4] text-ink-deep">받은 요청</h2>
              <span className="text-[12px] text-steel">다른 부서·본부의 확인·보고 요청 {requests.length}건</span>
            </header>
            {requests.length === 0 ? (
              <p className="border-t border-hairline-soft py-8 text-center text-[14px] text-steel">받은 요청이 없어요.</p>
            ) : (
              <ul className="divide-y divide-hairline-soft border-t border-hairline-soft">
                {sortedRequests.map((r) => (
                  <li key={r.id}>
                    <button type="button" onClick={() => setSheet({ kind: "request", id: r.id })} className="row-button flex items-center gap-3 py-2 text-[14px] leading-[25px]">
                      <span className="min-w-0 flex-1 font-medium text-ink-deep">{r.title}</span>
                      {REQ_STATUS[r.status] ? <Badge tone="neutral">{REQ_STATUS[r.status]}</Badge> : null}
                      <span className="hidden shrink-0 text-[12px] text-steel sm:inline">{r.fromOrg}</span>
                      <span className="shrink-0 text-[12px] text-steel tnum">{r.dueDate ? `기한 ${formatDate(r.dueDate)}` : ""}</span>
                      <span aria-hidden="true" className="shrink-0 text-[16px] font-medium text-icon">
                        ›
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {/* 그 밖의 검토 사유 — 관련 목표가 없는 주목 사항 · 검토 필요사항 */}
          {looseAttentions.length + reviewQueue.length + reviewItems.length > 0 ? (
            <details className="group rounded-[10px] border border-hairline-soft bg-canvas">
              <summary className="flex cursor-pointer list-none items-center justify-between px-6 py-4 text-[14px] font-bold text-ink-deep">
                그 밖의 검토 사유 {looseAttentions.length + reviewQueue.length + reviewItems.length}건
                <span className="flex items-center gap-1 text-[12px] font-normal text-steel">
                  일배치 스캔 · 저장한 항목
                  <IconChevron className="transition-transform group-open:rotate-90" />
                </span>
              </summary>
              <ul className="flex flex-col gap-2 border-t border-hairline-soft px-6 py-4 text-[13px]">
                {looseAttentions.map((a) => (
                  <li key={a.id} className="flex items-start gap-2">
                    <Badge tone="info">AI 주목 사항</Badge>
                    <span className="min-w-0 flex-1">
                      <button type="button" onClick={() => setSheet({ kind: "attention", id: a.id })} className="group inline-flex min-w-0 items-start gap-0.5 text-left font-medium leading-snug text-ink-deep">
                        <span className="underline decoration-hairline decoration-dotted underline-offset-[3px] group-hover:decoration-solid group-hover:decoration-current">{a.title}</span>
                        <IconChevron className="mt-[3px] shrink-0 text-icon group-hover:text-ink-deep" />
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
        <div className="shell flex flex-col gap-6 pb-6">
          <section className="rounded-[10px] border border-hairline-soft bg-canvas px-6 py-6" aria-label="경영목표 전파 경로">
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
      {sheet?.kind === "history" ? (
        <HistorySheet
          goals={goals}
          focusGoalId={sheet.goalId}
          onClose={close}
          onRestore={(goalId, toVersion, value) => setSheet({ kind: "change", req: { mode: "revert", goalId, toVersion, value } })}
        />
      ) : null}
      {sheet?.kind === "change" ? (
        <GoalChangeDialog request={sheet.req} goal={goals.find((g) => g.id === sheet.req.goalId)} added={addedGoals.find((g) => g.id === sheet.req.goalId)} onClose={close} />
      ) : null}
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
  onRevert,
  onUnstage,
}: {
  proposal: Proposal;
  goal: Goal;
  acted?: keyof typeof DONE_LABEL;
  inBasket: boolean;
  onReview: () => void;
  /** 처리 완료된 제안 — 확정한 변경을 되돌린다 (사유 필수 · 새 버전으로 기록) */
  onRevert: () => void;
  onUnstage: () => void;
}) {
  return (
    <div className="flex items-center gap-2 rounded-lg bg-info-faint py-3 pl-4 pr-3">
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <RangeText proposal={proposal} goal={goal} />
        <p className="flex flex-wrap items-center gap-[5px] text-[12px] text-steel">
          <StateTag acted={acted} inBasket={inBasket} />
          {acted && acted !== "added" ? (
            <button type="button" onClick={onRevert} className="text-[12px] font-bold text-steel underline underline-offset-2 hover:text-ink-deep">
              되돌리기
            </button>
          ) : null}
          {inBasket && !acted ? (
            <>
              <span>1단계 · 3단계에서 담음</span>
              <span aria-hidden="true" className="text-icon">
                ·
              </span>
              <button type="button" onClick={onUnstage} className="font-medium underline underline-offset-2 hover:text-ink-deep">
                담기 취소
              </button>
            </>
          ) : null}
        </p>
      </div>
      {acted ? null : <ReviewButton onClick={onReview} />}
    </div>
  );
}

/** 추천 범위 — '추천' 12 Medium · 숫자 20 Bold(primary/700) · 단위 12 Bold. 증가율 목표는 부호(+)를 붙인다 */
function RangeText({ proposal, goal }: { proposal: Proposal; goal?: Goal }) {
  const r = proposal.recommendation;
  const unit = UNIT_LABEL[r.unit];
  const dec = r.decimals ?? 1;
  const signed = r.unit === "PCT" && (goal?.targetType === "growth" || /증가|성장/.test(goal?.metricLabel ?? ""));
  const n = (v?: number | null, first?: boolean) => (v === undefined || v === null ? "-" : `${first && signed && v > 0 ? "+" : ""}${v.toFixed(dec)}`);
  const body = r.mode === "range" ? `${n(r.low, true)} ~ ${n(r.high)}` : r.mode === "point" ? n(r.value, true) : null;
  return (
    <p className="flex items-baseline gap-[5px] whitespace-nowrap">
      <span className="text-[12px] font-medium text-steel">추천</span>
      {body ? (
        <b className="tnum text-[20px] font-bold leading-[25px] text-primary-deep">
          {body}
          {unit ? <span className={clsx("text-[12px]", unit !== "%" && "ml-1")}>{unit}</span> : null}
        </b>
      ) : (
        <b className="text-[14px] font-bold text-primary-deep">{proposalRange(proposal)}</b>
      )}
    </p>
  );
}

/** [제안 검토] — 흰 바탕 · 테두리 · 36px · 12 Bold */
function ReviewButton({ onClick }: { onClick: () => void }) {
  return (
    <button type="button" onClick={onClick} className="inline-flex h-9 shrink-0 items-center rounded-md border border-hairline-soft bg-canvas px-3 text-[12px] font-bold text-ink-deep hover:bg-surface-soft">
      제안 검토
    </button>
  );
}

function StateTag({ acted, inBasket }: { acted?: keyof typeof DONE_LABEL; inBasket: boolean }) {
  const tag = "inline-flex h-[22px] items-center rounded-pill px-2 text-[12px] font-bold";
  if (acted) return <span className={clsx(tag, "bg-track text-steel")}>{DONE_LABEL[acted]} 완료</span>;
  if (inBasket) return <span className={clsx(tag, "bg-info-soft text-primary-deep")}>✓ 조정안에 담김</span>;
  return <span className={clsx(tag, "bg-track text-ink-deep")}>검토 필요</span>;
}

/** 목표 줄의 … 메뉴 — 목표 수정 · 변경 이력 · 목표 삭제(위험색). 키보드: Enter/Space/↓ 로 열고 ↑↓ 로 이동, Esc · 바깥 클릭으로 닫고 트리거로 포커스 복귀 */
interface GoalMenuItem {
  label: string;
  onSelect: () => void;
  danger?: boolean;
}
function GoalMenu({ items }: { items: GoalMenuItem[] }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const itemRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const id = useId();
  const closeMenu = useCallback(() => setOpen(false), []);
  const dismiss = useCallback(() => {
    setOpen(false);
    triggerRef.current?.focus();
  }, []);
  useDismiss(ref, open, dismiss);
  useEffect(() => {
    if (open) itemRefs.current[0]?.focus();
  }, [open]);
  const onMenuKey = (e: KeyboardEvent<HTMLUListElement>) => {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp" && e.key !== "Home" && e.key !== "End") return;
    e.preventDefault();
    const list = itemRefs.current.filter(Boolean) as HTMLButtonElement[];
    const at = list.indexOf(document.activeElement as HTMLButtonElement);
    const next = e.key === "Home" ? 0 : e.key === "End" ? list.length - 1 : (at + (e.key === "ArrowDown" ? 1 : -1) + list.length) % list.length;
    list[next]?.focus();
  };
  return (
    <div ref={ref} className="relative">
      <button
        ref={triggerRef}
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? id : undefined}
        aria-label="목표 메뉴"
        onClick={() => setOpen((v) => !v)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown" && !open) {
            e.preventDefault();
            setOpen(true);
          }
        }}
        className={clsx("inline-flex h-[26px] w-[26px] items-center justify-center rounded-md text-steel hover:bg-surface-soft hover:text-ink-deep", open && "bg-surface-soft")}
      >
        <IconDots />
      </button>
      {open ? (
        <ul id={id} role="menu" aria-label="목표 메뉴" onKeyDown={onMenuKey} className="absolute left-0 top-[calc(100%+4px)] z-30 w-[160px] animate-pop-in rounded-xl border border-hairline-soft bg-canvas p-1 shadow-tooltip">
          {items.map((it, i) => (
            <li key={it.label} role="none">
              <button
                ref={(el) => {
                  itemRefs.current[i] = el;
                }}
                type="button"
                role="menuitem"
                onClick={() => {
                  closeMenu();
                  // 다이얼로그 · 서랍이 닫히면 포커스가 이 트리거로 돌아오게 먼저 옮겨 둔다
                  triggerRef.current?.focus();
                  it.onSelect();
                }}
                className={clsx("flex h-11 w-full items-center rounded-lg px-3 text-left text-[14px] font-medium hover:bg-surface-soft focus-visible:bg-surface-soft", it.danger ? "text-critical" : "text-ink-deep")}
              >
                {it.label}
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
      <section className="flex flex-wrap items-center justify-between gap-3 rounded-[10px] border border-hairline-soft bg-canvas py-[18px] pl-6 pr-[18px]" aria-live="polite">
        <div>
          <h2 className="text-[16px] font-bold leading-[1.4] text-ink-deep">조정안 {count}건이 확정을 기다리고 있어요</h2>
          <p className="mt-0.5 text-[12px] leading-[18px] text-steel">확정하면 AI가 실행방안과 영업점 기준을 자동으로 보완해 전파합니다.</p>
        </div>
        <Button onClick={onConfirm} disabled={busy} className="!h-[45px]">
          {busy ? "확정하는 중…" : "조정안 확정"}
        </Button>
      </section>
    );
  }
  if (confirmed) {
    return (
      <section className="flex flex-wrap items-center justify-between gap-3 rounded-[10px] border border-hairline-soft bg-info-faint py-[18px] pl-6 pr-[18px]" aria-live="polite">
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
    <section className="rounded-[10px] border border-dashed border-hairline bg-transparent py-[18px] pl-6 pr-[18px]">
      <h2 className="text-[14px] font-bold text-ink-deep">확정할 조정안이 없어요</h2>
      <p className="mt-0.5 text-[12px] leading-normal text-steel">[제안 검토]에서 [조정안에 담기]를 누르면 여기서 한꺼번에 확정할 수 있어요.</p>
    </section>
  );
}
