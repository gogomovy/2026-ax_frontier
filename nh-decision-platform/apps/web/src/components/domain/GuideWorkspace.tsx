"use client";

import { useEffect, useState, type ReactNode } from "react";
import clsx from "clsx";
import { CascadeFlow } from "@/components/domain/CascadeFlow";
import { PlanSheet } from "@/components/domain/PlanSheet";
import { useCascadeModel } from "@/components/domain/useCascadeModel";
import { AsOfTools } from "@/components/layout/PageTools";
import { useNavModel } from "@/components/layout/nav-model";
import { usePlanState } from "@/components/providers/PlanStateProvider";
import { useSession } from "@/components/providers/SessionProvider";
import { useUi } from "@/components/providers/UiProvider";
import { IconHistory } from "@/components/ui/icons";
import { Badge, Button, IconChevron, IconPlus, PillTabs } from "@/components/ui/primitives";
import { api } from "@/lib/api-client";
import { ALIGNMENT_LABEL } from "@/lib/format";
import type { ActionPlan, AlignmentVerdict, AnalysisTab, CascadeNode, Goal, Proposal } from "@/lib/types";

type Tab = "plans" | "cascade";
const NO_GOALS: Goal[] = [];
/** 수정 제안은 종합기획부 내부 검토 — 사업부서 흐름도에는 '수정 제안' 표시를 두지 않는다 */
const NO_PROPOSALS: Proposal[] = [];
type SheetState = { kind: "view"; id: string } | { kind: "create" } | null;

/**
 * STEP 3 — 수행방안 (요구사항 CRM-06 ~ CRM-14, PROP-03)
 *  탭 1: 진행중인 사업(흰 카드) 위 · AI 제안안(옅은 보라 판) 아래 (시안 345:2) / 탭 2: 전파 경로 (시안 345:98).
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

  const open = (id: string) => setSheet({ kind: "view", id });
  const create = () => setSheet({ kind: "create" });
  return (
    <>
      {/* 제목 줄 — 종합기획부 현황 · 신용리스크관리부 현황과 같은 22px 제목 · 구분선 · 부제 (시안 345:2 · 345:98) */}
      <div className="shell pb-4 pt-5">
        <header className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3">
          <div className="flex min-w-0 flex-wrap items-center gap-y-2">
            <h1 className="text-[22px] font-bold leading-[1.25] text-ink-deep">수행방안</h1>
            <span aria-hidden="true" className="mx-4 h-[14px] w-px bg-hairline-soft" />
            <span className="text-[13px] font-medium text-steel">AI 제안안을 진행사업으로 등록하고 영업점 참고 여부를 정해요</span>
          </div>
          <AsOfTools>
            {/* 사업부서 수행방안 변경 이력 API 가 없다 — 회색 자리표시 (경영목표 이력은 종합기획부 전용 goal_state) */}
            <button
              type="button"
              aria-disabled="true"
              title="수행방안 변경 이력은 아직 제공되지 않아요"
              className="no-print inline-flex h-[31px] items-center gap-[5px] rounded-md px-1.5 text-[14px] font-medium text-icon"
            >
              <IconHistory /> 변경 이력
            </button>
          </AsOfTools>
        </header>
        <div className="mt-4">
          <PillTabs
            label="수행방안 화면"
            items={[
              { key: "plans" as const, label: "진행사업·제안안", count: proposedPlans.length || undefined },
              { key: "cascade" as const, label: "전파 경로" },
            ]}
            value={tab}
            onChange={setTab}
          />
        </div>
      </div>
      {tab === "plans" ? (
        <div className="shell flex flex-col gap-4 pb-6 pt-[9px]">
          {/* 진행중인 사업 — 흰 카드 */}
          <section aria-labelledby="guide-running" className="rounded-[10px] border border-hairline-soft bg-canvas px-[23px] pb-1.5 pt-[19px]">
            <header className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 pb-4">
              <div className="flex flex-wrap items-baseline gap-x-2">
                <h2 id="guide-running" className="text-[14px] font-bold leading-[1.4] text-ink-deep">
                  진행중인 사업
                </h2>
                <span className="tnum text-[12px] text-steel">
                  {inProgressPlans.length}건 · 영업점 참고 {sharedCount}건
                </span>
              </div>
            </header>
            {inProgressPlans.length === 0 ? (
              <div className="border-t border-track py-8 text-center">
                <p className="text-[13px] font-bold text-charcoal">등록된 진행사업이 없습니다</p>
                <p className="mt-1 text-[12px] text-steel">
                  아래 AI 제안안에서 [진행사업으로 등록]을 누르면 이곳으로 옮겨지고, AI 가 제시한 근거와 지표가 함께 유지됩니다.
                </p>
              </div>
            ) : (
              <ul className="divide-y divide-track border-t border-track">
                {inProgressPlans.map((plan) => (
                  <li key={plan.id} className="flex items-center gap-4 py-[13px]">
                    <button type="button" onClick={() => open(plan.id)} className="min-w-0 flex-1 rounded-md text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary">
                      <PlanHead plan={plan} />
                    </button>
                    <ShareToggle
                      checked={plan.branchShared}
                      title={plan.title}
                      onChange={() => {
                        toggleBranchShare(plan.id);
                        showToast(plan.branchShared ? "영업점 참고를 중단했습니다" : "영업점 AI가 참고할 수 있습니다");
                      }}
                    />
                    <button
                      type="button"
                      aria-label={`${plan.title} 상세 보기`}
                      onClick={() => open(plan.id)}
                      className="-mr-1.5 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-stone hover:bg-surface-soft hover:text-ink-deep focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                    >
                      <IconChevron />
                    </button>
                  </li>
                ))}
              </ul>
            )}
            {/* 목록 끝에 붙는 추가 영역 — 목록을 이어 쓰는 동작이라 헤더가 아니라 마지막 행 아래에 둔다 (경영목표 설정과 같은 모양) */}
            <div className="border-t border-hairline-soft pb-1.5 pt-3">
              <button
                type="button"
                onClick={create}
                className="flex h-10 w-full items-center justify-center gap-1 rounded-lg text-[13px] font-bold text-primary-deep transition-colors hover:bg-info-faint focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
              >
                <IconPlus /> 직접 추가
              </button>
            </div>
          </section>
          {/* AI 제안안 — 옅은 보라 판 안의 흰 목록. 제안안이 없으면 영역 자체를 두지 않는다 */}
          {proposedPlans.length > 0 ? (
          <section aria-labelledby="guide-proposals" className="rounded-[10px] bg-info-soft px-4 pb-3.5 pt-5">
            <header className="flex flex-wrap items-center gap-x-3 gap-y-1 pb-[15px] pl-2">
              <h2 id="guide-proposals" className="inline-flex items-center rounded-pill bg-canvas px-2 py-0.5 text-[12px] font-bold text-primary">
                ✦ AI 제안안 {proposedPlans.length}건
              </h2>
              <span className="text-[12px] text-steel">특이사항별 가이드 · 배치 검증을 거쳐 제시돼요</span>
            </header>
            {(
              <ul className="divide-y divide-track rounded-lg bg-canvas px-4">
                {proposedPlans.map((plan) => {
                  const blocked = plan.alignment.verdict === "conflict";
                  const src = sourceOf(plan, tabs);
                  return (
                    <li key={plan.id} className="flex items-center gap-4 py-3">
                      <div className="min-w-0 flex-1">
                        <PlanHead plan={plan} />
                        {src ? <p className="mt-[5px] text-[11px] leading-[1.4] text-charcoal">✦ {src}에서 나온 제안이에요</p> : null}
                      </div>
                      <div className="flex shrink-0 items-center gap-2.5 pr-2">
                        <button type="button" onClick={() => open(plan.id)} className={TEXT_LINK}>
                          상세 보기
                        </button>
                        <Button
                          variant="secondary"
                          size="sm"
                          className="h-[29px] px-[13px] text-[12px] font-bold"
                          disabled={blocked}
                          title={blocked ? "상위 기준과 배치되어 등록할 수 없습니다" : undefined}
                          onClick={() => {
                            registerPlan(plan.id);
                            showToast("진행사업으로 등록했습니다 — 종합기획부에서 조회됩니다");
                          }}
                        >
                          진행사업으로 등록
                        </Button>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
          ) : null}
        </div>
      ) : (
        <div className="shell flex flex-col gap-5 pb-6 pt-[9px]">
          {/* 종합기획부 [목표 관리 · 전파 경로]와 같은 흐름도 — 경영목표 → 실행 사업 → 영업점 (SCP-04) */}
          <section className="rounded-[10px] border border-hairline-soft bg-canvas px-4 pb-3 pt-[22px]" aria-label="경영목표 전파 경로">
            <header className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1 pb-3.5">
              <h2 className="text-[16px] font-bold leading-[1.3] text-ink-deep">경영목표 전파 경로</h2>
              <span className="text-[12px] text-steel">최근 확정된 목표부터 위에 · 우리 부서 사업은 보라 테두리로 표시돼요</span>
              <button
                type="button"
                onClick={() => setTab("plans")}
                className="ml-auto inline-flex items-center gap-0.5 rounded-md text-[12px] font-bold text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
              >
                진행사업·제안안 <IconChevron />
              </button>
            </header>
            <CascadeFlow nodes={cascade} goals={goals} proposals={NO_PROPOSALS} highlightOrg={ownOrg} ownBorder drawIn />
          </section>
        </div>
      )}
      {viewing ? <PlanSheet key={viewing.id} plan={viewing} tabs={tabs} onClose={() => setSheet(null)} /> : null}
      {sheet?.kind === "create" ? <PlanSheet tabs={tabs} mode="create" onClose={() => setSheet(null)} /> : null}
    </>
  );
}

const TEXT_LINK =
  "rounded-md text-[12px] font-medium text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary";

/** 배치 검증 결과 태그 — 정합은 회색, 확인 필요는 주의색, 배치는 위험색 (시안 345:2) */
const ALIGN_TAG: Record<AlignmentVerdict, { label: string; tone: TagTone }> = {
  aligned: { label: `배치 ${ALIGNMENT_LABEL.aligned}`, tone: "neutral" },
  unknown: { label: `배치 ${ALIGNMENT_LABEL.unknown}`, tone: "attention" },
  conflict: { label: "상위 기준과 배치", tone: "critical" },
};

type TagTone = "neutral" | "attention" | "critical" | "info";
const TAG_TONE: Record<TagTone, string> = {
  neutral: "bg-track text-charcoal",
  attention: "bg-attention-soft text-attention",
  critical: "bg-critical-soft text-critical",
  info: "bg-info-soft text-primary",
};

function PlanTag({ tone, children }: { tone: TagTone; children: ReactNode }) {
  return (
    <span className={clsx("inline-flex h-4 items-center whitespace-nowrap rounded-pill px-1.5 text-[10px] font-bold leading-none", TAG_TONE[tone])}>
      {children}
    </span>
  );
}

/** 사업 제목 + '월 점검 · 지표 4 · 근거 4 · 분석 연결' + 배치 태그 */
function PlanHead({ plan }: { plan: ActionPlan }) {
  const tag = ALIGN_TAG[plan.alignment.verdict];
  const meta = [
    `${plan.reviewCycle} 점검`,
    `지표 ${plan.monitoringMetrics.length}`,
    `근거 ${plan.evidence.length}`,
    plan.linkedAnalysisLabel ? "분석 연결" : null,
  ]
    .filter(Boolean)
    .join(" · ");
  return (
    <>
      <span className="flex flex-wrap items-center gap-1.5">
        {plan.origin === "user" ? <PlanTag tone="info">직접 등록</PlanTag> : null}
        <span className="text-[14px] font-bold leading-[1.4] text-ink-deep">{plan.title}</span>
      </span>
      <span className="mt-1 flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-[11px] leading-[1.4] text-steel">
        <span className="tnum">{meta}</span>
        <PlanTag tone={tag.tone}>{tag.label}</PlanTag>
      </span>
    </>
  );
}

/** 제안 출처 — 연결 분석 이름, 없으면 출처 특이사항의 분석 탭 이름 (앞의 ①② 번호는 뺀다) */
function sourceOf(plan: ActionPlan, tabs: AnalysisTab[]): string | null {
  const label = plan.linkedAnalysisLabel ?? tabs.find((t) => t.insightId && t.insightId === plan.sourceInsightId)?.label;
  return label?.replace(/^[\u2460-\u2473]\s*/, "").trim() || null;
}

/** 영업점 참고 토글 — 시안 32×18 · 손잡이 14 */
function ShareToggle({ checked, onChange, title }: { checked: boolean; onChange: () => void; title: string }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={`${title} 영업점 참고`}
      onClick={onChange}
      className="inline-flex shrink-0 items-center gap-2 rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
    >
      <span aria-hidden="true" className={clsx("relative h-[18px] w-8 rounded-pill transition-colors", checked ? "bg-primary" : "bg-icon")}>
        <span className={clsx("absolute top-0.5 h-3.5 w-3.5 rounded-circle bg-white transition-all", checked ? "left-4" : "left-0.5")} />
      </span>
      <span className={clsx("text-[12px] font-medium", checked ? "text-ink-deep" : "text-steel")}>{checked ? "영업점 참고 중" : "영업점 참고 중단"}</span>
    </button>
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
