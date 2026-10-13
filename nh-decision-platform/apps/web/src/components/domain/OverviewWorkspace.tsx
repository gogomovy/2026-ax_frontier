"use client";

import Link from "next/link";
import { useState, type ReactNode } from "react";
import clsx from "clsx";
import { BigFigure } from "@/components/data/BigFigure";
import { FigureText } from "@/components/data/FigureText";
import { ChartCard } from "@/components/charts/ChartCard";
import { SemiGauge } from "@/components/charts/SemiGauge";
import { TrendChart, type TrendPoint } from "@/components/charts/TrendChart";
import { ProposalPopup } from "@/components/domain/ProposalPopup";
import { useSector } from "@/components/domain/SectorTitle";
import { useGoalState } from "@/components/providers/GoalStateProvider";
import { IconInfoCircle, IconSparkle } from "@/components/ui/icons";
import { EmptyCard } from "@/components/ui/StateViews";
import { Badge, IconChevron, IconWarn, NextStep } from "@/components/ui/primitives";
import { derivedFigure } from "@/lib/derived";
import { UNIT_LABEL, formatFigure } from "@/lib/format";
import { GOAL_VERDICT, directionSuffix, proposalRange, resolveGoal } from "@/lib/goalView";
import { lastStep, revenueRowsOf, trendPhrase } from "@/lib/loanView";
import { NO_VALUE, periodOf } from "@/lib/period";
import type { CapitalView, DomainCardInfo, Figure, Goal, Insight, LoanOverview, Proposal } from "@/lib/types";

type Verdict = NonNullable<Goal["gapVerdict"]>;

/** 값이 없어 판정할 수 없을 때(업로드 전 빈 템플릿) */
const NO_STATUS = { label: "자료 없음", tone: "neutral" as const, gauge: "primary" as const };

/** 한도형 비율의 상태 — 85% 이상 근접, 100% 이상 초과 */
function limitStatus(pct: number) {
  if (pct >= 100) return { label: "한도 초과", tone: "critical" as const, gauge: "danger" as const };
  if (pct >= 85) return { label: "한도 근접", tone: "attention" as const, gauge: "warning" as const };
  return { label: "정상", tone: "neutral" as const, gauge: "primary" as const };
}

/** 추천 범위가 지금 목표보다 높은지 낮은지 — 한도형 목표는 낮추는 것이 강화 */
function changeWord(goal: Goal, p: Proposal, overridden?: number): string {
  const cur = overridden ?? goal.targetValue;
  const r = p.recommendation;
  const mid = r.mode === "range" ? ((r.low ?? 0) + (r.high ?? 0)) / 2 : (r.value ?? null);
  if (cur === null || cur === undefined || mid === null) return "조정";
  if (mid > cur) return goal.targetType === "limit" ? "완화" : "상향";
  if (mid < cur) return goal.targetType === "limit" ? "강화" : "하향";
  return "유지";
}

/** 이슈로 보여 줄 목표의 심각도 순서 — 초과 > 미달 > 근접 */
const ISSUE_ORDER: Partial<Record<Verdict, number>> = { breach: 0, below: 1, near_limit: 2 };

/**
 * 1단계 — 경영 현황·목표 (가이드 7155 · 7166 · 7167)
 * 은행 종합목표 3장 → 사업부문 박스 탭 → [적용 경영목표 요약 · 주요 이슈 · 핵심 지표 · 추이 차트] → 다음 단계.
 * 이슈에서 [제안 검토]로 AI 제안을 검토해 조정안에 담고, 확정은 3단계에서 한다.
 */
export function OverviewWorkspace({
  domains,
  goals,
  loan,
  capital,
  proposals,
  attentions,
  aside,
}: {
  domains: DomainCardInfo[];
  goals: Goal[];
  loan: LoanOverview;
  capital: CapitalView;
  proposals: Proposal[];
  attentions: Insight[];
  /** 사업부문 아래 · 다음 단계 위에 놓을 내용 (최근 감지된 변화) */
  aside?: ReactNode;
}) {
  const { overrides, proposalActions, staged } = useGoalState();
  const { code, domain, select } = useSector(domains);
  const [reviewId, setReviewId] = useState<string | null>(null);
  const [showAllIssues, setShowAllIssues] = useState(false);
  const active = domain?.status === "active";
  const domainGoals = goals.filter((g) => g.domainCode === code);

  // 기간 · 추세 문구는 산출물 기준일과 계열 값에서 계산한다 (Phase I · 하드코딩 제거)
  const lp = periodOf(loan.asOf);
  const cap = periodOf(capital.asOf);
  const month = cap.month === NO_VALUE ? null : Number(cap.month.replace("월", ""));
  const yearLabel = lp.year === NO_VALUE ? NO_VALUE : `${lp.year}년`;
  const monthCum = lp.month === NO_VALUE ? "누계" : `${lp.month} 누계`;

  /* ── 은행 종합목표 ───────────────────────────────── */
  const bank = capital.bankTarget;
  const bankCeiling = bank.ceiling.value;
  const bankPct = bank.value.value != null && bankCeiling ? (bank.value.value / bankCeiling) * 100 : null;
  const bankStatus = bankPct === null ? NO_STATUS : limitStatus(bankPct);

  // 신용RWA — 서버가 계산한 조직별 배분 · 사용 · 소진율만 쓴다(화면에서 합계 수치를 만들지 않는다)
  const rwaRows = capital.rwaAllocation.filter((r) => r.used.value != null || r.usageRate.value != null);

  const revenueGoal = goals.find((g) => g.id === "goal-annual-revenue");
  const revenueProgress = revenueGoal?.gap?.value ?? null;
  // 연간 경과율 = 기준월 ÷ 12 × 100 — 기준월을 알 때만 계산한다
  const elapsed = month !== null ? (month / 12) * 100 : null;
  const elapsedFig =
    elapsed === null || month === null
      ? null
      : derivedFigure({
          id: "ov_elapsed",
          label: "연간 경과율",
          value: Number(elapsed.toFixed(1)),
          unit: "PCT",
          decimals: 1,
          expression: "기준월 ÷ 12개월 × 100",
          inputs: [{ key: "month", label: "기준월", value: String(month), unit: "월", source: `기준일 ${capital.asOf}` }],
          asOf: capital.asOf,
        });
  const onPlan = revenueProgress !== null && elapsed !== null ? revenueProgress >= elapsed - 5 : null;

  /* ── 선택 부문: 요약 · 이슈 ──────────────────────── */
  const counts = domainGoals.reduce<Record<Verdict, number>>((acc, g) => ({ ...acc, [g.gapVerdict ?? "on_track"]: acc[g.gapVerdict ?? "on_track"] + 1 }), { on_track: 0, near_limit: 0, below: 0, breach: 0 });
  const issues = domainGoals
    .filter((g) => g.gapVerdict && g.gapVerdict in ISSUE_ORDER)
    .sort((a, b) => (ISSUE_ORDER[a.gapVerdict as Verdict] ?? 9) - (ISSUE_ORDER[b.gapVerdict as Verdict] ?? 9));
  const shownIssues = showAllIssues ? issues : issues.slice(0, 2);
  const proposalOf = (goalId: string) => proposals.find((p) => p.targetGoalId === goalId);
  const reviewProposal = proposals.find((p) => p.id === reviewId);
  const flagged = Object.fromEntries(domains.map((d) => [d.domainCode, attentions.some((a) => a.domainCode === d.domainCode)]));

  /* ── 차트 ────────────────────────────────────────── */
  const corpGoal = goals.find((g) => g.id === "goal-corp-growth");
  const corpTarget = corpGoal ? resolveGoal(corpGoal, overrides[corpGoal.id]) : null;
  const corpGrowth = corpGoal ? (overrides[corpGoal.id]?.targetValue ?? corpGoal.targetValue) : null;
  // 목표 경로의 출발점 = 전년 동월 잔액 — 연도별 계열에서 전년 동월 라벨로 찾는다(기준일에서 계산)
  const corpBase = lp.prevYm === NO_VALUE ? null : (loan.corporate.yearly.find((p) => p.label.endsWith(lp.prevYm))?.value ?? null);
  const corpPoints = loan.corporate.monthly;
  const corpPath = corpBase !== null && corpGrowth !== null && corpGrowth !== undefined ? corpPoints.map((_, i) => corpBase * (1 + (corpGrowth / 100) * ((i + 1) / 12))) : null;

  const hhLimitGoal = goals.find((g) => g.id === "goal-hh-balance");
  const hhLimit = hhLimitGoal ? (overrides[hhLimitGoal.id]?.targetValue ?? hhLimitGoal.targetValue) : null;

  // 표기 단위 · 기간은 잔액 수치의 단위와 기준일에서 정한다
  const corpUnit = UNIT_LABEL[loan.corporate.balance.unit] || "";
  const hhUnit = UNIT_LABEL[loan.household.balance.unit] || "";
  const rangeLabel = `${yearLabel} 1~${lp.month === NO_VALUE ? NO_VALUE : lp.month}`;
  const ymOf = (i: number) => (lp.year === NO_VALUE ? NO_VALUE : `${lp.year}.${String(i + 1).padStart(2, "0")}`);
  // 이자마진 비중 계열의 연도 범위 — 라벨에서 연도를 읽는다
  const shareYears = loan.revenue.nimShareTrend.map((p) => p.label).filter(Boolean);
  const shareRange = shareYears.length >= 2 ? `${shareYears[0]}~${shareYears[shareYears.length - 1]}` : shareYears[0] ?? NO_VALUE;
  const nimRow = revenueRowsOf(loan.revenue.rows).nim;
  const shareTrend = trendPhrase(loan.revenue.nimShareTrend);
  const shareStep = lastStep(loan.revenue.nimShareTrend);

  const tn = (v: number) => v.toFixed(2);
  const signed = (v: number, d = 2) => `${v > 0 ? "+" : ""}${v.toFixed(d)}`;

  return (
    <div className="shell flex flex-col gap-10 pb-6">
      {/* 은행 종합목표 */}
      <section aria-labelledby="ov-bank">
        <h2 id="ov-bank" className="mb-5 flex items-center gap-1 text-[20px] font-bold leading-[1.25] text-ink-deep">
          <Link href="/hq/capital" className="inline-flex items-center gap-1 hover:text-primary">
            은행 종합목표
            <IconChevron className="text-steel" />
          </Link>
        </h2>
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
          <BankCard
            title="총자산 증가율 목표"
            status={bankStatus}
            gauge={<SemiGauge percent={bankPct ?? 0} label="한도 소진율" tone={bankStatus.gauge} />}
            main={<BigFigure figure={bank.value} size="kpi" />}
            rows={[
              [bank.ceiling.label || "지주 한도", <FigureText key="c" figure={bank.ceiling} plain strong />],
              ["여유", <FigureText key="h" figure={bank.headroom} signed plain strong />],
            ]}
          />
          <RwaCard rows={rwaRows} />
          {revenueGoal?.actual ? (
            <BankCard
              title="여신 이자마진 수익"
              status={onPlan === null ? NO_STATUS : onPlan ? { label: "계획 수준", tone: "neutral" } : { label: "계획 미달", tone: "attention" }}
              gauge={<SemiGauge percent={revenueProgress ?? 0} label={revenueGoal.gapLabel ?? "목표 진행률"} tone={onPlan === false ? "warning" : "primary"} />}
              main={<BigFigure figure={revenueGoal.actual} size="kpi" />}
              rows={[
                ["연간 목표", <span key="t" className="tnum font-bold text-ink-deep">{revenueGoal.targetFigure ? formatFigure(revenueGoal.targetFigure) : NO_VALUE}</span>],
                ["연간 경과율", elapsedFig ? <FigureText key="e" figure={elapsedFig} plain strong /> : <span key="e" className="text-steel">{NO_VALUE}</span>],
              ]}
            />
          ) : null}
        </div>
      </section>

      {/* 사업부문 */}
      <section aria-labelledby="ov-sector">
        <h2 id="ov-sector" className="mb-5 text-[20px] font-bold leading-[1.25] text-ink-deep">
          사업부문
        </h2>
        <div className="overflow-hidden rounded-xl border border-hairline-soft bg-canvas">
          <div role="tablist" aria-label="사업부문" className="grid grid-cols-2 border-b border-hairline-soft bg-surface-soft sm:grid-cols-4 xl:grid-cols-7">
            {domains.map((d) => {
              const on = d.domainCode === code;
              const ready = d.status === "active";
              const label = d.headline ? d.headline.label.replace(/\(.*\)/, "").replace(d.name, "").trim() || "규모" : "";
              return (
                <button
                  key={d.domainCode}
                  type="button"
                  role="tab"
                  aria-selected={on}
                  onClick={() => select(d.domainCode)}
                  className={clsx("relative flex flex-col items-start gap-1 border-b border-r border-hairline-soft px-6 py-5 text-left transition-colors last:border-r-0 sm:border-b-0", on ? "bg-canvas" : "hover:bg-canvas")}
                >
                  {on ? <span aria-hidden="true" className="absolute inset-x-0 top-0 h-1 bg-primary" /> : null}
                  <span className={clsx("flex items-center gap-1.5 text-[16px] leading-[1.4]", on ? "font-bold text-primary" : "font-bold text-ink-deep")}>
                    {d.name}
                    {flagged[d.domainCode] && !on ? <span aria-label="확인하지 않은 이슈가 있어요" className="h-[7px] w-[7px] rounded-circle bg-critical" /> : null}
                  </span>
                  <span className="tnum text-[14px] text-steel">{ready && d.headline ? `${label} ${formatFigure(d.headline)}` : "준비 중"}</span>
                </button>
              );
            })}
          </div>

          <div role="tabpanel" className="p-7">
            {!active ? (
              <EmptyCard
                className="border-0"
                title="이 부문에 적용된 경영목표가 없어요"
                description="3단계 경영목표 설정에서 목표를 추가하면 현황과 주요 이슈가 여기에 표시돼요."
                actionLabel="경영목표 추가하기"
                href="/hq/goals"
              />
            ) : (
              <div className="flex flex-col gap-6">
                <p className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-[14px]">
                  <b className="font-bold text-ink-deep">
                    적용 경영목표 <span className="tnum">{domainGoals.length}</span>건
                  </b>
                  <span className="text-[12px] text-steel">
                    정상 <b className="tnum text-ink-deep">{counts.on_track}</b> · 한도 근접 <b className="tnum text-ink-deep">{counts.near_limit}</b> · 목표 미달{" "}
                    <b className="tnum text-ink-deep">{counts.below}</b> · 한도 초과 <b className="tnum text-ink-deep">{counts.breach}</b>
                  </span>
                </p>

                {/* 주요 이슈 — AI 영역: primary/100 박스 + 흰 내부 카드 */}
                <div className="rounded-xl bg-info-soft p-5">
                  <div className="mb-4 flex items-center justify-between gap-3">
                    <h3 className="flex items-center gap-2 text-[14px] font-bold text-ink-deep">
                      <IconWarn className="text-ink-deep" />
                      주요 이슈
                    </h3>
                    {issues.length > 2 ? (
                      <button type="button" onClick={() => setShowAllIssues((v) => !v)} className="inline-flex items-center gap-0.5 text-[13px] font-bold text-primary hover:underline">
                        {showAllIssues ? "2건만 보기" : `전체 ${issues.length}건 보기`}
                        <IconChevron className={clsx("transition-transform", showAllIssues && "-rotate-90")} />
                      </button>
                    ) : null}
                  </div>
                  {issues.length === 0 ? (
                    <p className="rounded-lg bg-canvas px-5 py-6 text-center text-[14px] text-steel">지금 확인할 이슈가 없어요.</p>
                  ) : (
                    <ul className="grid grid-cols-1 gap-5 xl:grid-cols-2">
                      {shownIssues.map((g) => {
                        const view = resolveGoal(g, overrides[g.id]);
                        const verdict = GOAL_VERDICT[g.gapVerdict as Verdict];
                        const p = proposalOf(g.id);
                        const acted = p ? proposalActions[p.id] : undefined;
                        const inBasket = p ? Boolean(staged[p.id]) : false;
                        const limit = g.targetType === "limit";
                        const tone = g.gapVerdict === "breach" ? "text-critical" : "text-attention";
                        return (
                          <li key={g.id} className="rounded-lg bg-canvas p-5">
                            <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
                              <div className="flex min-w-0 items-center gap-2">
                                <h4 className="text-[16px] font-bold leading-[1.4] text-ink-deep">{view.title}</h4>
                                <Badge tone={verdict.tone}>{verdict.label}</Badge>
                              </div>
                              <dl className="flex items-baseline gap-4 text-[12px] text-steel">
                                {g.actual ? (
                                  <div className="flex items-baseline gap-1.5">
                                    <dt>실적</dt>
                                    <dd className="text-[14px]">
                                      <FigureText figure={g.actual} plain strong />
                                    </dd>
                                  </div>
                                ) : null}
                                <div className="flex items-baseline gap-1.5">
                                  <dt>{limit ? "한도" : "목표"}</dt>
                                  <dd className="tnum text-[14px] font-bold text-ink-deep">{view.targetLabel}</dd>
                                </div>
                                {g.gap ? (
                                  <div className="flex items-baseline gap-1.5">
                                    <dt>차이</dt>
                                    <dd className="text-[14px]">
                                      <FigureText figure={g.gap} signed={g.gapSigned ?? true} plain className={tone} />
                                    </dd>
                                  </div>
                                ) : null}
                              </dl>
                            </div>
                            {p ? (
                              <div className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg bg-info-faint px-4 py-3">
                                <IconSparkle className="shrink-0 text-primary" />
                                <div className="min-w-0 flex-1 leading-normal">
                                  <p className="text-[13px]">
                                    <b className="font-bold text-primary">AI 목표 수정 제안</b>
                                    <span className="ml-2 text-ink-deep">
                                      목표 {view.targetLabel} → {proposalRange(p)}
                                      {directionSuffix(g)}로 {changeWord(g, p, overrides[g.id]?.targetValue)}
                                    </span>
                                  </p>
                                  <p className="line-clamp-1 text-[12px] text-steel">{p.recommendation.text}</p>
                                </div>
                                {acted ? (
                                  <Badge tone="neutral">처리 완료</Badge>
                                ) : (
                                  <>
                                    {inBasket ? <Badge tone="info">조정안에 담김</Badge> : null}
                                    <button
                                      type="button"
                                      onClick={() => setReviewId(p.id)}
                                      className="inline-flex h-8 shrink-0 items-center gap-0.5 rounded-md border border-hairline bg-canvas px-3 text-[13px] font-bold text-ink-deep hover:bg-surface-soft"
                                    >
                                      제안 검토
                                      <IconChevron />
                                    </button>
                                  </>
                                )}
                              </div>
                            ) : null}
                          </li>
                        );
                      })}
                    </ul>
                  )}
                </div>

                {/* 핵심 지표 */}
                <dl className={clsx("grid grid-cols-2 divide-hairline-soft overflow-hidden rounded-xl border border-hairline-soft lg:divide-x", nimRow ? "lg:grid-cols-4" : "lg:grid-cols-3")}>
                  {nimRow ? (
                    <Kpi label={`여신 이자마진 수익 (${monthCum})`} figure={nimRow.current} caption={<>전년 동기 <FigureText figure={nimRow.diffRate} signed plain className="text-ink-deep" /></>} />
                  ) : null}
                  <Kpi label="전체 수익 중 비중" figure={loan.revenue.nimShare} caption={shareTrend ?? undefined} tone={shareStep === "축소" ? "attention" : undefined} />
                  <Kpi label="기업여신 잔액" figure={loan.corporate.balance} caption={<>증가율 <FigureText figure={loan.corporate.growth} signed plain className="text-ink-deep" />{corpTarget ? <> · 목표 {corpTarget.targetLabel}</> : null}</>} />
                  <Kpi label="가계여신 잔액" figure={loan.household.balance} caption={<>증가율 <FigureText figure={loan.household.growth} signed plain className="text-ink-deep" />{hhLimit ? <> · 한도 {hhLimit.toFixed(2)}{hhUnit}</> : null}</>} />
                </dl>

                {/* 추이 */}
                <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
                  <ChartCard
                    title="기업여신 실적 vs 목표 경로"
                    legend={[
                      { label: "실적", color: "var(--color-primary)" },
                      ...(corpPath ? [{ label: `목표 경로 (연 +${corpGrowth?.toFixed(1)}%)`, color: "var(--chart-4)", dashed: true }] : []),
                    ]}
                    caption={
                      <>
                        {rangeLabel} · 단위 {corpUnit}
                        {corpPath ? <span className="block">목표 경로 = 전년 동기 잔액 × (1 + 연 목표 증가율 × 경과월 ÷ 12)</span> : null}
                      </>
                    }
                    table={{
                      columns: [
                        { key: "m", label: "월" },
                        { key: "a", label: `실적(${corpUnit})`, align: "right" },
                        ...(corpPath ? [{ key: "t", label: `목표 경로(${corpUnit})`, align: "right" as const }, { key: "d", label: `목표 대비(${corpUnit})`, align: "right" as const }] : []),
                      ],
                      rows: corpPoints.map((p, i) => ({
                        m: p.label,
                        a: p.value !== null ? tn(p.value) : "-",
                        t: corpPath ? tn(corpPath[i]) : "",
                        d: corpPath && p.value !== null ? signed(p.value - corpPath[i]) : "",
                      })),
                    }}
                  >
                    <TrendChart
                      ariaLabel={`기업여신 잔액 월별 실적과 목표 경로 — ${corpPoints.map((p) => `${p.label} ${p.value !== null ? tn(p.value) : "-"}${corpUnit}`).join(", ")}`}
                      points={corpPoints}
                      target={corpPath ? { name: "목표", values: corpPath } : undefined}
                      gapFill
                      format={(v) => v.toFixed(2)}
                      formatTick={(v) => v.toFixed(0)}
                      tooltip={(i) => {
                        const v = corpPoints[i].value ?? 0;
                        return {
                          head: `${ymOf(i)} · 기업여신`,
                          value: tn(v),
                          unit: corpUnit,
                          rows: corpPath
                            ? [
                                { label: "목표 경로", value: `${tn(corpPath[i])}${corpUnit}` },
                                { label: "목표 대비", value: `${signed(v - corpPath[i])}${corpUnit}`, tone: v < corpPath[i] ? "warning" : undefined },
                              ]
                            : undefined,
                        };
                      }}
                    />
                  </ChartCard>

                  <ChartCard
                    title="가계여신 잔액 vs 관리 한도"
                    legend={[
                      { label: "가계여신 잔액", color: "var(--color-primary)" },
                      ...(hhLimit ? [{ label: `관리 한도 ${hhLimit.toFixed(0)}${hhUnit}`, color: "var(--color-critical)", dashed: true }] : []),
                    ]}
                    caption={`${rangeLabel} · 단위 ${hhUnit}`}
                    table={{
                      columns: [
                        { key: "m", label: "월" },
                        { key: "a", label: `잔액(${hhUnit})`, align: "right" },
                        ...(hhLimit ? [{ key: "r", label: `한도 여유(${hhUnit})`, align: "right" as const }] : []),
                      ],
                      rows: loan.household.monthly.map((p) => ({ m: p.label, a: p.value !== null ? tn(p.value) : "-", r: hhLimit && p.value !== null ? tn(hhLimit - p.value) : "" })),
                    }}
                  >
                    <TrendChart
                      ariaLabel={`가계여신 잔액 월별 추이와 관리 한도 — ${loan.household.monthly.map((p) => `${p.label} ${p.value !== null ? tn(p.value) : "-"}${hhUnit}`).join(", ")}`}
                      points={loan.household.monthly}
                      limit={hhLimit ? { value: hhLimit, label: "관리 한도" } : undefined}
                      format={(v) => v.toFixed(2)}
                      formatTick={(v) => v.toFixed(0)}
                      tooltip={(i) => {
                        const v = loan.household.monthly[i].value ?? 0;
                        return {
                          head: `${ymOf(i)} · 가계여신`,
                          value: tn(v),
                          unit: hhUnit,
                          rows: hhLimit ? [{ label: "관리 한도", value: `${hhLimit.toFixed(2)}${hhUnit}` }, { label: "한도 여유", value: `${tn(hhLimit - v)}${hhUnit}`, tone: hhLimit - v < 1 ? "danger" : undefined }] : undefined,
                        };
                      }}
                    />
                  </ChartCard>

                  <ChartCard
                    title="여신 이자마진 비중 추이"
                    legend={[{ label: "전체 수익 중 비중", color: "var(--color-primary)" }]}
                    caption={`${shareRange} ${lp.month === NO_VALUE ? "" : `${lp.month} 누계 `}· 단위 %`}
                    table={{
                      columns: [
                        { key: "m", label: "시점" },
                        { key: "v", label: "비중(%)", align: "right" },
                      ],
                      rows: loan.revenue.nimShareTrend.map((p) => ({ m: p.label, v: p.value !== null ? p.value.toFixed(2) : "-" })),
                    }}
                  >
                    <NimTrend points={loan.revenue.nimShareTrend} />
                  </ChartCard>
                </div>
              </div>
            )}
          </div>
        </div>
      </section>

      {aside}

      <NextStep step={2} title="데이터 분석" description={`${domain?.name ?? "여신"} 부문 이슈를 Agent 해설과 함께 분석하고, 목표 조정이 필요한 지점을 찾아요.`} href="/hq/analysis" cta="분석 시작" />

      {reviewProposal ? <ProposalPopup proposal={reviewProposal} goal={goals.find((g) => g.id === reviewProposal.targetGoalId)} onClose={() => setReviewId(null)} /> : null}
    </div>
  );
}

/**
 * 여신 신용RWA 소진 — 서버가 계산한 조직별 배분 · 사용 · 소진율 수치만 그린다(화면에서 합계 수치를 만들지 않는다).
 * 사용 수치가 하나도 없으면(업로드 전) 빈 상태.
 */
function RwaCard({ rows }: { rows: CapitalView["rwaAllocation"] }) {
  const worst = rows.reduce<number | null>((m, r) => (r.usageRate.value == null ? m : m === null ? r.usageRate.value : Math.max(m, r.usageRate.value)), null);
  const status = worst === null ? NO_STATUS : limitStatus(worst);
  return (
    <article className="rounded-xl border border-hairline-soft bg-canvas p-6" data-rwa-card>
      <header className="flex items-center justify-between gap-2">
        <h3 className="flex items-center gap-1.5 text-[14px] text-steel">
          여신 신용RWA 소진
          <IconInfoCircle className="text-icon" />
        </h3>
        <Badge tone={status.tone}>{status.label}</Badge>
      </header>
      {rows.length === 0 ? (
        <p className="mt-4 text-[13px] leading-snug text-steel">신용RWA 배분 · 사용 자료가 없습니다. 자료를 올리면 계산됩니다.</p>
      ) : (
        <ul className="mt-4 flex flex-col gap-3">
          {rows.map((r) => (
            <li key={r.org}>
              <div className="flex items-baseline justify-between gap-2 text-[13px]">
                <span className="font-bold text-ink-deep">{r.org}</span>
                <span className="tnum text-steel">
                  <FigureText figure={r.used} plain /> / <FigureText figure={r.allocated} plain /> · <FigureText figure={r.usageRate} plain strong />
                </span>
              </div>
              <div className="mt-1.5 h-1.5 overflow-hidden rounded-pill bg-track" role="presentation">
                <div className={clsx("h-full rounded-pill", (r.usageRate.value ?? 0) >= 100 ? "bg-critical" : (r.usageRate.value ?? 0) >= 85 ? "bg-attention" : "bg-primary")} style={{ width: `${Math.min(100, Math.max(0, r.usageRate.value ?? 0))}%` }} />
              </div>
            </li>
          ))}
        </ul>
      )}
    </article>
  );
}

function NimTrend({ points }: { points: TrendPoint[] }) {
  return (
    <TrendChart
      ariaLabel={`여신 이자마진 비중 추이 — ${points.map((p) => `${p.label} ${p.value}%`).join(", ")}`}
      points={points}
      format={(v) => `${v.toFixed(2)}%`}
      formatTick={(v) => `${v.toFixed(1)}%`}
      tooltip={(i) => {
        const v = points[i].value ?? 0;
        const prev = i > 0 ? points[i - 1].value : null;
        return {
          head: `${points[i].label} · 여신 이자마진`,
          value: v.toFixed(2),
          unit: "%",
          rows: prev !== null && prev !== undefined ? [{ label: "전기 대비", value: `${v - prev > 0 ? "+" : ""}${(v - prev).toFixed(2)}%p`, tone: v < prev ? "warning" : undefined }] : undefined,
        };
      }}
    />
  );
}

function BankCard({
  title,
  status,
  gauge,
  main,
  rows,
}: {
  title: string;
  status: { label: string; tone: "neutral" | "attention" | "critical" };
  gauge: React.ReactNode;
  main: React.ReactNode;
  rows: [string, React.ReactNode][];
}) {
  return (
    <article className="rounded-xl border border-hairline-soft bg-canvas p-6">
      <header className="flex items-center justify-between gap-2">
        <h3 className="flex items-center gap-1.5 text-[14px] text-steel">
          {title}
          <IconInfoCircle className="text-icon" />
        </h3>
        <Badge tone={status.tone}>{status.label}</Badge>
      </header>
      <div className="mt-4 flex flex-wrap items-center gap-x-6 gap-y-4">
        {gauge}
        <div className="min-w-[150px] flex-1">
          {main}
          <dl className="mt-3 flex flex-col gap-2 border-t border-hairline-soft pt-3">
            {rows.map(([label, value]) => (
              <div key={label} className="flex items-center justify-between gap-3 text-[13px]">
                <dt className="text-steel">{label}</dt>
                <dd className="text-[14px]">{value}</dd>
              </div>
            ))}
          </dl>
        </div>
      </div>
    </article>
  );
}

function Kpi({ label, figure, caption, tone }: { label: string; figure: Figure; caption?: React.ReactNode; tone?: "attention" }) {
  return (
    <div className="border-b border-hairline-soft px-6 py-5 last:border-b-0 lg:border-b-0">
      <dt className="flex items-center gap-1.5 text-[14px] text-steel">
        {label}
        <IconInfoCircle className="text-icon" />
      </dt>
      <dd className="mt-2">
        <BigFigure figure={figure} size="kpi" />
        {caption ? <p className={clsx("mt-1.5 text-[12px]", tone === "attention" ? "font-bold text-attention" : "text-steel")}>{caption}</p> : null}
      </dd>
    </div>
  );
}
