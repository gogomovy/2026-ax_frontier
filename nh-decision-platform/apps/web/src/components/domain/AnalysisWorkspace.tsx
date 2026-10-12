"use client";

import { useState } from "react";
import { Chart } from "@/components/charts/Chart";
import { ComparisonTable } from "@/components/data/ComparisonTable";
import { MetricStrip } from "@/components/data/MetricStrip";
import { AgentNote } from "@/components/domain/AgentNote";
import { SegmentDetail } from "@/components/domain/SegmentDetail";
import { OnDemandAnalysis } from "@/components/agent/AgentProgress";
import { PageHeader } from "@/components/layout/PageHeader";
import Link from "next/link";
import { IconWarn, NextStep, PillTabs, SectionHead, SeverityBadge, StatusDot, TextLink } from "@/components/ui/primitives";
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
 * 4개 영역을 화면 내부 탭으로 묶고, 영역마다 핵심 지표 → Agent 해설 → 표·차트 순서를 지킨다.
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
            <MetricStrip
              items={[
                { label: "전체 수익 (8월 누계)", figure: revenue.rows[0].current, delta: revenue.rows[0].diffRate },
                { label: "여신 이자마진 수익", figure: revenue.rows[1].current, delta: revenue.rows[1].diffRate },
                {
                  label: "전체 수익 중 비중",
                  figure: revenue.nimShare,
                  caption: "전년 45.90% → 축소",
                  tone: "attention",
                },
                {
                  label: "기업 이자수익",
                  figure: revenue.rows[2].current,
                  caption: `가계 ${revenue.rows[3].current.value?.toLocaleString("ko-KR")}억원`,
                },
              ]}
            />

            <AgentNote
              text={revenue.narrative}
              figures={revenue.narrativeFigures}
              evidence={revenue.evidence}
              evidenceTitle="여신 종합수익 해설 근거"
            />

            <section className="flex flex-col gap-xxl">
              <div>
                <SectionHead title="전년 동기 대비" hint="3개년 8월 누계" />
                <div className="rounded-2xl border border-hairline-soft p-lg">
                  <ComparisonTable rows={revenue.rows} unitLabel="억원" />
                </div>
              </div>
              <div>
                <SectionHead title="여신 이자마진 비중" hint="전체 수익 대비" />
                <div className="rounded-2xl border border-hairline-soft p-lg">
                  <Chart
                    kind="line"
                    title=""
                    unit="PCT"
                    decimals={2}
                    series={[{ name: "비중", points: revenue.nimShareTrend }]}
                    zeroBased={false}
                    caption="3개년 연속 축소 흐름"
                  />
                </div>
              </div>
            </section>
          </>
        ) : null}

        {tab === "corporate" ? <SegmentDetail segment={corporate} /> : null}
        {tab === "household" ? <SegmentDetail segment={household} /> : null}

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
              <SectionHead title="잔액 규모" hint="2026년 월별" />
              <div className="rounded-2xl border border-hairline-soft p-lg">
                <Chart kind="line" title="" unit="KRW_TN" decimals={2} series={comparison.balanceSeries} zeroBased={false} />
                <div className="mt-lg">
                  <ComparisonTable rows={comparison.balanceRows} unitLabel="조원" />
                </div>
              </div>
            </section>

            <section className="grid grid-cols-1 gap-xl xl:grid-cols-2">
              <div>
                <SectionHead title="구성비" hint="기업+가계 합계 기준 3개년" />
                <div className="rounded-2xl border border-hairline-soft p-lg">
                  <Chart
                    kind="bar"
                    title=""
                    unit="PCT"
                    decimals={2}
                    series={comparison.shareSeries}
                    caption="기업여신 구성비는 3개년 연속 축소, 가계여신 구성비는 확대되는 흐름입니다."
                  />
                </div>
              </div>
              <div>
                <SectionHead title="이자수익 규모" hint="원화대출금이자수익 하위 항목" />
                <div className="rounded-2xl border border-hairline-soft p-lg">
                  <ComparisonTable rows={comparison.interestRows} unitLabel="억원" />
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
          description="AI Attention 과 목표 수정·신규 제안을 검토해 확정하고, 사업부서로 전파합니다."
          href="/hq/goals"
        />
      </div>
    </>
  );
}
