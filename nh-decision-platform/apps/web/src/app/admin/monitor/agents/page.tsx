"use client";
import { useState } from "react";
import { AdminPage, C, Card, Collapse, JsonView, Loading, Mono, Select, Table, fmtTime, useAction, useApiData } from "@/components/admin/kit";
import { Badge, Button } from "@/components/ui/primitives";
import { apiPost } from "@/lib/api-client";

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
interface ApprovalJob {
  id: number;
  workflow: string;
  createdAt: string;
  causeCount: number;
  causes: { event_id?: number; type?: string; reasons?: string[]; actor?: string; at?: string }[];
}
interface Topology {
  agents: { code: string; name: string; role: string; kind: string; enabled: boolean }[];
  workflows: { code: string; name: string; enabled: boolean; nodes: { key: string; name: string; impl: string; agent: string | null; enabled: boolean }[] }[];
  orchestrator: { policy: Record<string, unknown>; depends_on: Record<string, Record<string, string[]>> };
}

const DECISION_TONE: Record<string, "neutral" | "info" | "attention" | "success" | "dark"> = { hold: "attention", release: "success", detect: "info", plan: "dark", narrated: "success" };
const DECISION_LABEL: Record<string, string> = { hold: "대기", release: "실행 허용", detect: "변화 판정", plan: "실행 계획", narrated: "서술 갱신", route: "경로 지정" };
const byOf = (d: Decision) => ((d.detail ?? {}) as { by?: string }).by;
const AGENT_NODE = new Set(["detect_changes", "plan_run", "narrate", "critic", "embed_chunks", "extract_documents"]);

/** 에이전트 결정 (B.30) — 오케스트레이터 · 변화 감지 · 플래너 · 서술 에이전트가 무엇을 왜 결정했는지 */
export default function AgentDecisionsAdmin() {
  const [agent, setAgent] = useState("");
  const topo = useApiData<Topology>("/admin/agents/topology");
  const dec = useApiData<{ counts: Record<string, number>; items: Decision[] }>(`/admin/agents/decisions?limit=150${agent ? `&agent=${agent}` : ""}`, { refreshMs: 10000 });
  const t = topo.data;
  const approvals = useApiData<ApprovalJob[]>("/admin/jobs/approval", { refreshMs: 10000 });
  const { run, busy } = useAction();
  return (
    <AdminPage
      title="에이전트 결정"
      description="이벤트가 오면 오케스트레이터(LLM)가 영향받는 워크플로우를 정하고, 실행 순서는 규칙으로 보장합니다. 워크플로우 안에서는 변화 감지(LLM 중요도 판단) → 화면 갱신 → 실행 계획(LLM: 서술 대상 · 검색어 · 후속 워크플로우) → 근거 · 서술 → 검증 순으로 진행합니다. LLM 판단은 허용 목록으로 검증하고, 미연결 · 실패 시 규칙으로 대체합니다. 수치는 모두 커널이 계산합니다."
    >
      {approvals.data?.length ? (
        <Card title={`사람 승인 대기 ${approvals.data.length}건`}>
          <p className="mb-md text-[12px] text-steel">설정 orchestrator.policy.require_approval 에 든 워크플로우는 자동 이벤트로 생긴 실행을 관리자가 승인해야 진행합니다.</p>
          <Table head={["작업", "워크플로우", "생성", "원인", ""]}>
            {approvals.data.map((j) => (
              <tr key={j.id} data-approval-job={j.id}>
                <C mono>#{j.id}</C>
                <C mono>{j.workflow}</C>
                <C>{fmtTime(j.createdAt)}</C>
                <C>
                  {j.causeCount}건 · {j.causes.slice(-3).map((c) => c.type).join(", ")}
                </C>
                <C right>
                  <span className="inline-flex gap-1">
                    <Button size="sm" variant="confirm" disabled={busy} onClick={() => run(() => apiPost(`/admin/jobs/${j.id}/approve`, {}), "승인했습니다 — 곧 실행됩니다", approvals.reload)}>
                      승인
                    </Button>
                    <Button size="sm" variant="quiet" disabled={busy} onClick={() => run(() => apiPost(`/admin/jobs/${j.id}/reject`, { reason: "관리자 반려" }), "반려했습니다", approvals.reload)}>
                      반려
                    </Button>
                  </span>
                </C>
              </tr>
            ))}
          </Table>
        </Card>
      ) : null}
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
                      <span className={`rounded-lg px-2 py-1 ${!n.enabled ? "bg-surface-soft text-stone line-through" : AGENT_NODE.has(n.impl) ? "bg-info-soft font-bold text-primary" : "bg-surface-soft text-charcoal"}`} title={n.agent ? `에이전트 ${n.agent}` : n.impl}>
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
            ariaLabel="에이전트 선택"
            value={agent}
            onChange={setAgent}
            options={[{ value: "", label: "전체 에이전트" }, ...(t?.agents ?? []).filter((a) => dec.data?.counts[a.code]).map((a) => ({ value: a.code, label: `${a.name} (${dec.data?.counts[a.code] ?? 0})` }))]}
          />
        }
      >
        <Loading error={dec.error} loading={!dec.data && dec.loading} />
        <Table head={["시각", "에이전트", "워크플로우", "결정", "판단", "요약", "근거"]}>
          {(dec.data?.items ?? []).map((d) => (
            <tr key={d.id}>
              <C className="whitespace-nowrap text-[11.5px]">{fmtTime(d.at)}</C>
              <C mono>{d.agent}</C>
              <C mono>{d.workflow ?? "-"}</C>
              <C>
                <Badge tone={DECISION_TONE[d.decision] ?? "neutral"}>{DECISION_LABEL[d.decision] ?? d.decision}</Badge>
              </C>
              <C>{byOf(d) ? <Badge tone={byOf(d) === "llm" ? "info" : "neutral"}>{byOf(d) === "llm" ? "LLM" : "규칙"}</Badge> : <Badge>규칙</Badge>}</C>
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
