import { Chart, TargetGauge } from "@/components/charts/Chart";
import { FigureText } from "@/components/data/FigureText";
import { MetricStrip } from "@/components/data/MetricStrip";
import { AgentNote } from "@/components/domain/AgentNote";
import { Badge, TextLink } from "@/components/ui/primitives";
import { GOAL_VERDICT } from "@/lib/goalView";
import type { LoanSegmentDetail } from "@/lib/types";

/** 기업여신 / 가계여신 상세 (요구사항 LOAN-04 ~ LOAN-09) */
export function SegmentDetail({ segment }: { segment: LoanSegmentDetail }) {
  const isHousehold = segment.key === "household";
  const verdict = segment.gapVerdict ? GOAL_VERDICT[segment.gapVerdict] : null;
  const offTrack = segment.gapVerdict === "below" || segment.gapVerdict === "breach";

  return (
    <>
      <MetricStrip
        items={[
          {
            label: `${segment.name} 잔액 (2026.08말)`,
            figure: segment.balance,
            delta: segment.growth,
            positiveIsGood: !isHousehold,
          },
          { label: "구성비 (기업+가계 기준)", figure: segment.share },
          { label: "이자수익 (8월 누계)", figure: segment.interestRevenue, caption: "2633 손익계산서" },
          {
            label: isHousehold ? "관리목표 대비" : "성장목표 대비",
            figure: segment.gap!,
            signed: true,
            caption: segment.goalLabel,
            tone: offTrack ? "critical" : "attention",
          },
        ]}
      />

      <section className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
        <AgentNote
          text={segment.narrative}
          figures={{
            [segment.balance.id]: segment.balance,
            [segment.growth.id]: segment.growth,
            [segment.share.id]: segment.share,
            [segment.interestRevenue.id]: segment.interestRevenue,
            [segment.goalValue!.id]: segment.goalValue!,
            [segment.gap!.id]: segment.gap!,
          }}
          evidence={segment.evidence}
          evidenceTitle={`${segment.name} 해설 근거`}
        />

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
                <FigureText figure={segment.goalValue!} />
                <span className="ml-1 text-[12px] font-normal text-steel">{isHousehold ? "이하" : "이상"}</span>
              </dd>
            </div>
            <div className="flex items-center justify-between gap-2 border-t border-hairline-soft pt-3">
              <dt className="text-[12.5px] text-steel">판정</dt>
              <dd>{verdict ? <Badge tone={verdict.tone}>{verdict.label}</Badge> : null}</dd>
            </div>
          </dl>
          <TargetGauge
            actual={segment.growth.value ?? 0}
            target={segment.goalValue?.value ?? 0}
            unit="PCT"
            decimals={1}
            tone={offTrack ? "critical" : "primary"}
            targetLabel="목표"
          />
          <p className="mt-4 text-[11.5px] leading-snug text-stone">
            {isHousehold
              ? "관리목표는 상한 개념입니다. 실적이 목표를 넘으면 관리 강화 대상입니다."
              : "성장목표는 하한 개념입니다. 실적이 목표에 못 미치면 실행 강화 대상입니다."}
          </p>
        </div>
      </section>

      <section>
        <h2 className="mb-5 text-[20px] font-bold leading-[1.25] text-ink-deep">추이 <span className="ml-2 text-[12px] font-normal text-steel">월별 잔액(당해) · 3개년 8월말 잔액</span></h2>
        <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
          <div className="rounded-xl border border-hairline-soft bg-canvas p-6">
            <Chart
              kind="line"
              title={`${segment.name} 월별 잔액 (2026년)`}
              unit="KRW_TN"
              decimals={2}
              series={[{ name: segment.name, points: segment.monthly }]}
              zeroBased={false}
            />
          </div>
          <div className="rounded-xl border border-hairline-soft bg-canvas p-6">
            <Chart
              kind="bar"
              title={`${segment.name} 3개년 8월말 잔액`}
              unit="KRW_TN"
              decimals={2}
              series={[{ name: segment.name, points: segment.yearly }]}
            />
          </div>
        </div>
      </section>
    </>
  );
}
