"use client";

import { useState } from "react";
import { Card, Check, fmtTime, useAction } from "@/components/admin/kit";
import { RequestPreview, RequestStatus, type UploadReq } from "@/components/knowledge/UploadWorkspace";
import { useConfirm } from "@/components/providers/UiProvider";
import { KeyValueList } from "@/components/ui/Layout";
import { Badge, Button } from "@/components/ui/primitives";
import { apiPost } from "@/lib/api-client";

/**
 * 자료 요청 검토 카드 (Phase C · UPL-02 · UPL-04) — 관리자 [자료 승인] · 부서 데이터 책임자 [승인할 자료] 공용.
 * base: 승인 · 반려 API 경로 앞부분 (/admin/uploads · /db/uploads). canReview=false 면 동작 없이 보기만(예: 본인 요청).
 */
export function RequestReviewCard({ r, reload, base, canReview = true, blockedReason }: { r: UploadReq; reload: () => Promise<void>; base: string; canReview?: boolean; blockedReason?: string }) {
  const { run, busy } = useAction();
  const confirm = useConfirm();
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
            ...(r.reviewedAt ? [{ label: "처리", value: `${r.reviewedByName ?? "-"} · ${fmtTime(r.reviewedAt)}${r.result.via === "steward" ? " · 부서 데이터 책임자" : ""}` }] : []),
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
      {r.status === "pending" && !canReview && blockedReason ? <p className="mt-md text-[12px] text-stone">{blockedReason}</p> : null}
      {r.status === "pending" && canReview ? (
        <div className="mt-lg flex flex-col gap-xs border-t border-hairline-soft pt-md" data-upload-review={r.id}>
          <label htmlFor={`note-${r.id}`} className="text-[12px] font-bold text-charcoal">
            {rejecting ? "반려 사유(필수)" : "처리 메모(선택)"}
          </label>
          <textarea id={`note-${r.id}`} className="input text-[12.5px]" rows={2} value={note} onChange={(e) => setNote(e.target.value)} maxLength={1000} />
          <div className="flex flex-wrap items-center gap-xs">
            {!rejecting ? (
              <>
                <Button
                  size="sm"
                  variant={force ? "danger" : "confirm"}
                  disabled={busy}
                  onClick={async () => {
                    // 품질 실패여도 확정 — 틀린 수치가 화면에 나갈 수 있어 한 번 더 묻는다 (Phase E · INT-01)
                    if (force) {
                      const ok = await confirm({ title: "품질 검사에 실패해도 확정할까요?", body: `${r.targetLabel} — 품질 검사를 통과하지 못한 자료도 현재 버전이 되고 관련 화면 수치가 다시 계산됩니다.`, confirmLabel: "실패해도 확정", tone: "danger" });
                      if (!ok) return;
                    }
                    await run(() => apiPost(`${base}/${r.id}/approve`, { note: note || null, force }), "승인했습니다 — 관련 워크플로가 다시 계산합니다", reload);
                  }}
                >
                  승인하고 반영
                </Button>
                {r.kind === "dataset" ? <Check label={warned ? "승인 때 품질 실패여도 확정(주의 항목 있음)" : "승인 때 품질 실패여도 확정"} checked={force} onChange={setForce} /> : null}
                <Button size="sm" variant="ghost" disabled={busy} onClick={() => setRejecting(true)}>
                  반려…
                </Button>
              </>
            ) : (
              <>
                <Button size="sm" variant="primary" disabled={busy || !note.trim()} onClick={() => run(() => apiPost(`${base}/${r.id}/reject`, { note }), "반려했습니다", reload)}>
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
