"use client";

import { useState } from "react";
import { Loading, useApiData } from "@/components/admin/kit";
import { RequestReviewCard } from "@/components/knowledge/RequestReviewCard";
import type { UploadReq } from "@/components/knowledge/UploadWorkspace";
import { EmptyState, Notice } from "@/components/ui/Layout";
import { PillTabs } from "@/components/ui/primitives";

export interface ReviewData {
  scope: { code: string; name: string } | null;
  items: UploadReq[];
  counts: Record<string, number>;
}

type Status = "pending" | "approved" | "rejected" | "failed" | "";

/** 부서 데이터 책임자 — 자기 부서 사용자가 올린 자료 승인 · 반려 (UPL-04 · Q107). 본인 요청은 다른 책임자 · 관리자가 처리 */
export function StewardReview({ initial }: { initial: ReviewData }) {
  const [status, setStatus] = useState<Status>("pending");
  const data = useApiData<ReviewData>(`/db/uploads/review?status=${status}`, { refreshMs: 20000 });
  const d = data.data ?? (status === "pending" ? initial : null);
  const c = d?.counts ?? initial.counts;
  return (
    <section aria-label="승인할 자료" className="flex flex-col gap-md" data-steward-review>
      <Notice tone="info" title={`${d?.scope?.name ?? initial.scope?.name ?? "소속 부서"} 데이터 책임자`}>
        이 부서 사용자가 올린 자료를 검사 결과와 함께 보고 승인하면 관리자 승인과 같은 경로로 반영되어 관련 화면이 다시 계산됩니다. 본인이 올린 자료는 다른 책임자나 관리자가 처리합니다.
      </Notice>
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
      <Loading error={data.error} loading={!d && data.loading} />
      {d && !d.items.length ? <EmptyState compact title={status === "pending" ? "승인할 자료가 없습니다" : "요청이 없습니다"} description="부서 사용자가 자료를 올리면 여기에 나타납니다." /> : null}
      {(d?.items ?? []).map((r) => (
        <RequestReviewCard key={r.id} r={r} reload={data.reload} base="/db/uploads" canReview={r.canReview !== false} blockedReason="본인이 올린 자료입니다 — 다른 책임자나 관리자가 처리합니다." />
      ))}
    </section>
  );
}
