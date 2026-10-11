"use client";

import { useState } from "react";
import { AdminPage, C, Card, Check, JsonView, Loading, Select, StatusBadge, Table, TextInput, fmtTime, useAction, useApiData } from "@/components/admin/kit";
import { Badge, Button } from "@/components/ui/primitives";
import { apiPatch, apiPost } from "@/lib/api-client";

interface Conn {
  id: number;
  name: string;
  baseUrl: string;
  apiKeyMasked: string;
  hasKey: boolean;
  active: boolean;
  note: string | null;
  lastTest: Record<string, unknown> | null;
}
interface Profile {
  id: number;
  name: string;
  connectionId: number | null;
  model: string;
  temperature: number | null;
  topP: number | null;
  maxTokens: number | null;
  timeoutSec: number;
  retries: number;
  toolsEnabled: boolean;
  extra: Record<string, unknown>;
  isDefault: boolean;
}

const num = (v: string) => (v === "" ? null : Number(v));

interface SetupState {
  connection: Conn | null;
  model: string;
  embeddingModel: string;
}
interface TestResult {
  ok: boolean;
  models?: string[];
  latency_ms?: number;
  chat_ok?: boolean;
  chat_latency_ms?: number;
  error?: string;
  chat_error?: string;
  models_status?: number;
}

/** 외부 LiteLLM 간단 설정 (B.36) — 주소 · 키 · 모델을 넣고 저장하면 바로 연결을 확인한다 */
function QuickSetup({ onSaved }: { onSaved: () => void }) {
  const cur = useApiData<SetupState>("/admin/llm/setup");
  const { run, busy } = useAction();
  const [f, setF] = useState<{ url: string; key: string; model: string; emb: string } | null>(null);
  const [test, setTest] = useState<TestResult | null>(null);
  const c = cur.data;
  const form = f ?? { url: c?.connection?.baseUrl ?? "", key: "", model: c?.model ?? "", emb: c?.embeddingModel ?? "" };
  const set = (patch: Partial<typeof form>) => setF({ ...form, ...patch });
  const last = (c?.connection?.lastTest ?? null) as TestResult | null;
  const shown = test ?? last;
  const save = () =>
    run(
      () =>
        apiPost<SetupState & { test: TestResult }>("/admin/llm/setup", {
          base_url: form.url.trim(),
          ...(form.key ? { api_key: form.key } : {}),
          model: form.model.trim(),
          embedding_model: form.emb.trim(),
        }),
      (r) => (r?.test?.ok ? "저장했습니다 — 연결 확인 성공" : "저장했습니다 — 연결 확인 실패(아래 결과 확인)"),
      () => {
        cur.reload();
        onSaved();
      },
    ).then((r) => {
      if (r) {
        setTest(r.test);
        setF({ ...form, key: "" });
      }
    });
  return (
    <Card title="LiteLLM 연결 (간단 설정)" actions={c?.connection?.hasKey ? <Badge tone="success">키 {c.connection.apiKeyMasked}</Badge> : <Badge tone="attention">키 없음</Badge>}>
      <p className="mb-md text-[12.5px] text-steel">
        사내 · 외부 LiteLLM(OpenAI 호환) 게이트웨이의 주소와 키를 넣고 저장하면 바로 연결을 확인합니다. 확인되면 그 게이트웨이에 등록된 모델 목록이 나오니 눌러서 고르세요. 키는 암호화 저장되고 다시 보여 주지 않습니다(비워 두면 기존 키 유지).
      </p>
      <Loading error={cur.error} loading={!c && cur.loading} />
      <div className="grid grid-cols-1 gap-md md:grid-cols-2" data-llm-setup>
        <TextInput label="LiteLLM 주소 (예: https://litellm.example.com 또는 …/v1)" value={form.url} onChange={(v) => set({ url: v })} mono placeholder="https://" />
        <TextInput label={c?.connection?.hasKey ? "API 키 (비우면 유지)" : "API 키"} type="password" value={form.key} onChange={(v) => set({ key: v })} />
        <TextInput label="기본 모델 (서술 · 판단 · 질의)" value={form.model} onChange={(v) => set({ model: v })} mono placeholder="예: coder.general.multimodal" />
        <TextInput label="임베딩 모델 (선택 — 비우면 키워드 검색만)" value={form.emb} onChange={(v) => set({ emb: v })} mono />
      </div>
      <div className="mt-md flex flex-wrap items-center gap-xs">
        <Button size="sm" variant="confirm" disabled={busy || !/^https?:\/\/.+/.test(form.url.trim())} onClick={save}>
          {busy ? "확인 중…" : "저장하고 연결 확인"}
        </Button>
        {shown ? (
          <span className="text-[12px]" role="status">
            {shown.ok ? <Badge tone="success">연결 성공</Badge> : <Badge tone="critical">연결 실패</Badge>}{" "}
            {shown.latency_ms !== undefined ? `모델 목록 ${shown.latency_ms}ms` : ""}
            {shown.chat_ok !== undefined ? ` · 모델 호출 ${shown.chat_ok ? `성공 ${shown.chat_latency_ms}ms` : "실패"}` : ""}
          </span>
        ) : null}
      </div>
      {shown && !shown.ok ? (
        <p className="mt-xs break-all text-[12px] text-critical">
          {shown.error || shown.chat_error || `HTTP ${shown.models_status ?? "-"}`} — 주소(…/v1 포함 여부) · 키 · 서버에서 그 주소로 나갈 수 있는지(보안 그룹 · 방화벽)를 확인하세요.
        </p>
      ) : null}
      {shown?.models?.length ? (
        <div className="mt-md">
          <p className="mb-xs text-[12px] font-bold text-charcoal">사용할 수 있는 모델 {shown.models.length}개 — 눌러서 기본 모델로</p>
          <div className="flex flex-wrap gap-1.5">
            {shown.models.slice(0, 60).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => set({ model: m })}
                aria-pressed={form.model === m}
                className={`rounded-pill border px-2.5 py-1 font-mono text-[11.5px] ${form.model === m ? "border-primary bg-[rgba(0,100,224,0.08)] text-primary" : "border-hairline-soft text-charcoal"}`}
              >
                {m}
              </button>
            ))}
          </div>
        </div>
      ) : null}
    </Card>
  );
}

/** LiteLLM 연결 · 키 · 기본 프로필 (ADM-05, LLM-01~03) */
export default function LlmAdmin() {
  const data = useApiData<{ connections: Conn[]; profiles: Profile[] }>("/admin/llm");
  const { run, busy } = useAction();
  const [newConn, setNewConn] = useState({ name: "", base_url: "", api_key: "" });
  const [testModel, setTestModel] = useState<Record<number, string>>({});
  const [testResult, setTestResult] = useState<Record<number, unknown>>({});
  const conns = data.data?.connections ?? [];

  return (
    <AdminPage
      title="LLM 연동"
      description="외부 LiteLLM(OpenAI 호환) 게이트웨이의 주소 · 키 · 모델을 등록합니다. 키는 암호화(AES-GCM) 저장되고 화면에는 가려서 표시됩니다. 보통은 위 '간단 설정' 만으로 충분하고, 연결을 여러 개 두거나 에이전트별로 다른 모델 · 파라미터를 쓸 때 아래 상세 설정과 [에이전트]를 씁니다."
    >
      <QuickSetup onSaved={data.reload} />
      <Loading error={data.error} loading={!data.data && data.loading} />
      <Card title="연결 (상세)">
        <div className="flex flex-col gap-lg">
          {conns.map((c) => (
            <ConnRow
              key={c.id}
              conn={c}
              busy={busy}
              testModel={testModel[c.id] ?? ""}
              setTestModel={(v) => setTestModel({ ...testModel, [c.id]: v })}
              result={testResult[c.id]}
              onTest={() => run(() => apiPost(`/admin/llm/connections/${c.id}/test`, { model: testModel[c.id] || null }), undefined, undefined).then((r) => r && setTestResult({ ...testResult, [c.id]: r }))}
              onSave={(patch) => run(() => apiPatch(`/admin/llm/connections/${c.id}`, patch), "저장했습니다", data.reload)}
            />
          ))}
        </div>
        <div className="mt-lg border-t border-hairline-soft pt-lg">
          <p className="mb-md text-[13px] font-bold text-ink-deep">연결 추가</p>
          <div className="grid grid-cols-1 gap-md md:grid-cols-4">
            <TextInput label="이름" value={newConn.name} onChange={(v) => setNewConn({ ...newConn, name: v })} />
            <TextInput label="Base URL" value={newConn.base_url} onChange={(v) => setNewConn({ ...newConn, base_url: v })} mono className="md:col-span-2" />
            <TextInput label="API 키" type="password" value={newConn.api_key} onChange={(v) => setNewConn({ ...newConn, api_key: v })} />
          </div>
          <Button size="sm" variant="confirm" className="mt-md" disabled={busy || !newConn.name || !newConn.base_url} onClick={() => run(() => apiPost("/admin/llm/connections", newConn), "연결을 추가했습니다", data.reload)}>
            추가
          </Button>
        </div>
      </Card>

      <Card title="프로필 (모델 + 파라미터)">
        <p className="mb-md text-[12px] text-steel">기본 프로필(★)은 프로필이 지정되지 않은 에이전트가 씁니다. 모델명은 LiteLLM 에 등록된 이름(예: coder.general.multimodal)을 그대로 입력합니다.</p>
        <Table head={["프로필", "연결", "모델", "temperature", "top_p", "max_tokens", "timeout(s)", "재시도", "도구 호출", "기본", ""]}>
          {(data.data?.profiles ?? []).map((p) => (
            <ProfileRow key={p.id} p={p} conns={conns} busy={busy} onSave={(patch) => run(() => apiPatch(`/admin/llm/profiles/${p.id}`, patch), "프로필을 저장했습니다", data.reload)} />
          ))}
        </Table>
      </Card>
    </AdminPage>
  );
}

function ConnRow({ conn, busy, onSave, onTest, testModel, setTestModel, result }: { conn: Conn; busy: boolean; onSave: (p: Record<string, unknown>) => void; onTest: () => void; testModel: string; setTestModel: (v: string) => void; result: unknown }) {
  const [url, setUrl] = useState(conn.baseUrl);
  const [key, setKey] = useState("");
  return (
    <div className="rounded-xl border border-hairline-soft p-base">
      <div className="mb-md flex flex-wrap items-center gap-xs">
        <p className="text-[14px] font-bold text-ink-deep">{conn.name}</p>
        <StatusBadge status={conn.active ? "active" : "disabled"} label={conn.active ? "사용" : "중지"} />
        {conn.hasKey ? <Badge tone="success">키 {conn.apiKeyMasked}</Badge> : <Badge tone="attention">키 없음</Badge>}
        {conn.lastTest ? <span className="text-[11px] text-stone">최근 테스트 {fmtTime(conn.lastTest.at as string)} · {conn.lastTest.ok ? "성공" : "실패"}</span> : null}
      </div>
      <div className="grid grid-cols-1 gap-md md:grid-cols-[2fr_1.4fr_auto_auto]">
        <TextInput label="Base URL" value={url} onChange={setUrl} mono />
        <TextInput label="새 API 키 (비우면 유지)" type="password" value={key} onChange={setKey} />
        <div className="flex items-end">
          <Check label="사용" checked={conn.active} onChange={(v) => onSave({ active: v })} />
        </div>
        <div className="flex items-end gap-xs">
          <Button size="sm" variant="confirm" disabled={busy} onClick={() => onSave({ base_url: url, ...(key ? { api_key: key } : {}) })}>
            저장
          </Button>
          {conn.hasKey ? (
            <Button size="sm" variant="ghost" disabled={busy} onClick={() => window.confirm("키를 삭제할까요?") && onSave({ api_key: "" })}>
              키 삭제
            </Button>
          ) : null}
        </div>
      </div>
      <div className="mt-md flex flex-wrap items-end gap-xs">
        <TextInput label="연결 테스트 — 모델(선택, 입력 시 1토큰 호출)" value={testModel} onChange={setTestModel} mono className="min-w-[280px]" />
        <Button size="sm" variant="quiet" disabled={busy} onClick={onTest}>
          테스트
        </Button>
      </div>
      {result ? (
        <div className="mt-md">
          <JsonView value={result} maxHeight={220} />
        </div>
      ) : null}
    </div>
  );
}

function ProfileRow({ p, conns, busy, onSave }: { p: Profile; conns: Conn[]; busy: boolean; onSave: (patch: Record<string, unknown>) => void }) {
  const [f, setF] = useState({
    connection_id: String(p.connectionId ?? ""),
    model: p.model,
    temperature: p.temperature?.toString() ?? "",
    top_p: p.topP?.toString() ?? "",
    max_tokens: p.maxTokens?.toString() ?? "",
    timeout_sec: String(p.timeoutSec),
    retries: String(p.retries),
    tools_enabled: p.toolsEnabled,
    is_default: p.isDefault,
  });
  return (
    <tr>
      <C>
        <span className="font-bold text-ink-deep">{p.name}</span>
      </C>
      <C className="min-w-[130px]">
        <Select ariaLabel={`${p.name} 연결`} value={f.connection_id} onChange={(v) => setF({ ...f, connection_id: v })} options={[{ value: "", label: "-" }, ...conns.map((c) => ({ value: String(c.id), label: c.name }))]} />
      </C>
      <C className="min-w-[220px]">
        <TextInput ariaLabel={`${p.name} 모델`} value={f.model} onChange={(v) => setF({ ...f, model: v })} mono placeholder="모델명" />
      </C>
      <C className="w-[90px]">
        <TextInput ariaLabel={`${p.name} temperature`} value={f.temperature} onChange={(v) => setF({ ...f, temperature: v })} type="number" />
      </C>
      <C className="w-[80px]">
        <TextInput ariaLabel={`${p.name} top_p`} value={f.top_p} onChange={(v) => setF({ ...f, top_p: v })} type="number" />
      </C>
      <C className="w-[100px]">
        <TextInput ariaLabel={`${p.name} max_tokens`} value={f.max_tokens} onChange={(v) => setF({ ...f, max_tokens: v })} type="number" />
      </C>
      <C className="w-[80px]">
        <TextInput ariaLabel={`${p.name} 대기 상한(초)`} value={f.timeout_sec} onChange={(v) => setF({ ...f, timeout_sec: v })} type="number" />
      </C>
      <C className="w-[70px]">
        <TextInput ariaLabel={`${p.name} 재시도`} value={f.retries} onChange={(v) => setF({ ...f, retries: v })} type="number" />
      </C>
      <C>
        <Check label="" ariaLabel={`${p.name} 도구 호출`} checked={f.tools_enabled} onChange={(v) => setF({ ...f, tools_enabled: v })} />
      </C>
      <C>
        <Check label={f.is_default ? "★" : ""} ariaLabel={`${p.name} 기본 프로필`} checked={f.is_default} onChange={(v) => setF({ ...f, is_default: v })} />
      </C>
      <C>
        <Button
          size="sm"
          variant="confirm"
          disabled={busy}
          onClick={() =>
            onSave({
              connection_id: f.connection_id ? Number(f.connection_id) : null,
              model: f.model.trim(),
              temperature: num(f.temperature),
              top_p: num(f.top_p),
              max_tokens: num(f.max_tokens),
              timeout_sec: Number(f.timeout_sec || 60),
              retries: Number(f.retries || 0),
              tools_enabled: f.tools_enabled,
              is_default: f.is_default,
            })
          }
        >
          저장
        </Button>
      </C>
    </tr>
  );
}
