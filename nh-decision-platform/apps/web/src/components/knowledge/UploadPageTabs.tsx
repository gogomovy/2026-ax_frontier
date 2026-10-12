"use client";

import { useState } from "react";
import { StewardReview, type ReviewData } from "@/components/knowledge/StewardReview";
import { UploadWorkspace, type Uploadable } from "@/components/knowledge/UploadWorkspace";
import { PillTabs } from "@/components/ui/primitives";

/** [자료 올리기] 화면 — 올리기(권한 db_upload) · 승인할 자료(부서 데이터 책임자) */
export function UploadPageTabs({ options, review, initialTab }: { options: Uploadable | null; review: ReviewData | null; initialTab?: "upload" | "review" }) {
  const [tab, setTab] = useState<"upload" | "review">(initialTab === "review" && review ? "review" : options ? "upload" : "review");
  if (!review) return options ? <UploadWorkspace initial={options} /> : null;
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
      {tab === "upload" ? <UploadWorkspace initial={options} /> : <StewardReview initial={review} />}
    </div>
  );
}
