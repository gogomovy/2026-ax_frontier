"use client";

import { useState } from "react";
import { Sheet, SheetSection } from "@/components/ui/Sheet";
import { Badge, Button, IconCheck, IconChevron } from "@/components/ui/primitives";
import { IconSparkle } from "@/components/ui/icons";
import { useGoalState } from "@/components/providers/GoalStateProvider";
import { useUi } from "@/components/providers/UiProvider";
import { formatDate, formatFigure } from "@/lib/format";
import { GOAL_VERDICT, proposalRange, resolveGoal } from "@/lib/goalView";
import type { Goal, Proposal, ReportRequest } from "@/lib/types";

const STATUS = {
  open: { label: "회신 대기", tone: "attention" as const },
  reviewing: { label: "검토 중", tone: "info" as const },
  done: { label: "완료", tone: "neutral" as const },
};

const DRAFT_KEY = (id: string) => `nhdip.reply.${id}`;

function daysBetween(from: string, to: string): number | null {
  const a = Date.parse(from.slice(0, 10));
  const b = Date.parse(to.slice(0, 10));
  return Number.isNaN(a) || Number.isNaN(b) ? null : Math.round((b - a) / 86_400_000);
}

/** 요청 · 관련 목표 · AI 제안 값으로 만드는 회신 초안 — 문장은 정해진 틀이고 숫자는 화면의 확정 수치만 쓴다 */
function draftReply(r: ReportRequest, goal?: Goal, proposal?: Proposal, goalLabel?: string): string {
  const lines = [`${r.fromOrg}의 요청(“${r.title}”)을 확인했습니다.`];
  if (goal) {
    const verdict = goal.gapVerdict ? GOAL_VERDICT[goal.gapVerdict].label : "";
    lines.push(`관련 목표 “${goalLabel ?? goal.title}”은(는) 현재 ${goal.actual ? formatFigure(goal.actual) : "실적 확인 중"}이며${verdict ? ` ${verdict} 상태입니다` : "입니다"}.`);
  }
  if (proposal) lines.push(`AI 목표 제안은 ${proposalRange(proposal)}이며, 상위 제약 검토를 거쳐 조정안이 확정되면 다시 알려드리겠습니다.`);
  lines.push(`${r.dueDate ? `${formatDate(r.dueDate)}까지` : "기한 내"} 검토 결과를 회신드리겠습니다.`);
  return lines.join("\n");
}

/**
 * 받은 요청 서랍 (가이드 7161) — 읽을거리는 우측 전체 높이 서랍.
 * 요청 정보 → 요청 내용 → 관련 목표 → AI 회신 초안 → 회신 작성.
 * 회신을 전달하는 서버 기능은 아직 없어서 [임시 저장]은 이 브라우저에만 저장하고,
 * 서버에 남는 동작은 [검토 대상으로 저장](경영목표 검토 목록에 올림) 하나다.
 */
export function RequestDrawer({
  request,
  goal,
  proposal,
  onClose,
  onOpenProposal,
}: {
  request: ReportRequest;
  goal?: Goal;
  proposal?: Proposal;
  onClose: () => void;
  onOpenProposal: (proposalId: string) => void;
}) {
  const { registerReviewItem, reviewItems, overrides } = useGoalState();
  const { showToast } = useUi();
  const saved = reviewItems.includes(request.title);
  const status = STATUS[request.status];
  const [text, setText] = useState(() => {
    try {
      return window.localStorage.getItem(DRAFT_KEY(request.id)) ?? "";
    } catch {
      return "";
    }
  });
  const view = goal ? resolveGoal(goal, overrides[goal.id]) : null;
  const span = request.dueDate ? daysBetween(request.createdAt, request.dueDate) : null;

  return (
    <Sheet
      open
      onClose={onClose}
      eyebrow={
        <>
          <span className="text-[12px] font-normal text-steel">받은 요청</span>
          <Badge tone={status.tone}>{status.label}</Badge>
        </>
      }
      title={request.title}
      footer={
        <div className="flex w-full gap-2">
          <Button
            variant="ghost"
            className="flex-1"
            onClick={() => {
              try {
                window.localStorage.setItem(DRAFT_KEY(request.id), text);
                showToast("임시 저장했어요. 이 브라우저에서 다시 열면 이어서 쓸 수 있어요.");
              } catch {
                showToast("실패 — 이 브라우저에서는 임시 저장을 할 수 없어요");
              }
            }}
          >
            임시 저장
          </Button>
          <Button
            className="flex-1"
            disabled={saved}
            onClick={() => {
              registerReviewItem(request.title);
              showToast("경영목표 검토 대상으로 저장했어요");
            }}
          >
            {saved ? (
              <>
                <IconCheck /> 검토 대상 저장됨
              </>
            ) : (
              "검토 대상으로 저장"
            )}
          </Button>
        </div>
      }
    >
      <dl className="grid grid-cols-3 gap-px overflow-hidden rounded-lg bg-hairline-soft text-[12px]">
        {[
          ["요청 부서", request.fromOrg],
          ["요청일", formatDate(request.createdAt)],
          ["회신 기한", request.dueDate ? `${formatDate(request.dueDate)}${span !== null ? ` (요청 후 ${span}일)` : ""}` : "-"],
        ].map(([k, v]) => (
          <div key={k} className="bg-surface-soft px-4 py-3">
            <dt className="text-steel">{k}</dt>
            <dd className="tnum mt-0.5 text-[14px] font-bold text-ink-deep">{v}</dd>
          </div>
        ))}
      </dl>

      <SheetSection title="요청 내용">
        <p className="whitespace-pre-line text-[14px] leading-[1.7] text-ink-deep">{request.body}</p>
      </SheetSection>

      {goal && view ? (
        <SheetSection title="관련 목표">
          <div className="flex items-center gap-3 rounded-lg border border-hairline-soft px-4 py-3">
            <div className="min-w-0 flex-1">
              <p className="flex flex-wrap items-center gap-2 text-[14px] font-bold text-ink-deep">
                {view.title}
                {proposal ? <Badge tone="info">AI 제안</Badge> : null}
              </p>
              <p className="mt-0.5 text-[12px] text-steel">
                {goal.periodLabel} · {goal.metricLabel}
                {proposal ? ` · 추천 ${proposalRange(proposal)}` : ""}
              </p>
            </div>
            {proposal ? (
              <button
                type="button"
                onClick={() => onOpenProposal(proposal.id)}
                className="inline-flex shrink-0 items-center gap-0.5 text-[13px] font-bold text-primary hover:underline"
              >
                제안 검토
                <IconChevron />
              </button>
            ) : null}
          </div>
        </SheetSection>
      ) : null}

      <div className="mb-5 rounded-lg bg-info-soft p-4">
        <div className="flex items-center justify-between gap-3">
          <p className="flex items-center gap-1.5 text-[13px] font-bold text-primary">
            <IconSparkle />
            AI 회신 초안
          </p>
          <button
            type="button"
            onClick={() => setText(draftReply(request, goal, proposal, view?.title))}
            className="inline-flex items-center gap-0.5 text-[13px] font-bold text-primary hover:underline"
          >
            초안 사용
            <IconChevron />
          </button>
        </div>
        <p className="mt-2 whitespace-pre-line text-[13px] leading-[1.6] text-ink-deep">{draftReply(request, goal, proposal, view?.title)}</p>
      </div>

      <SheetSection title="회신">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={6}
          placeholder="회신 내용을 입력하거나 AI 초안을 사용하세요."
          className="input"
          aria-label="회신 내용"
        />
        <p className="mt-2 text-[12px] leading-normal text-steel">회신을 요청 부서로 전달하는 기능은 아직 연결되지 않았어요. 작성한 내용은 이 브라우저에만 임시 저장돼요.</p>
      </SheetSection>
    </Sheet>
  );
}
