import { redirect } from "next/navigation";
import type { ReactNode } from "react";
import { apiTry, hasSession } from "@/lib/api-server";
import { API_MODE } from "@/lib/config";

/** 관리자 화면 — API 모드 + 관리자 역할만. 개별 API 도 서버에서 관리자 권한을 다시 검사한다. */
export default async function AdminLayout({ children }: { children: ReactNode }) {
  if (!API_MODE) {
    return (
      <div className="shell py-section">
        <h1 className="text-[22px] font-bold text-ink-deep">관리자 화면은 백엔드 연동 모드에서만 동작합니다</h1>
        <p className="mt-2 text-[13px] text-steel">
          `NEXT_PUBLIC_DATA_SOURCE=api` 로 실행하세요 (docker compose 기본값).
        </p>
      </div>
    );
  }
  const me = (await hasSession()) ? await apiTry<{ user: { role: string } }>("/me") : null;
  if (!me) redirect("/login?next=/admin");
  if (me.user.role !== "admin") redirect("/forbidden?from=/admin");
  return <>{children}</>;
}
