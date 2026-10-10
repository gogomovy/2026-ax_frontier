"use client";

import { useState } from "react";
import { AdminPage, Card, Check, Collapse, JsonView, Loading, Select, StatusBadge, TextInput, fmtTime, useAction, useApiData } from "@/components/admin/kit";
import { Badge, Button } from "@/components/ui/primitives";
import { apiPatch, apiPost } from "@/lib/api-client";

interface Agent {
  code: string;
  name: string;
  role: string;
  kind: "llm" | "rule";
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

/** 에이전트별 LiteLLM 연결 · 키 · 모델 · 파라미터 · 프롬프트 (ADM-06, LLM-02) */
export default function AgentsAdmin() {
  const agents = useApiData<Agent[]>("/admin/agents");
  const llm = useApiData<LlmData>("/admin/llm");
  return (
    <AdminPage
      title="에이전트"
      description="에이전트마다 연결(키 · URL)과 모델 · 파라미터를 따로 지정할 수 있습니다. 비워 둔 값은 프로필 값을 따릅니다(override > 프로필 > 기본 프로필). 실행 시점의 값은 호출 기록에 스냅샷으로 남습니다."
    >
      <Loading error={agents.error} loading={!agents.data && agents.loading} />
      {(agents.data ?? []).map((a) => (
        <AgentCard key={a.code} a={a} llm={llm.data} reload={agents.reload} />
      ))}
    </AdminPage>
  );
}

const OV_KEYS = ["connection_id", "model", "temperature", "top_p", "max_tokens", "timeout_sec", "retries"] as const;

function AgentCard({ a, llm, reload }: { a: Agent; llm: LlmData | null; reload: () => Promise<void> }) {
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
        <p className="text-[12px] text-stone">규칙 기반 에이전트입니다. 규칙은 [판정 규칙]의 CRITIC_RULES 에서 관리합니다.</p>
      )}
    </Card>
  );
}
