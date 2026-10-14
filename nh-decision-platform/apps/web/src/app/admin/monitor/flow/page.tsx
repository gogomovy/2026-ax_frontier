"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { AdminPage, Card, Collapse, JsonView, Loading, Select, duration, fmtTime, useApiData } from "@/components/admin/kit";
import { Connector, Funnel, NodeStrip, Step, fmtMs, stepOf, type StepState } from "@/components/admin/flowViz";
import { BarList } from "@/components/charts/Bars";
import { EmptyState } from "@/components/ui/Layout";
import { Button } from "@/components/ui/primitives";

interface RunNode {
  key: string;
  name: string;
  status: string;
  ms: number | null;
}
interface FlowRun {
  run: string;
  workflow: string;
  status: string;
  startedAt: string;
  finishedAt: string | null;
  published: string[];
  unpublished?: string[];
  nodes?: RunNode[];
  note?: string | null;
  error?: string | null;
}
interface Pending {
  job: number;
  workflow: string;
  status: string;
  runAfter: string;
}
interface Matched {
  workflow?: string;
  reasons?: string[];
  note?: string;
  blocked?: string;
}
interface FlowEvent {
  id: number;
  type: string;
  payload: Record<string, unknown>;
  actor: string | null;
  at: string;
  dispatchedAt: string | null;
  matched: Matched[];
  runs: FlowRun[];
  pending: Pending[];
}
interface Lane {
  workflow: string;
  reasons: string[];
  blocked?: string;
  runs: FlowRun[];
  jobs: Pending[];
}

const TYPE_LABEL: Record<string, string> = {
  "dataset.committed": "데이터셋 확정",
  "dataset.deleted": "데이터셋 삭제",
  "document.ingested": "문서 등록",
  "document.deleted": "문서 삭제",
  "rule.changed": "규칙 변경",
  "goal.confirmed": "경영목표 확정",
  "config.changed": "설정 변경",
  "contract.changed": "컬럼 정의서 변경",
  "ontology.changed": "스키마 변경",
  "kb.indexed": "질문하기 색인 갱신",
  "request.created": "분석 요청",
  manual: "수동 실행",
  schedule: "정기 실행",
};

/** 데이터 흐름 — 이벤트 → 분배(매칭 워크플로우) → 작업 → 실행(노드) → 게시 산출물 (ADM-11) */
export default function FlowMonitor() {
  const data = useApiData<FlowEvent[]>("/admin/monitor/flow?limit=80", { refreshMs: 4000 });
  const [type, setType] = useState("");
  const all = useMemo(() => data.data ?? [], [data.data]);
  const stats = useMemo(() => {
    const runs = all.flatMap((e) => e.runs);
    const by = (s: string) => runs.filter((r) => r.status === s).length;
    return {
      byType: Object.entries(all.reduce<Record<string, number>>((m, e) => ((m[e.type] = (m[e.type] ?? 0) + 1), m), {})).sort((a, b) => b[1] - a[1]),
      dispatched: all.filter((e) => e.dispatchedAt).length,
      waiting: all.filter((e) => !e.dispatchedAt).length,
      matched: all.filter((e) => e.matched.some((m) => m.workflow && !m.workflow.startsWith("("))).length,
      noMatch: all.filter((e) => e.dispatchedAt && !e.matched.some((m) => m.workflow)).length,
      runs: runs.length,
      ok: by("succeeded"),
      degraded: by("degraded"),
      failed: by("failed"),
      running: by("running"),
      publishedRuns: runs.filter((r) => r.published.length).length,
      artifacts: new Set(runs.flatMap((r) => r.published)).size,
    };
  }, [all]);
  const rows = all.filter((e) => !type || e.type === type);
  // 최근 이벤트 몇 건만 펼치고 나머지는 한 줄 요약 — 80건을 모두 펼치면 화면이 수만 px 로 길어진다
  const [shown, setShown] = useState(PAGE);
  const [open, setOpen] = useState<Record<number, boolean>>({});
  const isOpen = (id: number, i: number) => open[id] ?? i < OPEN_FIRST;
  const runState: StepState = stats.failed ? "fail" : stats.degraded ? "warn" : stats.running ? "active" : "done";
  return (
    <AdminPage
      title="데이터 흐름"
      description="데이터 · 문서 · 규칙 · 목표가 바뀔 때마다 어떤 워크플로가 왜 실행됐는지(트리거 또는 계보)를 이벤트 → 분배 → 작업 → 실행(노드) → 게시 순서로 보여 줍니다. 관련 없는 워크플로는 실행되지 않습니다. 4초마다 갱신됩니다."
      actions={
        <Button size="sm" variant="quiet" onClick={data.reload}>
          새로고침
        </Button>
      }
      summary={
        <div className="grid grid-cols-1 gap-lg xl:grid-cols-[1.9fr_1fr]">
          <Card className="!mb-0" title="처리 단계 요약 (최근 80건)">
            <Funnel
              label="데이터 흐름 처리 단계"
              steps={[
                { key: "events", title: "변경 이벤트", value: all.length, unit: "건", hint: "최근 80건 기준" },
                { key: "dispatch", title: "분배", value: stats.dispatched, unit: "건", hint: stats.waiting ? `워커 대기 ${stats.waiting}건` : "모두 처리됨", state: stats.waiting ? "warn" : "done" },
                { key: "match", title: "워크플로우 매칭", value: stats.matched, unit: "건", hint: `관련 없음 ${stats.noMatch}건 — 실행 안 함`, state: "done" },
                { key: "runs", title: "실행", value: stats.runs, unit: "건", hint: `성공 ${stats.ok} · 축소 ${stats.degraded} · 실패 ${stats.failed}${stats.running ? ` · 진행 ${stats.running}` : ""}`, state: runState },
                { key: "publish", title: "산출물 게시", value: stats.artifacts, unit: "종", hint: `게시한 실행 ${stats.publishedRuns}건`, state: stats.publishedRuns ? "done" : "idle" },
              ]}
            />
          </Card>
          <Card className="!mb-0">
            <BarList title="이벤트 종류별 건수" items={stats.byType.map(([k, v]) => ({ label: TYPE_LABEL[k] ?? k, value: v, display: `${v}건` }))} />
          </Card>
        </div>
      }
    >
      <Loading error={data.error} loading={!data.data && data.loading} />
      <div className="mb-md flex flex-wrap items-center gap-xs">
        <Select
          className="w-[220px]"
          ariaLabel="이벤트 종류 고르기"
          value={type}
          onChange={(v) => {
            setType(v);
            setShown(PAGE);
          }}
          options={[{ value: "", label: "종류 전체" }, ...stats.byType.map(([k]) => ({ value: k, label: TYPE_LABEL[k] ?? k }))]}
        />
        <span className="text-[12px] text-stone">
          {rows.length}건 중 {Math.min(shown, rows.length)}건 표시
        </span>
        <Button size="sm" variant="quiet" onClick={() => setOpen(Object.fromEntries(rows.slice(0, shown).map((e) => [e.id, true])))}>
          모두 펼치기
        </Button>
        <Button size="sm" variant="quiet" onClick={() => setOpen(Object.fromEntries(rows.map((e) => [e.id, false])))}>
          모두 접기
        </Button>
        <Legend />
      </div>
      {data.data && !rows.length ? <EmptyState title="변경 이벤트가 없습니다" description="자료를 반영하거나 규칙 · 문서를 바꾸면 여기에 흐름이 나타납니다." /> : null}
      <div className="flex flex-col gap-xs">
        {rows.slice(0, shown).map((e, i) => (
          <EventFlow key={e.id} e={e} open={isOpen(e.id, i)} onToggle={() => setOpen((o) => ({ ...o, [e.id]: !isOpen(e.id, i) }))} />
        ))}
      </div>
      {rows.length > shown ? (
        <div className="mt-md flex justify-center">
          <Button size="sm" variant="secondary" onClick={() => setShown((n) => n + PAGE)}>
            이벤트 더 보기 ({rows.length - shown}건 남음)
          </Button>
        </div>
      ) : null}
    </AdminPage>
  );
}

function Legend() {
  const items: [string, StepState][] = [
    ["완료", "done"],
    ["진행·대기", "active"],
    ["축소 실행·승인 대기", "warn"],
    ["실패", "fail"],
  ];
  const dot: Record<string, string> = { done: "bg-success", active: "bg-primary", warn: "bg-warning", fail: "bg-critical" };
  return (
    <ul className="ml-auto flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-steel" aria-label="상태 표시 설명">
      {items.map(([label, s]) => (
        <li key={s} className="inline-flex items-center gap-1">
          <span aria-hidden="true" className={`inline-block h-2.5 w-2.5 rounded-full ${dot[s]}`} />
          {label}
        </li>
      ))}
      <li className="inline-flex items-center gap-1">
        <span aria-hidden="true" className="inline-block h-2.5 w-2.5 rounded-full border-2 border-steel bg-white" />
        기록 없음
      </li>
    </ul>
  );
}

function lanesOf(e: FlowEvent): Lane[] {
  const m = new Map<string, Lane>();
  const get = (wf: string) => {
    let l = m.get(wf);
    if (!l) {
      l = { workflow: wf, reasons: [], runs: [], jobs: [] };
      m.set(wf, l);
    }
    return l;
  };
  for (const x of e.matched) {
    if (!x.workflow || x.workflow.startsWith("(")) continue;
    const l = get(x.workflow);
    l.reasons = x.reasons ?? [];
    if (x.blocked) l.blocked = x.blocked;
  }
  for (const r of e.runs) get(r.workflow).runs.push(r);
  for (const p of e.pending) get(p.workflow).jobs.push(p);
  return [...m.values()];
}

const PAGE = 15; // 한 번에 보여 줄 이벤트 수
const OPEN_FIRST = 3; // 처음부터 펼쳐 둘 최근 이벤트 수

/** 접힌 이벤트의 한 줄 요약 — 실행 상태별 건수 */
function runTally(e: FlowEvent): { state: StepState; text: string } {
  const by = (s: string) => e.runs.filter((r) => r.status === s).length;
  const parts = [
    [by("succeeded"), "성공"],
    [by("degraded"), "축소"],
    [by("failed"), "실패"],
    [by("running"), "진행"],
    [e.pending.length, "대기"],
  ].filter(([n]) => n) as [number, string][];
  const state: StepState = by("failed") ? "fail" : by("degraded") ? "warn" : by("running") || e.pending.length || !e.dispatchedAt ? "active" : e.runs.length ? "done" : "skip";
  return { state, text: parts.length ? parts.map(([n, l]) => `${l} ${n}`).join(" · ") : e.dispatchedAt ? "실행 없음" : "분배 대기" };
}

const TALLY_DOT: Record<StepState, string> = { done: "bg-success", active: "bg-primary", warn: "bg-warning", fail: "bg-critical", idle: "border-2 border-steel bg-white", skip: "border-2 border-steel bg-white" };

function EventFlow({ e, open, onToggle }: { e: FlowEvent; open: boolean; onToggle: () => void }) {
  const lanes = lanesOf(e);
  const tally = runTally(e);
  const header = (
    <button type="button" onClick={onToggle} aria-expanded={open} className="flex w-full flex-wrap items-center gap-x-2 gap-y-1 rounded-lg text-left">
      <span aria-hidden="true" className="w-3 text-[11px] text-steel">
        {open ? "▾" : "▸"}
      </span>
      <b className="text-[12.5px] text-ink-deep">#{e.id}</b>
      <span className="rounded bg-surface-soft px-1.5 py-0.5 text-[11px] font-bold text-charcoal">{TYPE_LABEL[e.type] ?? e.type}</span>
      <span className="min-w-0 max-w-[460px] truncate text-[12px] text-charcoal">{describe(e)}</span>
      <span className="text-[11px] text-steel">{fmtTime(e.at)}</span>
      <span className="ml-auto inline-flex items-center gap-1.5 text-[11.5px] text-steel">
        <span aria-hidden="true" className={`inline-block h-2.5 w-2.5 rounded-full ${TALLY_DOT[tally.state]}`} />
        {lanes.filter((l) => !l.blocked).length ? `워크플로우 ${lanes.filter((l) => !l.blocked).length}개 · ` : ""}
        {tally.text}
      </span>
    </button>
  );
  if (!open)
    return (
      <Card className="!mb-0 !px-base !py-2.5">
        <div data-flow-event={e.id}>{header}</div>
      </Card>
    );
  // "(디스패치 실패)" · "(재시도 n/5)" 같은 분배 문제 표시
  const trouble = e.matched.find((x) => x.workflow?.startsWith("("));
  const actionable = lanes.filter((l) => !l.blocked || l.runs.length || l.jobs.length);
  const dispatch: { state: StepState; label: string; text: string } = !e.dispatchedAt
    ? trouble
      ? { state: "warn", label: "재시도 중", text: trouble.blocked ?? trouble.workflow ?? "" }
      : { state: "active", label: "대기", text: "워커가 아직 분배하지 않았습니다" }
    : trouble
      ? { state: "fail", label: "분배 실패", text: trouble.blocked ?? "" }
      : actionable.length
        ? { state: "done", label: "완료", text: `${actionable.length}개 워크플로우에 연결` }
        : { state: "skip", label: "관련 없음", text: lanes.length ? "연쇄 안전장치로 막힘" : "트리거 · 계보에 맞는 워크플로우 없음 — 실행하지 않음" };
  return (
    <Card className="!mb-0 !p-base">
      <div className="mb-sm">{header}</div>
      <div className="grid grid-cols-1 gap-sm lg:grid-cols-[250px_minmax(0,1fr)] lg:gap-0" data-flow-event={e.id}>
        <div className="flex flex-col gap-xs lg:pr-0">
          <Step title={`① 이벤트 #${e.id}`} state="done" stateLabel={TYPE_LABEL[e.type] ?? e.type}>
            <span className="block break-words font-bold text-ink-deep">{describe(e)}</span>
            <span className="block text-[11px] text-steel">
              {fmtTime(e.at)} · {e.actor ?? "시스템"}
            </span>
          </Step>
          <Connector vertical />
          <Step title="② 분배" state={dispatch.state} stateLabel={dispatch.label}>
            <span className="block text-[11.5px]">{dispatch.text}</span>
            {e.dispatchedAt ? <span className="block text-[11px] text-steel">{fmtTime(e.dispatchedAt)}</span> : null}
          </Step>
        </div>
        <div className="flex min-w-0 gap-0 lg:pl-0">
          <Connector className="!hidden !w-7 lg:!flex" />
          <div className="flex min-w-0 flex-1 flex-col gap-xs">
            {lanes.length ? lanes.map((l) => <LaneRow key={l.workflow} lane={l} />) : <p className="rounded-xl bg-surface-soft px-3 py-2.5 text-[12px] text-steel">이 이벤트로 시작된 실행이 없습니다.</p>}
          </div>
        </div>
      </div>
      <div className="mt-xs">
        <Collapse label="이벤트 원본(JSON)">
          <JsonView value={e.payload} maxHeight={160} />
        </Collapse>
      </div>
    </Card>
  );
}

function LaneRow({ lane }: { lane: Lane }) {
  const job = lane.jobs[0];
  const jobStep = job ? stepOf(job.status) : lane.runs.length ? { state: "done" as StepState, label: "완료" } : lane.blocked ? { state: "skip" as StepState, label: "막힘" } : { state: "idle" as StepState, label: "기록 없음" };
  return (
    <div className="rounded-xl bg-surface-soft p-2.5" data-flow-lane={lane.workflow}>
      <p className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
        <b className="text-[12.5px] text-ink-deep">③ {lane.workflow}</b>
        {lane.reasons.length ? <span className="text-[11px] text-steel">{lane.reasons.join(" · ")}</span> : null}
      </p>
      {lane.blocked ? <p className="mt-0.5 text-[11.5px] text-attention">{lane.blocked}</p> : null}
      <div className="mt-1.5 flex flex-col gap-xs">
        {lane.runs.length ? (
          lane.runs.map((r, i) => <RunRow key={r.run} run={r} jobStep={i === 0 ? { ...jobStep, job } : null} />)
        ) : (
          <div className="flex flex-wrap items-stretch gap-1">
            <Step title="작업" state={jobStep.state} stateLabel={jobStep.label} className="w-full sm:w-[190px]">
              {job ? <span className="text-[11.5px]">실행 예정 {fmtTime(job.runAfter)}</span> : <span className="text-[11.5px] text-steel">작업 기록 없음</span>}
            </Step>
          </div>
        )}
      </div>
    </div>
  );
}

function RunRow({ run, jobStep }: { run: FlowRun; jobStep: { state: StepState; label: string; job?: Pending } | null }) {
  const st = stepOf(run.status);
  const nodes = run.nodes ?? [];
  const nodeState: StepState = nodes.some((n) => n.status === "failed") ? "fail" : nodes.some((n) => n.status === "degraded") ? "warn" : nodes.length ? "done" : "idle";
  const unpublished = run.unpublished ?? [];
  const pubState: StepState = run.published.length ? "done" : run.status === "failed" ? "fail" : run.status === "running" ? "active" : "idle";
  const why = run.error ?? run.note ?? null;
  return (
    <div className="flex flex-col gap-1 md:flex-row md:flex-wrap md:items-stretch" data-flow-run={run.run}>
      {jobStep ? (
        <>
          <Step title="작업" state={jobStep.state} stateLabel={jobStep.label} className="md:w-[130px]">
            {jobStep.job ? <span className="text-[11px]">예정 {fmtTime(jobStep.job.runAfter).slice(11)}</span> : <span className="text-[11px] text-steel">#{run.run.slice(0, 6)}</span>}
          </Step>
          <Connector className="hidden md:flex" />
        </>
      ) : null}
      <Step title="④ 실행" state={st.state} stateLabel={st.label} className="md:w-[210px]">
        <Link href={`/admin/monitor/runs?run=${run.run}`} className="font-bold text-primary underline-offset-2 hover:underline">
          실행 상세 보기
        </Link>
        <span className="block text-[11px] text-steel">
          {fmtTime(run.startedAt).slice(5)} · {run.finishedAt ? duration(run.startedAt, run.finishedAt) : "진행 중"}
        </span>
        {why ? <span className={`mt-0.5 block text-[11px] leading-snug ${run.error ? "text-critical-text" : "text-steel"}`}>{why}</span> : null}
      </Step>
      <Connector className="hidden md:flex" />
      <Step title="⑤ 노드" state={nodeState} className="md:min-w-[170px] md:flex-1">
        {nodes.length ? <NodeStrip nodes={nodes} label={`${run.workflow} 노드 실행 상태`} /> : <span className="text-[11px] text-steel">노드 기록 없음</span>}
        {nodes.length ? (
          <div className="mt-1">
            <Collapse label="노드별 보기">
              <ul className="grid grid-cols-1 gap-x-3 gap-y-0.5 sm:grid-cols-2">
                {nodes.map((n) => {
                  const s = stepOf(n.status);
                  return (
                    <li key={n.key} className="flex items-baseline justify-between gap-2 text-[11px]">
                      <span className="truncate text-charcoal">{n.name}</span>
                      <span className="shrink-0 text-steel">
                        {s.label}
                        {n.ms ? ` · ${fmtMs(n.ms)}` : ""}
                      </span>
                    </li>
                  );
                })}
              </ul>
            </Collapse>
          </div>
        ) : null}
      </Step>
      <Connector className="hidden md:flex" />
      <Step title="⑥ 게시" state={pubState} stateLabel={run.published.length ? `${run.published.length}종` : run.status === "failed" ? "반영 안 됨" : "변경 없음"} className="md:min-w-[170px] md:flex-1">
        {run.published.length ? (
          <ul className="flex flex-wrap gap-1" aria-label="게시한 산출물">
            {run.published.slice(0, 8).map((k) => (
              <li key={k} className="rounded bg-surface-soft px-1.5 py-0.5 font-mono text-[10.5px] text-charcoal">
                {k}
              </li>
            ))}
            {run.published.length > 8 ? <li className="text-[10.5px] text-steel">외 {run.published.length - 8}종</li> : null}
          </ul>
        ) : run.status === "failed" && unpublished.length ? (
          <span className="text-[11px] text-critical-text">실패로 반영하지 못함 {unpublished.length}종</span>
        ) : (
          <span className="text-[11px] text-steel">{run.status === "running" ? "게시 전" : "화면에 바뀐 내용 없음"}</span>
        )}
      </Step>
    </div>
  );
}

function describe(e: FlowEvent): string {
  const p = e.payload as Record<string, string | number | boolean | undefined>;
  if (e.type.startsWith("dataset.")) return `${p.dataset} v${p.version}${p.rollback ? " (되돌리기)" : ""} · ${p.origin === "bank" ? "당행" : "외부"}${p.rows !== undefined ? ` · ${p.rows}행` : ""}`;
  if (e.type.startsWith("document.")) return `${p.doc_code} · ${p.doc_class} · ${p.origin === "bank" ? "당행" : "외부"}`;
  if (e.type === "rule.changed") return `${p.rule} v${p.version}`;
  if (e.type === "goal.confirmed") return `${p.goal ?? ""} · ${p.mode ?? ""}${p.value !== undefined ? ` · ${p.value}` : ""}`;
  if (e.type === "manual") return `${p.workflow} · ${p.reason ?? ""}`;
  if (e.type === "schedule") return `${p.workflow} · cron ${p.cron}`;
  return `${p.kind ?? ""} ${p.code ?? p.key ?? ""}`.trim() || (TYPE_LABEL[e.type] ?? e.type);
}
