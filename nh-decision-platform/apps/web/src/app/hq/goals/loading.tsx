import { Bone, SkelCard, SkelCardTitle, SkelPageHeader, SkelPanel, SkelRows, SkeletonScreen } from "@/components/ui/Skeletons";
/** 종합기획부 3단계 · 경영목표 설정 로딩 — 목표 목록 · AI 신규 목표 제안 · 요청 · 이력 (GoalsWorkspace 배치) */
export default function Loading() {
  return (
    <SkeletonScreen>
      <SkelPageHeader title="w-[192px]" tabs={["w-[78px]", "w-[52px]"]} />
      <div className="shell flex flex-col gap-6 pb-6">
        {/* 목표 목록 — 머리 줄 + 목표 6줄 + 추가 버튼 */}
        <SkelCard pad="px-6 pb-4 pt-6">
          <div className="flex h-12 items-center justify-between gap-x-6 pb-3 pt-[13px]">
            <Bone className="h-[18px] w-[260px]" />
            <Bone className="h-3.5 w-[420px] max-w-[40%]" />
          </div>
          <SkelRows count={6} rowClass="h-[88px]" cols={["w-[38%]", "w-[6%]", "w-[34%]"]} className="border-y border-hairline-soft" />
          <div className="pt-3">
            <Bone className="h-10 w-full" round="rounded-lg" />
          </div>
        </SkelCard>
        {/* AI 신규 목표 제안 */}
        <SkelPanel className="flex flex-col gap-3 p-4">
          <div className="flex items-center gap-2">
            <Bone className="h-[23px] w-[127px]" round="rounded-pill" tone="canvas" />
            <Bone className="h-3 w-[120px]" tone="canvas" />
          </div>
          <div className="flex h-[125px] flex-col gap-3 rounded-lg bg-canvas py-4 pl-5 pr-4">
            <Bone className="h-4 w-[280px]" />
            <Bone className="h-3.5 w-3/5" />
            <Bone className="h-3.5 w-2/5" />
          </div>
        </SkelPanel>
        {/* 요청 목록 */}
        <SkelCard pad="px-6 pb-3 pt-[22px]">
          <SkelCardTitle title="w-[60px]" sub="w-[168px]" />
          <div className="mt-2 h-[86px] border-t border-hairline-soft" />
        </SkelCard>
        {/* 변경 이력 (접힘) */}
        <section className="flex h-[55px] items-center justify-between rounded-[10px] border border-hairline-soft bg-canvas px-6">
          <Bone className="h-4 w-[120px]" />
          <Bone className="h-3 w-[135px]" />
        </section>
        {/* 안내 (점선 카드) */}
        <section className="flex h-[79px] flex-col justify-center gap-2 rounded-[10px] border border-dashed border-hairline pl-6 pr-[18px]">
          <Bone className="h-4 w-[200px]" />
          <Bone className="h-3 w-[420px] max-w-full" />
        </section>
      </div>
    </SkeletonScreen>
  );
}
