"use client";

import { useEffect, useState } from "react";
import { useGoalState } from "@/components/providers/GoalStateProvider";
import { Sheet } from "@/components/ui/Sheet";
import { EmptyCard } from "@/components/ui/StateViews";
import { api } from "@/lib/api-client";
import { UNIT_LABEL, formatDate, formatDateTime } from "@/lib/format";
import { resolveGoal } from "@/lib/goalView";
import type { Goal } from "@/lib/types";

interface Entry {
  key: string;
  at: string;
  goal: string;
  goalId: string;
  title: string;
  meta: string;
  /** 이 기록이 만든 목표 버전 · 값 — 복원 대상 */
  version?: number | null;
  value?: number | null;
}

interface ServerEntry {
  at: string;
  action: string;
  actorName: string | null;
  actor: string | null;
  value: number | null;
  version?: number | null;
  restoredVersion?: number | null;
  reason: string | null;
  forced: boolean;
}

/** 목표값 버전을 만드는 기록 — [이 버전으로 복원] 대상 */
const VERSIONED = new Set(["goal.apply", "goal.edit", "goal.revert"]);

const ACTION: Record<string, string> = {
  "goal.apply": "목표 변경",
  "goal.keep": "기존 유지",
  "goal.add_new": "신규 추가",
  "goal.add_manual": "직접 등록",
  "goal.reset": "처리 초기화",
  "goal.revert": "되돌리기",
  "goal.edit": "목표 수정",
  "goal.delete": "목표 삭제",
};

/**
 * 변경 이력 서랍 — 모든 경영목표의 변경을 최신순으로 한 줄씩 보여 준다 (읽을거리 = 서랍).
 * 서버 감사 기록(처리자 · 사유 · 강제 확정 여부)을 목표별로 모아 보여 준다.
 */
export function HistorySheet({
  goals,
  focusGoalId,
  onClose,
  onRestore,
}: {
  goals: Goal[];
  focusGoalId?: string | null;
  onClose: () => void;
  /** 지난 버전 [이 버전으로 복원] — 되돌리기 다이얼로그를 연다 (없으면 복원 단추를 숨김) */
  onRestore?: (goalId: string, toVersion: number, value: number | null) => void;
}) {
  const { overrides } = useGoalState();
  const [server, setServer] = useState<Entry[] | null>(null);

  useEffect(() => {
    let live = true;
    Promise.all(
      goals.map((g) =>
        api<ServerEntry[]>(`/state/goals/${encodeURIComponent(g.id)}/history`)
          .then((rows) =>
            rows.map<Entry>((h, i) => ({
              key: `${g.id}-${h.at}-${i}`,
              at: h.at,
              goal: g.title,
              goalId: g.id,
              version: VERSIONED.has(h.action) ? h.version : null,
              value: h.value,
              title: `${h.version != null ? `v${h.version} · ` : ""}${ACTION[h.action] ?? h.action}${h.value != null && h.action !== "goal.delete" ? ` · ${h.value}${UNIT_LABEL[g.unit]}` : ""}${h.restoredVersion != null ? ` · v${h.restoredVersion} 복원` : ""}${h.forced ? " · 경고 확인 후 확정" : ""}`,
              meta: `${h.actorName ?? h.actor ?? "-"}${h.reason ? ` · ${h.reason}` : ""}`,
            })),
          )
          .catch(() => [] as Entry[]),
      ),
    ).then((all) => {
      if (live) setServer(all.flat());
    });
    return () => {
      live = false;
    };
  }, [goals]);

  const current = (g: Goal) => resolveGoal(g, overrides[g.id]).version;
  // 기준(산출물) 버전 — 확정 변경이 있는 목표만 한 줄 덧붙여 [이 버전으로 복원]으로 기준값에 돌아갈 수 있게 한다
  const baseEntries: Entry[] = server
    ? goals
        .filter((g) => overrides[g.id] && current(g) > g.version)
        .map((g) => ({
          key: `${g.id}-base`,
          at: g.updatedAt,
          goal: g.title,
          goalId: g.id,
          version: g.version,
          value: g.targetValue,
          title: `v${g.version} · 기준 목표${g.targetValue != null ? ` · ${g.targetValue}${UNIT_LABEL[g.unit]}` : ""}`,
          meta: "업로드된 기준 경영목표",
        }))
    : [];
  const entries = [...(server ?? []), ...baseEntries]
    .filter((e) => !focusGoalId || e.goalId === focusGoalId)
    .sort((a, b) => b.at.localeCompare(a.at));
  const goalOf = (id: string) => goals.find((g) => g.id === id);

  return (
    <Sheet open onClose={onClose} eyebrow={<span className="text-[12px] font-normal text-steel">경영목표</span>} title={focusGoalId ? "목표 변경 이력" : "변경 이력"} meta="최신순 · 처리자와 사유가 함께 남아요">
      {server === null ? (
        <p className="py-10 text-center text-[14px] text-steel">변경 이력을 불러오는 중이에요</p>
      ) : entries.length === 0 ? (
        <EmptyCard className="border-0" title="변경 이력이 없어요" description="목표를 조정하거나 유지로 결정하면 이력이 여기에 남아요." />
      ) : (
        <ol className="relative flex flex-col gap-5 border-l border-hairline-soft pl-5">
          {entries.map((e, i) => (
            <li key={e.key} className="relative">
              <span aria-hidden="true" className={`absolute -left-[25px] top-1.5 h-2 w-2 rounded-circle ${i === 0 ? "bg-primary" : "bg-icon"}`} />
              <p className="text-[12px] text-steel tnum">{e.at.length > 10 ? formatDateTime(e.at) : formatDate(e.at)}</p>
              <p className="mt-0.5 text-[14px] font-bold text-ink-deep">{e.title}</p>
              <p className="text-[12px] text-steel">{e.goal}</p>
              {e.meta ? <p className="mt-0.5 text-[12px] text-charcoal">{e.meta}</p> : null}
              {(() => {
                const g = goalOf(e.goalId);
                if (!onRestore || !g || e.version == null || e.version === current(g)) return null;
                return (
                  <button
                    type="button"
                    onClick={() => onRestore(e.goalId, e.version as number, e.value ?? null)}
                    className="mt-1 inline-flex items-center gap-0.5 text-[12px] font-bold text-primary-deep hover:underline"
                    aria-label={`${g.title} v${e.version} 버전으로 복원`}
                  >
                    이 버전으로 복원 <span aria-hidden="true">›</span>
                  </button>
                );
              })()}
            </li>
          ))}
        </ol>
      )}
    </Sheet>
  );
}
