"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { FigureText } from "@/components/data/FigureText";
import { RichText } from "@/components/data/RichText";
import { EvidenceSummary } from "@/components/evidence/EvidenceChips";
import { VerificationRow } from "@/components/domain/Verification";
import { useGoalState } from "@/components/providers/GoalStateProvider";
import { useUi } from "@/components/providers/UiProvider";
import { Sheet, SheetSection } from "@/components/ui/Sheet";
import { Badge, Button, IconCheck, IconChevron, SeverityBadge } from "@/components/ui/primitives";
import { api } from "@/lib/api-client";
import { API_MODE } from "@/lib/config";
import { UNIT_LABEL, formatDate, formatDateTime } from "@/lib/format";
import { proposalRange, resolveGoal } from "@/lib/goalView";
import type { Goal, Insight, Proposal } from "@/lib/types";

export const SUB_LABEL: Record<string, string> = {
  corporate: "기업여신",
  household: "가계여신",
  revenue: "여신 종합수익",
  portfolio: "포트폴리오",
  model_risk: "모형 리스크",
  inclusive_finance: "포용금융",
};

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
