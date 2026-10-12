"use client";

import Link from "next/link";
import { useEffect } from "react";

/** 화면 오류 경계 (B.32) — 백엔드 지연 · 오류로 화면을 그리지 못했을 때. 내부 오류 문구는 보여 주지 않고 추적용 digest 만 */
export default function ErrorPage({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);
  return (
    <div role="alert" className="shell flex min-h-[60vh] flex-col items-center justify-center gap-2 text-center">
      <p className="text-[12px] font-bold text-stone">일시적인 오류</p>
      <h1 className="text-[24px] font-bold text-ink-deep">화면을 불러오지 못했습니다</h1>
      <p className="max-w-[440px] text-[13.5px] leading-relaxed text-steel">
        서버 응답이 늦거나 오류가 발생했습니다. 잠시 후 다시 시도해 주세요. 계속되면 관리자에게 아래 오류 번호를 알려 주세요.
      </p>
      {error.digest ? <p className="font-mono text-[11.5px] text-stone">오류 번호 {error.digest}</p> : null}
      <div className="mt-lg flex flex-wrap justify-center gap-xs">
        <button type="button" onClick={reset} className="rounded-pill bg-ink-button px-6 py-2.5 text-[13px] font-bold text-white">
          다시 시도
        </button>
        <Link href="/" className="rounded-pill border-2 border-line-strong px-6 py-2.5 text-[13px] font-bold text-ink-deep">
          처음 화면으로
        </Link>
      </div>
    </div>
  );
}
