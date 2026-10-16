import { Bone, SkelCard, SkelCardTitle, SkelChangeFeed, SkelChart, SkelNextStep, SkelRows, SkelTableHead, SkelTitleRow, SkeletonScreen } from "@/components/ui/Skeletons";
/** 신용리스크관리부 1단계 · 현황 로딩 — 모형 모니터링 지표 · 부도율 추이 · 모형 표 · 특이사항 · 변화 · 다음 단계 (RiskOverview 배치) */
export default function Loading() {
  return (
    <SkeletonScreen>
      <div className="shell flex flex-col pb-6 pt-5">
        <SkelTitleRow title="w-[194px]" />
        <div className="mt-[15px] grid grid-cols-1 items-stretch gap-4 xl:grid-cols-[1640fr_1080fr]">
          {/* 모형 모니터링 지표 */}
          <SkelCard className="flex h-[405px] flex-col" pad="px-6 pb-4 pt-5">
            <SkelCardTitle title="w-[150px]" sub="w-[180px]" right="w-[90px]" />
            <div className="-mx-2 mt-3">
              <SkelTableHead />
              <SkelRows count={5} rowClass="h-[52px] px-4" cols={["w-[20%]", "w-[14%]", "w-[14%]", "w-[14%]", "w-[10%]"]} className="mt-1.5" />
            </div>
            <Bone className="mt-auto h-3 w-[420px] max-w-full" />
          </SkelCard>
          {/* 부도율 추이 + 하단 링크 */}
          <section className="flex h-[405px] min-w-0 flex-col overflow-hidden rounded-[10px] border border-hairline-soft bg-canvas">
            <div className="flex flex-1 flex-col px-6 pb-4 pt-5">
              <SkelCardTitle title="w-[110px]" sub="w-[120px]" />
              <Bone className="mt-4 h-8 w-[120px]" />
              <SkelChart className="mt-4 flex-1" />
            </div>
            <div className="flex h-12 shrink-0 items-center border-t border-hairline-soft bg-surface-soft px-6">
              <Bone className="h-3.5 w-[260px]" />
            </div>
          </section>
        </div>
        {/* 모형별 현황 표 */}
        <SkelCard className="mt-6 h-[359px]" pad="px-6 pb-4 pt-5">
          <SkelCardTitle title="w-[150px]" sub="w-[90px]" />
          <div className="-mx-2 mt-3">
            <SkelTableHead />
            <SkelRows count={5} rowClass="h-11 px-4" cols={["w-[16%]", "w-[10%]", "w-[10%]", "w-[10%]", "w-[10%]", "w-[10%]", "w-[8%]"]} className="mt-1.5" />
          </div>
        </SkelCard>
        {/* 특이사항 칸 */}
        <SkelCard className="mt-4 h-[146px]">
          <SkelCardTitle title="w-[117px]" sub={null} />
          <ul className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-3 xl:grid-cols-4">
            {[0, 1, 2].map((i) => (
              <li key={i} className="flex h-[62px] flex-col justify-center gap-2 rounded-lg bg-page px-3.5">
                <Bone className="h-3.5 w-[160px]" />
                <Bone className="h-3 w-[110px]" />
              </li>
            ))}
          </ul>
        </SkelCard>
        <SkelChangeFeed className="mt-4" />
        <SkelNextStep className="mt-4" />
      </div>
    </SkeletonScreen>
  );
}
