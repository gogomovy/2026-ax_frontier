"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { AdminPage, C, Card, Loading, StatusBadge, Table, fmtTime, useAction, useApiData } from "@/components/admin/kit";
import { Notice } from "@/components/ui/Layout";
import { Badge, Button, PillTabs } from "@/components/ui/primitives";
import { StatCard, StatGrid } from "@/components/ui/StatCard";
import { apiPost } from "@/lib/api-client";
import { refreshConditions, stateLabel, type WorkflowStatus } from "@/lib/refreshStatus";

interface Item extends WorkflowStatus {
  runs24h: number;
  failed24h: number;
  kind: "business" | "analysis_agent" | "base";
}
interface Overview {
  workflows: Item[];
  decisions: { id: number; at: string; decision: "impact" | "skip"; summary: string; matched: string[]; kinds: Record<string, number> }[];
  policy: { debounceSec: number; maxChain: number; routeOn: string[]; maxRoute: number; requireApproval: string[]; holdSec: number; maxHoldSec: number; llmJudge: boolean; schedulerEverySec: number; timezone: string };
  counts: { workflows: number; pending: number; cron: number; failed24h: number };
  generatedAt: string;
}

const KINDS = [
  { key: "business", label: "업무 흐름" },
  { key: "analysis_agent", label: "분석 에이전트" },
  { key: "base", label: "기반(그래프 · 온톨로지)" },
  { key: "all", label: "전체" },
] as const;
type KindKey = (typeof KINDS)[number]["key"];

/**
 * 자동 실행 · 변경 감지 (Phase P · AGW-09) — 흐름마다 무엇이 바뀌면 다시 계산되는지(감지 조건 · 상위 흐름 · 정기 실행),
 * 지금 반영 대기 · 실행 중인지, 최근 영향 판단(판단 에이전트) 기록. 흐름별로 바로 실행할 수 있다.
 */
export default function AutomationAdmin() {
  const data = useApiData<Overview>("/admin/automation", { refreshMs: 15000 });
  const { run, busy } = useAction();
  const [kind, setKind] = useState<KindKey>("business");
  const items = useMemo(() => (data.data?.workflows ?? []).filter((w) => kind === "all" || w.kind === kind), [data.data, kind]);
  const c = data.data?.counts;
  const p = data.data?.policy;
  return (
    <AdminPage
      title="자동 실행 · 변경 감지"
      description="자료 · 문서 · 경영목표 · 판정 규칙 · 공통 통합 DB · 상위 분석 결과가 바뀌면 판단 에이전트가 영향받는 흐름을 정하고, 오케스트레이터가 순서를 맞춰 다시 계산합니다. 흐름마다 감지 조건 · 정기 실행 · 지금 상태를 봅니다."
      summary={
        <StatGrid columns={4} label="자동 실행 요약">
          <StatCard label="흐름" value={c?.workflows ?? 0} unit="개" />
          <StatCard label="반영 대기 · 실행 중" value={c?.pending ?? 0} unit="개" tone={c?.pending ? "info" : "success"} hint={c?.pending ? "새 자료를 반영하는 중" : "모두 최신"} />
          <StatCard label="정기 실행" value={c?.cron ?? 0} unit="건" hint={p ? `워커가 ${p.schedulerEverySec}초마다 확인 · ${p.timezone}` : undefined} />
          <StatCard label="24시간 실패" value={c?.failed24h ?? 0} unit="회" tone={c?.failed24h ? "critical" : "success"} />
        </StatGrid>
      }
    >
      <Loading error={data.error} loading={!data.data && data.loading} />
      {p ? (
        <Notice tone="info" title="감지 → 판단 → 실행 순서">
          ① 변경 이벤트(자료 반영 · 되돌림 · 삭제, 문서, 목표 확정, 규칙 · 정의 변경, 상위 흐름 결과 변화) → ② 판단 에이전트가 명시 조건 · 계보 · 팀 · 공통 · 상위 지표로 영향 흐름을 정함(같은 파일 재반영은 건너뜀) → ③{" "}
          {p.debounceSec}초 모아서(디바운스) 대기열 → ④ 오케스트레이터가 상위 흐름 완료를 기다림(최대 {p.maxHoldSec}초) → ⑤ 계산 · 변화 감지(LLM {p.llmJudge ? "켜짐" : "꺼짐"}) · 실행 계획 · 서술 · 검증 · 게시 → ⑥ 결과가 바뀐 지표를 쓰는 하위 흐름으로 전파(최대 연쇄{" "}
          {p.maxChain}){p.routeOn.length ? ` · LLM 경로 지정: ${p.routeOn.join(", ")}` : ""}
          {p.requireApproval.length ? ` · 사람 승인 대상: ${p.requireApproval.join(", ")}` : ""}.
        </Notice>
      ) : null}
      <div className="my-md">
        <PillTabs size="sm" label="흐름 종류" value={kind} onChange={(k) => setKind(k)} items={KINDS.map((k) => ({ key: k.key, label: k.label, count: k.key === "all" ? data.data?.workflows.length : data.data?.workflows.filter((w) => w.kind === k.key).length }))} />
      </div>
      <Card title={`흐름 ${items.length}개`}>
        <Table head={["흐름", "상태", "자동으로 다시 계산되는 때", "다음 정기 실행", "마지막 실행", "24시간", ""]}>
          {items.map((w) => {
            const conds = refreshConditions(w);
            return (
              <tr key={w.workflow} data-automation-row={w.workflow}>
                <C>
                  <span className="block font-bold text-ink-deep">{w.name}</span>
                  <code className="font-mono text-[11px] text-stone">{w.workflow}</code>
                  {!w.enabled ? <Badge>꺼짐</Badge> : null}
                </C>
                <C>
                  <Badge tone={w.state === "idle" ? "success" : w.state === "approval" ? "attention" : "info"}>{stateLabel(w.state)}</Badge>
                  {w.pending?.causes.length ? <span className="mt-0.5 block max-w-[220px] text-[11px] text-steel">{w.pending.causes.slice(-2).join(" · ")}</span> : null}
                </C>
                <C className="max-w-[360px] text-[12px]">{conds.length ? conds.join(" · ") : "수동 실행만"}</C>
                <C className="text-[12px] tnum">{w.triggers.cron[0] ? `${w.triggers.cron[0].label} · ${fmtTime(w.triggers.cron[0].next)}` : "-"}</C>
                <C className="text-[12px]">
                  {w.lastRun ? (
                    <Link href={`/admin/monitor/runs?run=${w.lastRun.id}`} className="inline-flex items-center gap-1 text-primary">
                      <StatusBadge status={w.lastRun.status} /> {fmtTime(w.lastRun.finishedAt ?? w.lastRun.startedAt)}
                    </Link>
                  ) : (
                    "-"
                  )}
                </C>
                <C right>
                  {w.runs24h}회{w.failed24h ? <span className="text-critical"> · 실패 {w.failed24h}</span> : null}
                </C>
                <C>
                  <Button size="sm" variant="ghost" disabled={busy || !w.enabled} onClick={() => run(() => apiPost(`/admin/workflows/${w.workflow}/run`, {}), `${w.name} — 실행 대기열에 올렸습니다`, data.reload)}>
                    지금 실행
                  </Button>
                </C>
              </tr>
            );
          })}
        </Table>
      </Card>
      <Card title="최근 영향 판단 (판단 에이전트)">
        {data.data && !data.data.decisions.length ? <p className="text-[12.5px] text-stone">아직 판단 기록이 없습니다 — 자료를 반영하면 여기에 남습니다.</p> : null}
        <Table head={["시각", "판단", "내용", "다시 계산한 흐름"]}>
          {(data.data?.decisions ?? []).map((d) => (
            <tr key={d.id}>
              <C className="whitespace-nowrap text-[12px] tnum">{fmtTime(d.at)}</C>
              <C>
                <Badge tone={d.decision === "skip" ? "neutral" : "info"}>{d.decision === "skip" ? "건너뜀" : "영향"}</Badge>
              </C>
              <C className="text-[12px]">{d.summary}</C>
              <C mono className="max-w-[280px]">
                {d.matched.join(", ") || "-"}
              </C>
            </tr>
          ))}
        </Table>
      </Card>
    </AdminPage>
  );
}
