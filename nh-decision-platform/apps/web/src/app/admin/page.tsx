"use client";

import Link from "next/link";
import { AdminPage, C, Card, JsonEditor, Loading, StatusBadge, Table, fmtTime, useAction, useApiData } from "@/components/admin/kit";
import { Button } from "@/components/ui/primitives";
import { apiPut } from "@/lib/api-client";

interface SystemInfo {
  postgres: { ok: boolean; version?: string; vector?: string; size?: string; error?: string };
  neo4j: { ok: boolean; nodes?: number; relationships?: number; error?: string };
  litellm: { ok: boolean; status?: number; base_url?: string; connection?: string; error?: string };
  workers: { id: string; seenAt: string; alive: boolean; info: Record<string, unknown> }[];
  jobs: Record<string, number>;
  pendingEvents: number;
  users: Record<string, number>;
  recentRuns: { id: string; workflow: string; status: string; startedAt: string; finishedAt: string | null }[];
}
interface Readiness {
  at: string;
  ready: boolean;
  counts: { ok: number; warn: number; fail: number };
  items: { key: string; label: string; level: "ok" | "warn" | "fail"; message: string; fix: string }[];
}
const LEVEL = { ok: { status: "ok", label: "정상" }, warn: { status: "warning", label: "확인" }, fail: { status: "error", label: "위험" } } as const;
interface SettingRow {
  key: string;
  value: unknown;
  description: string;
  updatedBy: string | null;
  updatedAt: string;
}

/** 시스템 상태 · 설정값 (ADM-01, ADM-12) */
export default function AdminHome() {
  const sys = useApiData<SystemInfo>("/admin/system", { refreshMs: 10000 });
  const settings = useApiData<SettingRow[]>("/admin/settings");
  const ready = useApiData<Readiness>("/admin/readiness", { refreshMs: 60000 });
  const { run, busy } = useAction();
  const s = sys.data;

  return (
    <AdminPage title="시스템 상태" description="저장소 · 그래프 · LLM 게이트웨이 · 워커 · 작업 큐 상태와 운영 설정값입니다. 10초마다 갱신됩니다." actions={<Button size="sm" variant="quiet" onClick={sys.reload}>새로고침</Button>}>
      <Loading error={sys.error} loading={!s && sys.loading} />
      {s ? (
        <>
          <div className="mb-lg grid grid-cols-1 gap-md md:grid-cols-2 xl:grid-cols-4">
            <Tile title="PostgreSQL + pgvector" ok={s.postgres.ok} lines={[`버전 ${s.postgres.version ?? "-"}`, `vector ${s.postgres.vector ?? "-"}`, `크기 ${s.postgres.size ?? "-"}`, s.postgres.error ?? ""]} />
            <Tile title="Neo4j (온톨로지 그래프)" ok={s.neo4j.ok} lines={[`노드 ${s.neo4j.nodes ?? "-"}`, `관계 ${s.neo4j.relationships ?? "-"}`, s.neo4j.error ?? ""]} href="/admin/ontology" />
            <Tile title="LiteLLM 게이트웨이" ok={s.litellm.ok} lines={[s.litellm.connection ? `연결 ${s.litellm.connection}` : "연결 없음", s.litellm.base_url ?? "", s.litellm.error ?? ""]} href="/admin/llm" />
            <Tile
              title="워커 · 작업 큐"
              ok={s.workers.some((w) => w.alive)}
              lines={[
                `워커 ${s.workers.filter((w) => w.alive).length}개 동작`,
                `대기 이벤트 ${s.pendingEvents}`,
                Object.entries(s.jobs).map(([k, v]) => `${k} ${v}`).join(" · ") || "작업 없음",
              ]}
              href="/admin/monitor/flow"
            />
          </div>
          <Card title="최근 워크플로우 실행" actions={<Link href="/admin/monitor/runs" className="text-[12px] font-bold text-primary">전체 보기</Link>}>
            <Table head={["워크플로우", "상태", "시작", "종료"]}>
              {s.recentRuns.map((r) => (
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
                  <C>{fmtTime(r.finishedAt)}</C>
                </tr>
              ))}
            </Table>
          </Card>
          <p className="mb-lg text-[12px] text-steel">
            사용자: {Object.entries(s.users).map(([k, v]) => `${k} ${v}`).join(" · ")}{" "}
            {s.users.pending ? (
              <Link href="/admin/users" className="font-bold text-primary">
                승인 대기 처리 →
              </Link>
            ) : null}
          </p>
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
        actions={<span className="text-[11.5px] text-stone">서버에서는 make preflight</span>}
      >
        <Loading error={ready.error} loading={!ready.data && ready.loading} />
        {ready.data ? (
          <Table head={["항목", "상태", "현재", "고치는 방법"]}>
            {[...ready.data.items].sort((a, b) => ["fail", "warn", "ok"].indexOf(a.level) - ["fail", "warn", "ok"].indexOf(b.level)).map((it) => (
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
        ) : null}
      </Card>
      <Card title="운영 설정값" actions={<span className="text-[11.5px] text-stone">변경은 즉시 반영 · 감사 로그 기록</span>}>
        <Loading error={settings.error} loading={!settings.data && settings.loading} />
        <div className="flex flex-col gap-md">
          {settings.data?.map((row) => (
            <div key={row.key} className="grid grid-cols-1 gap-xs border-b border-hairline-soft pb-md lg:grid-cols-[280px_1fr]">
              <div>
                <p className="font-mono text-[12px] font-bold text-ink-deep">{row.key}</p>
                <p className="mt-0.5 text-[11.5px] text-steel">{row.description}</p>
                <p className="mt-0.5 text-[10.5px] text-stone">
                  {row.updatedBy ?? "-"} · {fmtTime(row.updatedAt)}
                </p>
              </div>
              <JsonEditor value={row.value} rows={typeof row.value === "object" ? 5 : 1} disabled={busy} onSave={(v) => run(() => apiPut<{ message?: string }>(`/admin/settings/${encodeURIComponent(row.key)}`, { value: v }), (r) => r?.message ?? "저장했습니다", settings.reload)} />
            </div>
          ))}
        </div>
      </Card>
    </AdminPage>
  );
}

function Tile({ title, ok, lines, href }: { title: string; ok: boolean; lines: string[]; href?: string }) {
  const body = (
    <div className="h-full rounded-2xl border border-hairline-soft p-base">
      <div className="flex items-center justify-between gap-xs">
        <p className="text-[13px] font-bold text-ink-deep">{title}</p>
        <StatusBadge status={ok ? "ok" : "error"} label={ok ? "정상" : "확인 필요"} />
      </div>
      <ul className="mt-xs space-y-0.5 text-[11.5px] text-steel">
        {lines.filter(Boolean).map((l, i) => (
          <li key={i} className="break-all">
            {l}
          </li>
        ))}
      </ul>
    </div>
  );
  return href ? <Link href={href}>{body}</Link> : body;
}
