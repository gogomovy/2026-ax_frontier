import Link from "next/link";
import { apiTry, hasSession } from "@/lib/api-server";

export const dynamic = "force-dynamic";

interface ScreenInfo {
  screen: { code: string; label: string; section: string; admin: boolean } | null;
  granted?: boolean;
  home?: string;
}

/**
 * 화면 권한 없음 (요구사항 AUTH-08 → Phase E · NAV-03) — 어느 화면인지(?from=) · 누구에게 어떻게 요청하는지 알린다.
 * 권한은 관리자 화면의 [화면 권한]에서 조직 단위로 부여한다.
 */
export default async function ForbiddenPage(props: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const sp = await props.searchParams;
  const raw = typeof sp.from === "string" ? sp.from : "";
  // 내부 주소만(외부 주소 · 스킴 차단)
  const from = raw.startsWith("/") && !raw.startsWith("//") ? raw.slice(0, 200) : "";
  const info = from && (await hasSession()) ? await apiTry<ScreenInfo>(`/me/screen?path=${encodeURIComponent(from)}`) : null;
  const sc = info?.screen ?? null;
  const home = info?.home ?? "/";

  return (
    <div className="shell flex min-h-screen flex-col items-center justify-center gap-2 text-center">
      <p className="text-[12px] font-bold text-stone">403</p>
      <h1 className="text-[24px] font-bold text-ink-deep">{sc ? `[${sc.label}] 화면에 대한 권한이 없습니다` : "이 화면에 대한 권한이 없습니다"}</h1>
      {sc ? (
        <p className="text-[12.5px] text-steel" data-forbidden-screen={sc.code}>
          메뉴 위치: {sc.admin ? "관리자" : "업무"} › {sc.section} › {sc.label}
        </p>
      ) : null}
      <div className="mt-xs max-w-[480px] text-[13.5px] leading-relaxed text-steel">
        {sc?.admin ? (
          <p>관리자 전용 화면입니다. 관리자 계정으로 로그인하세요.</p>
        ) : (
          <>
            <p>화면 권한은 소속 조직(상위 부·국 포함) 기준으로 부여됩니다.</p>
            <p className="mt-1">
              필요하면 소속 부서장이나 관리자에게 {sc ? <strong className="font-bold text-ink-deep">‘{sc.section} › {sc.label}’</strong> : "이 화면의"} 권한을 요청하세요. 관리자는 [관리자 › 사용자와 권한 › 화면 권한]에서 조직 단위로 부여합니다.
            </p>
          </>
        )}
      </div>
      <div className="mt-lg flex flex-wrap justify-center gap-xs">
        <Link href={home} className="rounded-pill bg-ink-button px-6 py-2.5 text-[13px] font-bold text-white">
          내 첫 화면으로
        </Link>
        <Link href={from ? `/login?next=${encodeURIComponent(from)}` : "/login"} className="rounded-pill border-2 border-line-strong px-6 py-2.5 text-[13px] font-bold text-ink-deep">
          다른 계정으로 로그인
        </Link>
      </div>
    </div>
  );
}
