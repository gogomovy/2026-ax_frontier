"use client";

import Link from "next/link";
import { createContext, useContext, useState, type ReactNode } from "react";
import clsx from "clsx";
import { BigFigure } from "@/components/data/BigFigure";
import { ComparisonTable } from "@/components/data/ComparisonTable";
import { FigureText } from "@/components/data/FigureText";
import { RichText } from "@/components/data/RichText";
import { ChartCard } from "@/components/charts/ChartCard";
import { ShareBars } from "@/components/charts/ShareBars";
import { TrendChart } from "@/components/charts/TrendChart";
import { PAIR, PairColumns, PairHBars, PairLine } from "@/components/charts/PairCharts";
import { derivedFigure } from "@/lib/derived";
import { SectorTitle, useSector } from "@/components/domain/SectorTitle";
import { OnDemandAnalysis } from "@/components/agent/AgentProgress";
import { EvidenceRow } from "@/components/evidence/EvidenceChips";
import { PageHeader } from "@/components/layout/PageHeader";
import { AsOfTools, ExportButton } from "@/components/layout/PageTools";
import { EmptyCard } from "@/components/ui/StateViews";
import { AddAgentTab, NextStep, StatusDot, tabClass } from "@/components/ui/primitives";
import { UNIT_LABEL, formatFigure, formatSigned, formatValue } from "@/lib/format";
import { pointCount, revenueRowsOf, targetPath, trendPhrase } from "@/lib/loanView";
import { NO_VALUE, periodOf } from "@/lib/period";
import { usePrinting } from "@/lib/printState";
import { toPoliteSentence, toPoliteText } from "@/lib/sentence";
import { signatureOf, tabSeenKey, tabSignature } from "@/lib/seen";
import type { AnalysisTab, ComparisonRow, ComparisonView, DomainCardInfo, Evidence, Figure, Goal, Insight, LoanOverview, LoanSegmentDetail, Severity } from "@/lib/types";
import { goalByRole, threshold } from "@/lib/uiConfig";
import { useUiConfig } from "@/components/providers/SessionProvider";
import { useSeen } from "@/components/ui/useSeen";

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
 * 기간 · 추세 문구는 산출물 기준일과 계열 값에서 계산한다 — 값이 없으면 '–' 로 그린다(Phase I · 하드코딩 제거).
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
  /** 분석 에이전트 만들기 (권한 있을 때만) */
  builderHref?: string | null;
}) {
  const [tab, setTab] = useState<TabKey>("revenue");
  const cfg = useUiConfig();
  const seen = useSeen();
  const { domain } = useSector(domains);
  const ready = domain?.status === "active";
  const { corporate, household } = overview;

  // 탭 점 — 역할로 지정된 목표의 판정(Phase K · HC-03) · 확인하지 않은 것만(DOT-01: 탭을 열면 사라지고 판정 · 기준일이 바뀌면 다시)
  const corpGoal = goalByRole(goals, cfg, "corpGrowth");
  const hhGoal = goalByRole(goals, cfg, "hhControl");
  const rawDots: Partial<Record<TabKey, { severity: Severity; sig: string }>> = {};
  const put = (k: TabKey, severity: Severity | undefined, ...parts: (string | null | undefined)[]) => {
    if (severity) rawDots[k] = { severity, sig: signatureOf([severity, ...parts], overview.asOf) };
  };
  put("corporate", dotOf(corpGoal), corpGoal?.id, corpGoal?.gapVerdict);
  put("household", dotOf(hhGoal), hhGoal?.id, hhGoal?.gapVerdict);
  put("comparison", comparison.divergence ? "critical" : undefined, "divergence", comparison.asOf);
  const dotKey = (k: TabKey) => `hq.analysis.${k}`;
  const dotFor = (k: TabKey) => {
    const d = rawDots[k];
    return d && seen.fresh(dotKey(k), d.sig) ? d.severity : undefined;
  };
  const openTab = (k: TabKey) => {
    setTab(k);
    seen.mark(dotKey(k), rawDots[k]?.sig);
  };


  return (
    <>
      <PageHeader
        compact
        title={<SectorTitle domains={domains} title="데이터 분석" />}
        actions={
          <AsOfTools>
            <ExportButton />
          </AsOfTools>
        }
      >
        {ready ? (
          // 화면 안 탭(tablist)과 다른 주소로 가는 맞춤 분석 · 만들기 링크는 같은 줄에 두되 역할을 나눈다(tablist 안에는 tab 만)
          <div data-custom-tabs className="flex flex-wrap items-center gap-x-6 border-b border-hairline-soft">
            <div role="tablist" aria-label="분석 영역" className="flex flex-wrap items-center gap-x-6">
            {TABS.map((t) => {
              const on = tab === t.key;
              const dot = on ? undefined : dotFor(t.key);
              return (
                <button key={t.key} type="button" role="tab" aria-selected={on} onClick={() => openTab(t.key)} className={clsx(tabClass(on, "md"), "-mb-px")}>
                  {t.label}
                  {dot ? <StatusDot severity={dot} /> : null}
                </button>
              );
            })}
            </div>
            {custom.map((t) => (
              <Link key={t.tabKey} href={`/hq/analysis/${t.tabKey}`} onClick={() => seen.mark(tabSeenKey(t), tabSignature(t))} className={clsx(tabClass(false, "md"), "-mb-px")} data-custom-tab={t.tabKey}>
                {t.label}
                {seen.fresh(tabSeenKey(t), tabSignature(t)) ? <StatusDot severity={t.severity} /> : null}
                <span className="rounded-sm bg-info-soft px-1.5 text-[12px] font-bold text-primary">{t.status === "paused" ? "중지" : "맞춤"}</span>
              </Link>
            ))}
            {builderHref ? <AddAgentTab href={builderHref} /> : null}
          </div>
        ) : null}
      </PageHeader>

      {/* 분석 다시 실행은 Agent 해설 상자 오른쪽 위에 둔다 — 다시 돌리는 대상(해설)과 같은 자리 */}
      <AgentRerunContext.Provider value={workflow ?? null}>
      <div className="shell flex flex-col gap-6 pb-6">
        {!ready ? (
          <EmptyCard
            title={`${domain?.name ?? "이"} 부문은 아직 준비 중이에요`}
            description="이 부문의 데이터셋과 지표를 등록하면 같은 구조로 분석이 열려요."
            actionLabel="현황·목표로 돌아가기"
            href="/hq/overview"
          />
        ) : null}

        {ready && tab === "revenue" ? <RevenueTab overview={overview} headline={headline ?? null} /> : null}
        {ready && tab === "corporate" ? <SegmentTab segment={corporate} overview={overview} comparison={comparison} goals={goals} /> : null}
        {ready && tab === "household" ? <SegmentTab segment={household} overview={overview} comparison={comparison} goals={goals} /> : null}

        {ready && tab === "comparison" ? <ComparisonTab overview={overview} comparison={comparison} /> : null}

        {ready ? (
          <NextStep
            step={3}
            title="경영목표 설정"
            description={
              tab === "corporate"
                ? `AI가 제안한 ${corporate.name} 목표 조정안을 검토합니다.`
                : tab === "household"
                  ? `AI가 제안한 ${household.name} 관리목표 조정안을 검토합니다.`
                  : "분석 결과를 바탕으로 기업여신 성장목표와 가계여신 관리 한도의 조정안을 검토합니다."
            }
            href="/hq/goals"
            cta="목표 설정으로"
          />
        ) : null}
      </div>
      </AgentRerunContext.Provider>
    </>
  );
}

/** Agent 해설 상자에 '분석 다시 실행'을 붙이기 위한 워크플로 코드 (없으면 버튼 없음) */
const AgentRerunContext = createContext<string | null>(null);

/** 억원 수치는 조원으로 바꿔 보여 준다(시안: 4.81조원 · 1.09조원) — 계산 추적은 같은 수치 */
function asTn(f: Figure): Figure {
  return f.unit === "KRW_BN" && f.value != null ? { ...f, value: f.value / 10000, unit: "KRW_TN", decimals: 2 } : f;
}
const tnText = (f: Figure) => formatFigure(asTn(f));
const signedText = (f?: Figure | null) => (f ? formatSigned(f) : NO_VALUE);
/** 2026.03 → 3월 */
const monthOf = (label: string) => {
  const m = /\d{4}[.-](\d{1,2})/.exec(label);
  return m ? `${Number(m[1])}월` : label;
};

type Kpi = { label: string; value: ReactNode; sub?: ReactNode };

/** Agent 해설 — primary/100 박스(안쪽 16) + 흰 카드(22·24·20·24): 큰 숫자 3칸 → 구분선 → 결론 한 문장 → 근거 */
function AgentBox({
  badge = "Agent 해설",
  kpis,
  conclusion,
  evidence,
  evidenceTitle,
  narrative,
  figures,
}: {
  badge?: string;
  kpis: Kpi[];
  conclusion: string;
  evidence: Evidence[];
  evidenceTitle: string;
  narrative: string;
  figures: Record<string, Figure>;
}) {
  const [fullOpen, setFull] = useState(false);
  const printing = usePrinting();
  const full = fullOpen || printing; // 인쇄 · PDF 에는 접어 둔 해설 전문도 (EXP-02)
  const rerun = useContext(AgentRerunContext);
  return (
    <section aria-label="Agent 해설" className="flex flex-col gap-3 rounded-[10px] bg-info-soft p-4">
      {/* 머리 줄 — 왼쪽 'Agent 해설' 배지 · 오른쪽 '분석 다시 실행'(이 해설을 다시 만든다) */}
      <div className="flex items-center justify-between gap-3">
        <span className="ml-0.5 inline-flex h-[23px] w-fit items-center gap-1 rounded-pill bg-canvas px-2 text-[12px] font-bold text-primary-deep">✦ {badge}</span>
        {rerun ? <OnDemandAnalysis workflow={rerun} variant="link" /> : null}
      </div>
      <div className="flex flex-col gap-4 rounded-lg bg-canvas px-6 pb-5 pt-[22px]">
        <dl className="grid grid-cols-1 gap-y-4 md:grid-cols-[421fr_446fr_446fr]">
          {kpis.map((k, i) => (
            <div key={k.label} className={clsx("flex min-w-0 flex-col gap-[3px]", i === 0 ? "md:pr-6" : "md:border-l md:border-hairline-soft md:px-6")}>
              <dt className="text-[12px] font-medium leading-[18px] text-steel">{k.label}</dt>
              <dd>{k.value}</dd>
              {k.sub ? <dd className="text-[12px] leading-[18px] text-steel">{k.sub}</dd> : null}
            </div>
          ))}
        </dl>
        {conclusion ? (
          <>
            <span aria-hidden="true" className="h-px bg-hairline-soft" />
            <div className="flex flex-col gap-[7px]">
              <p className="flex items-start gap-1.5 text-[15px] font-bold leading-[21px] text-ink-deep">
                <span aria-hidden="true" className="text-[14px] text-primary">
                  ✦
                </span>
                {conclusion}
              </p>
              <EvidenceRow items={evidence} title={evidenceTitle} statement={conclusion} expanded={full} onToggleFull={() => setFull((v) => !v)} />
            </div>
            {full ? <RichText text={toPoliteText(narrative)} figures={figures} className="rounded-lg bg-surface-soft px-5 py-4 text-[14px] leading-[1.7] text-ink-deep" /> : null}
          </>
        ) : null}
      </div>
    </section>
  );
}

/** 여신 종합수익 — Agent 해설 + 전년 동기 대비 표 + 이자마진 비중 (시안 158:2) */
function RevenueTab({ overview, headline }: { overview: LoanOverview; headline: Insight | null }) {
  const { revenue } = overview;
  const p = periodOf(overview.asOf);
  const rows = revenueRowsOf(revenue.rows);
  const { total, nim } = rows;
  const cfg = useUiConfig();
  const delta = revenue.narrativeFigures.nim_share_delta;
  const trendPts = revenue.nimShareTrend.filter((pt) => pt.value !== null);
  const prior = trendPts.length >= 2 ? trendPts[trendPts.length - 2] : null;
  const years = pointCount(revenue.nimShareTrend);
  const down = (delta?.value ?? 0) < 0;
  const conclusion = toPoliteSentence(headline?.title ?? (revenue.narrative ? lastSentence(revenue.narrative) : ""));
  const monthLabel = p.month === NO_VALUE ? "누계" : `${p.month} 누계`;
  const unit = rows.total ? UNIT_LABEL[rows.total.current.unit] : "";

  const totalGrowth = total?.diffRate.value ?? null;
  const nimGrowth = nim?.diffRate.value ?? null;
  const compared = totalGrowth !== null && nimGrowth !== null;
  const gap = compared ? Math.abs(totalGrowth - nimGrowth).toFixed(2) : null;
  const nimSlower = compared ? nimGrowth < totalGrowth : false;

  const kpis: Kpi[] = [
    {
      label: "여신 이자마진 비중",
      value: <BigFigure figure={revenue.nimShare} size="hero" />,
      sub:
        delta && delta.value != null && prior ? (
          <span className={clsx("font-bold", down ? "text-attention" : "text-ink-deep")}>
            {down ? "▼" : "▲"} {Math.abs(delta.value).toFixed(2)}%p{"  "}전년 {prior.value?.toFixed(2)}%
          </span>
        ) : null,
    },
    {
      label: "전체 수익 증가율",
      value: total ? <BigFigure figure={total.diffRate} size="title" signed /> : <span className="text-[24px] font-bold text-steel">{NO_VALUE}</span>,
      sub: total ? `${tnText(total.current)} · ${monthLabel}` : null,
    },
    {
      label: "여신 이자마진 증가율",
      value: nim ? <BigFigure figure={nim.diffRate} size="title" signed /> : <span className="text-[24px] font-bold text-steel">{NO_VALUE}</span>,
      sub: nim ? `${tnText(nim.current)}${compared ? ` · 전체보다 ${gap}%p ${nimSlower ? "낮음" : "높음"}` : ""}` : null,
    },
  ];

  return (
    <>
      <AgentBox kpis={kpis} conclusion={conclusion} evidence={revenue.evidence} evidenceTitle="여신 종합수익 해설 근거" narrative={revenue.narrative} figures={revenue.narrativeFigures} />

      <section className="grid grid-cols-1 gap-4 xl:grid-cols-[856fr_520fr]">
        <div className="flex min-w-0 flex-col gap-3 rounded-[10px] border border-hairline-soft bg-canvas px-6 pb-[22px] pt-6">
          <h2 className="flex flex-wrap items-baseline gap-x-2 text-[20px] font-bold leading-[25px] text-ink-deep">
            전년 동기 대비
            <span className="text-[12px] font-normal text-steel">
              {years ? `${years}개년 ` : ""}
              {monthLabel}
              {unit ? ` · 단위 ${unit}` : ""}
            </span>
          </h2>
          <ComparisonTable rows={revenue.rows} asOf={overview.asOf} highlight={(r) => r === nim} sortable />
          {compared && total && nim ? (
            <p className="text-[12px] text-steel">
              여신 이자마진({signedText(nim.diffRate)})이 전체 수익({signedText(total.diffRate)})보다 {nimSlower ? "느리게" : "빠르게"} 늘어 비중이 {down ? "줄었습니다" : "늘었습니다"}.
            </p>
          ) : null}
        </div>

        <ChartCard
          title="여신 이자마진 비중"
          legend={[
            { label: "여신 이자마진", color: "var(--color-primary)", dot: true },
            { label: "기타 수익", color: "var(--color-hairline-soft)", dot: true },
          ]}
          table={{
            columns: [
              { key: "p", label: "시점" },
              { key: "a", label: "여신 이자마진(%)", align: "right" },
              { key: "b", label: "기타 수익(%)", align: "right" },
            ],
            rows: revenue.nimShareTrend.map((pt) => ({
              p: pt.label,
              a: pt.value === null ? NO_VALUE : pt.value.toFixed(2),
              b: pt.value === null ? NO_VALUE : (100 - pt.value).toFixed(2),
            })),
          }}
        >
          <ShareBars points={revenue.nimShareTrend} targetName="여신 이자마진" otherName="기타 수익" referenceAt={threshold(cfg, "shareReferencePct")} />
        </ChartCard>
      </section>
    </>
  );
}

/** 기업여신 · 가계여신 — Agent 해설 + 실적 vs 목표(한도) 추이 + 기업·가계 구성비 (시안 208:2 · 208:297) */
function SegmentTab({ segment, overview, comparison, goals }: { segment: LoanSegmentDetail; overview: LoanOverview; comparison: ComparisonView; goals: Goal[] }) {
  const cfg = useUiConfig();
  const hh = segment.key === "household";
  const p = periodOf(overview.asOf);
  const monthLabel = p.month === NO_VALUE ? "누계" : `${p.month} 누계`;
  const rows = revenueRowsOf(overview.revenue.rows);
  const interestRow = hh ? rows.household : rows.corporate;
  // 가계여신 잔액 관리 한도 — 역할 지정이 없으면 '가계 · 잔액 · 한도형' 목표에서 찾는다
  const limitGoal = hh
    ? (goalByRole(goals, cfg, "hhLimit") ??
      goals.find((g) => g.targetType === "limit" && g.targetFigure?.unit === segment.balance.unit && /가계/.test(`${g.metricLabel} ${g.title}`)))
    : undefined;
  const limitFig: Figure | null =
    limitGoal?.targetFigure ??
    (limitGoal && limitGoal.targetValue != null
      ? { id: `${limitGoal.id}_target`, label: `${limitGoal.metricLabel} 관리 한도`, value: limitGoal.targetValue, unit: limitGoal.unit, decimals: limitGoal.decimals ?? 2, dataOrigin: segment.balance.dataOrigin }
      : null);
  const verdict = segment.gapVerdict;
  const tone = verdict === "breach" ? "text-critical" : verdict === "below" || verdict === "near_limit" ? "text-attention" : "text-steel";

  // 구성비 — 이 부문 계열(이름으로 찾음)
  const shareSeries = comparison.shareSeries.find((s) => s.name.includes(segment.name)) ?? comparison.shareSeries[0];
  const corpShare = comparison.shareSeries.find((s) => s.name.includes("기업")) ?? comparison.shareSeries[0];
  const sharePts = (shareSeries?.points ?? []).filter((pt) => pt.value !== null);
  const firstShare = sharePts[0] ?? null;
  const shareMove = firstShare && segment.share.value != null && firstShare.value != null ? segment.share.value - firstShare.value : null;

  const kpis: Kpi[] = [
    {
      label: `${segment.name} 증가율`,
      value: <BigFigure figure={segment.growth} size="hero" signed />,
      sub:
        segment.goalValue && segment.gap ? (
          <span className={clsx("font-bold", tone)}>
            {(segment.gap.value ?? 0) < 0 ? "▼" : "▲"} {hh ? "관리 한도" : "목표"} {formatSigned(segment.goalValue)} 대비 {formatSigned(segment.gap)}
          </span>
        ) : null,
    },
    hh
      ? {
          label: `${segment.name} 잔액`,
          value: <BigFigure figure={segment.balance} size="title" />,
          sub:
            limitFig && limitFig.value && segment.balance.value != null
              ? `관리 한도 ${formatValue({ ...limitFig, decimals: 0 })}${UNIT_LABEL[limitFig.unit]}의 ${((segment.balance.value / limitFig.value) * 100).toFixed(1)}%`
              : `전년 동기 ${formatSigned(segment.growth)}`,
        }
      : {
          label: `${segment.name} 구성비`,
          value: <BigFigure figure={segment.share} size="title" />,
          sub: firstShare && shareMove !== null ? `${firstShare.label.slice(0, 4)}년 ${firstShare.value?.toFixed(2)}% → ${shareMove > 0 ? "+" : ""}${shareMove.toFixed(2)}%p` : null,
        },
    {
      label: `이자수익 (${monthLabel})`,
      value: <BigFigure figure={asTn(segment.interestRevenue)} size="title" />,
      sub: interestRow ? `전년 동기 ${formatSigned(interestRow.diffRate)}` : null,
    },
  ];

  // 추이 — 1월 ~ 기준월
  const monthly = segment.monthly.map((pt) => ({ label: monthOf(pt.label), value: pt.value }));
  const last = [...segment.monthly].reverse().find((pt) => pt.value !== null)?.value ?? null;
  const base = last !== null && segment.growth.value != null ? last / (1 + segment.growth.value / 100) : null;
  const path = !hh ? targetPath(base, segment.goalValue?.value ?? null, monthly.length) : null;
  const unit = UNIT_LABEL[segment.balance.unit];
  const dec = segment.balance.decimals ?? 2;
  const caption = `${p.year === NO_VALUE ? NO_VALUE : `${p.year}년`} 1–${monthly.length}월 · 단위 ${unit}`;

  const figures: Record<string, Figure> = {
    [segment.balance.id]: segment.balance,
    [segment.growth.id]: segment.growth,
    [segment.share.id]: segment.share,
    [segment.interestRevenue.id]: segment.interestRevenue,
    ...(segment.goalValue ? { [segment.goalValue.id]: segment.goalValue } : {}),
    ...(segment.gap ? { [segment.gap.id]: segment.gap } : {}),
  };

  return (
    <>
      <AgentBox
        kpis={kpis}
        conclusion={segment.narrative ? toPoliteSentence(lastSentence(segment.narrative)) : ""}
        evidence={segment.evidence}
        evidenceTitle={`${segment.name} 해설 근거`}
        narrative={segment.narrative}
        figures={figures}
      />

      <section className="grid grid-cols-1 gap-4 xl:grid-cols-[856fr_520fr]">
        <ChartCard
          title={hh ? `${segment.name} 잔액 vs 관리 한도` : `${segment.name} 실적 vs 목표 경로`}
          legend={
            hh
              ? [
                  { label: `${segment.name} 잔액`, color: "var(--color-primary)" },
                  ...(limitFig ? [{ label: `관리 한도 ${formatValue({ ...limitFig, decimals: 0 })}${UNIT_LABEL[limitFig.unit]}`, color: "var(--color-critical)", dashed: true }] : []),
                ]
              : [
                  { label: "실적", color: "var(--color-primary-deep)" },
                  ...(segment.goalValue ? [{ label: `목표 경로 (연 ${formatSigned(segment.goalValue)})`, color: "var(--color-icon)", dashed: true }] : []),
                  { label: "미달 폭", color: "var(--color-track)", dot: true },
                ]
          }
          caption={caption}
          table={{
            columns: [
              { key: "m", label: "월" },
              { key: "v", label: `잔액(${unit})`, align: "right" },
              ...(path ? [{ key: "t", label: `목표 경로(${unit})`, align: "right" as const }] : []),
            ],
            rows: monthly.map((pt, i) => ({ m: pt.label, v: pt.value === null ? NO_VALUE : pt.value.toFixed(dec), t: path ? path[i].toFixed(dec) : "" })),
          }}
        >
          {monthly.length ? (
            <TrendChart
              width={800}
              height={210}
              ariaLabel={`${segment.name} 월별 잔액`}
              points={monthly}
              target={path ? { name: "목표", values: path.map((v) => Number(v.toFixed(dec))) } : undefined}
              limit={hh && limitFig?.value != null ? { value: limitFig.value, label: "관리 한도" } : undefined}
              gapFill={!hh}
              areaUnder={hh}
              format={(v) => v.toFixed(dec)}
              formatTick={(v) => String(Math.round(v))}
              tooltip={(i) => {
                const v = monthly[i].value;
                const t = path?.[i] ?? (hh ? (limitFig?.value ?? null) : null);
                return {
                  head: `${monthly[i].label} · ${segment.name}`,
                  value: v === null ? NO_VALUE : v.toFixed(dec),
                  unit,
                  rows:
                    v !== null && t !== null
                      ? [
                          { label: hh ? "관리 한도" : "목표 경로", value: `${t.toFixed(dec)}${unit}` },
                          { label: "차이", value: `${v - t > 0 ? "+" : ""}${(v - t).toFixed(dec)}${unit}`, tone: hh ? (v > t ? "danger" : undefined) : v < t ? "warning" : undefined },
                        ]
                      : undefined,
                };
              }}
            />
          ) : (
            <p className="rounded-lg bg-surface-soft px-5 py-8 text-center text-[13px] text-steel">월별 잔액 자료가 없어요.</p>
          )}
        </ChartCard>

        <ChartCard
          title="기업·가계 구성비"
          legend={[
            { label: "기업여신", color: "var(--color-primary)", dot: true },
            { label: "가계여신", color: "var(--color-hairline-soft)", dot: true },
          ]}
          table={{
            columns: [
              { key: "p", label: "시점" },
              { key: "a", label: "기업여신(%)", align: "right" },
              { key: "b", label: "가계여신(%)", align: "right" },
            ],
            rows: (corpShare?.points ?? []).map((pt) => ({
              p: pt.label,
              a: pt.value === null ? NO_VALUE : pt.value.toFixed(2),
              b: pt.value === null ? NO_VALUE : (100 - pt.value).toFixed(2),
            })),
          }}
        >
          <ShareBars points={corpShare?.points ?? []} targetName="기업여신" otherName="가계여신" referenceAt={threshold(cfg, "shareReferencePct")} />
        </ChartCard>
      </section>
    </>
  );
}

/** 기업·가계 비교 — Agent 해설 + 잔액 추이 · 구성비 + 이자수익 규모 · 전년 대비 증가율 (시안 304:2) */
function ComparisonTab({ overview, comparison }: { overview: LoanOverview; comparison: ComparisonView }) {
  const cfg = useUiConfig();
  const { corporate: corp, household: hh } = overview;
  const asOf = comparison.asOf;
  const p = periodOf(asOf);
  const dv = comparison.divergence;
  const isCorp = (name: string) => /기업/.test(name);
  const isHh = (name: string) => /가계/.test(name);

  // 핵심 수치 — 증가율 격차 · 구성비 · 규모 대비 수익률 (모두 산출물에서 계산)
  const gapFig =
    corp.growth.value != null && hh.growth.value != null
      ? derivedFigure({ id: "cmp_growth_gap", label: "가계 − 기업 증가율 격차", value: Number((hh.growth.value - corp.growth.value).toFixed(2)), unit: "PP", decimals: 2, expression: "가계여신 증가율 − 기업여신 증가율", inputs: [], asOf, from: [hh.growth, corp.growth] })
      : null;
  const yieldOf = (seg: LoanSegmentDetail, id: string, label: string) => {
    const tn = asTn(seg.interestRevenue).value;
    const bal = seg.balance.unit === "KRW_TN" ? seg.balance.value : seg.balance.unit === "KRW_BN" && seg.balance.value != null ? seg.balance.value / 10000 : null;
    return tn != null && bal ? derivedFigure({ id, label, value: Number(((tn / bal) * 100).toFixed(3)), unit: "PCT", decimals: 3, expression: "이자수익(누계) ÷ 잔액 × 100", inputs: [], asOf, from: [seg.interestRevenue, seg.balance] }) : null;
  };
  const corpYield = yieldOf(corp, "cmp_corp_yield", "기업여신 수익률 (규모 대비)");
  const hhYield = yieldOf(hh, "cmp_hh_yield", "가계여신 수익률 (규모 대비)");
  const corpShareSeries = comparison.shareSeries.find((s) => isCorp(s.name)) ?? comparison.shareSeries[0];
  const sharePts = (corpShareSeries?.points ?? []).filter((pt) => pt.value !== null);
  const firstShare = sharePts[0] ?? null;
  const lastShare = sharePts[sharePts.length - 1] ?? null;
  const shareMove = firstShare && lastShare ? (lastShare.value as number) - (firstShare.value as number) : null;
  const shareTrend = trendPhrase(corpShareSeries?.points);
  const minus = (v: number, d = 2) => `${v > 0 ? "+" : "−"}${Math.abs(v).toFixed(d)}`;

  const kpis: Kpi[] = [
    {
      label: "가계 − 기업 증가율 격차",
      value: gapFig ? <BigFigure figure={gapFig} size="hero" signed /> : <span className="text-[32px] font-bold text-steel">{NO_VALUE}</span>,
      sub: (
        <span className={clsx("font-bold", (gapFig?.value ?? 0) > 0 ? "text-critical" : "text-ink-deep")}>
          {(gapFig?.value ?? 0) > 0 ? "▲" : "▼"} 가계 {formatSigned(hh.growth)} · 기업 {formatSigned(corp.growth)} (전년 대비)
        </span>
      ),
    },
    {
      label: "기업여신 구성비",
      value: <BigFigure figure={corp.share} size="title" />,
      sub: firstShare && shareMove !== null ? `${firstShare.label} ${firstShare.value?.toFixed(2)}%에서 ${shareTrend ? shareTrend.replace("개년", "년") : "변화"} (${minus(shareMove)}%p)` : null,
    },
    {
      label: "기업여신 수익률 (규모 대비)",
      value: corpYield ? <BigFigure figure={corpYield} size="title" /> : <span className="text-[24px] font-bold text-steel">{NO_VALUE}</span>,
      sub:
        corpYield?.value != null && hhYield?.value != null
          ? `가계 ${hhYield.value.toFixed(3)}% 대비 ${minus(corpYield.value - hhYield.value, 3)}%p ${corpYield.value >= hhYield.value ? "우위" : "열위"}`
          : null,
    },
  ];

  // 잔액 추이 (월)
  const balA = comparison.balanceSeries.find((s) => isCorp(s.name)) ?? comparison.balanceSeries[0];
  const balB = comparison.balanceSeries.find((s) => isHh(s.name)) ?? comparison.balanceSeries[1];
  const months = (balA?.points ?? balB?.points ?? []).map((pt) => monthOf(pt.label));
  const balUnit = UNIT_LABEL[comparison.balanceRows[0]?.current.unit ?? "KRW_TN"];
  const balDec = comparison.balanceRows[0]?.current.decimals ?? 2;
  const lastHhShare = lastShare?.value != null ? 100 - lastShare.value : null;

  // 이자수익 규모 (3개년 8월 누계)
  const intA = comparison.interestRows.find((r) => isCorp(r.label));
  const intB = comparison.interestRows.find((r) => isHh(r.label));
  const years = [p.prev2Ym, p.prevYm, p.ym];
  const yearVals = (r?: ComparisonRow) => (r ? [r.prior2?.value ?? null, r.prior.value, r.current.value] : [null, null, null]);
  const intUnit = intA ? UNIT_LABEL[intA.current.unit] : "";

  // 전년 대비 증가율
  const balRowA = comparison.balanceRows.find((r) => isCorp(r.label));
  const balRowB = comparison.balanceRows.find((r) => isHh(r.label));
  const rateRows = [
    { label: "잔액", a: balRowA?.diffRate.value ?? null, b: balRowB?.diffRate.value ?? null },
    { label: "이자수익", a: intA?.diffRate.value ?? null, b: intB?.diffRate.value ?? null },
  ];
  const hhFaster = rateRows.every((r) => r.a !== null && r.b !== null && r.b > r.a);

  // 결론 한 문장 — 괴리 제목('… — … 방향')은 머리글이라 문장으로 쓰지 않고, 이 화면 수치에서 문장을 만든다.
  // 기조(기업 확대 · 가계 관리)는 괴리 판정(divergence)이 있을 때만 말한다.
  const shareShrinking = shareMove !== null && shareMove < 0;
  const shareYears = sharePts.length;
  const conclusion = dv
    ? hhFaster && shareShrinking
      ? toPoliteSentence(`기조는 기업 확대 · 가계 관리인데, 실제로는 가계가 더 빠르게 늘고 기업 구성비는 ${shareYears >= 2 ? `${shareYears}년째` : ""} 줄고 있어요`.replace(/\s{2,}/g, " "))
      : toPoliteSentence(lastSentence(dv.statement.replace(/\[\[fig:[^\]]+\]\]/g, "")) || dv.title)
    : "";

  return (
    <>
      <AgentBox
        kpis={kpis}
        conclusion={conclusion}
        evidence={dv?.evidence ?? []}
        evidenceTitle={dv?.title ?? "기업·가계 비교 근거"}
        narrative={dv?.statement ?? ""}
        figures={dv?.figures ?? {}}
      />

      <section className="grid grid-cols-1 gap-4 xl:grid-cols-[856fr_520fr]">
        <ChartCard
          title="기업·가계 잔액 추이"
          legend={[
            { label: balA?.name ?? "기업", color: PAIR.a },
            { label: balB?.name ?? "가계", color: PAIR.b },
          ]}
          caption={`${p.year === NO_VALUE ? NO_VALUE : `${p.year}년`} 1–${months.length}월 · 단위 ${balUnit}`}
          table={{
            columns: [
              { key: "m", label: "월" },
              { key: "a", label: `${balA?.name ?? "기업"}(${balUnit})`, align: "right" },
              { key: "b", label: `${balB?.name ?? "가계"}(${balUnit})`, align: "right" },
            ],
            rows: months.map((m, i) => ({ m, a: balA?.points[i]?.value?.toFixed(balDec) ?? NO_VALUE, b: balB?.points[i]?.value?.toFixed(balDec) ?? NO_VALUE })),
          }}
        >
          <PairLine labels={months} a={(balA?.points ?? []).map((pt) => pt.value)} b={(balB?.points ?? []).map((pt) => pt.value)} decimals={balDec} ariaLabel="기업·가계 월별 잔액" />
        </ChartCard>

        <ChartCard
          title="기업·가계 구성비"
          legend={[
            { label: "기업여신", color: PAIR.a, dot: true },
            { label: "가계여신", color: PAIR.b, dot: true },
          ]}
          caption={shareTrend && lastHhShare !== null ? `기업여신 구성비 ${shareTrend.replace("개년", "년")} · 가계여신 ${lastHhShare.toFixed(2)}%로 ${shareMove !== null && shareMove < 0 ? "확대" : "축소"}` : undefined}
          table={{
            columns: [
              { key: "p", label: "시점" },
              { key: "a", label: "기업여신(%)", align: "right" },
              { key: "b", label: "가계여신(%)", align: "right" },
            ],
            rows: (corpShareSeries?.points ?? []).map((pt) => ({ p: pt.label, a: pt.value === null ? NO_VALUE : pt.value.toFixed(2), b: pt.value === null ? NO_VALUE : (100 - pt.value).toFixed(2) })),
          }}
        >
          <ShareBars pair points={corpShareSeries?.points ?? []} targetName="기업여신" otherName="가계여신" referenceAt={threshold(cfg, "shareReferencePct")} />
        </ChartCard>
      </section>

      <section className="grid grid-cols-1 gap-4 xl:grid-cols-[856fr_520fr]">
        <ChartCard
          title={`이자수익 규모 · ${years.filter((y) => y !== NO_VALUE).length}개년`}
          legend={[
            { label: intA?.label ?? "기업", color: PAIR.a, dot: true },
            { label: intB?.label ?? "가계", color: PAIR.b, dot: true },
          ]}
          caption={`매년 ${p.month === NO_VALUE ? NO_VALUE : p.month} 누계 · 단위 ${intUnit} · 원화대출금이자수익 하위 항목`}
          table={{
            columns: [
              { key: "y", label: "시점" },
              { key: "a", label: `${intA?.label ?? "기업"}(${intUnit})`, align: "right" },
              { key: "b", label: `${intB?.label ?? "가계"}(${intUnit})`, align: "right" },
            ],
            rows: years.map((y, i) => ({ y, a: yearVals(intA)[i]?.toLocaleString("ko-KR") ?? NO_VALUE, b: yearVals(intB)[i]?.toLocaleString("ko-KR") ?? NO_VALUE })),
          }}
        >
          <PairColumns labels={years} a={yearVals(intA)} b={yearVals(intB)} ariaLabel={`기업·가계 이자수익 ${years.filter((y) => y !== NO_VALUE).length}개년`} format={(v) => v.toLocaleString("ko-KR")} />
        </ChartCard>

        <ChartCard
          title="전년 대비 증가율"
          legend={[
            { label: "기업여신", color: PAIR.a, dot: true },
            { label: "가계여신", color: PAIR.b, dot: true },
          ]}
          caption={`${p.prevYm} → ${p.ym}${hhFaster ? " · 가계가 잔액·이자수익 모두 더 빠르게 증가" : ""}`}
          table={{
            columns: [
              { key: "k", label: "항목" },
              { key: "a", label: "기업여신", align: "right" },
              { key: "b", label: "가계여신", align: "right" },
            ],
            rows: rateRows.map((r) => ({ k: r.label, a: r.a === null ? NO_VALUE : `${r.a.toFixed(2)}%`, b: r.b === null ? NO_VALUE : `${r.b.toFixed(2)}%` })),
          }}
        >
          <PairHBars rows={rateRows} ariaLabel="기업·가계 전년 대비 증가율" />
        </ChartCard>
      </section>

      {comparison.proxyNote ? (
        <p className="-mt-1 flex items-start gap-1.5 pl-1 text-[12px] leading-[18px] text-steel">
          <svg viewBox="0 0 12 12" width="12" height="12" aria-hidden="true" className="mt-[3px] shrink-0 text-attention">
            <path d="M6 1.2 11.2 10.5H.8Z" fill="currentColor" />
            <path d="M6 4.6v2.7" stroke="var(--color-canvas)" strokeWidth="1.3" strokeLinecap="round" />
            <circle cx="6" cy="8.85" r=".7" fill="var(--color-canvas)" />
          </svg>
          {comparison.proxyNote}
        </p>
      ) : null}
    </>
  );
}
