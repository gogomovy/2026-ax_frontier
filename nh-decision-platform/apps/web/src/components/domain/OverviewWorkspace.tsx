"use client";

import Link from "next/link";
import { useState } from "react";
import clsx from "clsx";
import { FigureText } from "@/components/data/FigureText";
import { MetricStrip, type MetricStripItem } from "@/components/data/MetricStrip";
import { useGoalState } from "@/components/providers/GoalStateProvider";
import { Badge, IconArrowRight, NextStep, ProgressBar, SectionHead, TextLink } from "@/components/ui/primitives";
import { formatFigure, formatSigned } from "@/lib/format";
import { resolveGoal } from "@/lib/goalView";
import { lastStep, revenueRowsOf, trendPhrase } from "@/lib/loanView";
import { NO_VALUE, periodOf } from "@/lib/period";
import type { CapitalView, DomainCardInfo, Figure, Goal, LoanOverview } from "@/lib/types";
import { ScrollRegion } from "@/components/ui/ScrollRegion";

/**
 * STEP 1 — 현황·목표
 * 검토 알림 → 사업부문 선택 → 선택 부문 핵심 지표·현재 경영목표 → 은행 종합목표 → 다음 단계
 */
export function OverviewWorkspace({
  domains,
  goals,
  loan,
  capital,
  pending,
}: {
  domains: DomainCardInfo[];
  goals: Goal[];
  loan: LoanOverview;
  capital: CapitalView;
  pending: { attentions: number; requests: number; proposals: number };
}) {
  const { overrides, proposalActions } = useGoalState();
  const [selected, setSelected] = useState("loan");
  const active = domains.find((d) => d.domainCode === selected);
  const isActive = active?.status === "active";
  const domainGoals = goals.filter((g) => g.domainCode === selected);
  const openProposals = Math.max(0, pending.proposals - Object.keys(proposalActions).length);

  const revenueGoal = goals.find((g) => g.id === "goal-annual-revenue");
  // 기간 · 추세 문구는 산출물 기준일과 계열 값에서 계산한다 (Phase I · 하드코딩 제거)
  const p = periodOf(loan.asOf);
  const nimRow = revenueRowsOf(loan.revenue.rows).nim;
  const shareTrend = trendPhrase(loan.revenue.nimShareTrend);
  const shareStep = lastStep(loan.revenue.nimShareTrend);
  const loanItems: MetricStripItem[] = [
    ...(nimRow ? [{ label: "여신 이자마진 수익", figure: nimRow.current, delta: nimRow.diffRate, caption: `${p.month} 누계` }] : []),
    {
      label: "전체 수익 중 비중",
      figure: loan.revenue.nimShare,
      caption: shareTrend ?? undefined,
      tone: shareStep === "축소" ? "attention" : "default",
    },
    { label: "기업여신 잔액", figure: loan.corporate.balance, delta: loan.corporate.growth },
    {
      label: "가계여신 잔액",
      figure: loan.household.balance,
      delta: loan.household.growth,
      positiveIsGood: false,
    },
  ];
  const { bankTarget } = capital;
  const ceiling = bankTarget.ceiling.value;
  const bankProgress = bankTarget.value.value != null && ceiling ? (bankTarget.value.value / ceiling) * 100 : 0;

  return (
    <div className="shell flex flex-col gap-xxl">
      {/* 검토 알림 — 3단계로 바로 이어지는 단일 진입점 */}
      {openProposals + pending.attentions > 0 ? (
        <Link
          href="/hq/goals"
          className="flex flex-wrap items-center gap-x-lg gap-y-2 rounded-2xl border border-info-line bg-info-faint px-lg py-base"
        >
          <span className="text-[14px] font-bold text-ink-deep">경영목표 검토가 필요한 사항이 있습니다</span>
          <span className="flex flex-wrap items-center gap-x-md gap-y-1 text-[12.5px] text-charcoal">
            <span>
              AI 주목 사항 <b className="tnum text-ink-deep">{pending.attentions}</b>
            </span>
            <span>
              확인·보고 요청 <b className="tnum text-ink-deep">{pending.requests}</b>
            </span>
            <span>
              AI 목표 제안 <b className="tnum text-primary">{openProposals}</b>
            </span>
          </span>
          <span className="ml-auto inline-flex items-center gap-1.5 text-[13px] font-bold text-primary">
            검토하기 <IconArrowRight />
          </span>
        </Link>
      ) : null}

      {/* 사업부문 */}
      <section>
        <SectionHead title="사업부문" hint="부문을 선택하면 현황과 현재 경영목표가 표시됩니다" />
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 xl:grid-cols-7">
          {domains.map((domain) => {
            const on = domain.domainCode === selected;
            const ready = domain.status === "active";
            return (
              <button
                key={domain.domainCode}
                type="button"
                onClick={() => setSelected(domain.domainCode)}
                aria-pressed={on}
                className={clsx(
                  "flex h-[76px] flex-col justify-between rounded-xl border px-base py-3 text-left transition-colors",
                  on
                    ? "border-ink-deep bg-ink-deep text-white"
                    : ready
                      ? "border-hairline-soft bg-canvas"
                      : "border-hairline-soft bg-surface-soft/60",
                )}
              >
                <span className={clsx("text-[14px] font-bold", on ? "text-white" : ready ? "text-ink-deep" : "text-steel")}>
                  {domain.name}
                </span>
                <span className={clsx("text-[12px] tnum", on ? "text-white/75" : ready ? "text-steel" : "text-stone")}>
                  {ready ? (domain.headline ? formatFigure(domain.headline) : NO_VALUE) : "준비 중"}
                </span>
              </button>
            );
          })}
        </div>
      </section>

      {!isActive ? (
        <section className="soft flex flex-col items-center gap-2 px-xl py-section text-center">
          <p className="text-[15px] font-bold text-charcoal">{active?.name} 부문은 준비 중입니다</p>
          <p className="max-w-[520px] text-[13px] leading-relaxed text-steel">
            1차 범위는 여신 부문입니다. 이 부문은 도메인·지표·플레이북 설정만 등록하면 같은 구조로 동작합니다.
          </p>
          <button
            type="button"
            onClick={() => setSelected("loan")}
            className="mt-2 rounded-pill bg-ink-button px-5 py-2.5 text-[13px] font-bold text-white"
          >
            여신 부문 보기
          </button>
        </section>
      ) : (
        <>
          {/* 핵심 지표 */}
          <section>
            <SectionHead
              title="여신 부문 현황"
              hint={`${p.ym} 기준`}
              right={<TextLink href="/hq/analysis">상세 분석</TextLink>}
            />
            <MetricStrip items={loanItems} columns={loanItems.length === 4 ? 4 : 3} />
          </section>

          {/* 현재 경영목표 */}
          <section>
            <SectionHead
              title="현재 경영목표"
              hint={`${domainGoals.length}건 · 종합기획부 확정`}
              right={<TextLink href="/hq/goals">목표 설정</TextLink>}
            />
            <ScrollRegion className="overflow-x-auto rounded-2xl border border-hairline-soft">
              <table className="w-full min-w-[720px] border-collapse text-[13px]">
                <thead>
                  <tr className="bg-surface-soft text-left">
                    <th scope="col" className="px-lg py-2.5 font-bold text-charcoal">경영목표</th>
                    <th scope="col" className="px-base py-2.5 text-right font-bold text-charcoal">실적</th>
                    <th scope="col" className="px-base py-2.5 text-right font-bold text-charcoal">목표 대비</th>
                    <th scope="col" className="px-lg py-2.5 text-right font-bold text-charcoal">상태</th>
                  </tr>
                </thead>
                <tbody>
                  {domainGoals.map((goal) => {
                    const view = resolveGoal(goal, overrides[goal.id]);
                    return (
                      <tr key={goal.id} className="border-t border-hairline-soft">
                        <td className="px-lg py-3">
                          <p className="font-bold text-ink-deep">{view.title}</p>
                          <p className="mt-0.5 text-[11.5px] text-stone">
                            {goal.periodLabel} · {goal.metricLabel}
                          </p>
                        </td>
                        <td className="px-base py-3 text-right">
                          {goal.actual ? <FigureText figure={goal.actual} /> : <span className="text-stone">-</span>}
                        </td>
                        <td className="px-base py-3 text-right">
                          {goal.gap ? (
                            <span className="inline-flex flex-col items-end">
                              <FigureText figure={goal.gap} signed={goal.gapSigned ?? true} />
                              <span className="text-[11px] text-stone">{goal.gapLabel ?? "목표 대비"}</span>
                            </span>
                          ) : (
                            <span className="text-stone">-</span>
                          )}
                        </td>
                        <td className="px-lg py-3 text-right">
                          <span className="inline-flex flex-wrap justify-end gap-1">
                            {view.changed ? <Badge tone="primary">방금 수정</Badge> : null}
                            {!view.changed && view.status === "ai_proposed" ? <Badge tone="info">AI 제안 있음</Badge> : null}
                            {view.verdict ? <Badge tone={view.verdict.tone}>{view.verdict.label}</Badge> : null}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </ScrollRegion>
          </section>

          {/* 은행 종합목표 */}
          <section>
            <SectionHead
              title="은행 종합목표"
              hint="사업부문 목표의 상위 기준 · 지주 한도 이내"
              right={<TextLink href="/hq/capital">산출 기준</TextLink>}
            />
            <div className="grid grid-cols-1 gap-md md:grid-cols-3">
              <TargetCard
                label="총자산 증가율 목표"
                value={bankTarget.value}
                sub={`${bankTarget.ceiling.label} ${formatFigure(bankTarget.ceiling)} · 여유 ${formatSigned(bankTarget.headroom)}`}
                progress={bankProgress}
              />
              <RwaCard rows={capital.rwaAllocation} />
              {revenueGoal?.actual ? (
                <TargetCard
                  label="여신 이자마진 수익"
                  value={revenueGoal.actual}
                  sub={`연간 목표 ${revenueGoal.targetFigure ? formatFigure(revenueGoal.targetFigure) : NO_VALUE} · ${revenueGoal.gapLabel ?? "진행률"} ${revenueGoal.gap ? formatFigure(revenueGoal.gap) : NO_VALUE}`}
                  progress={revenueGoal.gap?.value ?? 0}
                />
              ) : null}
            </div>
          </section>
        </>
      )}

      <NextStep
        step={2}
        title="데이터 분석"
        description="여신 실적을 AI 해설과 함께 확인하고, 목표 조정이 필요한 지점을 찾습니다."
        href="/hq/analysis"
      />
    </div>
  );
}

/**
 * 여신 신용RWA 소진 — 서버가 계산한 부서별 배분 · 사용 · 소진율 수치만 그린다(화면에서 합계 수치를 만들지 않는다).
 * 사용 수치가 하나도 없으면(업로드 전) 빈 상태.
 */
function RwaCard({ rows }: { rows: CapitalView["rwaAllocation"] }) {
  const filled = rows.filter((r) => r.used.value != null || r.usageRate.value != null);
  return (
    <div className="rounded-2xl border border-hairline-soft px-lg py-base" data-rwa-card>
      <p className="text-[12px] text-steel">여신 신용RWA 소진</p>
      {filled.length === 0 ? (
        <p className="mt-3 text-[12.5px] leading-snug text-stone">신용RWA 배분 · 사용 자료가 없습니다. 자료를 올리면 계산됩니다.</p>
      ) : (
        <ul className="mt-2 flex flex-col gap-2">
          {filled.map((r) => (
            <li key={r.org}>
              <div className="flex items-baseline justify-between gap-2 text-[12px]">
                <span className="font-bold text-charcoal">{r.org}</span>
                <span className="text-steel">
                  <FigureText figure={r.used} /> / <FigureText figure={r.allocated} /> · <FigureText figure={r.usageRate} />
                </span>
              </div>
              <div className="mt-1">
                <ProgressBar value={r.usageRate.value ?? 0} tone={(r.usageRate.value ?? 0) > 90 ? "critical" : "primary"} />
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function TargetCard({ label, value, sub, progress }: { label: string; value: Figure; sub: string; progress: number }) {
  return (
    <div className="rounded-2xl border border-hairline-soft px-lg py-base">
      <p className="text-[12px] text-steel">{label}</p>
      <p className="mt-1.5 text-[22px] font-bold leading-none text-ink-deep">
        <FigureText figure={value} strong />
      </p>
      <div className="mt-3">
        <ProgressBar value={progress} tone={progress > 90 ? "critical" : "primary"} />
      </div>
      <p className="mt-2 text-[11.5px] leading-snug text-stone">{sub}</p>
    </div>
  );
}
