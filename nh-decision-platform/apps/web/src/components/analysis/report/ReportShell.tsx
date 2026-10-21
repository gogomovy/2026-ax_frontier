import type { ReactNode } from "react";
import { ReportDownload } from "@/components/analysis/report/kit";
import { OnDemandAnalysis } from "@/components/agent/AgentProgress";
import { RefreshStatus } from "@/components/agent/RefreshStatus";
import { Block, ReportView } from "@/components/domain/ReportView";
import { PageHeader } from "@/components/layout/PageHeader";
import { AsOfTools } from "@/components/layout/PageTools";
import { Notice } from "@/components/ui/Layout";
import { AddAgentTab, SEVERITY_TEXT, StatusDot } from "@/components/ui/primitives";
import { SeenTabLinks } from "@/components/ui/SeenTabLinks";
import { shortTabLabel } from "@/lib/analysisReport";
import { formatDate } from "@/lib/format";
import { tabSeenKey, tabSignature } from "@/lib/seen";
import type { AnalysisTab, ReportDoc } from "@/lib/types";

/**
 * 2단계 분석 결과 화면 틀 (시안 346 · 348 · 350 · 352) — 영업점 · 신용리스크관리부.
 * 22px 제목 + 기준월 · 보고서 다운로드(내보내기 자리) → 밑줄 탭(짧은 이름 · 확인 안 한 점 · [+]) · 이전 분석 → 본문 → 다음 단계.
 * 분석 에이전트 탭(kind dynamic)은 DynamicReport 본문(같은 kit), 본문을 그리지 않은 보고서(이전 세대 등)는 기존 보고서 보기(목차 + 본문)로 보여 준다.
 */
export function ReportShell({
  title,
  report,
  tabs,
  previous,
  activeKey,
  basePath,
  query = "",
  exportKey,
  office,
  picker,
  builderHref,
  next,
  lead = [],
  children,
}: {
  title: string;
  report: ReportDoc;
  tabs: AnalysisTab[];
  previous: AnalysisTab[];
  activeKey: string;
  basePath: string;
  query?: string;
  /** 내려받기 키 (영업점: branch-<탭>) */
  exportKey?: string;
  office?: string | null;
  /** 지점 선택(영업점 — 관리자 · 영업본부만 보인다) */
  picker?: ReactNode;
  /** 분석 에이전트 만들기 (권한 있을 때만) */
  builderHref?: string | null;
  next?: ReactNode;
  /** 앞에 붙일 고정 탭 — 같은 화면의 기본 분석으로 돌아가는 링크(종합기획부 [데이터 분석] 탭 · Q109) */
  lead?: { href: string; label: string }[];
  /** 시안대로 그린 본문 — 없으면 기존 보고서 보기 */
  children?: ReactNode;
}) {
  const agent = report.analysisAgent;
  // 시안 본문으로 그릴 때도 이 플랫폼의 '참고한 팀 데이터' 절(Phase P · TDB-06)과 자동 갱신 상태(AGW-08)는 그대로 보인다(기존 보고서 보기는 ReportView 가 절을 그린다)
  const teamSec = children ? report.sections.find((s) => s.id === "sec-team") : undefined;
  return (
    <>
      <PageHeader
        compact
        title={title}
        actions={
          <AsOfTools key="page-tools">
            {picker}
            {report.workflow ? <RefreshStatus workflow={report.workflow} /> : null}
            {/* 시안 본문은 의견 상자 안에 '분석 다시 실행'이 있다 — 기존 보고서 보기(분석 에이전트 탭 등)는 여기에 */}
            {!children && report.workflow ? <OnDemandAnalysis workflow={report.workflow} /> : null}
            <ReportDownload tabKey={exportKey ?? activeKey} office={office} />
          </AsOfTools>
        }
      >
        <div className="no-print">
          <SeenTabLinks
            label="분석 탭"
            activeHref={`${basePath}/${activeKey}${query}`}
            items={[...lead.map((l) => ({ href: l.href, label: l.label })), ...tabs.map((tab) => ({
              href: `${basePath}/${tab.tabKey}${query}`,
              label: tab.dynamic ? (
                <>
                  {shortTabLabel(tab.label)}
                  <span className="ml-1 rounded-sm bg-canvas px-1 text-[10px] font-bold text-primary ring-1 ring-inset ring-info-line">{tab.status === "paused" ? "중지" : "맞춤"}</span>
                </>
              ) : (
                shortTabLabel(tab.label)
              ),
              dot: tab.severity,
              seenKey: tabSeenKey(tab),
              signature: tabSignature(tab),
            }))]}
            after={
              <>
                {builderHref ? <AddAgentTab href={builderHref} /> : null}
                {previous.length > 0 ? (
                  <div className="ml-auto flex items-center gap-3 self-center pb-2">
                    <details className="relative">
                      <summary className="cursor-pointer list-none rounded-pill border border-hairline px-3 py-1 text-[12px] font-bold text-charcoal">이전 분석 {previous.length}</summary>
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
                  </div>
                ) : null}
              </>
            }
          />
        </div>
      </PageHeader>
      {agent && agent.status === "paused" ? (
        <div className="shell mb-lg">
          <Notice tone="attention" title="일시 중지된 분석입니다">
            관리자가 이 분석을 일시 중지했습니다. 마지막 결과를 보여 주며 자료가 바뀌어도 다시 계산하지 않습니다.
          </Notice>
        </div>
      ) : null}
      {children ? (
        <div className="shell flex flex-col gap-4 pb-6">
          <header className="hidden print:block">
            <p className="text-[18px] font-bold text-ink-deep">{report.title}</p>
            <p className="text-[12px] text-steel">{report.subtitle}</p>
          </header>
          {children}
          {teamSec ? (
            <section aria-labelledby="sec-team-title" className="rounded-2xl border border-hairline-soft bg-canvas p-lg" data-report-team>
              <h2 id="sec-team-title" className="mb-3 text-[16px] font-bold text-ink-deep">
                {teamSec.heading}
              </h2>
              {teamSec.blocks.map((b, i) => (
                <Block key={i} block={b} report={report} />
              ))}
            </section>
          ) : null}
          {next}
        </div>
      ) : (
        <>
          <ReportView report={report} />
          {next ? <div className="shell mt-section pb-6">{next}</div> : null}
        </>
      )}
    </>
  );
}
