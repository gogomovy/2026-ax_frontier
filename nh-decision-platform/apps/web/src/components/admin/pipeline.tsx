"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Collapse, JsonView, fmtTime, useApiData } from "@/components/admin/kit";
import { Badge } from "@/components/ui/primitives";
import { apiGetC } from "@/lib/api-client";

/* ───────────── 타입 (GET /admin/pipeline · 설계 §19.22) ───────────── */
export interface PipeStage {
  key: string;
  label: string;
  impls: string[];
}
export interface PipeSource {
  id: string;
  kind: "dataset" | "doc_class" | "rule" | "event" | "cron" | "any" | "setting";
  code: string;
  label: string;
  origin?: string;
  version?: number | null;
  committedAt?: string | null;
  rows?: number | null;
  dataOrigin?: string | null;
  documents?: number;
}
export interface PipeAgent {
  code: string;
  name: string;
  kind: string;
  model: string | null;
  enabled: boolean;
}
export interface PipeNode {
  key: string;
  name: string;
  impl: string;
  stage: string;
  enabled: boolean;
  seq: number;
  agent: PipeAgent | null;
  last: { status: string; ms: number | null; summary: string; by: string | null; model: string | null } | null;
  live: { status: string; ms: number | null } | null;
}
export interface PipeWorkflow {
  code: string;
  name: string;
  description: string;
  enabled: boolean;
  inputs: { source: string; via: "trigger" | "lineage" | "evidence"; trigger?: string }[];
  nodes: PipeNode[];
  outputs: string[];
  lastRun: { id: string; status: string; startedAt: string; finishedAt: string | null; causes: { type?: string; reasons?: string[] }[]; wallMs: number | null } | null;
  live: { status: string; runId?: string; startedAt?: string; done?: number; total?: number; currentNode?: string | null; runAfter?: string } | null;
  jobs: { id: number; status: string; runAfter: string; causes: number }[];
}
export interface PipeOutput {
  id: string;
  kind: "artifact" | "report" | "mart";
  key: string;
  label: string;
  screens: string[];
  updatedAt: string | null;
  workflowRun: string | null;
  rows?: number | null;
}
export interface PipeScreen {
  code: string;
  label: string;
  path: string;
  section: string;
}
export interface PipelineData {
  stages: PipeStage[];
  sources: PipeSource[];
  workflows: PipeWorkflow[];
  outputs: PipeOutput[];
  screens: PipeScreen[];
}

/* ───────────── 공통 표시 ───────────── */
export const STATUS_KO: Record<string, string> = { succeeded: "성공", degraded: "축소 실행", skipped: "건너뜀", failed: "실패", running: "실행 중", queued: "대기", approval: "승인 대기", done: "완료" };
const STATUS_BAR: Record<string, string> = { succeeded: "bg-success", degraded: "bg-warning", skipped: "bg-hairline", failed: "bg-critical", running: "bg-primary", queued: "bg-steel", approval: "bg-attention" };
const STATUS_TONE: Record<string, "success" | "attention" | "critical" | "neutral" | "info"> = { succeeded: "success", degraded: "attention", skipped: "neutral", failed: "critical", running: "info", queued: "neutral", approval: "attention" };
const KIND_KO: Record<string, string> = { dataset: "데이터셋", doc_class: "문서 분류", rule: "판정 규칙", event: "이벤트", cron: "정기 실행", any: "전체 변경", setting: "설정" };
const COMPACT = new Set(["rule", "event", "cron", "any", "setting"]);
const OUT_KO: Record<string, string> = { artifact: "화면 산출물", report: "보고서", mart: "정의서 mart" };

export function StatusPill({ status }: { status?: string | null }) {
  if (!status) return <Badge>실행 없음</Badge>;
  return <Badge tone={STATUS_TONE[status] ?? "neutral"}>{STATUS_KO[status] ?? status}</Badge>;
}

export function AgentBadge({ agent }: { agent: PipeAgent | null }) {
  if (!agent) return null;
  if (agent.kind === "llm")
    return (
      <span className="inline-flex items-center gap-1 rounded-md bg-info-soft px-1.5 py-0.5 text-[10.5px] font-bold text-primary-text" title={`에이전트 ${agent.name}`}>
        <span aria-hidden="true">✦</span> LLM · {agent.model ?? "미연결"}
      </span>
    );
  return (
    <span className="inline-flex items-center gap-1 rounded-md bg-surface-soft px-1.5 py-0.5 text-[10.5px] font-bold text-charcoal" title={`에이전트 ${agent.name}`}>
      규칙 에이전트 · {agent.name}
    </span>
  );
}

function ms(v?: number | null) {
  if (v === null || v === undefined) return "";
  return v < 1000 ? `${v}ms` : `${(v / 1000).toFixed(1)}s`;
}

/* ───────────── 전체 지도 (PIPE-01) ───────────── */
type Edge = { from: string; to: string; dashed?: boolean };

function useGraph(d: PipelineData) {
  return useMemo(() => {
    const edges: Edge[] = [];
    for (const w of d.workflows) {
      for (const i of w.inputs) edges.push({ from: i.source, to: `wf:${w.code}`, dashed: i.via !== "trigger" });
      for (const o of w.outputs) edges.push({ from: `wf:${w.code}`, to: o });
    }
    const outIds = new Set(d.outputs.map((o) => o.id));
    for (const o of d.outputs) for (const s of o.screens) if (outIds.has(o.id)) edges.push({ from: o.id, to: `sc:${s}` });
    const fwd = new Map<string, string[]>();
    const back = new Map<string, string[]>();
    for (const e of edges) {
      fwd.set(e.from, [...(fwd.get(e.from) ?? []), e.to]);
      back.set(e.to, [...(back.get(e.to) ?? []), e.from]);
    }
    return { edges, fwd, back };
  }, [d]);
}

function related(id: string | null, fwd: Map<string, string[]>, back: Map<string, string[]>): Set<string> | null {
  if (!id) return null;
  const out = new Set<string>([id]);
  const walk = (start: string, m: Map<string, string[]>) => {
    const stack = [start];
    while (stack.length) {
      const x = stack.pop() as string;
      for (const y of m.get(x) ?? []) if (!out.has(y)) {
        out.add(y);
        stack.push(y);
      }
    }
  };
  walk(id, fwd);
  walk(id, back);
  return out;
}

export function PipelineMap({ data, onOpenWorkflow }: { data: PipelineData; onOpenWorkflow: (code: string) => void }) {
  const { edges, fwd, back } = useGraph(data);
  const [sel, setSel] = useState<string | null>(null);
  const rel = useMemo(() => related(sel, fwd, back), [sel, fwd, back]);
  const wrap = useRef<HTMLDivElement>(null);
  const [paths, setPaths] = useState<{ d: string; on: boolean; dashed?: boolean; key: string }[]>([]);
  const [size, setSize] = useState({ w: 0, h: 0 });

  const measure = useCallback(() => {
    const el = wrap.current;
    if (!el) return;
    const box = el.getBoundingClientRect();
    if (box.width < 1000) {
      setPaths([]);
      return;
    }
    const pos = new Map<string, DOMRect>();
    el.querySelectorAll<HTMLElement>("[data-pipe-id]").forEach((n) => pos.set(n.dataset.pipeId as string, n.getBoundingClientRect()));
    const out: { d: string; on: boolean; dashed?: boolean; key: string }[] = [];
    for (const e of edges) {
      const a = pos.get(e.from);
      const b = pos.get(e.to);
      if (!a || !b) continue;
      const x1 = a.right - box.left;
      const y1 = a.top + a.height / 2 - box.top;
      const x2 = b.left - box.left;
      const y2 = b.top + b.height / 2 - box.top;
      const c = Math.max(24, (x2 - x1) / 2);
      out.push({ key: `${e.from}>${e.to}`, d: `M${x1},${y1} C${x1 + c},${y1} ${x2 - c},${y2} ${x2},${y2}`, on: !rel || (rel.has(e.from) && rel.has(e.to)), dashed: e.dashed });
    }
    setSize({ w: box.width, h: el.scrollHeight });
    setPaths(out);
  }, [edges, rel]);

  // 배치가 끝난 다음 프레임에 카드 위치를 재서 연결선을 그린다(크기 변화 · 데이터 갱신 · 선택 시)
  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    let raf = window.requestAnimationFrame(measure);
    const ro = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(() => {
      window.cancelAnimationFrame(raf);
      raf = window.requestAnimationFrame(measure);
    });
    ro?.observe(el);
    return () => {
      window.cancelAnimationFrame(raf);
      ro?.disconnect();
    };
  }, [measure, data]);

  const dim = (id: string) => (rel && !rel.has(id) ? "opacity-35" : "");
  const pick = (id: string) => setSel((s) => (s === id ? null : id));
  const label = (id: string): string => {
    if (id.startsWith("wf:")) return data.workflows.find((w) => `wf:${w.code}` === id)?.name ?? id;
    if (id.startsWith("sc:")) return data.screens.find((s) => `sc:${s.code}` === id)?.label ?? id;
    return data.sources.find((s) => s.id === id)?.label ?? data.outputs.find((o) => o.id === id)?.label ?? id;
  };
  const groups: [string, PipeSource[]][] = [
    ["당행 데이터셋", data.sources.filter((s) => s.kind === "dataset" && s.origin === "bank")],
    ["외부 데이터셋", data.sources.filter((s) => s.kind === "dataset" && s.origin !== "bank")],
    ["문서 분류", data.sources.filter((s) => s.kind === "doc_class")],
    ["판정 규칙", data.sources.filter((s) => s.kind === "rule")],
    ["이벤트 · 정기 실행 · 설정", data.sources.filter((s) => ["event", "cron", "any", "setting"].includes(s.kind))],
  ];
  const usedScreens = new Set(data.outputs.flatMap((o) => o.screens));

  return (
    <div>
      <p className="mb-md text-[12px] text-steel">
        항목을 누르면 연결된 원천 · 워크플로우 · 산출물 · 화면만 강조됩니다. 실선 = 트리거(명시 연결), 점선 = 계보(지표 · 표가 읽는 데이터셋) · 근거 문서. 워크플로우의 <b>파이프라인 보기</b>는 노드 단위 흐름으로 이동합니다.
      </p>
      {sel ? <ConnectionList id={sel} label={label} fwd={fwd} back={back} onClear={() => setSel(null)} /> : null}
      <div ref={wrap} className="relative" data-pipeline-map>
        <svg aria-hidden="true" className="pointer-events-none absolute left-0 top-0" width={size.w} height={size.h}>
          {paths.map((p) => (
            <path key={p.key} d={p.d} fill="none" strokeWidth={p.on && rel ? 2 : 1.2} strokeDasharray={p.dashed ? "4 3" : undefined} className={p.on ? (rel ? "stroke-primary" : "stroke-chart-axis") : "stroke-chart-grid"} />
          ))}
        </svg>
        <div className="relative grid grid-cols-1 gap-lg lg:grid-cols-[1.1fr_1.2fr_1.1fr_0.8fr] lg:gap-[56px]">
          <Column title="① 원천" hint="데이터 · 문서 · 규칙 · 이벤트">
            {groups.map(([g, items]) =>
              items.length ? (
                <div key={g} className="mb-sm">
                  <p className="mb-1 text-[10.5px] font-bold text-steel">
                    {g} {items.length}
                  </p>
                  <ul className={COMPACT.has(items[0].kind) ? "grid grid-cols-2 gap-1" : "flex flex-col gap-1"}>
                    {items.map((s) =>
                      COMPACT.has(s.kind) ? (
                        <li key={s.id}>
                          <MapItem id={s.id} selected={sel === s.id} className={`${dim(s.id)} !py-1`} onClick={() => pick(s.id)} title={s.code}>
                            <span className="block truncate text-[11px] font-bold text-ink-deep">{s.label}</span>
                          </MapItem>
                        </li>
                      ) : (
                      <li key={s.id}>
                        <MapItem id={s.id} selected={sel === s.id} className={dim(s.id)} onClick={() => pick(s.id)}>
                          <span className="block truncate font-bold text-ink-deep">{s.label}</span>
                          <span className="block truncate font-mono text-[10px] text-stone">
                            {s.code}
                            {s.kind === "dataset" ? ` · v${s.version ?? "-"}${s.rows !== undefined && s.rows !== null ? ` · ${s.rows.toLocaleString()}행` : ""}${s.dataOrigin === "simulation" ? " · 시뮬레이션" : ""}` : ""}
                            {s.kind === "doc_class" ? ` · 문서 ${s.documents ?? 0}건` : ""}
                          </span>
                        </MapItem>
                      </li>
                      ),
                    )}
                  </ul>
                </div>
              ) : null,
            )}
          </Column>
          <Column title="② 워크플로우" hint="이벤트가 오면 관련 워크플로우만 실행">
            <ul className="flex flex-col gap-sm">
              {data.workflows.map((w) => {
                const id = `wf:${w.code}`;
                const llm = w.nodes.filter((n) => n.agent?.kind === "llm").length;
                return (
                  <li key={w.code}>
                    <MapItem id={id} selected={sel === id} className={`${dim(id)} !p-sm`} onClick={() => pick(id)}>
                      <span className="flex flex-wrap items-center gap-1">
                        <span className="font-bold text-ink-deep">{w.name}</span>
                        {w.live ? <LiveDot label={STATUS_KO[w.live.status] ?? w.live.status} /> : null}
                      </span>
                      <span className="mt-0.5 flex flex-wrap items-center gap-1 text-[10.5px] text-steel">
                        <StatusPill status={w.lastRun?.status} /> 노드 {w.nodes.length} · LLM 에이전트 {llm} · 입력 {w.inputs.length} · 산출물 {w.outputs.length}
                      </span>
                      <span className="mt-0.5 block text-[10.5px] text-stone">최근 {fmtTime(w.lastRun?.finishedAt ?? w.lastRun?.startedAt)}{w.lastRun?.wallMs ? ` · ${ms(w.lastRun.wallMs)}` : ""}</span>
                    </MapItem>
                    <button type="button" onClick={() => onOpenWorkflow(w.code)} className="mt-0.5 text-[11px] font-bold text-primary-text underline-offset-2 hover:underline">
                      {w.name} 파이프라인 보기 →
                    </button>
                  </li>
                );
              })}
            </ul>
          </Column>
          <Column title="③ 산출물" hint="화면 산출물 · 보고서 · 정의서 mart">
            {(["artifact", "report", "mart"] as const).map((k) => {
              const items = data.outputs.filter((o) => o.kind === k);
              return items.length ? (
                <div key={k} className="mb-sm">
                  <p className="mb-1 text-[10.5px] font-bold text-steel">
                    {OUT_KO[k]} {items.length}
                  </p>
                  <ul className="flex flex-col gap-1">
                    {items.map((o) => (
                      <li key={o.id}>
                        <MapItem id={o.id} selected={sel === o.id} className={dim(o.id)} onClick={() => pick(o.id)}>
                          <span className="block truncate font-bold text-ink-deep">{o.label}</span>
                          <span className="block truncate font-mono text-[10px] text-stone">
                            {o.key}
                            {o.rows !== undefined && o.rows !== null ? ` · ${o.rows}행` : ""} · {fmtTime(o.updatedAt)}
                          </span>
                        </MapItem>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null;
            })}
          </Column>
          <Column title="④ 업무 화면" hint="산출물을 읽는 화면">
            <ul className="flex flex-col gap-1">
              {data.screens
                .filter((s) => usedScreens.has(s.code))
                .map((s) => {
                  const id = `sc:${s.code}`;
                  return (
                    <li key={s.code}>
                      <MapItem id={id} selected={sel === id} className={dim(id)} onClick={() => pick(id)}>
                        <span className="block truncate font-bold text-ink-deep">{s.label}</span>
                        <span className="block truncate text-[10px] text-stone">
                          {s.section} · {s.path}
                        </span>
                      </MapItem>
                    </li>
                  );
                })}
            </ul>
          </Column>
        </div>
      </div>
    </div>
  );
}

function Column({ title, hint, children }: { title: string; hint: string; children: React.ReactNode }) {
  return (
    <section aria-label={title}>
      <h3 className="mb-1 text-[13px] font-bold text-ink-deep">{title}</h3>
      <p className="mb-sm text-[11px] text-stone">{hint}</p>
      {children}
    </section>
  );
}

function MapItem({ id, selected, className, onClick, children, title }: { id: string; selected: boolean; className?: string; onClick: () => void; children: React.ReactNode; title?: string }) {
  return (
    <button
      type="button"
      title={title}
      data-pipe-id={id}
      aria-pressed={selected}
      onClick={onClick}
      className={`relative z-[1] block w-full rounded-lg border bg-white px-2 py-1 text-left text-[11.5px] transition-opacity ${selected ? "border-primary ring-2 ring-info-line" : "border-hairline hover:border-steel"} ${className ?? ""}`}
    >
      {children}
    </button>
  );
}

function ConnectionList({ id, label, fwd, back, onClear }: { id: string; label: (id: string) => string; fwd: Map<string, string[]>; back: Map<string, string[]>; onClear: () => void }) {
  const up = back.get(id) ?? [];
  const down = fwd.get(id) ?? [];
  return (
    <div className="mb-md rounded-lg border border-info-line bg-info-faint p-sm text-[12px]" role="status" aria-live="polite" data-pipeline-selection>
      <div className="flex flex-wrap items-center gap-xs">
        <b className="text-ink-deep">{label(id)}</b>
        <button type="button" onClick={onClear} className="ml-auto text-[11px] font-bold text-primary-text">
          선택 해제
        </button>
      </div>
      <p className="mt-0.5 text-charcoal">
        <span className="font-bold text-steel">받는 곳</span> {up.length ? up.map(label).join(" · ") : "없음"}
      </p>
      <p className="text-charcoal">
        <span className="font-bold text-steel">보내는 곳</span> {down.length ? down.map(label).join(" · ") : "없음"}
      </p>
    </div>
  );
}

function LiveDot({ label }: { label: string }) {
  return (
    <span className="inline-flex items-center gap-1 text-[10.5px] font-bold text-primary-text">
      <span aria-hidden="true" className="inline-block h-2 w-2 rounded-full bg-primary motion-safe:animate-pulse" />
      {label}
    </span>
  );
}

/* ───────────── 워크플로우 파이프라인 (PIPE-02 · 03 · 05) ───────────── */
interface Decision {
  id: number;
  at: string;
  agent: string;
  decision: string;
  summary: string;
  detail: { by?: string } | null;
  runId: string | null;
}
const DECISION_KO: Record<string, string> = { hold: "실행 대기", release: "실행 허용", detect: "변화 판정", plan: "실행 계획", narrated: "서술 갱신", route: "경로 지정" };

export function WorkflowPipeline({ data, code, onRun, busy }: { data: PipelineData; code: string; onRun: (code: string) => void; busy: boolean }) {
  const w = data.workflows.find((x) => x.code === code) ?? data.workflows[0];
  const [node, setNode] = useState<string | null>(null);
  const runId = w?.live?.runId ?? w?.lastRun?.id ?? null;
  const dec = useApiData<{ items: Decision[] }>(runId ? `/admin/agents/decisions?run=${runId}&limit=60` : null, { refreshMs: w?.live ? 5000 : 0 });
  if (!w) return <p className="text-[12px] text-stone">워크플로우가 없습니다.</p>;
  const stageLabel = Object.fromEntries(data.stages.map((s) => [s.key, s.label]));
  // 실행 순서(seq)대로, 같은 단계가 이어지면 한 묶음
  const segs: { stage: string; nodes: PipeNode[] }[] = [];
  for (const n of w.nodes) {
    const last = segs[segs.length - 1];
    if (last && last.stage === n.stage) last.nodes.push(n);
    else segs.push({ stage: n.stage, nodes: [n] });
  }
  const src = new Map(data.sources.map((s) => [s.id, s]));
  const outs = new Map(data.outputs.map((o) => [o.id, o]));
  const sel = w.nodes.find((n) => n.key === node) ?? null;
  const live = w.live?.status === "running";
  const pct = live && w.live?.total ? Math.round(((w.live.done ?? 0) / w.live.total) * 100) : null;

  return (
    <div data-workflow-pipeline={w.code}>
      <div className="mb-md flex flex-wrap items-center gap-xs">
        <h3 className="text-[15px] font-bold text-ink-deep">{w.name}</h3>
        <code className="font-mono text-[11px] text-stone">{w.code}</code>
        <StatusPill status={live ? "running" : w.lastRun?.status} />
        {w.jobs.length ? <Badge tone="neutral">대기 작업 {w.jobs.length}</Badge> : null}
        <span className="text-[11.5px] text-stone">
          최근 실행 {fmtTime(w.lastRun?.startedAt)}
          {w.lastRun?.wallMs ? ` · ${ms(w.lastRun.wallMs)}` : ""}
          {w.lastRun?.causes?.length ? ` · 원인 ${w.lastRun.causes.map((c) => c.type).filter(Boolean).slice(-3).join(", ")}` : ""}
        </span>
        <span className="ml-auto inline-flex gap-xs">
          {runId ? (
            <Link href={`/admin/monitor/runs?run=${runId}`} className="rounded-pill bg-surface-soft px-3 py-1 text-[12px] font-bold text-charcoal">
              실행 상세
            </Link>
          ) : null}
          <button type="button" disabled={busy || !w.enabled} onClick={() => onRun(w.code)} className="rounded-pill bg-ink-deep px-3 py-1 text-[12px] font-bold text-white disabled:opacity-50">
            지금 실행
          </button>
        </span>
      </div>
      {live ? (
        <div className="mb-md" role="status" aria-live="polite">
          <p className="mb-1 text-[12px] font-bold text-primary-text">
            실행 중 — {w.live?.done}/{w.live?.total} 노드 완료{w.live?.currentNode ? ` · 다음 ${w.nodes.find((n) => n.key === w.live?.currentNode)?.name ?? w.live.currentNode}` : ""}
          </p>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-soft" aria-hidden="true">
            <div className="h-full bg-primary transition-all" style={{ width: `${pct ?? 0}%` }} />
          </div>
        </div>
      ) : w.jobs.length ? (
        <p className="mb-md text-[12px] text-steel">대기 작업: {w.jobs.map((j) => `#${j.id} ${STATUS_KO[j.status] ?? j.status} · 실행 예정 ${fmtTime(j.runAfter)} · 원인 ${j.causes}건`).join(" / ")}</p>
      ) : null}

      <div className="pb-sm">
        <ol className="flex flex-wrap items-start gap-y-sm" aria-label={`${w.name} 노드 흐름 — 실행 순서`}>
          <li className="flex items-stretch">
            <EndCap title="입력" items={w.inputs.map((i) => ({ key: i.source, text: src.get(i.source)?.label ?? i.source, sub: i.via === "trigger" ? "트리거" : i.via === "lineage" ? "계보" : "근거" }))} />
            <Arrow />
          </li>
          {segs.map((sg, i) => (
            <li key={`${sg.stage}-${i}`} className="flex items-stretch">
              <section aria-label={stageLabel[sg.stage] ?? sg.stage} className="flex w-[188px] flex-col rounded-xl bg-surface-soft p-xs">
                <h4 className="mb-xs px-1 text-[11px] font-bold uppercase tracking-wide text-steel">{stageLabel[sg.stage] ?? sg.stage}</h4>
                <ul className="flex flex-col gap-xs">
                  {sg.nodes.map((n) => (
                    <li key={n.key}>
                      <NodeCard n={n} current={live && w.live?.currentNode === n.key} live={live} selected={node === n.key} onClick={() => setNode(node === n.key ? null : n.key)} />
                    </li>
                  ))}
                </ul>
              </section>
              {i < segs.length - 1 ? <Arrow /> : null}
            </li>
          ))}
          <li className="flex items-stretch">
            <Arrow />
            <EndCap title="산출물" items={w.outputs.map((o) => ({ key: o, text: outs.get(o)?.label ?? o, sub: OUT_KO[outs.get(o)?.kind ?? "artifact"] }))} />
          </li>
        </ol>
      </div>

      {sel ? <NodeDetail key={`${runId}-${sel.key}`} n={sel} runId={runId} stage={stageLabel[sel.stage] ?? sel.stage} onClose={() => setNode(null)} /> : <p className="mt-sm text-[11.5px] text-stone">노드를 누르면 입력 · 출력 요약을 볼 수 있습니다.</p>}

      <div className="mt-lg">
        <h4 className="mb-xs text-[13px] font-bold text-ink-deep">에이전트 판단 타임라인</h4>
        <p className="mb-sm text-[11.5px] text-stone">이 실행에서 에이전트가 무엇을 왜 결정했는지 — LLM 판단은 허용 목록으로 검증되고, 실패하면 규칙으로 대체됩니다. 수치는 모두 커널이 계산합니다.</p>
        <ol className="relative ml-2 border-l-2 border-hairline pl-md" data-agent-timeline>
          {[...(dec.data?.items ?? [])].reverse().map((d) => {
            const by = d.detail?.by;
            return (
              <li key={d.id} className="relative mb-sm">
                <span aria-hidden="true" className={`absolute -left-[23px] top-1 h-3 w-3 rounded-full border-2 border-white ${by === "llm" ? "bg-primary" : "bg-steel"}`} />
                <p className="flex flex-wrap items-center gap-1 text-[11.5px]">
                  <span className="font-mono text-stone">{fmtTime(d.at).slice(11)}</span>
                  <b className="text-ink-deep">{d.agent}</b>
                  <Badge tone="dark">{DECISION_KO[d.decision] ?? d.decision}</Badge>
                  {by ? <Badge tone={by === "llm" ? "info" : "neutral"}>{by === "llm" ? "LLM 판단" : "규칙 판단"}</Badge> : null}
                </p>
                <p className="text-[12px] text-charcoal">{d.summary}</p>
              </li>
            );
          })}
          {dec.data && !dec.data.items.length ? <li className="text-[11.5px] text-stone">이 실행의 에이전트 결정 기록 없음</li> : null}
        </ol>
      </div>
    </div>
  );
}

function Arrow() {
  return (
    <span aria-hidden="true" className="flex w-6 shrink-0 items-center justify-center text-[16px] text-stone">
      →
    </span>
  );
}

function EndCap({ title, items }: { title: string; items: { key: string; text: string; sub: string }[] }) {
  return (
    <section aria-label={title} className="flex w-[176px] flex-col rounded-xl border border-dashed border-hairline p-xs">
      <h4 className="mb-xs px-1 text-[11px] font-bold text-steel">
        {title} {items.length}
      </h4>
      <ul className="flex max-h-[300px] flex-col gap-1 overflow-y-auto" tabIndex={0} aria-label={`${title} 목록`}>
        {items.map((it) => (
          <li key={it.key} className="rounded-md bg-white px-1.5 py-1 text-[11px]">
            <span className="block truncate font-bold text-ink-deep">{it.text}</span>
            <span className="text-[10px] text-stone">{it.sub}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function NodeCard({ n, current, live, selected, onClick }: { n: PipeNode; current: boolean; live: boolean; selected: boolean; onClick: () => void }) {
  const st = !n.enabled ? "skipped" : live ? (n.live?.status ?? (current ? "running" : "queued")) : (n.last?.status ?? null);
  const t = live ? n.live?.ms : n.last?.ms;
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      data-node={n.key}
      className={`block w-full overflow-hidden rounded-lg border bg-white text-left ${selected ? "border-primary ring-2 ring-info-line" : "border-hairline hover:border-steel"} ${!n.enabled ? "opacity-60" : ""}`}
    >
      <span aria-hidden="true" className={`block h-1 w-full ${STATUS_BAR[st ?? ""] ?? "bg-hairline"} ${st === "running" ? "motion-safe:animate-pulse" : ""}`} />
      <span className="block p-1.5">
        <span className="flex items-start justify-between gap-1">
          <span className="text-[12px] font-bold leading-tight text-ink-deep">{n.name}</span>
          <span className="shrink-0 text-[10px] text-stone">{ms(t)}</span>
        </span>
        <span className="mt-0.5 flex flex-wrap items-center gap-1">
          <span className={`text-[10.5px] font-bold ${st === "failed" ? "text-critical-text" : st === "degraded" ? "text-attention" : st === "succeeded" ? "text-success-text" : "text-steel"}`}>{!n.enabled ? "꺼짐" : (STATUS_KO[st ?? ""] ?? "실행 없음")}</span>
          <AgentBadge agent={n.agent} />
        </span>
        {n.last?.summary && !live ? <span className="mt-0.5 block text-[10.5px] leading-snug text-charcoal">{n.last.summary}</span> : null}
      </span>
    </button>
  );
}

function NodeDetail({ n, runId, stage, onClose }: { n: PipeNode; runId: string | null; stage: string; onClose: () => void }) {
  const [detail, setDetail] = useState<{ input: unknown; output: unknown; error: string | null } | null>(null);
  useEffect(() => {
    let off = false;
    if (runId)
      apiGetC<{ nodes: { key: string; input: unknown; output: unknown; error: string | null }[] }>(`/admin/monitor/runs/${runId}`)
        .then((r) => {
          if (!off) setDetail(r.nodes.find((x) => x.key === n.key) ?? null);
        })
        .catch(() => undefined);
    return () => {
      off = true;
    };
  }, [runId, n.key]);
  return (
    <div className="mt-md rounded-xl border border-hairline p-md" data-node-detail={n.key}>
      <div className="flex flex-wrap items-center gap-xs">
        <b className="text-[13px] text-ink-deep">{n.name}</b>
        <Badge>{stage}</Badge>
        <code className="font-mono text-[11px] text-stone">{n.impl}</code>
        <AgentBadge agent={n.agent} />
        <StatusPill status={n.enabled ? n.last?.status : "skipped"} />
        <button type="button" onClick={onClose} className="ml-auto text-[11px] font-bold text-primary-text">
          닫기
        </button>
      </div>
      <p className="mt-xs text-[12px] text-charcoal">{n.last?.summary || "요약 없음"}</p>
      {n.last?.by ? <p className="text-[11.5px] text-steel">판단 주체: {n.last.by === "llm" ? "LLM" : "규칙"}</p> : null}
      {detail?.error ? <p className="mt-xs text-[11.5px] text-critical-text">오류: {detail.error}</p> : null}
      <div className="mt-xs grid grid-cols-1 gap-xs lg:grid-cols-2">
        <Collapse label="입력">{detail ? <JsonView value={detail.input} maxHeight={260} /> : <p className="text-[11px] text-stone">불러오는 중</p>}</Collapse>
        <Collapse label="출력">{detail ? <JsonView value={detail.output} maxHeight={260} /> : <p className="text-[11px] text-stone">불러오는 중</p>}</Collapse>
      </div>
    </div>
  );
}

/* ───────────── 이벤트 흐름 (PIPE-04) ───────────── */
interface FlowEvent {
  id: number;
  type: string;
  payload: Record<string, unknown>;
  actor: string | null;
  at: string;
  dispatchedAt: string | null;
  matched: { workflow?: string; reasons?: string[]; note?: string }[];
  runs: { run: string; workflow: string; status: string; startedAt: string; finishedAt: string | null; published: string[] }[];
  pending: { job: number; workflow: string; status: string; runAfter: string }[];
}
const EVENT_KO: Record<string, string> = {
  "dataset.committed": "데이터셋 확정",
  "document.ingested": "문서 등록",
  "rule.changed": "규칙 변경",
  "goal.confirmed": "경영목표 확정",
  "config.changed": "설정 변경",
  "contract.changed": "정의서 변경",
  "change.detected": "변화 감지",
  "agent.followup": "후속 실행(플래너)",
  manual: "수동 실행",
  schedule: "정기 실행",
};

function describe(e: FlowEvent): string {
  const p = e.payload as Record<string, string | number | boolean | undefined>;
  if (e.type.startsWith("dataset.")) return `${p.dataset} v${p.version}${p.rows !== undefined ? ` · ${p.rows}행` : ""}`;
  if (e.type.startsWith("document.")) return `${p.doc_code} · ${p.doc_class}`;
  if (e.type === "rule.changed") return `${p.rule} v${p.version}`;
  if (e.type === "manual" || e.type === "agent.followup") return `${p.workflow ?? ""}`;
  if (e.type === "schedule") return `${p.workflow} · ${p.cron}`;
  if (e.type === "contract.changed") return `${p.table ?? p.workbook ?? ""}`;
  return `${p.kind ?? ""} ${p.code ?? p.key ?? ""}`.trim();
}

export function EventPipeline() {
  const data = useApiData<FlowEvent[]>("/admin/monitor/flow?limit=30", { refreshMs: 5000 });
  return (
    <div>
      <p className="mb-md text-[12px] text-steel">이벤트 → 매칭 워크플로우(사유) → 실행 → 게시 산출물. 매칭되지 않은 워크플로우는 실행되지 않습니다. 5초마다 갱신.</p>
      <ol className="flex flex-col gap-xs" data-event-pipeline>
        {(data.data ?? []).map((e) => (
          <li key={e.id} className="rounded-lg border border-hairline bg-white p-xs">
            <div className="flex flex-wrap items-center gap-1 text-[11.5px]">
              <Chip tone="dark">
                <span className="font-mono text-[10px] opacity-80">#{e.id}</span> {EVENT_KO[e.type] ?? e.type}
              </Chip>
              <span className="text-charcoal">{describe(e)}</span>
              <span className="text-[10.5px] text-stone">
                {fmtTime(e.at)} · {e.actor ?? "-"}
              </span>
              <Arrow />
              {e.matched.length ? (
                e.matched.map((m, i) =>
                  m.workflow ? (
                    <Chip key={i} title={m.reasons?.join(" · ")}>
                      {m.workflow} <span className="text-[10px] text-stone">{(m.reasons ?? []).slice(0, 2).join(" · ")}</span>
                    </Chip>
                  ) : (
                    <span key={i} className="text-[10.5px] text-stone">
                      {m.note}
                    </span>
                  ),
                )
              ) : (
                <span className="text-[10.5px] text-stone">{e.dispatchedAt ? "관련 워크플로우 없음" : "디스패치 대기"}</span>
              )}
              {e.runs.length || e.pending.length ? <Arrow /> : null}
              {e.pending.map((p) => (
                <Chip key={`p${p.job}`}>
                  {p.workflow} <StatusPill status={p.status} />
                </Chip>
              ))}
              {e.runs.map((r) => (
                <Chip key={r.run}>
                  <Link href={`/admin/monitor/runs?run=${r.run}`} className="font-bold text-primary-text">
                    {r.workflow}
                  </Link>{" "}
                  <StatusPill status={r.status} />
                  {r.published.length ? <span className="text-[10px] text-stone"> → 게시 {r.published.length}</span> : null}
                </Chip>
              ))}
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}

function Chip({ children, tone, title }: { children: React.ReactNode; tone?: "dark"; title?: string }) {
  return (
    <span title={title} className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 ${tone === "dark" ? "bg-ink-deep text-white" : "bg-surface-soft text-charcoal"}`}>
      {children}
    </span>
  );
}
