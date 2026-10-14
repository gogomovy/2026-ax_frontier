import { SEVERITY_TEXT, StatusDot } from "@/components/ui/primitives";
import { SeenTabLinks } from "@/components/ui/SeenTabLinks";
import { formatDate, formatDateTime } from "@/lib/format";
import { tabSeenKey, tabSignature } from "@/lib/seen";
import type { AnalysisTab } from "@/lib/types";

/**
 * 동적 탭 (요구사항 CRM-05)
 * 1화면 의견 수만큼 탭이 생기고 일 단위로 재생성된다. 이전 세대는 열람 전용으로 남긴다.
 */
export function DynamicTabBar({
  tabs,
  previous,
  activeKey,
  basePath = "/risk/analysis",
  query = "",
  lead = [],
}: {
  tabs: AnalysisTab[];
  previous: AnalysisTab[];
  activeKey: string;
  /** 탭 링크 경로 (영업점: /branch/analysis) */
  basePath?: string;
  /** 탭 링크에 이어 붙일 주소 인자 (영업점 지점 선택 `?office=` — B.47) */
  query?: string;
  /** 앞에 붙일 고정 탭 — 화면 안 탭이 있는 기존 분석(예: 종합기획부 데이터 분석)으로 돌아가는 링크 (Q109) */
  lead?: { href: string; label: string }[];
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-md no-print">
      <SeenTabLinks
        label="분석 탭"
        activeHref={`${basePath}/${activeKey}${query}`}
        items={[...lead.map((l) => ({ href: l.href, label: l.label })), ...tabs.map((tab) => ({
          href: `${basePath}/${tab.tabKey}${query}`,
          // 분석 에이전트 탭(Phase C) — 사용자가 만든 분석임을 글로도 알린다
          label: tab.dynamic ? (
            <>
              {tab.label}
              {/* 활성 탭(어두운 바탕)에서도 대비가 유지되도록 흰 바탕 배지 */}
              <span className="ml-1 rounded-sm bg-canvas px-1 text-[10px] font-bold text-primary ring-1 ring-inset ring-info-line">{tab.status === "paused" ? "중지" : "맞춤"}</span>
            </>
          ) : (
            tab.label
          ),
          // 레드닷 — 확인하지 않은 새 분석만(Phase K · DOT-01). 열면 사라지고, 다시 생성돼 내용이 바뀌면 다시 뜬다
          dot: tab.severity,
          seenKey: tabSeenKey(tab),
          signature: tabSignature(tab),
        }))]}
      />

      <div className="flex items-center gap-md text-[12px] text-stone">
        {tabs[0]?.generatedAt ? <span className="tnum">일 단위 재생성 · {formatDateTime(tabs[0].generatedAt)}</span> : null}
        {previous.length > 0 ? (
          <details className="relative">
            <summary className="cursor-pointer list-none rounded-pill border border-hairline px-3 py-1.5 text-[12px] font-bold text-charcoal">
              이전 분석 {previous.length}
            </summary>
            <div className="absolute right-0 top-[calc(100%+6px)] z-30 w-[300px] rounded-xl border border-hairline-soft bg-canvas p-1.5 shadow-pop">
              <p className="px-2.5 pb-1 pt-1.5 text-[10.5px] font-bold text-stone">이전 세대 · 열람 전용</p>
              <ul>
                {previous.map((tab) => (
                  <li key={tab.tabKey} className="flex items-start gap-2 rounded-lg px-2.5 py-2">
                    <StatusDot severity={tab.severity} className="mt-[6px]" />
                    <span className="min-w-0">
                      <span className="block text-[12.5px] font-bold text-ink">{tab.label}</span>
                      <span className="block text-[11px] text-stone">
                        {formatDate(tab.asOf)} · {SEVERITY_TEXT[tab.severity]}
                      </span>
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          </details>
        ) : null}
      </div>
    </div>
  );
}
