import { redirect } from "next/navigation";
import type { ReactNode } from "react";
import { apiTry, hasSession } from "@/lib/api-server";

/** 관리자 화면 — 관리자 역할만. 개별 API 도 서버에서 관리자 권한을 다시 검사한다. */
export default async function AdminLayout({ children }: { children: ReactNode }) {
  const me = (await hasSession()) ? await apiTry<{ user: { role: string } }>("/me") : null;
  if (!me) redirect("/login?next=/admin");
  if (me.user.role !== "admin") redirect("/forbidden?from=/admin");
  return <>{children}</>;
}
