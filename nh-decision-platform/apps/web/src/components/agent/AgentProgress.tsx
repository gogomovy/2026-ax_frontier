"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import clsx from "clsx";
import { useUi } from "@/components/providers/UiProvider";
import { Button, IconCheck, IconWarn } from "@/components/ui/primitives";
import { api } from "@/lib/api-client";
import { API_MODE } from "@/lib/config";

interface Step {
  key: string;
  name: string;
  status: "pending" | "running" | "succeeded" | "degraded" | "skipped" | "failed";
  durationMs: number | null;
}
interface Progress {
  phase: "queued" | "running" | "done" | "failed" | "timeout" | "missing";
  workflow?: string;
  runId?: string | null;
  status?: string | null;
  traceId?: string | null;
  steps: Step[];
}

const PHASE_LABEL: Record<Progress["phase"], string> = {
  queued: "대기 중",
  running: "분석 중",
  done: "완료",
  failed: "실패",
  timeout: "응답 지연",
  missing: "요청 없음",
};

/** 단계 목록 (UX-05) — 완료 · 진행 · 대기 · 축소(degraded) · 실패 */
export function AgentProgress({ progress }: { progress: Progress }) {
  return (
    <ol aria-label="분석 단계" aria-live="polite" className="flex flex-col gap-1.5" data-agent-progress>
      {progress.steps.map((s) => (
        <li key={s.key} className="flex items-center gap-2 text-[12.5px]" data-step={s.key} data-status={s.status}>
          <span
            aria-hidden
            className={clsx(
              "flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px]",
              s.status === "succeeded" && "bg-success-soft text-success",
              s.status === "degraded" && "bg-attention-soft text-warning",
              s.status === "failed" && "bg-critical-soft text-critical",
              s.status === "running" && "animate-pulse bg-info-soft text-primary",
              (s.status === "pending" || s.status === "skipped") && "bg-surface-soft text-stone",
            )}
          >
            {s.status === "succeeded" ? <IconCheck /> : s.status === "failed" || s.status === "degraded" ? <IconWarn /> : "•"}
          </span>
          <span className={clsx(s.status === "pending" ? "text-stone" : "text-ink")}>{s.name}</span>
          <span className="ml-auto text-[11px] text-stone tnum">
            {s.status === "running" ? "진행 중" : s.status === "degraded" ? "축소 실행" : s.status === "skipped" ? "건너뜀" : s.durationMs != null ? `${s.durationMs}ms` : ""}
          </span>
        </li>
      ))}
    </ol>
  );
}

/**
 * 온디맨드 분석 (F.9) — 버튼 → `POST /analysis/run` → `GET /analysis/stream` (SSE) 로 단계 진행 표시 → 완료 시 화면 새로고침.
 * 목업 모드에서는 표시하지 않는다.
 */
export function OnDemandAnalysis({ workflow, label = "분석 다시 실행" }: { workflow: string; label?: string }) {
  const router = useRouter();
  const { showToast } = useUi();
  const [progress, setProgress] = useState<Progress | null>(null);
  const [open, setOpen] = useState(false);
  const source = useRef<EventSource | null>(null);

  useEffect(() => () => source.current?.close(), []);

  const start = useCallback(async () => {
    source.current?.close();
    setOpen(true);
    setProgress({ phase: "queued", steps: [] });
    try {
      const r = await api<{ event: number; reused: boolean }>("/analysis/run", { method: "POST", json: { workflow } });
      if (r.reused) showToast("방금 요청된 같은 분석의 진행 상황을 보여줍니다");
      const es = new EventSource(`/backend/analysis/stream?event=${r.event}`);
      source.current = es;
      const read = (e: MessageEvent<string>) => setProgress(JSON.parse(e.data) as Progress);
      es.addEventListener("progress", read as EventListener);
      es.addEventListener("end", ((e: MessageEvent<string>) => {
        const p = JSON.parse(e.data) as Progress;
        setProgress(p);
        es.close();
        if (p.phase === "done") {
          showToast(p.status === "degraded" ? "분석을 갱신했습니다(일부 단계 축소 실행)" : "분석을 갱신했습니다");
          router.refresh();
        } else {
          showToast(`분석이 끝나지 않았습니다 — ${PHASE_LABEL[p.phase]}${p.traceId ? ` · 추적 ID ${p.traceId}` : ""}`);
        }
      }) as EventListener);
      es.onerror = () => {
        // 서버가 스트림을 닫은 뒤의 재연결 시도는 무시(end 수신 후 close)
        if (es.readyState === EventSource.CLOSED) return;
      };
    } catch (e) {
      setProgress(null);
      setOpen(false);
      showToast(`분석을 시작하지 못했습니다 — ${(e as Error).message}`);
    }
  }, [workflow, router, showToast]);

  if (!API_MODE) return null;
  const running = progress && (progress.phase === "queued" || progress.phase === "running");
  return (
    <div className="relative" data-on-demand={workflow}>
      <Button size="sm" variant="ghost" disabled={Boolean(running)} onClick={start}>
        {running ? `${PHASE_LABEL[progress.phase]}…` : label}
      </Button>
      {open && progress ? (
        <div
          role="status"
          className="absolute right-0 z-30 mt-2 w-[300px] rounded-xl border border-hairline bg-canvas p-base shadow-pop"
        >
          <div className="mb-2 flex items-center justify-between">
            <p className="text-[12px] font-bold text-ink-deep">분석 진행 · {PHASE_LABEL[progress.phase]}</p>
            <button type="button" className="text-[11px] text-steel" onClick={() => setOpen(false)}>
              닫기
            </button>
          </div>
          {progress.steps.length ? <AgentProgress progress={progress} /> : <p className="text-[12px] text-stone">작업 대기열에 올렸습니다…</p>}
        </div>
      ) : null}
    </div>
  );
}
