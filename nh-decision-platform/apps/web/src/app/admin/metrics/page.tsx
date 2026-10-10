"use client";

import { useMemo, useState } from "react";
import { AdminPage, C, Card, Check, Collapse, JsonEditor, JsonView, Loading, Table, Tabs, fmtTime, useAction, useApiData } from "@/components/admin/kit";
import { Badge, Button } from "@/components/ui/primitives";
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
  const list = (data.data?.metrics ?? []).filter((m) => wf === "all" || m.workflow_code === wf);

  return (
    <AdminPage
      title="지표 · 계산"
      description="화면의 모든 수치는 이 정의로 계산됩니다. 입력은 데이터셋 조회(q) · 다른 지표 · 규칙 · 설정 참조이고, 계산은 커널 수식(decimal · numpy · scipy · scikit-learn)이 합니다. LLM 은 계산하지 않습니다."
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
      {tab === "metrics" ? (
        <Card
          actions={
            <div className="flex flex-wrap gap-1">
              {["all", ...wfs].map((w) => (
                <button key={w} type="button" onClick={() => setWf(w)} className={`rounded-pill px-3 py-1 text-[11.5px] font-bold ${wf === w ? "bg-ink-deep text-white" : "bg-surface-soft text-charcoal"}`}>
                  {w === "all" ? "전체" : w}
                </button>
              ))}
            </div>
          }
        >
          <Table head={["지표", "수식", "표시", "최근 값", "사용", "정의"]}>
            {list.map((m) => (
              <tr key={m.code} className={m.enabled ? "" : "opacity-60"}>
                <C className="min-w-[200px]">
                  <span className="font-bold text-ink-deep">{m.label}</span>
                  <p className="font-mono text-[10.5px] text-stone">
                    {m.code} → {m.figure_ids.join(", ") || "(화면 수치 없음)"}
                  </p>
                  {m.description ? <p className="text-[10.5px] text-[#8a5d00]">{m.description}</p> : null}
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
                  {m.latest.previous !== null && m.latest.previous !== m.latest.display ? <p className="text-[10.5px] text-[#8a5d00]">이전 {m.latest.previous}</p> : null}
                  <p className="text-[10px] text-stone">{fmtTime(m.latest.at)}</p>
                </C>
                <C>
                  <Check label="" checked={m.enabled} onChange={(v) => run(() => apiPatch(`/admin/metrics/${m.code}`, { enabled: v }), "저장했습니다", data.reload)} />
                </C>
                <C className="min-w-[360px]">
                  <Collapse label="정의 편집 · 미리 계산">
                    <JsonEditor value={{ formula: m.formula, args: m.args, unit: m.unit, decimals: m.decimals, rounding: m.rounding, scale: m.scale, figure_ids: m.figure_ids, label: m.label }} rows={12} disabled={busy} onSave={(v) => run(() => apiPatch(`/admin/metrics/${m.code}`, v), "지표 정의를 저장했습니다 — 다음 실행부터 적용", data.reload)} />
                    <Button size="sm" variant="quiet" className="mt-xs" disabled={busy} onClick={() => run(() => apiPost(`/admin/metrics/${m.code}/preview`), undefined).then((r) => r && setPreview({ ...preview, [m.code]: r }))}>
                      현재 데이터로 미리 계산(기록 안 함)
                    </Button>
                    {preview[m.code] ? <JsonView value={preview[m.code]} maxHeight={260} /> : null}
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
                  <Check label="" checked={b.enabled} onChange={(v) => run(() => apiPatch(`/admin/bindings/${b.id}`, { enabled: v }), "저장했습니다", data.reload)} />
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
