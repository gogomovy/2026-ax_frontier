"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import clsx from "clsx";
import { api } from "@/lib/api-client";
import { formatDateTime } from "@/lib/format";
import { refreshConditions, stateLabel, type WorkflowStatus } from "@/lib/refreshStatus";

/**
 * 분석 갱신 상태 (Phase P · AGW-08) — 이 분석이 언제 · 왜 다시 계산되는지(자료 변경 · 팀 · 공통 DB · 상위 지표 · 정기 실행)와
 * 지금 새 자료 반영을 기다리는지 · 실행 중인지. 대기 · 실행 중이면 15초마다 다시 보고, 끝나면 화면을 새로 고친다.
 */
export function RefreshStatus({ workflow }: { workflow: string }) {
  const router = useRouter();
  const [st, setSt] = useState<WorkflowStatus | null>(null);
  const [open, setOpen] = useState(false);
  const busyBefore = useRef(false);

  const load = useCallback(
    () =>
      api<WorkflowStatus>(`/analysis/status?workflow=${encodeURIComponent(workflow)}`)
        .then((s) => {
          setSt(s);
          const busy = s.state !== "idle";
          if (busyBefore.current && !busy) router.refresh(); // 반영이 끝났다 — 새 결과로
          busyBefore.current = busy;
        })
        .catch(() => setSt(null)), // 권한 없음 · 일시 오류 — 칩을 그리지 않는다
    [workflow, router],
  );

  useEffect(() => {
    const first = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(first);
  }, [load]);
  const busyNow = Boolean(st && st.state !== "idle");
  useEffect(() => {
    if (!busyNow) return;
    const t = window.setInterval(() => void load(), 15000);
    return () => window.clearInterval(t);
  }, [busyNow, load]);

  if (!st) return null;
  const busy = st.state !== "idle";
  const conds = refreshConditions(st);
  const next = st.triggers.cron[0]?.next;
  return (
    <div className="relative" data-refresh-status={st.state}>
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className={clsx(
          "inline-flex h-8 items-center gap-1.5 rounded-pill border px-3 text-[12px] font-bold transition-colors",
          busy ? "border-info-line bg-info-faint text-primary-deep" : "border-hairline-soft bg-canvas text-steel hover:text-ink-deep",
        )}
      >
        <span aria-hidden className={clsx("h-2 w-2 rounded-full", busy ? "animate-pulse bg-primary" : st.lastRun?.status === "failed" ? "bg-critical" : "bg-success")} />
        {busy ? stateLabel(st.state) : `자동 갱신 · ${conds[0] ?? "수동"}`}
      </button>
      {open ? (
        <div role="dialog" aria-label="분석 갱신 상태" className="absolute right-0 z-30 mt-2 w-[320px] rounded-xl border border-hairline bg-canvas p-base text-[12.5px] shadow-pop">
          <p className="font-bold text-ink-deep">{busy ? stateLabel(st.state) : "최신 상태"}</p>
          {busy && st.pending?.causes.length ? (
            <ul className="mt-1 list-disc pl-4 text-charcoal">
              {st.pending.causes.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
          ) : null}
          <p className="mt-2 text-[11.5px] font-bold text-steel">자동으로 다시 계산되는 때</p>
          <ul className="mt-0.5 list-disc pl-4 text-charcoal">
            {conds.length ? conds.map((c) => <li key={c}>{c}</li>) : <li>수동 실행만</li>}
          </ul>
          <dl className="mt-2 grid grid-cols-[88px_1fr] gap-y-0.5 text-[11.5px]">
            <dt className="text-steel">마지막 갱신</dt>
            <dd className="text-ink tnum">{st.lastSuccessAt ? formatDateTime(st.lastSuccessAt) : "-"}</dd>
            <dt className="text-steel">다음 정기 실행</dt>
            <dd className="text-ink tnum">{next ? formatDateTime(next) : "-"}</dd>
          </dl>
          <button type="button" className="mt-2 text-[11px] text-steel" onClick={() => setOpen(false)}>
            닫기
          </button>
        </div>
      ) : null}
    </div>
  );
}
