"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { ACTION_PLANS as MOCK_ACTION_PLANS } from "@/mock/risk";
import { api } from "@/lib/api-client";
import { API_MODE } from "@/lib/config";
import type { ActionPlan, Evidence } from "@/lib/types";
import { useSession } from "./SessionProvider";
import { useUi } from "./UiProvider";

/**
 * 수행방안·진행사업 상태 계층.
 *
 *  - API 모드: 서버 상태(`/state/plans/*`) — 등록/해제·전파 토글·수정·삭제·추가가 모든 사용자에게 공유된다.
 *    응답이 이 Provider 의 저장 구조(runtime · userPlans · deleted)와 같아서 병합 로직은 그대로 쓴다.
 *  - 목데이터 모드: 클라이언트 상태 + localStorage
 * 신용리스크관리부 3화면과 종합기획부 '사업부서별 진행 사업 현황' 화면이 같은 상태를 본다.
 */

const STORE_KEY = "nhdip.planState.v1";
const TODAY = "2026-09-27";

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
  const remote = API_MODE && Boolean(session.menu);
  const ACTION_PLANS: ActionPlan[] = useMemo(() => (API_MODE ? (session.actionPlans ?? []) : MOCK_ACTION_PLANS), [session.actionPlans]);

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
    if (remote) {
      api<PersistedState>("/state/plans")
        .then((next) => setState({ ...EMPTY, ...next }))
        .catch(() => undefined);
      return;
    }
    if (API_MODE) return;
    try {
      const raw = window.localStorage.getItem(STORE_KEY);
      // localStorage 는 SSR 과 첫 렌더를 맞추기 위해 마운트 후에만 읽는다
      // eslint-disable-next-line react-hooks/set-state-in-effect
      if (raw) setState({ ...EMPTY, ...(JSON.parse(raw) as PersistedState) });
    } catch {
      /* 저장소 접근 불가 시 기본 상태 유지 */
    }
  }, [remote]);

  const persist = useCallback((next: PersistedState) => {
    setState(next);
    if (API_MODE) return;
    try {
      window.localStorage.setItem(STORE_KEY, JSON.stringify(next));
    } catch {
      /* 저장 실패는 화면 동작에 영향을 주지 않는다 */
    }
  }, []);

  const mutate = useCallback(
    (fn: (prev: PersistedState) => PersistedState) => {
      setState((prev) => {
        const next = fn(prev);
        if (API_MODE) return next; // 서버 응답으로 곧 교체되는 낙관적 갱신
        try {
          window.localStorage.setItem(STORE_KEY, JSON.stringify(next));
        } catch {
          /* noop */
        }
        return next;
      });
    },
    [],
  );

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
      setRuntime(id, { status: "in_progress", registeredAt: TODAY });
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
                    updatedAt: TODAY,
                  }
                : p,
            ),
          };
        }
        return {
          ...prev,
          runtime: {
            ...prev.runtime,
            [id]: { ...prev.runtime[id], patch: { ...prev.runtime[id]?.patch, ...patch }, updatedAt: TODAY },
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
        ownerOrg: input.ownerOrg ?? "신용리스크관리부",
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
        updatedAt: TODAY,
        guideRuleId: "USER_DEFINED",
      };
      mutate((prev) => ({ ...prev, userPlans: [...prev.userPlans, plan] }));
      if (remote) call("/state/plans", { method: "POST", json: { ...input, id } });
      return id;
    },
    [mutate, remote, call],
  );

  const resetPlans = useCallback(() => {
    persist(EMPTY);
    if (remote) call("/state/plans/reset", { method: "POST", json: {} });
  }, [persist, remote, call]);

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
