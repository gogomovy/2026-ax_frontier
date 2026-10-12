"use client";

import { useMemo, useState } from "react";
import { AdminPage, C, Card, JsonEditor, JsonView, Loading, Table, Tabs, TextInput, fmtTime, useAction, useApiData } from "@/components/admin/kit";
import { ValueView } from "@/components/admin/ValueView";
import { BarList } from "@/components/charts/Bars";
import { Advanced, EmptyState, Notice } from "@/components/ui/Layout";
import { Badge, Button } from "@/components/ui/primitives";
import { StatCard, StatGrid } from "@/components/ui/StatCard";
import { apiPatch, apiPost, apiPut } from "@/lib/api-client";

interface Onto {
  schema: { version: number; classes: Record<string, unknown>[]; relations: Record<string, unknown>[]; aliases: Record<string, unknown>; note: string | null } | null;
  versions: { version: number; active: boolean; note: string | null; createdAt: string }[];
  graph: { ok: boolean; labels?: { label: string; n: number }[]; relationships?: { type: string; n: number }[]; error?: string };
  openIssues: Record<string, number>;
}
interface Issue {
  id: number;
  origin: string;
  documentId: number | null;
  kind: string;
  reason: string;
  raw: unknown;
  status: string;
  createdAt: string;
}
interface Graph {
  nodes: { id: string; label: string; name: string }[];
  edges: { from: string; to: string; type: string; by: string | null }[];
}

/** 온톨로지 스키마 · 그래프 통계 · 추출 검토 대기 · 재투영 (ADM-09, ONT-13~16) */
export default function OntologyAdmin() {
  const data = useApiData<Onto>("/admin/ontology");
  const issues = useApiData<Issue[]>("/admin/ontology/issues?status=open");
  const [tab, setTab] = useState<"graph" | "schema" | "issues">("graph");
  const [label, setLabel] = useState("");
  const graph = useApiData<Graph>(`/admin/ontology/graph?limit=300${label ? `&label=${encodeURIComponent(label)}` : ""}`);
  const { run, busy } = useAction();
  const d = data.data;

  const openTotal = Object.values(d?.openIssues ?? {}).reduce((n, v) => n + v, 0);
  const nodeName = useMemo(() => Object.fromEntries((graph.data?.nodes ?? []).map((n) => [n.id, `${n.name}`])), [graph.data]);

  return (
    <AdminPage
      title="온톨로지"
      description="그래프에는 사실(행 값)을 복제하지 않고 개념 · 계보 · 문서 근거만 둡니다. 정형 데이터는 데이터셋 매핑으로 결정론 투영하고, 문서는 LLM 구조화 결과를 스키마로 검증해 통과분만 반영합니다(실패분은 검토 대기)."
      actions={
        <Button size="sm" variant="confirm" disabled={busy} onClick={() => run(() => apiPost("/admin/ontology/reproject"), "재투영을 요청했습니다", data.reload)}>
          그래프 재투영
        </Button>
      }
    >
      <Loading error={data.error} loading={!d && data.loading} />
      {d ? (
        <>
          <div className="mb-lg">
            <StatGrid columns={4} label="온톨로지 요약">
              <StatCard label="스키마" value={`v${d.schema?.version ?? "-"}`} hint={`클래스 ${d.schema?.classes.length ?? 0} · 관계 ${d.schema?.relations.length ?? 0}`} />
              <StatCard
                label="그래프 노드"
                value={d.graph.ok ? (d.graph.labels ?? []).reduce((n, l) => n + l.n, 0).toLocaleString("ko-KR") : "연결 안 됨"}
                tone={d.graph.ok ? "default" : "attention"}
                hint={d.graph.ok ? `종류 ${(d.graph.labels ?? []).length}가지` : "그래프 없이 축소 동작 — 화면 수치에는 영향 없음"}
              />
              <StatCard label="그래프 관계" value={d.graph.ok ? (d.graph.relationships ?? []).reduce((n, r) => n + r.n, 0).toLocaleString("ko-KR") : "-"} hint={d.graph.ok ? `종류 ${(d.graph.relationships ?? []).length}가지` : undefined} />
              <StatCard label="추출 검토 대기" value={openTotal} unit="건" tone={openTotal ? "attention" : "success"} hint={openTotal ? "문서 구조화 결과 중 스키마 검증 실패분" : "검토할 것 없음"} />
            </StatGrid>
          </div>
          {d.graph.ok ? (
            <div className="mb-lg grid grid-cols-1 gap-lg lg:grid-cols-2">
              <Card className="!mb-0">
                <BarList title="노드 종류별 개수" items={(d.graph.labels ?? []).slice(0, 10).map((l) => ({ label: l.label, value: l.n }))} />
              </Card>
              <Card className="!mb-0">
                <BarList title="관계 종류별 개수" items={(d.graph.relationships ?? []).slice(0, 10).map((r) => ({ label: r.type, value: r.n, tone: "neutral" as const }))} />
              </Card>
            </div>
          ) : (
            <div className="mb-lg">
              <Notice tone="attention" title="그래프에 연결되지 않았습니다">
                {d.graph.error ?? "그래프 장애"} — 근거 탐색 · 계보 미리보기가 축소되어 동작합니다.
              </Notice>
            </div>
          )}
        </>
      ) : null}
      <Tabs
        active={tab}
        onChange={setTab}
        tabs={[
          { key: "graph", label: "그래프 탐색" },
          { key: "schema", label: "스키마 편집" },
          { key: "issues", label: "추출 검토", count: issues.data?.length },
        ]}
      />
      {tab === "graph" ? (
        <Card title={label ? `${label} 관련 관계` : "관계 (최대 300)"}>
          {d?.graph.ok ? (
            <div className="mb-md flex flex-wrap items-center gap-1" role="group" aria-label="노드 종류로 거르기">
              <span className="mr-1 text-[11.5px] font-bold text-steel">노드 종류</span>
              {(d.graph.labels ?? []).map((l) => (
                <button key={l.label} type="button" aria-pressed={label === l.label} onClick={() => setLabel(label === l.label ? "" : l.label)}>
                  <Badge tone={label === l.label ? "dark" : "neutral"}>
                    {l.label} {l.n}
                  </Badge>
                </button>
              ))}
            </div>
          ) : null}
          <Loading error={graph.error} loading={!graph.data && graph.loading} />
          <Table head={["시작", "관계", "끝", "추출"]}>
            {(graph.data?.edges ?? []).map((e, i) => (
              <tr key={i}>
                <C>
                  <Badge>{e.from.split(":")[0]}</Badge> {nodeName[e.from]}
                </C>
                <C mono>{e.type}</C>
                <C>
                  <Badge>{e.to.split(":")[0]}</Badge> {nodeName[e.to]}
                </C>
                <C className="text-[11px] text-stone">{e.by ?? "-"}</C>
              </tr>
            ))}
          </Table>
        </Card>
      ) : null}
      {tab === "schema" && d?.schema ? (
        <Card title="스키마 (저장 시 새 버전 · 그래프 재투영)">
          <SchemaEditor schema={d.schema} busy={busy} onSave={(v) => run(() => apiPut("/admin/ontology/schema", v), "새 스키마 버전을 적용했습니다", data.reload)} />
          <p className="mt-md text-[11.5px] text-stone">
            버전 이력: {d.versions.map((v) => `v${v.version}${v.active ? "(활성)" : ""} ${fmtTime(v.createdAt)}`).join(" · ")}
          </p>
        </Card>
      ) : null}
      {tab === "issues" ? (
        <Card>
          <Table head={["종류", "사유", "원문", "문서", "처리"]}>
            {(issues.data ?? []).map((i) => (
              <tr key={i.id}>
                <C>
                  <Badge tone="attention">{i.kind}</Badge>
                </C>
                <C className="max-w-[280px]">{i.reason}</C>
                <C className="max-w-[360px]">
                  <ValueView value={i.raw} depth={1} />
                  <div className="mt-xs">
                    <Advanced label="원문(JSON)">
                      <JsonView value={i.raw} maxHeight={120} />
                    </Advanced>
                  </div>
                </C>
                <C className="text-[11px]">
                  {i.origin}#{i.documentId}
                  <br />
                  {fmtTime(i.createdAt)}
                </C>
                <C>
                  <div className="flex gap-1">
                    <Button size="sm" variant="confirm" disabled={busy} onClick={() => run(() => apiPatch(`/admin/ontology/issues/${i.id}`, { status: "accepted" }), "확인 처리했습니다", issues.reload)}>
                      확인
                    </Button>
                    <Button size="sm" variant="ghost" disabled={busy} onClick={() => run(() => apiPatch(`/admin/ontology/issues/${i.id}`, { status: "rejected" }), "제외했습니다", issues.reload)}>
                      제외
                    </Button>
                  </div>
                </C>
              </tr>
            ))}
          </Table>
          {issues.data && !issues.data.length ? <EmptyState compact title="검토 대기 항목이 없습니다" description="문서 구조화 결과가 모두 스키마 검증을 통과했습니다." /> : null}
        </Card>
      ) : null}
    </AdminPage>
  );
}

function SchemaEditor({ schema, busy, onSave }: { schema: NonNullable<Onto["schema"]>; busy: boolean; onSave: (v: unknown) => void }) {
  const [note, setNote] = useState("");
  return (
    <div className="flex flex-col gap-md">
      <div>
        <p className="mb-xs text-[12.5px] font-bold text-ink-deep">클래스 {schema.classes.length}</p>
        <ValueView value={schema.classes} />
      </div>
      <div>
        <p className="mb-xs text-[12.5px] font-bold text-ink-deep">관계 {schema.relations.length}</p>
        <ValueView value={schema.relations} />
      </div>
      <Advanced label="고급 — 스키마 JSON 편집(새 버전으로 저장)">
        <TextInput label="변경 메모" value={note} onChange={setNote} />
        <div className="mt-md">
          <JsonEditor value={{ classes: schema.classes, relations: schema.relations, aliases: schema.aliases }} rows={26} disabled={busy} label="새 버전으로 저장" onSave={(v) => onSave({ ...(v as object), note: note || null })} />
        </div>
      </Advanced>
    </div>
  );
}
