"use client";

import Link from "next/link";
import { useState } from "react";
import { AdminPage, Card, Loading, Tabs, useAction, useApiData } from "@/components/admin/kit";
import { EventPipeline, PipelineMap, StatusPill, WorkflowPipeline, type PipelineData } from "@/components/admin/pipeline";
import { Button } from "@/components/ui/primitives";
import { apiPost } from "@/lib/api-client";

type TabKey = "map" | "workflow" | "events";

/** 파이프라인 (B.39 · PIPE-01~07) — 원천 → 워크플로우(노드 · 에이전트) → 산출물 → 화면을 한눈에, 실행 상태는 5초마다 갱신 */
export default function PipelineAdmin() {
  const data = useApiData<PipelineData>("/admin/pipeline", { refreshMs: 5000 });
  const [tab, setTab] = useState<TabKey>("map");
  const [wf, setWf] = useState<string | null>(null);
  const { run, busy } = useAction();
  const d = data.data;
  const cur = wf ?? d?.workflows[0]?.code ?? "";
  const running = d?.workflows.filter((w) => w.live?.status === "running").length ?? 0;

  return (
    <AdminPage
      title="파이프라인"
      description="데이터 · 문서 · 규칙이 바뀌면 관련 워크플로우만 실행되고, 워크플로우 안에서는 계산(커널) → 변화 감지 → 화면 갱신 → 실행 계획 → 근거 → 서술(LLM) → 검증 → 적재 → 게시 순으로 진행합니다. 편집은 워크플로우 · 에이전트 · 컬럼 정의서 화면에서 합니다."
      actions={
        <Button size="sm" variant="quiet" onClick={data.reload}>
          새로고침
        </Button>
      }
    >
      <Loading error={data.error} loading={!d && data.loading} />
      {d ? (
        <>
          <div className="mb-md grid grid-cols-2 gap-xs md:grid-cols-5" data-pipeline-summary>
            <Stat label="원천" value={d.sources.filter((s) => s.kind !== "waiting").length} sub={d.sources.some((s) => s.kind === "waiting") ? `자료 대기 ${d.sources.filter((s) => s.kind === "waiting").length}` : undefined} />
            <Stat label="워크플로우" value={d.workflows.length} sub={running ? `실행 중 ${running}` : "대기"} />
            <Stat label="에이전트 노드" value={d.workflows.reduce((a, w) => a + w.nodes.filter((n) => n.agent).length, 0)} sub={`LLM ${d.workflows.reduce((a, w) => a + w.nodes.filter((n) => n.agent?.kind === "llm").length, 0)}`} />
            <Stat label="산출물" value={d.outputs.length} sub={`정의서 mart ${d.outputs.filter((o) => o.kind === "mart").length}`} />
            <Stat label="업무 화면" value={new Set(d.outputs.flatMap((o) => o.screens)).size} />
          </div>
          <Tabs<TabKey>
            active={tab}
            onChange={setTab}
            tabs={[
              { key: "map", label: "전체 지도" },
              { key: "workflow", label: "워크플로우 파이프라인" },
              { key: "events", label: "이벤트 흐름" },
            ]}
          />
          {tab === "map" ? (
            <Card>
              <PipelineMap
                data={d}
                onOpenWorkflow={(c) => {
                  setWf(c);
                  setTab("workflow");
                }}
              />
            </Card>
          ) : null}
          {tab === "workflow" ? (
            <Card>
              <div className="mb-md flex flex-wrap gap-1.5" role="group" aria-label="워크플로우 선택">
                {d.workflows.map((w) => (
                  <button
                    key={w.code}
                    type="button"
                    aria-pressed={w.code === cur}
                    onClick={() => setWf(w.code)}
                    className={`inline-flex items-center gap-1 rounded-pill px-3 py-1 text-[12px] font-bold ${w.code === cur ? "bg-ink-deep text-white" : "bg-surface-soft text-charcoal"}`}
                  >
                    {w.name}
                    <span className={w.code === cur ? "rounded bg-white px-0.5" : ""}>
                      <StatusPill status={w.live?.status === "running" ? "running" : w.lastRun?.status} />
                    </span>
                  </button>
                ))}
              </div>
              <WorkflowPipeline data={d} code={cur} busy={busy} onRun={(c) => run(() => apiPost(`/admin/workflows/${c}/run`), "실행을 요청했습니다 — 노드가 차례로 끝나는 것을 볼 수 있습니다", data.reload)} />
            </Card>
          ) : null}
          {tab === "events" ? (
            <Card>
              <EventPipeline />
            </Card>
          ) : null}
          <p className="mt-md text-[11.5px] text-stone">
            단계 이름 · 순서는 설정 <code className="font-mono">pipeline.stages</code>, 산출물 → 화면 연결은 <code className="font-mono">screen.resources</code> 에서 바꿉니다. 상세:{" "}
            <Link href="/admin/workflows" className="font-bold text-primary-text">
              워크플로우
            </Link>{" "}
            ·{" "}
            <Link href="/admin/monitor/agents" className="font-bold text-primary-text">
              에이전트 결정
            </Link>{" "}
            ·{" "}
            <Link href="/admin/monitor/runs" className="font-bold text-primary-text">
              에이전트 실행
            </Link>{" "}
            ·{" "}
            <Link href="/admin/contracts" className="font-bold text-primary-text">
              컬럼 정의서
            </Link>
          </p>
        </>
      ) : null}
    </AdminPage>
  );
}

function Stat({ label, value, sub }: { label: string; value: number; sub?: string }) {
  return (
    <div className="rounded-xl border border-hairline bg-white p-sm">
      <p className="text-[11px] font-bold text-steel">{label}</p>
      <p className="tnum text-[20px] font-bold text-ink-deep">{value}</p>
      {sub ? <p className="text-[10.5px] text-stone">{sub}</p> : null}
    </div>
  );
}
