"use client";

import clsx from "clsx";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { JsonEditor } from "@/components/admin/kit";
import { ReportView } from "@/components/domain/ReportView";
import { useUi } from "@/components/providers/UiProvider";
import { Advanced, EmptyState, KeyValueList, Notice } from "@/components/ui/Layout";
import { Badge, Button } from "@/components/ui/primitives";
import { api } from "@/lib/api-client";
import type { ReportDoc } from "@/lib/types";

/*
 * 분석 에이전트 만들기 (Phase C · DAG-01~04 · DAG-08)
 * ① 하고 싶은 분석을 글로 → [정제] 분석 에이전트(정제)가 명세 초안 + 검증 결과
 * ② 명세 확인 · 수정(지표 · 표 · 구성 · 의견 · 실행 주기) → [다시 검증]
 * ③ [미리보기] 실제 계산 · 보고서(저장 안 함) → [승인 요청] → 관리자 승인 후 부서 분석 화면에 탭으로
 */

export interface Catalog {
  spaces: { key: string; label: string; path: string }[];
  space: string;
  datasets: { code: string; name: string; description: string; origin: string; columns: { name: string; label: string; type: string }[] }[];
  formulas: { id: string; description: string; params: Record<string, string> }[];
  units: { code: string; label: string }[];
}
interface Issue {
  path: string;
  message: string;
}
interface Validation {
  ok: boolean;
  issues: Issue[];
  counts?: Record<string, number>;
}
type Ref = { q?: { dataset: string; col?: string; agg: string; where?: Record<string, unknown> }; metric?: string; const?: number; label?: string };
interface SpecMetric {
  key: string;
  label: string;
  formula: string;
  args: Record<string, Ref>;
  unit: string;
  decimals?: number;
  rule?: { op: string; value: number; severity: string };
}
interface SpecTable {
  key: string;
  caption: string;
  dataset: string;
  group_by: string;
  value?: string;
  agg: string;
  top: number;
  group_label?: string;
  value_label?: string;
}
interface Spec {
  title: string;
  purpose: string;
  domain_knowledge: string;
  task: string;
  metrics: SpecMetric[];
  tables: SpecTable[];
  sections: { heading: string; blocks: { type: string; metrics?: string[]; table?: string; kind?: string; text?: string }[] }[];
  insights: { key: string; title: string; metrics: string[]; instruction: string }[];
  evidence?: { query: string; doc_classes: string[]; k: number };
  schedule: { cron: string | null; on_data_change: boolean };
}
export interface MyAnalysis {
  code: string;
  space: string;
  spaceLabel: string;
  title: string;
  status: string;
  statusLabel: string;
  version: number;
  href: string | null;
  pendingVersion: number | null;
  lastRun: { status: string; startedAt: string } | null;
  versions: { version: number; status: string; statusLabel: string; reviewNote: string | null; reviewedByName?: string | null }[];
  updatedAt: string;
}

const STATUS_TONE: Record<string, "success" | "attention" | "critical" | "neutral" | "info"> = { active: "success", pending: "attention", paused: "neutral", retired: "neutral", rejected: "critical", draft: "info" };
const SAMPLES = [
  "7790 상품별 충당금 자료로 상품명별 충당금 합계와 충당금이 많은 상위 상품을 보고 싶습니다. 특정 상품에 쏠림이 있는지 의견을 주세요.",
  "월별 부도율 자료에서 최근 기준월 구분별 부도율을 보고, 부도율이 높은 구분을 짚어 주세요.",
];

function refText(r: Ref): string {
  if (r.q) return `${r.q.dataset} · ${r.q.col ?? "행"} ${r.q.agg}${r.q.where && Object.keys(r.q.where).length ? ` (${Object.entries(r.q.where).map(([k, v]) => `${k}=${typeof v === "object" ? JSON.stringify(v) : String(v)}`).join(", ")})` : ""}`;
  if (r.metric) return `지표 ${r.metric}`;
  if (r.const !== undefined) return `상수 ${r.const}`;
  return "-";
}

function Step({ n, title, active, done, children }: { n: number; title: string; active: boolean; done: boolean; children: React.ReactNode }) {
  return (
    <section aria-labelledby={`step-${n}`} className={clsx("rounded-2xl border bg-canvas p-lg", active ? "border-primary" : "border-hairline-soft")}>
      <h2 id={`step-${n}`} className="mb-md flex items-center gap-2 text-[15px] font-bold text-ink-deep">
        <span aria-hidden="true" className={clsx("flex h-7 w-7 items-center justify-center rounded-circle text-[12px]", done ? "bg-success-soft text-success" : active ? "bg-ink-deep text-white" : "bg-surface-soft text-steel")}>
          {n}
        </span>
        <span className="sr-only">{n}단계 · </span>
        {title}
        {done ? <Badge tone="success">완료</Badge> : null}
      </h2>
      {children}
    </section>
  );
}

export function AnalysisBuilder({ catalog, mine: initialMine, editing, initialDatasets }: { catalog: Catalog; mine: MyAnalysis[]; editing?: { code: string; text: string; spec: Spec } | null; initialDatasets?: string[] }) {
  const { showToast } = useUi();
  const router = useRouter();
  const [space, setSpace] = useState(catalog.space);
  const [text, setText] = useState(editing?.text ?? "");
  // 주소 ?dataset= — 관리자 [데이터셋 › 연결 도우미]에서 이 자료로 분석을 만들러 왔을 때 미리 골라 둔다(카탈로그에 있는 것만 · Phase M DOB-11)
  const [hints, setHints] = useState<string[]>(() => (initialDatasets ?? []).filter((c) => catalog.datasets.some((d) => d.code === c)));
  const [spec, setSpec] = useState<Spec | null>(editing?.spec ?? null);
  const [validation, setValidation] = useState<Validation | null>(null);
  const [meta, setMeta] = useState<{ by?: string; reason?: string; notes?: string[] } | null>(null);
  const [report, setReport] = useState<ReportDoc | null>(null);
  const [nodes, setNodes] = useState<{ key: string; status: string; error?: string }[]>([]);
  const [busy, setBusy] = useState<"" | "refine" | "validate" | "preview" | "request">("");
  const [error, setError] = useState<string | null>(null);
  const [mine, setMine] = useState(initialMine);
  const [done, setDone] = useState<{ agent: string; version: number } | null>(null);
  const [dsQ, setDsQ] = useState("");
  const dsName = useMemo(() => Object.fromEntries(catalog.datasets.map((d) => [d.code, d.name])), [catalog.datasets]);
  const unitLabel = useMemo(() => Object.fromEntries(catalog.units.map((u) => [u.code, u.label])), [catalog.units]);
  const spaceLabel = catalog.spaces.find((s) => s.key === space)?.label ?? space;

  const call = async <T,>(kind: typeof busy, path: string, body: unknown): Promise<T | null> => {
    setBusy(kind);
    setError(null);
    try {
      return await api<T>(path, { method: "POST", json: body });
    } catch (e) {
      setError((e as Error).message);
      return null;
    } finally {
      setBusy("");
    }
  };

  const doRefine = async () => {
    const r = await call<{ spec: Spec; validation: Validation; meta: { by: string; reason?: string; notes?: string[] } }>("refine", "/analysis-agents/refine", { space, text, datasets: hints });
    if (r) {
      setSpec(r.spec);
      setValidation(r.validation);
      setMeta(r.meta);
      setReport(null);
    }
  };
  const doValidate = async (next?: Spec) => {
    const r = await call<{ spec: Spec; validation: Validation }>("validate", "/analysis-agents/validate", { space, spec: next ?? spec });
    if (r) {
      setSpec(r.spec);
      setValidation(r.validation);
      setReport(null);
    }
  };
  const doPreview = async () => {
    const r = await call<{ spec: Spec; validation: Validation; report: ReportDoc | null; nodes: typeof nodes }>("preview", "/analysis-agents/preview", { space, spec });
    if (r) {
      setSpec(r.spec);
      setValidation(r.validation);
      setReport(r.report);
      setNodes(r.nodes ?? []);
    }
  };
  const doRequest = async () => {
    const r = await call<{ agent: string; version: number }>("request", "/analysis-agents", { space, text, spec, agent_code: editing?.code ?? null });
    if (r) {
      setDone(r);
      showToast("승인을 요청했습니다 — 관리자가 승인하면 분석 화면에 탭으로 나타납니다");
      api<MyAnalysis[]>("/analysis-agents/mine").then(setMine).catch(() => undefined);
      router.refresh();
    }
  };
  const edit = (patch: Partial<Spec>) => {
    if (!spec) return;
    setSpec({ ...spec, ...patch });
    setReport(null);
    setValidation(validation ? { ...validation, ok: false } : null);
  };
  const removeMetric = (key: string) =>
    spec &&
    edit({
      metrics: spec.metrics.filter((m) => m.key !== key),
      sections: spec.sections.map((s) => ({ ...s, blocks: s.blocks.map((b) => (b.type === "metrics" ? { ...b, metrics: (b.metrics ?? []).filter((k) => k !== key) } : b)).filter((b) => b.type !== "metrics" || (b.metrics ?? []).length) })).filter((s) => s.blocks.length),
      insights: spec.insights.map((i) => ({ ...i, metrics: i.metrics.filter((k) => k !== key) })),
    });
  const removeTable = (key: string) =>
    spec && edit({ tables: spec.tables.filter((t) => t.key !== key), sections: spec.sections.map((s) => ({ ...s, blocks: s.blocks.filter((b) => b.table !== key) })).filter((s) => s.blocks.length) });

  const datasets = catalog.datasets.filter((d) => !dsQ || `${d.code} ${d.name}`.toLowerCase().includes(dsQ.toLowerCase())).slice(0, 30);
  const stage = done ? 4 : report ? 3 : spec ? 2 : 1;

  return (
    <div className="grid grid-cols-1 gap-xl xl:grid-cols-[minmax(0,1fr)_340px]">
      <div className="flex min-w-0 flex-col gap-lg">
        {error ? (
          <Notice tone="critical" title="처리하지 못했습니다">
            {error}
          </Notice>
        ) : null}

        <Step n={1} title="하고 싶은 분석을 글로 적기" active={stage === 1} done={stage > 1}>
          <div className="flex flex-col gap-md">
            {catalog.spaces.length > 1 ? (
              <label className="block max-w-[320px]">
                <span className="mb-1 block text-[12px] font-bold text-charcoal">분석을 올릴 부서 화면</span>
                <select className="input !h-9 text-[13px]" value={space} onChange={(e) => setSpace(e.target.value)}>
                  {catalog.spaces.map((s) => (
                    <option key={s.key} value={s.key}>
                      {s.label}
                    </option>
                  ))}
                </select>
              </label>
            ) : (
              <p className="text-[12.5px] text-steel">
                만든 분석은 <b className="text-ink-deep">{spaceLabel}</b> 분석 화면에 탭으로 나타납니다.
              </p>
            )}
            <label className="block">
              <span className="mb-1 block text-[12px] font-bold text-charcoal">도메인 지식 · 하고 싶은 분석</span>
              <textarea
                className="input text-[13px] leading-relaxed"
                rows={7}
                maxLength={6000}
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="예: 어떤 자료로 무엇을 보고 싶은지, 업무에서 중요하게 보는 기준(예: 쏠림 · 증가 추세), 어떤 의견이 필요한지 자유롭게 적어 주세요. 숫자 계산은 계산 커널이 합니다."
                data-builder-text
              />
              <span className="mt-1 block text-right text-[11px] text-stone tnum">{text.length.toLocaleString("ko-KR")} / 6,000자</span>
            </label>
            <div className="flex flex-wrap gap-1.5">
              <span className="text-[11.5px] font-bold text-steel">예시</span>
              {SAMPLES.map((s, i) => (
                <button key={i} type="button" onClick={() => setText(s)} className="rounded-pill border border-hairline px-2.5 py-1 text-[11.5px] text-charcoal hover:bg-surface-soft">
                  예시 {i + 1}
                </button>
              ))}
            </div>
            <Advanced label={`사용할 자료 지정(선택) ${hints.length ? `· ${hints.length}개` : ""}`} hint="비우면 글에서 찾습니다" defaultOpen={Boolean(initialDatasets?.length)}>
              <input className="input !h-9 mb-xs w-full max-w-[320px] text-[13px]" placeholder="자료 이름 · 코드로 찾기" aria-label="자료 찾기" value={dsQ} onChange={(e) => setDsQ(e.target.value)} />
              <ul className="flex flex-wrap gap-1.5">
                {datasets.map((d) => {
                  const on = hints.includes(d.code);
                  return (
                    <li key={d.code}>
                      <button type="button" aria-pressed={on} onClick={() => setHints(on ? hints.filter((h) => h !== d.code) : [...hints, d.code].slice(0, 5))} className={clsx("rounded-pill border px-2.5 py-1 text-[11.5px]", on ? "border-primary bg-info-faint font-bold text-primary" : "border-hairline text-charcoal")}>
                        {d.name}
                      </button>
                    </li>
                  );
                })}
              </ul>
            </Advanced>
            <div>
              <Button variant="confirm" disabled={text.trim().length < 10 || busy !== ""} onClick={doRefine} data-builder-refine>
                {busy === "refine" ? "정제 중…" : spec ? "다시 정제" : "정제하기"}
              </Button>
              <span className="ml-xs text-[11.5px] text-stone">분석 에이전트가 글을 데이터 · 지표 · 보고서 구성으로 정리합니다(LLM 연결 시 30초 ~ 1분).</span>
            </div>
          </div>
        </Step>

        <Step n={2} title="분석 명세 확인 · 수정" active={stage === 2} done={stage > 2}>
          {!spec ? (
            <p className="text-[12.5px] text-stone">1단계에서 정제하면 명세가 여기에 나타납니다.</p>
          ) : (
            <div className="flex flex-col gap-lg" data-builder-spec>
              {meta ? (
                <p className="text-[11.5px] text-steel">
                  정제: {meta.by === "llm" ? "분석 정제 에이전트(LLM)" : "규칙 정제"}
                  {meta.reason ? ` — ${meta.reason}` : ""}
                </p>
              ) : null}
              {validation?.ok ? (
                <Notice tone="success" title="검증 통과">
                  허용된 데이터 · 계산식만 쓰는 명세입니다.
                </Notice>
              ) : null}
              {validation && validation.issues.length ? (
                <Notice tone={validation.ok ? "attention" : "critical"} title={validation.ok ? `확인할 점 ${validation.issues.length}개 — 정리하면서 빼거나 고친 항목` : "이대로는 실행할 수 없습니다"}>
                  <ul className="list-disc pl-4">
                    {validation.issues.slice(0, 12).map((i, k) => (
                      <li key={k}>{i.message}</li>
                    ))}
                  </ul>
                </Notice>
              ) : null}
              <div className="grid grid-cols-1 gap-md md:grid-cols-2">
                <label className="block">
                  <span className="mb-1 block text-[12px] font-bold text-charcoal">제목(탭 이름)</span>
                  <input className="input !h-9 text-[13px]" value={spec.title} maxLength={80} onChange={(e) => edit({ title: e.target.value })} />
                </label>
                <label className="block">
                  <span className="mb-1 block text-[12px] font-bold text-charcoal">목적</span>
                  <input className="input !h-9 text-[13px]" value={spec.purpose} maxLength={400} onChange={(e) => edit({ purpose: e.target.value })} />
                </label>
              </div>
              <div>
                <h3 className="mb-xs text-[13px] font-bold text-ink-deep">지표 {spec.metrics.length}개 · 계산 커널이 계산</h3>
                {spec.metrics.length ? (
                  <ul className="flex flex-col gap-xs">
                    {spec.metrics.map((m) => (
                      <li key={m.key} className="flex flex-wrap items-start gap-xs rounded-xl border border-hairline-soft px-md py-2">
                        <div className="min-w-0 flex-1">
                          <p className="flex flex-wrap items-center gap-1.5 text-[13px] font-bold text-ink-deep">
                            {m.label} <Badge tone="info">{m.formula}</Badge> <span className="text-[11px] font-medium text-stone">{unitLabel[m.unit] ?? m.unit}</span>
                            {m.rule ? (
                              <Badge tone="attention">
                                {m.rule.op} {m.rule.value} → {m.rule.severity}
                              </Badge>
                            ) : null}
                          </p>
                          <ul className="mt-0.5 text-[11.5px] text-steel">
                            {Object.entries(m.args).map(([k, r]) => (
                              <li key={k}>
                                <span className="font-mono text-stone">{k}</span> = {r.q ? `${dsName[r.q.dataset] ?? r.q.dataset} · ` : ""}
                                {refText(r)}
                              </li>
                            ))}
                          </ul>
                        </div>
                        <Button size="sm" variant="quiet" onClick={() => removeMetric(m.key)} aria-label={`${m.label} 빼기`}>
                          빼기
                        </Button>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <EmptyState compact title="지표가 없습니다" description="글에 자료 이름과 보고 싶은 값(합계 · 건수 · 비율 등)을 더 구체적으로 적어 다시 정제하세요." />
                )}
              </div>
              {spec.tables.length ? (
                <div>
                  <h3 className="mb-xs text-[13px] font-bold text-ink-deep">표 · 그래프 {spec.tables.length}개</h3>
                  <ul className="flex flex-col gap-xs">
                    {spec.tables.map((t) => (
                      <li key={t.key} className="flex flex-wrap items-center gap-xs rounded-xl border border-hairline-soft px-md py-2 text-[12.5px]">
                        <span className="min-w-0 flex-1">
                          <b className="text-ink-deep">{t.caption}</b>
                          <span className="ml-1.5 text-[11.5px] text-steel">
                            {dsName[t.dataset] ?? t.dataset} · {t.group_label ?? t.group_by}별 {t.value_label ?? t.value ?? "건수"} {t.agg} · 상위 {t.top}
                          </span>
                        </span>
                        <Button size="sm" variant="quiet" onClick={() => removeTable(t.key)} aria-label={`${t.caption} 빼기`}>
                          빼기
                        </Button>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
              <div>
                <h3 className="mb-xs text-[13px] font-bold text-ink-deep">에이전트 의견 {spec.insights.length}개</h3>
                {spec.insights.map((ins, i) => (
                  <div key={ins.key} className="mb-xs grid grid-cols-1 gap-xs rounded-xl border border-hairline-soft p-md md:grid-cols-[240px_1fr]">
                    <label className="block">
                      <span className="mb-1 block text-[11.5px] font-bold text-steel">의견 제목</span>
                      <input
                        className="input !h-9 text-[13px]"
                        value={ins.title}
                        maxLength={80}
                        onChange={(e) => edit({ insights: spec.insights.map((x, k) => (k === i ? { ...x, title: e.target.value } : x)) })}
                      />
                    </label>
                    <label className="block">
                      <span className="mb-1 block text-[11.5px] font-bold text-steel">의견 작성 지시(분석 에이전트에게)</span>
                      <input
                        className="input !h-9 text-[13px]"
                        value={ins.instruction}
                        maxLength={600}
                        onChange={(e) => edit({ insights: spec.insights.map((x, k) => (k === i ? { ...x, instruction: e.target.value } : x)) })}
                      />
                    </label>
                  </div>
                ))}
              </div>
              <KeyValueList
                items={[
                  { label: "보고서 구성", value: spec.sections.map((s) => s.heading).join(" · ") || "-" },
                  { label: "근거 문서 검색", value: spec.evidence ? `${spec.evidence.query}` : "사용 안 함" },
                ]}
              />
              <div className="grid grid-cols-1 gap-md md:grid-cols-2">
                <label className="block">
                  <span className="mb-1 block text-[12px] font-bold text-charcoal">정기 실행(선택, cron)</span>
                  <input className="input !h-9 font-mono text-[13px]" value={spec.schedule.cron ?? ""} placeholder="예: 0 7 * * 1-5 (평일 7시)" onChange={(e) => edit({ schedule: { ...spec.schedule, cron: e.target.value || null } })} />
                </label>
                <label className="flex items-end gap-1.5 pb-2 text-[12.5px] text-charcoal">
                  <input type="checkbox" checked={spec.schedule.on_data_change} onChange={(e) => edit({ schedule: { ...spec.schedule, on_data_change: e.target.checked } })} />
                  자료가 바뀌면 다시 계산
                </label>
              </div>
              <Advanced label="고급 — 명세 원본(JSON) 직접 고치기">
                <JsonEditor value={spec} rows={16} label="이 명세로 다시 검증" disabled={busy !== ""} onSave={(v) => doValidate(v as Spec)} />
              </Advanced>
              <div className="flex flex-wrap items-center gap-xs">
                <Button variant="quiet" disabled={busy !== ""} onClick={() => doValidate()}>
                  {busy === "validate" ? "검증 중…" : "다시 검증"}
                </Button>
                <Button variant="confirm" disabled={busy !== "" || !spec.metrics.length} onClick={doPreview} data-builder-preview>
                  {busy === "preview" ? "계산 중…" : "미리보기"}
                </Button>
                <span className="text-[11.5px] text-stone">미리보기는 실제 자료로 계산하지만 저장하지 않습니다.</span>
              </div>
            </div>
          )}
        </Step>

        <Step n={3} title="미리보기 확인 후 승인 요청" active={stage === 3} done={stage > 3}>
          {!report ? (
            <p className="text-[12.5px] text-stone">2단계에서 [미리보기]를 누르면 계산된 보고서가 여기에 나타납니다.</p>
          ) : (
            <div className="flex flex-col gap-md" data-builder-report>
              {nodes.some((n) => n.status === "failed") ? (
                <Notice tone="critical" title="일부 단계가 실패했습니다">
                  {nodes
                    .filter((n) => n.status === "failed")
                    .map((n) => `${n.key}: ${n.error ?? ""}`)
                    .join(" · ")}
                </Notice>
              ) : null}
              <Notice tone="info" title="미리보기 — 저장되지 않았습니다">
                의견 문장은 승인 후 실행에서 이 분석 전용 에이전트가 작성합니다(지금은 기본 문장). 수치는 계산 커널이 계산한 값입니다.
              </Notice>
              <div className="overflow-hidden rounded-2xl border border-hairline-soft">
                <ReportView report={report} />
              </div>
              {done ? (
                <Notice tone="success" title={`승인 요청을 보냈습니다 (v${done.version})`}>
                  관리자가 승인하면 {spaceLabel} 분석 화면에 탭으로 나타나고 자료가 바뀔 때마다 다시 계산됩니다. 오른쪽 &lsquo;내 분석&rsquo; 에서 상태를 볼 수 있습니다.
                </Notice>
              ) : (
                <div>
                  <Button variant="confirm" disabled={busy !== "" || !validation?.ok} onClick={doRequest} data-builder-request>
                    {busy === "request" ? "요청 중…" : editing ? "새 버전 승인 요청" : "관리자에게 승인 요청"}
                  </Button>
                </div>
              )}
            </div>
          )}
        </Step>
      </div>

      <aside aria-label="내 분석" className="h-fit rounded-2xl border border-hairline-soft bg-canvas p-lg">
        <h2 className="mb-md text-[15px] font-bold text-ink-deep">내 분석</h2>
        {!mine.length ? (
          <EmptyState compact title="아직 만든 분석이 없습니다" description="왼쪽에서 분석을 만들어 승인을 요청하세요." />
        ) : (
          <ul className="flex flex-col divide-y divide-hairline-soft" data-my-analyses>
            {mine.map((a) => {
              const rejected = a.versions.find((v) => v.status === "rejected" && v.reviewNote);
              return (
                <li key={a.code} className="py-2.5">
                  <p className="flex flex-wrap items-center gap-1.5">
                    <Badge tone={STATUS_TONE[a.status] ?? "neutral"}>{a.pendingVersion ? `v${a.pendingVersion} 승인 대기` : a.statusLabel}</Badge>
                    <span className="text-[12.5px] font-bold text-ink-deep">{a.title}</span>
                  </p>
                  <p className="mt-0.5 text-[11px] text-stone">
                    {a.spaceLabel}
                    {a.version ? ` · 승인 v${a.version}` : ""}
                    {a.lastRun ? ` · 최근 실행 ${a.lastRun.status === "failed" ? "실패" : "완료"}` : ""}
                  </p>
                  {rejected && a.status === "rejected" ? <p className="mt-0.5 text-[11.5px] text-critical">반려 사유: {rejected.reviewNote}</p> : null}
                  <div className="mt-1 flex flex-wrap gap-xs text-[11.5px] font-bold">
                    {a.href ? (
                      <Link href={a.href} className="text-primary">
                        결과 보기
                      </Link>
                    ) : null}
                    {(a.status === "active" || a.status === "paused" || a.status === "rejected") && !a.pendingVersion ? (
                      <Link href={`/analysis/builder?space=${encodeURIComponent(a.space)}&edit=${encodeURIComponent(a.code)}`} className="text-steel">
                        고쳐서 새 버전 요청
                      </Link>
                    ) : null}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </aside>
    </div>
  );
}
