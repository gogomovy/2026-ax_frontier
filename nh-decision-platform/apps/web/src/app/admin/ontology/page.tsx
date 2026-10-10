"use client";

import { useMemo, useState } from "react";
import { AdminPage, C, Card, JsonEditor, JsonView, Loading, StatusBadge, Table, Tabs, TextInput, fmtTime, useAction, useApiData } from "@/components/admin/kit";
import { Badge, Button } from "@/components/ui/primitives";
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
        <div className="mb-lg grid grid-cols-1 gap-md md:grid-cols-3">
          <Card title={`스키마 v${d.schema?.version ?? "-"}`} className="!mb-0">
            <p className="text-[12px] text-steel">
              클래스 {d.schema?.classes.length ?? 0} · 관계 {d.schema?.relations.length ?? 0}
            </p>
            <p className="mt-1 text-[11px] text-stone">{d.schema?.note}</p>
          </Card>
          <Card title="그래프" className="!mb-0">
            {d.graph.ok ? (
              <div className="flex flex-wrap gap-1">
                {(d.graph.labels ?? []).map((l) => (
                  <button key={l.label} type="button" onClick={() => setLabel(label === l.label ? "" : l.label)}>
                    <Badge tone={label === l.label ? "dark" : "neutral"}>
                      {l.label} {l.n}
                    </Badge>
                  </button>
                ))}
              </div>
            ) : (
              <StatusBadge status="error" label={d.graph.error ?? "그래프 장애"} />
            )}
          </Card>
          <Card title="검토 대기" className="!mb-0">
            <p className="text-[12px] text-steel">
              {Object.entries(d.openIssues)
                .map(([k, v]) => `${k} ${v}`)
                .join(" · ") || "없음"}
            </p>
          </Card>
        </div>
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
                  <JsonView value={i.raw} maxHeight={120} />
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
          {issues.data && !issues.data.length ? <p className="py-lg text-center text-[12.5px] text-stone">검토 대기 항목이 없습니다.</p> : null}
        </Card>
      ) : null}
    </AdminPage>
  );
}

function SchemaEditor({ schema, busy, onSave }: { schema: NonNullable<Onto["schema"]>; busy: boolean; onSave: (v: unknown) => void }) {
  const [note, setNote] = useState("");
  return (
    <div>
      <TextInput label="변경 메모" value={note} onChange={setNote} />
      <div className="mt-md">
        <JsonEditor value={{ classes: schema.classes, relations: schema.relations, aliases: schema.aliases }} rows={26} disabled={busy} label="새 버전으로 저장" onSave={(v) => onSave({ ...(v as object), note: note || null })} />
      </div>
    </div>
  );
}
