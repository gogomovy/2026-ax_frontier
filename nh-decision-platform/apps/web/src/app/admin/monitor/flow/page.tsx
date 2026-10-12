"use client";

import Link from "next/link";
import { useState } from "react";
import { AdminPage, Card, JsonView, Loading, Select, StatusBadge, duration, fmtTime, useApiData } from "@/components/admin/kit";
import { BarList } from "@/components/charts/Bars";
import { Advanced, EmptyState } from "@/components/ui/Layout";
import { Badge, Button } from "@/components/ui/primitives";
import { StatCard, StatGrid } from "@/components/ui/StatCard";

interface FlowEvent {
  id: number;
  type: string;
  payload: Record<string, unknown>;
  actor: string | null;
  at: string;
  dispatchedAt: string | null;
  matched: { workflow?: string; reasons?: string[]; note?: string }[];
  runs: { run: string; workflow: string; status: string; startedAt: string; finishedAt: string | null; published: string[] }[];
  pending: { job: number; workflow: string; status: string; runAfter: string }[];
}

const TYPE_LABEL: Record<string, string> = {
  "dataset.committed": "데이터셋 확정",
  "document.ingested": "문서 등록",
  "rule.changed": "규칙 변경",
  "goal.confirmed": "경영목표 확정",
  "config.changed": "설정 변경",
  "ontology.changed": "스키마 변경",
  manual: "수동 실행",
  schedule: "정기 실행",
};

/** 데이터 흐름 — 변경 이벤트 → 매칭 워크플로우(사유) → 대기 작업 → 실행 → 게시 산출물 (ADM-11) */
export default function FlowMonitor() {
  const data = useApiData<FlowEvent[]>("/admin/monitor/flow?limit=80", { refreshMs: 4000 });
  const [type, setType] = useState("");
  const all = data.data ?? [];
  const byType = Object.entries(all.reduce<Record<string, number>>((m, e) => ((m[e.type] = (m[e.type] ?? 0) + 1), m), {})).sort((a, b) => b[1] - a[1]);
  const waiting = all.filter((e) => !e.dispatchedAt).length;
  const noMatch = all.filter((e) => e.dispatchedAt && !e.matched.some((m) => m.workflow)).length;
  const runCount = all.reduce((n, e) => n + e.runs.length, 0);
  const rows = all.filter((e) => !type || e.type === type);
  return (
    <AdminPage
      title="데이터 흐름"
      description="데이터 · 문서 · 규칙 · 목표가 바뀔 때마다 어떤 워크플로가 왜 실행됐는지(트리거 또는 계보) 보여 줍니다. 관련 없는 워크플로는 실행되지 않습니다. 4초마다 갱신됩니다."
      actions={
        <Button size="sm" variant="quiet" onClick={data.reload}>
          새로고침
        </Button>
      }
      summary={
        <div className="grid grid-cols-1 gap-lg xl:grid-cols-[1fr_1fr]">
          <StatGrid columns={2} label="흐름 요약">
            <StatCard label="최근 변경 이벤트" value={all.length} unit="건" hint="최근 80건 기준" />
            <StatCard label="이어진 실행" value={runCount} unit="건" hint="이벤트로 시작된 워크플로 실행" />
            <StatCard label="디스패치 대기" value={waiting} unit="건" tone={waiting ? "attention" : "default"} hint={waiting ? "워커가 아직 처리하지 않음" : "모두 처리됨"} />
            <StatCard label="관련 워크플로 없음" value={noMatch} unit="건" hint="트리거 · 계보에 맞는 워크플로가 없어 실행 안 함" />
          </StatGrid>
          <Card className="!mb-0">
            <BarList title="이벤트 종류별 건수" items={byType.map(([k, v]) => ({ label: TYPE_LABEL[k] ?? k, value: v, display: `${v}건` }))} />
          </Card>
        </div>
      }
    >
      <Loading error={data.error} loading={!data.data && data.loading} />
      <div className="mb-md flex flex-wrap items-center gap-xs">
        <Select
          className="w-[220px]"
          ariaLabel="이벤트 종류 고르기"
          value={type}
          onChange={setType}
          options={[{ value: "", label: "종류 전체" }, ...byType.map(([k]) => ({ value: k, label: TYPE_LABEL[k] ?? k }))]}
        />
        <span className="text-[12px] text-stone">{rows.length}건 표시</span>
      </div>
      {data.data && !rows.length ? <EmptyState title="변경 이벤트가 없습니다" description="자료를 반영하거나 규칙 · 문서를 바꾸면 여기에 흐름이 나타납니다." /> : null}
      <div className="flex flex-col gap-md">
        {rows.map((e) => (
          <Card key={e.id} className="!mb-0 !p-base">
            <div className="flex flex-wrap items-center gap-xs">
              <span className="font-mono text-[11px] text-stone">#{e.id}</span>
              <Badge tone="dark">{TYPE_LABEL[e.type] ?? e.type}</Badge>
              <span className="text-[12.5px] font-bold text-ink-deep">{describe(e)}</span>
              <span className="ml-auto text-[11px] text-stone">
                {fmtTime(e.at)} · {e.actor ?? "-"} {e.dispatchedAt ? "" : "· 디스패치 대기"}
              </span>
            </div>
            <div className="mt-xs grid grid-cols-1 gap-xs md:grid-cols-[1fr_1.4fr]">
              <div>
                <p className="text-[11px] font-bold text-steel">매칭 워크플로우</p>
                {e.matched.length ? (
                  <ul className="text-[12px]">
                    {e.matched.map((m, i) =>
                      m.workflow ? (
                        <li key={i}>
                          <b className="text-ink-deep">{m.workflow}</b> <span className="text-[11px] text-stone">{m.reasons?.join(" · ")}</span>
                        </li>
                      ) : (
                        <li key={i} className="text-[11px] text-stone">
                          {m.note}
                        </li>
                      ),
                    )}
                  </ul>
                ) : (
                  <p className="text-[11.5px] text-stone">{e.dispatchedAt ? "관련 워크플로우 없음 — 실행하지 않음" : "-"}</p>
                )}
              </div>
              <div>
                <p className="text-[11px] font-bold text-steel">실행 · 산출물</p>
                <ul className="space-y-0.5 text-[12px]">
                  {e.pending.map((p) => (
                    <li key={`p${p.job}`}>
                      <StatusBadge status={p.status} /> {p.workflow} · 실행 예정 {fmtTime(p.runAfter)}
                    </li>
                  ))}
                  {e.runs.map((r) => (
                    <li key={r.run}>
                      <StatusBadge status={r.status} />{" "}
                      <Link href={`/admin/monitor/runs?run=${r.run}`} className="font-bold text-primary">
                        {r.workflow}
                      </Link>{" "}
                      <span className="text-[11px] text-stone">
                        {duration(r.startedAt, r.finishedAt)} · 게시 {r.published.length ? r.published.join(", ") : "변경 없음"}
                      </span>
                    </li>
                  ))}
                  {!e.pending.length && !e.runs.length ? <li className="text-[11.5px] text-stone">-</li> : null}
                </ul>
              </div>
            </div>
            <div className="mt-xs">
              <Advanced label="이벤트 원본(JSON)">
                <JsonView value={e.payload} maxHeight={160} />
              </Advanced>
            </div>
          </Card>
        ))}
      </div>
    </AdminPage>
  );
}

function describe(e: FlowEvent): string {
  const p = e.payload as Record<string, string | number | boolean | undefined>;
  if (e.type.startsWith("dataset.")) return `${p.dataset} v${p.version}${p.rollback ? " (되돌리기)" : ""} · ${p.origin === "bank" ? "당행" : "외부"}${p.rows !== undefined ? ` · ${p.rows}행` : ""}`;
  if (e.type.startsWith("document.")) return `${p.doc_code} · ${p.doc_class} · ${p.origin === "bank" ? "당행" : "외부"}`;
  if (e.type === "rule.changed") return `${p.rule} v${p.version}`;
  if (e.type === "goal.confirmed") return `${p.goal ?? ""} · ${p.mode ?? ""}${p.value !== undefined ? ` · ${p.value}` : ""}`;
  if (e.type === "manual") return `${p.workflow} · ${p.reason ?? ""}`;
  if (e.type === "schedule") return `${p.workflow} · cron ${p.cron}`;
  return `${p.kind ?? ""} ${p.code ?? p.key ?? ""}`;
}
