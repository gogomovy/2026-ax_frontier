import Link from "next/link";
import type { ReactNode } from "react";
import { DynamicTabBar } from "@/components/domain/DynamicTabBar";
import { ReportActions, ReportView } from "@/components/domain/ReportView";
import { PageHeader } from "@/components/layout/PageHeader";
import { Notice } from "@/components/ui/Layout";
import type { AnalysisTab, ReportDoc } from "@/lib/types";

/**
 * 부서 분석 보고서 화면 (Phase C · DAG-06 · DAG-07 · Q101 · Q102)
 * 기존 분석(신용리스크 · 영업점)과 분석 에이전트 보고서가 같은 표시 단계를 쓴다:
 * 위치 · 제목 · 동작(내려받기 · 다시 실행) → 분석 탭 → 의견 → 목차 · 본문 → 다음 할 일.
 */
export function AnalysisReportPage({
  eyebrow,
  crumbs,
  report,
  tabs,
  previous,
  activeKey,
  basePath,
  query = "",
  exportKey,
  office,
  builderHref,
  next,
}: {
  eyebrow?: string;
  crumbs?: { label: string; href?: string }[];
  report: ReportDoc;
  tabs: AnalysisTab[];
  previous: AnalysisTab[];
  activeKey: string;
  basePath: string;
  query?: string;
  /** 내려받기 키 (영업점: branch-<탭>) */
  exportKey?: string;
  office?: string | null;
  /** 분석 만들기 (권한 있을 때만) */
  builderHref?: string | null;
  next?: ReactNode;
}) {
  const agent = report.analysisAgent;
  return (
    <>
      <PageHeader
        crumbs={crumbs}
        eyebrow={eyebrow}
        title={report.title}
        description={report.subtitle}
        actions={
          <>
            {builderHref ? (
              <Link href={builderHref} className="inline-flex h-9 items-center rounded-pill border border-hairline px-4 text-[13px] font-bold text-ink" data-builder-link>
                분석 만들기
              </Link>
            ) : null}
            <ReportActions report={report} tabKey={exportKey ?? activeKey} office={office ?? undefined} />
          </>
        }
      >
        <DynamicTabBar tabs={tabs} previous={previous} activeKey={activeKey} basePath={basePath} query={query} />
      </PageHeader>

      {agent && agent.status === "paused" ? (
        <div className="shell mb-lg">
          <Notice tone="attention" title="일시 중지된 분석입니다">
            관리자가 이 분석을 일시 중지했습니다. 마지막 결과를 보여 주며 자료가 바뀌어도 다시 계산하지 않습니다.
          </Notice>
        </div>
      ) : null}

      <ReportView report={report} />

      {next ? <div className="shell mt-section">{next}</div> : null}
    </>
  );
}
