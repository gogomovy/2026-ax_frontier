import { redirect } from "next/navigation";
import { apiTry, hasSession } from "@/lib/api-server";
import { API_MODE } from "@/lib/config";

/** 진입 화면 — API 모드는 사용자 권한의 첫 화면, 목데이터 모드는 종합기획부 STEP 1 */
export default async function RootPage() {
  if (API_MODE) {
    const me = (await hasSession()) ? await apiTry<{ home: string }>("/me") : null;
    redirect(me?.home ?? "/login");
  }
  redirect("/hq/overview");
}
