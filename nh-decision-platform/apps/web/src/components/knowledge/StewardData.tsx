"use client";

import { useCallback, useState } from "react";
import { C, Card, Loading, StatusBadge, Table, fmtTime, useAction, useApiData } from "@/components/admin/kit";
import { STORE_LABEL, reasonRule, type DeleteWorkflow } from "@/components/admin/DataDelete";
import { useConfirm } from "@/components/providers/UiProvider";
import { EmptyState, KeyValueList, Notice } from "@/components/ui/Layout";
import { Badge, Button, PillTabs } from "@/components/ui/primitives";
import { apiGetC, apiPost } from "@/lib/api-client";
import { scrubText, type Scrubbed } from "@/lib/scrubText";

/** 부서 데이터 책임자가 볼 수 있는 자료 한 건 — 우리 부서가 올려 반영된 데이터셋 버전 · 문서 (Phase J 후속 · DEL-09) */
export interface StewardItem {
  requestId: number;
  kind: "dataset" | "document";
  origin: "bank" | "ext";
  target: string;
  targetLabel: string;
  label: string;
  version: number;
  status: string;
  isCurrent: boolean;
  fileName: string;
  requestedBy: string;
  requestedByName?: string | null;
  approvedAt: string | null;
  approvedByName?: string | null;
  asOf?: string | null;
  rows?: number | null;
  docCode?: string;
  docClass?: string;
  deleted?: { at: string; by: string; byName?: string | null; reason: string } | null;
}
interface ItemsData {
  scope: { code: string; name: string } | null;
  items: StewardItem[];
}
interface DeletePreview {
  requestId: number;
  isCurrent: boolean;
  promote: { id: number; version: number } | null;
  workflows: DeleteWorkflow[];
  rows?: number;
  asOf?: string | null;
  emptyAfter?: boolean;
  chunks?: number;
}
interface PurgeRow {
  id: number;
  store: "es" | "neo4j" | "pg";
  subjectRef: string;
  status: string;
  attempts: number;
  lastError: string | null;
  createdAt: string | null;
  doneAt: string | null;
}

function ItemCard({ it, reload }: { it: StewardItem; reload: () => Promise<void> }) {
  const confirm = useConfirm();
  const { run, busy } = useAction();
  const isDataset = it.kind === "dataset";

  const remove = async () => {
    const p = await run(() => apiGetC<DeletePreview>(`/db/steward/items/${it.requestId}/delete-preview`), undefined);
    if (!p) return;
    const reason = await confirm({
      title: isDataset ? `v${it.version}을(를) 삭제할까요?` : "문서를 삭제할까요?",
      tone: "danger",
      confirmLabel: "삭제",
      body: (
        <div className="flex flex-col gap-xs text-[12.5px]" data-steward-delete-preview={it.kind}>
          <p>
            <strong>{it.label}</strong> {isDataset ? `v${it.version}` : `(${it.docCode} v${it.version})`}
            {isDataset ? ` · ${(p.rows ?? it.rows ?? 0).toLocaleString("ko-KR")}행${p.asOf ? ` (기준일 ${p.asOf})` : ""}` : ` · 청크 ${(p.chunks ?? 0).toLocaleString("ko-KR")}개`}
          </p>
          {p.isCurrent ? (
            p.promote ? (
              <p className="font-bold text-attention">현재 버전입니다. 지우면 v{p.promote.version}이(가) 현재 {isDataset ? "버전" : "문서"}이 되고 화면이 그 자료로 다시 계산됩니다.</p>
            ) : (
              <p className="font-bold text-critical">
                {isDataset ? "현재 버전이고 같은 기준일의 이전 버전이 없습니다. 지우면 이 기준일 자료가 비어 관련 수치가 '갱신 실패'로 표시되고 검색에서는 값이 빠집니다." : "현재 문서입니다. 지우면 검색 · 근거 인용 · 그래프에서 빠집니다."}
              </p>
            )
          ) : (
            <p>현재 버전이 아니라 화면 수치는 바뀌지 않습니다.</p>
          )}
          {p.isCurrent ? (
            p.workflows.length ? (
              <p className="text-steel">다시 계산되는 워크플로우: {p.workflows.map((w) => w.name).join(", ")}</p>
            ) : (
              <p className="text-steel">다시 도는 워크플로우가 없습니다.</p>
            )
          ) : null}
          <p className="text-steel">
            {isDataset
              ? "행 · 원본 파일을 지우고 그래프(Neo4j)에서도 지웁니다. 이 자료로 만든 지난 산출물 세대는 관련 계산이 다시 끝난 뒤 정리합니다."
              : "본문 · 청크(임베딩) · 구조화 결과 · 원본 파일을 지우고 검색 색인(Elasticsearch) · 그래프(Neo4j)에서도 지웁니다. AI 호출 기록 · 실행 기록 · 보고서 근거에 복사된 본문 조각도 지웁니다."}{" "}
            되돌릴 수 없습니다. 삭제 기록은 감사 로그에 남습니다.
          </p>
        </div>
      ),
      input: { label: "삭제 사유", placeholder: isDataset ? "예: 잘못된 기준월 파일 업로드" : "예: 폐기된 지침", validate: reasonRule },
    });
    if (typeof reason !== "string" || !reason) return;
    await run(() => apiPost<{ scrubbed?: Scrubbed }>(`/db/steward/items/${it.requestId}/delete`, { reason }), (r) => `삭제했습니다 — 관련 계산 · 검색 색인 · 그래프 반영이 이어서 실행됩니다${scrubText(r.scrubbed)}`, reload);
  };

  return (
    <Card
      title={
        <span className="flex flex-wrap items-center gap-xs" data-steward-item={it.requestId}>
          <span className="font-mono text-[12px] text-stone">#{it.requestId}</span>
          {it.label}
          <Badge tone={isDataset ? "info" : "neutral"}>{isDataset ? "정형 자료" : "문서"}</Badge>
          <Badge tone={it.origin === "bank" ? "dark" : "info"}>{it.origin === "bank" ? "당행" : "외부"}</Badge>
          {it.deleted ? <Badge tone="attention">삭제됨</Badge> : it.isCurrent ? <Badge tone="success">현재 버전</Badge> : <Badge>이전 버전</Badge>}
        </span>
      }
      actions={
        it.deleted ? null : (
          <Button size="sm" variant="danger" disabled={busy} onClick={remove}>
            삭제…
          </Button>
        )
      }
    >
      <KeyValueList
        columns={2}
        dense
        items={[
          { label: "버전", value: isDataset ? `v${it.version}${it.asOf ? ` · 기준일 ${it.asOf}` : ""}${it.rows != null ? ` · ${it.rows.toLocaleString("ko-KR")}행` : ""}` : `${it.docCode} v${it.version}` },
          { label: "파일", value: <span className="break-all">{it.fileName}</span> },
          { label: "올린 사람", value: it.requestedByName ?? it.requestedBy },
          { label: "반영 시각", value: `${fmtTime(it.approvedAt)}${it.approvedByName ? ` · ${it.approvedByName} 승인` : ""}` },
          ...(it.deleted ? [{ label: "삭제", value: `${it.deleted.byName ?? it.deleted.by} · ${fmtTime(it.deleted.at)}` }, { label: "삭제 사유", value: it.deleted.reason }] : []),
        ]}
      />
    </Card>
  );
}

/** 삭제 반영 상태 — 내가 지운 자료의 검색 색인 · 그래프 삭제 작업. 저장소가 멈췄으면 워커가 30초마다 다시 시도한다 */
function MyPurgeStatus() {
  const data = useApiData<{ counts: Record<string, number>; tasks: PurgeRow[] }>("/db/steward/purge-status?limit=20", { refreshMs: 10000 });
  const { run, busy } = useAction();
  const tasks = data.data?.tasks ?? [];
  if (data.data && !tasks.length) return null;
  const pending = data.data?.counts.pending ?? 0;
  return (
    <Card
      title={
        <span className="flex items-center gap-xs" data-steward-purge>
          삭제 반영 상태 {pending ? <Badge tone="attention">대기 {pending}</Badge> : <Badge tone="success">모두 반영</Badge>}
        </span>
      }
      actions={
        pending ? (
          <Button size="sm" variant="quiet" disabled={busy} onClick={() => run(() => apiPost("/db/steward/purge-run"), "삭제 작업을 다시 실행했습니다", data.reload)}>
            지금 다시 실행
          </Button>
        ) : null
      }
    >
      <p className="mb-md text-[12px] text-steel">지운 자료는 원장(PostgreSQL · 청크 임베딩)에서 바로 사라지고, 검색 색인 · 그래프는 아래 작업으로 지웁니다. 저장소가 멈춰 있으면 끝날 때까지 다시 시도합니다.</p>
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
            <C className="text-[11px]">{fmtTime(t.createdAt)}</C>
            <C className="max-w-[320px] text-[11px]">{t.doneAt ? fmtTime(t.doneAt) : t.lastError ? <span className="text-critical">{t.lastError}</span> : "-"}</C>
          </tr>
        ))}
      </Table>
    </Card>
  );
}

/**
 * 부서 데이터 책임자 — 우리 부서가 올려 반영된 자료 삭제 (Phase J 후속 · DEL-09~12 · Q157~Q159).
 * 관리자 삭제와 같은 연쇄(행 · 청크 임베딩 · 검색 색인 · 그래프 · 원본 파일 · 재계산)를 타며, 다른 부서나 관리자가 올린 자료는 보이지 않는다.
 */
export function StewardData() {
  const [view, setView] = useState<"active" | "deleted">("active");
  const data = useApiData<ItemsData>(`/db/steward/items?deleted=${view === "deleted"}`, { refreshMs: 20000 });
  // 삭제하면 '삭제 반영 상태' 카드도 바로 새로 불러온다(자체 주기는 10초)
  const [purgeStamp, setPurgeStamp] = useState(0);
  const { reload: reloadItems } = data;
  const reload = useCallback(async () => {
    await reloadItems();
    setPurgeStamp((n) => n + 1);
  }, [reloadItems]);
  const d = data.data;
  return (
    <section aria-label="우리 부서 자료" className="flex flex-col gap-md" data-steward-data>
      <Notice tone="info" title={`${d?.scope?.name ?? "소속 부서"} 자료 관리`}>
        우리 부서가 올려 반영된 자료만 볼 수 있고 삭제할 수 있습니다. 삭제하면 검색 · 질문하기와 그래프에서도 함께 지워지고 관련 화면이 다시 계산됩니다. 관리자가 직접 올렸거나 다른 부서가 올린 자료는 데이터 관리자에게 요청하세요.
      </Notice>
      <PillTabs
        size="sm"
        label="자료 보기"
        value={view}
        onChange={setView}
        items={[
          { key: "active", label: "삭제할 수 있는 자료" },
          { key: "deleted", label: "삭제한 기록" },
        ]}
      />
      <Loading error={data.error} loading={!d && data.loading} />
      {d && !d.items.length ? <EmptyState compact title={view === "active" ? "삭제할 수 있는 자료가 없습니다" : "삭제한 기록이 없습니다"} description="부서 사용자가 올려 승인된 자료가 여기에 나타납니다." /> : null}
      {(d?.items ?? []).map((it) => (
        <ItemCard key={it.requestId} it={it} reload={reload} />
      ))}
      <MyPurgeStatus key={purgeStamp} />
    </section>
  );
}
