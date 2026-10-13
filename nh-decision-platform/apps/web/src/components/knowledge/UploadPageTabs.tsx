"use client";

import { useState } from "react";
import { StewardReview, type ReviewData } from "@/components/knowledge/StewardReview";
import { UploadWorkspace, type Uploadable } from "@/components/knowledge/UploadWorkspace";
import { PillTabs } from "@/components/ui/primitives";

/** [자료 올리기] 화면 — 올리기(권한 db_upload) · 승인할 자료(부서 데이터 책임자). `initialTarget` = 주소 `?target=` (Phase E · UXF-05) */
export function UploadPageTabs({ options, review, initialTab, initialTarget }: { options: Uploadable | null; review: ReviewData | null; initialTab?: "upload" | "review"; initialTarget?: string }) {
  const [tab, setTab] = useState<"upload" | "review">(initialTab === "review" && review ? "review" : options ? "upload" : "review");
  // 같은 화면에서 ?target= 만 바뀌어도(예: '고쳐서 다시 올리기') 새 대상으로 시작하도록 key 로 다시 만든다
  const workspace = options ? <UploadWorkspace key={initialTarget ?? ""} initial={options} initialTarget={initialTarget} /> : null;
  if (!review) return workspace;
  if (!options) return <StewardReview initial={review} />;
  return (
    <div className="flex flex-col gap-lg">
      <PillTabs
        label="자료 올리기 화면"
        value={tab}
        onChange={setTab}
        items={[
          { key: "upload", label: "자료 올리기" },
          { key: "review", label: "승인할 자료", count: review.counts.pending ?? 0 },
        ]}
      />
      {tab === "upload" ? workspace : <StewardReview initial={review} />}
    </div>
  );
}
