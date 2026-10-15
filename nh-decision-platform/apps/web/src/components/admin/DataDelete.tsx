"use client";

import { C, Card, Loading, StatusBadge, Table, fmtTime, useAction, useApiData } from "@/components/admin/kit";
import { useConfirm } from "@/components/providers/UiProvider";
import { useSession } from "@/components/providers/SessionProvider";
import { Badge, Button } from "@/components/ui/primitives";
import { apiGetC, apiPost } from "@/lib/api-client";
import { scrubText, type Scrubbed } from "@/lib/scrubText";

/**
 * 업로드 자료 삭제 (Phase J · DEL-01~08 · Q143~Q147) — 데이터 관리자만.
 * 삭제 전 미리보기(현재 버전 여부 · 승격 대상 · 다시 도는 워크플로우)를 보여 주고 사유를 받아 한 번 더 묻는다.
 */
export interface DeleteWorkflow {
  code: string;
  name: string;
  reasons: string[];
}
interface VersionPreview {
  id: number;
  version: number;
  status: string;
  isCurrent: boolean;
  asOf: string | null;
  rows: number;
  fileName: string | null;
  promote: { id: number; version: number } | null;
  emptyAfter: boolean;
  workflows: DeleteWorkflow[];
}
/** 연결까지 정의 삭제 미리보기 (DOB-12 · Q208) */
export interface DefinitionPreview {
  code: string;
  name: string;
  /** 이 정의로 이어진 업무 구성의 자료 이름 (Phase O · BIZ-03) */
  sources?: string[];
  versions: { id: number; version: number; asOf: string | null; isCurrent: boolean; rows: number; status: string }[];
  rows: number;
  metrics: { code: string; label: string; workflow: string | null; derived: boolean }[];
  bindings: { id: number; workflow: string | null; builder: string; artifact: string; path: string }[];
  triggers: { id: number; workflow: string; kind: string; debounce: number | null; enabled: boolean }[];
  ontology: string[];
  proposals: number;
  contracts: number;
  pending: number;
  workflows: { code: string; name: string }[];
  blocked: string | null;
}
interface DefinitionDeleted {
  deleted: string;
  removed: {
    versions: number;
    rows: number;
    metricsDisabled: number;
    bindingsDisabled: number;
    triggersRemoved: number;
    screensCleared: number;
    calcRunsRemoved: number;
    noDataLeft: boolean;
    ontologyBackingRemoved: number;
  };
  rerun: string[];
}

const short = (xs: string[], n = 4) => (xs.length > n ? `${xs.slice(0, n).join(", ")} 외 ${xs.length - n}개` : xs.join(", "));

/** 연결까지 정의 삭제 확인 본문 — 무엇이 지워지고 무엇이 꺼지는지 */
export function DefinitionPreviewBody({ p }: { p: DefinitionPreview }) {
  const derived = p.metrics.filter((m) => m.derived).length;
  return (
    <div className="flex flex-col gap-xs text-[12.5px]" data-delete-preview="definition">
      {p.sources?.length ? (
        <p className="font-bold text-attention">
          업무 구성 자료({short(p.sources)})로 이어진 정의입니다. 지우면 그 자료는 &apos;자료 대기&apos;가 되고, 같은 열 구성의 파일을 다시 올리면 자동으로 다시 이어집니다.
        </p>
      ) : null}
      <ul className="list-disc pl-5">
        <li>
          올라온 버전 {p.versions.length}개{p.versions.length ? ` · ${p.rows.toLocaleString("ko-KR")}행` : ""} — {p.versions.length ? "행 · 원본 파일 · 그래프에서 지웁니다" : "없음"}
        </li>
        <li>
          지표 {p.metrics.length}개 끔{derived ? `(파생 ${derived}개 포함)` : ""}
          {p.metrics.length ? ` — ${short(p.metrics.map((m) => m.label || m.code))}` : ""}
        </li>
        <li>화면 바인딩 {p.bindings.length}개 끔</li>
        <li>
          워크플로 트리거 {p.triggers.length}개 지움{p.triggers.length ? ` — ${short([...new Set(p.triggers.map((t) => t.workflow))])}` : ""}
        </li>
        <li>이 자료로 계산된 값 — 업무 화면의 수치 · 서술 · 표/차트, 지난 화면 세대, 계산 기록, 실행 기록의 계산 값에서 지웁니다</li>
        {p.ontology.length ? <li>온톨로지 원천({short(p.ontology)}) — 원천 연결을 뺀 새 스키마 판을 만듭니다(객체 · 링크 유형은 남김)</li> : null}
        {p.proposals ? <li>이 자료를 원천으로 쓰는 승인 대기 온톨로지 제안 {p.proposals}건을 닫습니다</li> : null}
        {p.contracts ? <li>컬럼 정의서 {p.contracts}개 컬럼이 이 자료의 기준월 · 원천을 읽습니다 — &apos;입력 자료 없음&apos;으로 표시됩니다</li> : null}
        <li>온톨로지 구성 지도 · 그래프(Neo4j)에서 빠집니다 — 꺼진 지표는 넣지 않고, 올린 자료가 하나도 없으면 비어 있습니다</li>
      </ul>
      {p.versions.some((v) => v.isCurrent) && p.workflows.length ? (
        <p className="text-steel">다시 계산되는 워크플로: {short(p.workflows.map((w) => w.name))}</p>
      ) : null}
      <p className="text-steel">지표 · 바인딩은 지우지 않고 끄기만 합니다([지표]에서 다시 켤 수 있음). 버전 · 행은 되돌릴 수 없습니다. 업무 구성(지표 산식 · 화면 연결)은 남습니다.</p>
    </div>
  );
}

interface DocumentPreview {
  id: number;
  docCode: string;
  versions: number[];
  isCurrent: boolean;
  chunks: number;
  promote: { id: number; version: number } | null;
  workflows: DeleteWorkflow[];
}

/** 로그인한 관리자가 데이터 관리자인지 (서버가 최종 판정 — 화면은 버튼만 숨긴다) */
export function useIsDataAdmin(): boolean {
  const { menu } = useSession();
  return Boolean(menu?.user.dataAdmin);
}

export const reasonRule = (v: string) => (v.trim().length >= 2 ? null : "삭제 사유를 2자 이상 입력하세요");

function WorkflowList({ items }: { items: DeleteWorkflow[] }) {
  if (!items.length) return <p className="mt-xs text-[12px] text-steel">다시 도는 워크플로우가 없습니다.</p>;
  return (
    <p className="mt-xs text-[12px] text-steel">
      다시 계산되는 워크플로우: {items.map((w) => w.name).join(", ")}
    </p>
  );
}

export function useDataDelete() {
  const confirm = useConfirm();
  const { run, busy } = useAction();

  const deleteVersion = async (ds: { code: string; name: string }, versionId: number, reload: () => Promise<void>) => {
    const p = await run(() => apiGetC<VersionPreview>(`/admin/datasets/${ds.code}/versions/${versionId}/delete-preview`), undefined);
    if (!p) return;
    const reason = await confirm({
      title: `v${p.version}을(를) 삭제할까요?`,
      tone: "danger",
      confirmLabel: "삭제",
      body: (
        <div className="flex flex-col gap-xs text-[12.5px]" data-delete-preview="dataset">
          <p>
            <strong>{ds.name}</strong> v{p.version}
            {p.asOf ? ` (기준일 ${p.asOf})` : ""} · {p.rows.toLocaleString("ko-KR")}행{p.fileName ? ` · ${p.fileName}` : ""}
          </p>
          {p.isCurrent ? (
            p.promote ? (
              <p className="font-bold text-attention">현재 버전입니다. 지우면 v{p.promote.version}이(가) 현재 버전이 되고 화면이 그 자료로 다시 계산됩니다.</p>
            ) : (
              <p className="font-bold text-critical">현재 버전이고 같은 기준일의 이전 버전이 없습니다. 지우면 이 기준일 자료가 비어 관련 수치가 &apos;미제공&apos;이 될 수 있습니다.</p>
            )
          ) : (
            <p>현재 버전이 아니라 화면 수치는 바뀌지 않습니다.</p>
          )}
          {p.isCurrent ? <WorkflowList items={p.workflows} /> : null}
          <p className="text-steel">행 · 원본 파일을 지우고 그래프(Neo4j)에서도 지웁니다. 이 자료로 만든 지난 산출물 세대는 관련 계산이 다시 끝난 뒤 정리합니다. 되돌릴 수 없습니다 — 버전 기록은 &apos;삭제됨&apos;으로 남습니다.</p>
        </div>
      ),
      input: { label: "삭제 사유", placeholder: "예: 잘못된 기준월 파일 업로드", validate: reasonRule },
    });
    if (typeof reason !== "string" || !reason) return;
    await run(() => apiPost(`/admin/datasets/${ds.code}/versions/${versionId}/delete`, { reason }), "삭제했습니다 — 관련 계산 · 그래프 반영이 이어서 실행됩니다", reload);
  };

  const deleteDocument = async (d: { origin: string; id: number; title: string; docCode: string; version: number }, reload: () => Promise<void>) => {
    const p = await run(() => apiGetC<DocumentPreview>(`/admin/documents/${d.origin}/${d.id}/delete-preview`), undefined);
    if (!p) return;
    const reason = await confirm({
      title: `문서를 삭제할까요?`,
      tone: "danger",
      confirmLabel: "삭제",
      body: (
        <div className="flex flex-col gap-xs text-[12.5px]" data-delete-preview="document">
          <p>
            <strong>{d.title}</strong> ({d.docCode} v{d.version}) · 청크 {p.chunks.toLocaleString("ko-KR")}개
          </p>
          {p.isCurrent ? (
            p.promote ? (
              <p className="font-bold text-attention">현재 버전입니다. 지우면 v{p.promote.version}이(가) 현재 문서가 됩니다.</p>
            ) : (
              <p className="font-bold text-attention">현재 문서입니다. 지우면 검색 · 근거 인용 · 그래프에서 빠집니다.</p>
            )
          ) : (
            <p>현재 버전이 아닌 이전 판입니다.</p>
          )}
          {p.isCurrent ? <WorkflowList items={p.workflows} /> : null}
          <p className="text-steel">본문 · 청크(임베딩) · 구조화 결과 · 원본 파일을 지우고 검색 색인(Elasticsearch) · 그래프(Neo4j)에서도 지웁니다. AI 호출 기록 · 실행 기록 · 보고서 근거에 복사된 본문 조각과 그 조각이 든 옛 산출물 세대도 지웁니다. 되돌릴 수 없습니다.</p>
        </div>
      ),
      input: { label: "삭제 사유", placeholder: "예: 폐기된 지침", validate: reasonRule },
    });
    if (typeof reason !== "string" || !reason) return;
    await run(() => apiPost<{ scrubbed?: Scrubbed }>(`/admin/documents/${d.origin}/${d.id}/delete`, { reason }), (r) => `문서를 삭제했습니다 — 색인 · 그래프 반영이 이어서 실행됩니다${scrubText(r.scrubbed)}`, reload);
  };

  /** 연결까지 정의 삭제 (DOB-12 · Q208) — 미리보기 → 사유 → 실행. 지운 뒤 onDone(목록으로 돌아가기 등) */
  const deleteDefinition = async (ds: { code: string; name: string }, onDone: () => Promise<void> | void) => {
    const p = await run(() => apiGetC<DefinitionPreview>(`/admin/datasets/${ds.code}/delete-preview`), undefined);
    if (!p) return;
    if (p.blocked) {
      await confirm({ title: "지금은 지울 수 없습니다", body: <p className="text-[12.5px]">{p.blocked}</p>, confirmLabel: "확인", tone: "default" });
      return;
    }
    const linked = p.versions.length + p.metrics.length + p.bindings.length + p.triggers.length > 0;
    const reason = await confirm({
      title: linked ? `${ds.name} 정의를 연결까지 지울까요?` : `${ds.name} 정의를 지울까요?`,
      tone: "danger",
      confirmLabel: linked ? "연결까지 정의 삭제" : "정의 삭제",
      body: <DefinitionPreviewBody p={p} />,
      input: { label: "삭제 사유", placeholder: "예: 쓰지 않는 시연용 정의 정리", validate: reasonRule },
    });
    if (typeof reason !== "string" || !reason) return;
    await run(
      () => apiPost<DefinitionDeleted>(`/admin/datasets/${ds.code}/delete`, { reason }),
      (r) =>
        `정의를 지웠습니다 — 버전 ${r.removed.versions}개 · 지표 ${r.removed.metricsDisabled}개 끔 · 트리거 ${r.removed.triggersRemoved}개 지움 · 화면 ${r.removed.screensCleared}개 · 계산 기록 ${r.removed.calcRunsRemoved}건 정리` +
        `${r.removed.ontologyBackingRemoved ? ` · 온톨로지 원천 ${r.removed.ontologyBackingRemoved}곳 제거` : ""}${r.removed.noDataLeft ? " · 올린 자료가 없어 화면을 모두 비웠습니다" : r.rerun.length ? ` · 다시 계산 ${r.rerun.length}개` : ""}`,
      onDone,
    );
  };

  return { deleteVersion, deleteDocument, deleteDefinition, busy };
}

interface PurgeTaskRow {
  id: number;
  store: "es" | "neo4j" | "pg";
  subjectKind: string;
  subjectRef: string;
  status: string;
  attempts: number;
  lastError: string | null;
  createdBy: string | null;
  createdAt: string | null;
  doneAt: string | null;
}

export const STORE_LABEL: Record<string, string> = { es: "검색 색인(Elasticsearch)", neo4j: "그래프(Neo4j)", pg: "산출물 이력(PostgreSQL)" };

/** 삭제 반영 상태 (DEL-07) — 외부 저장소 삭제 작업. 저장소가 멈췄으면 워커가 30초마다 다시 시도한다 */
export function PurgeStatus() {
  const data = useApiData<{ counts: Record<string, number>; tasks: PurgeTaskRow[] }>("/admin/purge-tasks?limit=30", { refreshMs: 10000 });
  const isDataAdmin = useIsDataAdmin();
  const { run, busy } = useAction();
  const tasks = data.data?.tasks ?? [];
  if (data.data && !tasks.length) return null;
  const pending = data.data?.counts.pending ?? 0;
  return (
    <Card
      title={
        <span className="flex items-center gap-xs">
          삭제 반영 상태 {pending ? <Badge tone="attention">대기 {pending}</Badge> : <Badge tone="success">모두 반영</Badge>}
        </span>
      }
      actions={
        isDataAdmin && pending ? (
          <Button size="sm" variant="quiet" disabled={busy} onClick={() => run(() => apiPost("/admin/purge-tasks/run"), "삭제 작업을 다시 실행했습니다", data.reload)}>
            지금 다시 실행
          </Button>
        ) : null
      }
    >
      <p className="mb-md text-[12px] text-steel">자료를 지우면 원장(PostgreSQL · 청크 임베딩)은 바로 지우고, 검색 색인 · 그래프는 이 작업으로 지웁니다. 저장소가 멈춰 있으면 끝날 때까지 다시 시도합니다.</p>
      <Loading error={data.error} loading={!data.data && data.loading} />
      <Table head={["저장소", "대상", "상태", "시도", "요청", "완료 · 오류"]}>
        {tasks.map((t) => (
          <tr key={t.id}>
            <C>{STORE_LABEL[t.store] ?? t.store}</C>
            <C mono>{t.subjectRef}</C>
            <C>
              <StatusBadge status={t.status} />
            </C>
            <C right>{t.attempts}</C>
            <C className="text-[11px]">
              {t.createdBy ?? "-"}
              <br />
              {fmtTime(t.createdAt)}
            </C>
            <C className="max-w-[320px] text-[11px]">{t.doneAt ? fmtTime(t.doneAt) : t.lastError ? <span className="text-critical">{t.lastError}</span> : "-"}</C>
          </tr>
        ))}
      </Table>
    </Card>
  );
}
