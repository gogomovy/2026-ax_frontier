"use client";

/* 관리자 [데이터 흐름] · [에이전트 결정] 공용 — 파이프라인 그림 부품.
 * 상태는 색만으로 전하지 않는다: 점 모양(채움 · 비움 · 점선) + 글자 라벨을 함께 쓴다. */

import clsx from "clsx";
import type { ReactNode } from "react";

export type StepState = "done" | "active" | "warn" | "fail" | "idle" | "skip";

export const STATUS_STEP: Record<string, { state: StepState; label: string }> = {
  succeeded: { state: "done", label: "성공" },
  done: { state: "done", label: "완료" },
  degraded: { state: "warn", label: "축소 실행" },
  failed: { state: "fail", label: "실패" },
  running: { state: "active", label: "실행 중" },
  queued: { state: "idle", label: "대기" },
  approval: { state: "warn", label: "승인 대기" },
  skipped: { state: "skip", label: "건너뜀" },
  rejected: { state: "skip", label: "반려" },
  cancelled: { state: "skip", label: "취소" },
};

export function stepOf(status?: string | null): { state: StepState; label: string } {
  return (status && STATUS_STEP[status]) || { state: "idle", label: status || "기록 없음" };
}

const DOT: Record<StepState, string> = {
  done: "bg-success",
  warn: "bg-warning",
  fail: "bg-critical",
  active: "bg-primary motion-safe:animate-pulse",
  idle: "border-2 border-steel bg-white",
  skip: "border-2 border-dashed border-stone bg-white",
};
const TEXT: Record<StepState, string> = {
  done: "text-success-text",
  warn: "text-attention",
  fail: "text-critical-text",
  active: "text-primary-text",
  idle: "text-steel",
  skip: "text-steel",
};
const EDGE: Record<StepState, string> = {
  done: "border-hairline",
  warn: "border-warning",
  fail: "border-critical",
  active: "border-primary",
  idle: "border-hairline",
  skip: "border-dashed border-hairline",
};
/** 노드 상태 막대(데이터 흐름 한 줄 보기) */
export const BAR: Record<string, string> = { succeeded: "bg-success", degraded: "bg-warning", skipped: "bg-hairline", failed: "bg-critical", running: "bg-primary motion-safe:animate-pulse", queued: "bg-steel" };

export function StateDot({ state, className }: { state: StepState; className?: string }) {
  return <span aria-hidden="true" className={clsx("inline-block h-2.5 w-2.5 shrink-0 rounded-full", DOT[state], className)} />;
}

export function stateText(state: StepState): string {
  return TEXT[state];
}

/** 단계 사이 연결 화살표 — 장식. vertical 은 위에서 아래로 */
export function Connector({ vertical = false, className }: { vertical?: boolean; className?: string }) {
  return (
    <span aria-hidden="true" className={clsx("flex shrink-0 items-center justify-center text-stone", vertical ? "h-5 w-full" : "w-5 self-center", className)}>
      {vertical ? (
        <svg width="10" height="20" viewBox="0 0 10 20" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">
          <path d="M5 2v14M1.5 12.5 5 16.5l3.5-4" />
        </svg>
      ) : (
        <svg width="20" height="10" viewBox="0 0 20 10" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">
          <path d="M1 5h16M13 1.5 17 5l-4 3.5" />
        </svg>
      )}
    </span>
  );
}

/** 파이프라인의 한 단계 카드 */
export function Step({ title, state, stateLabel, children, className, dataKey }: { title: ReactNode; state: StepState; stateLabel?: string; children?: ReactNode; className?: string; dataKey?: string }) {
  return (
    <div data-step={dataKey} className={clsx("min-w-0 rounded-xl border bg-white px-3 py-2", EDGE[state], className)}>
      <div className="flex items-center gap-1.5">
        <StateDot state={state} />
        <span className="text-[10.5px] font-bold tracking-wide text-steel">{title}</span>
        {stateLabel ? <span className={clsx("ml-auto pl-2 text-[10.5px] font-bold", TEXT[state])}>{stateLabel}</span> : null}
      </div>
      {children ? <div className="mt-1 text-[12px] text-charcoal">{children}</div> : null}
    </div>
  );
}

export function fmtMs(v?: number | null): string {
  if (v === null || v === undefined) return "";
  return v < 1000 ? `${v}ms` : `${(v / 1000).toFixed(1)}s`;
}

/** 노드 상태를 막대로 이어 붙인 한 줄 — 이름 · 상태는 마우스를 올리거나 화면 낭독기로 */
export function NodeStrip({ nodes, label }: { nodes: { key: string; name: string; status: string; ms?: number | null }[]; label: string }) {
  if (!nodes.length) return null;
  const count = (s: string) => nodes.filter((n) => n.status === s).length;
  const tail = [count("degraded") ? `축소 ${count("degraded")}` : "", count("failed") ? `실패 ${count("failed")}` : "", count("skipped") ? `건너뜀 ${count("skipped")}` : ""].filter(Boolean).join(" · ");
  return (
    <div className="min-w-0">
      <ol className="flex flex-wrap gap-[3px]" aria-label={label}>
        {nodes.map((n) => (
          <li key={n.key} title={`${n.name} · ${stepOf(n.status).label}${n.ms ? ` · ${fmtMs(n.ms)}` : ""}`}>
            <span aria-hidden="true" className={clsx("block h-2.5 w-4 rounded-[3px]", BAR[n.status] ?? "bg-hairline")} />
            <span className="sr-only">
              {n.name} {stepOf(n.status).label}
            </span>
          </li>
        ))}
      </ol>
      <p className="mt-1 text-[11px] text-steel">
        노드 {nodes.length}
        {tail ? ` · ${tail}` : ""}
      </p>
    </div>
  );
}

/** 요약 단계(깔때기) — 숫자 카드를 화살표로 이어 처리 단계를 한눈에 */
export function Funnel({ steps, label }: { steps: { key: string; title: string; value: number | string; unit?: string; hint?: string; state?: StepState }[]; label: string }) {
  return (
    <ol className="grid grid-cols-1 gap-xs md:grid-cols-[repeat(5,minmax(0,1fr))] md:gap-5" aria-label={label} data-flow-funnel>
      {steps.map((s, i) => (
        <li key={s.key} className="relative">
          <div className={clsx("h-full rounded-xl border bg-white px-3 py-2.5", EDGE[s.state ?? "done"])}>
            <p className="flex items-center gap-1.5 text-[11px] font-bold text-steel">
              <StateDot state={s.state ?? "done"} />
              <span className="text-[10px] text-stone" aria-hidden="true">
                {i + 1}
              </span>
              {s.title}
            </p>
            <p className="mt-0.5 text-[22px] font-bold leading-tight text-ink-deep tnum">
              {s.value}
              {s.unit ? <span className="ml-0.5 text-[12px] font-medium text-steel">{s.unit}</span> : null}
            </p>
            {s.hint ? <p className="mt-0.5 text-[11px] leading-snug text-steel">{s.hint}</p> : null}
          </div>
          {i < steps.length - 1 ? <span aria-hidden="true" className="absolute -right-5 top-1/2 hidden -translate-y-1/2 text-stone md:block"><Connector /></span> : null}
        </li>
      ))}
    </ol>
  );
}
