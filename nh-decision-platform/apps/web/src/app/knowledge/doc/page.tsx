import { notFound } from "next/navigation";
import { DocViewer, DocViewerActions } from "@/components/evidence/DocViewer";
import { PageHeader } from "@/components/layout/PageHeader";
import { getDocumentView } from "@/lib/data";
import { DB_CLASS_LABEL, formatDate } from "@/lib/format";

// 문서 · 인용 위치가 요청마다 다르므로 요청 시 렌더링한다
export const dynamic = "force-dynamic";

/** 목록 화면이 있는 문서 분류 (`/knowledge/[dbClass]`) */
const CLASS_PAGES = ["gov_policy", "mgmt_decision", "model_method", "branch_ref"];

type Search = { id?: string; file?: string; title?: string; page?: string; q?: string };

/** 원본 문서 뷰어 (F.12 · DB-07) — 근거 드로어의 '원본 열기' · 데이터베이스 문서 목록에서 연다 */
export default async function DocumentViewerPage(props: { searchParams: Promise<Search> }) {
  const sp = await props.searchParams;
  const page = sp.page && /^\d{1,5}$/.test(sp.page) ? Number(sp.page) : undefined;
  if (!sp.id && !sp.file && !sp.title) notFound();
  const view = await getDocumentView({ id: sp.id, file: sp.file, title: sp.title, page, q: sp.q?.slice(0, 1000) });

  if (!view) {
    return (
      <>
        <PageHeader crumbs={[{ label: "데이터베이스", href: "/knowledge" }, { label: "원본 문서" }]} title="원본 문서 뷰어" />
        <div className="shell">
          <p className="panel px-xl py-lg text-[13px] text-steel">
            문서를 찾지 못했습니다. 문서가 아직 올라오지 않았거나 열람 권한 밖일 수 있습니다.
          </p>
        </div>
      </>
    );
  }

  const classLabel = DB_CLASS_LABEL[view.dbClass as keyof typeof DB_CLASS_LABEL] ?? view.dbClass;
  return (
    <>
      <PageHeader
        crumbs={[
          { label: "데이터베이스", href: "/knowledge" },
          { label: classLabel, href: CLASS_PAGES.includes(view.dbClass) ? `/knowledge/${view.dbClass}` : undefined },
          { label: "원본 문서" },
        ]}
        title={view.title}
        description={[
          view.issuer,
          view.effectiveDate ? `기준일 ${formatDate(view.effectiveDate)}` : null,
          `v${view.version}`,
          view.origin === "ext" ? "외부 자료" : "당행 자료",
          view.fileName,
        ]
          .filter(Boolean)
          .join(" · ")}
        actions={<DocViewerActions view={view} />}
      />
      <div className="shell">
        {view.source === "excerpt" ? (
          <p className="mb-base text-[12px] text-steel">
            원본 파일이 아직 등록되지 않아, 분석 근거로 인용된 면의 발췌만 보여줍니다. 관리자 화면 [데이터셋·문서]에서 원본을 올리면 전체 면이 표시됩니다.
          </p>
        ) : null}
        {view.pages.length === 0 ? (
          <p className="panel px-xl py-lg text-[13px] text-steel">표시할 본문이 없습니다.</p>
        ) : (
          <DocViewer view={view} />
        )}
      </div>
    </>
  );
}
