"use client";

import { useState } from "react";
import { AdminPage, Card, Check, Loading, fmtTime, useAction, useApiData } from "@/components/admin/kit";
import { RequestPreview, RequestStatus, type UploadReq } from "@/components/knowledge/UploadWorkspace";
import { EmptyState, KeyValueList } from "@/components/ui/Layout";
import { Badge, Button, PillTabs } from "@/components/ui/primitives";
import { StatCard, StatGrid } from "@/components/ui/StatCard";
import { apiPost } from "@/lib/api-client";

type Status = "pending" | "approved" | "rejected" | "failed" | "";
interface Data {
  items: UploadReq[];
  counts: Record<string, number>;
}

/** 자료 승인 (Phase C · UPL-02 · UPL-03) — 업무 사용자가 올린 자료를 검사 결과와 함께 보고 승인(확정 · 재계산) 또는 반려(사유) */
export default function AdminUploads() {
  const [status, setStatus] = useState<Status>("pending");
  const data = useApiData<Data>(`/admin/uploads${status ? `?status=${status}` : ""}`, { refreshMs: 15000 });
  const c = data.data?.counts ?? {};
  return (
    <AdminPage
      title="자료 승인"
      description="업무 부서가 [데이터베이스 > 자료 올리기]에서 올린 자료입니다. 검사 결과를 확인하고 승인하면 관리자 직접 업로드와 같은 경로로 확정되어 관련 워크플로가 다시 계산합니다. 반려하면 아무것도 바뀌지 않습니다."
      summary={
        <StatGrid columns={4} label="요청 요약">
          <StatCard label="승인 대기" value={c.pending ?? 0} unit="건" tone={c.pending ? "attention" : "success"} hint={c.pending ? "검토가 필요합니다" : "대기 중인 요청 없음"} />
          <StatCard label="승인 · 반영" value={c.approved ?? 0} unit="건" />
          <StatCard label="반려" value={c.rejected ?? 0} unit="건" />
          <StatCard label="반영 실패" value={c.failed ?? 0} unit="건" tone={c.failed ? "critical" : "default"} hint="승인했지만 확정 단계에서 실패" />
        </StatGrid>
      }
    >
      <div className="mb-md">
        <PillTabs
          size="sm"
          label="요청 상태"
          value={status}
          onChange={setStatus}
          items={[
            { key: "pending", label: "승인 대기", count: c.pending ?? 0 },
            { key: "approved", label: "승인", count: c.approved ?? 0 },
            { key: "rejected", label: "반려", count: c.rejected ?? 0 },
            { key: "failed", label: "실패", count: c.failed ?? 0 },
            { key: "", label: "전체" },
          ]}
        />
      </div>
      <Loading error={data.error} loading={!data.data && data.loading} />
      {data.data && !data.data.items.length ? (
        <EmptyState title={status === "pending" ? "승인할 자료가 없습니다" : "요청이 없습니다"} description="업무 부서가 자료를 올리면 여기에 나타나고 관리자 홈의 처리할 일에도 표시됩니다." />
      ) : null}
      {(data.data?.items ?? []).map((r) => (
        <RequestCard key={r.id} r={r} reload={data.reload} />
      ))}
    </AdminPage>
  );
}

function RequestCard({ r, reload }: { r: UploadReq; reload: () => Promise<void> }) {
  const { run, busy } = useAction();
  const [note, setNote] = useState("");
  const [force, setForce] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const warned = r.preview.quality?.status === "warning";
  return (
    <Card
      title={
        <span className="flex flex-wrap items-center gap-xs">
          <span className="font-mono text-[12px] text-stone">#{r.id}</span>
          {r.targetLabel}
          <Badge tone={r.kind === "dataset" ? "info" : "neutral"}>{r.kind === "dataset" ? "정형 자료" : "문서"}</Badge>
          <Badge tone={r.origin === "bank" ? "dark" : "info"}>{r.origin === "bank" ? "당행" : "외부"}</Badge>
          <RequestStatus r={r} />
        </span>
      }
    >
      <div className="grid grid-cols-1 gap-lg lg:grid-cols-[minmax(0,320px)_1fr]">
        <KeyValueList
          columns={1}
          dense
          items={[
            { label: "요청자", value: `${r.requestedByName ?? r.requestedBy}${r.requestedOrgName ? ` · ${r.requestedOrgName}` : ""}` },
            { label: "요청 시각", value: fmtTime(r.createdAt) },
            { label: "파일", value: <span className="break-all">{r.fileName}</span> },
            { label: "대상", value: <span className="font-mono text-[11.5px]">{r.target}</span> },
            ...(r.meta.note ? [{ label: "요청 메모", value: r.meta.note }] : []),
            ...(r.reviewedAt ? [{ label: "처리", value: `${r.reviewedByName ?? "-"} · ${fmtTime(r.reviewedAt)}` }] : []),
            ...(r.reviewNote ? [{ label: "처리 메모", value: r.reviewNote }] : []),
            ...(r.result.error ? [{ label: "실패 사유", value: <span className="text-critical">{r.result.error}</span> }] : []),
            ...(r.status === "approved" && r.result.version ? [{ label: "반영", value: r.kind === "dataset" ? `v${r.result.version} · ${r.result.rows ?? "-"}행${r.result.isCurrent ? " · 현재 버전" : ""}` : `${r.result.docCode} v${r.result.version}` }] : []),
          ]}
        />
        <div className="min-w-0">
          <p className="mb-xs text-[12px] font-bold text-steel">검사 결과</p>
          <RequestPreview r={r} showSample />
        </div>
      </div>
      {r.status === "pending" ? (
        <div className="mt-lg flex flex-col gap-xs border-t border-hairline-soft pt-md" data-upload-review={r.id}>
          <label htmlFor={`note-${r.id}`} className="text-[12px] font-bold text-charcoal">
            {rejecting ? "반려 사유(필수)" : "처리 메모(선택)"}
          </label>
          <textarea id={`note-${r.id}`} className="input text-[12.5px]" rows={2} value={note} onChange={(e) => setNote(e.target.value)} maxLength={1000} />
          <div className="flex flex-wrap items-center gap-xs">
            {!rejecting ? (
              <>
                <Button size="sm" variant="confirm" disabled={busy} onClick={() => run(() => apiPost(`/admin/uploads/${r.id}/approve`, { note: note || null, force }), "승인했습니다 — 관련 워크플로가 다시 계산합니다", reload)}>
                  승인하고 반영
                </Button>
                {r.kind === "dataset" ? <Check label={warned ? "승인 때 품질 실패여도 확정(주의 항목 있음)" : "승인 때 품질 실패여도 확정"} checked={force} onChange={setForce} /> : null}
                <Button size="sm" variant="ghost" disabled={busy} onClick={() => setRejecting(true)}>
                  반려…
                </Button>
              </>
            ) : (
              <>
                <Button size="sm" variant="primary" disabled={busy || !note.trim()} onClick={() => run(() => apiPost(`/admin/uploads/${r.id}/reject`, { note }), "반려했습니다", reload)}>
                  반려 확정
                </Button>
                <Button size="sm" variant="quiet" disabled={busy} onClick={() => setRejecting(false)}>
                  취소
                </Button>
              </>
            )}
          </div>
        </div>
      ) : null}
    </Card>
  );
}
