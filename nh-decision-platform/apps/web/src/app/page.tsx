import { redirect } from "next/navigation";
import { apiTry, hasSession } from "@/lib/api-server";

/** 진입 화면 — 사용자 권한의 첫 화면(로그인 전이면 로그인) */
export default async function RootPage() {
  const me = (await hasSession()) ? await apiTry<{ home: string }>("/me") : null;
  redirect(me?.home ?? "/login");
}
