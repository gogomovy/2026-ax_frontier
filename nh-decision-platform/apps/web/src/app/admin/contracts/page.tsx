"use client";

import { useState } from "react";
import { AdminPage, C, Card, Collapse, JsonEditor, Loading, Table, Tabs, fmtTime, useAction, useApiData } from "@/components/admin/kit";
import { Badge, Button } from "@/components/ui/primitives";
import { api, apiGetC, apiPatch, apiPost } from "@/lib/api-client";

interface ContractColumn {
  id: number;
  table: string;
  seq: number;
  column: string;
  kor: string;
  isPk: boolean;
  type: string | null;
  source: string | null;
  sourceColumn: string | null;
  isMock: boolean;
  expected: string | null;
  binding: Record<string, unknown>;
  active: boolean;
}
interface CheckRow {
  column: string;
  kind: string;
  value: string | null;
  display: string | null;
  unit: string | null;
  verdict: string;
  note: string;
  question: string | null;
  calcRunId: string | null;
}
interface ContractTable {
  code: string;
  name: string;
  dept: string;
  mart: string;
  workbook: string | null;
  columns: ContractColumn[];
  report: { baseYm: string | null; summary: Record<string, number>; columns: CheckRow[]; notes: string[]; rows?: number; kind?: string; table?: string | null } | null;
  reportAt: string | null;
  reportRun: string | null;
  workflow?: string | null;
  builder?: { builder: string; params?: Record<string, unknown> } | null;
}

const VERDICT: Record<string, { label: string; tone: "success" | "critical" | "attention" | "neutral" | "info" }> = {
  match: { label: "일치", tone: "success" },
  mismatch: { label: "불일치", tone: "critical" },
  no_expected: { label: "기대값 없음", tone: "neutral" },
  unmapped: { label: "미연결", tone: "attention" },
  error: { label: "오류", tone: "critical" },
  derived: { label: "파생", tone: "info" },
  text: { label: "서술", tone: "info" },
  row: { label: "행 값", tone: "info" },
  mapped: { label: "원천 확인", tone: "success" },
  empty: { label: "값 없음", tone: "neutral" },
};
const UNIT: Record<string, string> = { PCT: "%", PP: "%p", KRW_TN: "조원", KRW_BN: "억원", KRW_MN: "백만원", CNT: "건", RATIO: "" };

function bindingLabel(b: Record<string, unknown>): string {
  if ("metric" in b) return `지표 ${b.metric}${b.field ? `.${b.field}` : ""}`;
  if ("base_ym" in b) return `기준년월 (${b.base_ym})`;
  if ("const" in b) return `고정값 ${String(b.const)}`;
  if ("version" in b) return "제안 버전";
  if ("insight" in b) return `서술 ${b.insight}`;
  if ("proposal" in b) return `제안 ${b.proposal}.${b.field ?? "judgement"}`;
  if ("row" in b) return `행 값 ${b.row}${b.check ? ` · 대조 ${JSON.stringify(b.check)}` : ""}`;
  if ("dataset" in b) return `원천 ${b.dataset}${b.column ? `.${b.column}` : ""}`;
  if ("analysis" in b) return b.analysis === "id" ? "분석결과 ID(실행)" : "분석 갱신일";
  if ("evidence" in b) return `근거 문서 ${b.evidence}`;
  if ("report" in b) return `보고서 ${b.report}${b.section ? `#${b.section}` : b.field ? `.${b.field}` : " (HTML)"}`;
  if ("plan" in b) return `실행계획 ${b.plan}.${b.field ?? "body"}`;
  return `미연결${b.question ? ` (${b.question})` : ""}`;
}

/** 컬럼 정의서 — 업무 담당자가 정의한 화면 테이블의 컬럼·원천·산식을 지표에 연결하고, 정의서 화면값과 계산값을 대조 (DCT-01~08) */
export default function ContractsAdmin() {
  const data = useApiData<{ tables: ContractTable[]; metrics: string[]; workflow: string | null }>("/admin/contracts");
  const { run, busy } = useAction();
  const [tab, setTab] = useState<string>("T01");
  const [dept, setDept] = useState<string | null>(null);
  const [filter, setFilter] = useState<string>("all");
  const [file, setFile] = useState<File | null>(null);
  const [rows, setRows] = useState<{ table: string; columns: string[]; rows: Record<string, unknown>[] } | null>(null);
  const all = data.data?.tables ?? [];
  // 기준 부서(표 코드에 접두가 없는 T01 · 종기부)를 먼저, 나머지는 표 코드 순
  const depts = Array.from(new Set([...all.filter((x) => !x.code.includes("_")), ...all].map((x) => x.dept)));
  const curDept = dept ?? depts[0] ?? null;
  const tables = all.filter((x) => x.dept === curDept);
  const t = tables.find((x) => x.code === tab) ?? tables[0];
  const wf = t?.workflow ?? data.data?.workflow ?? null;
  const checks: Record<string, CheckRow> = Object.fromEntries((t?.report?.columns ?? []).map((c) => [c.column, c]));
  const list = (t?.columns ?? []).filter((c) => c.active && (filter === "all" || checks[c.column]?.verdict === filter || (filter === "mock" && c.isMock)));

  const upload = () => {
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    return run(() => api("/admin/contracts/import", { method: "POST", body: fd }), "정의서를 반영했습니다 — 적재 노드가 있는 워크플로우가 다시 계산합니다", data.reload);
  };

  return (
    <AdminPage
      title="컬럼 정의서"
      description="부서별 컬럼정의서(종기부 · 사업부서 · 영업점)의 각 컬럼을 지표(커널 계산) · 행 생성기 · 서술 · 원천에 연결합니다. 실행마다 mart 테이블에 적재하고, 정의서의 화면값(목업값)과 계산값을 단위 환산해 대조합니다. 원천이 없는 컬럼은 미연결로 남깁니다."
      actions={
        <Button size="sm" variant="confirm" disabled={busy || !wf} onClick={() => run(() => apiPost(`/admin/workflows/${wf}/run`), "다시 계산을 요청했습니다", data.reload)}>
          다시 계산{wf ? ` (${wf})` : ""}
        </Button>
      }
    >
      <Card title="정의서 업로드">
        <div className="flex flex-wrap items-end gap-md">
          <label className="block">
            <span className="mb-1 block text-[11.5px] font-bold text-steel">엑셀(.xlsx) — 시트명 `T01_부서_이름`, 헤더 `컬럼명 · 한글컬럼명 · PK유무 · TYPE · 원본데이터 · 원천 컬럼 · 목데이터 · 화면값`</span>
            <input type="file" accept=".xlsx" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="text-[12.5px]" />
          </label>
          <Button size="sm" variant="confirm" disabled={busy || !file} onClick={upload}>
            반영
          </Button>
          <span className="text-[11.5px] text-stone">기존 바인딩은 유지되고, 새 컬럼은 기본 바인딩(없으면 미연결)으로, 빠진 컬럼은 비활성으로 바뀝니다. DRM 암호화 파일은 해제 후 올려 주세요.</span>
        </div>
      </Card>
      <Loading error={data.error} loading={!data.data && data.loading} />
      {t ? (
        <>
          <div className="flex flex-wrap gap-1.5" role="group" aria-label="부서">
            {depts.map((d) => (
              <button key={d} type="button" aria-pressed={d === curDept} onClick={() => setDept(d)} className={`rounded-pill px-3 py-1 text-[12px] font-bold ${d === curDept ? "bg-ink-deep text-white" : "bg-surface-soft text-charcoal"}`}>
                {d} {all.filter((x) => x.dept === d).length}
              </button>
            ))}
          </div>
          <Tabs active={t.code} onChange={(k) => setTab(k)} tabs={tables.map((x) => ({ key: x.code, label: `${x.code} ${x.name}`, count: x.columns.filter((c) => c.active).length }))} />
          <Card
            title={
              <span className="flex flex-wrap items-center gap-xs">
                {t.code} {t.name} <Badge>{t.dept}</Badge> <code className="font-mono text-[11px] text-stone">{t.report?.kind === "source" ? "원천 검사(적재 안 함)" : t.mart}</code>
                {t.builder ? <Badge tone="info">행 생성기 {t.builder.builder}</Badge> : null}
                {t.report?.rows !== undefined && t.report.kind !== "source" ? <span className="text-[11px] text-stone">{t.report.rows}행</span> : null}
              </span>
            }
            actions={
              <>
                <span className="text-[11px] text-stone">
                  기준년월 {t.report?.baseYm ?? "-"} · 대조 {fmtTime(t.reportAt)} · 정의서 {t.workbook ?? "-"}
                </span>
                <Button size="sm" variant="quiet" onClick={() => apiGetC<{ table: string; columns: string[]; rows: Record<string, unknown>[] }>(`/admin/contracts/${t.code}/rows`).then(setRows)}>
                  적재 행 보기
                </Button>
              </>
            }
          >
            <div className="mb-md flex flex-wrap gap-1.5">
              {[["all", "전체"], ["mismatch", "불일치"], ["error", "오류"], ["unmapped", "미연결"], ["match", "일치"], ["row", "행 값"], ["mapped", "원천 확인"], ["no_expected", "기대값 없음"], ["mock", "목데이터"]].map(([k, l]) => (
                <button key={k} type="button" onClick={() => setFilter(k)} className={`rounded-pill px-3 py-1 text-[11.5px] font-bold ${filter === k ? "bg-ink-deep text-white" : "bg-surface-soft text-charcoal"}`}>
                  {l}
                  {k !== "all" && k !== "mock" ? ` ${t.report?.summary?.[k] ?? 0}` : ""}
                </button>
              ))}
            </div>
            {t.report?.notes?.length ? <p className="mb-md text-[11.5px] text-[#8a5d00]">{t.report.notes.join(" · ")}</p> : null}
            <Table head={["컬럼", "원천 · 산식(정의서)", "연결", "계산값", "정의서 화면값", "대조", ""]}>
              {list.map((c) => {
                const ch = checks[c.column];
                const v = VERDICT[ch?.verdict ?? "unmapped"] ?? VERDICT.unmapped;
                return (
                  <tr key={c.id}>
                    <C className="min-w-[220px]">
                      <span className="font-bold text-ink-deep">{c.kor}</span> {c.isPk ? <Badge tone="dark">PK</Badge> : null} {c.isMock ? <Badge tone="attention">목데이터</Badge> : null}
                      <p className="font-mono text-[10.5px] text-stone">
                        {c.column} · {c.type ?? "-"}
                      </p>
                    </C>
                    <C className="max-w-[300px] text-[11px]">
                      {c.source ?? "-"}
                      {c.sourceColumn ? <p className="text-stone">{c.sourceColumn}</p> : null}
                    </C>
                    <C className="text-[11px]">{bindingLabel(c.binding)}</C>
                    <C right>
                      {ch?.kind === "text" ? (
                        <span className="line-clamp-3 max-w-[280px] text-left text-[11px]">{ch.value}</span>
                      ) : (
                        <>
                          <b>{ch?.display ?? ch?.value ?? "-"}</b> <span className="text-[10.5px] text-stone">{ch?.unit ? UNIT[ch.unit] ?? ch.unit : ""}</span>
                        </>
                      )}
                    </C>
                    <C className="text-[11.5px]">{c.expected ?? "-"}</C>
                    <C className="min-w-[160px]">
                      <Badge tone={v.tone}>{v.label}</Badge>
                      {ch?.note ? <p className="mt-0.5 text-[10.5px] text-steel">{ch.note}</p> : null}
                    </C>
                    <C className="min-w-[260px]">
                      <Collapse label="연결 편집">
                        <p className="mb-1 text-[10.5px] text-stone">metric · row(check) · dataset(column) · base_ym · const · version · insight · proposal · report(section) · plan · evidence · analysis · unmapped — 설정 contracts.row_builders 로 행 생성기 변경</p>
                        <JsonEditor value={c.binding} rows={3} disabled={busy} onSave={(b) => run(() => apiPatch(`/admin/contracts/${c.id}`, { binding: b }), "연결을 저장했습니다 — 다시 계산합니다", data.reload)} />
                      </Collapse>
                    </C>
                  </tr>
                );
              })}
            </Table>
          </Card>
          {rows ? (
            <Card title={`${rows.table} — 최근 적재 행`}>
              <div className="max-h-[420px] overflow-auto">
                <Table head={rows.columns}>
                  {rows.rows.map((r, i) => (
                    <tr key={i}>
                      {rows.columns.map((k) => (
                        <C key={k} mono>
                          {r[k] === null || r[k] === undefined ? "" : String(r[k]).slice(0, 80)}
                        </C>
                      ))}
                    </tr>
                  ))}
                </Table>
              </div>
            </Card>
          ) : null}
        </>
      ) : null}
    </AdminPage>
  );
}
