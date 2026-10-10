import Link from "next/link";
import { IconArrowRight, SEVERITY_TEXT, StatusDot } from "@/components/ui/primitives";
import type { AnalysisTab, Insight } from "@/lib/types";

/**
 * 분석 결과 알림 (요구사항 CRM-04)
 * 1화면에는 요약만 두고, 항목을 누르면 2화면의 해당 분석 탭으로 바로 이동한다.
 */
export function AnalysisAlertStrip({
  opinions,
  tabs,
  generatedAt,
}: {
  opinions: Insight[];
  tabs: AnalysisTab[];
  generatedAt: string;
}) {
  if (opinions.length === 0) return null;

  const tabOf = (insight: Insight) =>
    insight.tabKey ?? tabs.find((t) => t.insightId === insight.id)?.tabKey ?? tabs[0]?.tabKey;

  return (
    <section
      aria-label="새 분석 결과"
      className="overflow-hidden rounded-2xl border border-[rgba(0,100,224,0.22)] bg-[rgba(0,100,224,0.04)]"
    >
      <div className="flex flex-wrap items-baseline gap-x-md gap-y-1 px-lg pt-base">
        <p className="text-[14px] font-bold text-ink-deep">새 분석 결과 {opinions.length}건</p>
        <p className="text-[12px] text-steel">오늘 {generatedAt.slice(11, 16)} 일배치 · 선택하면 해당 분석으로 이동합니다</p>
      </div>
      <ul className="mt-2 divide-y divide-[rgba(0,100,224,0.12)] border-t border-[rgba(0,100,224,0.12)]">
        {opinions.map((insight) => {
          const tabKey = tabOf(insight);
          return (
            <li key={insight.id}>
              <Link
                href={tabKey ? `/risk/analysis/${tabKey}` : "/risk"}
                className="row-button flex items-center gap-md px-lg py-3"
              >
                <StatusDot severity={insight.severity} />
                <span className="w-9 shrink-0 text-[11.5px] font-bold text-steel">{SEVERITY_TEXT[insight.severity]}</span>
                <span className="min-w-0 flex-1 truncate text-[13.5px] font-bold text-ink-deep">{insight.title}</span>
                <span className="inline-flex shrink-0 items-center gap-1 text-[12.5px] font-bold text-primary">
                  열기 <IconArrowRight />
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
