"use client";

import { useState } from "react";
import { AdminPage, C, Card, JsonView, Loading, Sparkline, Table, Tabs, fmtTime, useApiData } from "@/components/admin/kit";
import { Advanced, KeyValueList } from "@/components/ui/Layout";
import { Badge, Button } from "@/components/ui/primitives";
import { StatCard, StatGrid } from "@/components/ui/StatCard";
import { apiGetC } from "@/lib/api-client";

interface MetricMon {
  code: string;
  label: string;
  workflow: string | null;
  unit: string;
  formula: string | null;
  display: number | null;
  previous: number | null;
  changed: boolean;
  calcRunId: string | null;
  at: string;
  history: number[];
}
interface CalcRun {
  id: string;
  formula: string;
  version: number;
  metric: string | null;
  inputs: Record<string, unknown>;
  sources: unknown[];
  result: unknown;
  value: string | null;
  display: number | null;
  decimals: number | null;
  rounding: string | null;
  library: string | null;
  error: string | null;
  runId: string | null;
  createdAt: string;
}
interface Artifact {
  key: string;
  generation: number;
  producedBy: string;
  runId: string | null;
  createdAt: string;
  changes: number;
}

/** 수치 모니터링 — 지표 값·변화·추이, 계산 입력 스냅샷, 산출물 세대 (ADM-11, CALC-02) */
export default function CalcMonitor() {
  const [tab, setTab] = useState<"metrics" | "artifacts">("metrics");
  const metrics = useApiData<MetricMon[]>("/admin/monitor/metrics", { refreshMs: 10000 });
  const artifacts = useApiData<Artifact[]>("/admin/monitor/artifacts");
  const [onlyChanged, setOnlyChanged] = useState(false);
  const [sel, setSel] = useState<string | null>(null);
  const runs = useApiData<CalcRun[]>(sel ? `/admin/monitor/calc?metric=${encodeURIComponent(sel)}&limit=20` : null);
  const [art, setArt] = useState<unknown>(null);
  const list = (metrics.data ?? []).filter((m) => !onlyChanged || m.changed);
  const changed = (metrics.data ?? []).filter((m) => m.changed).length;
  const missing = (metrics.data ?? []).filter((m) => m.display === null).length;

  return (
    <AdminPage
      title="수치 모니터링"
      description="모든 지표의 최근 값 · 직전 값 · 추이와 계산 입력(데이터셋 버전 · 행 · 규칙 버전)을 봅니다. 화면에 나간 산출물이 몇 번째 세대인지, 어떤 실행이 만들었는지도 확인합니다."
      summary={
        <StatGrid columns={4} label="수치 요약">
          <StatCard label="지표" value={metrics.data?.length ?? "-"} unit="개" hint="계산 커널로 산출되는 지표" />
          <StatCard label="최근 변경" value={changed} unit="개" tone={changed ? "attention" : "default"} hint="직전 계산과 값이 다른 지표" />
          <StatCard label="값 없음" value={missing} unit="개" tone={missing ? "critical" : "default"} hint={missing ? "필요한 자료가 없거나 계산 오류" : "모든 지표에 값이 있음"} />
          <StatCard label="화면 산출물" value={artifacts.data?.length ?? "-"} unit="개" hint="화면에 게시된 결과 묶음" />
        </StatGrid>
      }
    >
      <Tabs active={tab} onChange={setTab} tabs={[{ key: "metrics", label: "지표", count: metrics.data?.length }, { key: "artifacts", label: "화면 산출물", count: artifacts.data?.length }]} />
      {tab === "metrics" ? (
        <div className="grid grid-cols-1 gap-lg xl:grid-cols-[1.3fr_1fr]">
          <Card title="지표" actions={<label className="text-[12px]"><input type="checkbox" checked={onlyChanged} onChange={(e) => setOnlyChanged(e.target.checked)} /> 변경된 것만</label>}>
            <Loading error={metrics.error} loading={!metrics.data && metrics.loading} />
            <Table head={["지표", "워크플로우", "값", "직전", "추이", "시각"]}>
              {list.map((m) => (
                <tr key={m.code} className={sel === m.code ? "bg-surface-soft" : ""}>
                  <C>
                    <button type="button" className="text-left" onClick={() => setSel(m.code)}>
                      <span className="font-bold text-ink-deep">{m.label}</span>
                      <p className="font-mono text-[10.5px] text-stone">
                        {m.code} · {m.formula}
                      </p>
                    </button>
                  </C>
                  <C className="text-[11px]">{m.workflow}</C>
                  <C right>
                    <b>{m.display ?? "-"}</b> <span className="text-[10.5px] text-stone">{m.unit}</span>
                  </C>
                  <C right>{m.changed ? <Badge tone="attention">{m.previous}</Badge> : <span className="text-stone">{m.previous ?? "-"}</span>}</C>
                  <C>
                    <Sparkline values={m.history} />
                  </C>
                  <C className="whitespace-nowrap text-[10.5px] text-stone">{fmtTime(m.at)}</C>
                </tr>
              ))}
            </Table>
          </Card>
          <Card title={sel ? `계산 이력 — ${sel}` : "계산 이력"}>
            {!sel ? <p className="text-[12px] text-stone">지표를 선택하세요.</p> : null}
            <Loading error={runs.error} loading={Boolean(sel) && !runs.data && runs.loading} />
            <div className="flex flex-col gap-md">
              {(runs.data ?? []).map((r) => (
                <div key={r.id} className="rounded-lg border border-hairline-soft p-md">
                  <div className="flex flex-wrap items-center gap-xs text-[12px]">
                    <Badge tone="info">
                      {r.formula} v{r.version}
                    </Badge>
                    <b>{r.display ?? "-"}</b>
                    <span className="font-mono text-[10.5px] text-stone">내부 {r.value}</span>
                    <span className="text-[10.5px] text-stone">
                      {r.decimals}자리 {r.rounding} · {r.library}
                    </span>
                    <span className="ml-auto text-[10.5px] text-stone">{fmtTime(r.createdAt)}</span>
                  </div>
                  {r.error ? <p className="mt-xs text-[11px] text-critical">{r.error}</p> : null}
                  {Object.keys(r.inputs ?? {}).length ? (
                    <div className="mt-xs">
                      <KeyValueList dense columns={1} items={Object.entries(r.inputs).slice(0, 12).map(([k, v]) => ({ label: <span className="font-mono text-[11px]">{k}</span>, value: typeof v === "object" ? JSON.stringify(v).slice(0, 120) : String(v) }))} />
                    </div>
                  ) : null}
                  <p className="mt-xs text-[11px] text-stone">출처 {Array.isArray(r.sources) ? r.sources.length : 0}건{r.runId ? ` · 실행 ${r.runId.slice(0, 8)}` : ""}</p>
                  <div className="mt-xs">
                    <Advanced label="계산 입력 · 출처 · 결과 원본(JSON)">
                      <JsonView value={{ inputs: r.inputs, sources: r.sources, result: r.result }} maxHeight={220} />
                    </Advanced>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        </div>
      ) : (
        <Card>
          <Loading error={artifacts.error} loading={!artifacts.data && artifacts.loading} />
          <Table head={["산출물", "세대", "생성", "수치 변경", "시각", ""]}>
            {(artifacts.data ?? []).map((a) => (
              <tr key={a.key}>
                <C mono>{a.key}</C>
                <C right>{a.generation}</C>
                <C>{a.producedBy === "seed" ? <Badge>목데이터 시드</Badge> : <Badge tone="info">{a.producedBy}</Badge>}</C>
                <C right>{a.changes}</C>
                <C className="text-[11px]">{fmtTime(a.createdAt)}</C>
                <C>
                  <Button size="sm" variant="quiet" onClick={() => apiGetC(`/admin/monitor/artifacts/${encodeURIComponent(a.key)}`).then((r) => setArt((r as { generations: unknown }).generations))}>
                    세대 이력
                  </Button>
                </C>
              </tr>
            ))}
          </Table>
          {art ? (
            <div className="mt-md">
              <Advanced label="세대 이력 원본(JSON)" defaultOpen>
                <JsonView value={art} maxHeight={420} />
              </Advanced>
            </div>
          ) : null}
        </Card>
      )}
    </AdminPage>
  );
}
