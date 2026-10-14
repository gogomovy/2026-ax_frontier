"use client";

import { useState } from "react";
import { StewardData } from "@/components/knowledge/StewardData";
import { StewardReview, type ReviewData } from "@/components/knowledge/StewardReview";
import { UploadWorkspace, type Uploadable } from "@/components/knowledge/UploadWorkspace";
import { PillTabs } from "@/components/ui/primitives";

type Tab = "upload" | "review" | "data";

/**
 * [자료 올리기] 화면 — 올리기(권한 db_upload) · 승인할 자료 · 우리 부서 자료(삭제) (부서 데이터 책임자). `initialTarget` = 주소 `?target=` (Phase E · UXF-05)
 * 책임자(review 있음)는 올리기 권한이 없어도 [승인할 자료] · [우리 부서 자료]를 쓴다.
 */
export function UploadPageTabs({ options, review, initialTab, initialTarget }: { options: Uploadable | null; review: ReviewData | null; initialTab?: Tab; initialTarget?: string }) {
  const [tab, setTab] = useState<Tab>(review && (initialTab === "review" || initialTab === "data") ? initialTab : options ? "upload" : "review");
  // 같은 화면에서 ?target= 만 바뀌어도(예: '고쳐서 다시 올리기') 새 대상으로 시작하도록 key 로 다시 만든다
  const workspace = options ? <UploadWorkspace key={initialTarget ?? ""} initial={options} initialTarget={initialTarget} /> : null;
  if (!review) return workspace;
  return (
    <div className="flex flex-col gap-lg">
      <PillTabs
        label="자료 올리기 화면"
        value={tab}
        onChange={setTab}
        items={[
          ...(options ? [{ key: "upload" as const, label: "자료 올리기" }] : []),
          { key: "review" as const, label: "승인할 자료", count: review.counts.pending ?? 0 },
          { key: "data" as const, label: "우리 부서 자료" },
        ]}
      />
      {tab === "upload" ? workspace : tab === "data" ? <StewardData /> : <StewardReview initial={review} />}
    </div>
  );
}
