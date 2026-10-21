import { Chart, TargetGauge } from "@/components/charts/Chart";
import { FigureText } from "@/components/data/FigureText";
import { MetricStrip, type MetricStripItem } from "@/components/data/MetricStrip";
import { AgentNote } from "@/components/domain/AgentNote";
import { Badge, TextLink } from "@/components/ui/primitives";
import { UNIT_LABEL, formatFigure } from "@/lib/format";
import { GOAL_VERDICT } from "@/lib/goalView";
import { pointCount, sourceLabel } from "@/lib/loanView";
import { NO_VALUE, periodOf } from "@/lib/period";
import { gapBasisText } from "@/lib/periodBasis";
import type { Figure, LoanSegmentDetail } from "@/lib/types";

/**
 * 기업여신 / 가계여신 상세 (요구사항 LOAN-04 ~ LOAN-09).
 * 기간 라벨은 산출물 기준일(asOf)에서, 차트 단위는 잔액 수치의 단위에서 정한다 — 목표 · 이탈 수치가 없으면 해당 칸을 그리지 않는다.
 */
export function SegmentDetail({ segment, asOf }: { segment: LoanSegmentDetail; asOf?: string | null }) {
  const isHousehold = segment.key === "household";
  const verdict = segment.gapVerdict ? GOAL_VERDICT[segment.gapVerdict] : null;
  const offTrack = segment.gapVerdict === "below" || segment.gapVerdict === "breach";
  const p = periodOf(asOf);
  const monthEnd = p.month === NO_VALUE ? NO_VALUE : `${p.month}말`;
  const yearLabel = p.year === NO_VALUE ? NO_VALUE : `${p.year}년`;
  // 연도별 비교 시점 수 — 값이 있는 시점만 센다 (예: 3개년)
  const years = pointCount(segment.yearly);
  const yearlyLabel = `${years ? `${years}개년 ` : ""}${monthEnd} 잔액`;
  const { gap, goalValue } = segment;
  const aligned = segment.gapBasis?.aligned;
  const basisText = gapBasisText(segment.gapBasis, goalValue ? UNIT_LABEL[goalValue.unit] : "");

  const items: MetricStripItem[] = [
    {
      label: `${segment.name} 잔액 (${p.ym === NO_VALUE ? NO_VALUE : `${p.ym}말`})`,
      figure: segment.balance,
      delta: segment.growth,
      positiveIsGood: !isHousehold,
    },
    { label: "구성비 (기업+가계 기준)", figure: segment.share },
    // 출처는 계산 추적의 원천(파일 · 표)에서 (Phase K · HC-04 — 보고서 번호를 코드에 두지 않는다)
    { label: `이자수익 (${p.month} 누계)`, figure: segment.interestRevenue, caption: sourceLabel(segment.interestRevenue) },
  ];
  if (gap) {
    items.push({
      label: isHousehold ? "관리목표 대비" : "성장목표 대비",
      figure: gap,
      signed: true,
      caption: segment.goalLabel,
      tone: offTrack ? "critical" : "attention",
    });
  }

  const noteFigures: Record<string, Figure> = {
    [segment.balance.id]: segment.balance,
    [segment.growth.id]: segment.growth,
    [segment.share.id]: segment.share,
    [segment.interestRevenue.id]: segment.interestRevenue,
    ...(goalValue ? { [goalValue.id]: goalValue } : {}),
    ...(gap ? { [gap.id]: gap } : {}),
  };
  const balanceUnit = segment.balance.unit;
  const balanceDecimals = segment.balance.decimals ?? 2;
  const showGauge = segment.growth.value != null && goalValue?.value != null;

  return (
    <>
      <MetricStrip items={items} columns={items.length === 4 ? 4 : 3} />

      <section className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
        <AgentNote text={segment.narrative} figures={noteFigures} evidence={segment.evidence} evidenceTitle={`${segment.name} 해설 근거`} />

        {/* 현재 경영목표 대비 (LOAN-06 / LOAN-09) */}
        <div className="rounded-xl border border-hairline-soft bg-canvas p-6">
          <div className="flex items-baseline justify-between gap-base">
            <p className="text-[16px] font-bold text-ink-deep">현재 경영목표 대비</p>
            <TextLink href="/hq/goals">목표 설정</TextLink>
          </div>
          <dl className="mt-3 flex flex-col gap-3">
            <div className="flex items-baseline justify-between gap-2">
              <dt className="text-[12.5px] text-steel">현재 증가율</dt>
              <dd className="text-[20px] font-bold text-ink-deep">
                <FigureText figure={segment.growth} signed strong />
              </dd>
            </div>
            <div className="flex items-baseline justify-between gap-2 border-t border-hairline-soft pt-3">
              <dt className="text-[12.5px] text-steel">경영목표</dt>
              <dd className="text-[20px] font-bold text-charcoal">
                {goalValue ? (
                  <>
                    <FigureText figure={goalValue} />
                    <span className="ml-1 text-[12px] font-normal text-steel">{isHousehold ? "이하" : "이상"}</span>
                  </>
                ) : (
                  <span className="text-stone">{NO_VALUE}</span>
                )}
              </dd>
            </div>
            {/* 실적이 원래와 다른 비교 기간이면(전년 동기 자료 없음) 목표를 그 기간으로 환산해 판정한다 — 판정 · 게이지가 같은 기준 */}
            {goalValue && typeof aligned === "number" ? (
              <div className="flex items-baseline justify-between gap-2 border-t border-hairline-soft pt-3" title={segment.gapBasis?.note}>
                <dt className="text-[12.5px] text-steel">{segment.gapBasis?.months}개월 환산 목표</dt>
                <dd className="text-[16px] font-bold text-charcoal tnum">{formatFigure({ ...goalValue, value: aligned, decimals: 2 })}</dd>
              </div>
            ) : null}
            <div className="flex items-center justify-between gap-2 border-t border-hairline-soft pt-3">
              <dt className="text-[12.5px] text-steel">판정</dt>
              <dd className="flex flex-col items-end gap-0.5">
                {verdict ? <Badge tone={verdict.tone}>{verdict.label}</Badge> : <span className="text-[12px] text-stone">{NO_VALUE}</span>}
                {basisText ? <span className="text-[11px] text-steel">{basisText}</span> : null}
              </dd>
            </div>
          </dl>
          {showGauge ? (
            <TargetGauge
              actual={segment.growth.value ?? 0}
              target={typeof aligned === "number" ? aligned : (goalValue?.value ?? 0)}
              unit={goalValue?.unit ?? segment.growth.unit}
              decimals={goalValue?.decimals ?? 1}
              tone={offTrack ? "critical" : "primary"}
              targetLabel="목표"
            />
          ) : null}
          <p className="mt-4 text-[11.5px] leading-snug text-stone">
            {isHousehold
              ? "관리목표는 상한 개념입니다. 실적이 목표를 넘으면 관리 강화 대상입니다."
              : "성장목표는 하한 개념입니다. 실적이 목표에 못 미치면 실행 강화 대상입니다."}
          </p>
        </div>
      </section>

      <section>
        <h2 className="mb-5 text-[20px] font-bold leading-[1.25] text-ink-deep">추이 <span className="ml-2 text-[12px] font-normal text-steel">월별 잔액(당해) · {yearlyLabel}</span></h2>
        <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
          <div className="rounded-xl border border-hairline-soft bg-canvas p-6">
            <Chart
              kind="line"
              title={`${segment.name} 월별 잔액 (${yearLabel})`}
              unit={balanceUnit}
              decimals={balanceDecimals}
              series={[{ name: segment.name, points: segment.monthly }]}
              zeroBased={false}
            />
          </div>
          <div className="rounded-xl border border-hairline-soft bg-canvas p-6">
            <Chart
              kind="bar"
              title={`${segment.name} ${yearlyLabel}`}
              unit={balanceUnit}
              decimals={balanceDecimals}
              series={[{ name: segment.name, points: segment.yearly }]}
            />
          </div>
        </div>
      </section>
    </>
  );
}
