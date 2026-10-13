"use client";

import Link from "next/link";
import { useState } from "react";
import { AdminPage, Card, JsonView, Loading, StatusBadge, fmtTime, useAction, useApiData } from "@/components/admin/kit";
import { useConfirm } from "@/components/providers/UiProvider";
import { Advanced, EmptyState, KeyValueList, Notice } from "@/components/ui/Layout";
import { Badge, Button, PillTabs } from "@/components/ui/primitives";
import { StatCard, StatGrid } from "@/components/ui/StatCard";
import { apiPost } from "@/lib/api-client";
import { runStatusLabel } from "@/lib/labels";

interface Version {
  version: number;
  status: string;
  statusLabel: string;
  requestedByName?: string | null;
  requestedBy?: string | null;
  reviewedByName?: string | null;
  reviewedAt: string | null;
  reviewNote: string | null;
  createdAt: string;
  counts?: Record<string, number>;
  issues: number;
  sourceText?: string;
  spec?: {
    title: string;
    purpose: string;
    metrics: { key: string; label: string; formula: string; unit: string; args: Record<string, { q?: { dataset: string; col?: string; agg: string }; metric?: string; const?: number }> }[];
    tables: { key: string; caption: string; dataset: string; group_by: string; agg: string }[];
    insights: { key: string; title: string; instruction: string }[];
    schedule: { cron: string | null; on_data_change: boolean };
    evidence?: { query: string };
    llm?: boolean;
  };
  validation?: { ok: boolean; issues: { message: string }[] };
  preview?: { figures?: Record<string, { label: string; value: number | null; unit: string; stale?: boolean }>; opinions?: { id: string; severity: string; statement: string }[]; nodes?: { key: string; status: string }[] };
}
interface Item {
  code: string;
  space: string;
  spaceLabel: string;
  title: string;
  status: string;
  statusLabel: string;
  version: number;
  tabKey: string;
  workflow: string | null;
  requestedBy: string | null;
  requestedByName?: string | null;
  approvedAt: string | null;
  updatedAt: string;
  href: string | null;
  lastRun: { id: string; status: string; startedAt: string } | null;
  pendingVersion: number | null;
  versions: Version[];
  prompt?: { version: number; system: string } | null;
  workflowEnabled?: boolean;
}

const TABS = [
  { key: "pending", label: "승인 대기" },
  { key: "active", label: "동작 중" },
  { key: "paused", label: "일시 중지" },
  { key: "rejected", label: "반려" },
  { key: "retired", label: "폐기" },
  { key: "", label: "전체" },
] as const;
type TabKey = (typeof TABS)[number]["key"];
const STATUS_MAP: Record<string, string> = { active: "active", pending: "pending", paused: "disabled", retired: "rolled_back", rejected: "rejected", draft: "queued" };

/** 분석 에이전트 (Phase C · DAG-04 · DAG-08) — 부서가 요청한 분석의 명세 · 미리보기 검토 → 승인(생성) · 반려, 일시 중지 · 재개 · 폐기 */
export default function AdminAnalysisAgents() {
  const [tab, setTab] = useState<TabKey>("pending");
  const [sel, setSel] = useState<string | null>(null);
  const list = useApiData<{ items: Item[]; counts: Record<string, number> }>(`/admin/analysis-agents${tab ? `?status=${tab}` : ""}`, { refreshMs: 15000 });
  const detail = useApiData<Item>(sel ? `/admin/analysis-agents/${sel}` : null);
  const c = list.data?.counts ?? {};
  const reloadAll = async () => {
    await list.reload();
    if (sel) await detail.reload();
  };

  return (
    <AdminPage
      title="분석 에이전트"
      description="부서 사용자가 [분석 만들기]로 요청한 분석입니다. 정제된 명세(데이터 · 계산식 · 보고서 구성 · 에이전트 지시)와 미리보기를 확인해 승인하면 지표 · 워크플로 · 그 분석 전용 에이전트가 만들어지고 부서 분석 화면에 탭으로 나타납니다."
      summary={
        <StatGrid columns={4} label="분석 에이전트 요약">
          <StatCard label="승인 대기" value={c.pendingVersions ?? 0} unit="건" tone={c.pendingVersions ? "attention" : "success"} hint={c.pendingVersions ? "검토가 필요합니다" : "대기 중인 요청 없음"} />
          <StatCard label="동작 중" value={c.active ?? 0} unit="개" tone="info" hint="자료 변경 · 정기 실행 때 다시 계산" />
          <StatCard label="일시 중지" value={c.paused ?? 0} unit="개" hint="탭은 남고 다시 계산하지 않음" />
          <StatCard label="반려 · 폐기" value={(c.rejected ?? 0) + (c.retired ?? 0)} unit="개" />
        </StatGrid>
      }
    >
      <div className="mb-md">
        <PillTabs
          size="sm"
          label="분석 상태"
          value={tab}
          onChange={(k) => {
            setTab(k);
            setSel(null);
          }}
          items={TABS.map((t) => ({ key: t.key, label: t.label, count: t.key === "pending" ? c.pendingVersions : t.key ? c[t.key] : undefined }))}
        />
      </div>
      <div className="grid grid-cols-1 gap-lg xl:grid-cols-[380px_1fr]">
        <Card title={`분석 ${list.data?.items.length ?? 0}개`}>
          <Loading error={list.error} loading={!list.data && list.loading} />
          {list.data && !list.data.items.length ? <EmptyState compact title="해당하는 분석이 없습니다" description="부서가 [분석 만들기]로 요청하면 여기와 관리자 홈의 처리할 일에 나타납니다." /> : null}
          <ul className="flex flex-col">
            {(list.data?.items ?? []).map((a) => (
              <li key={a.code}>
                <button type="button" aria-current={sel === a.code ? "true" : undefined} onClick={() => setSel(a.code)} className={`row-button w-full border-b border-hairline-soft px-xs py-2 text-left ${sel === a.code ? "bg-surface-soft" : ""}`}>
                  <span className="flex items-center gap-xs">
                    <StatusBadge status={STATUS_MAP[a.status] ?? a.status} label={a.pendingVersion ? `v${a.pendingVersion} 승인 대기` : a.statusLabel} />
                    <span className="truncate text-[12.5px] font-bold text-ink-deep">{a.title}</span>
                  </span>
                  <span className="mt-0.5 block text-[11px] text-stone">
                    {a.spaceLabel} · {a.requestedByName ?? a.requestedBy ?? "-"} · {fmtTime(a.updatedAt)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </Card>
        <div className="min-w-0">
          {!sel ? <EmptyState title="분석을 고르세요" description="왼쪽에서 분석을 고르면 요청 글 · 명세 · 미리보기와 승인 · 수명 관리 동작이 보입니다." /> : null}
          <Loading error={detail.error} loading={Boolean(sel) && !detail.data && detail.loading} />
          {detail.data && detail.data.code === sel ? <Detail key={`${detail.data.code}-${detail.data.pendingVersion ?? detail.data.version}`} a={detail.data} reload={reloadAll} /> : null}
        </div>
      </div>
    </AdminPage>
  );
}

function Detail({ a, reload }: { a: Item; reload: () => Promise<void> }) {
  const { run, busy } = useAction();
  const confirm = useConfirm();
  const [note, setNote] = useState("");
  const pending = a.versions.find((v) => v.status === "pending");
  const shown = pending ?? a.versions[0];
  const spec = shown?.spec;
  // 관리자 승인 기준 (Q108) — 실행 주기 · 자료 변경 때 실행 · LLM 의견 사용. 요청 명세 값으로 시작
  const [cron, setCron] = useState(spec?.schedule.cron ?? "");
  const [onData, setOnData] = useState(spec?.schedule.on_data_change ?? true);
  const [llm, setLlm] = useState(spec?.llm !== false);
  return (
    <>
      <Card
        title={
          <span className="flex flex-wrap items-center gap-xs">
            {a.title} <code className="font-mono text-[11px] text-stone">{a.code}</code> <Badge>{a.spaceLabel}</Badge>
          </span>
        }
        actions={
          <>
            {a.href ? (
              <Link href={a.href} className="text-[12px] font-bold text-primary">
                분석 화면 보기
              </Link>
            ) : null}
            {a.workflow ? (
              <Link href={`/admin/monitor/runs${a.lastRun ? `?run=${a.lastRun.id}` : ""}`} className="text-[12px] font-bold text-primary">
                실행 기록
              </Link>
            ) : null}
          </>
        }
      >
        <KeyValueList
          items={[
            { label: "상태", value: a.statusLabel },
            { label: "승인 버전", value: a.version ? `v${a.version}` : "없음" },
            { label: "요청자", value: a.requestedByName ?? a.requestedBy ?? "-" },
            { label: "워크플로", value: a.workflow ? <code className="font-mono text-[11.5px]">{a.workflow}</code> : "승인 때 생성" },
            { label: "최근 실행", value: a.lastRun ? `${runStatusLabel(a.lastRun.status)} · ${fmtTime(a.lastRun.startedAt)}` : "-" },
            { label: "탭 키", value: <code className="font-mono text-[11.5px]">{a.tabKey}</code> },
          ]}
        />
        <div className="mt-md flex flex-wrap gap-xs">
          {a.status === "active" ? (
            <Button size="sm" variant="quiet" disabled={busy} onClick={() => run(() => apiPost(`/admin/analysis-agents/${a.code}/pause`), "일시 중지했습니다 — 탭은 남고 다시 계산하지 않습니다", reload)}>
              일시 중지
            </Button>
          ) : null}
          {a.status === "paused" ? (
            <Button size="sm" variant="confirm" disabled={busy} onClick={() => run(() => apiPost(`/admin/analysis-agents/${a.code}/resume`), "재개했습니다", reload)}>
              재개
            </Button>
          ) : null}
          {a.status !== "retired" ? (
            <Button
              size="sm"
              variant="ghost"
              disabled={busy}
              onClick={async () => {
                const ok = await confirm({ title: "이 분석을 폐기할까요?", body: `[${a.title}] 탭이 ${a.spaceLabel} 화면에서 사라지고 다시 계산하지 않습니다. 이력은 남습니다.`, confirmLabel: "폐기", tone: "danger" });
                if (ok) await run(() => apiPost(`/admin/analysis-agents/${a.code}/retire`), "폐기했습니다", reload);
              }}
            >
              폐기
            </Button>
          ) : null}
        </div>
      </Card>

      {shown ? (
        <Card title={`명세 v${shown.version} · ${shown.statusLabel}`} actions={<span className="text-[11.5px] text-stone">{shown.requestedByName ?? shown.requestedBy ?? "-"} · {fmtTime(shown.createdAt)}</span>}>
          {shown.validation && !shown.validation.ok ? <Notice tone="critical" title="검증을 통과하지 못한 명세입니다">{shown.validation.issues.map((i) => i.message).join(" · ")}</Notice> : null}
          {shown.validation?.ok && shown.validation.issues.length ? (
            <Notice tone="attention" title={`정제 · 검증에서 뺀 항목 ${shown.validation.issues.length}개`}>
              {shown.validation.issues.slice(0, 6).map((i) => i.message).join(" · ")}
            </Notice>
          ) : null}
          {shown.sourceText ? (
            <div className="my-md">
              <p className="mb-xs text-[11.5px] font-bold text-steel">요청 글 (에이전트에게는 구분자 안 참고 자료로만 전달)</p>
              <p className="whitespace-pre-wrap rounded-lg bg-surface-soft px-md py-2 text-[12.5px] leading-relaxed text-charcoal">{shown.sourceText}</p>
            </div>
          ) : null}
          {spec ? (
            <div className="flex flex-col gap-md">
              <KeyValueList
                items={[
                  { label: "목적", value: spec.purpose || "-" },
                  { label: "실행", value: `${spec.schedule.on_data_change ? "자료 변경 시" : ""}${spec.schedule.cron ? ` · 정기 ${spec.schedule.cron}` : ""}` || "수동" },
                  { label: "근거 검색", value: spec.evidence?.query ?? "사용 안 함" },
                ]}
              />
              <div>
                <p className="mb-xs text-[12.5px] font-bold text-ink-deep">지표 {spec.metrics.length}개</p>
                <ul className="flex flex-col gap-0.5 text-[12px]">
                  {spec.metrics.map((m) => (
                    <li key={m.key}>
                      <b className="text-ink-deep">{m.label}</b> <Badge tone="info">{m.formula}</Badge>{" "}
                      <span className="text-steel">
                        {Object.values(m.args)
                          .map((r) => (r.q ? `${r.q.dataset}.${r.q.col ?? "행"} ${r.q.agg}` : r.metric ? `지표 ${r.metric}` : `상수 ${r.const}`))
                          .join(", ")}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
              {spec.tables.length ? (
                <p className="text-[12px] text-steel">
                  표 · 그래프: {spec.tables.map((t) => `${t.caption}(${t.dataset} · ${t.group_by} ${t.agg})`).join(", ")}
                </p>
              ) : null}
              <div>
                <p className="mb-xs text-[12.5px] font-bold text-ink-deep">의견 · 에이전트 지시</p>
                <ul className="flex flex-col gap-0.5 text-[12px] text-charcoal">
                  {spec.insights.map((i) => (
                    <li key={i.key}>
                      <b>{i.title}</b> — {i.instruction || "(지시 없음)"}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          ) : null}
          {shown.preview?.figures ? (
            <div className="mt-md">
              <p className="mb-xs text-[12.5px] font-bold text-ink-deep">미리보기 계산 결과 (요청 시점)</p>
              <ul className="grid grid-cols-1 gap-xs sm:grid-cols-2 xl:grid-cols-3">
                {Object.entries(shown.preview.figures).map(([id, f]) => (
                  <li key={id} className="rounded-lg border border-hairline-soft px-md py-2">
                    <p className="text-[11.5px] text-steel">{f.label}</p>
                    <p className="text-[15px] font-bold text-ink-deep tnum">
                      {f.value === null ? <span className="text-critical">계산 불가</span> : `${f.value.toLocaleString("ko-KR")} ${f.unit === "NONE" ? "" : f.unit}`}
                    </p>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          <div className="mt-md flex flex-col gap-xs">
            <Advanced label="명세 원본(JSON)">
              <JsonView value={spec ?? {}} maxHeight={360} />
            </Advanced>
            {a.prompt ? (
              <Advanced label={`전용 에이전트 프롬프트 v${a.prompt.version}`} hint="관리자 [에이전트·프롬프트]에서 조정">
                <JsonView value={a.prompt.system} maxHeight={260} />
              </Advanced>
            ) : null}
          </div>
          {pending ? (
            <div className="mt-lg flex flex-col gap-xs border-t border-hairline-soft pt-md" data-analysis-review>
              <fieldset className="mb-xs rounded-xl border border-hairline-soft p-md" data-approval-options>
                <legend className="px-1 text-[12px] font-bold text-charcoal">승인 기준 — 실행 주기 · 비용</legend>
                <div className="grid grid-cols-1 gap-md md:grid-cols-[260px_1fr]">
                  <label className="block">
                    <span className="mb-1 block text-[11.5px] font-bold text-steel">정기 실행(cron, 비우면 없음)</span>
                    <input className="input !h-9 font-mono text-[13px]" value={cron} placeholder="예: 0 7 * * 1-5" onChange={(e) => setCron(e.target.value)} aria-label="정기 실행 cron" />
                  </label>
                  <div className="flex flex-col justify-end gap-1 pb-1 text-[12.5px] text-charcoal">
                    <label className="inline-flex items-center gap-1.5">
                      <input type="checkbox" checked={onData} onChange={(e) => setOnData(e.target.checked)} />
                      자료가 바뀌면 다시 계산
                    </label>
                    <label className="inline-flex items-center gap-1.5">
                      <input type="checkbox" checked={llm} onChange={(e) => setLlm(e.target.checked)} />
                      LLM 으로 의견 작성(실행마다 1회 호출 · 끄면 규칙 판정 · 기본 문장)
                    </label>
                  </div>
                </div>
              </fieldset>
              <label htmlFor={`an-note-${a.code}`} className="text-[12px] font-bold text-charcoal">
                검토 메모(반려 시 필수)
              </label>
              <textarea id={`an-note-${a.code}`} className="input text-[12.5px]" rows={2} value={note} maxLength={1000} onChange={(e) => setNote(e.target.value)} />
              <div className="flex flex-wrap gap-xs">
                <Button size="sm" variant="confirm" disabled={busy || !pending.validation?.ok} onClick={() => run(() => apiPost(`/admin/analysis-agents/${a.code}/versions/${pending.version}/approve`, { note: note || null, cron: cron.trim(), on_data_change: onData, llm }), "승인했습니다 — 첫 실행이 이어집니다", reload)}>
                  승인하고 만들기
                </Button>
                <Button size="sm" variant="ghost" disabled={busy || !note.trim()} onClick={() => run(() => apiPost(`/admin/analysis-agents/${a.code}/versions/${pending.version}/reject`, { note }), "반려했습니다", reload)}>
                  반려
                </Button>
              </div>
            </div>
          ) : null}
        </Card>
      ) : null}

      {a.versions.length > 1 ? (
        <Card title="버전 이력">
          <ul className="flex flex-col gap-0.5 text-[12px] text-charcoal">
            {a.versions.map((v) => (
              <li key={v.version}>
                v{v.version} · {v.statusLabel} · {fmtTime(v.createdAt)}
                {v.reviewedAt ? ` · 처리 ${v.reviewedByName ?? "-"} ${fmtTime(v.reviewedAt)}` : ""}
                {v.reviewNote ? ` · ${v.reviewNote}` : ""}
              </li>
            ))}
          </ul>
        </Card>
      ) : null}
    </>
  );
}
