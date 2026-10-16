import { Bone, SkelCard, SkelCardTitle, SkelChangeFeed, SkelNextStep, SkelProgressList, SkelTitleRow, SkeletonScreen } from "@/components/ui/Skeletons";
/** 영업점 1단계 · 현황 로딩 — 업적평가 총득점 · 가점 확보 방안 · KPI별 득점 · 사업부문 · 변화 · 다음 단계 (BranchOverview 배치) */
export default function Loading() {
  return (
    <SkeletonScreen>
      <div className="shell flex flex-col pb-6 pt-5">
        <SkelTitleRow title="w-[156px]" />
        {/* 업적평가 총득점 — 큰 숫자 · AI 반영 시 · 진행 막대 */}
        <SkelCard className="mt-[15px] h-[153px]" pad="px-6 pb-6 pt-[19px]">
          <SkelCardTitle title="w-[176px]" sub="w-[150px]" height="h-5" />
          <div className="mt-2.5 flex h-[51px] items-end gap-x-[22px]">
            <Bone className="h-[42px] w-[206px]" />
            <Bone className="h-[38px] w-[162px]" />
          </div>
          <Bone className="mt-5 h-2 w-full" round="rounded-pill" />
        </SkelCard>
        {/* 가점 확보 방안 — 가이드 2칸 */}
        <SkelCard className="mt-4" pad="px-6 pb-6 pt-[19px]">
          <SkelCardTitle title="w-[80px]" sub="w-[210px]" height="h-5" />
          <ul className="mt-3.5 grid grid-cols-1 gap-3 lg:grid-cols-2">
            {[0, 1].map((i) => (
              <li key={i} className="flex h-[186px] min-w-0 flex-col rounded-[8px] bg-page px-[18px] pb-4 pt-[15px]">
                <div className="flex items-center justify-between">
                  <Bone className="h-6 w-[360px] max-w-[80%]" />
                  <Bone className="h-3 w-[56px]" />
                </div>
                <Bone className="mt-3 h-3 w-11/12" />
                <div className="mt-6 flex items-center justify-between">
                  <Bone className="h-3 w-[140px]" />
                  <Bone className="h-3 w-[50px]" />
                </div>
                <Bone className="mt-2 h-2 w-full" round="rounded-pill" />
                <Bone className="mt-3 h-3 w-[150px]" />
                <Bone className="mt-auto h-3 w-[56px]" />
              </li>
            ))}
          </ul>
        </SkelCard>
        {/* KPI별 득점 — 좌우 2열 */}
        <SkelCard className="mt-4 h-[550px]" pad="px-6 pb-[15px] pt-[19px]">
          <SkelCardTitle title="w-[60px]" sub="w-[70px]" right="w-[100px]" height="h-5" />
          <div className="mt-[18px] grid h-[432px] grid-cols-1 gap-y-8 lg:grid-cols-[1fr_1px_1fr] lg:gap-x-6">
            <SkelProgressList count={9} rowClass="py-[11px]" />
            <div className="hidden bg-hairline-soft lg:block" />
            <SkelProgressList count={6} rowClass="py-[13px]" />
          </div>
        </SkelCard>
        {/* 사업부문 — 부문 5칸 + 지표 4칸 */}
        <SkelCard className="mt-4 h-[250px]" pad="px-6 pb-6 pt-[19px]">
          <SkelCardTitle title="w-[50px]" sub="w-[260px]" right="w-[81px]" height="h-5" />
          <div className="mt-3.5 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
            {[0, 1, 2, 3, 4].map((i) => (
              <div key={i} className="flex h-[58px] flex-col justify-center gap-2 rounded-[8px] border-[1.5px] border-hairline-soft px-[15px]">
                <Bone className="h-3.5 w-[40px]" />
                <Bone className="h-3 w-[110px]" />
              </div>
            ))}
          </div>
          <div className="mt-[9px] grid h-[104px] grid-cols-1 rounded-[8px] bg-surface-soft sm:grid-cols-2 xl:grid-cols-4">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="flex flex-col gap-2 px-5 py-4">
                <Bone className="h-3 w-[110px]" />
                <Bone className="h-7 w-[130px]" />
                <Bone className="h-3 w-[90px]" />
              </div>
            ))}
          </div>
        </SkelCard>
        <SkelChangeFeed className="mt-4" dense />
        <SkelNextStep className="mt-4" />
      </div>
    </SkeletonScreen>
  );
}
