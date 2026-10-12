"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";
import { AdminPage, C, Card, Collapse, JsonView, Loading, StatusBadge, Table, duration, fmtTime, useApiData } from "@/components/admin/kit";
import { Timeline } from "@/components/charts/Bars";
import { Advanced, EmptyState, KeyValueList } from "@/components/ui/Layout";
import { Badge, Button } from "@/components/ui/primitives";
import { StatCard, StatGrid } from "@/components/ui/StatCard";
import { apiGetC } from "@/lib/api-client";

interface RunRow {
  id: string;
  workflow: string;
  status: string;
  startedAt: string;
  finishedAt: string | null;
  causes: { type: string; payload: Record<string, unknown>; reasons?: string[] }[];
  summary: { nodes?: { key: string; status: string; ms: number }[]; published?: string[]; figure_changes?: number; scopes?: { scope: string; status?: string }[] };
  traceId?: string | null;
  error: string | null;
  llmCalls: number;
  tokens: number;
  calcRuns: number;
}
interface NodeRow {
  id: string;
  seq: number;
  key: string;
  impl: string;
  agent: string | null;
  status: string;
  input: unknown;
  output: unknown;
  error: string | null;
  durationMs: number | null;
  startedAt?: string | null;
}
interface RunDetail {
  run: RunRow;
  nodes: NodeRow[];
  llmCalls: { id: string; nodeRunId: string | null; agent: string | null; purpose: string; model: string | null; connection: string | null; params: Record<string, unknown>; status: string; error: string | null; promptTokens: number | null; completionTokens: number | null; latencyMs: number | null; output: string | null }[];
  calcRuns: { id: string; formula: string; metric: string | null; display: number | null; value: string | null; error: string | null; library: string | null }[];
}

const STATUS_LABEL: Record<string, string> = { succeeded: "성공", degraded: "축소", failed: "실패", running: "실행 중", skipped: "건너뜀", queued: "대기" };
const CAUSE_LABEL: Record<string, string> = { "dataset.committed": "자료 반영", schedule: "일정", manual: "수동 실행", "rule.changed": "규칙 변경", "ontology.changed": "온톨로지 변경" };

export default function RunsMonitorPage() {
  return (
    <Suspense>
      <RunsMonitor />
    </Suspense>
  );
}

/** 노드 시작 시각 → 실행 시작 기준 ms (없으면 앞 노드 끝에 이어 붙인다) */
function timelineItems(run: RunRow, nodes: NodeRow[]) {
  const t0 = new Date(run.startedAt).getTime();
  let cursor = 0;
  return nodes.map((n) => {
    const at = n.startedAt ? new Date(n.startedAt).getTime() - t0 : cursor;
    const start = Number.isFinite(at) && at >= 0 ? at : cursor;
    const dur = n.durationMs ?? 0;
    cursor = Math.max(cursor, start + dur);
    return { key: n.id, label: n.key, status: n.status, startMs: start, durationMs: dur };
  });
}

/** 에이전트 실행 → 노드 입력·출력 → LLM 호출 원문 → 계산 (ADM-11 · MON-02) */
function RunsMonitor() {
  const params = useSearchParams();
  const [wf, setWf] = useState("");
  const [st, setSt] = useState("");
  const runs = useApiData<RunRow[]>(`/admin/monitor/runs?limit=60${wf ? `&workflow=${wf}` : ""}`, { refreshMs: 6000 });
  const [sel, setSel] = useState<string | null>(params.get("run"));
  const detail = useApiData<RunDetail>(sel ? `/admin/monitor/runs/${sel}` : null);
  const [call, setCall] = useState<unknown>(null);
  const wfs = Array.from(new Set((runs.data ?? []).map((r) => r.workflow)));
  const rows = (runs.data ?? []).filter((r) => !st || r.status === st);
  const d = detail.data;
  const items = useMemo(() => (d ? timelineItems(d.run, d.nodes) : []), [d]);
  const tokens = d ? d.llmCalls.reduce((n, c) => n + (c.promptTokens ?? 0) + (c.completionTokens ?? 0), 0) : 0;
  const failedNodes = d ? d.nodes.filter((n) => n.status === "failed").length : 0;

  return (
    <AdminPage
      title="에이전트 실행"
      description="워크플로 실행 한 건마다 왜 실행됐는지(원인), 노드가 어떤 순서로 얼마나 걸렸는지(타임라인), LLM 호출과 커널 계산을 확인합니다. 왼쪽에서 실행을 고르세요."
    >
      <div className="grid grid-cols-1 gap-lg xl:grid-cols-[400px_1fr]">
        <Card
          title={`실행 목록 ${rows.length}`}
          actions={
            <>
              <select className="input !h-8 !w-auto text-[12px]" value={wf} onChange={(e) => setWf(e.target.value)} aria-label="워크플로 고르기">
                <option value="">워크플로 전체</option>
                {wfs.map((w) => (
                  <option key={w} value={w}>
                    {w}
                  </option>
                ))}
              </select>
              <select className="input !h-8 !w-auto text-[12px]" value={st} onChange={(e) => setSt(e.target.value)} aria-label="상태 고르기">
                <option value="">상태 전체</option>
                {["succeeded", "degraded", "failed", "running"].map((s) => (
                  <option key={s} value={s}>
                    {STATUS_LABEL[s]}
                  </option>
                ))}
              </select>
            </>
          }
        >
          <Loading error={runs.error} loading={!runs.data && runs.loading} />
          {runs.data && !rows.length ? <EmptyState compact title="실행이 없습니다" description="자료를 반영하거나 워크플로 화면에서 실행하면 여기에 나타납니다." /> : null}
          <ul className="flex flex-col">
            {rows.map((r) => (
              <li key={r.id}>
                <button
                  type="button"
                  aria-current={sel === r.id ? "true" : undefined}
                  onClick={() => {
                    setSel(r.id);
                    setCall(null);
                  }}
                  className={`row-button w-full border-b border-hairline-soft px-xs py-2 text-left ${sel === r.id ? "bg-surface-soft" : ""}`}
                >
                  <div className="flex items-center gap-xs">
                    <StatusBadge status={r.status} label={STATUS_LABEL[r.status] ?? r.status} />
                    <span className="truncate text-[12.5px] font-bold text-ink-deep">{r.workflow}</span>
                    <span className="ml-auto shrink-0 text-[10.5px] text-stone tnum">{duration(r.startedAt, r.finishedAt)}</span>
                  </div>
                  <p className="mt-0.5 text-[10.5px] text-stone">
                    {fmtTime(r.startedAt)} · {r.causes.map((c) => CAUSE_LABEL[c.type] ?? c.type).join(", ") || "원인 없음"} · LLM {r.llmCalls} · 계산 {r.calcRuns}
                  </p>
                </button>
              </li>
            ))}
          </ul>
        </Card>
        <div className="min-w-0">
          {!sel ? <EmptyState title="실행을 고르세요" description="왼쪽 목록에서 실행 한 건을 고르면 원인 · 노드 타임라인 · LLM 호출 · 커널 계산을 보여 줍니다." /> : null}
          <Loading error={detail.error} loading={Boolean(sel) && !d && detail.loading} />
          {d ? (
            <>
              <div className="mb-lg">
                <StatGrid columns={4} label="실행 요약">
                  <StatCard label="상태" value={STATUS_LABEL[d.run.status] ?? d.run.status} tone={d.run.status === "failed" ? "critical" : d.run.status === "degraded" ? "attention" : "success"} hint={`${fmtTime(d.run.startedAt)} 시작`} />
                  <StatCard label="소요" value={duration(d.run.startedAt, d.run.finishedAt)} hint={`노드 ${d.nodes.length}개${failedNodes ? ` · 실패 ${failedNodes}` : ""}`} tone={failedNodes ? "critical" : "default"} />
                  <StatCard label="LLM 호출" value={d.llmCalls.length} unit="건" hint={`토큰 ${tokens.toLocaleString("ko-KR")}`} />
                  <StatCard label="수치 변경" value={d.run.summary.figure_changes ?? 0} unit="건" hint={`커널 계산 ${d.calcRuns.length}건`} />
                </StatGrid>
              </div>
              <Card title={`${d.run.workflow} · ${fmtTime(d.run.startedAt)}`} actions={<StatusBadge status={d.run.status} label={STATUS_LABEL[d.run.status] ?? d.run.status} />}>
                {d.run.error ? <p className="mb-md rounded-lg bg-critical-faint px-md py-2 text-[12px] text-critical">{d.run.error}</p> : null}
                <KeyValueList
                  items={[
                    {
                      label: "원인",
                      value: d.run.causes.length ? (
                        <ul className="flex flex-col gap-0.5">
                          {d.run.causes.map((c, i) => (
                            <li key={i}>
                              <Badge>{CAUSE_LABEL[c.type] ?? c.type}</Badge> <span className="text-[11.5px] text-steel">{c.reasons?.join(" · ")}</span>
                            </li>
                          ))}
                        </ul>
                      ) : (
                        "-"
                      ),
                    },
                    { label: "게시", value: d.run.summary.published?.join(", ") || "변경 없음" },
                    ...(d.run.summary.scopes?.length ? [{ label: "범위(지점)", value: d.run.summary.scopes.map((s) => s.scope).join(", ") }] : []),
                    ...(d.run.traceId
                      ? [
                          {
                            label: "추적 ID",
                            value: (
                              <a className="font-mono text-[11.5px] text-primary hover:underline" href={`/admin/monitor/trace?id=${d.run.traceId}`} data-run-trace>
                                {d.run.traceId}
                              </a>
                            ),
                          },
                        ]
                      : []),
                  ]}
                />
                <div className="mt-md">
                  <Advanced label="원인 원본(JSON)">
                    <JsonView value={d.run.causes} maxHeight={240} />
                  </Advanced>
                </div>
              </Card>
              <Card title="노드 타임라인">
                <Timeline title="실행 시작 기준 노드별 시작 · 소요" items={items} />
              </Card>
              <Card title={`노드 ${d.nodes.length}개`}>
                <div className="flex flex-col gap-md">
                  {d.nodes.map((n) => (
                    <div key={n.id} className="rounded-lg border border-hairline-soft p-md">
                      <div className="flex flex-wrap items-center gap-xs">
                        <span className="font-mono text-[11px] text-stone">{n.seq}</span>
                        <b className="text-[13px] text-ink-deep">{n.key}</b>
                        <Badge>{n.impl}</Badge>
                        {n.agent ? <Badge tone="info">{n.agent}</Badge> : null}
                        <StatusBadge status={n.status} label={STATUS_LABEL[n.status] ?? n.status} />
                        <span className="ml-auto text-[11px] text-stone tnum">{n.durationMs ?? "-"}ms</span>
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
              <Card title={`LLM 호출 ${d.llmCalls.length}건`}>
                {d.llmCalls.length ? (
                  <Table head={["에이전트", "모델 · 연결", "상태", "토큰(입력/출력)", "지연", ""]}>
                    {d.llmCalls.map((c) => (
                      <tr key={c.id}>
                        <C>
                          {c.agent} <Badge>{c.purpose}</Badge>
                        </C>
                        <C mono>
                          {c.model}
                          <br />
                          {c.connection}
                        </C>
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
                ) : (
                  <p className="py-xs text-[12px] text-stone">LLM 호출 없음 — 모델이 설정되지 않았거나 서술할 변화가 없으면 서술 노드가 기존 문장을 유지합니다.</p>
                )}
                {call ? (
                  <div className="mt-md">
                    <Advanced label="호출 원문(메시지 · 응답 · 파라미터)" defaultOpen>
                      <JsonView value={call} maxHeight={480} />
                    </Advanced>
                  </div>
                ) : null}
              </Card>
              <Card title={`커널 계산 ${d.calcRuns.length}건`}>
                {d.calcRuns.length ? (
                  <Table head={["지표", "수식", "표시값", "내부값", "라이브러리", "오류"]}>
                    {d.calcRuns.map((c) => (
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
                ) : (
                  <p className="py-xs text-[12px] text-stone">이 실행에서는 커널 계산이 없었습니다.</p>
                )}
              </Card>
            </>
          ) : null}
        </div>
      </div>
    </AdminPage>
  );
}
