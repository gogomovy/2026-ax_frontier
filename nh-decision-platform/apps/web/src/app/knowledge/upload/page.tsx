import { UploadWorkspace, type Uploadable } from "@/components/knowledge/UploadWorkspace";
import { PageHeader } from "@/components/layout/PageHeader";
import { Notice } from "@/components/ui/Layout";
import { apiGet } from "@/lib/api-server";
import { API_MODE } from "@/lib/config";

export const dynamic = "force-dynamic";

/** 업무 자료 올리기 (Phase C · UPL-01~03) — 올리기 → 검사 → 승인 요청, 내 요청 상태. 권한(db_upload) 없으면 권한 없음 화면 */
export default async function KnowledgeUploadPage() {
  const options = API_MODE ? await apiGet<Uploadable>("/db/uploadable") : null;
  return (
    <>
      <PageHeader
        crumbs={[{ label: "데이터베이스", href: "/knowledge" }, { label: "자료 올리기" }]}
        title="자료 올리기"
        description="업무 자료(정형 자료의 새 버전 · 문서)를 올려 데이터베이스 반영을 요청합니다. 올리는 즉시 검사 결과를 보여 주고, 관리자가 승인하면 관련 화면 수치와 분석이 다시 계산됩니다."
      />
      <div className="shell pb-section">
        {options ? (
          <UploadWorkspace initial={options} />
        ) : (
          <Notice tone="info" title="서버 연결 모드에서 쓸 수 있습니다">
            목업 화면에서는 자료를 올릴 수 없습니다.
          </Notice>
        )}
      </div>
    </>
  );
}
