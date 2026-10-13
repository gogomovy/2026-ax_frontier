import { redirect } from "next/navigation";
import type { ReviewData } from "@/components/knowledge/StewardReview";
import { UploadPageTabs } from "@/components/knowledge/UploadPageTabs";
import type { Uploadable } from "@/components/knowledge/UploadWorkspace";
import { PageHeader } from "@/components/layout/PageHeader";
import { apiTry } from "@/lib/api-server";

export const dynamic = "force-dynamic";

/**
 * 업무 자료 올리기 (Phase C · UPL-01~04) — 올리기 → 검사 → 승인 요청 · 내 요청 (권한 db_upload),
 * 승인할 자료(부서 데이터 책임자 — 자기 부서 요청 승인 · 반려). 둘 다 없으면 권한 없음 화면.
 */
export default async function KnowledgeUploadPage(props: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const sp = await props.searchParams;
  const [options, review] = await Promise.all([apiTry<Uploadable>("/db/uploadable"), apiTry<ReviewData>("/db/uploads/review?status=pending")]);
  if (!options && !review) redirect("/forbidden?from=/knowledge/upload");
  return (
    <>
      <PageHeader
        crumbs={[{ label: "데이터베이스", href: "/knowledge" }, { label: "자료 올리기" }]}
        title="자료 올리기"
        description="업무 자료(정형 자료의 새 버전 · 문서)를 올려 데이터베이스 반영을 요청합니다. 올리는 즉시 검사 결과를 보여 주고, 부서 데이터 책임자나 관리자가 승인하면 관련 화면 수치와 분석이 다시 계산됩니다."
      />
      <div className="shell pb-section">
        <UploadPageTabs options={options} review={review} initialTab={sp.tab === "review" ? "review" : "upload"} initialTarget={typeof sp.target === "string" ? sp.target : undefined} />
      </div>
    </>
  );
}
