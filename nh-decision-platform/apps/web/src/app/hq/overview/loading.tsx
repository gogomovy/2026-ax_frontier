import { Bone, SkelCard, SkelCardTitle, SkelChart, SkelRows, SkelTableHead, SkelTitleRow, SkeletonScreen } from "@/components/ui/Skeletons";
/** 종합기획부 1단계 · 경영 현황·목표 로딩 — 상단 지표 띠 · 사업부문별 목표 표 · 선택 부문 상세 (OverviewMockup 배치) */
export default function Loading() {
  return (
    <SkeletonScreen>
      <div className="shell flex flex-col pb-6 pt-5">
        <SkelTitleRow title="w-[124px]" />
        {/* 상단 지표 띠 — 은행 종합목표(파란 칸 440px) + 지표 3칸 */}
        <section className="mt-[15px] flex h-[136px] overflow-hidden rounded-[12px] border border-hairline-soft bg-canvas">
          <div className="flex w-[440px] shrink-0 flex-col bg-info-soft px-7 pb-[17px] pt-[19px]">
            <Bone className="h-3.5 w-[260px]" tone="canvas" />
            <Bone className="mt-3 h-10 w-[150px]" tone="canvas" />
            <Bone className="mt-3 h-1.5 w-full" round="rounded-pill" tone="canvas" />
            <Bone className="mt-3 h-3 w-full" tone="canvas" />
          </div>
          {[0, 1, 2].map((i) => (
            <div key={i} className="flex min-w-0 flex-1 flex-col border-l border-hairline-soft px-6 pb-[17px] pt-[19px]">
              <div className="flex items-center justify-between">
                <Bone className="h-3.5 w-[90px]" />
                <Bone className="h-[22px] w-[60px]" round="rounded-pill" />
              </div>
              <Bone className="mt-3 h-8 w-[96px]" />
              <Bone className="mt-3 h-1.5 w-full" round="rounded-pill" />
              <Bone className="mt-3 h-3 w-full" />
            </div>
          ))}
        </section>
        <div className="mt-6 grid grid-cols-1 items-stretch gap-4 xl:grid-cols-[900fr_460fr]">
          {/* 사업부문별 목표 상태 — 머리 줄 + 7개 부문 */}
          <SkelCard className="flex h-[619px] flex-col">
            <SkelCardTitle title="w-[130px]" sub="w-[196px]" right="w-[100px]" />
            <div className="-mx-2 mt-[13px]">
              <SkelTableHead />
              <SkelRows count={7} rowClass="h-16 px-4" cols={["w-[12%]", "w-[18%]", "w-[16%]", "w-[22%]", "w-[8%]"]} className="mt-1.5" />
            </div>
            <div className="mt-auto flex items-center justify-between border-t border-hairline-soft pt-2.5">
              <Bone className="h-3 w-[310px]" />
              <Bone className="h-3 w-[230px]" />
            </div>
          </SkelCard>
          {/* 선택한 부문 — 누적 추이 · 요약 3칸 · 확인 필요 목표 */}
          <SkelCard className="flex h-[619px] flex-col">
            <div className="flex items-start justify-between">
              <div>
                <Bone className="h-3 w-[64px]" />
                <Bone className="mt-2 h-6 w-[104px]" />
              </div>
              <Bone className="mt-1.5 h-[34px] w-[83px]" />
            </div>
            <div className="mt-[25px] flex items-center justify-between">
              <Bone className="h-4 w-[176px]" />
              <Bone className="h-3 w-[130px]" />
            </div>
            <SkelChart className="mt-2 h-[145px]" />
            <div className="mt-4 grid grid-cols-3 gap-2">
              {[0, 1, 2].map((i) => (
                <div key={i} className="h-[60px] rounded-lg bg-surface-soft px-3 pt-2.5">
                  <Bone className="h-3 w-[56px]" />
                  <Bone className="mt-2 h-5 w-[64px]" />
                </div>
              ))}
            </div>
            <div className="mt-[22px] flex items-center justify-between">
              <Bone className="h-4 w-[80px]" />
              <Bone className="h-3 w-[50px]" />
            </div>
            <SkelRows count={4} rowClass="h-[50px]" cols={["w-[55%]", "w-[18%]"]} className="mt-3" />
          </SkelCard>
        </div>
      </div>
    </SkeletonScreen>
  );
}
