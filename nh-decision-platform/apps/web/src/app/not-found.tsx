import Link from "next/link";

/** 존재하지 않는 경로 — 모든 사용자가 갈 수 있는 '내 첫 화면'(/ → 역할별 첫 화면)으로 안내 (Phase E · NAV-03) */
export default function NotFound() {
  return (
    <div className="shell flex min-h-[60vh] flex-col items-center justify-center gap-2 text-center">
      <p className="text-[12px] font-bold text-stone">404</p>
      <h1 className="text-[24px] font-bold text-ink-deep">찾는 화면이 없습니다</h1>
      <p className="max-w-[420px] text-[13.5px] leading-relaxed text-steel">
        주소가 바뀌었거나 일 단위로 다시 만드는 분석 탭이 교체되었을 수 있습니다. 이전 분석은 각 분석 화면의 ‘이전 분석’에서 볼 수 있습니다.
      </p>
      <div className="mt-lg flex flex-wrap justify-center gap-xs">
        <Link href="/" className="rounded-pill bg-ink-button px-6 py-2.5 text-[13px] font-bold text-white">
          내 첫 화면으로
        </Link>
        <Link href="/knowledge" className="rounded-pill border-2 border-line-strong px-6 py-2.5 text-[13px] font-bold text-ink-deep">
          데이터베이스
        </Link>
      </div>
    </div>
  );
}
