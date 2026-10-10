"use client";
import { useEffect, useState } from "react";
import { AdminPage, C, Card, Collapse, JsonView, Loading, Mono, StatusBadge, Table, TextInput, fmtTime, useApiData } from "@/components/admin/kit";
import { Badge } from "@/components/ui/primitives";

interface TraceRow {
  traceId: string;
  at: string;
  method: string;
  path: string;
  route: string | null;
  status: number;
  durationMs: number;
  dbQueries: number;
  dbMs: number;
  actor: string | null;
}
interface Span {
  kind: "http" | "audit" | "event" | "run" | "llm";
  at: string;
  label: string;
  status?: number | string;
  durationMs?: number | null;
  db?: { queries?: number; ms?: number; db_queries?: number; db_ms?: number } | null;
  actor?: string | null;
  target?: string;
  matched?: string[];
  nodes?: { key: string; status: string; durationMs: number | null }[];
  calcRuns?: number;
  merged?: boolean;
  runId?: string;
  model?: string | null;
  tokens?: number;
  detail?: unknown;
  payload?: unknown;
}
const KIND_LABEL = { http: "HTTP", audit: "감사", event: "이벤트", run: "워크플로우", llm: "LLM" } as const;
const KIND_TONE = { http: "dark", audit: "neutral", event: "info", run: "success", llm: "attention" } as const;
const HEX32 = /^[0-9a-f]{32}$/;

function dbText(db: Span["db"]) {
  if (!db) return null;
  const q = db.queries ?? db.db_queries;
  const ms = db.ms ?? db.db_ms;
  return q === undefined ? null : `DB ${q}건 · ${ms ?? 0}ms`;
}

/** 요청 추적 (작업 0.5 · NFR-09) — 응답 헤더 X-Trace-Id 하나로 HTTP → 이벤트 → 워커 → 계산 · LLM · DB 구간 조회 */
export default function TraceAdmin() {
  const [input, setInput] = useState("");
  const [tid, setTid] = useState<string | null>(null);
  /* 주소의 ?id= 로 바로 열기 (모니터링 화면 링크) */
  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get("id")?.toLowerCase() ?? "";
    if (!HEX32.test(id)) return;
    // 주소 값은 마운트 후에만 읽을 수 있다 (SSR 과 첫 렌더 일치)
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setInput(id);
    setTid(id);
  }, []);
  const recent = useApiData<TraceRow[]>("/admin/monitor/traces?limit=80");
  const trace = useApiData<{ traceId: string; spans: Span[] }>(tid ? `/admin/monitor/trace/${tid}` : null);
  const pick = (id: string) => {
    setInput(id);
    setTid(id);
  };
  const t0 = trace.data?.spans[0]?.at ? Date.parse(trace.data.spans[0].at) : 0;

  return (
    <AdminPage
      title="요청 추적"
      description="모든 API 응답에는 X-Trace-Id 헤더가 붙습니다. 그 값으로 요청 → 감사 기록 → 변경 이벤트 → 워커의 워크플로우 실행(노드 · 계산 · LLM · DB)까지 한 줄로 봅니다. 변경 요청 · 오류 · 느린 조회(설정 obs.slow_request_ms)가 기록됩니다."
    >
      <Card>
        <form
          className="flex flex-wrap items-end gap-md"
          onSubmit={(e) => {
            e.preventDefault();
            const v = input.trim().toLowerCase();
            if (HEX32.test(v)) setTid(v);
          }}
        >
          <TextInput label="추적 ID (32자리)" value={input} onChange={setInput} mono className="min-w-[340px]" />
          <button type="submit" className="rounded-pill bg-ink-deep px-4 py-2 text-[12px] font-bold text-white" disabled={!HEX32.test(input.trim().toLowerCase())}>
            조회
          </button>
        </form>
      </Card>

      {tid ? (
        <Card title={<span>구간 · <Mono>{tid}</Mono></span>}>
          <Loading error={trace.error} loading={!trace.data && trace.loading} />
          {trace.data ? (
            <ol className="flex flex-col gap-2" data-trace-spans>
              {trace.data.spans.map((s, i) => (
                <li key={i} className="rounded-lg border border-hairline-soft px-3 py-2.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="w-[64px] text-right font-mono text-[11px] text-stone">+{Math.max(0, Date.parse(s.at) - t0)}ms</span>
                    <Badge tone={KIND_TONE[s.kind]}>{KIND_LABEL[s.kind]}</Badge>
                    <span className="text-[12.5px] font-bold text-ink-deep">{s.label}</span>
                    {s.status !== undefined ? <StatusBadge status={String(s.status)} /> : null}
                    {s.durationMs != null ? <span className="text-[11px] text-steel">{s.durationMs}ms</span> : null}
                    {dbText(s.db) ? <span className="text-[11px] text-steel">{dbText(s.db)}</span> : null}
                    {s.actor ? <span className="text-[11px] text-stone">사번 {s.actor}</span> : null}
                    {s.merged ? <Badge tone="warning">다른 변경과 병합 실행</Badge> : null}
                  </div>
                  {s.kind === "event" && s.matched?.length ? <p className="mt-1 pl-[72px] text-[11px] text-steel">매칭 → {s.matched.join(" · ")}</p> : null}
                  {s.kind === "audit" && s.target ? <p className="mt-1 pl-[72px] text-[11px] text-steel">대상 {s.target}</p> : null}
                  {s.kind === "llm" ? <p className="mt-1 pl-[72px] text-[11px] text-steel">{s.model ?? "-"} · 토큰 {s.tokens ?? 0}</p> : null}
                  {s.kind === "run" && s.nodes ? (
                    <p className="mt-1 pl-[72px] text-[11px] text-steel">
                      {s.nodes.map((n) => `${n.key}(${n.status}${n.durationMs != null ? ` ${n.durationMs}ms` : ""})`).join(" → ")} · 계산 {s.calcRuns ?? 0}건
                    </p>
                  ) : null}
                  {s.detail || s.payload ? (
                    <div className="mt-1 pl-[72px]">
                      <Collapse label="상세">
                        <JsonView value={s.detail ?? s.payload} maxHeight={180} />
                      </Collapse>
                    </div>
                  ) : null}
                </li>
              ))}
            </ol>
          ) : null}
        </Card>
      ) : null}

      <Card title="최근 기록된 요청">
        <Loading error={recent.error} loading={!recent.data && recent.loading} />
        <Table head={["시각", "요청", "상태", "소요", "DB", "사번", "추적 ID"]}>
          {(recent.data ?? []).map((r) => (
            <tr key={`${r.traceId}-${r.at}`}>
              <C className="whitespace-nowrap text-[11.5px]">{fmtTime(r.at)}</C>
              <C className="text-[12px]">
                <b>{r.method}</b> {r.route ?? r.path}
              </C>
              <C>
                <StatusBadge status={String(r.status)} />
              </C>
              <C right>{r.durationMs}ms</C>
              <C right className="text-[11.5px]">
                {r.dbQueries}건 · {r.dbMs}ms
              </C>
              <C mono>{r.actor ?? "-"}</C>
              <C>
                <button type="button" className="font-mono text-[11px] text-primary hover:underline" onClick={() => pick(r.traceId)} data-trace-pick>
                  {r.traceId.slice(0, 12)}…
                </button>
              </C>
            </tr>
          ))}
        </Table>
      </Card>
    </AdminPage>
  );
}
