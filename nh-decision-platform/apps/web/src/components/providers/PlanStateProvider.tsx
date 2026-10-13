"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "@/lib/api-client";
import { todayKst } from "@/lib/period";
import type { ActionPlan, Evidence } from "@/lib/types";
import { useSession } from "./SessionProvider";
import { useUi } from "./UiProvider";

/**
 * 수행방안·진행사업 상태 계층 — 서버 상태(`/state/plans/*`).
 * 등록/해제·전파 토글·수정·삭제·추가가 모든 사용자에게 공유된다.
 * 응답이 이 Provider 의 저장 구조(runtime · userPlans · deleted)와 같아서 병합 로직은 그대로 쓴다.
 * 화면 변경은 낙관적으로 먼저 반영하고 서버 응답으로 곧 교체한다.
 * 신용리스크관리부 3화면과 종합기획부 '사업부서별 진행 사업 현황' 화면이 같은 상태를 본다.
 */

export interface PlanPatch {
  title?: string;
  body?: string;
  monitoringMetrics?: string[];
  evidenceNote?: string;
  reviewCycle?: string;
  linkedTabKey?: string;
  linkedAnalysisLabel?: string;
}

export interface NewPlanInput {
  title: string;
  body: string;
  evidenceNote?: string;
  monitoringMetrics: string[];
  reviewCycle?: string;
  ownerOrg?: string;
  linkedTabKey?: string;
  linkedAnalysisLabel?: string;
}

interface PlanRuntime {
  status?: ActionPlan["status"];
  branchShared?: boolean;
  registeredAt?: string;
  updatedAt?: string;
  patch?: PlanPatch;
}

interface PersistedState {
  runtime: Record<string, PlanRuntime>;
  userPlans: ActionPlan[];
  deleted: string[];
}

const EMPTY: PersistedState = { runtime: {}, userPlans: [], deleted: [] };

interface PlanStateValue {
  /** 삭제·수정·등록 상태가 모두 반영된 최종 목록 */
  plans: ActionPlan[];
  proposedPlans: ActionPlan[];
  inProgressPlans: ActionPlan[];
  /** 조직별 진행사업 (종합기획부 현황 화면용) */
  plansByOrg: { org: string; plans: ActionPlan[] }[];
  registerPlan: (id: string) => void;
  unregisterPlan: (id: string) => void;
  toggleBranchShare: (id: string) => void;
  updatePlan: (id: string, patch: PlanPatch) => void;
  deletePlan: (id: string) => void;
  addPlan: (input: NewPlanInput) => string;
  resetPlans: () => void;
}

const PlanStateContext = createContext<PlanStateValue | null>(null);

function userEvidence(note?: string): Evidence[] {
  if (!note?.trim()) return [];
  return [
    {
      id: `ev-user-${Math.random().toString(36).slice(2, 8)}`,
      category: "internal_direction",
      sourceKind: "none",
      label: "담당자 입력 근거",
      snippet: note.trim(),
    },
  ];
}

export function PlanStateProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<PersistedState>(EMPTY);
  const session = useSession();
  const { showToast } = useUi();
  const remote = Boolean(session.menu);
  // 기준 수행방안은 레이아웃이 서버에서 받은 목록 — 없으면 빈 목록
  const ACTION_PLANS: ActionPlan[] = useMemo(() => session.actionPlans ?? [], [session.actionPlans]);
  // 새 수행방안의 기본 담당조직 = 로그인 사용자 소속
  const userOrg = session.menu?.user.org.name ?? "";

  /** 서버 호출 → 응답 상태로 교체 */
  const call = useCallback(
    (path: string, init: { method: string; json?: unknown }) => {
      api<PersistedState>(path, init)
        .then((next) => setState({ ...EMPTY, ...next }))
        .catch((e: Error) => showToast(`처리하지 못했습니다 — ${e.message}`));
    },
    [showToast],
  );

  /* 초기 로드 — SSR 과 첫 렌더를 일치시키기 위해 마운트 후 읽는다 */
  useEffect(() => {
    if (!remote) return;
    api<PersistedState>("/state/plans")
      .then((next) => setState({ ...EMPTY, ...next }))
      .catch(() => undefined);
  }, [remote]);

  /** 낙관적 갱신 — 서버 응답으로 곧 교체된다 */
  const mutate = useCallback((fn: (prev: PersistedState) => PersistedState) => setState(fn), []);

  const setRuntime = useCallback(
    (id: string, value: PlanRuntime) =>
      mutate((prev) => ({
        ...prev,
        runtime: { ...prev.runtime, [id]: { ...prev.runtime[id], ...value } },
      })),
    [mutate],
  );

  const registerPlan = useCallback(
    (id: string) => {
      setRuntime(id, { status: "in_progress", registeredAt: todayKst() });
      if (remote) call(`/state/plans/${encodeURIComponent(id)}/register`, { method: "POST" });
    },
    [setRuntime, remote, call],
  );

  /** 진행사업 등록 해제 — 제안안으로 되돌리고 영업점 참고도 중단한다 */
  const unregisterPlan = useCallback(
    (id: string) => {
      setRuntime(id, { status: "proposed", branchShared: false, registeredAt: undefined });
      if (remote) call(`/state/plans/${encodeURIComponent(id)}/unregister`, { method: "POST" });
    },
    [setRuntime, remote, call],
  );

  const toggleBranchShare = useCallback(
    (id: string) => {
      if (remote) call(`/state/plans/${encodeURIComponent(id)}/toggle-share`, { method: "POST" });
      mutate((prev) => {
        const base = ACTION_PLANS.find((p) => p.id === id) ?? prev.userPlans.find((p) => p.id === id);
        const current = prev.runtime[id]?.branchShared ?? base?.branchShared ?? false;
        return {
          ...prev,
          runtime: { ...prev.runtime, [id]: { ...prev.runtime[id], branchShared: !current } },
        };
      });
    },
    [mutate, remote, call, ACTION_PLANS],
  );

  const updatePlan = useCallback(
    (id: string, patch: PlanPatch) => {
      if (remote) call(`/state/plans/${encodeURIComponent(id)}`, { method: "PATCH", json: patch });
      const today = todayKst();
      mutate((prev) => {
        const isUser = prev.userPlans.some((p) => p.id === id);
        if (isUser) {
          return {
            ...prev,
            userPlans: prev.userPlans.map((p) =>
              p.id === id
                ? {
                    ...p,
                    ...patch,
                    evidence: patch.evidenceNote !== undefined ? userEvidence(patch.evidenceNote) : p.evidence,
                    updatedAt: today,
                  }
                : p,
            ),
          };
        }
        return {
          ...prev,
          runtime: {
            ...prev.runtime,
            [id]: { ...prev.runtime[id], patch: { ...prev.runtime[id]?.patch, ...patch }, updatedAt: today },
          },
        };
      });
    },
    [mutate, remote, call],
  );

  const deletePlan = useCallback(
    (id: string) => {
      if (remote) call(`/state/plans/${encodeURIComponent(id)}`, { method: "DELETE" });
      mutate((prev) => ({
        ...prev,
        deleted: prev.deleted.includes(id) ? prev.deleted : [...prev.deleted, id],
        userPlans: prev.userPlans.filter((p) => p.id !== id),
      }));
    },
    [mutate, remote, call],
  );

  const addPlan = useCallback(
    (input: NewPlanInput) => {
      const id = `plan-user-${Date.now().toString(36)}`;
      const plan: ActionPlan = {
        id,
        title: input.title,
        body: input.body,
        ownerOrg: input.ownerOrg ?? userOrg,
        monitoringMetrics: input.monitoringMetrics,
        reviewCycle: input.reviewCycle ?? "월",
        alignment: { verdict: "unknown", matched: [], conflicts: [] },
        evidence: userEvidence(input.evidenceNote),
        evidenceNote: input.evidenceNote,
        status: "proposed",
        branchShared: false,
        origin: "user",
        linkedTabKey: input.linkedTabKey,
        linkedAnalysisLabel: input.linkedAnalysisLabel,
        updatedAt: todayKst(),
        guideRuleId: "USER_DEFINED",
      };
      mutate((prev) => ({ ...prev, userPlans: [...prev.userPlans, plan] }));
      if (remote) call("/state/plans", { method: "POST", json: { ...input, id } });
      return id;
    },
    [mutate, remote, call, userOrg],
  );

  const resetPlans = useCallback(() => {
    setState(EMPTY);
    if (remote) call("/state/plans/reset", { method: "POST", json: {} });
  }, [remote, call]);

  const plans = useMemo(() => {
    const base = ACTION_PLANS.filter((p) => !state.deleted.includes(p.id)).map((p) => {
      const rt = state.runtime[p.id];
      if (!rt) return p;
      return {
        ...p,
        ...rt.patch,
        status: rt.status ?? p.status,
        branchShared: rt.branchShared ?? p.branchShared,
        registeredAt: rt.registeredAt ?? p.registeredAt,
        updatedAt: rt.updatedAt ?? p.updatedAt,
      };
    });
    const user = state.userPlans
      .filter((p) => !state.deleted.includes(p.id))
      .map((p) => {
        const rt = state.runtime[p.id];
        if (!rt) return p;
        return {
          ...p,
          ...rt.patch,
          status: rt.status ?? p.status,
          branchShared: rt.branchShared ?? p.branchShared,
          registeredAt: rt.registeredAt ?? p.registeredAt,
          updatedAt: rt.updatedAt ?? p.updatedAt,
        };
      });
    return [...base, ...user];
  }, [state, ACTION_PLANS]);

  const proposedPlans = useMemo(() => plans.filter((p) => p.status === "proposed"), [plans]);
  const inProgressPlans = useMemo(() => plans.filter((p) => p.status === "in_progress"), [plans]);

  const plansByOrg = useMemo(() => {
    const orgs = Array.from(new Set(inProgressPlans.map((p) => p.ownerOrg)));
    return orgs.map((org) => ({ org, plans: inProgressPlans.filter((p) => p.ownerOrg === org) }));
  }, [inProgressPlans]);

  const value = useMemo(
    () => ({
      plans,
      proposedPlans,
      inProgressPlans,
      plansByOrg,
      registerPlan,
      unregisterPlan,
      toggleBranchShare,
      updatePlan,
      deletePlan,
      addPlan,
      resetPlans,
    }),
    [
      plans,
      proposedPlans,
      inProgressPlans,
      plansByOrg,
      registerPlan,
      unregisterPlan,
      toggleBranchShare,
      updatePlan,
      deletePlan,
      addPlan,
      resetPlans,
    ],
  );

  return <PlanStateContext.Provider value={value}>{children}</PlanStateContext.Provider>;
}

export function usePlanState() {
  const ctx = useContext(PlanStateContext);
  if (!ctx) throw new Error("usePlanState must be used within PlanStateProvider");
  return ctx;
}
