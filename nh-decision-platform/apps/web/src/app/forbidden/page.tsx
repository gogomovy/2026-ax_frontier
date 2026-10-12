import Link from "next/link";

/** 화면 권한 없음 (요구사항 AUTH-08) — 권한은 관리자 화면의 [화면 권한]에서 조직 단위로 부여한다 */
export default function ForbiddenPage() {
  return (
    <div className="shell flex min-h-screen flex-col items-center justify-center gap-2 text-center">
      <p className="text-[12px] font-bold text-stone">403</p>
      <h1 className="text-[24px] font-bold text-ink-deep">이 화면에 대한 권한이 없습니다</h1>
      <p className="max-w-[440px] text-[13.5px] leading-relaxed text-steel">
        화면 권한은 소속 조직(상위 부·국 포함) 기준으로 부여됩니다. 필요하면 관리자에게 권한을 요청하세요.
      </p>
      <div className="mt-lg flex flex-wrap justify-center gap-xs">
        <Link href="/" className="rounded-pill bg-ink-button px-6 py-2.5 text-[13px] font-bold text-white">
          내 첫 화면으로
        </Link>
        <Link href="/login" className="rounded-pill border-2 border-line-strong px-6 py-2.5 text-[13px] font-bold text-ink-deep">
          다른 계정으로 로그인
        </Link>
      </div>
    </div>
  );
}
