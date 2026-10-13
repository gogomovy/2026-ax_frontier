"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { FigureText } from "@/components/data/FigureText";
import { RichText } from "@/components/data/RichText";
import { EvidenceSummary } from "@/components/evidence/EvidenceChips";
import { AlignmentPanel, VerificationRow } from "@/components/domain/Verification";
import { useGoalState } from "@/components/providers/GoalStateProvider";
import { useUi } from "@/components/providers/UiProvider";
import { Sheet, SheetSection } from "@/components/ui/Sheet";
import { Badge, Button, IconCalc, IconCheck, IconChevron, SeverityBadge } from "@/components/ui/primitives";
import { api } from "@/lib/api-client";
import { API_MODE } from "@/lib/config";
import { UNIT_LABEL, formatDate, formatDateTime } from "@/lib/format";
import { resolveGoal } from "@/lib/goalView";
import type { Goal, Insight, Proposal, ReportRequest } from "@/lib/types";

export const SUB_LABEL: Record<string, string> = {
  corporate: "기업여신",
  household: "가계여신",
  revenue: "여신 종합수익",
  portfolio: "포트폴리오",
  model_risk: "모형 리스크",
  inclusive_finance: "포용금융",
};

/** 정합성 검증 항목 (`POST /state/goals/check`, 6.4.7) */
interface ConsistencyIssue {
  code: string;
  severity: "block" | "warn" | "info";
  message: string;
}
/** 서버 변경 이력 (`GET /state/goals/{id}/history`, 6.4.8) */
interface GoalHistoryEntry {
  at: string;
  action: string;
  actor: string | null;
  actorName: string | null;
  value: number | null;
  reason: string | null;
  forced: boolean;
}
/** 목표 변경 영향 (`GET /cascade/{id}/impact`, 6.6.3) */
interface GoalImpact {
  current: number | null;
  proposed: number | null;
  metrics: { code: string; label: string; workflow: string }[];
  artifacts: string[];
  plans: { id: string; title: string; status: string; ownerOrg?: string; needsReview: boolean }[];
  cascade: { nodes: number; plans: number; targets: number };
}

const HISTORY_ACTION: Record<string, string> = {
  "goal.apply": "목표 변경",
  "goal.keep": "기존 유지",
  "goal.add_new": "신규 추가",
  "goal.add_manual": "직접 등록",
  "goal.reset": "처리 초기화",
};

const DETAIL_HREF: Record<string, string> = {
  corporate: "/hq/analysis",
  household: "/hq/analysis",
  revenue: "/hq/analysis",
  portfolio: "/hq/analysis",
  inclusive_finance: "/risk/analysis",
};

const ACTION_LABEL = {
  keep: "기존 목표 유지",
  adopt: "AI 제안 반영",
  manual_edit: "직접 수정 반영",
  added: "경영목표로 추가",
} as const;

export function proposalRange(p: Proposal) {
  const unit = UNIT_LABEL[p.recommendation.unit];
  const dec = p.recommendation.decimals ?? 1;
  const n = (v?: number) => (v === undefined || v === null ? "-" : v.toFixed(dec));
  if (p.recommendation.mode === "range") return `${n(p.recommendation.low)}${unit} ~ ${n(p.recommendation.high)}${unit}`;
  if (p.recommendation.mode === "point") return `${n(p.recommendation.value)}${unit}`;
  return "방향성만 제시";
}

/* ═══════════════ AI 주목 사항 ═══════════════ */
export function AttentionSheet({
  insight,
  onClose,
  onOpenGoal,
}: {
  insight: Insight;
  onClose: () => void;
  onOpenGoal: (goalId: string) => void;
}) {
  const { registerReviewItem, reviewItems } = useGoalState();
  const { showToast } = useUi();
  const saved = reviewItems.includes(insight.title);
  const detailHref = insight.subDomain ? DETAIL_HREF[insight.subDomain] : undefined;

  return (
    <Sheet
      open
      onClose={onClose}
      eyebrow={
        <>
          <Badge tone="dark">AI 주목 사항</Badge>
          <SeverityBadge severity={insight.severity} />
          {insight.subDomain ? <span className="text-[12px] text-steel">{SUB_LABEL[insight.subDomain]}</span> : null}
        </>
      }
      title={insight.title}
      footer={
        <>
          <Button
            variant={saved ? "quiet" : "primary"}
            size="sm"
            disabled={saved}
            onClick={() => {
              registerReviewItem(insight.title);
              showToast("경영목표 검토 대상으로 저장했습니다");
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
          {insight.relatedGoalId ? (
            <Button variant="ghost" size="sm" onClick={() => onOpenGoal(insight.relatedGoalId!)}>
              관련 경영목표
            </Button>
          ) : null}
          {detailHref ? (
            <Link href={detailHref} className="ml-auto inline-flex items-center gap-1 text-[12.5px] font-bold text-primary">
              상세 데이터 <IconChevron />
            </Link>
          ) : null}
        </>
      }
    >
      <SheetSection title="AI 판단" aside={<VerificationRow items={insight.verifications} />}>
        <RichText text={insight.statement} figures={insight.figures} className="text-[14px] leading-[1.7] text-charcoal" />
      </SheetSection>

      <SheetSection title="근거">
        <EvidenceSummary items={insight.evidence} title={insight.title} />
      </SheetSection>

      {insight.rankBasis ? (
        <SheetSection title="우선순위 산출 근거" aside={<span className="text-[12px] font-bold text-ink tnum">{insight.rankScore?.toFixed(1)}점</span>}>
          <p className="text-[12.5px] leading-relaxed text-charcoal">{insight.rankBasis}</p>
          <p className="mt-1.5 text-[11px] text-stone">ATTENTION_SCORE v1 · 가중합 규칙</p>
        </SheetSection>
      ) : null}
    </Sheet>
  );
}

/* ═══════════════ 확인·보고 요청 ═══════════════ */
const REQ_STATUS = {
  open: { label: "확인 대기", tone: "attention" as const },
  reviewing: { label: "검토 중", tone: "info" as const },
  done: { label: "완료", tone: "success" as const },
};

export function RequestSheet({
  request,
  onClose,
  onOpenGoal,
}: {
  request: ReportRequest;
  onClose: () => void;
  onOpenGoal: (goalId: string) => void;
}) {
  const { registerReviewItem, reviewItems } = useGoalState();
  const { showToast } = useUi();
  const saved = reviewItems.includes(request.title);
  const status = REQ_STATUS[request.status];

  return (
    <Sheet
      open
      onClose={onClose}
      eyebrow={
        <>
          <Badge tone="neutral">{request.reqTypeLabel}</Badge>
          <Badge tone={status.tone}>{status.label}</Badge>
        </>
      }
      title={request.title}
      meta={`${request.fromOrg} → ${request.toOrg} · 등록 ${formatDate(request.createdAt)}${
        request.dueDate ? ` · 기한 ${formatDate(request.dueDate)}` : ""
      }`}
      footer={
        <>
          <Button
            variant={saved ? "quiet" : "primary"}
            size="sm"
            disabled={saved}
            onClick={() => {
              registerReviewItem(request.title);
              showToast("경영목표 검토 대상으로 저장했습니다");
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
          {request.relatedGoalId ? (
            <Button variant="ghost" size="sm" onClick={() => onOpenGoal(request.relatedGoalId!)}>
              관련 경영목표
            </Button>
          ) : null}
        </>
      }
    >
      <SheetSection title="요청 내용">
        <p className="text-[14px] leading-[1.7] text-charcoal">{request.body}</p>
      </SheetSection>
      <SheetSection title="처리 안내">
        <p className="text-[12.5px] leading-relaxed text-steel">
          AI 주목 사항과 달리 타 조직이 직접 올린 요청입니다. 검토 대상으로 저장하면 경영목표 검토 목록에 함께 표시됩니다.
        </p>
      </SheetSection>
    </Sheet>
  );
}

/* ═══════════════ 경영목표 상세 ═══════════════ */
export function GoalSheet({
  goal,
  proposal,
  onClose,
  onOpenProposal,
}: {
  goal: Goal;
  proposal?: Proposal;
  onClose: () => void;
  onOpenProposal: (proposalId: string) => void;
}) {
  const { overrides, proposalActions } = useGoalState();
  const view = resolveGoal(goal, overrides[goal.id]);
  const pending = proposal && !proposalActions[proposal.id];
  const [serverHistory, setServerHistory] = useState<GoalHistoryEntry[] | null>(null);
  const [goalImpact, setGoalImpact] = useState<GoalImpact | null>(null);
  const override = overrides[goal.id];
  /* API 모드 — 감사 기록 기준 이력(처리자 · 사유 · 강제 확정). 목표 처리 상태가 바뀌면 다시 읽는다 */
  useEffect(() => {
    if (!API_MODE) return;
    api<GoalHistoryEntry[]>(`/state/goals/${encodeURIComponent(goal.id)}/history`)
      .then(setServerHistory)
      .catch(() => setServerHistory(null));
    api<GoalImpact>(`/cascade/${encodeURIComponent(goal.id)}/impact`)
      .then(setGoalImpact)
      .catch(() => setGoalImpact(null));
  }, [goal.id, override]);

  return (
    <Sheet
      open
      onClose={onClose}
      eyebrow={
        <>
          <Badge tone="success">현재 적용 중</Badge>
          {view.changed ? <Badge tone="primary">방금 수정</Badge> : null}
          {view.verdict ? <Badge tone={view.verdict.tone}>{view.verdict.label}</Badge> : null}
        </>
      }
      title={view.title}
      meta={`${goal.periodLabel} · ${goal.metricLabel} · v${view.version} · 최근 수정 ${formatDate(view.updatedAt)}`}
      footer={
        pending ? (
          <Button variant="confirm" size="sm" onClick={() => onOpenProposal(proposal.id)}>
            AI 수정 제안 검토 <IconChevron />
          </Button>
        ) : undefined
      }
    >
      {pending ? (
        <div className="mb-lg rounded-xl border border-info-line bg-info-faint px-base py-3">
          <p className="text-[13px] font-bold text-ink-deep">이 목표에 대한 AI 수정 제안이 있습니다</p>
          <p className="mt-0.5 text-[12px] text-charcoal">추천 {proposalRange(proposal)}</p>
        </div>
      ) : null}

      <SheetSection title="목표 대비 실적">
        <dl className="grid grid-cols-3 gap-px overflow-hidden rounded-xl border border-hairline-soft bg-hairline-soft">
          <Cell label="목표">
            <span className="text-[18px] font-bold text-ink-deep tnum">{view.targetLabel}</span>
            {view.changed ? (
              <span className="block text-[11px] text-stone line-through">{view.originalLabel}</span>
            ) : null}
          </Cell>
          <Cell label="실적">{goal.actual ? <FigureText figure={goal.actual} strong /> : "-"}</Cell>
          <Cell label={goal.gapLabel ?? "목표 대비"}>
            {goal.gap ? <FigureText figure={goal.gap} signed={goal.gapSigned ?? true} strong /> : "-"}
          </Cell>
        </dl>
        {view.changeReason ? (
          <p className="mt-2.5 rounded-lg bg-surface-soft px-3 py-2 text-[12px] text-charcoal">{view.changeReason}</p>
        ) : null}
      </SheetSection>

      {goalImpact && goalImpact.metrics.length ? (
        <SheetSection title="변경 영향">
          <div className="rounded-lg bg-surface-soft px-3 py-2.5 text-[12.5px] text-charcoal" data-goal-impact>
            <p>
              목표가 바뀌면 지표 <b className="tnum">{goalImpact.metrics.length}</b>개 · 화면 <b className="tnum">{goalImpact.artifacts.length}</b>개를 다시 계산하고, 전파 경로 하위 <b className="tnum">{goalImpact.cascade.nodes}</b>개 노드에 반영됩니다.
            </p>
            <p className="mt-1 text-[11.5px] text-steel">{goalImpact.metrics.slice(0, 6).map((m) => m.label).join(" · ")}{goalImpact.metrics.length > 6 ? " 외" : ""}</p>
            {goalImpact.plans.length ? (
              <ul className="mt-1.5 flex flex-col gap-0.5">
                {goalImpact.plans.map((p) => (
                  <li key={p.id} className="text-[12px]">
                    {p.needsReview ? <Badge tone="attention">재검토 필요</Badge> : <Badge tone="neutral">제안</Badge>} {p.title}
                    {p.ownerOrg ? <span className="text-stone"> · {p.ownerOrg}</span> : null}
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        </SheetSection>
      ) : null}

      <SheetSection title="변경 이력">
        <ol className="flex flex-col gap-3">
          {serverHistory
            ? serverHistory.map((h, i) => (
                <HistoryItem
                  key={`${h.at}-${i}`}
                  current={i === 0}
                  title={`${HISTORY_ACTION[h.action] ?? h.action}${h.value != null ? ` · ${h.value}${UNIT_LABEL[goal.unit]}` : ""}${h.forced ? " · 정합성 경고 확인 후 강제 확정" : ""}`}
                  meta={`${formatDateTime(h.at)} · ${h.actorName ?? h.actor ?? "-"}${h.reason ? ` · ${h.reason}` : ""}`}
                />
              ))
            : null}
          {!serverHistory && view.changed ? (
            <HistoryItem
              current
              title={`v${view.version} · ${view.originalLabel} → ${view.targetLabel}`}
              meta={`${formatDate(view.updatedAt)} · 이수정 과장 · ${view.changeReason ?? ""}`}
            />
          ) : null}
          {(goal.history ?? [])
            .slice()
            .reverse()
            .map((h) => (
              <HistoryItem
                key={h.version}
                title={`v${h.version} · ${h.from ? `${h.from} → ` : ""}${h.to}`}
                meta={`${formatDate(h.at)} · ${h.actor} · ${h.reason}`}
              />
            ))}
          {!goal.history?.length && !view.changed && !serverHistory?.length ? <p className="text-[12px] text-stone">변경 이력이 없습니다.</p> : null}
        </ol>
      </SheetSection>
    </Sheet>
  );
}

function Cell({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="bg-canvas px-base py-3">
      <dt className="text-[11.5px] text-steel">{label}</dt>
      <dd className="mt-1 text-[16px]">{children}</dd>
    </div>
  );
}

function HistoryItem({ title, meta, current }: { title: string; meta: string; current?: boolean }) {
  return (
    <li className="flex gap-2.5">
      <span
        aria-hidden="true"
        className={`mt-1.5 h-2 w-2 shrink-0 rounded-circle ${current ? "bg-primary" : "bg-hairline"}`}
      />
      <div>
        <p className="text-[13px] font-bold text-ink">{title}</p>
        <p className="mt-0.5 text-[11.5px] text-steel">{meta}</p>
      </div>
    </li>
  );
}

/* ═══════════════ AI 제안 ═══════════════ */
export function ProposalSheet({
  proposal,
  goal,
  onClose,
}: {
  proposal: Proposal;
  goal?: Goal;
  onClose: () => void;
}) {
  const { applyProposal, keepGoal, addNewGoal, proposalActions } = useGoalState();
  const { showToast } = useUi();
  const [showLogic, setShowLogic] = useState(false);
  const [editing, setEditing] = useState(false);
  /* 확정 전 정합성 검증(6.4.7) — 경고면 사유 입력 후 강제 확정, 차단이면 확정 불가 */
  const [check, setCheck] = useState<{ mode: "adopt" | "manual_edit"; value?: number; issues: ConsistencyIssue[]; blocked: boolean } | null>(null);
  const [reason, setReason] = useState("");
  const confirm = async (mode: "adopt" | "manual_edit", v?: number) => {
    if (API_MODE) {
      try {
        const r = await api<{ passed: boolean; blocked: boolean; issues: ConsistencyIssue[] }>("/state/goals/check", { method: "POST", json: { proposalId: proposal.id, mode, value: v } });
        if (!r.passed) {
          setCheck({ mode, value: v, issues: r.issues, blocked: r.blocked });
          setReason("");
          return;
        }
      } catch (e) {
        showToast(`정합성 검증을 하지 못했습니다 — ${(e as Error).message}`);
        return;
      }
    }
    applyProposal(proposal, mode, v);
    showToast(mode === "adopt" ? "AI 제안을 반영했습니다" : "입력한 목표값으로 수정했습니다");
    setEditing(false);
  };
  const [value, setValue] = useState(String(proposal.recommendation.high ?? proposal.recommendation.value ?? ""));
  const action = proposalActions[proposal.id];
  const isNew = proposal.kind === "goal_new";
  const unit = UNIT_LABEL[proposal.recommendation.unit];
  const dec = proposal.recommendation.decimals ?? 1;
  const range = proposalRange(proposal);

  const checkFooter = check ? (
    <div className="flex w-full flex-col gap-2" data-consistency>
      <ul className="flex flex-col gap-1">
        {check.issues.map((i) => (
          <li key={i.code} className="flex items-start gap-1.5 text-[12px]">
            <Badge tone={i.severity === "block" ? "critical" : i.severity === "warn" ? "attention" : "neutral"}>
              {i.severity === "block" ? "확정 불가" : i.severity === "warn" ? "경고" : "참고"}
            </Badge>
            <span className="text-charcoal">{i.message}</span>
          </li>
        ))}
      </ul>
      {check.blocked ? null : (
        <label className="flex flex-col gap-1">
          <span className="text-[11.5px] font-bold text-steel">강제 확정 사유 (5자 이상 · 이력에 남습니다)</span>
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={2}
            className="rounded-lg border border-hairline px-3 py-2 text-[13px] focus:border-primary focus:outline-none"
            aria-label="강제 확정 사유"
          />
        </label>
      )}
      <div className="flex gap-2">
        {check.blocked ? null : (
          <Button
            variant="confirm"
            size="sm"
            disabled={reason.trim().length < 5}
            onClick={() => {
              applyProposal(proposal, check.mode, check.value, reason.trim(), true);
              showToast("사유와 함께 확정했습니다");
              setCheck(null);
              setEditing(false);
            }}
          >
            사유 입력 후 확정
          </Button>
        )}
        <Button variant="ghost" size="sm" onClick={() => setCheck(null)}>
          {check.blocked ? "값 다시 입력" : "취소"}
        </Button>
      </div>
    </div>
  ) : null;

  const footer = checkFooter ?? (action ? (
    <>
      <Badge tone="success">
        <IconCheck />
        {ACTION_LABEL[action]} 완료
      </Badge>
      <span className="text-[12px] text-steel">변경 사유·채택 여부·근거 ID 가 함께 기록됩니다.</span>
      <Button variant="ghost" size="sm" className="ml-auto" onClick={onClose}>
        닫기
      </Button>
    </>
  ) : editing ? (
    <>
      <label className="flex items-center gap-2">
        <span className="text-[12px] font-bold text-steel">목표값</span>
        <input
          type="number"
          step="0.1"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          className="h-10 w-[120px] rounded-lg border border-hairline px-3 text-[14px] font-bold text-ink tnum focus:border-primary focus:outline-none"
          aria-label="직접 입력 목표값"
        />
        <span className="text-[13px] text-steel">{unit}</span>
      </label>
      <Button
        variant="confirm"
        size="sm"
        disabled={!value}
        onClick={() => {
          if (isNew) {
            addNewGoal(proposal, `${Number(value).toFixed(dec)}${unit}`);
            showToast("조정한 값으로 신규 경영목표를 추가했습니다");
            setEditing(false);
          } else {
            void confirm("manual_edit", Number(value));
          }
        }}
      >
        반영
      </Button>
      <Button variant="ghost" size="sm" onClick={() => setEditing(false)}>
        취소
      </Button>
    </>
  ) : isNew ? (
    <>
      <Button
        variant="confirm"
        size="sm"
        onClick={() => {
          addNewGoal(proposal, range);
          showToast("신규 경영목표로 추가했습니다");
        }}
      >
        경영목표로 추가
      </Button>
      <Button variant="ghost" size="sm" onClick={() => setEditing(true)}>
        값 조정 후 추가
      </Button>
    </>
  ) : (
    <>
      <Button
        variant="confirm"
        size="sm"
        onClick={() => void confirm("adopt")}
      >
        제안 반영
      </Button>
      <Button variant="ghost" size="sm" onClick={() => setEditing(true)}>
        직접 수정
      </Button>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => {
          keepGoal(proposal);
          showToast("기존 목표를 유지합니다");
        }}
      >
        기존 유지
      </Button>
    </>
  ));

  return (
    <Sheet
      open
      onClose={onClose}
      width="lg"
      eyebrow={
        <>
          <Badge tone={isNew ? "primary" : "attention"}>{isNew ? "신규 목표 제안" : "목표 수정 제안"}</Badge>
          <AlignmentPanel compact verdict={proposal.alignment.verdict} matched={[]} conflicts={[]} />
          <VerificationRow items={proposal.verifications} />
        </>
      }
      title={proposal.title}
      meta={goal ? `대상 목표 · ${goal.title}` : "기존 목표가 다루지 않는 영역"}
      footer={footer}
    >
      <SheetSection title={isNew ? "왜 신설이 필요한가" : "왜 수정이 필요한가"}>
        <RichText text={proposal.judgement} figures={proposal.figures} className="text-[14px] leading-[1.7] text-charcoal" />
      </SheetSection>

      <SheetSection title="추천 목표값 · 왜 이 수치인가">
        <div className="flex flex-wrap items-end gap-x-lg gap-y-2">
          <div>
            <p className="text-[11.5px] text-steel">현재</p>
            <p className="text-[17px] font-bold leading-tight text-stone tnum">
              {proposal.recommendation.currentValue !== undefined
                ? `${proposal.recommendation.currentValue.toFixed(dec)}${unit}`
                : "미설정"}
            </p>
          </div>
          <IconChevron className="mb-1 text-stone" />
          <div>
            <p className="text-[11.5px] text-steel">추천 {proposal.recommendation.mode === "range" ? "범위" : "값"}</p>
            <p className="text-[24px] font-bold leading-tight text-primary tnum">{range}</p>
          </div>
        </div>
        <p className="mt-2 text-[13px] leading-relaxed text-charcoal">{proposal.recommendation.text}</p>

        <button
          type="button"
          onClick={() => setShowLogic((v) => !v)}
          aria-expanded={showLogic}
          className="mt-3 inline-flex items-center gap-1.5 text-[12px] font-bold text-primary"
        >
          <IconCalc />
          {showLogic ? "산출 근거 접기" : "산출 근거 보기"} · {proposal.ruleId}
        </button>
        {showLogic ? (
          <div className="mt-2 overflow-hidden rounded-xl border border-hairline-soft">
            <table className="w-full border-collapse text-[12px]">
              <thead>
                <tr className="bg-surface-soft text-left">
                  <th scope="col" className="px-3 py-2 font-bold text-charcoal">입력</th>
                  <th scope="col" className="px-3 py-2 font-bold text-charcoal">값</th>
                  <th scope="col" className="px-3 py-2 font-bold text-charcoal">출처</th>
                </tr>
              </thead>
              <tbody>
                {proposal.ruleInputs.map((input) => (
                  <tr key={input.label} className="border-t border-hairline-soft">
                    <td className="px-3 py-2 text-charcoal">{input.label}</td>
                    <td className="px-3 py-2 font-bold text-ink tnum">{input.value}</td>
                    <td className="px-3 py-2 font-mono text-[10.5px] text-stone">{input.source}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="border-t border-hairline-soft bg-surface-soft px-3 py-2 text-[11.5px] text-charcoal">
              목표값은 위 입력과 Rule 로만 산출되며 LLM 이 임의로 만들지 않습니다. 최종 수치는 담당자가 확정합니다.
            </p>
          </div>
        ) : null}
      </SheetSection>

      {proposal.constraintChecks.length > 0 ? (
        <SheetSection title="상위 제약 검증">
          <ul className="flex flex-col divide-y divide-hairline-soft overflow-hidden rounded-xl border border-hairline-soft">
            {proposal.constraintChecks.map((c) => (
              <li key={c.label} className="flex flex-wrap items-center gap-x-md gap-y-1 px-base py-3">
                <div className="min-w-0 flex-1">
                  <p className="text-[12.5px] font-bold text-ink">{c.label}</p>
                  {c.basisDoc ? (
                    <p className="text-[11px] text-stone">
                      {c.basisDoc.title}
                      {c.basisDoc.page ? ` p.${c.basisDoc.page}` : ""}
                    </p>
                  ) : null}
                </div>
                <span className="text-[12px] text-steel">
                  한도 <FigureText figure={c.ceiling} />
                </span>
                <span className="text-[12px] text-steel">
                  여유 <FigureText figure={c.headroom} />
                </span>
                <Badge tone={c.passed ? "success" : "critical"}>{c.passed ? "충족" : "초과"}</Badge>
              </li>
            ))}
          </ul>
        </SheetSection>
      ) : null}

      <SheetSection title="근거">
        <EvidenceSummary items={proposal.evidence} title={proposal.title} />
      </SheetSection>

      <SheetSection title="배치 검증">
        <AlignmentPanel
          verdict={proposal.alignment.verdict}
          matched={proposal.alignment.matched}
          conflicts={proposal.alignment.conflicts}
        />
      </SheetSection>
    </Sheet>
  );
}

/* ═══════════════ 목표 직접 추가 ═══════════════ */
export function NewGoalSheet({ onClose }: { onClose: () => void }) {
  const { addManualGoal } = useGoalState();
  const { showToast } = useUi();
  const [title, setTitle] = useState("");
  const [target, setTarget] = useState("");
  const [period, setPeriod] = useState("2026 연간");
  const [metric, setMetric] = useState("");
  const [owner, setOwner] = useState("종합기획부");

  const submit = () => {
    addManualGoal({
      title: title.trim(),
      targetLabel: target.trim() || "관리방향 기준",
      periodLabel: period,
      metricLabel: metric.trim() || undefined,
      ownerOrg: owner,
    });
    showToast("신규 경영목표를 추가했습니다 — 전파 경로에 반영됩니다");
    onClose();
  };

  return (
    <Sheet
      open
      onClose={onClose}
      eyebrow={<Badge tone="neutral">직접 입력</Badge>}
      title="경영목표 직접 추가"
      meta="AI 제안 없이 담당자가 신규 목표를 등록합니다."
      footer={
        <>
          <Button variant="confirm" size="sm" disabled={!title.trim()} onClick={submit}>
            목표 추가
          </Button>
          <Button variant="ghost" size="sm" onClick={onClose}>
            취소
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-base">
        <FormField label="목표 내용" required>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="예) 중·저신용자 여신 공급액 3.2조원 이상"
            className="input"
          />
        </FormField>
        <FormField label="목표값 또는 관리방향">
          <input value={target} onChange={(e) => setTarget(e.target.value)} placeholder="예) 3.2조원 이상" className="input" />
        </FormField>
        <div className="grid grid-cols-1 gap-base sm:grid-cols-2">
          <FormField label="적용기간">
            <select value={period} onChange={(e) => setPeriod(e.target.value)} className="input">
              {["2026 연간", "2026.4Q", "2027 상반기", "2027 연간"].map((p) => (
                <option key={p}>{p}</option>
              ))}
            </select>
          </FormField>
          <FormField label="담당조직">
            <select value={owner} onChange={(e) => setOwner(e.target.value)} className="input">
              {["종합기획부", "여신관리부", "신용리스크관리부"].map((o) => (
                <option key={o}>{o}</option>
              ))}
            </select>
          </FormField>
        </div>
        <FormField label="측정지표">
          <input value={metric} onChange={(e) => setMetric(e.target.value)} placeholder="예) 중·저신용자 신규 취급액" className="input" />
        </FormField>
        <p className="text-[11.5px] leading-relaxed text-stone">
          추가된 목표는 상위 제약 검증을 거친 뒤 확정되며, 확정 시 사업부서·영업점 판단 기준으로 전파됩니다.
        </p>
      </div>
    </Sheet>
  );
}

export function FormField({
  label,
  required,
  children,
}: {
  label: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-[12px] font-bold text-charcoal">
        {label}
        {required ? <span className="ml-0.5 text-critical">*</span> : null}
      </span>
      {children}
    </label>
  );
}
