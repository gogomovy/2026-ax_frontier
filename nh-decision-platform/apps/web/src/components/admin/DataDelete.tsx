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

  return { deleteVersion, deleteDocument, busy };
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
