import { RegionOverview } from "@/components/domain/RegionOverview";
import { RegionPicker } from "@/components/domain/RegionPicker";
import { AsOfTools, ExportButton } from "@/components/layout/PageTools";
import { RowEmpty } from "@/components/ui/primitives";
import { getRegionKpi } from "@/lib/data";
import { regionParam, withRegionDerived } from "@/lib/regionView";

// 지역본부 소속 · 고른 지역에 따라 달라지고 영업점 흐름이 갱신하므로 요청 시 렌더링한다
export const dynamic = "force-dynamic";

/** 영업본부 STEP 1 — 지역본부 아래 영업점 업적평가 통합 (§37 RGN · Figma 386:2). 지점 점수 · 순위 · 평균은 화면 API 값 그대로 */
export default async function RegionKpiPage(props: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  // 화면 보조 값(그룹 평균 득점률 · 상향 평균 · 향상 기회 수)은 API 가 주지 않으면 받은 지점 값에서 센다 — 순위 · 점수는 그대로
  const data = withRegionDerived(await getRegionKpi(regionParam(await props.searchParams)));
  return (
    <div className="shell flex flex-col pb-6 pt-5">
      {/* 제목 줄 — 다른 1단계 화면과 같은 22px 제목 · 기준월 선택 · 내보내기 */}
      <header className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3">
        <h1 className="flex min-w-0 flex-wrap items-center gap-x-2.5 text-[22px] font-bold leading-[1.25] text-ink-deep">
          <RegionPicker data={data} />
          <span>영업점 업적평가</span>
        </h1>
        <AsOfTools key="page-tools">
          <ExportButton />
        </AsOfTools>
      </header>
      {data.region ? (
        <RegionOverview data={data} />
      ) : (
        <div className="mt-[15px]">
          <RowEmpty title="지역본부가 없습니다" description="관리자 [조직]에서 지역본부(REGION)를 만들고 영업점을 그 아래에 두면 여기에 보입니다." />
        </div>
      )}
    </div>
  );
}
