"use client";

import clsx from "clsx";
import Link from "next/link";
import { Fragment, useState } from "react";
import { Connector, NodeStrip, StateDot, Step, fmtMs, stateText, stepOf } from "@/components/admin/flowViz";
import { AdminPage, Card, Loading, Table, C, Tabs, fmtTime, useApiData } from "@/components/admin/kit";
import { GRADE_KO } from "@/components/admin/ontology/opText";
import { Badge } from "@/components/ui/primitives";

/* 관리자 [에이전틱 파이프라인] (Phase M · AGG-03 · Q189) — 기능 그룹 → 그 그룹 에이전트가 맡은 워크플로 단계 순서.
 * 상태는 실제 실행 기록(노드 실행 · LLM 호출 24시간 · 결정)에서 읽는다. 색만으로 전하지 않고 점 모양 + 글자 라벨을 함께 쓴다. */

interface Summary { agents: number; llm: number; rule: number; enabled: number; calls24h: number; errors24h: number; errorRate: number | null; avgLatencyMs: number | null; tokens24h: number }
interface AgentView { code: string; name: string; kind: "llm" | "rule"; enabled: boolean; model: string | null; connection: string | null; ready: boolean; reason: string | null; stats: { calls?: number; errors?: number; skipped?: number; avgLatencyMs?: number | null; tokens?: number } }
interface PNode { key: string; name: string; impl: string; enabled: boolean; agent: string | null; agentName: string | null; agentGroup: string | null; inGroup: boolean; status: string | null; ms: number | null }
interface Pipeline { workflow: string; name: string; enabled: boolean; nodes: PNode[]; lastRun: { id: string; status: string; startedAt: string; finishedAt: string | null } | null; runs24h: Record<string, number> & { total: number } }
interface FlowStep { label: string; agent: string | null; agentName: string | null; description: string; status: string | null; calls24h: number }
interface Group {
  code: string; name: string; description: string; summary: Summary; agents: AgentView[]; pipelines: Pipeline[]; flow: FlowStep[];
  decisions: { id: number; at: string; agent: string; agentName: string | null; decision: string; summary: string; workflow: string | null }[];
  ontology?: { datasets: number; profiled: number; pendingProposals: number; appliedProposals: number; grade: string | null; checkedAt: string | null };
  intake?: { drafts: number; pending: number; applied: number; failed: number; applied24h: number };
}
interface Overview {
  groups: Group[];
  breaker: { key: string; name: string | null; fails: number; open: boolean; remainingSec: number; lastError: string | null }[];
  totals: { agents: number; llm: number; calls24h: number; errors24h: number };
  generatedAt: string;
}

const ALL = "__all";

export default function AgenticAdmin() {
  const data = useApiData<Overview>("/admin/agentic/overview", { refreshMs: 15000 });
  const [tab, setTab] = useState<string>(ALL);
  const groups = data.data?.groups ?? [];
  const tabs = [{ key: ALL, label: "전체 보기" }, ...groups.map((g) => ({ key: g.code, label: g.name, count: g.agents.length }))];
  const g = groups.find((x) => x.code === tab);
  const t = data.data?.totals;
  const open = (data.data?.breaker ?? []).filter((b) => b.open);
  return (
    <AdminPage
      title="에이전틱 파이프라인"
      description="기능 그룹마다 그 그룹 에이전트가 맡은 워크플로 단계를 순서대로 보여 줍니다. 상태는 최근 실행 기록과 최근 24시간 LLM 호출에서 읽습니다. 에이전트 설정은 [에이전트·프롬프트]에서 바꿉니다."
      actions={
        <Link href="/admin/agents" className="text-[12.5px] font-bold text-primary">
          에이전트·프롬프트 설정
        </Link>
      }
      summary={
        t ? (
          <div className="flex flex-wrap gap-xs text-[12px] text-steel">
            <Badge tone="neutral">에이전트 {t.agents}</Badge>
            <Badge tone="info">LLM {t.llm}</Badge>
            <Badge tone="neutral">24시간 호출 {t.calls24h.toLocaleString()}</Badge>
            <Badge tone={t.errors24h ? "warning" : "neutral"}>오류 {t.errors24h.toLocaleString()}</Badge>
            {data.data?.generatedAt ? <span className="self-center">기준 {fmtTime(data.data.generatedAt)}</span> : null}
          </div>
        ) : null
      }
    >
      <Loading error={data.error} loading={!data.data && data.loading} />
      {open.length ? (
        <p role="status" className="mb-lg rounded-lg bg-critical-faint px-md py-2.5 text-[12.5px] text-critical">
          연결 차단 중: {open.map((b) => `${b.name ?? b.key} (${b.remainingSec}초 남음)`).join(" · ")} — 연속 실패로 잠시 보내지 않고 규칙으로 대체합니다.
        </p>
      ) : null}
      {groups.length ? <Tabs tabs={tabs} active={tab} onChange={setTab} /> : null}
      {tab === ALL ? <AllGroups groups={groups} onOpen={setTab} /> : g ? <GroupDetail g={g} /> : null}
    </AdminPage>
  );
}

function health(s: Summary): { state: "done" | "warn" | "fail" | "idle"; label: string } {
  if (!s.calls24h) return { state: "idle", label: s.llm ? "24시간 호출 없음" : "규칙형" };
  if (s.errorRate != null && s.errorRate >= 50) return { state: "fail", label: `오류율 ${s.errorRate}%` };
  if (s.errorRate) return { state: "warn", label: `오류율 ${s.errorRate}%` };
  return { state: "done", label: "정상" };
}

function AllGroups({ groups, onOpen }: { groups: Group[]; onOpen: (k: string) => void }) {
  return (
    <ol className="grid grid-cols-1 gap-md lg:grid-cols-2" aria-label="에이전트 그룹">
      {groups.map((g) => {
        const h = health(g.summary);
        return (
          <li key={g.code} className="rounded-2xl border border-hairline-soft bg-canvas p-lg" data-group={g.code}>
            <div className="flex items-start gap-xs">
              <StateDot state={h.state} className="mt-1.5" />
              <div className="min-w-0 flex-1">
                <h2 className="text-[15px] font-bold text-ink-deep">{g.name}</h2>
                <p className="text-[12px] text-steel">{g.description}</p>
              </div>
              <span className={clsx("shrink-0 text-[11.5px] font-bold", stateText(h.state))}>{h.label}</span>
            </div>
            <p className="mt-md text-[12px] text-charcoal">
              에이전트 {g.summary.agents} (LLM {g.summary.llm} · 규칙 {g.summary.rule}) · 24시간 호출 {g.summary.calls24h.toLocaleString()}
              {g.summary.avgLatencyMs ? ` · 평균 ${fmtMs(g.summary.avgLatencyMs)}` : ""}
            </p>
            <div className="mt-md flex flex-col gap-md">
              {g.pipelines.slice(0, 3).map((p) => (
                <div key={p.workflow}>
                  <p className="mb-1 text-[11.5px] font-bold text-steel">{p.name}</p>
                  <NodeStrip nodes={p.nodes.filter((n) => n.enabled).map((n) => ({ key: n.key, name: n.name, status: n.status ?? "", ms: n.ms }))} label={`${p.name} 최근 실행 노드 상태`} />
                </div>
              ))}
              {!g.pipelines.length && g.flow.length ? <p className="text-[11.5px] text-steel">호출 경로: {g.flow.map((f) => f.label).join(" → ")}</p> : null}
              {g.pipelines.length > 3 ? <p className="text-[11px] text-stone">그 밖의 워크플로 {g.pipelines.length - 3}개</p> : null}
            </div>
            <button type="button" className="mt-md text-[12.5px] font-bold text-primary" onClick={() => onOpen(g.code)}>
              {g.name} 자세히 보기
            </button>
          </li>
        );
      })}
    </ol>
  );
}

function PipelineChain({ p }: { p: Pipeline }) {
  const nodes = p.nodes.filter((n) => n.enabled);
  const last = p.lastRun ? stepOf(p.lastRun.status) : stepOf(null);
  return (
    <Card
      title={
        <span className="flex flex-wrap items-center gap-xs">
          {p.name} <code className="font-mono text-[11px] text-stone">{p.workflow}</code>
          {!p.enabled ? <Badge tone="neutral">꺼짐</Badge> : null}
        </span>
      }
      actions={
        <span className="flex items-center gap-1.5 text-[11.5px] text-steel">
          <StateDot state={last.state} />
          최근 {last.label}
          {p.lastRun ? ` · ${fmtTime(p.lastRun.startedAt)}` : ""} · 24시간 {p.runs24h.total}회
        </span>
      }
    >
      <ol className="flex flex-wrap items-stretch gap-y-xs" aria-label={`${p.name} 단계`}>
        {nodes.map((n, i) => {
          const st = stepOf(n.status);
          return (
            <Fragment key={n.key}>
              <li className={clsx(n.inGroup ? "w-[168px]" : "w-auto")}>
                {n.inGroup ? (
                  <Step title={n.name} state={st.state} stateLabel={st.label} dataKey={n.impl} className="h-full">
                    <span className="block truncate font-bold text-ink">{n.agentName ?? n.agent}</span>
                    <span className="block text-[11px] text-steel">{n.impl}{n.ms ? ` · ${fmtMs(n.ms)}` : ""}</span>
                  </Step>
                ) : (
                  <span className="flex h-full items-center gap-1 rounded-lg border border-dashed border-hairline px-2 py-1 text-[11px] text-steel" title={`${n.name} · ${st.label}`}>
                    <StateDot state={st.state} className="h-2 w-2" />
                    {n.name}
                    <span className="sr-only"> {st.label}</span>
                  </span>
                )}
              </li>
              {i < nodes.length - 1 ? (
                <li aria-hidden="true" className="flex">
                  <Connector />
                </li>
              ) : null}
            </Fragment>
          );
        })}
      </ol>
      <p className="mt-xs text-[11px] text-stone">굵은 카드 = 이 그룹 에이전트가 맡은 단계 · 점선 = 다른 그룹 · 계산(커널 · 규칙) 단계</p>
    </Card>
  );
}

function FlowChain({ g }: { g: Group }) {
  return (
    <Card title="호출 경로" actions={<span className="text-[11.5px] text-steel">워크플로 밖에서 부르는 에이전트 — 상태는 24시간 호출 기록</span>}>
      <ol className="flex flex-wrap items-stretch gap-y-xs" aria-label={`${g.name} 호출 경로`}>
        {g.flow.map((f, i) => {
          const st = f.agent ? (f.status ? stepOf(f.status) : { state: "idle" as const, label: "호출 없음" }) : { state: "skip" as const, label: "규칙 · 처리" };
          return (
            <Fragment key={f.label}>
              <li className="w-[176px]">
                <Step title={f.label} state={st.state} stateLabel={st.label} className="h-full">
                  {f.agent ? <span className="block truncate font-bold text-ink">{f.agentName ?? f.agent}</span> : null}
                  <span className="block text-[11px] text-steel">{f.description}{f.agent ? ` · ${f.calls24h}회` : ""}</span>
                </Step>
              </li>
              {i < g.flow.length - 1 ? (
                <li aria-hidden="true" className="flex">
                  <Connector />
                </li>
              ) : null}
            </Fragment>
          );
        })}
      </ol>
    </Card>
  );
}

function GroupDetail({ g }: { g: Group }) {
  const h = health(g.summary);
  return (
    <div data-group-detail={g.code}>
      <Card title={g.name} actions={<span className={clsx("flex items-center gap-1.5 text-[12px] font-bold", stateText(h.state))}><StateDot state={h.state} />{h.label}</span>}>
        <p className="text-[12.5px] text-steel">{g.description}</p>
        {g.ontology ? (
          <dl className="mt-md grid grid-cols-2 gap-xs text-[12.5px] md:grid-cols-5">
            <Fact k="구조 파악" v={`${g.ontology.profiled} / ${g.ontology.datasets} 데이터셋`} />
            <Fact k="대기 제안" v={`${g.ontology.pendingProposals}건`} href="/admin/ontology" />
            <Fact k="적용한 제안" v={`${g.ontology.appliedProposals}건`} />
            <Fact k="품질 등급" v={g.ontology.grade ? (GRADE_KO[g.ontology.grade] ?? g.ontology.grade) : "-"} />
            <Fact k="최근 점검" v={fmtTime(g.ontology.checkedAt)} />
          </dl>
        ) : null}
        {g.intake ? (
          <dl className="mt-md grid grid-cols-2 gap-xs text-[12.5px] md:grid-cols-5">
            <Fact k="초안" v={`${g.intake.drafts}건`} />
            <Fact k="승인 대기" v={`${g.intake.pending}건`} href="/admin/datasets" />
            <Fact k="반영" v={`${g.intake.applied}건`} />
            <Fact k="24시간 반영" v={`${g.intake.applied24h}건`} />
            <Fact k="실패" v={`${g.intake.failed}건`} />
          </dl>
        ) : null}
      </Card>
      {g.pipelines.map((p) => (
        <PipelineChain key={p.workflow} p={p} />
      ))}
      {g.flow.length ? <FlowChain g={g} /> : null}
      <Card title={`에이전트 ${g.agents.length}`}>
        <Table head={["에이전트", "종류", "모델 · 연결", "24시간 호출", "오류 · 차단", "평균 지연", "토큰"]}>
          {g.agents.map((a) => (
            <tr key={a.code}>
              <C>
                <span className="font-bold text-ink">{a.name}</span> <code className="font-mono text-[10.5px] text-stone">{a.code}</code>
                {!a.enabled ? <Badge tone="neutral">꺼짐</Badge> : null}
              </C>
              <C>{a.kind === "llm" ? "LLM" : "규칙"}</C>
              <C>{a.kind === "llm" ? (a.ready ? `${a.model} · ${a.connection}` : <span className="text-attention">미설정 — {a.reason}</span>) : "-"}</C>
              <C right>{(a.stats.calls ?? 0).toLocaleString()}</C>
              <C right>{`${a.stats.errors ?? 0} · ${a.stats.skipped ?? 0}`}</C>
              <C right>{a.stats.avgLatencyMs ? fmtMs(a.stats.avgLatencyMs) : "-"}</C>
              <C right>{(a.stats.tokens ?? 0).toLocaleString()}</C>
            </tr>
          ))}
        </Table>
      </Card>
      <Card title="최근 결정" actions={<Link href="/admin/monitor/agents" className="text-[12px] font-bold text-primary">에이전트 결정 전체</Link>}>
        {g.decisions.length ? (
          <ul className="flex flex-col gap-1.5 text-[12.5px]">
            {g.decisions.map((d) => (
              <li key={d.id} className="flex flex-wrap gap-x-xs">
                <span className="text-stone tnum">{fmtTime(d.at)}</span>
                <Badge tone="neutral">{d.agentName ?? d.agent}</Badge>
                <span className="font-mono text-[11px] text-steel">{d.decision}</span>
                <span className="min-w-0 flex-1 text-charcoal">{d.summary}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-[12px] text-stone">결정 기록이 아직 없습니다.</p>
        )}
      </Card>
    </div>
  );
}

function Fact({ k, v, href }: { k: string; v: string; href?: string }) {
  return (
    <div className="rounded-xl bg-surface-soft px-md py-2">
      <dt className="text-[11px] text-stone">{k}</dt>
      <dd className="font-bold text-ink tnum">{href ? <Link href={href} className="text-primary">{v}</Link> : v}</dd>
    </div>
  );
}
