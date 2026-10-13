"use client";

import { useState } from "react";
import { Chart } from "@/components/charts/Chart";
import { ComparisonTable } from "@/components/data/ComparisonTable";
import { MetricStrip, type MetricStripItem } from "@/components/data/MetricStrip";
import { AgentNote } from "@/components/domain/AgentNote";
import { SegmentDetail } from "@/components/domain/SegmentDetail";
import { OnDemandAnalysis } from "@/components/agent/AgentProgress";
import { PageHeader } from "@/components/layout/PageHeader";
import Link from "next/link";
import { IconWarn, NextStep, PillTabs, SectionHead, SeverityBadge, StatusDot, TextLink } from "@/components/ui/primitives";
import { formatFigure } from "@/lib/format";
import { lastStep, pointCount, prevStepPhrase, revenueRowsOf, trendPhrase } from "@/lib/loanView";
import { NO_VALUE, periodOf } from "@/lib/period";
import type { AnalysisTab, ComparisonView, LoanOverview } from "@/lib/types";

type TabKey = "revenue" | "corporate" | "household" | "comparison";

const TABS: { key: TabKey; label: string }[] = [
  { key: "revenue", label: "여신 종합수익" },
  { key: "corporate", label: "기업여신" },
  { key: "household", label: "가계여신" },
  { key: "comparison", label: "기업·가계 비교" },
];

/**
 * STEP 2 — 데이터 설명과 분석
 * 4개 영역을 화면 내부 탭으로 묶고, 영역마다 핵심 지표 → AI 해설 → 표·차트 순서를 지킨다.
 */
export function AnalysisWorkspace({
  overview,
  comparison,
  workflow,
  custom = [],
  builderHref = null,
}: {
  overview: LoanOverview;
  comparison: ComparisonView;
  /** 화면 산출물을 만드는 워크플로우(서버 제공) — 없으면 '분석 다시 실행' 숨김 */
  workflow?: string | null;
  /** 맞춤 분석 탭 (분석 에이전트 · 공간 hq · Q109) — 같은 화면의 탭으로 이어 붙인다 */
  custom?: AnalysisTab[];
  /** 분석 만들기 (권한 있을 때만) */
  builderHref?: string | null;
}) {
  const [tab, setTab] = useState<TabKey>("revenue");
  const { revenue, corporate, household } = overview;
  // 기간 · 추세 문구는 산출물 기준일과 계열 값에서 계산한다 (Phase I · 하드코딩 제거)
  const p = periodOf(overview.asOf);
  const cp = periodOf(comparison.asOf);
  const rows = revenueRowsOf(revenue.rows);
  const shareStep = lastStep(revenue.nimShareTrend);
  const revenueItems: MetricStripItem[] = [];
  if (rows.total) revenueItems.push({ label: `전체 수익 (${p.month} 누계)`, figure: rows.total.current, delta: rows.total.diffRate });
  if (rows.nim) revenueItems.push({ label: "여신 이자마진 수익", figure: rows.nim.current, delta: rows.nim.diffRate });
  revenueItems.push({
    label: "전체 수익 중 비중",
    figure: revenue.nimShare,
    caption: prevStepPhrase(revenue.nimShareTrend, revenue.nimShare) ?? undefined,
    tone: shareStep === "축소" ? "attention" : "default",
  });
  if (rows.corporate) {
    revenueItems.push({
      label: "기업 이자수익",
      figure: rows.corporate.current,
      caption: rows.household ? `가계 ${formatFigure(rows.household.current)}` : undefined,
    });
  }
  const shareTrend = trendPhrase(revenue.nimShareTrend);
  // 기업 · 가계 구성비 흐름 — 계열마다 방향을 계산해 잇는다
  const shareCaption = comparison.shareSeries
    .map((s) => {
      const t = trendPhrase(s.points);
      return t ? `${s.name} ${t}` : null;
    })
    .filter(Boolean)
    .join(" · ");
  const shareYears = Math.max(0, ...comparison.shareSeries.map((s) => pointCount(s.points)));
  const balanceFigure = comparison.balanceRows[0]?.current;

  return (
    <>
      <PageHeader
        eyebrow="2단계"
        title="데이터 분석"
        description="여신 실적을 원천 데이터 기준으로 해석합니다. 수치는 원천 파일·셀까지 추적되고, 해설은 인과 단정 없이 기술됩니다."
        actions={workflow ? <OnDemandAnalysis workflow={workflow} /> : null}
      >
        <div className="flex flex-wrap items-center gap-1.5">
        <PillTabs
          label="분석 영역"
          items={TABS.map((t) => ({
            key: t.key,
            label: (
              <>
                {t.label}
                {t.key === "comparison" && comparison.divergence ? (
                  <span className="h-1.5 w-1.5 rounded-circle bg-critical" aria-label="괴리 탐지" />
                ) : null}
              </>
            ),
          }))}
          value={tab}
          onChange={setTab}
        />
        {custom.length || builderHref ? (
          <>
            <span aria-hidden="true" className="mx-1 h-5 w-px bg-hairline" />
            <nav aria-label="맞춤 분석" className="flex flex-wrap items-center gap-1.5" data-custom-tabs>
              {custom.map((t) => (
                <Link
                  key={t.tabKey}
                  href={`/hq/analysis/${t.tabKey}`}
                  className="inline-flex items-center gap-1.5 rounded-pill border border-hairline bg-canvas px-3 py-1.5 text-[12px] font-bold text-ink"
                  data-custom-tab={t.tabKey}
                >
                  <StatusDot severity={t.severity} />
                  {t.label}
                  <span className="rounded-sm bg-canvas px-1 text-[10px] font-bold text-primary ring-1 ring-inset ring-info-line">{t.status === "paused" ? "중지" : "맞춤"}</span>
                </Link>
              ))}
              {builderHref ? (
                <Link href={builderHref} className="inline-flex items-center rounded-pill border border-dashed border-hairline px-3 py-1.5 text-[12px] font-bold text-primary" data-builder-link>
                  + 분석 만들기
                </Link>
              ) : null}
            </nav>
          </>
        ) : null}
        </div>
      </PageHeader>

      <div className="shell flex flex-col gap-xxl">
        {tab === "revenue" ? (
          <>
            <MetricStrip items={revenueItems} columns={revenueItems.length === 4 ? 4 : 3} />

            <AgentNote
              text={revenue.narrative}
              figures={revenue.narrativeFigures}
              evidence={revenue.evidence}
              evidenceTitle="여신 종합수익 해설 근거"
            />

            <section className="flex flex-col gap-xxl">
              <div>
                <SectionHead title="전년 동기 대비" hint={`3개년 ${p.month} 누계`} />
                <div className="rounded-2xl border border-hairline-soft p-lg">
                  <ComparisonTable rows={revenue.rows} asOf={overview.asOf} />
                </div>
              </div>
              <div>
                <SectionHead title="여신 이자마진 비중" hint="전체 수익 대비" />
                <div className="rounded-2xl border border-hairline-soft p-lg">
                  <Chart
                    kind="line"
                    title=""
                    unit={revenue.nimShare.unit}
                    decimals={revenue.nimShare.decimals ?? 2}
                    series={[{ name: "비중", points: revenue.nimShareTrend }]}
                    zeroBased={false}
                    caption={shareTrend ? `${shareTrend} 흐름` : undefined}
                  />
                </div>
              </div>
            </section>
          </>
        ) : null}

        {tab === "corporate" ? <SegmentDetail segment={corporate} asOf={overview.asOf} /> : null}
        {tab === "household" ? <SegmentDetail segment={household} asOf={overview.asOf} /> : null}

        {tab === "comparison" ? (
          <>
            {comparison.divergence ? (
              <AgentNote
                label="기조 괴리 탐지"
                title={
                  <span className="flex flex-wrap items-center gap-2">
                    <SeverityBadge severity={comparison.divergence.severity} />
                    {comparison.divergence.title}
                  </span>
                }
                text={comparison.divergence.statement}
                figures={comparison.divergence.figures}
                evidence={comparison.divergence.evidence}
                evidenceTitle={comparison.divergence.title}
                verifications={comparison.divergence.verifications}
                footer={<TextLink href="/hq/goals">경영목표 검토로</TextLink>}
              />
            ) : null}

            <section>
              <SectionHead title="잔액 규모" hint={`${cp.year === NO_VALUE ? NO_VALUE : `${cp.year}년`} 월별`} />
              <div className="rounded-2xl border border-hairline-soft p-lg">
                <Chart
                  kind="line"
                  title=""
                  unit={balanceFigure?.unit ?? "NONE"}
                  decimals={balanceFigure?.decimals ?? 2}
                  series={comparison.balanceSeries}
                  zeroBased={false}
                />
                <div className="mt-lg">
                  <ComparisonTable rows={comparison.balanceRows} asOf={comparison.asOf} />
                </div>
              </div>
            </section>

            <section className="grid grid-cols-1 gap-xl xl:grid-cols-2">
              <div>
                <SectionHead title="구성비" hint={`기업+가계 합계 기준${shareYears ? ` ${shareYears}개년` : ""}`} />
                <div className="rounded-2xl border border-hairline-soft p-lg">
                  <Chart kind="bar" title="" unit="PCT" decimals={2} series={comparison.shareSeries} caption={shareCaption || undefined} />
                </div>
              </div>
              <div>
                <SectionHead title="이자수익 규모" hint="원화대출금이자수익 하위 항목" />
                <div className="rounded-2xl border border-hairline-soft p-lg">
                  <ComparisonTable rows={comparison.interestRows} asOf={comparison.asOf} />
                </div>
              </div>
            </section>

            <p className="flex items-start gap-2 text-[12px] leading-relaxed text-steel">
              <IconWarn className="mt-0.5 shrink-0 text-attention" />
              {comparison.proxyNote}
            </p>
          </>
        ) : null}

        <NextStep
          step={3}
          title="경영목표 설정"
          description="AI 주목 사항과 목표 수정·신규 제안을 검토해 확정하고, 사업부서로 전파합니다."
          href="/hq/goals"
        />
      </div>
    </>
  );
}
