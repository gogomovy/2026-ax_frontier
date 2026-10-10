"use client";

import Link from "next/link";
import { useState } from "react";
import { AdminPage, C, Card, Check, Collapse, JsonEditor, JsonView, Loading, Select, StatusBadge, Table, TextInput, fmtTime, useAction, useApiData } from "@/components/admin/kit";
import { Badge, Button } from "@/components/ui/primitives";
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

/** 워크플로우 노드 · 트리거 · 수동 실행 · 영향 미리보기 (ADM-07, EVT-01~05) */
export default function WorkflowsAdmin() {
  const data = useApiData<Data>("/admin/workflows", { refreshMs: 8000 });
  const agents = useApiData<{ code: string; name: string }[]>("/admin/agents");
  const datasets = useApiData<{ code: string; name: string }[]>("/admin/datasets");
  const [impactDs, setImpactDs] = useState("");
  const [impact, setImpact] = useState<unknown>(null);

  return (
    <AdminPage
      title="워크플로우"
      description="데이터가 바뀌면 트리거와 계보(지표·바인딩이 참조하는 데이터셋)가 맞는 워크플로우만 실행됩니다. 연속 변경은 디바운스 시간 안에서 1회 실행으로 병합됩니다."
    >
      <Card title="영향 미리보기 — 이 데이터셋이 바뀌면?">
        <div className="flex flex-wrap items-end gap-xs">
          <Select label="데이터셋" value={impactDs} onChange={setImpactDs} options={[{ value: "", label: "선택" }, ...(datasets.data ?? []).map((d) => ({ value: d.code, label: `${d.code} · ${d.name}` }))]} className="min-w-[320px]" />
          <Button size="sm" variant="quiet" disabled={!impactDs} onClick={() => apiGetC(`/admin/impact?dataset=${encodeURIComponent(impactDs)}`).then(setImpact)}>
            확인
          </Button>
        </div>
        {impact ? (
          <div className="mt-md">
            <JsonView value={impact} maxHeight={240} />
          </div>
        ) : null}
      </Card>
      <Loading error={data.error} loading={!data.data && data.loading} />
      {(data.data?.workflows ?? []).map((w) => (
        <WorkflowCard key={w.code} w={w} impls={data.data?.impls ?? []} kinds={data.data?.triggerKinds ?? []} agents={agents.data ?? []} reload={data.reload} />
      ))}
    </AdminPage>
  );
}

function WorkflowCard({ w, impls, kinds, agents, reload }: { w: Wf; impls: Data["impls"]; kinds: string[]; agents: { code: string; name: string }[]; reload: () => Promise<void> }) {
  const { run, busy } = useAction();
  const [trig, setTrig] = useState({ kind: "dataset", target: "", debounce_sec: "" });
  const base = `/admin/workflows/${w.code}`;
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
      <p className="mb-md text-[11.5px] text-stone">산출물: {w.outputs.join(", ") || "-"}</p>

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
              <Mono2>{n.impl}</Mono2>
              <p className="text-[10.5px] text-stone">{n.implDescription}</p>
            </C>
            <C className="min-w-[160px]">
              <Select value={n.agentCode ?? ""} onChange={(v) => run(() => apiPatch(`${base}/nodes/${n.id}`, { agent_code: v || null }), "담당 에이전트를 바꿨습니다", reload)} options={[{ value: "", label: "-" }, ...agents.map((a) => ({ value: a.code, label: a.name }))]} />
            </C>
            <C>
              <Check label="" checked={n.enabled} onChange={(v) => run(() => apiPatch(`${base}/nodes/${n.id}`, { enabled: v }), v ? "노드를 켰습니다" : "노드를 껐습니다(skipped)", reload)} />
            </C>
            <C className="min-w-[320px]">
              <Collapse label="설정 JSON">
                <JsonEditor value={n.config} rows={8} disabled={busy} onSave={(v) => run(() => apiPatch(`${base}/nodes/${n.id}`, { config: v }), "노드 설정을 저장했습니다", reload)} />
              </Collapse>
            </C>
          </tr>
        ))}
      </Table>
      <Collapse label="노드 추가">
        <NodeAdd impls={impls} onAdd={(body) => run(() => apiPost(`${base}/nodes`, body), "노드를 추가했습니다", reload)} />
      </Collapse>

      <p className="mb-xs mt-lg text-[12.5px] font-bold text-ink-deep">트리거</p>
      <Table head={["종류", "대상", "디바운스(초)", "정기 실행", "사용", ""]}>
        {w.triggers.map((t) => (
          <tr key={t.id}>
            <C>
              <Badge>{t.kind}</Badge>
            </C>
            <C mono>{t.target}</C>
            <C right>{t.kind === "cron" ? "-" : (t.debounceSec ?? "기본값")}</C>
            <C className="text-[11px]">
              {t.kind === "cron" ? (t.nextFireAt === "invalid" ? <span className="text-critical">식 오류</span> : `다음 ${fmtTime(t.nextFireAt)} · 최근 ${fmtTime(t.lastFiredAt)}`) : "-"}
            </C>
            <C>
              <Check label="" checked={t.enabled} onChange={(v) => run(() => apiPatch(`${base}/triggers/${t.id}`, { enabled: v }), "저장했습니다", reload)} />
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
        <Select label="종류" value={trig.kind} onChange={(v) => setTrig({ ...trig, kind: v })} options={kinds.map((k) => ({ value: k, label: k }))} />
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
                  #{j.id} <StatusBadge status={j.status} /> 실행 예정 {fmtTime(j.runAfter)} · 원인 {j.causes}건
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
                <StatusBadge status={r.status} /> 원인 {r.causes}건
              </li>
            ))}
          </ul>
        </div>
      </div>
    </Card>
  );
}

function Mono2({ children }: { children: React.ReactNode }) {
  return <code className="font-mono text-[11.5px] text-ink-deep">{children}</code>;
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
