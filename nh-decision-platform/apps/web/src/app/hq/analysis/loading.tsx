import { Bone, SkelBars, SkelCard, SkelNextStep, SkelPageHeader, SkelPanel, SkelRows, SkelStat, SkelTableHead, SkeletonScreen } from "@/components/ui/Skeletons";
/** 종합기획부 2단계 · 데이터 분석 로딩 — AI 요약 영역 · 비교 표 + 차트 · 다음 단계 (AnalysisWorkspace 배치) */
export default function Loading() {
  return (
    <SkeletonScreen>
      <SkelPageHeader title="w-[173px]" tabs={["w-[110px]", "w-[120px]", "w-[110px]"]} />
      <div className="shell flex flex-col gap-6 pb-6">
        {/* AI 요약 — 태그 + 흰 카드(지표 3칸 · 설명 2줄) */}
        <SkelPanel className="flex flex-col gap-3 p-4">
          <div className="flex h-6 items-center justify-between">
            <Bone className="h-[23px] w-[85px]" round="rounded-pill" tone="canvas" />
            <Bone className="h-6 w-[92px]" tone="canvas" />
          </div>
          <div className="flex h-[207px] flex-col gap-4 rounded-lg bg-canvas px-6 pb-5 pt-[22px]">
            <div className="grid grid-cols-1 gap-y-4 md:grid-cols-[421fr_446fr_446fr]">
              <SkelStat value="w-[140px]" />
              <SkelStat value="w-[140px]" />
              <SkelStat value="w-[140px]" />
            </div>
            <div className="mt-auto space-y-2.5">
              <Bone className="h-3.5 w-4/5" />
              <Bone className="h-3.5 w-3/5" />
            </div>
          </div>
        </SkelPanel>
        {/* 비교 표 + 차트 */}
        <section className="grid grid-cols-1 gap-4 xl:grid-cols-[856fr_520fr]">
          <SkelCard className="flex h-[338px] flex-col gap-3" pad="px-6 pb-[22px] pt-6">
            <Bone className="h-6 w-[220px]" />
            <SkelTableHead />
            <SkelRows count={4} rowClass="h-11 px-4" cols={["w-[16%]", "w-[14%]", "w-[14%]", "w-[14%]", "w-[14%]"]} />
            <Bone className="mt-auto h-3 w-[300px]" />
          </SkelCard>
          <SkelCard className="flex h-[338px] flex-col" pad="px-6 pb-[22px] pt-6">
            <div className="flex items-start justify-between">
              <div>
                <Bone className="h-5 w-[160px]" />
                <Bone className="mt-2 h-3 w-[200px]" />
              </div>
              <Bone className="h-3 w-[90px]" />
            </div>
            <SkelBars className="mt-4 min-h-0 flex-1" count={8} />
          </SkelCard>
        </section>
        <SkelNextStep />
      </div>
    </SkeletonScreen>
  );
}
