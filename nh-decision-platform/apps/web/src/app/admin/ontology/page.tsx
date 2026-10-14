"use client";

import { useMemo, useState } from "react";
import { AdminPage, C, Card, JsonEditor, JsonView, Loading, Table, Tabs, TextInput, fmtTime, useAction, useApiData } from "@/components/admin/kit";
import { BuildPipeline, ProposalsPanel } from "@/components/admin/ontology/BuildPanels";
import { OntologyMap } from "@/components/admin/ontology/OntologyMap";
import { SchemaMap } from "@/components/admin/ontology/SchemaMap";
import { colorOf, relKo, type MapClass, type OntologyMapData } from "@/components/admin/ontology/mapMath";
import { ValueView } from "@/components/admin/ValueView";
import { BarList } from "@/components/charts/Bars";
import { Advanced, EmptyState, Notice } from "@/components/ui/Layout";
import { Badge, Button, DataTable, PillTabs, Td } from "@/components/ui/primitives";
import { StatCard, StatGrid } from "@/components/ui/StatCard";
import { apiPatch, apiPost, apiPut } from "@/lib/api-client";

interface Onto {
  schema: { version: number; classes: Record<string, unknown>[]; relations: Record<string, unknown>[]; aliases: Record<string, unknown>; note: string | null } | null;
  versions: { version: number; active: boolean; note: string | null; createdAt: string }[];
  graph: { ok: boolean; labels?: { label: string; n: number }[]; relationships?: { type: string; n: number }[]; error?: string };
  openIssues: Record<string, number>;
  /** 승인 대기 변경 제안 수 (Phase M · ONB-09) */
  pendingProposals?: number;
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

type MapView = "3d" | "2d" | "schema" | "table";

/** 노드 종류 거르기 칩 — 색 점 · 업무 이름 · 영문 식별자 · 개수 */
function KindChip({ active, name, code, count, color, onClick }: { active: boolean; name: string; code?: string; count?: number; color?: string; onClick: () => void }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 rounded-pill border px-2.5 py-1 text-[12px] transition-colors ${active ? "border-ink-deep bg-ink-deep text-white" : "border-hairline-soft bg-white text-charcoal hover:bg-surface-soft"}`}
    >
      {color ? <span aria-hidden="true" className="inline-block h-2.5 w-2.5 shrink-0 rounded-circle" style={{ background: color }} /> : null}
      <b>{name}</b>
      {code && code !== name ? <span className={`font-mono text-[10px] ${active ? "text-white/75" : "text-stone"}`}>{code}</span> : null}
      {count !== undefined ? <span className={`tnum text-[11px] ${active ? "text-white/90" : "text-steel"}`}>{count.toLocaleString("ko-KR")}</span> : null}
    </button>
  );
}

/** 관계 표의 노드 칸 — 종류(색 · 업무 이름) 위, 개체 이름 아래 */
function NodeCell({ cls, name, info }: { cls: string; name?: string; info: Record<string, MapClass> }) {
  const c = info[cls];
  return (
    <span className="block min-w-0">
      <span className="inline-flex items-center gap-1 text-[11px] text-steel">
        <span aria-hidden="true" className="inline-block h-2 w-2 shrink-0 rounded-circle" style={{ background: c ? colorOf(c.color) : "#94a3b8" }} />
        {c?.ko ?? cls}
        {c ? <span className="font-mono text-[10px] text-stone">{cls}</span> : null}
      </span>
      <span className="block break-words text-[12.5px] font-bold text-ink-deep">{name ?? "-"}</span>
    </span>
  );
}

/** 온톨로지 — 구성 지도(원장 기준 · Phase G) · 그래프 관계(Neo4j) · 스키마 · 추출 검토 · 재투영 (ADM-09, ONT-13~16, OV-01~06) */
export default function OntologyAdmin() {
  const data = useApiData<Onto>("/admin/ontology");
  const issues = useApiData<Issue[]>("/admin/ontology/issues?status=open");
  const [tab, setTab] = useState<"map" | "build" | "proposals" | "graph" | "schema" | "issues">("map");
  const [view, setView] = useState<MapView>("3d");
  const [mapRefresh, setMapRefresh] = useState(0);
  const map = useApiData<OntologyMapData>(`/admin/ontology/map?limit=1500${mapRefresh ? `&refresh=true&n=${mapRefresh}` : ""}`);
  const [label, setLabel] = useState("");
  // Neo4j 관계 표는 그 탭을 열 때만 부른다(그래프가 없으면 503 — 지도는 원장 기준이라 영향 없음)
  const graph = useApiData<Graph>(tab === "graph" ? `/admin/ontology/graph?limit=300${label ? `&label=${encodeURIComponent(label)}` : ""}` : null);
  const { run, busy } = useAction();
  const d = data.data;
  const m = map.data;

  const openTotal = Object.values(d?.openIssues ?? {}).reduce((n, v) => n + v, 0);
  const nodeName = useMemo(() => Object.fromEntries((graph.data?.nodes ?? []).map((n) => [n.id, `${n.name}`])), [graph.data]);
  // 노드 종류의 업무 이름 · 색 — 구성 지도와 같은 값(원장 기준 클래스 목록)
  const classInfo = useMemo<Record<string, MapClass>>(() => Object.fromEntries((m?.classes ?? []).map((c) => [c.label, c])), [m?.classes]);

  return (
    <AdminPage
      title="온톨로지"
      description="온톨로지로 구축된 개체 · 관계가 어떻게 묶여 있는지 구성 지도로 봅니다(PostgreSQL 원장 기준 — Neo4j 투영과 같은 규칙). 그래프에는 사실(행 값)을 복제하지 않고 개념 · 계보 · 문서 근거만 두며, 문서는 구조화 결과를 스키마로 검증해 통과분만 반영합니다(실패분은 검토 대기)."
      actions={
        <>
          <Button size="sm" variant="quiet" disabled={map.loading} onClick={() => setMapRefresh((x) => x + 1)}>
            지도 새로 계산
          </Button>
          <Button size="sm" variant="confirm" disabled={busy} onClick={() => run(() => apiPost("/admin/ontology/reproject"), "재투영을 요청했습니다", data.reload)}>
            그래프 재투영
          </Button>
        </>
      }
    >
      <Loading error={data.error} loading={!d && data.loading} />
      <div className="mb-lg">
        <StatGrid columns={4} label="온톨로지 요약(원장 기준)">
          <StatCard label="스키마" value={`v${d?.schema?.version ?? m?.schemaVersion ?? "-"}`} hint={`클래스 ${d?.schema?.classes.length ?? 0} · 관계 유형 ${d?.schema?.relations.length ?? 0}`} />
          <StatCard label="개체" value={m ? m.total.nodes.toLocaleString("ko-KR") : "-"} unit="개" hint={m ? `클래스 ${m.classes.filter((c) => c.total > 0).length}가지 · 군집 ${m.clusters.length}개` : "불러오는 중"} />
          <StatCard label="관계" value={m ? m.total.links.toLocaleString("ko-KR") : "-"} unit="개" hint={m ? `유형 ${m.relations.length}가지` : undefined} />
          <StatCard label="추출 검토 대기" value={openTotal} unit="건" tone={openTotal ? "attention" : "success"} hint={openTotal ? "문서 구조화 결과 중 스키마 검증 실패분" : "검토할 것 없음"} />
        </StatGrid>
        {d && !d.graph.ok ? (
          <p className="mt-xs text-[12px] text-steel" data-neo4j-status="down" title={d.graph.error ?? undefined}>
            Neo4j 연결 안 됨 — 구성 지도 · 요약은 원장 기준으로 그대로 보이고, 근거 탐색의 그래프 채널 · 계보 미리보기만 축소 동작합니다. 원인은 [그래프 관계(Neo4j)] 탭에서 볼 수 있습니다.
          </p>
        ) : d ? (
          <p className="mt-xs text-[12px] text-steel" data-neo4j-status="up">
            Neo4j 반영: 노드 {(d.graph.labels ?? []).reduce((n, l) => n + l.n, 0).toLocaleString("ko-KR")} · 관계 {(d.graph.relationships ?? []).reduce((n, r) => n + r.n, 0).toLocaleString("ko-KR")}
          </p>
        ) : null}
      </div>
      <Tabs
        active={tab}
        onChange={setTab}
        tabs={[
          { key: "map", label: "구성 지도" },
          { key: "build", label: "구축 파이프라인" },
          { key: "proposals", label: "변경 제안", count: d?.pendingProposals },
          { key: "graph", label: "그래프 관계(Neo4j)" },
          { key: "schema", label: "스키마 편집" },
          { key: "issues", label: "추출 검토", count: issues.data?.length },
        ]}
      />
      {tab === "build" ? <BuildPipeline /> : null}
      {tab === "proposals" ? <ProposalsPanel onApplied={() => { void data.reload(); setMapRefresh((x) => x + 1); }} /> : null}
      {tab === "map" ? (
        <Card>
          <div className="mb-md flex flex-wrap items-center justify-between gap-xs">
            <PillTabs
              label="구성 지도 보기"
              value={view}
              onChange={setView}
              items={[
                { key: "3d", label: "3D 군집 지도" },
                { key: "2d", label: "2D 지도" },
                { key: "schema", label: "구조도" },
                { key: "table", label: "표" },
              ]}
            />
            {m ? (
              <span className="text-[11.5px] text-stone">
                {m.cached ? "보관본" : "새로 계산"} · {m.generatedAt ? fmtTime(m.generatedAt) : ""}
                {m.elapsedMs ? ` · ${m.elapsedMs.toLocaleString("ko-KR")}ms` : ""}
              </span>
            ) : null}
          </div>
          <Loading error={map.error} loading={!m && map.loading} />
          {m?.empty ? <EmptyState compact title="지도를 그릴 수 없습니다" description={m.empty} /> : null}
          {m && m.truncated ? (
            <div className="mb-md">
              <Notice tone="info" title="일부만 표시합니다">
                개체 {m.total.nodes.toLocaleString("ko-KR")}개 중 연결이 많은 {m.nodes.length.toLocaleString("ko-KR")}개(클래스마다 최소 몫)를 그렸습니다. 아래 범례로 클래스를 거르면 더 자세히 볼 수 있습니다.
              </Notice>
            </div>
          ) : null}
          {m && !m.empty && m.nodes.length ? (
            view === "3d" || view === "2d" ? (
              <OntologyMap key={`${m.generatedAt}-${view}`} data={m} mode={view} />
            ) : view === "schema" ? (
              <SchemaMap data={m} />
            ) : (
              <OntologyTables data={m} />
            )
          ) : null}
          {m && !m.empty && !m.nodes.length ? <EmptyState compact title="아직 개체가 없습니다" description="데이터셋 · 문서를 올리면 투영 규칙에 따라 개체 · 관계가 생깁니다." /> : null}
        </Card>
      ) : null}
      {tab === "graph" ? (
        <Card title={label ? `${label} 관련 관계` : "Neo4j 관계 (최대 300)"}>
          {d?.graph.ok ? (
            <div className="mb-md" role="group" aria-label="노드 종류로 거르기" data-graph-kinds>
              <p className="mb-xs flex flex-wrap items-baseline gap-x-2 text-[12.5px]">
                <b className="text-charcoal">노드 종류 {(d.graph.labels ?? []).length}</b>
                <span className="text-[11px] text-stone">
                  노드 {(d.graph.labels ?? []).reduce((s, l) => s + l.n, 0).toLocaleString("ko-KR")}개 · 하나를 누르면 그 종류가 들어간 관계만 봅니다 · 색은 구성 지도와 같습니다
                </span>
              </p>
              <ul className="flex flex-wrap gap-1.5">
                <li>
                  <KindChip active={!label} name="전체" onClick={() => setLabel("")} />
                </li>
                {[...(d.graph.labels ?? [])]
                  .sort((a, b) => b.n - a.n)
                  .map((l) => (
                    <li key={l.label}>
                      <KindChip active={label === l.label} name={classInfo[l.label]?.ko ?? l.label} code={l.label} count={l.n} color={classInfo[l.label] ? colorOf(classInfo[l.label].color) : undefined} onClick={() => setLabel(label === l.label ? "" : l.label)} />
                    </li>
                  ))}
              </ul>
            </div>
          ) : (
            <div className="mb-md">
              <Notice tone="attention" title="Neo4j 에 연결되지 않았습니다">
                {d?.graph.error ?? "그래프 장애"} — 구성 지도 탭은 원장 기준으로 볼 수 있습니다.
              </Notice>
            </div>
          )}
          {d?.graph.ok ? (
            <>
              <Loading error={graph.error} loading={!graph.data && graph.loading} />
              <Table head={["시작", "관계", "끝", "추출"]}>
                {(graph.data?.edges ?? []).map((e, i) => (
                  <tr key={i}>
                    <C>
                      <NodeCell cls={e.from.split(":")[0]} name={nodeName[e.from]} info={classInfo} />
                    </C>
                    <C>
                      <span className="block text-[12px] font-bold text-charcoal">→ {relKo(e.type)}</span>
                      <span className="block font-mono text-[10.5px] text-stone">{e.type}</span>
                    </C>
                    <C>
                      <NodeCell cls={e.to.split(":")[0]} name={nodeName[e.to]} info={classInfo} />
                    </C>
                    <C className="text-[11px] text-stone">{e.by ?? "-"}</C>
                  </tr>
                ))}
              </Table>
            </>
          ) : null}
        </Card>
      ) : null}
      {tab === "schema" && d?.schema ? (
        <Card title="스키마 (저장 시 새 버전 · 그래프 재투영)">
          <SchemaEditor schema={d.schema} busy={busy} onSave={(v) => run(() => apiPut("/admin/ontology/schema", v), "새 스키마 버전을 적용했습니다", data.reload)} />
          <div className="mt-lg border-t border-hairline-soft pt-md">
            <p className="mb-xs text-[12.5px] font-bold text-ink">판 이력 · 되돌리기</p>
            <p className="mb-md text-[11.5px] text-stone">되돌리기는 그 판의 내용으로 새 판을 만듭니다(이력은 남고 판 번호는 계속 늘어남). 지금 데이터와 맞지 않는 판은 거절됩니다.</p>
            <ul className="flex flex-col gap-1 text-[12px]">
              {d.versions.slice(0, 12).map((v) => (
                <li key={v.version} className="flex flex-wrap items-center gap-xs">
                  <b className="tnum">v{v.version}</b>
                  {v.active ? <Badge tone="success">활성</Badge> : null}
                  <span className="text-stone">{fmtTime(v.createdAt)}</span>
                  <span className="min-w-0 flex-1 text-charcoal">{v.note ?? ""}</span>
                  {!v.active ? (
                    <Button size="sm" variant="ghost" disabled={busy} onClick={() => run(() => apiPost(`/admin/ontology/schema/${v.version}/activate`), `v${v.version} 내용으로 새 판을 만들었습니다`, data.reload)}>
                      이 판으로 되돌리기
                    </Button>
                  ) : null}
                </li>
              ))}
            </ul>
          </div>
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

/** 표 보기 — 지도와 같은 정보를 글로 (OV-05): 군집 · 클래스 · 관계 유형(시작 → 끝) */
function OntologyTables({ data }: { data: OntologyMapData }) {
  const ko = Object.fromEntries(data.classes.map((c) => [c.label, c.ko || c.label]));
  return (
    <div className="flex flex-col gap-lg" data-ontology-tables>
      <div className="grid grid-cols-1 gap-lg lg:grid-cols-2">
        <BarList title="클래스별 개체 수" items={data.classes.filter((c) => c.total > 0).map((c) => ({ label: `${c.ko} (${c.label})`, value: c.total }))} />
        <BarList title="관계 유형별 개수" items={[...data.relations].sort((a, b) => b.count - a.count).map((r) => ({ label: `${relKo(r.type)} (${r.type})`, value: r.count, tone: "neutral" as const }))} />
      </div>
      <section aria-label="군집">
        <h3 className="mb-xs text-[13px] font-bold text-ink-deep">군집 {data.clusters.length}개</h3>
        <DataTable
          dense
          caption="군집 — 연결 구조로 묶인 개체 묶음(Louvain)"
          columns={[
            { key: "label", label: "군집" },
            { key: "size", label: "개체", align: "right" },
            { key: "classes", label: "구성(클래스 · 개수)" },
          ]}
        >
          {data.clusters.map((c) => (
            <tr key={c.id}>
              <Td strong>{c.label}</Td>
              <Td align="right">{c.size.toLocaleString("ko-KR")}</Td>
              <Td>
                <span className="flex flex-wrap gap-1">
                  {Object.entries(c.classes).map(([k, v]) => (
                    <span key={k} className="inline-flex items-center gap-1 text-[11.5px] text-charcoal">
                      <span aria-hidden="true" className="inline-block h-2 w-2 rounded-circle" style={{ background: colorOf(data.classes.find((x) => x.label === k)?.color ?? 0) }} />
                      {ko[k] ?? k} {v}
                    </span>
                  ))}
                </span>
              </Td>
            </tr>
          ))}
        </DataTable>
      </section>
      <section aria-label="관계 구조">
        <h3 className="mb-xs text-[13px] font-bold text-ink-deep">관계 구조 {data.schema.length}가지</h3>
        <DataTable
          dense
          caption="클래스 사이 관계 유형과 개수"
          columns={[
            { key: "from", label: "시작 클래스" },
            { key: "type", label: "관계" },
            { key: "to", label: "끝 클래스" },
            { key: "count", label: "개수", align: "right" },
          ]}
        >
          {data.schema.map((s) => (
            <tr key={`${s.from}-${s.type}-${s.to}`}>
              <Td>
                {ko[s.from] ?? s.from} <span className="font-mono text-[10.5px] text-stone">{s.from}</span>
              </Td>
              <Td>
                {relKo(s.type)} <span className="font-mono text-[10.5px] text-stone">{s.type}</span>
              </Td>
              <Td>
                {ko[s.to] ?? s.to} <span className="font-mono text-[10.5px] text-stone">{s.to}</span>
              </Td>
              <Td align="right">{s.count.toLocaleString("ko-KR")}</Td>
            </tr>
          ))}
        </DataTable>
      </section>
      <section aria-label="클래스 설명">
        <h3 className="mb-xs text-[13px] font-bold text-ink-deep">클래스</h3>
        <DataTable
          dense
          caption="클래스 — 지도에 그린 수 / 원장 전체"
          columns={[
            { key: "cls", label: "클래스" },
            { key: "count", label: "그린 수 / 전체", align: "right" },
            { key: "desc", label: "설명" },
          ]}
        >
          {data.classes.map((c) => (
            <tr key={c.label}>
              <Td strong>
                <span className="inline-flex items-center gap-1.5">
                  <span aria-hidden="true" className="inline-block h-2.5 w-2.5 rounded-circle" style={{ background: colorOf(c.color) }} />
                  {c.ko} <span className="font-mono text-[10.5px] font-medium text-stone">{c.label}</span>
                </span>
              </Td>
              <Td align="right">
                {c.count.toLocaleString("ko-KR")} / {c.total.toLocaleString("ko-KR")}
              </Td>
              <Td>
                <span className="text-[11.5px] text-steel">{c.description || "-"}</span>
              </Td>
            </tr>
          ))}
        </DataTable>
      </section>
    </div>
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
