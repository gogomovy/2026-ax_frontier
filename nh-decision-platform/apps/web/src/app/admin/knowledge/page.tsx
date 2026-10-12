"use client";

import { useState, type FormEvent } from "react";
import { AdminPage, C, Card, Check, Collapse, JsonEditor, JsonView, Loading, Select, Table, Tabs, TextInput, fmtTime, useAction, useApiData } from "@/components/admin/kit";
import { StatCard, StatGrid } from "@/components/ui/StatCard";
import { Badge, Button } from "@/components/ui/primitives";
import { apiPost, apiPut } from "@/lib/api-client";

interface OrgRef {
  code: string;
  name: string;
}
interface CollectionStats {
  chunks: number;
  embedded: number;
  sources: number;
  documents?: number;
  lastIndexedAt: string | null;
}
interface Collection {
  code: string;
  label: string;
  description: string | null;
  kind: string;
  audience: "all" | "restricted" | "owner_only";
  enabled: boolean;
  boost: number;
  sort: number;
  ownerOrgs: OrgRef[];
  sharedOrgs: OrgRef[];
  requiredResources: string[];
  sources: Record<string, string[]>;
  updatedBy: string | null;
  updatedAt: string | null;
  stats?: CollectionStats;
}
interface Status {
  totals: { chunks: number; embedded: number; pendingEmbedding: number };
  stale: { count: number; toIndex: string[]; toDelete: string[] };
  state: Record<string, unknown>;
  documentsByClass: Record<string, number>;
  embedding: { agent: string; model: string | null; on: boolean; reason?: string };
  graph: { ok: boolean; nodes?: number; relationships?: number; error?: string };
  unassigned: number;
  orphanChunks: number;
  collections: Collection[];
}
interface ChannelState {
  on: boolean;
  candidates: number;
  reason?: string;
  docGraph?: boolean;
}
interface DiagHit {
  kind: string;
  type?: string;
  collection: string | null;
  collectionLabel: string | null;
  owned: boolean;
  title: string;
  artifactTitle?: string | null;
  text: string;
  score: number;
  signals?: Record<string, number>;
  parts?: Record<string, number> | null;
}
interface Diagnosis {
  asEmpNo: string;
  scope: { code: string; label: string; owned: boolean; partial: boolean }[];
  query: string;
  concepts: string[];
  expanded: { key: string; via?: string; source?: string }[] | string[];
  analysis: DiagHit[];
  documents: DiagHit[];
  rejected: Record<string, unknown>[];
  diagnostics: {
    channels: Record<string, ChannelState>;
    timingsMs?: Record<string, number>;
    errors?: Record<string, string>;
    semantic?: boolean;
    graph?: boolean;
    intent?: string | null;
  };
}

type TabKey = "status" | "collections" | "diagnose";
const KIND_LABEL: Record<string, string> = { document: "문서", analysis: "분석 결과", glossary: "용어", catalog: "데이터 목록" };
const AUDIENCE_OPTIONS = [
  { value: "all", label: "전체 공개 (all)" },
  { value: "restricted", label: "담당·공유 팀 + 화면 권한 (restricted)" },
  { value: "owner_only", label: "담당 팀·관리자만 (owner_only)" },
];
const CHANNEL_LABEL: Record<string, string> = { keyword: "키워드", vector: "의미(임베딩)", graph: "그래프(개념)" };

/** 채널별 소요 — 서버는 단계(kb_keyword · doc_vector …) 이름으로 재므로 채널로 합산한다 */
const CHANNEL_STEPS: Record<string, string[]> = {
  keyword: ["kb_keyword", "doc_keyword"],
  vector: ["embed", "kb_vector", "doc_vector"],
  graph: ["expand", "kb_graph", "doc_graph_lookup", "doc_graph"],
};
const channelMs = (t: Record<string, number> | undefined, ch: string) => (t ? (CHANNEL_STEPS[ch] ?? []).reduce((a, k) => a + (t[k] ?? 0), 0) : null);

const splitCodes = (s: string) => Array.from(new Set(s.split(/[\s,]+/).map((x) => x.trim()).filter(Boolean)));
const orgText = (orgs: OrgRef[]) => orgs.map((o) => o.code).join(", ");
const orgNames = (orgs: OrgRef[]) => (orgs.length ? orgs.map((o) => `${o.name}(${o.code})`).join(" · ") : "없음");

/** 질문하기 지식 색인 (요구사항 NFR-KB-03/04 · 설계 §21.8) — 색인 상태 · 컬렉션(담당 팀 · 공개 범위) 편집 · 사용자 관점 검색 진단 */
export default function KnowledgeAdmin() {
  const status = useApiData<Status>("/admin/knowledge/status", { refreshMs: 30000 });
  const { run, busy } = useAction();
  const [tab, setTab] = useState<TabKey>("status");
  const st = status.data;

  return (
    <AdminPage
      title="질문하기 색인"
      description="질문하기가 찾는 자료(분석 결과 · 문서 · 용어)를 팀별 컬렉션으로 나누어 관리합니다. 담당 팀과 공개 범위를 바꾸면 다음 질문부터 적용되고, 포함 규칙을 바꾸면 워커가 1분 안에 다시 색인합니다."
      actions={
        <>
          <Button size="sm" variant="quiet" onClick={status.reload}>
            새로고침
          </Button>
          <Button
            size="sm"
            variant="confirm"
            disabled={busy}
            onClick={() => run(() => apiPost<{ note: string }>("/admin/knowledge/reindex"), (r) => r.note, status.reload)}
          >
            전체 재색인
          </Button>
        </>
      }
    >
      <Loading error={status.error} loading={!st && status.loading} />
      <Tabs
        tabs={[
          { key: "status", label: "색인 상태" },
          { key: "collections", label: "컬렉션", count: st?.collections.length },
          { key: "diagnose", label: "검색 진단" },
        ]}
        active={tab}
        onChange={setTab}
      />
      {tab === "status" && st ? <StatusTab st={st} /> : null}
      {tab === "collections" && st ? <CollectionsTab items={st.collections} reload={status.reload} /> : null}
      {tab === "diagnose" ? <DiagnoseTab /> : null}
    </AdminPage>
  );
}

function StatusTab({ st }: { st: Status }) {
  const pct = st.totals.chunks ? Math.round((st.totals.embedded / st.totals.chunks) * 100) : 0;
  return (
    <>
      <div className="mb-lg">
        <StatGrid columns={4} label="색인 상태 요약">
          <StatCard dataKey="kb-chunks" label="색인된 조각(청크)" value={st.totals.chunks.toLocaleString("ko-KR")} unit="개" hint={`컬렉션 ${st.collections.length}개`} />
          <StatCard
            dataKey="kb-embedded"
            label="의미 검색 준비"
            value={`${pct}%`}
            tone={st.embedding.on ? (st.totals.pendingEmbedding ? "attention" : "success") : "attention"}
            hint={st.embedding.on ? `임베딩 ${st.totals.embedded}/${st.totals.chunks} · 대기 ${st.totals.pendingEmbedding} · 모델 ${st.embedding.model}` : `임베딩 모델 없음 — 키워드·그래프로만 찾습니다${st.embedding.reason ? ` (${st.embedding.reason})` : ""}`}
          />
          <StatCard
            dataKey="kb-stale"
            label="뒤처진 산출물"
            value={st.stale.count}
            unit="건"
            tone={st.stale.count ? "attention" : "success"}
            hint={st.stale.count ? "워커가 1분 안에 따라잡습니다. 계속되면 워커 로그 확인" : "게시된 산출물과 색인이 같습니다"}
          />
          <StatCard
            dataKey="kb-unassigned"
            label="미분류 조각"
            value={st.unassigned}
            unit="개"
            tone={st.unassigned ? "attention" : "success"}
            hint={st.unassigned ? "어느 컬렉션 규칙에도 맞지 않음 — 관리자만 볼 수 있습니다. 컬렉션 포함 규칙을 정하세요" : "모두 컬렉션에 배정됨"}
          />
        </StatGrid>
      </div>
      <Card title="컬렉션별 현황" actions={<span className="text-[11.5px] text-stone">그래프: {st.graph.ok ? `연결됨 · 노드 ${st.graph.nodes} · 관계 ${st.graph.relationships}` : "연결 안 됨 — 개념 확장은 PostgreSQL 간선으로 계속 동작"}</span>}>
        <Table head={["컬렉션", "종류", "담당 팀", "공개 범위", "조각", "임베딩", "출처", "마지막 색인", "상태"]}>
          {st.collections.map((c) => (
            <tr key={c.code} data-kb-collection={c.code}>
              <C>
                <b className="text-ink-deep">{c.label}</b>
                <div className="font-mono text-[10.5px] text-stone">{c.code}</div>
              </C>
              <C>{KIND_LABEL[c.kind] ?? c.kind}</C>
              <C>{orgNames(c.ownerOrgs)}</C>
              <C>{c.audience}</C>
              <C right>{c.kind === "document" ? `문서 ${c.stats?.documents ?? 0}` : (c.stats?.chunks ?? 0)}</C>
              <C right>{c.kind === "document" ? "-" : `${c.stats?.embedded ?? 0}/${c.stats?.chunks ?? 0}`}</C>
              <C right>{c.kind === "document" ? "-" : (c.stats?.sources ?? 0)}</C>
              <C>{c.kind === "document" ? "-" : fmtTime(c.stats?.lastIndexedAt)}</C>
              <C>{c.enabled ? <Badge tone="success">사용</Badge> : <Badge>중지</Badge>}</C>
            </tr>
          ))}
        </Table>
        <p className="mt-md text-[11.5px] text-stone">
          문서 컬렉션은 문서 DB 의 현재 문서를 분류로 묶어 보여 줍니다(조각은 문서 청크 테이블에 따로 있음). 분류별 현재 문서: {Object.entries(st.documentsByClass).map(([k, v]) => `${k} ${v}`).join(" · ") || "없음"}
          {st.orphanChunks ? ` · 컬렉션이 없는 조각 ${st.orphanChunks}개(재색인 필요)` : ""}
        </p>
      </Card>
    </>
  );
}

function CollectionsTab({ items, reload }: { items: Collection[]; reload: () => unknown }) {
  const [open, setOpen] = useState<string | null>(null);
  return (
    <Card title="컬렉션 — 담당 팀 · 공개 범위 · 포함 규칙">
      <p className="mb-md text-[12.5px] text-steel">
        한 줄을 눌러 편집합니다. <b>담당 팀</b>은 그 컬렉션을 전체 열람하고 검색에서 앞서 보입니다. <b>공유 팀</b>은 열람만 합니다. 조직 코드는 하위 조직을 포함합니다(예: D200 = 신용리스크관리부 전체).
      </p>
      <ul className="flex flex-col gap-xs">
        {items.map((c) => (
          <li key={c.code} className="rounded-xl border border-hairline-soft" data-kb-edit={c.code}>
            <button
              type="button"
              className="flex w-full flex-wrap items-center gap-x-md gap-y-1 px-md py-2.5 text-left"
              aria-expanded={open === c.code}
              onClick={() => setOpen(open === c.code ? null : c.code)}
            >
              <span aria-hidden="true">{open === c.code ? "▾" : "▸"}</span>
              <b className="text-[13px] text-ink-deep">{c.label}</b>
              <span className="font-mono text-[11px] text-stone">{c.code}</span>
              <Badge>{KIND_LABEL[c.kind] ?? c.kind}</Badge>
              <Badge tone={c.audience === "all" ? "success" : c.audience === "owner_only" ? "warning" : "info"}>{c.audience}</Badge>
              {!c.enabled ? <Badge tone="critical">중지</Badge> : null}
              <span className="text-[12px] text-steel">담당: {orgNames(c.ownerOrgs)}</span>
            </button>
            {open === c.code ? <CollectionEditor key={`${c.code}-${c.updatedAt}`} c={c} reload={reload} /> : null}
          </li>
        ))}
      </ul>
    </Card>
  );
}

function CollectionEditor({ c, reload }: { c: Collection; reload: () => unknown }) {
  const { run, busy } = useAction();
  const [label, setLabel] = useState(c.label);
  const [description, setDescription] = useState(c.description ?? "");
  const [owners, setOwners] = useState(orgText(c.ownerOrgs));
  const [shared, setShared] = useState(orgText(c.sharedOrgs));
  const [resources, setResources] = useState(c.requiredResources.join(", "));
  const [audience, setAudience] = useState<string>(c.audience);
  const [boost, setBoost] = useState(String(c.boost));
  const [enabled, setEnabled] = useState(c.enabled);
  const boostNum = Number(boost);
  const boostOk = boost.trim() !== "" && Number.isFinite(boostNum) && boostNum >= -1 && boostNum <= 1;
  const url = `/admin/knowledge/collections/${encodeURIComponent(c.code)}`;

  const save = (e: FormEvent) => {
    e.preventDefault();
    if (!boostOk || !label.trim()) return;
    run(
      () => apiPut<{ note: string }>(url, { label: label.trim(), description: description.trim() || null, owner_orgs: splitCodes(owners), shared_orgs: splitCodes(shared), required_resources: splitCodes(resources), audience, boost: boostNum, enabled }),
      (r) => r.note,
      reload,
    );
  };

  return (
    <div className="border-t border-hairline-soft px-md pb-md pt-md">
      <form onSubmit={save} className="grid grid-cols-1 gap-md md:grid-cols-2">
        <TextInput label="이름" value={label} onChange={setLabel} />
        <Select label="공개 범위" value={audience} onChange={setAudience} options={AUDIENCE_OPTIONS} />
        <div>
          <TextInput label="담당 팀 (조직 코드, 쉼표로 구분)" value={owners} onChange={setOwners} mono />
          <p className="mt-1 text-[11px] text-stone">{orgNames(c.ownerOrgs)}</p>
        </div>
        <div>
          <TextInput label="공유 팀 (조직 코드, 쉼표로 구분)" value={shared} onChange={setShared} mono />
          <p className="mt-1 text-[11px] text-stone">{orgNames(c.sharedOrgs)}</p>
        </div>
        <TextInput label="열람 화면 권한 (리소스 코드, 쉼표로 구분 — 이 권한이 있으면 전체 열람)" value={resources} onChange={setResources} mono className="md:col-span-2" />
        <TextInput label="설명" value={description} onChange={setDescription} className="md:col-span-2" />
        <div>
          <TextInput label="검색 가산점 (−1 ~ 1)" value={boost} onChange={setBoost} type="number" />
          {!boostOk ? <p className="mt-1 text-[11px] text-critical">−1 에서 1 사이의 숫자를 입력하세요</p> : null}
        </div>
        <div className="flex items-end gap-md">
          <Check label="사용" checked={enabled} onChange={setEnabled} />
          <Button type="submit" size="sm" variant="confirm" disabled={busy || !boostOk || !label.trim()}>
            저장
          </Button>
          <span className="text-[11px] text-stone">{c.updatedBy ? `마지막 수정 ${c.updatedBy} · ${fmtTime(c.updatedAt)}` : "기본값(시드)"}</span>
        </div>
      </form>
      <div className="mt-md">
        <Collapse label="포함 규칙 (어떤 자료가 이 컬렉션에 들어오는지) — 고급">
          <p className="mb-xs text-[11.5px] text-steel">
            키: doc_classes(문서 분류) · artifact_keys(산출물 키) · artifact_prefixes(키 접두어) · spaces(분석 공간) · personas(P1 종합기획부 · P2 신용리스크 · P3 영업점) · screens(화면 경로 접두어, 가산점용). 저장하면 워커 대조(1분) 뒤 다시 색인됩니다.
          </p>
          <JsonEditor value={c.sources} rows={8} label="규칙 저장" disabled={busy} onSave={(v) => run(() => apiPut<{ note: string }>(url, { sources: v }), (r) => r.note, reload)} />
        </Collapse>
      </div>
    </div>
  );
}

function DiagnoseTab() {
  const { run, busy } = useAction();
  const [query, setQuery] = useState("");
  const [emp, setEmp] = useState("");
  const [screen, setScreen] = useState("");
  const [res, setRes] = useState<Diagnosis | null>(null);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (query.trim().length < 2) return;
    run(
      () => apiPost<Diagnosis>("/admin/knowledge/search", { query: query.trim(), asEmpNo: emp.trim() || undefined, screen: screen.trim() || undefined }),
      undefined,
      undefined,
    ).then((r) => r && setRes(r));
  };

  return (
    <>
      <Card title="사용자 관점으로 검색해 보기">
        <p className="mb-md text-[12.5px] text-steel">
          그 사용자가 질문하기에서 같은 질문을 했을 때 어떤 컬렉션에서 무엇이 어떤 근거로 나오는지 봅니다. 읽기 전용이며 감사 로그에 남습니다. 사번을 비우면 관리자(전체 범위) 관점입니다.
        </p>
        <form onSubmit={submit} className="grid grid-cols-1 gap-md md:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,1fr)_auto] md:items-end">
          <TextInput label="질문" value={query} onChange={setQuery} placeholder="예: 포용금융 충당금 비중은?" />
          <TextInput label="사용자 사번 (선택)" value={emp} onChange={setEmp} mono placeholder="예: 20250002" />
          <TextInput label="현재 화면 경로 (선택)" value={screen} onChange={setScreen} mono placeholder="/risk" />
          <Button type="submit" size="sm" variant="confirm" disabled={busy || query.trim().length < 2}>
            {busy ? "검색 중…" : "검색"}
          </Button>
        </form>
      </Card>
      {res ? <DiagnosisResult r={res} /> : null}
    </>
  );
}

function HitTable({ hits, empty }: { hits: DiagHit[]; empty: string }) {
  if (!hits.length) return <p className="text-[12.5px] text-steel">{empty}</p>;
  return (
    <Table head={["#", "컬렉션", "제목", "점수", "채널 순위 · 신호", "본문"]}>
      {hits.map((h, i) => (
        <tr key={`${h.title}-${i}`}>
          <C right>{i + 1}</C>
          <C>
            {h.collectionLabel ?? "-"} {h.owned ? <Badge tone="primary">담당</Badge> : null}
          </C>
          <C className="min-w-[180px] font-bold text-ink-deep">{h.artifactTitle && h.artifactTitle !== h.title ? `${h.artifactTitle} › ${h.title}` : h.title}</C>
          <C right>{h.score}</C>
          <C mono className="min-w-[160px]">
            {Object.entries(h.signals ?? {}).map(([k, v]) => `${k}=${v}`).join(" ") || "-"}
            {h.parts ? <Collapse label="점수 구성"><JsonView value={h.parts} maxHeight={140} /></Collapse> : null}
          </C>
          <C className="min-w-[260px] text-steel">{h.text.length > 160 ? `${h.text.slice(0, 160)}…` : h.text}</C>
        </tr>
      ))}
    </Table>
  );
}

function DiagnosisResult({ r }: { r: Diagnosis }) {
  const ch = r.diagnostics.channels;
  const expanded = (r.expanded as (string | { key: string })[]).map((e) => (typeof e === "string" ? e : e.key));
  return (
    <>
      <Card title={`범위 — ${r.asEmpNo} 가 질문할 수 있는 컬렉션`}>
        <ul className="flex flex-wrap gap-1.5" aria-label="질문 가능 범위">
          {r.scope.map((c) => (
            <li key={c.code}>
              <Badge tone={c.owned ? "primary" : "neutral"}>
                {c.label}
                {c.owned ? " · 담당" : c.partial ? " · 일부" : ""}
              </Badge>
            </li>
          ))}
        </ul>
        <p className="mt-md text-[12px] text-steel">
          검색어: <b>{r.query}</b> · 질문 개념: {r.concepts.length ? r.concepts.join(", ") : "없음"} · 확장 개념: {expanded.length ? expanded.slice(0, 12).join(", ") : "없음"} · 의도: {r.diagnostics.intent ?? "-"}
        </p>
      </Card>
      <Card title="채널별 후보">
        <Table head={["채널", "사용", "후보 수", "사유 · 비고", "소요(ms)"]}>
          {Object.entries(ch).map(([k, v]) => (
            <tr key={k}>
              <C className="font-bold text-ink-deep">{CHANNEL_LABEL[k] ?? k}</C>
              <C>{v.on ? <Badge tone="success">사용</Badge> : <Badge tone="attention">꺼짐</Badge>}</C>
              <C right>{v.candidates}</C>
              <C className="text-steel">{v.reason ?? (v.docGraph === false ? "문서 그래프 미연결 — 분석 결과 개념 태그로 대신 찾음" : "-")}</C>
              <C right>{channelMs(r.diagnostics.timingsMs, k) ?? "-"}</C>
            </tr>
          ))}
        </Table>
        {r.diagnostics.timingsMs ? <p className="mt-md text-[11.5px] text-stone">단계별 소요(ms): {Object.entries(r.diagnostics.timingsMs).map(([k, v]) => `${k} ${v}`).join(" · ")}</p> : null}
        {r.diagnostics.errors && Object.keys(r.diagnostics.errors).length ? (
          <p role="alert" className="mt-xs text-[12px] text-critical">
            실패한 단계: {Object.entries(r.diagnostics.errors).map(([k, v]) => `${k} (${v})`).join(" · ")}
          </p>
        ) : null}
      </Card>
      <Card title={`분석 결과 후보 ${r.analysis.length}건`}>
        <HitTable hits={r.analysis} empty="이 사용자 범위에서 질문과 연결된 분석 결과가 없습니다." />
      </Card>
      <Card title={`문서 근거 ${r.documents.length}건`}>
        <HitTable hits={r.documents} empty="이 사용자 범위에서 질문과 연결된 문서가 없습니다." />
      </Card>
      <Card title={`걸러진 후보 ${r.rejected.length}건`}>
        {r.rejected.length ? (
          <Collapse label="사유 보기">
            <JsonView value={r.rejected} maxHeight={260} />
          </Collapse>
        ) : (
          <p className="text-[12.5px] text-steel">걸러진 후보가 없습니다.</p>
        )}
      </Card>
    </>
  );
}
