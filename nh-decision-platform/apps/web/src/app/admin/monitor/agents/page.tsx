"use client";
import { useState } from "react";
import { AdminPage, C, Card, Collapse, JsonView, Loading, Mono, Select, Table, fmtTime, useApiData } from "@/components/admin/kit";
import { Badge } from "@/components/ui/primitives";

interface Decision {
  id: number;
  at: string;
  agent: string;
  workflow: string | null;
  jobId: number | null;
  runId: string | null;
  decision: string;
  summary: string;
  detail: unknown;
  traceId: string | null;
}
interface Topology {
  agents: { code: string; name: string; role: string; kind: string; enabled: boolean }[];
  workflows: { code: string; name: string; enabled: boolean; nodes: { key: string; name: string; impl: string; agent: string | null; enabled: boolean }[] }[];
  orchestrator: { policy: Record<string, unknown>; depends_on: Record<string, Record<string, string[]>> };
}

const DECISION_TONE: Record<string, "neutral" | "info" | "attention" | "success" | "dark"> = { hold: "attention", release: "success", detect: "info", plan: "dark", narrated: "success" };
const DECISION_LABEL: Record<string, string> = { hold: "대기", release: "실행 허용", detect: "변화 판정", plan: "실행 계획", narrated: "서술 갱신" };
const AGENT_NODE = new Set(["detect_changes", "plan_run", "narrate", "critic", "embed_chunks", "extract_documents"]);

/** 에이전트 결정 (B.30) — 오케스트레이터 · 변화 감지 · 플래너 · 서술 에이전트가 무엇을 왜 결정했는지 */
export default function AgentDecisionsAdmin() {
  const [agent, setAgent] = useState("");
  const topo = useApiData<Topology>("/admin/agents/topology");
  const dec = useApiData<{ counts: Record<string, number>; items: Decision[] }>(`/admin/agents/decisions?limit=150${agent ? `&agent=${agent}` : ""}`, { refreshMs: 10000 });
  const t = topo.data;
  return (
    <AdminPage
      title="에이전트 결정"
      description="워크플로우 사이는 오케스트레이터가 실행 순서를 정하고, 워크플로우 안에서는 변화 감지 → 화면 갱신 → 실행 계획(플래너) → 근거 · 서술(LLM) → 검증 순으로 진행합니다. 판단 에이전트는 규칙 기반이며 수치는 모두 커널이 계산합니다."
    >
      <Card title="워크플로우별 에이전트 배치">
        <Loading error={topo.error} loading={!t && topo.loading} />
        {t ? (
          <div className="flex flex-col gap-md" data-agent-topology>
            {t.workflows.map((w) => (
              <div key={w.code}>
                <p className="mb-1.5 text-[12.5px] font-bold text-ink-deep">
                  {w.name} <Mono>{w.code}</Mono>
                </p>
                <ol className="flex flex-wrap items-center gap-1 text-[11.5px]">
                  {w.nodes.map((n, i) => (
                    <li key={n.key} className="flex items-center gap-1">
                      <span className={`rounded-lg px-2 py-1 ${!n.enabled ? "bg-surface-soft text-stone line-through" : AGENT_NODE.has(n.impl) ? "bg-[rgba(0,100,224,0.08)] font-bold text-primary" : "bg-surface-soft text-charcoal"}`} title={n.agent ? `에이전트 ${n.agent}` : n.impl}>
                        {n.name}
                      </span>
                      {i < w.nodes.length - 1 ? <span className="text-stone">→</span> : null}
                    </li>
                  ))}
                </ol>
              </div>
            ))}
          </div>
        ) : null}
      </Card>

      <Card title="오케스트레이터 — 워크플로우 의존 관계">
        {t ? (
          <>
            <p className="mb-md text-[12px] text-steel">
              설정 <Mono>orchestrator.policy</Mono> · 대기 간격 {String(t.orchestrator.policy.hold_sec)}초 · 최대 대기 {String(t.orchestrator.policy.max_hold_sec)}초 · {t.orchestrator.policy.enabled ? "켜짐" : "꺼짐"}
            </p>
            <Table head={["워크플로우", "먼저 끝나야 하는 워크플로우", "근거"]}>
              {Object.entries(t.orchestrator.depends_on).map(([wf, ups]) => (
                <tr key={wf}>
                  <C mono>{wf}</C>
                  <C mono>{Object.keys(ups).join(", ")}</C>
                  <C className="text-[11.5px]">{Object.values(ups).flat().slice(0, 4).join(" · ")}</C>
                </tr>
              ))}
            </Table>
          </>
        ) : null}
      </Card>

      <Card
        title="최근 결정"
        actions={
          <Select
            value={agent}
            onChange={setAgent}
            options={[{ value: "", label: "전체 에이전트" }, ...(t?.agents ?? []).filter((a) => dec.data?.counts[a.code]).map((a) => ({ value: a.code, label: `${a.name} (${dec.data?.counts[a.code] ?? 0})` }))]}
          />
        }
      >
        <Loading error={dec.error} loading={!dec.data && dec.loading} />
        <Table head={["시각", "에이전트", "워크플로우", "결정", "요약", "근거"]}>
          {(dec.data?.items ?? []).map((d) => (
            <tr key={d.id}>
              <C className="whitespace-nowrap text-[11.5px]">{fmtTime(d.at)}</C>
              <C mono>{d.agent}</C>
              <C mono>{d.workflow ?? "-"}</C>
              <C>
                <Badge tone={DECISION_TONE[d.decision] ?? "neutral"}>{DECISION_LABEL[d.decision] ?? d.decision}</Badge>
              </C>
              <C className="text-[12.5px]">{d.summary}</C>
              <C className="min-w-[200px]">
                <Collapse label="보기">
                  <JsonView value={d.detail} maxHeight={240} />
                </Collapse>
              </C>
            </tr>
          ))}
        </Table>
      </Card>
    </AdminPage>
  );
}
