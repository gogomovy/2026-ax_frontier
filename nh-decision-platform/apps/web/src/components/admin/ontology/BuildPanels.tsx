"use client";

/* [온톨로지 › 구축 파이프라인] · [변경 제안] (Phase M · AGG-04 · ONB-09 · Q181)
 * 구축 에이전트는 스키마를 직접 바꾸지 않는다 — 제안으로 남기고 관리자가 연산별 차이 · 근거 · 영향을 보고 승인 · 반려 · 연산 빼기를 한다. */

import { Fragment, useState } from "react";
import { Connector, Step, fmtMs, stepOf } from "@/components/admin/flowViz";
import { C, Card, Loading, Table, TextInput, fmtTime, useAction, useApiData } from "@/components/admin/kit";
import { EmptyState } from "@/components/ui/Layout";
import { Badge, Button } from "@/components/ui/primitives";
import { apiPost } from "@/lib/api-client";
import { GRADE_KO, opText, type Op } from "./opText";

export { GRADE_KO, opText };

export interface Proposal {
  id: number;
  status: "pending" | "applied" | "rejected" | "failed" | string;
  source: string;
  agent: string | null;
  title: string;
  summary: string | null;
  ops: Op[];
  opKeys: string[];
  evidence: Record<string, unknown>;
  impact: { nodesDelta?: number; relationsDelta?: number; nodes?: Record<string, { before: number; after: number }>; relations?: Record<string, { before: number; after: number }>; dangling?: Record<string, number> };
  validation: { errors?: string[]; warnings?: string[]; skipped?: { key: string; reason: string }[]; diff?: Record<string, unknown> };
  baseVersion: number | null;
  appliedVersion: number | null;
  createdAt: string;
  decidedBy: string | null;
  decidedAt: string | null;
  note: string | null;
}
interface Build {
  runs: { id: string; status: string; startedAt: string; finishedAt: string | null; causes: string[] }[];
  stages: { key: string; impl: string; agent: string | null; status: string; ms: number | null; output: Record<string, unknown>; error: string | null }[];
  quality: { grade?: "ok" | "warn" | "risk" | string; checks?: { code: string; title?: string; ok?: boolean; severity?: "ok" | "warn" | "risk" | string; detail?: string; count?: number }[] } | null;
  profiles: { dataset: string; name: string; kind: string; profiled: boolean; at: string | null; by: string | null; rows: number | null; dimensions: string[]; measures: string[]; keyCandidates: (string | string[])[]; entity: string | null; summary: string | null }[];
  decisions: { id: number; at: string; agent: string; decision: string; summary: string }[];
}

const STAGE_KO: Record<string, string> = {
  profile_datasets: "구조 파악", design_object_types: "객체 유형 설계", discover_links: "링크 발견", resolve_entities: "개체 해소", check_ontology: "품질 점검", propose_ontology: "변경 제안",
};
const SOURCE_KO: Record<string, string> = { agent: "구축 에이전트", review: "추출 검토 수락", admin: "관리자" };
const STATUS_KO: Record<string, { label: string; tone: "info" | "success" | "neutral" | "critical" }> = {
  pending: { label: "승인 대기", tone: "info" }, applied: { label: "적용", tone: "success" }, rejected: { label: "반려", tone: "neutral" }, failed: { label: "검증 실패", tone: "critical" },
  superseded: { label: "이미 반영", tone: "neutral" },
};

/** [구축 파이프라인] — 최근 실행 단계 · 데이터셋별 구조 파악 · 품질 점검 · 결정 */
export function BuildPipeline() {
  const data = useApiData<Build>("/admin/ontology/build", { refreshMs: 10000 });
  const { run, busy } = useAction();
  const b = data.data;
  const last = b?.runs[0];
  const lastSt = stepOf(last?.status);
  const profiled = (b?.profiles ?? []).filter((p) => p.profiled).length;
  return (
    <>
      <Card
        title="구축 에이전트 단계"
        actions={
          <>
            <span className="text-[11.5px] text-steel">{last ? `최근 ${lastSt.label} · ${fmtTime(last.startedAt)}${last.causes.length ? ` · ${last.causes.join(", ")}` : ""}` : "실행 기록 없음"}</span>
            <Button size="sm" variant="confirm" disabled={busy} onClick={() => run(() => apiPost("/admin/ontology/build/run"), "온톨로지 구축을 요청했습니다 — 워커가 곧 실행합니다", data.reload)}>
              지금 구축 실행
            </Button>
          </>
        }
      >
        <Loading error={data.error} loading={!b && data.loading} />
        <p className="mb-md text-[12px] text-steel">데이터셋이 반영되거나 정의가 바뀌면(이벤트) · 매일 07시에 돕니다. 스키마는 바뀌지 않고 [변경 제안]으로 남습니다(자동 적용은 설정 ontology.build.auto_apply 에 둔 연산만).</p>
        {b?.stages.length ? (
          <ol className="flex flex-wrap items-stretch gap-y-xs" aria-label="최근 구축 실행 단계">
            {b.stages.map((st, i) => {
              const x = stepOf(st.status);
              const out = st.output ?? {};
              const facts = Object.entries(out).filter(([, v]) => typeof v === "number" || typeof v === "string").slice(0, 3);
              return (
                <Fragment key={st.key}>
                  <li className="w-[170px]">
                    <Step title={STAGE_KO[st.impl] ?? st.key} state={x.state} stateLabel={x.label} dataKey={st.impl} className="h-full">
                      <span className="block text-[11px] text-steel">{st.agent ?? "규칙"}{st.ms ? ` · ${fmtMs(st.ms)}` : ""}</span>
                      {facts.map(([k, v]) => (
                        <span key={k} className="block truncate text-[11px] text-charcoal">{k}: {String(v)}</span>
                      ))}
                      {st.error ? <span className="block text-[11px] text-critical">{st.error}</span> : null}
                    </Step>
                  </li>
                  {i < b.stages.length - 1 ? (
                    <li aria-hidden="true" className="flex">
                      <Connector />
                    </li>
                  ) : null}
                </Fragment>
              );
            })}
          </ol>
        ) : b ? (
          <EmptyState compact title="아직 구축 실행이 없습니다" description="[지금 구축 실행]을 누르거나 데이터셋을 반영하면 구조 파악부터 시작합니다." />
        ) : null}
      </Card>
      {b?.quality?.checks?.length ? (
        <Card title={`품질 점검 — ${GRADE_KO[b.quality.grade ?? ""] ?? b.quality.grade ?? "-"}`}>
          <Table head={["점검", "결과", "내용"]}>
            {b.quality.checks.map((c) => (
              <tr key={c.code}>
                <C>{c.title ?? c.code}</C>
                <C>{c.ok ? <Badge tone="success">통과</Badge> : <Badge tone={c.severity === "risk" ? "critical" : "attention"}>{c.severity === "risk" ? "위험" : "주의"}</Badge>}</C>
                <C className="max-w-[520px]">{c.detail ?? (c.count !== undefined ? `${c.count}건` : "")}</C>
              </tr>
            ))}
          </Table>
        </Card>
      ) : null}
      <Card title={`구조 파악 ${profiled} / ${b?.profiles.length ?? 0} 데이터셋`}>
        <Table head={["데이터셋", "행이 가리키는 대상", "키 후보", "차원 · 측정값", "행 수", "파악"]}>
          {(b?.profiles ?? []).map((p) => (
            <tr key={p.dataset}>
              <C>
                <span className="font-bold text-ink">{p.name}</span>
                <span className="block font-mono text-[10.5px] text-stone">{p.dataset}</span>
              </C>
              <C>{p.entity ?? "-"}{p.summary ? <span className="block text-[11px] text-steel">{p.summary}</span> : null}</C>
              <C mono>{p.keyCandidates.map((k) => (Array.isArray(k) ? k.join("+") : k)).join(" · ") || "-"}</C>
              <C className="text-[11.5px]">
                {p.dimensions.length ? `차원 ${p.dimensions.join(", ")}` : ""}
                {p.measures.length ? <span className="block">측정 {p.measures.join(", ")}</span> : null}
              </C>
              <C right>{p.rows?.toLocaleString("ko-KR") ?? "-"}</C>
              <C>{p.profiled ? <span className="text-[11.5px]">{fmtTime(p.at)} · {p.by}</span> : <Badge tone="neutral">대기</Badge>}</C>
            </tr>
          ))}
        </Table>
      </Card>
      {b?.decisions.length ? (
        <Card title="구축 에이전트 결정">
          <ul className="flex flex-col gap-1.5 text-[12.5px]">
            {b.decisions.slice(0, 15).map((d) => (
              <li key={d.id} className="flex flex-wrap gap-x-xs">
                <span className="text-stone tnum">{fmtTime(d.at)}</span>
                <Badge tone="neutral">{d.agent}</Badge>
                <span className="font-mono text-[11px] text-steel">{d.decision}</span>
                <span className="min-w-0 flex-1 text-charcoal">{d.summary}</span>
              </li>
            ))}
          </ul>
        </Card>
      ) : null}
    </>
  );
}

/** [변경 제안] — 목록 · 연산별 차이 · 근거 · 영향 · 승인(연산 빼기) · 반려(사유) */
export function ProposalsPanel({ onApplied }: { onApplied?: () => void }) {
  const [status, setStatus] = useState<"pending" | "all">("pending");
  const data = useApiData<{ proposals: Proposal[]; counts: Record<string, number> }>(`/admin/ontology/proposals${status === "pending" ? "?status=pending" : ""}`);
  const list = data.data?.proposals ?? [];
  const counts = data.data?.counts ?? {};
  return (
    <>
      <div className="mb-md flex flex-wrap items-center gap-xs" role="group" aria-label="제안 거르기">
        <Button size="sm" variant={status === "pending" ? "primary" : "ghost"} aria-pressed={status === "pending"} onClick={() => setStatus("pending")}>
          승인 대기 {counts.pending ?? 0}
        </Button>
        <Button size="sm" variant={status === "all" ? "primary" : "ghost"} aria-pressed={status === "all"} onClick={() => setStatus("all")}>
          전체 {Object.values(counts).reduce((n, v) => n + v, 0)}
        </Button>
        <span className="text-[11.5px] text-stone">적용 {counts.applied ?? 0} · 반려 {counts.rejected ?? 0} · 검증 실패 {counts.failed ?? 0}</span>
      </div>
      <Loading error={data.error} loading={!data.data && data.loading} />
      {data.data && !list.length ? <EmptyState compact title={status === "pending" ? "승인 대기 제안이 없습니다" : "제안이 없습니다"} description="구축 에이전트가 새 객체 유형 · 링크 · 별칭을 찾으면 여기에 남깁니다." /> : null}
      {list.map((p) => (
        <ProposalCard key={p.id} p={p} reload={async () => { await data.reload(); onApplied?.(); }} />
      ))}
    </>
  );
}

function ProposalCard({ p, reload }: { p: Proposal; reload: () => Promise<void> }) {
  const { run, busy } = useAction();
  const [drop, setDrop] = useState<Set<number>>(new Set());
  const [note, setNote] = useState("");
  const st = STATUS_KO[p.status] ?? { label: p.status, tone: "neutral" as const };
  const pending = p.status === "pending";
  const impact = p.impact ?? {};
  const toggle = (i: number) => setDrop((d) => { const n = new Set(d); if (n.has(i)) n.delete(i); else n.add(i); return n; });
  const ev = p.evidence ?? {};
  return (
    <Card
      title={
        <span className="flex flex-wrap items-center gap-xs">
          <Badge tone={st.tone}>{st.label}</Badge> #{p.id} {p.title}
        </span>
      }
      actions={<span className="text-[11.5px] text-steel">{SOURCE_KO[p.source] ?? p.source}{p.agent ? ` · ${p.agent}` : ""} · {fmtTime(p.createdAt)} · 기준 v{p.baseVersion}{p.appliedVersion ? ` → v${p.appliedVersion}` : ""}</span>}
    >
      {p.summary ? <p className="mb-md text-[12.5px] text-steel">{p.summary}</p> : null}
      <fieldset>
        <legend className="mb-xs text-[12px] font-bold text-ink">연산 {p.ops.length}개{pending ? " — 체크를 풀면 그 연산은 빼고 적용합니다" : ""}</legend>
        <ul className="flex flex-col gap-1">
          {p.ops.map((o, i) => (
            <li key={p.opKeys[i] ?? i} className="flex items-start gap-xs text-[12.5px]">
              {pending ? (
                <input type="checkbox" className="mt-1" checked={!drop.has(i)} onChange={() => toggle(i)} aria-label={`연산 ${i + 1} 적용: ${opText(o)}`} />
              ) : (
                <span aria-hidden="true" className="mt-0.5 text-stone">·</span>
              )}
              <span className={drop.has(i) ? "text-stone line-through" : "text-charcoal"}>{opText(o)}</span>
            </li>
          ))}
        </ul>
      </fieldset>
      <dl className="mt-md grid grid-cols-2 gap-xs text-[12px] md:grid-cols-4">
        <div className="rounded-xl bg-surface-soft px-md py-2">
          <dt className="text-[11px] text-stone">개체 변화(예상)</dt>
          <dd className="font-bold text-ink tnum">{impact.nodesDelta === undefined ? "-" : `${impact.nodesDelta >= 0 ? "+" : ""}${impact.nodesDelta.toLocaleString("ko-KR")}`}</dd>
        </div>
        <div className="rounded-xl bg-surface-soft px-md py-2">
          <dt className="text-[11px] text-stone">관계 변화(예상)</dt>
          <dd className="font-bold text-ink tnum">{impact.relationsDelta === undefined ? "-" : `${impact.relationsDelta >= 0 ? "+" : ""}${impact.relationsDelta.toLocaleString("ko-KR")}`}</dd>
        </div>
        <div className="rounded-xl bg-surface-soft px-md py-2">
          <dt className="text-[11px] text-stone">검증</dt>
          <dd className="font-bold text-ink">{p.validation.errors?.length ? `오류 ${p.validation.errors.length}` : "통과"}{p.validation.warnings?.length ? ` · 주의 ${p.validation.warnings.length}` : ""}</dd>
        </div>
        <div className="rounded-xl bg-surface-soft px-md py-2">
          <dt className="text-[11px] text-stone">끊긴 관계 변화</dt>
          <dd className="font-bold text-ink">{Object.keys(impact.dangling ?? {}).length ? Object.entries(impact.dangling ?? {}).map(([k, v]) => `${k} ${v}`).join(" · ") : "없음"}</dd>
        </div>
      </dl>
      {p.validation.errors?.length ? <p className="mt-xs text-[12px] text-critical">{p.validation.errors.join(" · ")}</p> : null}
      {p.validation.warnings?.length ? <p className="mt-xs text-[11.5px] text-attention">{p.validation.warnings.slice(0, 5).join(" · ")}</p> : null}
      {Object.keys(ev).length ? (
        <details className="mt-md text-[12px]">
          <summary className="cursor-pointer font-bold text-steel">근거 보기</summary>
          <pre className="mt-xs max-h-[220px] overflow-auto rounded-lg bg-surface-soft p-md font-mono text-[11px] text-charcoal">{JSON.stringify(ev, null, 2)}</pre>
        </details>
      ) : null}
      {pending ? (
        <div className="mt-md flex flex-wrap items-end gap-xs border-t border-hairline-soft pt-md">
          <Button size="sm" variant="confirm" disabled={busy || drop.size === p.ops.length} onClick={() => run(() => apiPost(`/admin/ontology/proposals/${p.id}/decide`, { approve: true, drop: [...drop] }), `제안 #${p.id} 을 새 스키마 판으로 적용했습니다`, reload)}>
            {drop.size ? `${p.ops.length - drop.size}개 연산 승인 · 적용` : "승인 · 적용"}
          </Button>
          <TextInput label="반려 사유" value={note} onChange={setNote} placeholder="예: 우연한 일치 — 같은 대상 아님" className="min-w-[280px] flex-1" />
          <Button size="sm" variant="danger" disabled={busy || !note.trim()} onClick={() => run(() => apiPost(`/admin/ontology/proposals/${p.id}/decide`, { approve: false, note }), `제안 #${p.id} 을 반려했습니다`, reload)}>
            반려
          </Button>
        </div>
      ) : p.decidedAt ? (
        <div className="mt-md flex flex-wrap items-center gap-xs">
          <p className="min-w-0 flex-1 text-[11.5px] text-stone">{p.decidedBy ?? "-"} · {fmtTime(p.decidedAt)}{p.note ? ` · ${p.note}` : ""}</p>
          {p.status === "rejected" ? (
            <Button size="sm" variant="ghost" disabled={busy} onClick={() => run(() => apiPost(`/admin/ontology/proposals/${p.id}/reopen`), `제안 #${p.id} 을 다시 승인 대기로 돌렸습니다`, reload)}>
              다시 검토
            </Button>
          ) : null}
        </div>
      ) : null}
    </Card>
  );
}
