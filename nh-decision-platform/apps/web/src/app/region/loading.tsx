import { Bone, SkelCard, SkelCardTitle, SkelTableHead, SkelTitleRow, SkeletonScreen } from "@/components/ui/Skeletons";
/** 영업본부 통합 업적평가 로딩 — 요약 띠 4칸 · 영업점별 표 · 평가 그룹별 득점률 (RegionOverview 배치) */
export default function Loading() {
  return (
    <SkeletonScreen>
      <div className="shell flex flex-col pb-6 pt-5">
        <SkelTitleRow title="w-[290px]" meta={false} />
        {/* 요약 띠 — 4칸 (라벨 · 큰 숫자 · 보조 줄) */}
        <SkelCard className="mt-[15px] grid h-[116px] grid-cols-1 sm:grid-cols-2 lg:grid-cols-4" pad="">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="flex flex-col px-6 pt-[19px]" aria-hidden="true">
              <Bone className="h-3 w-[90px]" />
              <Bone className="mt-[9px] h-[30px] w-[150px]" />
              <Bone className="mt-[15px] h-3 w-[140px]" />
            </div>
          ))}
        </SkelCard>
        {/* 영업점별 업적평가 — 머리줄 + 지점 줄 */}
        <SkelCard className="mt-4 h-[310px]" pad="px-[15px] pb-[17px] pt-[19px]">
          <SkelCardTitle title="w-[110px]" sub="w-[130px]" right="w-[200px]" height="h-5" className="px-2" />
          <SkelTableHead className="mt-4 !h-7" />
          <ul className="divide-y divide-track" aria-hidden="true">
            {[50, 50, 40, 40].map((h, i) => (
              <li key={i} className="flex items-center gap-x-6 pl-4" style={{ height: h }}>
                <Bone className="h-5 w-5" round="rounded-circle" />
                <Bone className="h-3.5 w-[100px]" />
                <Bone className="h-2 w-[40%]" round="rounded-pill" />
                <Bone className="ml-auto mr-6 h-3 w-[300px]" />
              </li>
            ))}
          </ul>
        </SkelCard>
        {/* 평가 그룹별 득점률 — 그룹 3개 막대 */}
        <SkelCard className="mt-4 h-[300px]" pad="px-6 pb-5 pt-[19px]">
          <SkelCardTitle title="w-[110px]" sub="w-[130px]" right="w-[200px]" height="h-5" />
          <div className="mt-[30px] flex flex-col gap-6" aria-hidden="true">
            {[0, 1, 2].map((i) => (
              <div key={i} className="flex items-center gap-x-6">
                <Bone className="h-3.5 w-[110px]" />
                <Bone className="h-2 flex-1" round="rounded-pill" />
                <Bone className="h-4 w-[56px]" />
              </div>
            ))}
          </div>
        </SkelCard>
      </div>
    </SkeletonScreen>
  );
}
