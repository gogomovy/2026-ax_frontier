"use client";
import { useMemo, useState } from "react";
import { AdminPage, C, Card, Collapse, JsonView, Loading, Mono, Select, StatusBadge, Table, duration, fmtTime, useAction, useApiData } from "@/components/admin/kit";
import { Funnel, StateDot, fmtMs, stateText, stepOf, type StepState } from "@/components/admin/flowViz";
import { Badge, Button } from "@/components/ui/primitives";
import { apiPost } from "@/lib/api-client";

interface Decision {
  id: number;
  at: string;
  agent: string;
  workflow: string | null;
  jobId: number | null;
  runId: string | null;
  decision: string;
  summary: string;
  detail: unknown;
  traceId: string | null;
}
interface ApprovalJob {
  id: number;
  workflow: string;
  createdAt: string;
  causeCount: number;
  causes: { event_id?: number; type?: string; reasons?: string[]; actor?: string; at?: string }[];
}
interface Topology {
  agents: { code: string; name: string; role: string; kind: string; enabled: boolean }[];
  workflows: { code: string; name: string; enabled: boolean; nodes: { key: string; name: string; impl: string; agent: string | null; enabled: boolean }[] }[];
  orchestrator: { policy: Record<string, unknown>; depends_on: Record<string, Record<string, string[]>> };
}
interface DecisionItem {
  id: number;
  at: string;
  agent: string;
  decision: string;
  summary: string;
  by: "llm" | "rule" | null;
  detail: unknown;
}
interface StageItem {
  nodeRunId: string | null;
  key: string;
  name: string;
  impl: string;
  agent: { code: string | null; name: string | null; kind: string; enabled: boolean } | null;
  status: string;
  ms: number | null;
  summary: string;
  error: string | null;
  decisions: DecisionItem[];
}
interface AgentRun {
  id: string;
  workflow: string;
  workflowName: string;
  status: string;
  startedAt: string;
  finishedAt: string | null;
  jobId: number | null;
  causes: { type?: string; reasons?: string[] }[];
  note: string | null;
  error: string | null;
  wallMs: number | null;
  before: DecisionItem[];
  stages: StageItem[];
  unplaced: DecisionItem[];
}
interface PipelineData {
  runs: AgentRun[];
  counts: Record<string, number>;
  workflows: { code: string; name: string }[];
}

const DECISION_TONE: Record<string, "neutral" | "info" | "attention" | "success" | "dark" | "critical"> = { hold: "attention", release: "success", detect: "info", plan: "dark", narrated: "success", rejected: "critical", route: "neutral" };
const DECISION_LABEL: Record<string, string> = { hold: "대기", release: "실행 허용", detect: "변화 판정", plan: "실행 계획", narrated: "서술 갱신", rejected: "서술 반려", route: "경로 지정" };
const byOf = (d: Decision) => ((d.detail ?? {}) as { by?: string }).by;
const AGENT_NODE = new Set(["detect_changes", "plan_run", "narrate", "critic", "embed_chunks", "extract_documents"]);
const ORCH = "__orchestrator";
const OTHER = "__unplaced";

/** 에이전트 결정 (B.30) — 실행마다 노드 순서 위에 오케스트레이터 · 변화 감지 · 플래너 · 서술 에이전트의 결정과 근거를 놓는다 */
export default function AgentDecisionsAdmin() {
  const [agent, setAgent] = useState("");
  const [wf, setWf] = useState("");
  const [limit, setLimit] = useState(8);
  const topo = useApiData<Topology>("/admin/agents/topology");
  const pipe = useApiData<PipelineData>(`/admin/agents/pipeline?limit=${limit}${wf ? `&workflow=${wf}` : ""}`, { refreshMs: 8000 });
  const dec = useApiData<{ counts: Record<string, number>; items: Decision[] }>(`/admin/agents/decisions?limit=150${agent ? `&agent=${agent}` : ""}`, { refreshMs: 10000 });
  const t = topo.data;
  const approvals = useApiData<ApprovalJob[]>("/admin/jobs/approval", { refreshMs: 10000 });
  const { run, busy } = useAction();
  const mix = useMemo(() => {
    const out: Record<string, { n: number; llm: number }> = {};
    for (const r of pipe.data?.runs ?? [])
      for (const d of [...r.before, ...r.stages.flatMap((s) => s.decisions), ...r.unplaced]) {
        const m = (out[d.decision] ??= { n: 0, llm: 0 });
        m.n += 1;
        if (d.by === "llm") m.llm += 1;
      }
    return out;
  }, [pipe.data]);
  const n = (k: string) => mix[k]?.n ?? 0;
  const by = (k: string) => (mix[k] ? `LLM ${mix[k].llm} · 규칙 ${mix[k].n - mix[k].llm}` : "기록 없음");
  const runs = pipe.data?.runs ?? [];
  return (
    <AdminPage
      title="에이전트 결정"
      description="이벤트가 오면 오케스트레이터(LLM)가 영향받는 워크플로우를 정하고, 실행 순서는 규칙으로 보장합니다. 워크플로우 안에서는 변화 감지(LLM 중요도 판단) → 화면 갱신 → 실행 계획(LLM: 서술 대상 · 검색어 · 후속 워크플로우) → 근거 · 서술 → 검증 순으로 진행합니다. LLM 판단은 허용 목록으로 검증하고, 미연결 · 실패 시 규칙으로 대체합니다. 수치는 모두 커널이 계산합니다."
      summary={
        <Card className="!mb-0" title={`결정 흐름 — 최근 ${runs.length}회 실행`}>
          <Funnel
            label="에이전트 결정 흐름"
            steps={[
              { key: "orch", title: "경로·순서 결정", value: n("route") + n("hold") + n("release"), unit: "건", hint: `경로 ${n("route")} · 대기 ${n("hold")} · 허용 ${n("release")}`, state: "done" },
              { key: "detect", title: "변화 판정", value: n("detect"), unit: "건", hint: by("detect") },
              { key: "plan", title: "실행 계획", value: n("plan"), unit: "건", hint: by("plan") },
              { key: "narrated", title: "서술 갱신", value: n("narrated"), unit: "건", hint: n("narrated") ? by("narrated") : "LLM 미연결이면 기존 문장 유지", state: n("narrated") ? "done" : "idle" },
              { key: "rejected", title: "서술 반려", value: n("rejected"), unit: "건", hint: n("rejected") ? "검증에서 막혀 기존 문장 유지" : "반려 없음", state: n("rejected") ? "warn" : "done" },
            ]}
          />
        </Card>
      }
    >
      {approvals.data?.length ? (
        <Card title={`사람 승인 대기 ${approvals.data.length}건`}>
          <p className="mb-md text-[12px] text-steel">설정 orchestrator.policy.require_approval 에 든 워크플로우는 자동 이벤트로 생긴 실행을 관리자가 승인해야 진행합니다.</p>
          <Table head={["작업", "워크플로우", "생성", "원인", ""]}>
            {approvals.data.map((j) => (
              <tr key={j.id} data-approval-job={j.id}>
                <C mono>#{j.id}</C>
                <C mono>{j.workflow}</C>
                <C>{fmtTime(j.createdAt)}</C>
                <C>
                  {j.causeCount}건 · {j.causes.slice(-3).map((c) => c.type).join(", ")}
                </C>
                <C right>
                  <span className="inline-flex gap-1">
                    <Button size="sm" variant="confirm" disabled={busy} onClick={() => run(() => apiPost(`/admin/jobs/${j.id}/approve`, {}), "승인했습니다 — 곧 실행됩니다", approvals.reload)}>
                      승인
                    </Button>
                    <Button size="sm" variant="quiet" disabled={busy} onClick={() => run(() => apiPost(`/admin/jobs/${j.id}/reject`, { reason: "관리자 반려" }), "반려했습니다", approvals.reload)}>
                      반려
                    </Button>
                  </span>
                </C>
              </tr>
            ))}
          </Table>
        </Card>
      ) : null}

      <Card
        title="실행별 결정 파이프라인"
        actions={
          <Select
            ariaLabel="워크플로우 선택"
            value={wf}
            onChange={(v) => {
              setWf(v);
              setLimit(8);
            }}
            options={[{ value: "", label: "전체 워크플로우" }, ...(pipe.data?.workflows ?? []).map((w) => ({ value: w.code, label: w.name }))]}
          />
        }
      >
        <p className="mb-md text-[12px] text-steel">
          실행의 노드 순서 위에 에이전트가 낸 결정을 놓았습니다. 단계를 누르면 그 단계의 판단 근거를 봅니다. 점 모양: 채움 = 완료 · 주황 = 축소 실행 · 빨강 = 실패 · 속 빈 점 = 대기 · 점선 = 건너뜀.
        </p>
        <Loading error={pipe.error} loading={!pipe.data && pipe.loading} />
        {pipe.data && !runs.length ? <p className="rounded-xl bg-surface-soft px-4 py-5 text-center text-[12.5px] text-steel">아직 실행 기록이 없습니다. 자료를 올리면 관련 워크플로우가 실행되고 결정이 여기에 쌓입니다.</p> : null}
        <div className="flex flex-col gap-md">
          {runs.map((r, i) => (
            <RunCard key={r.id} run={r} defaultOpen={i === 0} />
          ))}
        </div>
        {runs.length >= limit && limit < 30 ? (
          <div className="mt-md text-center">
            <Button size="sm" variant="quiet" onClick={() => setLimit((v) => Math.min(30, v + 8))}>
              이전 실행 더 보기
            </Button>
          </div>
        ) : null}
      </Card>

      <Card title="워크플로우별 에이전트 배치">
        <Loading error={topo.error} loading={!t && topo.loading} />
        {t ? (
          <div className="flex flex-col gap-md" data-agent-topology>
            {t.workflows.map((w) => (
              <div key={w.code}>
                <p className="mb-1.5 text-[12.5px] font-bold text-ink-deep">
                  {w.name} <Mono>{w.code}</Mono>
                </p>
                <ol className="flex flex-wrap items-center gap-1 text-[11.5px]">
                  {w.nodes.map((nd, i) => (
                    <li key={nd.key} className="flex items-center gap-1">
                      <span className={`rounded-lg px-2 py-1 ${!nd.enabled ? "bg-surface-soft text-stone line-through" : AGENT_NODE.has(nd.impl) ? "bg-info-soft font-bold text-primary" : "bg-surface-soft text-charcoal"}`} title={nd.agent ? `에이전트 ${nd.agent}` : nd.impl}>
                        {nd.name}
                      </span>
                      {i < w.nodes.length - 1 ? (
                        <span className="text-stone" aria-hidden="true">
                          →
                        </span>
                      ) : null}
                    </li>
                  ))}
                </ol>
              </div>
            ))}
          </div>
        ) : null}
      </Card>

      <Card title="오케스트레이터 — 워크플로우 의존 관계">
        {t ? (
          <>
            <p className="mb-md text-[12px] text-steel">
              설정 <Mono>orchestrator.policy</Mono> · 대기 간격 {String(t.orchestrator.policy.hold_sec)}초 · 최대 대기 {String(t.orchestrator.policy.max_hold_sec)}초 · {t.orchestrator.policy.enabled ? "켜짐" : "꺼짐"}
            </p>
            <Table head={["워크플로우", "먼저 끝나야 하는 워크플로우", "근거"]}>
              {Object.entries(t.orchestrator.depends_on).map(([w, ups]) => (
                <tr key={w}>
                  <C mono>{w}</C>
                  <C mono>{Object.keys(ups).join(", ")}</C>
                  <C className="text-[11.5px]">{Object.values(ups).flat().slice(0, 4).join(" · ")}</C>
                </tr>
              ))}
            </Table>
          </>
        ) : null}
      </Card>

      <Card
        title="결정 기록 전체(표)"
        actions={
          <Select
            ariaLabel="에이전트 선택"
            value={agent}
            onChange={setAgent}
            options={[{ value: "", label: "전체 에이전트" }, ...(t?.agents ?? []).filter((a) => dec.data?.counts[a.code]).map((a) => ({ value: a.code, label: `${a.name} (${dec.data?.counts[a.code] ?? 0})` }))]}
          />
        }
      >
        <Loading error={dec.error} loading={!dec.data && dec.loading} />
        <Table head={["시각", "에이전트", "워크플로우", "결정", "판단", "요약", "근거"]}>
          {(dec.data?.items ?? []).map((d) => (
            <tr key={d.id}>
              <C className="whitespace-nowrap text-[11.5px]">{fmtTime(d.at)}</C>
              <C mono className="whitespace-nowrap">{d.agent}</C>
              <C mono className="whitespace-nowrap">{d.workflow ?? "-"}</C>
              <C>
                <Badge tone={DECISION_TONE[d.decision] ?? "neutral"}>{DECISION_LABEL[d.decision] ?? d.decision}</Badge>
              </C>
              <C>{byOf(d) ? <Badge tone={byOf(d) === "llm" ? "info" : "neutral"}>{byOf(d) === "llm" ? "LLM" : "규칙"}</Badge> : <Badge>규칙</Badge>}</C>
              <C className="text-[12.5px]">{d.summary}</C>
              <C className="min-w-[200px]">
                <Collapse label="보기">
                  <JsonView value={d.detail} maxHeight={240} />
                </Collapse>
              </C>
            </tr>
          ))}
        </Table>
      </Card>
    </AdminPage>
  );
}

/** 실행 하나 — 노드 순서(스텝퍼) + 선택한 단계의 결정 */
function RunCard({ run, defaultOpen }: { run: AgentRun; defaultOpen: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  const stages = useMemo<StageItem[]>(() => {
    const out: StageItem[] = [];
    if (run.before.length) out.push({ nodeRunId: null, key: ORCH, name: "오케스트레이터", impl: "orchestrator", agent: { code: "orchestrator", name: "오케스트레이터", kind: "llm", enabled: true }, status: "succeeded", ms: null, summary: "경로 지정 · 실행 순서(대기 · 허용)", error: null, decisions: run.before });
    out.push(...run.stages);
    if (run.unplaced.length) out.push({ nodeRunId: null, key: OTHER, name: "기타 결정", impl: "other", agent: null, status: "succeeded", ms: null, summary: "노드와 연결되지 않은 기록", error: null, decisions: run.unplaced });
    return out;
  }, [run]);
  const first = stages.find((s) => s.decisions.length)?.key ?? stages[0]?.key ?? null;
  const [sel, setSel] = useState<string | null>(first);
  const cur = stages.find((s) => s.key === sel) ?? null;
  const st = stepOf(run.status);
  const total = stages.reduce((sum, s) => sum + s.decisions.length, 0);
  const cause = run.causes.map((c) => c.type).filter(Boolean).join(", ");
  return (
    <section className="rounded-2xl border border-hairline-soft bg-surface-soft/60 p-md" data-agent-run={run.id} aria-label={`${run.workflowName} 실행`}>
      <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open} className="flex w-full flex-wrap items-center gap-x-2 gap-y-1 text-left">
        <span aria-hidden="true" className="text-[11px] text-steel">
          {open ? "▾" : "▸"}
        </span>
        <b className="text-[13.5px] text-ink-deep">{run.workflowName}</b>
        <Mono>{run.workflow}</Mono>
        <StatusBadge status={run.status} />
        <span className="text-[11.5px] text-steel">
          {fmtTime(run.startedAt)} · {run.finishedAt ? (run.wallMs ? fmtMs(run.wallMs) : duration(run.startedAt, run.finishedAt)) : "진행 중"}
        </span>
        <span className="ml-auto text-[11.5px] text-steel">결정 {total}건{cause ? ` · 원인 ${cause}` : ""}</span>
      </button>
      {run.note ? <p className="mt-1 text-[11.5px] text-steel">{run.note}</p> : null}
      {run.error ? <p className="mt-1 text-[11.5px] text-critical-text">{run.error}</p> : null}
      {open ? (
        <div className="mt-sm">
          {stages.length ? (
            <ol className="grid grid-cols-[repeat(auto-fill,minmax(148px,1fr))] gap-x-2 gap-y-3" aria-label={`${run.workflowName} 노드 순서`}>
              {stages.map((s, i) => (
                <StageCell key={`${s.key}-${i}`} n={i + 1} stage={s} selected={sel === s.key} onPick={() => setSel(sel === s.key ? null : s.key)} />
              ))}
            </ol>
          ) : (
            <p className="text-[12px] text-steel">이 실행의 노드 기록이 없습니다. (준비 단계에서 멈춘 실행일 수 있습니다 — {st.label})</p>
          )}
          {cur ? <StagePanel stage={cur} /> : stages.length ? <p className="mt-sm text-[11.5px] text-steel">단계를 누르면 판단 근거를 볼 수 있습니다.</p> : null}
        </div>
      ) : null}
    </section>
  );
}

function StageCell({ n, stage, selected, onPick }: { n: number; stage: StageItem; selected: boolean; onPick: () => void }) {
  const s = stepOf(stage.status);
  const dot: Record<StepState, string> = { done: "bg-success", warn: "bg-warning", fail: "bg-critical", active: "bg-primary motion-safe:animate-pulse", idle: "border-2 border-steel bg-white", skip: "border-2 border-dashed border-stone bg-white" };
  const llm = stage.agent?.kind === "llm";
  return (
    <li className="relative pt-5">
      <span aria-hidden="true" className="absolute left-2 right-[-8px] top-[7px] h-px bg-hairline" />
      <span aria-hidden="true" className={`absolute left-0 top-0 h-[15px] w-[15px] rounded-full border-2 border-white shadow-sm ${dot[s.state]}`} />
      <button
        type="button"
        onClick={onPick}
        aria-pressed={selected}
        data-stage={stage.key}
        className={`block h-full w-full rounded-xl border px-2.5 py-2 text-left transition-colors ${selected ? "border-primary bg-info-soft" : "border-hairline bg-white hover:border-steel"}`}
      >
        <span className="flex items-start justify-between gap-1">
          <span className="text-[12px] font-bold leading-tight text-ink-deep">
            <span className="mr-1 text-[10px] font-medium text-steel">{n}</span>
            {stage.name}
          </span>
        </span>
        <span className={`mt-1 flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-[10.5px] font-bold ${stateText(s.state)}`}>
          {s.label}
          {stage.ms ? <span className="font-medium text-steel">{fmtMs(stage.ms)}</span> : null}
        </span>
        <span className="mt-1 flex flex-wrap items-center gap-1">
          {stage.agent ? (
            <span className={`rounded-md px-1.5 py-0.5 text-[10px] font-bold ${llm ? "bg-info-soft text-primary-text" : "bg-surface-soft text-charcoal"}`} title={stage.agent.name ?? stage.agent.code ?? ""}>
              {llm ? "✦ LLM" : "규칙"} 에이전트
            </span>
          ) : null}
          {stage.decisions.length ? <span className="rounded-md bg-ink-deep px-1.5 py-0.5 text-[10px] font-bold text-white">결정 {stage.decisions.length}</span> : null}
        </span>
      </button>
    </li>
  );
}

function StagePanel({ stage }: { stage: StageItem }) {
  const s = stepOf(stage.status);
  return (
    <div className="mt-sm rounded-xl border border-hairline bg-white p-md" data-stage-panel={stage.key}>
      <div className="flex flex-wrap items-center gap-xs">
        <StateDot state={s.state} />
        <b className="text-[13px] text-ink-deep">{stage.name}</b>
        <span className={`text-[11.5px] font-bold ${stateText(s.state)}`}>{s.label}</span>
        {stage.ms ? <span className="text-[11.5px] text-steel">{fmtMs(stage.ms)}</span> : null}
        {stage.agent?.name ? <span className="text-[11.5px] text-steel">· {stage.agent.name}</span> : null}
      </div>
      {stage.summary ? <p className="mt-1 text-[12px] text-charcoal">{stage.summary}</p> : null}
      {stage.error ? <p className="mt-1 text-[11.5px] text-critical-text">{stage.error}</p> : null}
      {stage.decisions.length ? (
        <ol className="mt-sm flex flex-col gap-xs" aria-label={`${stage.name}의 결정`}>
          {stage.decisions.map((d) => (
            <li key={d.id} className="rounded-xl bg-surface-soft p-sm">
              <div className="flex flex-wrap items-center gap-1.5">
                <Badge tone={DECISION_TONE[d.decision] ?? "neutral"}>{DECISION_LABEL[d.decision] ?? d.decision}</Badge>
                <Badge tone={d.by === "llm" ? "info" : "neutral"}>{d.by === "llm" ? "LLM 판단" : "규칙 판단"}</Badge>
                <span className="font-mono text-[11px] text-steel">{d.agent}</span>
                <span className="ml-auto text-[11px] text-steel">{fmtTime(d.at).slice(11)}</span>
              </div>
              <p className="mt-1 text-[12.5px] text-charcoal">{d.summary}</p>
              <div className="mt-1">
                <Collapse label="판단 근거 보기">
                  <JsonView value={d.detail} maxHeight={260} />
                </Collapse>
              </div>
            </li>
          ))}
        </ol>
      ) : (
        <p className="mt-sm text-[11.5px] text-steel">이 단계에서 기록된 에이전트 결정이 없습니다{stage.agent ? "" : " (규칙으로 수행하는 단계)"}.</p>
      )}
    </div>
  );
}
