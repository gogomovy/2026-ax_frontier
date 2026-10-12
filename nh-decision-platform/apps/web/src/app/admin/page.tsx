"use client";

import Link from "next/link";
import { AdminPage, C, Card, Loading, StatusBadge, Table, fmtTime, useApiData } from "@/components/admin/kit";
import { StackedBars } from "@/components/charts/Bars";
import { Advanced, EmptyState } from "@/components/ui/Layout";
import { Button, IconCheck } from "@/components/ui/primitives";
import { StatCard, StatGrid, type StatTone } from "@/components/ui/StatCard";

interface Overview {
  at: string;
  tasks: { key: string; label: string; count: number; href: string; tone: StatTone }[];
  pendingTotal: number;
  status: { key: string; label: string; ok: boolean; detail: string }[];
  runs24h: { total: number; succeeded?: number; degraded?: number; failed?: number; buckets: { label: string; values: Record<string, number> }[] };
  llm24h: { calls: number; tokens: number };
  users: Record<string, number>;
  workflows: number;
  recentRuns: { id: string; workflow: string; status: string; startedAt: string; finishedAt: string | null }[];
}
interface Readiness {
  at: string;
  ready: boolean;
  counts: { ok: number; warn: number; fail: number };
  items: { key: string; label: string; level: "ok" | "warn" | "fail"; message: string; fix: string }[];
}
const LEVEL = { ok: { status: "ok", label: "정상" }, warn: { status: "warning", label: "확인" }, fail: { status: "error", label: "위험" } } as const;

/** 관리자 홈 (Phase C · ADM-02) — 처리할 일 · 시스템 상태 · 최근 24시간 실행 · 운영 준비 점검 */
export default function AdminHome() {
  const ov = useApiData<Overview>("/admin/overview", { refreshMs: 15000 });
  const ready = useApiData<Readiness>("/admin/readiness", { refreshMs: 60000 });
  const o = ov.data;
  const open = o?.tasks.filter((t) => t.count > 0) ?? [];

  return (
    <AdminPage
      title="관리자 홈"
      description="처리할 일과 시스템 상태를 한눈에 봅니다. 숫자를 누르면 해당 화면으로 이동합니다. 15초마다 갱신됩니다."
      actions={
        <Button size="sm" variant="quiet" onClick={ov.reload}>
          새로고침
        </Button>
      }
    >
      <Loading error={ov.error} loading={!o && ov.loading} />
      {o ? (
        <>
          <section aria-labelledby="todo-head" className="mb-xl">
            <h2 id="todo-head" className="mb-md text-[16px] font-bold text-ink-deep">
              처리할 일 {o.pendingTotal ? <span className="tnum text-primary">{o.pendingTotal}</span> : null}
            </h2>
            {open.length === 0 ? (
              <EmptyState compact icon={<IconCheck />} title="지금 처리할 일이 없습니다" description="가입 · 자료 · 분석 · 실행 승인 대기와 경고 알림이 모두 비어 있습니다." />
            ) : (
              <StatGrid columns={3} label="처리할 일">
                {o.tasks.map((t) => (
                  <StatCard key={t.key} dataKey={`task-${t.key}`} label={t.label} value={t.count} unit="건" tone={t.count ? t.tone : "default"} href={t.href} hint={t.count ? "눌러서 처리" : "대기 없음"} />
                ))}
              </StatGrid>
            )}
          </section>

          <section aria-labelledby="status-head" className="mb-xl">
            <h2 id="status-head" className="mb-md text-[16px] font-bold text-ink-deep">
              시스템 상태
            </h2>
            <StatGrid columns={4} label="시스템 상태">
              {o.status.map((s) => (
                <StatCard key={s.key} dataKey={`status-${s.key}`} label={s.label} value={s.ok ? "정상" : "확인 필요"} tone={s.ok ? "success" : "attention"} hint={s.detail} />
              ))}
            </StatGrid>
          </section>

          <div className="mb-lg grid grid-cols-1 gap-lg xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
            <Card title="최근 24시간 워크플로 실행" actions={<Link href="/admin/monitor" className="text-[12px] font-bold text-primary">운영 개요</Link>}>
              <p className="mb-md text-[12.5px] text-steel">
                전체 <b className="tnum text-ink-deep">{o.runs24h.total}</b>건 · 성공 <b className="tnum text-success">{o.runs24h.succeeded ?? 0}</b> · 축소 <b className="tnum text-attention">{o.runs24h.degraded ?? 0}</b> · 실패 <b className="tnum text-critical">{o.runs24h.failed ?? 0}</b> · LLM 호출 <b className="tnum">{o.llm24h.calls}</b>회 · 토큰 <b className="tnum">{o.llm24h.tokens.toLocaleString("ko-KR")}</b>
              </p>
              <StackedBars
                title="시간대별 실행 상태"
                buckets={o.runs24h.buckets}
                series={[
                  { key: "succeeded", label: "성공", tone: "success" },
                  { key: "degraded", label: "축소", tone: "attention" },
                  { key: "failed", label: "실패", tone: "critical" },
                  { key: "running", label: "실행 중", tone: "info" },
                ]}
              />
            </Card>
            <Card title="최근 실행" actions={<Link href="/admin/monitor/runs" className="text-[12px] font-bold text-primary">전체 보기</Link>}>
              <Table head={["워크플로", "상태", "시작"]}>
                {o.recentRuns.map((r) => (
                  <tr key={r.id}>
                    <C>
                      <Link href={`/admin/monitor/runs?run=${r.id}`} className="font-bold text-ink-deep">
                        {r.workflow}
                      </Link>
                    </C>
                    <C>
                      <StatusBadge status={r.status} />
                    </C>
                    <C>{fmtTime(r.startedAt)}</C>
                  </tr>
                ))}
              </Table>
              <p className="mt-md text-[12px] text-steel">
                사용 중 워크플로 {o.workflows}개 · 사용자 {Object.entries(o.users).map(([k, v]) => `${USER_STATUS[k] ?? k} ${v}`).join(" · ")}
              </p>
            </Card>
          </div>
        </>
      ) : null}

      <Card
        title={
          ready.data ? (
            <span className="flex flex-wrap items-center gap-xs">
              운영 준비 점검 <StatusBadge status={ready.data.ready ? "ok" : "error"} label={ready.data.ready ? "운영 가능" : "위험 항목 있음"} />
              <span className="text-[11.5px] font-normal text-steel">
                정상 {ready.data.counts.ok} · 확인 {ready.data.counts.warn} · 위험 {ready.data.counts.fail}
              </span>
            </span>
          ) : (
            "운영 준비 점검"
          )
        }
        actions={<span className="text-[11.5px] text-stone">서버에서는 make preflight · 설정은 운영 설정 화면</span>}
      >
        <Loading error={ready.error} loading={!ready.data && ready.loading} />
        {ready.data ? (
          <>
            <ReadinessTable items={ready.data.items.filter((i) => i.level !== "ok")} empty="확인 · 위험 항목이 없습니다." />
            <div className="mt-md">
              <Advanced label={`정상 항목 ${ready.data.counts.ok}개 보기`}>
                <ReadinessTable items={ready.data.items.filter((i) => i.level === "ok")} empty="-" />
              </Advanced>
            </div>
          </>
        ) : null}
      </Card>
    </AdminPage>
  );
}

const USER_STATUS: Record<string, string> = { active: "사용", pending: "승인 대기", locked: "잠김", disabled: "중지" };

function ReadinessTable({ items, empty }: { items: Readiness["items"]; empty: string }) {
  if (!items.length) return <p className="text-[12.5px] text-steel">{empty}</p>;
  return (
    <Table head={["항목", "상태", "현재", "고치는 방법"]}>
      {[...items]
        .sort((a, b) => ["fail", "warn", "ok"].indexOf(a.level) - ["fail", "warn", "ok"].indexOf(b.level))
        .map((it) => (
          <tr key={it.key} data-readiness={it.key}>
            <C className="font-bold text-ink-deep">{it.label}</C>
            <C>
              <StatusBadge status={LEVEL[it.level].status} label={LEVEL[it.level].label} />
            </C>
            <C>{it.message}</C>
            <C className="text-steel">{it.level === "ok" ? "" : it.fix}</C>
          </tr>
        ))}
    </Table>
  );
}
