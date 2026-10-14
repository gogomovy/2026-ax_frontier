import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState } from "@/components/ui/Layout";
import { getSpaceTabs } from "@/lib/data";

export const dynamic = "force-dynamic";

/** 부서 분석 공간 (Phase C · DAG-07) — 첫 분석으로 이동, 분석이 없으면 만들기 안내 */
export default async function AnalysisSpacePage(props: { params: Promise<{ space: string }> }) {
  const { space } = await props.params;
  const tabs = await getSpaceTabs(space);
  if (!tabs) notFound();
  // 기존 경로가 있는 공간(신용리스크 · 영업점)은 그 화면으로
  if (tabs.space.path && tabs.space.path !== `/analysis/${space}`) redirect(tabs.space.path);
  if (tabs.current.length) redirect(`/analysis/${space}/${tabs.current[0].tabKey}`);
  return (
    <>
      <PageHeader crumbs={[{ label: tabs.space.label }, { label: "분석 보고서" }]} title={`${tabs.space.label} 분석 보고서`} description="부서에서 만든 분석이 관리자 승인 후 이곳에 탭으로 나타납니다. 자료가 바뀌거나 정해진 주기가 되면 다시 계산됩니다." />
      <div className="shell pb-section">
        <EmptyState
          title="아직 분석이 없습니다"
          description="하고 싶은 분석을 글로 적으면 분석 에이전트가 데이터 · 지표 · 보고서 구성으로 정리합니다. 미리보기로 결과를 확인한 뒤 관리자에게 승인을 요청하세요."
          action={
            tabs.builder.allowed ? (
              <Link href={`/analysis/builder?space=${encodeURIComponent(space)}`} className="inline-flex h-10 items-center rounded-pill bg-ink-button px-5 text-[13.5px] font-bold text-on-ink-button" data-builder-link>
                분석 에이전트 만들기
              </Link>
            ) : (
              <p className="text-[12px] text-stone">분석 에이전트 만들기 권한은 관리자에게 요청하세요.</p>
            )
          }
        />
      </div>
    </>
  );
}
