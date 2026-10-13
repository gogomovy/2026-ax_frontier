"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ErrorCard } from "@/components/ui/StateViews";
import { formatKstShort } from "@/lib/format";

/**
 * 화면 오류 경계 (B.32 · 가이드 G06) — 백엔드 지연 · 오류로 화면을 그리지 못했을 때.
 * 내부 오류 문구는 보여 주지 않고, 다시 시도(메인 버튼) + 오류 코드 · 시각만 보여 문의할 때 바로 전달할 수 있게 한다.
 */
export default function ErrorPage({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  const [at] = useState(() => formatKstShort(new Date().toISOString()));
  useEffect(() => {
    console.error(error);
  }, [error]);
  return (
    <div className="shell flex min-h-[60vh] flex-col items-center justify-center py-10">
      <ErrorCard
        className="w-full max-w-[560px]"
        title="화면을 불러오지 못했어요"
        description="서버 응답이 늦거나 오류가 발생했어요. 잠시 후 다시 시도해 주세요. 문제가 계속되면 관리자에게 아래 오류 번호를 알려주세요."
        code={error.digest}
        at={at}
        onRetry={reset}
      />
      <Link href="/" className="mt-4 text-[13px] font-bold text-primary hover:underline">
        처음 화면으로
      </Link>
    </div>
  );
}
