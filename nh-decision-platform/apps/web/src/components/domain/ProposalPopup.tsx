"use client";

import { useState } from "react";
import clsx from "clsx";
import { FigureText } from "@/components/data/FigureText";
import { RichText } from "@/components/data/RichText";
import { AlignmentPanel, VerificationRow } from "@/components/domain/Verification";
import { useCascadeModel } from "@/components/domain/useCascadeModel";
import { EvidenceRow } from "@/components/evidence/EvidenceChips";
import { useGoalState } from "@/components/providers/GoalStateProvider";
import { useUi } from "@/components/providers/UiProvider";
import { IconCheckCircle, IconSparkle } from "@/components/ui/icons";
import { Sheet, SheetSection } from "@/components/ui/Sheet";
import { Badge, Button, IconCheck, IconChevron } from "@/components/ui/primitives";
import { api } from "@/lib/api-client";
import { API_MODE } from "@/lib/config";
import { UNIT_LABEL } from "@/lib/format";
import { directionSuffix, proposalRange, resolveGoal } from "@/lib/goalView";
import type { CascadeNode, Goal, Proposal } from "@/lib/types";

interface ConsistencyIssue {
  code: string;
  severity: "block" | "warn" | "info";
  message: string;
}
interface PendingCheck {
  mode: "adopt" | "manual_edit";
  value?: number;
  issues: ConsistencyIssue[];
  blocked: boolean;
}

const GOAL_STEP_HREF = "/hq/goals";

/** 확정되면 AI가 자동으로 보완하는 하위 노드 (실행방안 · 영업점 기준) */
function downstream(node: CascadeNode | undefined) {
  const plans = node?.children?.filter((c) => c.kind === "plan") ?? [];
  return plans.flatMap((p) => [{ node: p, level: "plan" as const }, ...(p.children ?? []).map((b) => ({ node: b, level: "branch" as const }))]);
}

/**
 * AI 목표 제안 검토 팝업 (가이드 G05 · 규칙 05 "결정은 팝업").
 * 결정은 하나뿐이다 — 이 제안을 조정안에 담을지, 기존 목표를 유지할지. 버튼 이름은 1단계 · 3단계에서 같다(규칙 04).
 * 담은 제안은 3단계 [조정안 확정]에서 한꺼번에 확정되고, 그 전까지 실행방안 · 영업점 기준은 바뀌지 않는다.
 */
export function ProposalPopup({ proposal, goal, onClose, inGoalStep = false }: { proposal: Proposal; goal?: Goal; onClose: () => void; inGoalStep?: boolean }) {
  const { overrides, proposalActions, staged, stageProposal, unstageProposal, keepGoal } = useGoalState();
  const { showToast } = useUi();
  const cascade = useCascadeModel();
  const [showLogic, setShowLogic] = useState(false);
  const [editing, setEditing] = useState(false);
  const [check, setCheck] = useState<PendingCheck | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  const isNew = proposal.kind === "goal_new";
  const rec = proposal.recommendation;
  const unit = UNIT_LABEL[rec.unit];
  const dec = rec.decimals ?? 1;
  const range = proposalRange(proposal);
  const [value, setValue] = useState(String(rec.high ?? rec.value ?? ""));
  const done = proposalActions[proposal.id];
  const stagedItem = staged[proposal.id];

  const view = goal ? resolveGoal(goal, overrides[goal.id]) : null;
  const suffix = directionSuffix(goal);
  const actualTone = goal?.gapVerdict === "breach" ? "text-critical" : goal?.gapVerdict === "below" || goal?.gapVerdict === "near_limit" ? "text-attention" : "text-ink-deep";
  const constraintOk = proposal.constraintChecks.length ? proposal.constraintChecks.every((c) => c.passed) : null;
  const steps = downstream(cascade.find((n) => n.id === proposal.targetGoalId));

  const toastStaged = () =>
    showToast(
      inGoalStep ? "조정안에 담았어요. 아래 [조정안 확정]에서 확정할 수 있어요." : "조정안에 담았어요. 3단계 경영목표 설정에서 확정할 수 있어요.",
      undefined,
      inGoalStep ? undefined : { label: "3단계로 이동", href: GOAL_STEP_HREF },
    );

  /** 담기 — API 모드에서는 먼저 정합성을 검증하고, 경고가 있으면 사유를 받아 함께 담는다 */
  const stage = async (mode: "adopt" | "manual_edit" | "added", v?: number) => {
    if (API_MODE && mode !== "added" && proposal.targetGoalId) {
      setBusy(true);
      try {
        const r = await api<{ passed: boolean; blocked: boolean; issues: ConsistencyIssue[] }>("/state/goals/check", {
          method: "POST",
          json: { proposalId: proposal.id, mode, value: v },
        });
        if (!r.passed) {
          setCheck({ mode, value: v, issues: r.issues, blocked: r.blocked });
          setReason("");
          return;
        }
      } catch (e) {
        showToast(`정합성 검증을 하지 못했습니다 — ${(e as Error).message}`);
        return;
      } finally {
        setBusy(false);
      }
    }
    stageProposal({ proposal, mode, value: v, targetLabel: mode === "added" ? (v !== undefined ? `${v.toFixed(dec)}${unit}` : range) : undefined });
    toastStaged();
    onClose();
  };

  const footer = check ? (
    <div className="flex w-full flex-col gap-3" data-consistency>
      <ul className="flex flex-col gap-1.5">
        {check.issues.map((i) => (
          <li key={i.code} className="flex items-start gap-2 text-[13px]">
            <Badge tone={i.severity === "block" ? "critical" : i.severity === "warn" ? "attention" : "neutral"}>{i.severity === "block" ? "확정 불가" : i.severity === "warn" ? "경고" : "참고"}</Badge>
            <span className="text-charcoal">{i.message}</span>
          </li>
        ))}
      </ul>
      {check.blocked ? null : (
        <label className="flex flex-col gap-1">
          <span className="text-[12px] font-bold text-ink-deep">경고를 확인하고 담는 사유 (5자 이상 · 변경 이력에 남아요)</span>
          <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={2} className="input" aria-label="경고 확인 사유" />
        </label>
      )}
      <div className="flex gap-2">
        {check.blocked ? null : (
          <Button
            className="flex-1"
            disabled={reason.trim().length < 5}
            onClick={() => {
              stageProposal({ proposal, mode: check.mode, value: check.value, reason: reason.trim(), force: true });
              toastStaged();
              onClose();
            }}
          >
            사유 입력 후 조정안에 담기
          </Button>
        )}
        <Button variant="ghost" className={check.blocked ? "flex-1" : ""} onClick={() => setCheck(null)}>
          {check.blocked ? "값 다시 입력" : "취소"}
        </Button>
      </div>
    </div>
  ) : done ? (
    <div className="flex w-full items-center gap-3">
      <Badge tone="neutral" icon={<IconCheck />}>
        처리 완료
      </Badge>
      <span className="text-[12px] text-steel">변경 사유 · 근거가 변경 이력에 남았어요.</span>
      <Button variant="ghost" className="ml-auto" onClick={onClose}>
        닫기
      </Button>
    </div>
  ) : stagedItem ? (
    <div className="flex w-full items-center gap-3">
      <Badge tone="info" icon={<IconCheck />}>
        조정안에 담김
      </Badge>
      <span className="text-[12px] text-steel">{stagedItem.mode === "manual_edit" && stagedItem.value !== undefined ? `직접 입력 ${stagedItem.value.toFixed(dec)}${unit}` : "AI 추천값"}</span>
      <Button
        variant="ghost"
        className="ml-auto"
        onClick={() => {
          unstageProposal(proposal.id);
          showToast("조정안에서 뺐어요");
        }}
      >
        담기 취소
      </Button>
    </div>
  ) : editing ? (
    <div className="flex w-full flex-col gap-3">
      <label className="flex items-center gap-2">
        <span className="text-[13px] font-bold text-ink-deep">목표값</span>
        <input
          type="number"
          step="0.1"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          className="input !w-[130px] font-bold tnum"
          aria-label="직접 입력 목표값"
        />
        <span className="text-[14px] text-steel">{unit}</span>
      </label>
      <div className="flex gap-2">
        <Button className="flex-1" disabled={!value || busy} onClick={() => void stage(isNew ? "added" : "manual_edit", Number(value))}>
          조정안에 담기
        </Button>
        <Button variant="ghost" onClick={() => setEditing(false)}>
          취소
        </Button>
      </div>
    </div>
  ) : (
    <div className="flex w-full gap-2">
      <Button
        variant="ghost"
        className="flex-1"
        onClick={() => {
          keepGoal(proposal);
          showToast("기존 목표를 유지합니다");
          onClose();
        }}
      >
        기존 유지
      </Button>
      <Button variant="ghost" className="flex-1" onClick={() => setEditing(true)}>
        값 직접 수정
      </Button>
      <Button className="flex-1" disabled={busy} onClick={() => void stage(isNew ? "added" : "adopt")}>
        조정안에 담기
      </Button>
    </div>
  );

  return (
    <Sheet
      open
      variant="popup"
      onClose={onClose}
      eyebrow={
        <>
          <span className="inline-flex items-center gap-1.5">
            <IconSparkle />
            {isNew ? "AI 신규 목표 제안" : "AI 목표 수정 제안"}
          </span>
          {constraintOk !== null ? <Badge tone={constraintOk ? "neutral" : "attention"}>{constraintOk ? "상위 제약 충족" : "상위 제약 확인 필요"}</Badge> : null}
        </>
      }
      title={proposal.title.replace("신규 경영목표 제안 — ", "")}
      meta={goal ? `대상 목표 · ${goal.title}` : "현재 경영목표가 다루지 않는 영역"}
      footer={footer}
    >
      {/* 현재 → AI 추천 / 현재 실적 */}
      <div className="rounded-lg bg-info-faint px-5 py-4">
        <div className="flex flex-wrap items-center gap-x-5 gap-y-3">
          <div>
            <p className="text-[12px] text-steel">현재 목표</p>
            <p className="tnum mt-0.5 text-[16px] font-bold text-ink-deep">
              {view ? view.targetLabel : rec.currentValue !== undefined ? `${rec.currentValue.toFixed(dec)}${unit}` : "미설정"}
              {suffix && view ? <span className="num-unit">{suffix}</span> : null}
            </p>
          </div>
          <span aria-hidden="true" className="text-[18px] text-icon">
            →
          </span>
          <div>
            <p className="text-[12px] text-steel">AI 추천 {rec.mode === "range" ? "범위" : "값"}</p>
            <p className="tnum mt-0.5 text-[22px] font-bold leading-[1.2] text-primary">
              {range}
              {suffix && rec.mode !== "direction_only" ? <span className="num-unit">{suffix}</span> : null}
            </p>
          </div>
          {goal?.actual ? (
            <div className="ml-auto text-right">
              <p className="text-[12px] text-steel">현재 실적</p>
              <p className={clsx("mt-0.5 text-[18px] font-bold", actualTone)}>
                <FigureText figure={goal.actual} plain className={actualTone} />
              </p>
            </div>
          ) : null}
        </div>
      </div>
      <p className="mt-3 text-[13px] leading-normal text-charcoal">{rec.text}</p>
      <button
        type="button"
        onClick={() => setShowLogic((v) => !v)}
        aria-expanded={showLogic}
        className="mt-2 inline-flex items-center gap-1 text-[12px] font-bold text-primary hover:underline"
      >
        <span className="font-normal text-steel">추천 범위 산출 근거</span>
        산출 방식 · 입력값 · 원천 보기
        <IconChevron className={clsx("transition-transform", showLogic && "rotate-90")} />
      </button>
      {showLogic ? (
        <div className="mt-2 overflow-hidden rounded-lg border border-hairline-soft">
          <table className="w-full border-collapse text-[12px]">
            <thead>
              <tr className="bg-surface-soft text-left text-steel">
                <th scope="col" className="px-3 py-2 font-bold">
                  입력
                </th>
                <th scope="col" className="px-3 py-2 font-bold">
                  값
                </th>
                <th scope="col" className="px-3 py-2 font-bold">
                  출처
                </th>
              </tr>
            </thead>
            <tbody>
              {proposal.ruleInputs.map((input) => (
                <tr key={input.label} className="border-t border-hairline-soft">
                  <td className="px-3 py-2 text-charcoal">{input.label}</td>
                  <td className="px-3 py-2 font-bold text-ink-deep tnum">{input.value}</td>
                  <td className="px-3 py-2 text-[11px] text-steel">{input.source}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="border-t border-hairline-soft bg-surface-soft px-3 py-2 text-[12px] text-charcoal">
            목표값은 위 입력과 규칙으로만 산출되며 AI 가 임의로 만들지 않아요. 최종 수치는 담당자가 확정해요.
          </p>
        </div>
      ) : null}

      <SheetSection title={isNew ? "왜 신설이 필요한가" : "왜 조정이 필요한가"}>
        <RichText text={proposal.judgement} figures={proposal.figures} className="text-[14px] leading-[1.7] text-ink-deep" />
      </SheetSection>

      {proposal.constraintChecks.length > 0 ? (
        <SheetSection title="상위 제약 검증">
          <ul className="divide-y divide-hairline-soft overflow-hidden rounded-lg border border-hairline-soft">
            {proposal.constraintChecks.map((c) => (
              <li key={c.label} className="flex items-center gap-3 px-4 py-3">
                <div className="min-w-0 flex-1">
                  <p className="text-[14px] font-bold text-ink-deep">{c.label}</p>
                  {c.basisDoc ? (
                    <p className="text-[12px] text-steel">
                      {c.basisDoc.title}
                      {c.basisDoc.page ? ` p.${c.basisDoc.page}` : ""}
                    </p>
                  ) : null}
                </div>
                <span className="text-[12px] text-steel">
                  여유 <FigureText figure={c.headroom} plain />
                </span>
                <Badge tone={c.passed ? "neutral" : "critical"}>{c.passed ? "충족" : "초과"}</Badge>
              </li>
            ))}
          </ul>
        </SheetSection>
      ) : null}

      <SheetSection title={<>확정 시 AI가 자동 보완 <span className="ml-1 text-[12px] font-normal text-steel">실행방안 · 영업점 기준</span></>}>
        {steps.length ? (
          <ul className="divide-y divide-hairline-soft overflow-hidden rounded-lg border border-hairline-soft">
            {steps.map(({ node, level }) => {
              const [head, ...rest] = node.label.split(" — ");
              return (
                <li key={node.id} className="flex items-center gap-3 px-4 py-3">
                  <div className="min-w-0 flex-1">
                    <p className="text-[14px] font-bold text-ink-deep">{level === "branch" && rest.length ? head : node.label}</p>
                    <p className="text-[12px] text-steel">{level === "branch" && rest.length ? rest.join(" — ") : [node.org, node.detail].filter(Boolean).join(" · ")}</p>
                  </div>
                  <span className="shrink-0 text-[13px] font-bold text-primary">{level === "plan" ? "목표 반영" : "기준 보완"}</span>
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="rounded-lg border border-dashed border-hairline px-4 py-3 text-[13px] leading-normal text-steel">
            {isNew ? "새로 만드는 목표라서 연결된 실행방안이 아직 없어요. 확정한 뒤 사업부서가 실행방안을 등록하면 영업점 기준까지 이어져요." : "이 목표에 연결된 실행방안이 아직 없어요."}
          </p>
        )}
      </SheetSection>

      <div className="border-b border-hairline-soft py-5">
        <EvidenceRow items={proposal.evidence} title={proposal.title} statement={proposal.recommendation.text} />
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <VerificationRow items={proposal.verifications} />
          <details className="group text-[12px]">
            <summary className="inline-flex cursor-pointer list-none items-center gap-1 font-bold text-primary">
              정책 · 경영방향 정합성
              <IconChevron className="transition-transform group-open:rotate-90" />
            </summary>
            <div className="mt-2 w-full min-w-[320px]">
              <AlignmentPanel verdict={proposal.alignment.verdict} matched={proposal.alignment.matched} conflicts={proposal.alignment.conflicts} />
            </div>
          </details>
        </div>
      </div>

      <p className="flex items-start gap-1.5 pb-1 pt-4 text-[12px] leading-normal text-steel">
        <IconCheckCircle size={14} className="mt-[1px] shrink-0 text-icon" />
        담은 조정안은 3단계에서 확정해요. 확정 전까지 실행방안 · 영업점 기준은 바뀌지 않아요.
      </p>
    </Sheet>
  );
}
