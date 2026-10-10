"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { AdminPage, C, Card, Collapse, JsonView, Loading, StatusBadge, Table, duration, fmtTime, useApiData } from "@/components/admin/kit";
import { Badge, Button } from "@/components/ui/primitives";
import { apiGetC } from "@/lib/api-client";

interface RunRow {
  id: string;
  workflow: string;
  status: string;
  startedAt: string;
  finishedAt: string | null;
  causes: { type: string; payload: Record<string, unknown>; reasons?: string[] }[];
  summary: { nodes?: { key: string; status: string; ms: number }[]; published?: string[]; figure_changes?: number };
  traceId?: string | null;
  error: string | null;
  llmCalls: number;
  tokens: number;
  calcRuns: number;
}
interface RunDetail {
  run: RunRow;
  nodes: { id: string; seq: number; key: string; impl: string; agent: string | null; status: string; input: unknown; output: unknown; error: string | null; durationMs: number | null }[];
  llmCalls: { id: string; nodeRunId: string | null; agent: string | null; purpose: string; model: string | null; connection: string | null; params: Record<string, unknown>; status: string; error: string | null; promptTokens: number | null; completionTokens: number | null; latencyMs: number | null; output: string | null }[];
  calcRuns: { id: string; formula: string; metric: string | null; display: number | null; value: string | null; error: string | null; library: string | null }[];
}

export default function RunsMonitorPage() {
  return (
    <Suspense>
      <RunsMonitor />
    </Suspense>
  );
}

/** 에이전트 실행 → 노드 입력·출력 → LLM 호출 원문 → 계산 (ADM-11) */
function RunsMonitor() {
  const params = useSearchParams();
  const [wf, setWf] = useState("");
  const runs = useApiData<RunRow[]>(`/admin/monitor/runs?limit=60${wf ? `&workflow=${wf}` : ""}`, { refreshMs: 6000 });
  const [sel, setSel] = useState<string | null>(params.get("run"));
  const detail = useApiData<RunDetail>(sel ? `/admin/monitor/runs/${sel}` : null);
  const [call, setCall] = useState<unknown>(null);
  const wfs = Array.from(new Set((runs.data ?? []).map((r) => r.workflow)));

  return (
    <AdminPage title="에이전트 실행" description="워크플로우 실행마다 원인(이벤트·사유), 노드별 입력·출력·소요, LLM 호출(모델·파라미터 스냅샷·메시지·응답·토큰·지연), 커널 계산을 확인합니다.">
      <div className="grid grid-cols-1 gap-lg xl:grid-cols-[420px_1fr]">
        <Card
          title="실행 목록"
          actions={
            <select className="input !h-8 !w-auto text-[12px]" value={wf} onChange={(e) => setWf(e.target.value)} aria-label="워크플로우">
              <option value="">전체</option>
              {wfs.map((w) => (
                <option key={w} value={w}>
                  {w}
                </option>
              ))}
            </select>
          }
        >
          <Loading error={runs.error} loading={!runs.data && runs.loading} />
          <ul className="flex flex-col">
            {(runs.data ?? []).map((r) => (
              <li key={r.id}>
                <button
                  type="button"
                  onClick={() => {
                    setSel(r.id);
                    setCall(null);
                  }} className={`row-button w-full border-b border-hairline-soft px-xs py-2 ${sel === r.id ? "bg-surface-soft" : ""}`}>
                  <div className="flex items-center gap-xs">
                    <StatusBadge status={r.status} />
                    <span className="text-[12.5px] font-bold text-ink-deep">{r.workflow}</span>
                    <span className="ml-auto text-[10.5px] text-stone">{duration(r.startedAt, r.finishedAt)}</span>
                  </div>
                  <p className="mt-0.5 text-[10.5px] text-stone">
                    {fmtTime(r.startedAt)} · 원인 {r.causes.map((c) => c.type).join(", ")} · LLM {r.llmCalls} · 계산 {r.calcRuns}
                  </p>
                </button>
              </li>
            ))}
          </ul>
        </Card>
        <div>
          {!sel ? <p className="text-[12.5px] text-stone">왼쪽에서 실행을 선택하세요.</p> : null}
          <Loading error={detail.error} loading={Boolean(sel) && !detail.data && detail.loading} />
          {detail.data ? (
            <>
              <Card title={`${detail.data.run.workflow} · ${fmtTime(detail.data.run.startedAt)}`} actions={<StatusBadge status={detail.data.run.status} />}>
                {detail.data.run.error ? <p className="mb-md text-[12px] text-critical">{detail.data.run.error}</p> : null}
                {detail.data.run.traceId ? (
                  <p className="mb-md text-[11.5px] text-steel">
                    추적 ID{" "}
                    <a className="font-mono text-primary hover:underline" href={`/admin/monitor/trace?id=${detail.data.run.traceId}`} data-run-trace>
                      {detail.data.run.traceId}
                    </a>
                  </p>
                ) : null}
                <p className="text-[11.5px] font-bold text-steel">원인</p>
                <ul className="mb-md text-[12px]">
                  {detail.data.run.causes.map((c, i) => (
                    <li key={i}>
                      <Badge>{c.type}</Badge> <span className="font-mono text-[11px]">{JSON.stringify(c.payload)}</span> <span className="text-[11px] text-stone">{c.reasons?.join(" · ")}</span>
                    </li>
                  ))}
                </ul>
                <p className="text-[11.5px] text-steel">
                  게시: {detail.data.run.summary.published?.join(", ") || "변경 없음"} · 수치 변경 {detail.data.run.summary.figure_changes ?? 0}건
                </p>
              </Card>
              <Card title="노드">
                <div className="flex flex-col gap-md">
                  {detail.data.nodes.map((n) => (
                    <div key={n.id} className="rounded-lg border border-hairline-soft p-md">
                      <div className="flex flex-wrap items-center gap-xs">
                        <span className="font-mono text-[11px] text-stone">{n.seq}</span>
                        <b className="text-[13px] text-ink-deep">{n.key}</b>
                        <Badge>{n.impl}</Badge>
                        {n.agent ? <Badge tone="info">{n.agent}</Badge> : null}
                        <StatusBadge status={n.status} />
                        <span className="ml-auto text-[11px] text-stone">{n.durationMs ?? "-"}ms</span>
                      </div>
                      {n.error ? <pre className="mt-xs whitespace-pre-wrap text-[11px] text-critical">{n.error.slice(0, 1500)}</pre> : null}
                      <div className="mt-xs grid grid-cols-1 gap-xs lg:grid-cols-2">
                        <Collapse label="입력">
                          <JsonView value={n.input} maxHeight={260} />
                        </Collapse>
                        <Collapse label="출력" defaultOpen={n.impl === "narrate" || n.impl === "critic"}>
                          <JsonView value={n.output} maxHeight={320} />
                        </Collapse>
                      </div>
                    </div>
                  ))}
                </div>
              </Card>
              <Card title={`LLM 호출 ${detail.data.llmCalls.length}건`}>
                <Table head={["에이전트", "모델 · 연결", "파라미터", "상태", "토큰", "지연", ""]}>
                  {detail.data.llmCalls.map((c) => (
                    <tr key={c.id}>
                      <C>
                        {c.agent} <Badge>{c.purpose}</Badge>
                      </C>
                      <C mono>
                        {c.model}
                        <br />
                        {c.connection}
                      </C>
                      <C className="max-w-[260px] font-mono text-[10.5px]">{JSON.stringify(c.params)}</C>
                      <C>
                        <StatusBadge status={c.status} />
                        {c.error ? <p className="max-w-[220px] text-[10.5px] text-critical">{c.error.slice(0, 200)}</p> : null}
                      </C>
                      <C right>
                        {c.promptTokens ?? "-"} / {c.completionTokens ?? "-"}
                      </C>
                      <C right>{c.latencyMs ?? "-"}ms</C>
                      <C>
                        <Button size="sm" variant="quiet" onClick={() => apiGetC(`/admin/monitor/llm-calls/${c.id}`).then(setCall)}>
                          원문
                        </Button>
                      </C>
                    </tr>
                  ))}
                </Table>
                {!detail.data.llmCalls.length ? <p className="py-md text-[12px] text-stone">LLM 호출 없음 (모델 미설정이면 서술 노드가 템플릿으로 폴백합니다)</p> : null}
                {call ? (
                  <div className="mt-md">
                    <JsonView value={call} maxHeight={480} />
                  </div>
                ) : null}
              </Card>
              <Card title={`커널 계산 ${detail.data.calcRuns.length}건`}>
                <Table head={["지표", "수식", "표시값", "내부값", "라이브러리", "오류"]}>
                  {detail.data.calcRuns.map((c) => (
                    <tr key={c.id}>
                      <C mono>{c.metric}</C>
                      <C>{c.formula}</C>
                      <C right>{c.display ?? "-"}</C>
                      <C mono>{c.value ?? "-"}</C>
                      <C className="text-[11px]">{c.library}</C>
                      <C className="text-[11px] text-critical">{c.error}</C>
                    </tr>
                  ))}
                </Table>
              </Card>
            </>
          ) : null}
        </div>
      </div>
    </AdminPage>
  );
}
