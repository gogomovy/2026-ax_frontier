import { Bone, SkelCard, SkelCardTitle, SkelPageHeader, SkelPanel, SkelRows, SkeletonScreen } from "@/components/ui/Skeletons";
/** 신용리스크관리부 3단계 · 수행방안 로딩 — 가이드 목록 · AI 제안 영역 (GuideWorkspace 배치) */
export default function Loading() {
  return (
    <SkeletonScreen>
      <SkelPageHeader title="w-[76px]" meta tabs={["w-[90px]", "w-[52px]"]} />
      <div className="shell flex flex-col gap-4 pb-6 pt-[9px]">
        <SkelCard className="h-[262px] overflow-hidden" pad="px-[23px] pb-1.5 pt-[19px]">
          <SkelCardTitle title="w-[110px]" sub="w-[70px]" right="w-[54px]" className="mb-4" />
          <SkelRows count={3} rowClass="h-[65px]" cols={["w-[8%]", "w-[44%]", "w-[12%]"]} className="border-t border-track" />
        </SkelCard>
        <SkelPanel className="px-4 pb-3.5 pt-5">
          <div className="flex items-center gap-3 pb-[15px] pl-2">
            <Bone className="h-[22px] w-[94px]" round="rounded-pill" tone="canvas" />
            <Bone className="h-3 w-[215px]" tone="canvas" />
          </div>
          <div className="flex h-[150px] flex-col items-center justify-center gap-2 rounded-lg bg-canvas px-4">
            <Bone className="h-4 w-[240px]" />
            <Bone className="h-3 w-[320px]" />
            <Bone className="mt-2 h-8 w-[110px]" />
          </div>
        </SkelPanel>
      </div>
    </SkeletonScreen>
  );
}
