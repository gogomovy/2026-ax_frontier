"use client";

import Link from "next/link";
import { useState } from "react";
import clsx from "clsx";
import { BigFigure } from "@/components/data/BigFigure";
import { ComparisonTable } from "@/components/data/ComparisonTable";
import { FigureText } from "@/components/data/FigureText";
import { MetricStrip } from "@/components/data/MetricStrip";
import { RichText } from "@/components/data/RichText";
import { ChartCard } from "@/components/charts/ChartCard";
import { Chart } from "@/components/charts/Chart";
import { ShareBars } from "@/components/charts/ShareBars";
import { AgentNote } from "@/components/domain/AgentNote";
import { SectorTitle, useSector } from "@/components/domain/SectorTitle";
import { SegmentDetail } from "@/components/domain/SegmentDetail";
import { OnDemandAnalysis } from "@/components/agent/AgentProgress";
import { EvidenceRow } from "@/components/evidence/EvidenceChips";
import { PageHeader } from "@/components/layout/PageHeader";
import { AsOfTools, ExportButton } from "@/components/layout/PageTools";
import { IconSparkle, IconTriangleDown, IconTriangleUp } from "@/components/ui/icons";
import { EmptyCard } from "@/components/ui/StateViews";
import { IconWarn, NextStep, SeverityBadge, StatusDot, TextLink, tabClass } from "@/components/ui/primitives";
import type { AnalysisTab, ComparisonView, DomainCardInfo, Goal, Insight, LoanOverview, Severity } from "@/lib/types";

type TabKey = "revenue" | "corporate" | "household" | "comparison";

const TABS: { key: TabKey; label: string }[] = [
  { key: "revenue", label: "여신 종합수익" },
  { key: "corporate", label: "기업여신" },
  { key: "household", label: "가계여신" },
  { key: "comparison", label: "기업·가계 비교" },
];

/** 목표 판정 → 탭의 점 색 (미달 · 근접 = 주황, 초과 = 빨강) */
function dotOf(goal?: Goal): Severity | undefined {
  if (!goal?.gapVerdict || goal.gapVerdict === "on_track") return undefined;
  return goal.gapVerdict === "breach" ? "critical" : "caution";
}

/** 문장 단위로 나눠 마지막 문장(결론)을 돌려준다 */
function lastSentence(text: string): string {
  const plain = text.replace(/\s+/g, " ").trim();
  const parts = plain.split(/(?<=[다요]\.)\s+/);
  return parts[parts.length - 1] ?? plain;
}

/**
 * 2단계 — 데이터 분석 (가이드 7156 · 7160 · 7157)
 * 부문 선택(제목) → 하위 분석 밑줄 탭 → Agent 해설(AI 영역: 큰 숫자 3개 + 결론 한 문장 + 근거) → 전년 동기 대비 표 + 비중 막대 → 다음 단계.
 * 선택한 탭에 미확인 이슈가 있으면 탭 이름 옆에 점(주황 · 빨강)이 있고, 탭을 선택하면 사라진다.
 */
export function AnalysisWorkspace({
  overview,
  comparison,
  domains,
  goals,
  headline,
  workflow,
  custom = [],
  builderHref = null,
}: {
  overview: LoanOverview;
  comparison: ComparisonView;
  domains: DomainCardInfo[];
  goals: Goal[];
  /** 결론 문장으로 쓸 AI 주목 사항 (없으면 해설의 마지막 문장) */
  headline?: Insight | null;
  /** 화면 산출물을 만드는 워크플로우(서버 제공) — 없으면 '분석 다시 실행' 숨김 */
  workflow?: string | null;
  /** 맞춤 분석 탭 (분석 에이전트 · 공간 hq · Q109) — 같은 화면의 탭으로 이어 붙인다 */
  custom?: AnalysisTab[];
  /** 분석 만들기 (권한 있을 때만) */
  builderHref?: string | null;
}) {
  const [tab, setTab] = useState<TabKey>("revenue");
  const { domain } = useSector(domains);
  const ready = domain?.status === "active";
  const { corporate, household } = overview;

  const dots: Partial<Record<TabKey, Severity>> = {
    corporate: dotOf(goals.find((g) => g.id === "goal-corp-growth")),
    household: dotOf(goals.find((g) => g.id === "goal-hh-control")),
    comparison: comparison.divergence ? "critical" : undefined,
  };

  return (
    <>
      <PageHeader
        title={<SectorTitle domains={domains} title="데이터 분석" />}
        actions={
          <AsOfTools>
            {workflow ? <OnDemandAnalysis workflow={workflow} /> : null}
            <ExportButton />
          </AsOfTools>
        }
      >
        {ready ? (
          <div role="tablist" aria-label="분석 영역" className="flex flex-wrap items-center gap-x-6 border-b border-hairline-soft">
            {TABS.map((t) => {
              const on = tab === t.key;
              const dot = on ? undefined : dots[t.key];
              return (
                <button key={t.key} type="button" role="tab" aria-selected={on} onClick={() => setTab(t.key)} className={clsx(tabClass(on, "md"), "-mb-px")}>
                  {t.label}
                  {dot ? <StatusDot severity={dot} /> : null}
                </button>
              );
            })}
            {custom.map((t) => (
              <Link key={t.tabKey} href={`/hq/analysis/${t.tabKey}`} className={clsx(tabClass(false, "md"), "-mb-px")} data-custom-tab={t.tabKey}>
                {t.label}
                <StatusDot severity={t.severity} />
                <span className="rounded-sm bg-info-soft px-1.5 text-[12px] font-bold text-primary">{t.status === "paused" ? "중지" : "맞춤"}</span>
              </Link>
            ))}
            {builderHref ? (
              <Link href={builderHref} className={clsx(tabClass(false, "md"), "-mb-px !text-primary")} data-builder-link>
                + 분석 만들기
              </Link>
            ) : null}
          </div>
        ) : null}
      </PageHeader>

      <div className="shell flex flex-col gap-10 pb-6">
        {!ready ? (
          <EmptyCard
            title={`${domain?.name ?? "이"} 부문은 아직 준비 중이에요`}
            description="1차 범위는 여신 부문이에요. 데이터셋과 지표를 등록하면 같은 구조로 분석이 열려요."
            actionLabel="현황·목표로 돌아가기"
            href="/hq/overview"
          />
        ) : null}

        {ready && tab === "revenue" ? <RevenueTab overview={overview} headline={headline ?? null} /> : null}
        {ready && tab === "corporate" ? <SegmentDetail segment={corporate} /> : null}
        {ready && tab === "household" ? <SegmentDetail segment={household} /> : null}

        {ready && tab === "comparison" ? (
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
              <h2 className="mb-5 text-[20px] font-bold leading-[1.25] text-ink-deep">잔액 규모 <span className="ml-2 text-[12px] font-normal text-steel">2026년 월별</span></h2>
              <div className="rounded-xl border border-hairline-soft bg-canvas p-6">
                <Chart kind="line" title="" unit="KRW_TN" decimals={2} series={comparison.balanceSeries} zeroBased={false} />
                <div className="mt-5">
                  <ComparisonTable rows={comparison.balanceRows} unitLabel="조원" />
                </div>
              </div>
            </section>

            <section className="grid grid-cols-1 gap-5 xl:grid-cols-2">
              <div>
                <h2 className="mb-5 text-[20px] font-bold leading-[1.25] text-ink-deep">구성비 <span className="ml-2 text-[12px] font-normal text-steel">기업+가계 합계 기준 3개년</span></h2>
                <div className="rounded-xl border border-hairline-soft bg-canvas p-6">
                  <Chart kind="bar" title="" unit="PCT" decimals={2} series={comparison.shareSeries} caption="기업여신 구성비는 3개년 연속 축소, 가계여신 구성비는 확대되는 흐름입니다." />
                </div>
              </div>
              <div>
                <h2 className="mb-5 text-[20px] font-bold leading-[1.25] text-ink-deep">이자수익 규모 <span className="ml-2 text-[12px] font-normal text-steel">원화대출금이자수익 하위 항목</span></h2>
                <div className="rounded-xl border border-hairline-soft bg-canvas p-6">
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

        {ready ? <NextStep step={3} title="경영목표 설정" description="분석 결과를 바탕으로 기업여신 성장목표와 가계여신 관리 한도의 조정안을 검토해요." href="/hq/goals" cta="목표 설정으로" /> : null}
      </div>
    </>
  );
}

/** 여신 종합수익 — Agent 해설 + 전년 동기 대비 + 비중 */
function RevenueTab({ overview, headline }: { overview: LoanOverview; headline: Insight | null }) {
  const { revenue } = overview;
  const [full, setFull] = useState(false);
  const f = revenue.narrativeFigures;
  const total = revenue.rows[0];
  const nim = revenue.rows[1];
  const toTn = (bn: number | null) => (bn === null ? "-" : (bn / 10000).toFixed(2));
  const totalGrowth = total.diffRate.value ?? 0;
  const nimGrowth = nim.diffRate.value ?? 0;
  const gap = Math.abs(totalGrowth - nimGrowth).toFixed(2);
  const delta = f.nim_share_delta;
  const prior = f.nim_share_2025;
  const down = (delta?.value ?? 0) < 0;
  const conclusion = headline?.title ?? lastSentence(revenue.narrative);

  return (
    <>
      {/* Agent 해설 — AI 영역: primary/100 박스 + 흰 내부 카드 */}
      <section aria-label="Agent 해설" className="rounded-xl bg-info-soft p-3">
        <span className="inline-flex h-7 items-center gap-1.5 rounded-pill bg-canvas px-3 text-[12px] font-bold text-primary">
          <IconSparkle />
          Agent 해설
        </span>
        <div className="mt-3 rounded-lg bg-canvas px-7 py-6">
          <dl className="grid grid-cols-1 gap-6 md:grid-cols-3 md:divide-x md:divide-hairline-soft">
            <div className="md:pr-6">
              <dt className="text-[14px] text-steel">여신 이자마진 비중</dt>
              <dd className="mt-2">
                <BigFigure figure={revenue.nimShare} size="hero" />
                {delta && prior ? (
                  <p className={clsx("mt-1.5 flex flex-wrap items-center gap-x-1.5 text-[13px] font-bold", down ? "text-attention" : "text-ink-deep")}>
                    {down ? <IconTriangleDown /> : <IconTriangleUp />}
                    <FigureText figure={delta} plain className={clsx(down ? "!text-attention" : "")} />
                    <span className="font-medium text-steel">
                      전년 <FigureText figure={prior} plain className="!font-medium !text-steel" />
                    </span>
                  </p>
                ) : null}
              </dd>
            </div>
            <div className="md:px-6">
              <dt className="text-[14px] text-steel">전체 수익 증가율</dt>
              <dd className="mt-2">
                <BigFigure figure={total.diffRate} size="hero" signed />
                <p className="mt-1.5 text-[13px] text-steel tnum">{toTn(total.current.value)}조원 · 8월 누계</p>
              </dd>
            </div>
            <div className="md:pl-6">
              <dt className="text-[14px] text-steel">여신 이자마진 증가율</dt>
              <dd className="mt-2">
                <BigFigure figure={nim.diffRate} size="hero" signed />
                <p className="mt-1.5 text-[13px] text-steel tnum">
                  {toTn(nim.current.value)}조원 · 전체보다 {gap}%p {nimGrowth < totalGrowth ? "낮음" : "높음"}
                </p>
              </dd>
            </div>
          </dl>

          <div className="mt-6 border-t border-hairline-soft pt-5">
            <p className="flex items-start gap-2 text-[16px] font-bold leading-[1.5] text-ink-deep">
              <IconSparkle size={14} className="mt-[5px] shrink-0 text-primary" />
              {conclusion}
            </p>
            <div className="mt-3">
              <EvidenceRow items={revenue.evidence} title="여신 종합수익 해설 근거" statement={conclusion} expanded={full} onToggleFull={() => setFull((v) => !v)} />
            </div>
            {full ? <RichText text={revenue.narrative} figures={revenue.narrativeFigures} className="mt-4 rounded-lg bg-surface-soft px-5 py-4 text-[14px] leading-[1.7] text-ink-deep" /> : null}
          </div>
        </div>
      </section>

      <section className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
        <div className="rounded-xl border border-hairline-soft bg-canvas p-6">
          <h2 className="flex flex-wrap items-baseline gap-x-3 text-[20px] font-bold leading-[1.25] text-ink-deep">
            전년 동기 대비
            <span className="text-[12px] font-normal text-steel">3개년 8월 누계 · 단위 억원</span>
          </h2>
          <div className="mt-5">
            <ComparisonTable rows={revenue.rows} unitLabel="억원" highlight={(r) => r === nim} sortable />
          </div>
          <p className="mt-4 text-[12px] leading-normal text-steel">
            여신 이자마진(<FigureText figure={nim.diffRate} signed plain className="!font-medium !text-steel" />)이 전체 수익(<FigureText figure={total.diffRate} signed plain className="!font-medium !text-steel" />)보다{" "}
            {nimGrowth < totalGrowth ? "느리게" : "빠르게"} 늘어 비중이 {down ? "줄었습니다" : "커졌습니다"}.
          </p>
        </div>

        <ChartCard
          title="여신 이자마진 비중"
          legend={[
            { label: "여신 이자마진", color: "var(--color-primary)", dot: true },
            { label: "기타 수익", color: "var(--color-hairline-soft)", dot: true },
          ]}
          caption="전체 수익 대비 비중 · 3개년 8월 누계"
          table={{
            columns: [
              { key: "p", label: "시점" },
              { key: "a", label: "여신 이자마진(%)", align: "right" },
              { key: "b", label: "기타 수익(%)", align: "right" },
            ],
            rows: revenue.nimShareTrend.map((p) => ({ p: p.label, a: (p.value ?? 0).toFixed(2), b: (100 - (p.value ?? 0)).toFixed(2) })),
          }}
          className="min-h-[300px]"
        >
          <ShareBars points={revenue.nimShareTrend} targetName="여신 이자마진" otherName="기타 수익" />
        </ChartCard>
      </section>

      {/* 하위 항목 한눈에 */}
      <MetricStrip
        items={[
          { label: "전체 수익 (8월 누계)", figure: total.current, delta: total.diffRate },
          { label: "여신 이자마진 수익", figure: nim.current, delta: nim.diffRate },
          { label: "기업 이자수익", figure: revenue.rows[2].current, delta: revenue.rows[2].diffRate },
          { label: "가계 이자수익", figure: revenue.rows[3].current, delta: revenue.rows[3].diffRate },
        ]}
      />
    </>
  );
}
