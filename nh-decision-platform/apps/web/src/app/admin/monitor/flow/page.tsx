"use client";

import Link from "next/link";
import { AdminPage, Card, Collapse, JsonView, Loading, StatusBadge, duration, fmtTime, useApiData } from "@/components/admin/kit";
import { Badge, Button } from "@/components/ui/primitives";

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
  return (
    <AdminPage
      title="데이터 흐름"
      description="데이터·문서·규칙·목표가 바뀔 때마다 어떤 워크플로우가 왜 실행됐는지(트리거 또는 계보) 보여줍니다. 매칭되지 않은 워크플로우는 실행되지 않습니다. 4초마다 갱신됩니다."
      actions={<Button size="sm" variant="quiet" onClick={data.reload}>새로고침</Button>}
    >
      <Loading error={data.error} loading={!data.data && data.loading} />
      <div className="flex flex-col gap-md">
        {(data.data ?? []).map((e) => (
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
              <Collapse label="이벤트 내용">
                <JsonView value={e.payload} maxHeight={160} />
              </Collapse>
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
