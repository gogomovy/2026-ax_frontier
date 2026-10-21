"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { AdminPage, C, Card, Check, Collapse, JsonEditor, JsonView, Loading, Select, Table, Tabs, TextInput, fmtTime, useAction, useApiData } from "@/components/admin/kit";
import { ValueView } from "@/components/admin/ValueView";
import { Advanced, EmptyState } from "@/components/ui/Layout";
import { Badge, Button } from "@/components/ui/primitives";
import { StatCard, StatGrid } from "@/components/ui/StatCard";
import { apiPatch, apiPost } from "@/lib/api-client";

interface Metric {
  code: string;
  label: string;
  formula: string;
  args: Record<string, unknown>;
  workflow_code: string;
  unit: string;
  decimals: number | null;
  rounding: string | null;
  scale: number | null;
  figure_ids: string[];
  description: string;
  enabled: boolean;
  sort: number;
  latest: { display: number | null; previous: number | null; calcRunId: string | null; at: string | null };
}
interface Formula {
  id: string;
  version: number;
  expression: string;
  description: string;
  params: Record<string, string>;
  library: string;
  returns: string;
}
interface Binding {
  id: number;
  workflowCode: string;
  artifactKey: string;
  path: string;
  builder: string;
  params: Record<string, unknown>;
  enabled: boolean;
}

/** 지표 정의(데이터셋 → 커널 수식 → 화면 수치) · 수식 레지스트리 · 표/차트 바인딩 (CALC-01·09·11) */
export default function MetricsAdmin() {
  const data = useApiData<{ metrics: Metric[]; formulas: Formula[]; builders: { key: string; description: string }[]; bindings: Binding[] }>("/admin/metrics");
  const [tab, setTab] = useState<"metrics" | "formulas" | "bindings">("metrics");
  const [wf, setWf] = useState<string>("all");
  const { run, busy } = useAction();
  const [preview, setPreview] = useState<Record<string, unknown>>({});
  const wfs = useMemo(() => Array.from(new Set((data.data?.metrics ?? []).map((m) => m.workflow_code))), [data.data]);
  const [q, setQ] = useState("");
  const all = data.data?.metrics ?? [];
  const list = all.filter((m) => (wf === "all" || m.workflow_code === wf) && (!q || `${m.code} ${m.label} ${m.formula} ${m.figure_ids.join(" ")}`.toLowerCase().includes(q.toLowerCase())));
  const noValue = all.filter((m) => m.enabled && m.latest.display === null).length;
  const changed = all.filter((m) => m.latest.previous !== null && m.latest.previous !== m.latest.display).length;

  return (
    <AdminPage
      title="지표 · 계산"
      description="화면의 모든 수치는 이 정의로 계산됩니다. 입력은 데이터셋 조회(q) · 다른 지표 · 규칙 · 설정 참조이고, 계산은 커널 수식(decimal · numpy · scipy · scikit-learn)이 합니다. LLM 은 계산하지 않습니다."
      summary={
        <StatGrid columns={4} label="지표 요약">
          <StatCard label="지표" value={all.length || "-"} unit="개" hint={`사용 ${all.filter((m) => m.enabled).length} · 워크플로 ${wfs.length}`} />
          <StatCard label="값 없음" value={noValue} unit="개" tone={noValue ? "critical" : "success"} hint={noValue ? "필요한 자료가 없거나 계산 오류" : "사용 중인 지표 모두 값 있음"} />
          <StatCard label="최근 변경" value={changed} unit="개" tone={changed ? "attention" : "default"} hint="직전 계산과 값이 다름" />
          <StatCard label="수식 · 바인딩" value={`${data.data?.formulas.length ?? "-"} · ${data.data?.bindings.length ?? "-"}`} hint="커널 수식 · 표/차트 바인딩" />
        </StatGrid>
      }
    >
      <Tabs
        active={tab}
        onChange={setTab}
        tabs={[
          { key: "metrics", label: "지표", count: data.data?.metrics.length },
          { key: "formulas", label: "수식 레지스트리", count: data.data?.formulas.length },
          { key: "bindings", label: "표·차트 바인딩", count: data.data?.bindings.length },
        ]}
      />
      <Loading error={data.error} loading={!data.data && data.loading} />
      {tab === "metrics" ? <MetricProposals onChanged={data.reload} /> : null}
      {tab === "metrics" ? (
        <Card
          title={`지표 ${list.length}개`}
          actions={
            <>
              <TextInput ariaLabel="지표 찾기" placeholder="코드 · 이름 · 수식 · 화면 수치" value={q} onChange={setQ} className="w-[240px]" />
              <Select ariaLabel="워크플로 고르기" value={wf} onChange={setWf} options={[{ value: "all", label: "워크플로 전체" }, ...wfs.map((w) => ({ value: w, label: w }))]} className="w-[220px]" />
            </>
          }
        >
          {data.data && !list.length ? <EmptyState compact title="맞는 지표가 없습니다" description="찾는 말이나 워크플로를 바꿔 보세요." /> : null}
          <Table head={["지표", "수식", "표시", "최근 값", "사용", "정의"]}>
            {list.map((m) => (
              <tr key={m.code} className={m.enabled ? "" : "bg-surface-soft"}>
                <C className="min-w-[200px]">
                  <span className="font-bold text-ink-deep">{m.label}</span>
                  <p className="font-mono text-[10.5px] text-stone">
                    {m.code} → {m.figure_ids.join(", ") || "(화면 수치 없음)"}
                  </p>
                  {m.description ? <p className="text-[10.5px] text-attention">{m.description}</p> : null}
                </C>
                <C>
                  <Badge tone="info">{m.formula}</Badge>
                </C>
                <C className="text-[11px]">
                  {m.unit} · {m.decimals ?? "-"}자리 · {m.rounding ?? "기본"}
                  {m.scale ? ` · ÷${m.scale}` : ""}
                </C>
                <C right>
                  <span className="font-bold text-ink-deep">{m.latest.display ?? "-"}</span>
                  {m.latest.previous !== null && m.latest.previous !== m.latest.display ? <p className="text-[10.5px] text-attention">이전 {m.latest.previous}</p> : null}
                  <p className="text-[10px] text-stone">{fmtTime(m.latest.at)}</p>
                </C>
                <C>
                  <Check label="" ariaLabel={`${m.label} 사용`} checked={m.enabled} onChange={(v) => run(() => apiPatch(`/admin/metrics/${m.code}`, { enabled: v }), "저장했습니다", data.reload)} />
                </C>
                <C className="min-w-[360px]">
                  <Collapse label="입력 · 정의 편집 · 미리 계산">
                    <div className="mb-xs rounded-lg border border-hairline-soft p-xs">
                      <ValueView value={m.args} />
                    </div>
                    <JsonEditor value={{ formula: m.formula, args: m.args, unit: m.unit, decimals: m.decimals, rounding: m.rounding, scale: m.scale, figure_ids: m.figure_ids, label: m.label }} rows={12} disabled={busy} onSave={(v) => run(() => apiPatch(`/admin/metrics/${m.code}`, v), "지표 정의를 저장했습니다 — 다음 실행부터 적용", data.reload)} />
                    <Button size="sm" variant="quiet" className="mt-xs" disabled={busy} onClick={() => run(() => apiPost(`/admin/metrics/${m.code}/preview`), undefined).then((r) => r && setPreview({ ...preview, [m.code]: r }))}>
                      현재 데이터로 미리 계산(기록 안 함)
                    </Button>
                    {preview[m.code] ? (
                      <div className="mt-xs flex flex-col gap-xs">
                        <ValueView value={preview[m.code]} />
                        <Advanced label="미리 계산 원본(JSON)">
                          <JsonView value={preview[m.code]} maxHeight={260} />
                        </Advanced>
                      </div>
                    ) : null}
                  </Collapse>
                </C>
              </tr>
            ))}
          </Table>
        </Card>
      ) : null}
      {tab === "formulas" ? (
        <Card>
          <Table head={["수식 ID", "버전", "계산식", "입력", "라이브러리", "반환"]}>
            {(data.data?.formulas ?? []).map((f) => (
              <tr key={f.id}>
                <C mono>{f.id}</C>
                <C right>v{f.version}</C>
                <C className="max-w-[360px]">
                  <span className="text-ink-deep">{f.expression}</span>
                  <p className="text-[10.5px] text-stone">{f.description}</p>
                </C>
                <C className="font-mono text-[10.5px]">
                  {Object.entries(f.params).map(([k, v]) => (
                    <div key={k}>
                      {k}: {v}
                    </div>
                  ))}
                </C>
                <C>{f.library}</C>
                <C>{f.returns}</C>
              </tr>
            ))}
          </Table>
        </Card>
      ) : null}
      {tab === "bindings" ? (
        <Card>
          <p className="mb-md text-[12px] text-steel">산출물의 표·차트 블록을 계산 결과로 다시 그립니다. 경로는 `table:캡션` · `table_note:캡션` · `chart:제목` · `series:키` · 점 표기 경로를 씁니다.</p>
          <Table head={["워크플로우", "산출물 · 경로", "빌더", "사용", "파라미터"]}>
            {(data.data?.bindings ?? []).map((b) => (
              <tr key={b.id}>
                <C mono>{b.workflowCode}</C>
                <C className="max-w-[320px] text-[11.5px]">
                  <span className="font-bold">{b.artifactKey}</span>
                  <p className="font-mono text-[10.5px] text-stone">{b.path}</p>
                </C>
                <C>
                  <Badge>{b.builder}</Badge>
                  <p className="text-[10.5px] text-stone">{data.data?.builders.find((x) => x.key === b.builder)?.description}</p>
                </C>
                <C>
                  <Check label="" ariaLabel={`${b.artifactKey} ${b.path} 사용`} checked={b.enabled} onChange={(v) => run(() => apiPatch(`/admin/bindings/${b.id}`, { enabled: v }), "저장했습니다", data.reload)} />
                </C>
                <C className="min-w-[320px]">
                  <Collapse label="파라미터">
                    <JsonEditor value={b.params} rows={8} disabled={busy} onSave={(v) => run(() => apiPatch(`/admin/bindings/${b.id}`, { params: v }), "저장했습니다", data.reload)} />
                  </Collapse>
                </C>
              </tr>
            ))}
          </Table>
        </Card>
      ) : null}
    </AdminPage>
  );
}

interface MetricProposal {
  code: string;
  label: string;
  formula: string;
  unit: string;
  description: string;
  args: unknown;
}

/** 에이전트가 제안한 새 지표(§35 MET) — 자료가 올라오면 지표가 없는 자료의 측정 열로 제안. 승인하면 켜지고 계산 커널이 바로 계산한다 */
function MetricProposals({ onChanged }: { onChanged: () => Promise<void> }) {
  const props = useApiData<MetricProposal[]>("/admin/metric-proposals");
  const { run, busy } = useAction();
  const rows = props.data ?? [];
  if (!rows.length) return null;
  const after = async () => {
    await props.reload();
    await onChanged();
  };
  return (
    <Card title={`에이전트 제안 지표 ${rows.length}개 — 승인 대기`}>
      <p className="mb-md text-[12.5px] text-steel">
        새로 올라온 자료 가운데 아직 어떤 지표도 읽지 않는 자료의 측정 열로 지표 제안 에이전트가 만든 후보입니다. 승인하면 계산 커널이 바로 계산해 지표 이력에 남기고, 반려하면 같은 열을 다시 제안하지 않습니다. 자료를 소유한 부서의 데이터 책임자도{" "}
        <Link href="/knowledge/upload?tab=proposals" className="font-bold text-primary underline">
          에이전트 제안 승인함
        </Link>
        에서 같은 제안(분석 화면 · 개념 연결 포함)을 승인할 수 있습니다.
      </p>
      <Table head={["지표", "수식", "이유 · 자료", ""]}>
        {rows.map((m) => (
          <tr key={m.code} data-metric-proposal={m.code}>
            <C>
              <span className="font-bold text-ink-deep">{m.label}</span>
              <p className="font-mono text-[10.5px] text-stone">{m.code}</p>
            </C>
            <C>
              <Badge>{m.formula}</Badge> <span className="text-[11px] text-steel">{m.unit}</span>
              <Collapse label="입력">
                <JsonView value={m.args} />
              </Collapse>
            </C>
            <C className="max-w-[420px] text-[12px]">{m.description}</C>
            <C>
              <div className="flex gap-1">
                <Button size="sm" variant="confirm" disabled={busy} onClick={() => run(() => apiPost(`/admin/metric-proposals/${m.code}/approve`), "승인했습니다 — 계산이 대기열에 올라갑니다", after)}>
                  승인
                </Button>
                <Button size="sm" variant="ghost" disabled={busy} onClick={() => run(() => apiPost(`/admin/metric-proposals/${m.code}/reject`), "반려했습니다", after)}>
                  반려
                </Button>
              </div>
            </C>
          </tr>
        ))}
      </Table>
    </Card>
  );
}
