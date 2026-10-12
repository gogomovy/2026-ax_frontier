"use client";

import { useState } from "react";
import { AdminPage, Loading, useApiData } from "@/components/admin/kit";
import { RequestReviewCard } from "@/components/knowledge/RequestReviewCard";
import type { UploadReq } from "@/components/knowledge/UploadWorkspace";
import { EmptyState } from "@/components/ui/Layout";
import { PillTabs } from "@/components/ui/primitives";
import { StatCard, StatGrid } from "@/components/ui/StatCard";

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
        <RequestReviewCard key={r.id} r={r} reload={data.reload} base="/admin/uploads" />
      ))}
    </AdminPage>
  );
}
