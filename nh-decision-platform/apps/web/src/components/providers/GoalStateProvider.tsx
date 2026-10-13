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
 *
 * 조정안(담기): 1단계 · 3단계의 [제안 검토]에서 [조정안에 담기]를 누르면 값만 담아 두고(서버에 보내지 않음),
 * 3단계에서 [조정안 확정]을 누르면 담긴 제안을 한꺼번에 확정한다. 확정 시점에 서버가 정합성을 다시 검증한다.
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

/** 조정안에 담긴 제안 한 건 */
export interface StagedItem {
  proposal: Proposal;
  /** adopt = AI 추천값 · manual_edit = 직접 입력 · added = 신규 목표로 추가 */
  mode: "adopt" | "manual_edit" | "added";
  /** manual_edit 의 목표값 */
  value?: number;
  /** added 의 목표 표기 (예: 3.1조원 ~ 3.3조원) */
  targetLabel?: string;
  /** 정합성 경고를 알고 확정할 때의 사유 (5자 이상) */
  reason?: string;
  force?: boolean;
  at: string;
}

export interface ConfirmedBatch {
  count: number;
  at: string;
  titles: string[];
}

interface GoalStateValue extends GoalStateShape {
  staged: Record<string, StagedItem>;
  lastConfirmed: ConfirmedBatch | null;
  stageProposal: (item: Omit<StagedItem, "at">) => void;
  unstageProposal: (proposalId: string) => void;
  /** 담긴 제안을 모두 확정 — 실패한 제안은 담긴 채로 남는다 */
  confirmStaged: () => Promise<{ confirmed: number; failed: number }>;
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
  const [staged, setStaged] = useState<Record<string, StagedItem>>({});
  const [lastConfirmed, setLastConfirmed] = useState<ConfirmedBatch | null>(null);
  const session = useSession();
  const { showToast } = useUi();
  const remote = API_MODE && Boolean(session.menu);

  useEffect(() => {
    if (!remote) return;
    api<GoalStateShape>("/state/goals")
      .then(setState)
      .catch(() => undefined); // 권한 없는 사용자 — 빈 상태
  }, [remote]);

  /** 서버 호출 → 응답 상태로 교체. 성공 여부를 돌려주고, 실패하면 메시지를 보여 준다 */
  const call = useCallback(
    async (path: string, json: unknown): Promise<boolean> => {
      try {
        setState(await api<GoalStateShape>(path, { method: "POST", json }));
        return true;
      } catch (e) {
        showToast(`처리하지 못했습니다 — ${(e as Error).message}`);
        return false;
      }
    },
    [showToast],
  );

  const applyCore = useCallback(
    async (proposal: Proposal, mode: "adopt" | "manual_edit", value?: number, reason?: string, force?: boolean): Promise<boolean> => {
      if (!proposal.targetGoalId) return false;
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
      return true;
    },
    [remote, call],
  );

  const addNewCore = useCallback(
    async (proposal: Proposal, targetLabel: string): Promise<boolean> => {
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
      return true;
    },
    [remote, call],
  );

  const applyProposal = useCallback(
    (proposal: Proposal, mode: "adopt" | "manual_edit", value?: number, reason?: string, force?: boolean) => {
      void applyCore(proposal, mode, value, reason, force);
    },
    [applyCore],
  );

  const addNewGoal = useCallback(
    (proposal: Proposal, targetLabel: string) => {
      void addNewCore(proposal, targetLabel);
    },
    [addNewCore],
  );

  const keepGoal = useCallback(
    (proposal: Proposal) => {
      if (remote) {
        void call("/state/goals/keep", { proposalId: proposal.id });
        return;
      }
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

  const addManualGoal = useCallback(
    (input: ManualGoalInput) => {
      if (remote) {
        void call("/state/goals/manual", input);
        return;
      }
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
      if (remote) {
        void call("/state/goals/review-items", { title });
        return;
      }
      setState((prev) => ({ ...prev, reviewItems: prev.reviewItems.includes(title) ? prev.reviewItems : [...prev.reviewItems, title] }));
    },
    [remote, call],
  );

  const stageProposal = useCallback((item: Omit<StagedItem, "at">) => {
    setStaged((prev) => ({ ...prev, [item.proposal.id]: { ...item, at: new Date().toISOString() } }));
    setLastConfirmed(null);
  }, []);

  const unstageProposal = useCallback((proposalId: string) => {
    setStaged((prev) => {
      if (!prev[proposalId]) return prev;
      const next = { ...prev };
      delete next[proposalId];
      return next;
    });
  }, []);

  const confirmStaged = useCallback(async () => {
    const items = Object.values(staged).sort((a, b) => a.at.localeCompare(b.at));
    const done: StagedItem[] = [];
    let failed = 0;
    // 서버 응답이 상태 전체를 교체하므로 한 건씩 차례로 확정한다
    for (const it of items) {
      const ok =
        it.mode === "added"
          ? await addNewCore(it.proposal, it.targetLabel ?? "")
          : await applyCore(it.proposal, it.mode, it.value, it.reason, it.force);
      if (ok) done.push(it);
      else failed += 1;
    }
    if (done.length) {
      setStaged((prev) => {
        const next = { ...prev };
        for (const it of done) delete next[it.proposal.id];
        return next;
      });
      setLastConfirmed({ count: done.length, at: new Date().toISOString(), titles: done.map((d) => d.proposal.title) });
    }
    return { confirmed: done.length, failed };
  }, [staged, applyCore, addNewCore]);

  const reset = useCallback(() => {
    setStaged({});
    setLastConfirmed(null);
    if (remote) {
      void call("/state/goals/reset", {});
      return;
    }
    setState(EMPTY);
  }, [remote, call]);

  const value = useMemo(
    () => ({
      ...state,
      staged,
      lastConfirmed,
      stageProposal,
      unstageProposal,
      confirmStaged,
      applyProposal,
      keepGoal,
      addNewGoal,
      addManualGoal,
      registerReviewItem,
      reset,
    }),
    [state, staged, lastConfirmed, stageProposal, unstageProposal, confirmStaged, applyProposal, keepGoal, addNewGoal, addManualGoal, registerReviewItem, reset],
  );

  return <GoalStateContext.Provider value={value}>{children}</GoalStateContext.Provider>;
}

export function useGoalState() {
  const ctx = useContext(GoalStateContext);
  if (!ctx) throw new Error("useGoalState must be used within GoalStateProvider");
  return ctx;
}
