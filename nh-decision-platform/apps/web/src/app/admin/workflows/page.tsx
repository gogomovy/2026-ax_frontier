"use client";

import Link from "next/link";
import { useState } from "react";
import { AdminPage, C, Card, Check, Collapse, JsonEditor, JsonView, Loading, Select, StatusBadge, Table, TextInput, fmtTime, useAction, useApiData } from "@/components/admin/kit";
import { Advanced, EmptyState } from "@/components/ui/Layout";
import { Badge, Button } from "@/components/ui/primitives";
import { StatCard, StatGrid } from "@/components/ui/StatCard";
import { apiDelete, apiGetC, apiPatch, apiPost } from "@/lib/api-client";

interface Wf {
  code: string;
  name: string;
  description: string;
  enabled: boolean;
  outputs: string[];
  metrics: number;
  nodes: { id: number; seq: number; key: string; name: string; impl: string; implDescription: string | null; agentCode: string | null; enabled: boolean; config: Record<string, unknown> }[];
  triggers: { id: number; kind: string; target: string; debounceSec: number | null; enabled: boolean; lastFiredAt: string | null; nextFireAt: string | null }[];
  recentRuns: { id: string; status: string; startedAt: string; finishedAt: string | null; causes: number }[];
  pendingJobs: { id: number; status: string; runAfter: string; causes: number }[];
}
interface Data {
  workflows: Wf[];
  impls: { key: string; description: string }[];
  triggerKinds: string[];
}
interface Impact {
  matched: { workflow?: string; reasons?: string[]; note?: string }[];
  graph?: { workflow?: string; code?: string; via?: string }[];
  graph_error?: string;
}

const KIND_LABEL: Record<string, string> = { dataset: "자료", document: "문서", event: "이벤트", rule: "규칙", config: "설정", cron: "정기 실행", ontology: "온톨로지" };
const STATUS_LABEL: Record<string, string> = { succeeded: "성공", degraded: "축소", failed: "실패", running: "실행 중", queued: "대기", approval: "승인 대기" };

/** 워크플로 — 목록 요약(노드 흐름 · 트리거 · 최근 실행) → 펼쳐서 노드 · 트리거 편집 · 수동 실행 · 영향 미리보기 (ADM-07, EVT-01~05, ADM-03) */
export default function WorkflowsAdmin() {
  const data = useApiData<Data>("/admin/workflows", { refreshMs: 8000 });
  const agents = useApiData<{ code: string; name: string }[]>("/admin/agents");
  const datasets = useApiData<{ code: string; name: string }[]>("/admin/datasets");
  const [impactDs, setImpactDs] = useState("");
  const [impact, setImpact] = useState<Impact | null>(null);
  const [q, setQ] = useState("");
  const wfs = data.data?.workflows ?? [];
  const list = wfs.filter((w) => !q || `${w.code} ${w.name} ${w.description}`.toLowerCase().includes(q.toLowerCase()));
  const enabled = wfs.filter((w) => w.enabled).length;
  const pending = wfs.reduce((n, w) => n + w.pendingJobs.length, 0);
  const lastFailed = wfs.filter((w) => w.recentRuns[0]?.status === "failed").length;
  const cron = wfs.filter((w) => w.triggers.some((t) => t.kind === "cron" && t.enabled)).length;

  return (
    <AdminPage
      title="워크플로"
      description="데이터가 바뀌면 트리거와 계보(지표 · 바인딩이 참조하는 데이터셋)가 맞는 워크플로만 실행됩니다. 연속 변경은 디바운스 시간 안에서 한 번 실행으로 합칩니다. 카드를 펼치면 노드 · 트리거를 고칠 수 있습니다."
      summary={
        <StatGrid columns={4} label="워크플로 요약">
          <StatCard label="사용 중" value={`${enabled}/${wfs.length || "-"}`} hint="꺼진 워크플로는 이벤트가 와도 실행하지 않음" />
          <StatCard label="대기 작업" value={pending} unit="건" tone={pending ? "info" : "default"} hint="디바운스 · 승인 대기 포함" />
          <StatCard label="최근 실행 실패" value={lastFailed} unit="개" tone={lastFailed ? "critical" : "success"} hint={lastFailed ? "마지막 실행이 실패한 워크플로" : "마지막 실행 모두 정상"} />
          <StatCard label="정기 실행" value={cron} unit="개" hint="cron 트리거가 켜진 워크플로" />
        </StatGrid>
      }
    >
      <Card title="영향 미리보기 — 이 데이터셋이 바뀌면 어떤 워크플로가 실행되나요?">
        <div className="flex flex-wrap items-end gap-xs">
          <Select label="데이터셋" value={impactDs} onChange={setImpactDs} options={[{ value: "", label: "선택" }, ...(datasets.data ?? []).map((d) => ({ value: d.code, label: `${d.code} · ${d.name}` }))]} className="min-w-[320px]" />
          <Button size="sm" variant="quiet" disabled={!impactDs} onClick={() => apiGetC<Impact>(`/admin/impact?dataset=${encodeURIComponent(impactDs)}`).then(setImpact)}>
            확인
          </Button>
        </div>
        {impact ? (
          <div className="mt-md flex flex-col gap-xs" data-impact>
            {impact.matched.filter((m) => m.workflow).length ? (
              <ul className="flex flex-col gap-1 text-[12.5px]">
                {impact.matched
                  .filter((m) => m.workflow)
                  .map((m, i) => (
                    <li key={i} className="flex flex-wrap items-center gap-xs">
                      <Badge tone="info">실행</Badge>
                      <b className="text-ink-deep">{m.workflow}</b>
                      <span className="text-[11.5px] text-stone">{m.reasons?.join(" · ")}</span>
                    </li>
                  ))}
              </ul>
            ) : (
              <p className="text-[12.5px] text-steel">관련 워크플로가 없습니다 — 이 자료가 바뀌어도 아무것도 다시 계산하지 않습니다.</p>
            )}
            {impact.matched.filter((m) => m.note).map((m, i) => (
              <p key={i} className="text-[11.5px] text-stone">
                {m.note}
              </p>
            ))}
            {impact.graph_error ? <p className="text-[11.5px] text-stone">그래프 계보 확인 불가 — {impact.graph_error}</p> : null}
            <Advanced label="원본(JSON)">
              <JsonView value={impact} maxHeight={240} />
            </Advanced>
          </div>
        ) : null}
      </Card>
      <div className="mb-md flex flex-wrap items-center gap-xs">
        <TextInput ariaLabel="워크플로 찾기" placeholder="코드 · 이름으로 찾기" value={q} onChange={setQ} className="w-[260px]" />
        <span className="text-[12px] text-stone">{list.length}개</span>
      </div>
      <Loading error={data.error} loading={!data.data && data.loading} />
      {data.data && !list.length ? <EmptyState title="맞는 워크플로가 없습니다" description="찾는 말을 바꿔 보세요." /> : null}
      {list.map((w) => (
        <WorkflowCard key={w.code} w={w} impls={data.data?.impls ?? []} kinds={data.data?.triggerKinds ?? []} agents={agents.data ?? []} reload={data.reload} />
      ))}
    </AdminPage>
  );
}

function triggerText(t: Wf["triggers"][number]) {
  if (t.kind === "cron") return t.nextFireAt === "invalid" ? `정기 ${t.target} · 식 오류` : `정기 ${t.target} · 다음 ${fmtTime(t.nextFireAt)}`;
  return `${KIND_LABEL[t.kind] ?? t.kind} ${t.target}`;
}

function WorkflowCard({ w, impls, kinds, agents, reload }: { w: Wf; impls: Data["impls"]; kinds: string[]; agents: { code: string; name: string }[]; reload: () => Promise<void> }) {
  const { run, busy } = useAction();
  const [open, setOpen] = useState(false);
  const [trig, setTrig] = useState({ kind: "dataset", target: "", debounce_sec: "" });
  const base = `/admin/workflows/${w.code}`;
  const last = w.recentRuns[0];
  const bodyId = `wf-${w.code}`;
  return (
    <Card
      title={
        <span className="flex flex-wrap items-center gap-xs">
          {w.name} <code className="font-mono text-[11px] text-stone">{w.code}</code>
          <StatusBadge status={w.enabled ? "active" : "disabled"} label={w.enabled ? "사용" : "중지"} />
          <Badge>지표 {w.metrics}</Badge>
        </span>
      }
      actions={
        <>
          <Check label="사용" checked={w.enabled} onChange={(v) => run(() => apiPatch(base, { enabled: v }), "저장했습니다", reload)} />
          <Button size="sm" variant="confirm" disabled={busy} onClick={() => run(() => apiPost(`${base}/run`), "실행을 요청했습니다 — 데이터 흐름에서 확인하세요", reload)}>
            지금 실행
          </Button>
        </>
      }
    >
      <p className="mb-md text-[12.5px] text-steel">{w.description}</p>
      {/* 노드 흐름 — 순서대로 */}
      <ol className="mb-md flex flex-wrap items-center gap-1 text-[11.5px]" aria-label="노드 순서">
        {w.nodes.map((n, i) => (
          <li key={n.id} className="flex items-center gap-1">
            <span className={`rounded-md border px-1.5 py-0.5 ${n.enabled ? "border-hairline-soft bg-surface-soft text-charcoal" : "border-dashed border-hairline text-stone line-through"}`} title={n.implDescription ?? n.impl}>
              {n.name}
            </span>
            {i < w.nodes.length - 1 ? <span aria-hidden="true" className="text-stone">→</span> : null}
          </li>
        ))}
      </ol>
      <div className="grid grid-cols-1 gap-md text-[12px] md:grid-cols-3">
        <div>
          <p className="mb-1 text-[11.5px] font-bold text-steel">언제 실행되나요</p>
          {w.triggers.length ? (
            <ul className="flex flex-col gap-0.5 text-charcoal">
              {w.triggers.map((t) => (
                <li key={t.id} className={t.enabled ? "" : "text-stone line-through"}>
                  {triggerText(t)}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-stone">트리거 없음 — 계보로만 실행</p>
          )}
        </div>
        <div>
          <p className="mb-1 text-[11.5px] font-bold text-steel">최근 실행</p>
          {last ? (
            <p>
              <StatusBadge status={last.status} label={STATUS_LABEL[last.status] ?? last.status} />{" "}
              <Link href={`/admin/monitor/runs?run=${last.id}`} className="font-bold text-primary">
                {fmtTime(last.startedAt)}
              </Link>
            </p>
          ) : (
            <p className="text-stone">아직 없음</p>
          )}
          {w.pendingJobs.length ? <p className="mt-0.5 text-steel">대기 {w.pendingJobs.length}건 · 다음 {fmtTime(w.pendingJobs[0].runAfter)}</p> : null}
        </div>
        <div>
          <p className="mb-1 text-[11.5px] font-bold text-steel">화면 산출물</p>
          <p className="break-words font-mono text-[11px] text-charcoal">{w.outputs.join(", ") || "-"}</p>
        </div>
      </div>
      <div className="mt-md">
        <button type="button" aria-expanded={open} aria-controls={bodyId} onClick={() => setOpen((v) => !v)} className="text-[12px] font-bold text-primary">
          {open ? "▾ 노드 · 트리거 편집 닫기" : "▸ 노드 · 트리거 편집"}
        </button>
      </div>
      {open ? (
        <div id={bodyId} className="mt-md">
          <p className="mb-xs text-[12.5px] font-bold text-ink-deep">노드</p>
          <Table head={["순서", "노드", "구현", "담당 에이전트", "사용", "설정"]}>
            {w.nodes.map((n) => (
              <tr key={n.id} className={n.enabled ? "" : "opacity-50"}>
                <C right>{n.seq}</C>
                <C>
                  <span className="font-bold text-ink-deep">{n.name}</span>
                  <p className="font-mono text-[10.5px] text-stone">{n.key}</p>
                </C>
                <C className="max-w-[260px]">
                  <code className="font-mono text-[11.5px] text-ink-deep">{n.impl}</code>
                  <p className="text-[10.5px] text-stone">{n.implDescription}</p>
                </C>
                <C className="min-w-[160px]">
                  <Select ariaLabel={`${n.name} 담당 에이전트`} value={n.agentCode ?? ""} onChange={(v) => run(() => apiPatch(`${base}/nodes/${n.id}`, { agent_code: v || null }), "담당 에이전트를 바꿨습니다", reload)} options={[{ value: "", label: "-" }, ...agents.map((a) => ({ value: a.code, label: a.name }))]} />
                </C>
                <C>
                  <Check label="" ariaLabel={`${n.name} 사용`} checked={n.enabled} onChange={(v) => run(() => apiPatch(`${base}/nodes/${n.id}`, { enabled: v }), v ? "노드를 켰습니다" : "노드를 껐습니다(skipped)", reload)} />
                </C>
                <C className="min-w-[320px]">
                  <Collapse label="설정(JSON)">
                    <JsonEditor value={n.config} rows={8} disabled={busy} onSave={(v) => run(() => apiPatch(`${base}/nodes/${n.id}`, { config: v }), "노드 설정을 저장했습니다", reload)} />
                  </Collapse>
                </C>
              </tr>
            ))}
          </Table>
          <div className="mt-xs">
            <Collapse label="노드 추가">
              <NodeAdd impls={impls} onAdd={(body) => run(() => apiPost(`${base}/nodes`, body), "노드를 추가했습니다", reload)} />
            </Collapse>
          </div>

          <p className="mb-xs mt-lg text-[12.5px] font-bold text-ink-deep">트리거</p>
          <Table head={["종류", "대상", "디바운스(초)", "정기 실행", "사용", ""]}>
            {w.triggers.map((t) => (
              <tr key={t.id}>
                <C>
                  <Badge>{KIND_LABEL[t.kind] ?? t.kind}</Badge>
                </C>
                <C mono>{t.target}</C>
                <C right>{t.kind === "cron" ? "-" : (t.debounceSec ?? "기본값")}</C>
                <C className="text-[11px]">{t.kind === "cron" ? (t.nextFireAt === "invalid" ? <span className="text-critical">식 오류</span> : `다음 ${fmtTime(t.nextFireAt)} · 최근 ${fmtTime(t.lastFiredAt)}`) : "-"}</C>
                <C>
                  <Check label="" ariaLabel={`트리거 ${t.target} 사용`} checked={t.enabled} onChange={(v) => run(() => apiPatch(`${base}/triggers/${t.id}`, { enabled: v }), "저장했습니다", reload)} />
                </C>
                <C>
                  <Button size="sm" variant="quiet" disabled={busy} onClick={() => run(() => apiDelete(`${base}/triggers/${t.id}`), "삭제했습니다", reload)}>
                    삭제
                  </Button>
                </C>
              </tr>
            ))}
          </Table>
          <div className="mt-xs flex flex-wrap items-end gap-xs">
            <Select label="종류" value={trig.kind} onChange={(v) => setTrig({ ...trig, kind: v })} options={kinds.map((k) => ({ value: k, label: KIND_LABEL[k] ?? k }))} />
            <TextInput label="대상 (데이터셋 코드 · 문서 분류 · 이벤트 · 규칙 · 설정 키 · cron 식 예: 0 6 * * 1-5)" value={trig.target} onChange={(v) => setTrig({ ...trig, target: v })} mono className="min-w-[280px]" />
            <TextInput label="디바운스(초)" value={trig.debounce_sec} onChange={(v) => setTrig({ ...trig, debounce_sec: v })} type="number" />
            <Button size="sm" variant="confirm" disabled={busy || !trig.target} onClick={() => run(() => apiPost(`${base}/triggers`, { kind: trig.kind, target: trig.target, debounce_sec: trig.debounce_sec ? Number(trig.debounce_sec) : null }), "트리거를 추가했습니다", reload)}>
              트리거 추가
            </Button>
          </div>

          <div className="mt-lg grid grid-cols-1 gap-md lg:grid-cols-2">
            <div>
              <p className="mb-xs text-[12.5px] font-bold text-ink-deep">대기 작업</p>
              {w.pendingJobs.length ? (
                <ul className="text-[12px] text-charcoal">
                  {w.pendingJobs.map((j) => (
                    <li key={j.id}>
                      #{j.id} <StatusBadge status={j.status} label={STATUS_LABEL[j.status] ?? j.status} /> 실행 예정 {fmtTime(j.runAfter)} · 원인 {j.causes}건
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-[12px] text-stone">없음</p>
              )}
            </div>
            <div>
              <p className="mb-xs text-[12.5px] font-bold text-ink-deep">최근 실행</p>
              <ul className="space-y-0.5 text-[12px] text-charcoal">
                {w.recentRuns.map((r) => (
                  <li key={r.id}>
                    <Link href={`/admin/monitor/runs?run=${r.id}`} className="font-bold text-primary">
                      {fmtTime(r.startedAt)}
                    </Link>{" "}
                    <StatusBadge status={r.status} label={STATUS_LABEL[r.status] ?? r.status} /> 원인 {r.causes}건
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      ) : null}
    </Card>
  );
}

function NodeAdd({ impls, onAdd }: { impls: Data["impls"]; onAdd: (b: Record<string, unknown>) => void }) {
  const [f, setF] = useState({ key: "", name: "", impl: impls[0]?.key ?? "", seq: "100" });
  return (
    <div className="mt-xs flex flex-wrap items-end gap-xs">
      <TextInput label="키" value={f.key} onChange={(v) => setF({ ...f, key: v })} mono />
      <TextInput label="이름" value={f.name} onChange={(v) => setF({ ...f, name: v })} />
      <Select label="구현" value={f.impl} onChange={(v) => setF({ ...f, impl: v })} options={impls.map((i) => ({ value: i.key, label: i.key }))} />
      <TextInput label="순서" value={f.seq} onChange={(v) => setF({ ...f, seq: v })} type="number" />
      <Button size="sm" variant="confirm" disabled={!f.key || !f.name} onClick={() => onAdd({ key: f.key, name: f.name, impl: f.impl, seq: Number(f.seq), config: {} })}>
        추가
      </Button>
    </div>
  );
}
