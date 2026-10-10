"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "@/lib/api-client";
import { API_MODE } from "@/lib/config";
import type { Goal, GoalStatus, Proposal } from "@/lib/types";
import { useSession } from "./SessionProvider";
import { useUi } from "./UiProvider";

/**
 * 경영목표 처리 상태.
 *  - API 모드: `/state/goals/*` (서버 저장 · 감사 기록 · goal.confirmed 이벤트 → 관련 워크플로우 재실행)
 *  - 목데이터 모드: 클라이언트 메모리
 */
export type ProposalAction = "keep" | "adopt" | "manual_edit" | "added";

export interface GoalOverride {
  status?: GoalStatus;
  targetValue?: number;
  version?: number;
  updatedAt?: string;
  changeReason?: string;
  creationMode?: Goal["creationMode"];
}

export interface AddedGoal {
  id: string;
  title: string;
  targetLabel: string;
  creationMode: Goal["creationMode"];
  status: GoalStatus;
  sourceProposalId?: string;
  periodLabel?: string;
  metricLabel?: string;
  ownerOrg?: string;
  addedAt: string;
}

export interface ManualGoalInput {
  title: string;
  targetLabel: string;
  periodLabel: string;
  metricLabel?: string;
  ownerOrg?: string;
}

interface GoalStateShape {
  overrides: Record<string, GoalOverride>;
  proposalActions: Record<string, ProposalAction>;
  addedGoals: AddedGoal[];
  reviewItems: string[];
}

interface GoalStateValue extends GoalStateShape {
  applyProposal: (proposal: Proposal, mode: "adopt" | "manual_edit", value?: number, reason?: string, force?: boolean) => void;
  keepGoal: (proposal: Proposal) => void;
  addNewGoal: (proposal: Proposal, targetLabel: string) => void;
  addManualGoal: (input: ManualGoalInput) => void;
  registerReviewItem: (title: string) => void;
  reset: () => void;
}

const GoalStateContext = createContext<GoalStateValue | null>(null);
const EMPTY: GoalStateShape = { overrides: {}, proposalActions: {}, addedGoals: [], reviewItems: [] };

const today = () => new Date().toISOString().slice(0, 10);

export function GoalStateProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<GoalStateShape>(EMPTY);
  const session = useSession();
  const { showToast } = useUi();
  const remote = API_MODE && Boolean(session.menu);

  useEffect(() => {
    if (!remote) return;
    api<GoalStateShape>("/state/goals")
      .then(setState)
      .catch(() => undefined); // 권한 없는 사용자 — 빈 상태
  }, [remote]);

  /** 서버 호출 → 응답 상태로 교체. 실패하면 메시지 표시 */
  const call = useCallback(
    (path: string, json: unknown) => {
      api<GoalStateShape>(path, { method: "POST", json })
        .then(setState)
        .catch((e: Error) => showToast(`처리하지 못했습니다 — ${e.message}`));
    },
    [showToast],
  );

  const applyProposal = useCallback(
    (proposal: Proposal, mode: "adopt" | "manual_edit", value?: number, reason?: string, force?: boolean) => {
      if (!proposal.targetGoalId) return;
      if (remote) return call("/state/goals/apply", { proposalId: proposal.id, mode, value, reason, force: Boolean(force) });
      const rec = proposal.recommendation;
      const resolved =
        value ??
        rec.value ??
        (rec.high !== undefined && rec.low !== undefined ? Number(((rec.high + rec.low) / 2).toFixed(2)) : undefined);
      setState((prev) => ({
        ...prev,
        overrides: {
          ...prev.overrides,
          [proposal.targetGoalId as string]: {
            status: "active",
            targetValue: resolved,
            updatedAt: today(),
            changeReason: reason ?? (mode === "adopt" ? `AI 제안 반영 — ${rec.text}` : "담당자 직접 수정"),
            creationMode: mode === "adopt" ? "ai_proposed" : "user_manual",
          },
        },
        proposalActions: { ...prev.proposalActions, [proposal.id]: mode },
      }));
    },
    [remote, call],
  );

  const keepGoal = useCallback(
    (proposal: Proposal) => {
      if (remote) return call("/state/goals/keep", { proposalId: proposal.id });
      setState((prev) => ({
        ...prev,
        overrides: proposal.targetGoalId
          ? { ...prev.overrides, [proposal.targetGoalId]: { status: "active", updatedAt: today(), changeReason: "기존 목표 유지 결정" } }
          : prev.overrides,
        proposalActions: { ...prev.proposalActions, [proposal.id]: "keep" },
      }));
    },
    [remote, call],
  );

  const addNewGoal = useCallback(
    (proposal: Proposal, targetLabel: string) => {
      if (remote) return call("/state/goals/add-new", { proposalId: proposal.id, targetLabel });
      setState((prev) => ({
        ...prev,
        addedGoals: prev.addedGoals.some((g) => g.sourceProposalId === proposal.id)
          ? prev.addedGoals
          : [
              ...prev.addedGoals,
              {
                id: `goal-new-${proposal.id}`,
                title: proposal.title.replace("신규 경영목표 제안 — ", ""),
                targetLabel,
                creationMode: "ai_proposed",
                status: "active",
                sourceProposalId: proposal.id,
                periodLabel: "2026 연간",
                ownerOrg: "종합기획부",
                addedAt: today(),
              },
            ],
        proposalActions: { ...prev.proposalActions, [proposal.id]: "added" },
      }));
    },
    [remote, call],
  );

  const addManualGoal = useCallback(
    (input: ManualGoalInput) => {
      if (remote) return call("/state/goals/manual", input);
      setState((prev) => ({
        ...prev,
        addedGoals: [
          ...prev.addedGoals,
          {
            id: `goal-manual-${Date.now().toString(36)}`,
            title: input.title,
            targetLabel: input.targetLabel,
            creationMode: "user_manual",
            status: "active",
            periodLabel: input.periodLabel,
            metricLabel: input.metricLabel,
            ownerOrg: input.ownerOrg ?? "종합기획부",
            addedAt: today(),
          },
        ],
      }));
    },
    [remote, call],
  );

  const registerReviewItem = useCallback(
    (title: string) => {
      if (remote) return call("/state/goals/review-items", { title });
      setState((prev) => ({ ...prev, reviewItems: prev.reviewItems.includes(title) ? prev.reviewItems : [...prev.reviewItems, title] }));
    },
    [remote, call],
  );

  const reset = useCallback(() => {
    if (remote) return call("/state/goals/reset", {});
    setState(EMPTY);
  }, [remote, call]);

  const value = useMemo(
    () => ({ ...state, applyProposal, keepGoal, addNewGoal, addManualGoal, registerReviewItem, reset }),
    [state, applyProposal, keepGoal, addNewGoal, addManualGoal, registerReviewItem, reset],
  );

  return <GoalStateContext.Provider value={value}>{children}</GoalStateContext.Provider>;
}

export function useGoalState() {
  const ctx = useContext(GoalStateContext);
  if (!ctx) throw new Error("useGoalState must be used within GoalStateProvider");
  return ctx;
}
