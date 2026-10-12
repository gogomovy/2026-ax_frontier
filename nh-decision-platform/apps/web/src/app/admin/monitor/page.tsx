"use client";

import Link from "next/link";
import { useState } from "react";
import { AdminPage, C, Card, Loading, StatusBadge, Table, fmtTime, useApiData } from "@/components/admin/kit";
import { BarList, StackedBars } from "@/components/charts/Bars";
import { EmptyState } from "@/components/ui/Layout";
import { PillTabs } from "@/components/ui/primitives";
import { StatCard, StatGrid } from "@/components/ui/StatCard";

interface Bucket {
  label: string;
  values: Record<string, number>;
}
interface MonitorOverview {
  hours: number;
  kpi: { runs: number; successRate: number | null; failed: number; degraded: number; avgMs: number | null; p95Ms: number | null; llmCalls: number; llmErrors: number; tokens: number; llmAvgMs: number | null; events: number; alerts: number };
  runs: Bucket[];
  llm: Bucket[];
  events: Bucket[];
  eventTypes: { type: string; count: number }[];
  workflows: { workflow: string; runs: number; succeeded: number; degraded: number; failed: number; successRate: number | null; avgMs: number | null; p95Ms: number | null }[];
  slowNodes: { impl: string; count: number; avgMs: number; failed: number }[];
  agents: { agent: string; calls: number; tokens: number; errors: number }[];
  budget: { monthly?: { tokens?: number; cost?: number }; limits?: Record<string, unknown> } & Record<string, unknown>;
  failures: { id: string; workflow: string; status: string; startedAt: string; error: string }[];
  recentAlerts: { id: number; at: string; kind: string; severity: string; title: string; status: string }[];
}

const ms = (v: number | null | undefined) => (v === null || v === undefined ? "-" : v < 1000 ? `${v}ms` : `${(v / 1000).toFixed(1)}s`);
const n = (v: number) => v.toLocaleString("ko-KR");

/** 운영 개요 (Phase C · MON-01 · Q105) — 실행 · LLM · 이벤트 · 알림을 시간대별로 */
export default function MonitorOverviewPage() {
  const [hours, setHours] = useState<"24" | "168">("24");
  const ov = useApiData<MonitorOverview>(`/admin/monitor/overview?hours=${hours}`, { refreshMs: 30000 });
  const o = ov.data;
  const k = o?.kpi;
  return (
    <AdminPage
      title="운영 개요"
      description="워크플로 실행 · LLM 호출 · 이벤트 처리 · 알림을 한 화면에서 봅니다. 그래프마다 '표로 보기' 로 같은 수치를 표로 볼 수 있습니다. 30초마다 갱신됩니다."
      actions={<PillTabs size="sm" label="기간" value={hours} onChange={setHours} items={[{ key: "24", label: "최근 24시간" }, { key: "168", label: "최근 7일" }]} />}
    >
      <Loading error={ov.error} loading={!o && ov.loading} />
      {o && k ? (
        <>
          <div className="mb-xl">
            <StatGrid columns={6} label="핵심 지표">
              <StatCard dataKey="runs" label="워크플로 실행" value={n(k.runs)} unit="건" hint={`축소 ${k.degraded} · 실패 ${k.failed}`} tone={k.failed ? "critical" : k.degraded ? "attention" : "default"} href="/admin/monitor/runs" />
              <StatCard dataKey="success" label="성공률(축소 포함)" value={k.successRate ?? "-"} unit={k.successRate === null ? undefined : "%"} tone={k.successRate === null ? "default" : k.successRate >= 99 ? "success" : k.successRate >= 95 ? "attention" : "critical"} hint="실패가 아닌 실행 비율" />
              <StatCard dataKey="duration" label="실행 소요" value={ms(k.avgMs)} hint={`평균 · p95 ${ms(k.p95Ms)}`} />
              <StatCard dataKey="llm" label="LLM 호출" value={n(k.llmCalls)} unit="회" hint={`오류 ${k.llmErrors} · 평균 ${ms(k.llmAvgMs)}`} tone={k.llmErrors ? "attention" : "default"} href="/admin/monitor/alerts" />
              <StatCard dataKey="tokens" label="LLM 토큰" value={n(k.tokens)} hint="입력 + 출력" />
              <StatCard dataKey="events" label="이벤트 · 알림" value={n(k.events)} unit="건" hint={`알림 ${k.alerts}건`} tone={k.alerts ? "attention" : "default"} href="/admin/monitor/flow" />
            </StatGrid>
          </div>

          <div className="grid grid-cols-1 gap-lg xl:grid-cols-2">
            <Card title="실행 상태 추이">
              <StackedBars
                title={`${o.hours === 24 ? "1시간" : "6시간"} 단위 실행 상태`}
                buckets={o.runs}
                series={[
                  { key: "succeeded", label: "성공", tone: "success" },
                  { key: "degraded", label: "축소", tone: "attention" },
                  { key: "failed", label: "실패", tone: "critical" },
                  { key: "running", label: "실행 중", tone: "info" },
                ]}
              />
            </Card>
            <Card title="LLM 호출 추이">
              <StackedBars
                title={`${o.hours === 24 ? "1시간" : "6시간"} 단위 LLM 호출`}
                buckets={o.llm}
                series={[
                  { key: "ok", label: "정상", tone: "primary" },
                  { key: "error", label: "오류", tone: "critical" },
                ]}
              />
            </Card>
            <Card title="워크플로별 실행" actions={<Link href="/admin/workflows" className="text-[12px] font-bold text-primary">워크플로</Link>}>
              {o.workflows.length === 0 ? (
                <EmptyState compact title="이 기간에 실행이 없습니다" />
              ) : (
                <Table head={["워크플로", "실행", "성공률", "평균", "p95", "축소 · 실패"]}>
                  {o.workflows.map((w) => (
                    <tr key={w.workflow} data-monitor-workflow={w.workflow}>
                      <C>
                        <Link href={`/admin/monitor/runs?workflow=${w.workflow}`} className="font-bold text-ink-deep">
                          {w.workflow}
                        </Link>
                      </C>
                      <C right>{w.runs}</C>
                      <C right>{w.successRate === null ? "-" : `${w.successRate}%`}</C>
                      <C right>{ms(w.avgMs)}</C>
                      <C right>{ms(w.p95Ms)}</C>
                      <C right>
                        {w.degraded} · <span className={w.failed ? "font-bold text-critical" : undefined}>{w.failed}</span>
                      </C>
                    </tr>
                  ))}
                </Table>
              )}
            </Card>
            <Card title="노드 평균 소요(느린 순)">
              <BarList
                title="노드 종류별 평균 소요"
                items={o.slowNodes.map((s) => ({ label: `${s.impl} (${s.count}회${s.failed ? ` · 실패 ${s.failed}` : ""})`, value: s.avgMs, display: ms(s.avgMs), tone: s.failed ? "critical" : "primary" }))}
              />
            </Card>
            <Card title="에이전트별 LLM 토큰">
              <BarList title="에이전트별 토큰(많은 순)" items={o.agents.map((a) => ({ label: `${a.agent} (${a.calls}회${a.errors ? ` · 오류 ${a.errors}` : ""})`, value: a.tokens, display: n(a.tokens), tone: a.errors ? "attention" : "primary" }))} />
            </Card>
            <Card title="이벤트 처리" actions={<Link href="/admin/monitor/flow" className="text-[12px] font-bold text-primary">데이터 흐름</Link>}>
              <StackedBars
                title="이벤트 디스패치"
                buckets={o.events}
                series={[
                  { key: "dispatched", label: "처리됨", tone: "primary" },
                  { key: "pending", label: "대기", tone: "attention" },
                ]}
                height={80}
              />
              <div className="mt-md">
                <BarList title="이벤트 종류" items={o.eventTypes.map((e) => ({ label: e.type, value: e.count, tone: "neutral" }))} />
              </div>
            </Card>
          </div>

          <div className="mt-lg grid grid-cols-1 gap-lg xl:grid-cols-2">
            <Card title="최근 실패 · 축소 실행">
              {o.failures.length === 0 ? (
                <EmptyState compact title="실패 · 축소 실행이 없습니다" />
              ) : (
                <Table head={["워크플로", "상태", "시작", "오류"]}>
                  {o.failures.map((f) => (
                    <tr key={f.id}>
                      <C>
                        <Link href={`/admin/monitor/runs?run=${f.id}`} className="font-bold text-ink-deep">
                          {f.workflow}
                        </Link>
                      </C>
                      <C>
                        <StatusBadge status={f.status} />
                      </C>
                      <C>{fmtTime(f.startedAt)}</C>
                      <C className="max-w-[320px] truncate text-steel">{f.error || "-"}</C>
                    </tr>
                  ))}
                </Table>
              )}
            </Card>
            <Card title="최근 알림" actions={<Link href="/admin/monitor/alerts" className="text-[12px] font-bold text-primary">알림 · 비용</Link>}>
              {o.recentAlerts.length === 0 ? (
                <EmptyState compact title="이 기간에 알림이 없습니다" />
              ) : (
                <Table head={["시각", "심각도", "내용", "발송"]}>
                  {o.recentAlerts.map((a) => (
                    <tr key={a.id}>
                      <C>{fmtTime(a.at)}</C>
                      <C>
                        <StatusBadge status={a.severity === "critical" ? "error" : a.severity === "warning" ? "warning" : "ok"} label={a.severity} />
                      </C>
                      <C>{a.title}</C>
                      <C>{a.status}</C>
                    </tr>
                  ))}
                </Table>
              )}
            </Card>
          </div>
        </>
      ) : null}
    </AdminPage>
  );
}
