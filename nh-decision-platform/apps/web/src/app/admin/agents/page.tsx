"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { AdminPage, Card, Check, Collapse, JsonView, Loading, Select, StatusBadge, Tabs, TextInput, fmtTime, useAction, useApiData } from "@/components/admin/kit";
import { Badge, Button } from "@/components/ui/primitives";
import { apiPatch, apiPost } from "@/lib/api-client";

interface Agent {
  code: string;
  name: string;
  role: string;
  kind: "llm" | "rule";
  groupCode: string | null;
  profileId: number | null;
  override: Record<string, unknown>;
  enabled: boolean;
  promptVersion: number | null;
  resolved: Record<string, unknown> & { ok: boolean; reason?: string };
  prompts: { version: number; system: string; userTemplate: string; note: string | null; createdBy: string | null; createdAt: string }[];
  stats: { calls: number; avgLatencyMs: number | null };
}
interface LlmData {
  connections: { id: number; name: string }[];
  profiles: { id: number; name: string; model: string }[];
}

interface GroupSummary {
  agents: number;
  llm: number;
  rule: number;
  enabled: number;
  calls24h: number;
  errors24h: number;
  errorRate: number | null;
  avgLatencyMs: number | null;
  tokens24h: number;
}
interface GroupsData {
  groups: { code: string; name: string; description: string; sort: number; agents: string[]; summary: GroupSummary }[];
  ungrouped: { agents: string[]; summary: GroupSummary };
  stats: Record<string, { calls: number; errors: number; skipped: number; avgLatencyMs: number | null; tokens: number }>;
}
type GroupOpt = { value: string; label: string };
const NONE = "__none";

/** 에이전트별 LiteLLM 연결 · 키 · 모델 · 파라미터 · 프롬프트 (ADM-06, LLM-02) — 기능 그룹 탭 · 그룹 요약 · 일괄 적용 (Phase M · AGG-02) */
export default function AgentsAdmin() {
  const agents = useApiData<Agent[]>("/admin/agents");
  const groups = useApiData<GroupsData>("/admin/agent-groups");
  const llm = useApiData<LlmData>("/admin/llm");
  const [tab, setTab] = useState<string>("");
  const reload = async () => {
    await Promise.all([agents.reload(), groups.reload()]);
  };
  const tabs = useMemo(() => {
    const g = (groups.data?.groups ?? []).filter((x) => x.agents.length > 0).map((x) => ({ key: x.code, label: x.name, count: x.agents.length }));
    const loose = groups.data?.ungrouped.agents.length ?? 0;
    return loose ? [...g, { key: NONE, label: "그룹 없음", count: loose }] : g;
  }, [groups.data]);
  const active = tab && tabs.some((t) => t.key === tab) ? tab : (tabs[0]?.key ?? "");
  const group = groups.data?.groups.find((g) => g.code === active);
  const members = new Set(active === NONE ? (groups.data?.ungrouped.agents ?? []) : (group?.agents ?? []));
  const list = (agents.data ?? []).filter((a) => members.has(a.code));
  const groupOpts: GroupOpt[] = [{ value: "", label: "(그룹 없음)" }, ...(groups.data?.groups ?? []).map((g) => ({ value: g.code, label: g.name }))];
  return (
    <AdminPage
      title="에이전트·프롬프트"
      description="에이전트를 기능 그룹으로 나눠 봅니다. 에이전트마다 연결(키 · URL)과 모델 · 파라미터를 따로 지정할 수 있고, 비워 둔 값은 프로필 값을 따릅니다(override > 프로필 > 기본 프로필). 그룹 일괄 적용은 그 그룹 LLM 에이전트의 override 에 같은 값을 넣습니다. 실행 시점의 값은 호출 기록에 스냅샷으로 남습니다."
      actions={
        <Link href="/admin/agentic" className="text-[12.5px] font-bold text-primary">
          에이전틱 파이프라인 보기
        </Link>
      }
    >
      <Loading error={agents.error || groups.error} loading={(!agents.data && agents.loading) || (!groups.data && groups.loading)} />
      {tabs.length ? <Tabs tabs={tabs} active={active} onChange={setTab} /> : null}
      {active ? (
        <GroupHeader
          key={active}
          code={active}
          name={group?.name ?? "그룹 없음"}
          description={group?.description ?? "기능 그룹을 정하지 않은 에이전트입니다. 카드의 [그룹]에서 옮길 수 있습니다."}
          summary={active === NONE ? groups.data?.ungrouped.summary : group?.summary}
          llmAgents={list.filter((a) => a.kind === "llm")}
          llm={llm.data}
          canApply={active !== NONE}
          reload={reload}
        />
      ) : null}
      {list.map((a) => (
        <AgentCard key={a.code} a={a} llm={llm.data} groups={groupOpts} reload={reload} />
      ))}
    </AdminPage>
  );
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: "warn" }) {
  return (
    <div className="min-w-[96px] rounded-xl bg-surface-soft px-md py-2">
      <p className="text-[11px] text-stone">{label}</p>
      <p className={`text-[15px] font-bold tnum ${tone === "warn" ? "text-critical" : "text-ink"}`}>{value}</p>
    </div>
  );
}

const APPLY_KEYS = ["connection_id", "model", "temperature", "max_tokens", "timeout_sec", "retries"] as const;

function GroupHeader({ code, name, description, summary, llmAgents, llm, canApply, reload }: {
  code: string; name: string; description: string; summary?: GroupSummary; llmAgents: Agent[]; llm: LlmData | null; canApply: boolean; reload: () => Promise<void>;
}) {
  const { run, busy } = useAction();
  const [form, setForm] = useState<Record<string, string>>(() => Object.fromEntries(APPLY_KEYS.map((k) => [k, ""])));
  // 뺀 에이전트만 기억한다 — 목록이 나중에 불러와져도 그룹의 LLM 에이전트 전체가 기본으로 골라져 있다
  const [excluded, setExcluded] = useState<Set<string>>(() => new Set());
  const picked = new Set(llmAgents.map((a) => a.code).filter((c) => !excluded.has(c)));
  const s = summary;
  const apply = () => {
    const ov: Record<string, unknown> = {};
    for (const k of APPLY_KEYS) {
      const v = form[k].trim();
      if (!v) continue;
      ov[k] = k === "model" ? v : Number(v);
    }
    if (!Object.keys(ov).length) return Promise.resolve(undefined);
    return run(() => apiPost(`/admin/agent-groups/${code}/apply`, { override: ov, agents: [...picked] }), `${name} 그룹 ${picked.size}개 에이전트에 적용했습니다`, reload);
  };
  return (
    <Card title={<span className="flex items-center gap-xs">{name} <code className="font-mono text-[11px] text-stone">{code === NONE ? "-" : code}</code></span>}>
      <p className="mb-md text-[12.5px] text-steel">{description}</p>
      {s ? (
        <div className="flex flex-wrap gap-xs" aria-label={`${name} 그룹 요약`}>
          <Stat label="에이전트" value={`${s.agents}개`} />
          <Stat label="LLM · 규칙" value={`${s.llm} · ${s.rule}`} />
          <Stat label="사용 중" value={`${s.enabled}개`} />
          <Stat label="24시간 호출" value={`${s.calls24h.toLocaleString()}회`} />
          <Stat label="오류율" value={s.errorRate == null ? "-" : `${s.errorRate}%`} tone={s.errorRate && s.errorRate >= 20 ? "warn" : undefined} />
          <Stat label="평균 지연" value={s.avgLatencyMs == null ? "-" : `${s.avgLatencyMs.toLocaleString()}ms`} />
          <Stat label="24시간 토큰" value={s.tokens24h.toLocaleString()} />
        </div>
      ) : null}
      {canApply && llmAgents.length ? (
        <div className="mt-lg border-t border-hairline-soft pt-md">
          <p className="mb-xs text-[12.5px] font-bold text-ink">그룹 일괄 적용</p>
          <p className="mb-md text-[11.5px] text-stone">입력한 항목만 고른 LLM 에이전트의 덮어쓰기에 넣습니다. 비워 둔 항목은 바꾸지 않습니다. 되돌리려면 카드에서 값을 지우고 저장하세요.</p>
          <div className="grid grid-cols-2 gap-md md:grid-cols-3 xl:grid-cols-6">
            <Select label="연결" value={form.connection_id} onChange={(v) => setForm({ ...form, connection_id: v })} options={[{ value: "", label: "(바꾸지 않음)" }, ...(llm?.connections ?? []).map((c) => ({ value: String(c.id), label: c.name }))]} />
            <TextInput label="모델" value={form.model} onChange={(v) => setForm({ ...form, model: v })} mono placeholder="(바꾸지 않음)" />
            <TextInput label="temperature" value={form.temperature} onChange={(v) => setForm({ ...form, temperature: v })} type="number" />
            <TextInput label="max_tokens" value={form.max_tokens} onChange={(v) => setForm({ ...form, max_tokens: v })} type="number" />
            <TextInput label="timeout(s)" value={form.timeout_sec} onChange={(v) => setForm({ ...form, timeout_sec: v })} type="number" />
            <TextInput label="재시도" value={form.retries} onChange={(v) => setForm({ ...form, retries: v })} type="number" />
          </div>
          <fieldset className="mt-md flex flex-wrap items-center gap-md">
            <legend className="sr-only">적용할 에이전트</legend>
            {llmAgents.map((a) => (
              <Check key={a.code} label={a.name} checked={picked.has(a.code)} onChange={(v) => setExcluded((p) => { const n = new Set(p); if (v) n.delete(a.code); else n.add(a.code); return n; })} />
            ))}
          </fieldset>
          <div className="mt-md">
            <Button size="sm" variant="confirm" disabled={busy || !picked.size || !APPLY_KEYS.some((k) => form[k].trim())} onClick={apply}>
              고른 {picked.size}개에 적용
            </Button>
          </div>
        </div>
      ) : null}
    </Card>
  );
}

const OV_KEYS = ["connection_id", "model", "temperature", "top_p", "max_tokens", "timeout_sec", "retries"] as const;

function AgentCard({ a, llm, groups, reload }: { a: Agent; llm: LlmData | null; groups: GroupOpt[]; reload: () => Promise<void> }) {
  const { run, busy } = useAction();
  const [ov, setOv] = useState<Record<string, string>>(() => Object.fromEntries(OV_KEYS.map((k) => [k, a.override[k] === undefined || a.override[k] === null ? "" : String(a.override[k])])));
  const [tools, setTools] = useState<string>(a.override.tools_enabled === undefined ? "" : String(a.override.tools_enabled));
  const latest = a.prompts[0];
  const [sys, setSys] = useState(latest?.system ?? "");
  const [tmpl, setTmpl] = useState(latest?.userTemplate ?? "");
  const [ask, setAsk] = useState("");
  const [answer, setAnswer] = useState<unknown>(null);

  const saveOverride = () => {
    const out: Record<string, unknown> = {};
    for (const k of OV_KEYS) {
      const v = ov[k].trim();
      if (!v) continue;
      out[k] = ["connection_id", "max_tokens", "retries"].includes(k) ? Number(v) : ["temperature", "top_p", "timeout_sec"].includes(k) ? Number(v) : v;
    }
    if (tools) out.tools_enabled = tools === "true";
    return run(() => apiPatch(`/admin/agents/${a.code}`, { override: out }), "에이전트 설정을 저장했습니다", reload);
  };

  return (
    <Card
      title={
        <span className="flex flex-wrap items-center gap-xs">
          {a.name} <code className="font-mono text-[11px] text-stone">{a.code}</code> <Badge tone={a.kind === "llm" ? "info" : "neutral"}>{a.kind === "llm" ? "LLM" : "규칙"}</Badge>
          {a.kind === "llm" ? <StatusBadge status={a.resolved.ok ? "ok" : "warning"} label={a.resolved.ok ? `${a.resolved.model} · ${a.resolved.connection}` : `미설정 — ${a.resolved.reason}`} /> : null}
        </span>
      }
      actions={
        <>
          <span className="text-[11px] text-stone">호출 {a.stats.calls}회{a.stats.avgLatencyMs ? ` · 평균 ${a.stats.avgLatencyMs}ms` : ""}</span>
          <Select ariaLabel={`${a.name} 그룹`} value={a.groupCode ?? ""} onChange={(v) => run(() => apiPatch(`/admin/agents/${a.code}`, { group_code: v }), "그룹을 바꿨습니다", reload)} options={groups} />
          <Check label="사용" checked={a.enabled} onChange={(v) => run(() => apiPatch(`/admin/agents/${a.code}`, { enabled: v }), "저장했습니다", reload)} />
        </>
      }
    >
      <p className="mb-md text-[12.5px] text-steel">{a.role}</p>
      {a.kind === "llm" ? (
        <>
          <div className="grid grid-cols-2 gap-md md:grid-cols-4 xl:grid-cols-9">
            <Select label="프로필" value={String(a.profileId ?? "")} onChange={(v) => run(() => apiPatch(`/admin/agents/${a.code}`, { profile_id: v ? Number(v) : null }), "프로필을 바꿨습니다", reload)} options={[{ value: "", label: "(기본 프로필)" }, ...(llm?.profiles ?? []).map((p) => ({ value: String(p.id), label: `${p.name}${p.model ? ` · ${p.model}` : ""}` }))]} className="xl:col-span-2" />
            <Select label="연결 덮어쓰기" value={ov.connection_id} onChange={(v) => setOv({ ...ov, connection_id: v })} options={[{ value: "", label: "(프로필 값)" }, ...(llm?.connections ?? []).map((c) => ({ value: String(c.id), label: c.name }))]} />
            <TextInput label="모델" value={ov.model} onChange={(v) => setOv({ ...ov, model: v })} mono placeholder="(프로필 값)" className="xl:col-span-2" />
            <TextInput label="temperature" value={ov.temperature} onChange={(v) => setOv({ ...ov, temperature: v })} type="number" />
            <TextInput label="top_p" value={ov.top_p} onChange={(v) => setOv({ ...ov, top_p: v })} type="number" />
            <TextInput label="max_tokens" value={ov.max_tokens} onChange={(v) => setOv({ ...ov, max_tokens: v })} type="number" />
            <TextInput label="timeout(s)" value={ov.timeout_sec} onChange={(v) => setOv({ ...ov, timeout_sec: v })} type="number" />
            <TextInput label="재시도" value={ov.retries} onChange={(v) => setOv({ ...ov, retries: v })} type="number" />
            <Select label="도구 호출" value={tools} onChange={setTools} options={[{ value: "", label: "(프로필 값)" }, { value: "true", label: "사용" }, { value: "false", label: "미사용" }]} />
          </div>
          <div className="mt-md flex flex-wrap items-center gap-xs">
            <Button size="sm" variant="confirm" disabled={busy} onClick={saveOverride}>
              덮어쓰기 저장
            </Button>
            <span className="text-[11.5px] text-stone">
              적용 값: {a.resolved.ok ? `${a.resolved.baseUrl} · ${a.resolved.model} · ${JSON.stringify(a.resolved.params)} · 키 ${a.resolved.apiKeyMasked || "없음"}` : "-"}
            </span>
          </div>
          <div className="mt-lg grid grid-cols-1 gap-md lg:grid-cols-2">
            <label className="block">
              <span className="mb-1 block text-[11.5px] font-bold text-steel">시스템 프롬프트 {latest ? `(현재 v${a.promptVersion ?? latest.version})` : ""}</span>
              <textarea className="input text-[12px]" rows={7} value={sys} onChange={(e) => setSys(e.target.value)} />
            </label>
            <label className="block">
              <span className="mb-1 block text-[11.5px] font-bold text-steel">사용자 템플릿 (비우면 노드 기본 템플릿 · {"{figures} {evidence} {current} {instruction}"} 등)</span>
              <textarea className="input font-mono text-[11.5px]" rows={7} value={tmpl} onChange={(e) => setTmpl(e.target.value)} />
            </label>
          </div>
          <div className="mt-xs flex flex-wrap items-center gap-xs">
            <Button size="sm" variant="confirm" disabled={busy} onClick={() => run(() => apiPost(`/admin/agents/${a.code}/prompts`, { system: sys, user_template: tmpl, note: "관리자 수정" }), "새 프롬프트 버전을 적용했습니다", reload)}>
              새 버전으로 저장
            </Button>
            <Collapse label={`버전 이력 ${a.prompts.length}건`}>
              <ul className="space-y-1 text-[11.5px] text-steel">
                {a.prompts.map((p) => (
                  <li key={p.version}>
                    v{p.version} · {p.createdBy ?? "-"} · {fmtTime(p.createdAt)} · {p.note ?? ""}{" "}
                    <button type="button" className="font-bold text-primary" onClick={() => run(() => apiPatch(`/admin/agents/${a.code}`, { prompt_version: p.version }), `v${p.version} 을 적용했습니다`, reload)}>
                      적용
                    </button>
                  </li>
                ))}
              </ul>
            </Collapse>
          </div>
          <div className="mt-lg border-t border-hairline-soft pt-md">
            <div className="flex flex-wrap items-end gap-xs">
              <TextInput label="시험 호출" value={ask} onChange={setAsk} placeholder={a.code === "query_assistant" ? "예: 부도 196건, 관측 2472건이면 부도율은?" : "메시지"} className="min-w-[360px] flex-1" />
              <Button size="sm" variant="quiet" disabled={busy || !ask} onClick={() => run(() => apiPost(`/admin/agents/${a.code}/ask`, { message: ask, use_tools: true }), undefined).then((r) => r && setAnswer(r))}>
                보내기
              </Button>
            </div>
            {answer ? (
              <div className="mt-md">
                <JsonView value={answer} maxHeight={260} />
              </div>
            ) : null}
          </div>
        </>
      ) : (
        <p className="text-[12px] text-stone">규칙 기반 에이전트입니다(LLM 을 부르지 않음). 기준은 [판정 규칙](예: CRITIC_RULES) · [운영 설정](예: ontology.build)에서 관리합니다.</p>
      )}
    </Card>
  );
}
