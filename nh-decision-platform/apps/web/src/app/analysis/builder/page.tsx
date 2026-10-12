import { AnalysisBuilder, type Catalog, type MyAnalysis } from "@/components/analysis/AnalysisBuilder";
import { PageHeader } from "@/components/layout/PageHeader";
import { Notice } from "@/components/ui/Layout";
import { apiGet } from "@/lib/api-server";
import { API_MODE } from "@/lib/config";

export const dynamic = "force-dynamic";

interface MineDetail {
  code: string;
  versions: { version: number; status: string; sourceText?: string; spec?: Record<string, unknown> }[];
}

/** 분석 만들기 (Phase C · DAG-01~04) — 글 → 정제 → 명세 확인 · 수정 → 미리보기 → 승인 요청. 권한(analysis_builder) 없으면 권한 없음 화면 */
export default async function AnalysisBuilderPage(props: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const sp = await props.searchParams;
  const space = typeof sp.space === "string" && /^[a-z][a-z0-9_]{0,30}$/.test(sp.space) ? sp.space : undefined;
  const edit = typeof sp.edit === "string" && /^an_[a-z0-9]{1,20}$/.test(sp.edit) ? sp.edit : undefined;
  if (!API_MODE) {
    return (
      <>
        <PageHeader title="분석 만들기" />
        <div className="shell pb-section">
          <Notice tone="info" title="서버 연결 모드에서 쓸 수 있습니다">
            목업 화면에서는 분석 에이전트를 만들 수 없습니다.
          </Notice>
        </div>
      </>
    );
  }
  const [catalog, mine, detail] = await Promise.all([
    apiGet<Catalog>(`/analysis-agents/catalog${space ? `?space=${space}` : ""}`),
    apiGet<MyAnalysis[]>("/analysis-agents/mine"),
    edit ? apiGet<MineDetail>(`/analysis-agents/mine/${edit}`) : Promise.resolve(null),
  ]);
  const base = detail?.versions.find((v) => v.spec && (v.status === "approved" || v.status === "rejected")) ?? detail?.versions[0];
  const editing = detail && base?.spec ? { code: detail.code, text: base.sourceText ?? "", spec: base.spec as never } : null;
  const spaceLabel = catalog.spaces.find((s) => s.key === catalog.space)?.label ?? catalog.space;
  return (
    <>
      <PageHeader
        crumbs={[{ label: spaceLabel, href: catalog.spaces.find((s) => s.key === catalog.space)?.path }, { label: editing ? "분석 고치기" : "분석 만들기" }]}
        title={editing ? "분석 고치기 — 새 버전 요청" : "분석 만들기"}
        description="하고 싶은 분석을 글로 적으면 분석 에이전트가 데이터 · 지표 · 보고서 구성으로 정리합니다. 수치는 계산 커널이 계산하고, 관리자 승인 뒤 부서 분석 화면에 탭으로 나타나 자료가 바뀔 때마다 다시 계산됩니다."
      />
      <div className="shell pb-section">
        <AnalysisBuilder catalog={catalog} mine={mine} editing={editing} />
      </div>
    </>
  );
}
