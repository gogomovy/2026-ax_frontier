import { Bone, SkelCard, SkelCardTitle, SkelOpinionPanel, SkelRows, SkelTabs, SkeletonScreen } from "@/components/ui/Skeletons";
/** 종합기획부 2단계 · 맞춤 분석 탭 로딩 — 머리말(단계 · 제목 · 설명) · 탭 · 목차 + 보고서 본문 (AnalysisReportPage 배치) */
export default function Loading() {
  return (
    <SkeletonScreen>
      <div className="shell pb-5 pt-8">
        <div className="flex items-center justify-between gap-x-6">
          <div>
            <Bone className="h-3 w-[180px]" />
            <Bone className="mt-2 h-[28px] w-[260px]" />
            <Bone className="mt-2 h-3.5 w-[480px] max-w-full" />
          </div>
          <div className="flex items-center gap-x-6">
            <Bone className="h-4 w-[110px]" />
            <Bone className="h-4 w-[90px]" />
          </div>
        </div>
        <SkelTabs widths={["w-[110px]", "w-[150px]", "w-[130px]"]} className="mt-5" />
      </div>
      <div className="shell grid grid-cols-1 gap-xxl lg:grid-cols-[200px_minmax(0,1fr)]">
        {/* 목차 */}
        <div className="hidden space-y-3 lg:block">
          {[120, 150, 110, 140, 100].map((w) => (
            <Bone key={w} className="h-3.5" style={{ width: w }} />
          ))}
        </div>
        <div className="flex min-w-0 flex-col gap-4">
          <SkelOpinionPanel tiles={3} />
          <SkelCard>
            <SkelCardTitle />
            <div className="mt-4 space-y-2.5">
              <Bone className="h-3.5 w-full" />
              <Bone className="h-3.5 w-11/12" />
              <Bone className="h-3.5 w-4/5" />
            </div>
            <SkelRows count={4} rowClass="h-11" className="mt-5 border-t border-hairline-soft" />
          </SkelCard>
        </div>
      </div>
    </SkeletonScreen>
  );
}
