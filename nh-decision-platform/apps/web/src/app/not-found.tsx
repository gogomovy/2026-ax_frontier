import Link from "next/link";

/** 존재하지 않는 경로 */
export default function NotFound() {
  return (
    <div className="shell flex min-h-[60vh] flex-col items-center justify-center gap-2 text-center">
      <p className="text-[12px] font-bold text-stone">404</p>
      <h1 className="text-[24px] font-bold text-ink-deep">찾는 화면이 없습니다</h1>
      <p className="max-w-[420px] text-[13.5px] leading-relaxed text-steel">
        주소가 바뀌었거나 일 단위로 재생성되는 분석 탭이 교체되었을 수 있습니다. 이전 분석은 분석 결과 화면의 `이전 분석`에서 볼 수 있습니다.
      </p>
      <div className="mt-lg flex flex-wrap justify-center gap-xs">
        <Link href="/" className="rounded-pill bg-ink-button px-6 py-2.5 text-[13px] font-bold text-white">
          처음 화면으로
        </Link>
        <Link
          href="/risk/analysis"
          className="rounded-pill border-2 border-line-strong px-6 py-2.5 text-[13px] font-bold text-ink-deep"
        >
          분석 결과
        </Link>
      </div>
    </div>
  );
}
