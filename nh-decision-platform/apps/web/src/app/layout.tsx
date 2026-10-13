import type { Metadata } from "next";
import "./globals.css";
import { UiProvider } from "@/components/providers/UiProvider";
import { GoalStateProvider } from "@/components/providers/GoalStateProvider";
import { PlanStateProvider } from "@/components/providers/PlanStateProvider";
import { SessionProvider, type Bootstrap, type MenuPayload } from "@/components/providers/SessionProvider";
import { SourceDrawer } from "@/components/evidence/SourceDrawer";
import { AppShell } from "@/components/layout/AppShell";
import { Toast } from "@/components/layout/Toast";
import { apiTry, hasSession } from "@/lib/api-server";
import type { ActionPlan, CascadeNode, Goal, Term } from "@/lib/types";

export const metadata: Metadata = {
  title: "NH AI 경영 의사결정 플랫폼",
  description:
    "은행 내·외부 정보를 연결하여 경영목표의 설정과 조정을 지원하고, 그 결과를 조직 전체의 판단 기준으로 전파하는 의사결정 플랫폼",
};

/** 로그인 사용자의 메뉴·용어집·공용 상태 기준 데이터를 한 번에 받아 클라이언트에 넘긴다 */
async function loadBootstrap(): Promise<Bootstrap | null> {
  if (!(await hasSession())) return null;
  const [menu, terms, actionPlans, cascade, goals, meta] = await Promise.all([
    apiTry<MenuPayload>("/me/menu"),
    apiTry<Term[]>("/screens/terms"),
    apiTry<ActionPlan[]>("/screens/action-plans"),
    apiTry<CascadeNode[]>("/screens/cascade"),
    apiTry<Goal[]>("/screens/goals"),
    apiTry<{ generatedAt: string | null }>("/screens/meta"),
  ]);
  if (!menu) return null;
  return { menu, terms, actionPlans, cascade, goals, generatedAt: meta?.generatedAt ?? null };
}

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const boot = await loadBootstrap();
  return (
    <html lang="ko">
      <body className="min-h-screen bg-canvas antialiased">
        <SessionProvider value={boot}>
          <UiProvider>
            <GoalStateProvider>
              <PlanStateProvider>
                <a
                  href="#main"
                  className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[70] focus:rounded-lg focus:bg-ink-deep focus:px-4 focus:py-2 focus:text-[13px] focus:font-bold focus:text-white"
                >
                  본문으로 건너뛰기
                </a>
                <AppShell>{children}</AppShell>
                <SourceDrawer />
                <Toast />
              </PlanStateProvider>
            </GoalStateProvider>
          </UiProvider>
        </SessionProvider>
      </body>
    </html>
  );
}
