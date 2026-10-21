"use client";

import { useState } from "react";
import { IntakeWizard } from "@/components/knowledge/IntakeWizard";
import { StewardData } from "@/components/knowledge/StewardData";
import { StewardProposals } from "@/components/knowledge/StewardProposals";
import { StewardReview, type ReviewData } from "@/components/knowledge/StewardReview";
import { UploadWorkspace, type Uploadable } from "@/components/knowledge/UploadWorkspace";
import { PillTabs } from "@/components/ui/primitives";
import type { ProposalsData } from "@/lib/stewardProposals";

export type UploadTab = "upload" | "intake" | "review" | "proposals" | "data";

/**
 * [자료 올리기] 화면 — 올리기(권한 db_upload) · 자료 등록(에이전트 분석 → 확인 · 반영, Phase M · DOB-01 · Q191) · 승인할 자료 · 우리 부서 자료(삭제) (부서 데이터 책임자).
 * `initialTarget` = 주소 `?target=` (Phase E · UXF-05). 책임자(review 있음)는 올리기 권한이 없어도 [승인할 자료] · [우리 부서 자료]를 쓴다.
 * [에이전트 제안](§40 STW) — 새 자료로 에이전트가 만든 분석 화면 · 추적 지표 · 개념 연결 · 부서 사용자 분석 요청(책임자 · 관리자, proposals 가 있을 때).
 */
export function UploadPageTabs({ options, review, proposals, initialTab, initialTarget }: { options: Uploadable | null; review: ReviewData | null; proposals?: ProposalsData | null; initialTab?: UploadTab; initialTarget?: string }) {
  const allowed: UploadTab[] = [...(options ? (["upload", "intake"] as const) : []), ...(review ? (["review"] as const) : []), ...(proposals ? (["proposals"] as const) : []), ...(review ? (["data"] as const) : [])];
  const [tab, setTab] = useState<UploadTab>(initialTab && allowed.includes(initialTab) ? initialTab : allowed[0]);
  // 같은 화면에서 ?target= 만 바뀌어도(예: '고쳐서 다시 올리기') 새 대상으로 시작하도록 key 로 다시 만든다
  const workspace = options ? <UploadWorkspace key={initialTarget ?? ""} initial={options} initialTarget={initialTarget} /> : null;
  return (
    <div className="flex flex-col gap-lg">
      <PillTabs
        label="자료 올리기 화면"
        value={tab}
        onChange={setTab}
        items={[
          ...(options ? [{ key: "upload" as const, label: "자료 올리기" }, { key: "intake" as const, label: "자료 등록(에이전트 분석)" }] : []),
          ...(review ? [{ key: "review" as const, label: "승인할 자료", count: review.counts.pending ?? 0 }] : []),
          ...(proposals ? [{ key: "proposals" as const, label: "에이전트 제안", count: proposals.counts.total ?? 0 }] : []),
          ...(review ? [{ key: "data" as const, label: "우리 부서 자료" }] : []),
        ]}
      />
      {tab === "upload" ? (
        workspace
      ) : tab === "intake" ? (
        <IntakeWizard context="business" />
      ) : tab === "data" ? (
        <StewardData />
      ) : tab === "proposals" && proposals ? (
        <StewardProposals initial={proposals} />
      ) : review ? (
        <StewardReview initial={review} />
      ) : null}
    </div>
  );
}
