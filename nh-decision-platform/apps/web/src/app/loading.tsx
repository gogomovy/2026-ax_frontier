import { LoadingCard } from "@/components/ui/StateViews";

/** 화면 데이터 대기 (B.32 · 가이드 G06) — 실제 레이아웃과 같은 자리에 회색 블록을 먼저 그려, 불러온 뒤 화면이 흔들리지 않게 한다 */
export default function Loading() {
  return (
    <div className="shell py-8">
      <div className="skeleton mb-6 h-8 w-56" aria-hidden="true" />
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <LoadingCard label="데이터를 불러오는 중이에요" />
        <LoadingCard label="데이터를 불러오는 중이에요" className="hidden lg:block" />
        <LoadingCard label="데이터를 불러오는 중이에요" className="hidden lg:block" />
      </div>
    </div>
  );
}
