"use client";

import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import Link from "next/link";
import clsx from "clsx";
import { FigureText } from "@/components/data/FigureText";
import { GoalChangeDialog } from "@/components/domain/GoalChangeDialog";
import { ProposalPopup } from "@/components/domain/ProposalPopup";
import { useGoalState } from "@/components/providers/GoalStateProvider";
import { useUiConfig } from "@/components/providers/SessionProvider";
import { useUi } from "@/components/providers/UiProvider";
import { useSeen } from "@/components/ui/useSeen";
import { BAND_CELL, BAND_FOOT, Fig, StatusMark, SummaryTile, TAG_TONE, Tag, type MarkTone, type Tone } from "@/components/domain/overviewKit";
import { derivedFigure } from "@/lib/derived";
import { UNIT_LABEL, formatFigure } from "@/lib/format";
import { isArchived } from "@/lib/goalChange";
import { GOAL_VERDICT, resolveGoal } from "@/lib/goalView";
import { NO_VALUE, periodOf } from "@/lib/period";
import { signatureOf } from "@/lib/seen";
import { bandOf, goalByRole, threshold, type Band } from "@/lib/uiConfig";
import type { CapitalView, DomainCardInfo, Figure, Goal, Insight, LoanOverview, Proposal } from "@/lib/types";

type Verdict = NonNullable<Goal["gapVerdict"]>;
type Status = { label: string; tone: Tone };

/** 값이 없어 판정할 수 없을 때 */
const NO_STATUS: Status = { label: "자료 없음", tone: "neutral" };

/** 한도형 비율의 상태 — 구간은 관리자 [화면 설정]의 판정 구간 */
function bandStatus(value: number | null, bands: Band[] | undefined): Status {
  const b = bandOf(value, bands);
  return b
    ? { label: b.label, tone: { neutral: "neutral", info: "info", positive: "success", attention: "attention", critical: "critical" }[b.tone] as Tone }
    : NO_STATUS;
}

/** 판정 → 목표 상태 칸 배경 색 (의미 토큰만 · 시안 3 색 규칙)
 *  정상 neutral/200 · 한도 근접 warning/500 · 목표 미달 warning/700(진한 주황) · 한도 초과 danger/500 */
const SEG_BG: Record<Verdict, string> = {
  // 정상 칸은 흰 카드 위에서도 보이도록 neutral/200 중 한 단계 진한 선 색(hairline)을 쓴다 — hairline-soft 는 흰 바탕에서 거의 안 보였다
  on_track: "bg-hairline",
  near_limit: "bg-attention",
  below: "bg-[var(--color-attention-text)]",
  breach: "bg-critical",
};

const VERDICT_ORDER: Verdict[] = ["on_track", "near_limit", "below", "breach"];

/** 상태 색 → 진행 막대 색 (의미 토큰만) */
function barClass(tone: Tone): string {
  if (tone === "critical") return "bg-critical";
  if (tone === "attention") return "bg-attention";
  if (tone === "success") return "bg-success";
  return "bg-primary";
}

/** 얇은 수평 진행 막대 — 게이지 대신. height 지정(기본 4px) */
function Bar({ percent, tone, h = 4 }: { percent: number; tone: Tone; h?: number }) {
  return (
    <div className="w-full overflow-hidden rounded-pill bg-track" style={{ height: h }} role="presentation">
      <div className={clsx("h-full origin-left rounded-pill motion-safe:animate-grow-x", barClass(tone))} style={{ width: `${Math.min(100, Math.max(0, percent))}%` }} />
    </div>
  );
}

/** 목표 1건 = 작은 칸 1개를 2px 간격으로 나열 (시안 3 · 색 규칙은 SEG_BG) */
function GoalCells({ counts, size = "sm" }: { counts: Record<Verdict, number>; size?: "sm" | "row" }) {
  const total = VERDICT_ORDER.reduce((s, v) => s + counts[v], 0);
  if (total === 0) return <span className="text-[12px] text-steel">–</span>;
  // 띠(sm): 시안 3처럼 칸 폭 전체를 채운다 — 목표 1건 = 1칸, 칸은 같은 폭으로 나눠 갖는다(간격 2px).
  // 표(row): 18×8px 고정 칸 · 간격 3px
  const cell = size === "row" ? "h-2 w-[18px] rounded-[2px]" : "h-2 min-w-[6px] flex-1 rounded-[2px]";
  return (
    <div className={clsx("flex", size === "row" ? "flex-wrap gap-[3px]" : "w-full gap-[2px]")} role="presentation">
      {VERDICT_ORDER.flatMap((v) => Array.from({ length: counts[v] }, (_, i) => <span key={`${v}-${i}`} className={clsx(cell, SEG_BG[v])} />))}
    </div>
  );
}

function emptyCounts(): Record<Verdict, number> {
  return { on_track: 0, near_limit: 0, below: 0, breach: 0 };
}

/** 판정 → 항목 상태 표시 색 (점 + 글자, 공용 StatusMark) */
const VERDICT_MARK: Record<Verdict, MarkTone> = {
  on_track: "neutral",
  near_limit: "attention",
  below: "attention",
  breach: "critical",
};

/**
 * 목업 — 종기부 시안 3 · 은행 띠 + 부문 표 + 상세 패널 (비파괴 미리보기).
 * 제목 줄 · 은행 종합목표 띠(카드 1장) · (왼쪽) 사업부문 목표 상태 표 · (오른쪽) 선택 부문 상세(카드 1장).
 * 수치는 모두 산출물(Figure · 계산 결과 · 집계)에서만 온다 — 리터럴 수치를 넣지 않는다.
 */
export function OverviewMockup({
  domains,
  goals: allGoals,
  loan,
  capital,
  proposals,
  attentions,
  tools,
}: {
  domains: DomainCardInfo[];
  goals: Goal[];
  loan: LoanOverview;
  capital: CapitalView;
  proposals: Proposal[];
  attentions: Insight[];
  tools?: ReactNode;
}) {
  const { overrides, staged, unstageProposal, proposalActions } = useGoalState();
  const { showToast } = useUi();
  const cfg = useUiConfig();
  const seen = useSeen();
  const [reviewId, setReviewId] = useState<string | null>(null);
  // 처리 완료 옆 [되돌리기] — 공용 되돌리기 다이얼로그 대상 목표
  const [revertId, setRevertId] = useState<string | null>(null);
  // 삭제(보관)한 목표는 현황 · 집계에서 뺀다 (변경 이력에는 남음)
  const goals = useMemo(() => allGoals.filter((g) => !isArchived(overrides[g.id])), [allGoals, overrides]);

  // 기간 라벨 — 기준일에서 계산
  const lp = periodOf(loan.asOf);
  const cap = periodOf(capital.asOf);
  const month = cap.month === NO_VALUE ? null : Number(cap.month.replace("월", ""));

  /* ── 이슈 순위 · 부문별 집계 ─────────────────────────── */
  const rank = (v: string | null | undefined) => (v ? cfg.issueOrder.indexOf(v) : -1);
  const goalsOf = (domainCode: string) => goals.filter((g) => g.domainCode === domainCode);
  const issuesOf = (domainCode: string) => goalsOf(domainCode).filter((g) => rank(g.gapVerdict) >= 0).sort((a, b) => rank(a.gapVerdict) - rank(b.gapVerdict));
  const countsOf = (domainCode: string) =>
    goalsOf(domainCode).reduce<Record<Verdict, number>>((acc, g) => ({ ...acc, [g.gapVerdict ?? "on_track"]: acc[g.gapVerdict ?? "on_track"] + 1 }), emptyCounts());

  // 레드닷 = 그 부문의 확인하지 않은 새 이슈
  const dotSig = (domainCode: string) => signatureOf(attentions.filter((a) => a.domainCode === domainCode).map((a) => a.id), capital.asOf);
  const dotKey = (domainCode: string) => `ovm.domain.${domainCode}`;
  const flagged = Object.fromEntries(domains.map((d) => [d.domainCode, seen.fresh(dotKey(d.domainCode), dotSig(d.domainCode))]));

  // 데이터 있는 부문을 위로, 준비 중 부문을 아래로
  const sortedDomains = useMemo(
    () => [...domains].sort((a, b) => (a.status === b.status ? 0 : a.status === "active" ? -1 : 1)),
    [domains],
  );

  // 선택 부문 — 기본은 첫 활성 부문
  const firstActive = domains.find((d) => d.status === "active")?.domainCode ?? domains[0]?.domainCode ?? "";
  const [selected, setSelected] = useState(firstActive);
  const selDomain = domains.find((d) => d.domainCode === selected) ?? null;
  const selActive = selDomain?.status === "active";

  useEffect(() => {
    if (selected) seen.mark(dotKey(selected), dotSig(selected));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 선택 부문 · 이슈가 바뀔 때만
  }, [selected, attentions, capital.asOf]);

  /* ── 전사 집계 ───────────────────────────────────────── */
  const totalCounts = goals.reduce<Record<Verdict, number>>((acc, g) => ({ ...acc, [g.gapVerdict ?? "on_track"]: acc[g.gapVerdict ?? "on_track"] + 1 }), emptyCounts());
  const reviewDomainCount = domains.filter((d) => issuesOf(d.domainCode).length > 0).length;
  const normalDomainCount = domains.filter((d) => d.status === "active" && issuesOf(d.domainCode).length === 0).length;
  // 확인 필요 건수 = 전사 이슈 판정 건수 합
  const attentionCount = totalCounts.breach + totalCounts.below + totalCounts.near_limit;

  // 집계 수치는 Figure 로 (계산 추적 가능)
  const asOf = capital.asOf;
  const countFig = (id: string, label: string, value: number, expression: string): Figure =>
    derivedFigure({ id, label, value, unit: "CNT", decimals: 0, expression, inputs: [], asOf });

  const totalGoalsFig = countFig("ovm_goals", "적용 경영목표 수", goals.length, "전 부문 적용 경영목표 건수 합");

  /* ── 은행 종합목표 ───────────────────────────────────── */
  const bank = capital.bankTarget;
  const bankCeiling = bank.ceiling.value;
  const bankPct = bank.value.value != null && bankCeiling ? (bank.value.value / bankCeiling) * 100 : null;
  const bankStat = bandStatus(bankPct, cfg.bands.limitUsage);
  const bankPctFig =
    bankPct === null
      ? null
      : derivedFigure({
          id: "ovm_bank_usage",
          label: "지주 한도 소진율",
          value: Number(bankPct.toFixed(1)),
          unit: "PCT",
          decimals: 1,
          expression: "총자산 증가율 목표 ÷ 지주 한도 × 100",
          inputs: [],
          asOf,
          from: [bank.value, bank.ceiling],
        });

  // 신용RWA — 서버가 계산한 조직별 배분 · 사용 · 소진율만
  const rwaRows = capital.rwaAllocation.filter((r) => r.used.value != null || r.usageRate.value != null);
  const rwaWorst = rwaRows.reduce<number | null>((m, r) => (r.usageRate.value == null ? m : m === null ? r.usageRate.value : Math.max(m, r.usageRate.value)), null);
  const rwaStat = bandStatus(rwaWorst, cfg.bands.rwaUsage);
  const rwaWorstRow = rwaRows.find((r) => r.usageRate.value === rwaWorst) ?? rwaRows[0] ?? null;

  // 역할로 지정된 목표 (은행 종합목표 = 여신 이자마진 수익)
  const revenueGoal = goalByRole(goals, cfg, "bankRevenue");
  const revenueProgress = revenueGoal?.gap?.value ?? null;
  const revenueProgressFig = revenueGoal?.gap ?? null;
  // 연간 경과율 = 기준월 ÷ 12 × 100
  const elapsed = month !== null ? (month / 12) * 100 : null;
  const elapsedFig =
    elapsed === null || month === null
      ? null
      : derivedFigure({
          id: "ovm_elapsed",
          label: "연간 경과율",
          value: Number(elapsed.toFixed(1)),
          unit: "PCT",
          decimals: 1,
          expression: "기준월 ÷ 12개월 × 100",
          inputs: [{ key: "month", label: "기준월", value: String(month), unit: "월", source: `기준일 ${capital.asOf}` }],
          asOf: capital.asOf,
        });
  // 경과 대비 진행률 차이 (pp) — 진행률 − 경과율
  const paceGap =
    revenueProgress !== null && elapsed !== null
      ? derivedFigure({ id: "ovm_pace_gap", label: "경과 대비", value: Number((revenueProgress - elapsed).toFixed(1)), unit: "PP", decimals: 1, expression: "목표 진행률 − 연간 경과율", inputs: [], asOf })
      : null;
  const tolerance = threshold(cfg, "planPaceTolerancePp");
  const onPlan = revenueProgress !== null && elapsed !== null && tolerance !== null ? revenueProgress >= elapsed - tolerance : null;

  /* ── 상세 차트 · 요약 (여신 이자마진 수익 누적) ─────────
   * 데이터에 '월별 누적 이자마진 수익' 계열이 없어, 실데이터(누적 실적 revenueGoal.actual ·
   * 연간 목표 revenueGoal.targetFigure)에서 월 경과에 비례한 누적 경로를 파생한다.
   * — 리터럴 수치를 박지 않는다(마지막 실적점 = 누적 실적값, 계획선 = 연간 목표 × 월/12). */
  const revActual = revenueGoal?.actual?.value ?? null; // 누적 실적 (조원)
  const revTarget = revenueGoal?.targetFigure?.value ?? null; // 연간 목표 (조원)
  const revUnit = UNIT_LABEL[revenueGoal?.actual?.unit ?? revenueGoal?.targetFigure?.unit ?? "KRW_TN"];
  const MONTHS = 12;
  const tn = (v: number) => v.toFixed(2);
  const signed = (v: number, d = 2) => `${v > 0 ? "+" : ""}${v.toFixed(d)}`;

  // 실적 누적 — 1~기준월, 월별 균등 적립 가정으로 기준월에 누적 실적에 도달
  const actualPts =
    revActual !== null && month !== null
      ? Array.from({ length: month }, (_, i) => ({ label: `${i + 1}월`, value: Number(((revActual * (i + 1)) / month).toFixed(2)) }))
      : [];
  // 계획선 — 1~12월, 연간 목표를 12개월 균등 적립 (없으면 미표시)
  const planVals = revTarget !== null ? Array.from({ length: MONTHS }, (_, i) => Number(((revTarget * (i + 1)) / MONTHS).toFixed(2))) : null;
  // 연말 예상 — 기준월 실적 추세를 12월까지 연장 (기준월 누적 ÷ 월 × 12)
  const yearEndEst = revActual !== null && month !== null ? Number(((revActual / month) * MONTHS).toFixed(2)) : null;
  // 차트 x축 1~12월 (실적은 기준월까지만 값, 이후 null)
  const chartPts = Array.from({ length: MONTHS }, (_, i) => ({ label: `${i + 1}월`, value: i < actualPts.length ? actualPts[i].value : null }));
  const hasChart = actualPts.length > 0;
  // 연말 예상 투영선 — 기준월 실적에서 12월 연말 예상까지 선형 (기준월 이전은 null). primary 짧은 점선.
  const projVals =
    revActual !== null && yearEndEst !== null && month !== null
      ? Array.from({ length: MONTHS }, (_, i) =>
          i + 1 < month ? null : Number((revActual + ((yearEndEst - revActual) * (i + 1 - month)) / (MONTHS - month)).toFixed(2)),
        )
      : null;
  // y축 눈금 — 0 기준 균등 4눈금. 데이터 최댓값을 nice step(…·1·1.2·1.5·2·2.5·3…×10^k)으로 올려 3등분
  const chartMax = Math.max(0, ...chartPts.map((p) => p.value ?? 0), ...(planVals ?? []), yearEndEst ?? 0);
  const niceStep = (raw: number) => {
    if (raw <= 0) return 1;
    const mag = 10 ** Math.floor(Math.log10(raw));
    const norm = raw / mag;
    const step = norm <= 1 ? 1 : norm <= 1.2 ? 1.2 : norm <= 1.5 ? 1.5 : norm <= 2 ? 2 : norm <= 2.5 ? 2.5 : norm <= 3 ? 3 : norm <= 5 ? 5 : 10;
    return step * mag;
  };
  const yStep = niceStep(chartMax / 3);
  const yTicks = [0, 1, 2, 3].map((k) => Number((yStep * k).toFixed(4)));
  // 계획 대비 달성률 (기준월) · 연말 예상 달성률 — 파생 Figure
  const planAtMonth = planVals && month !== null ? planVals[month - 1] : null;
  const planVsActualPct =
    revActual !== null && planAtMonth
      ? derivedFigure({ id: "ovm_plan_vs", label: "계획 대비", value: Number(((revActual / planAtMonth) * 100).toFixed(1)), unit: "PCT", decimals: 1, expression: "누적 실적 ÷ 월 계획 × 100", inputs: [], asOf, from: [revenueGoal?.actual, revenueGoal?.targetFigure] })
      : null;
  const yearEndAchievePct =
    yearEndEst !== null && revTarget
      ? derivedFigure({ id: "ovm_year_end", label: "연말 예상 달성", value: Number(((yearEndEst / revTarget) * 100).toFixed(1)), unit: "PCT", decimals: 1, expression: "연말 예상 ÷ 연간 목표 × 100", inputs: [], asOf, from: [revenueGoal?.actual, revenueGoal?.targetFigure] })
      : null;

  const reviewProposal = proposals.find((p) => p.id === reviewId);
  const proposalOf = (goalId: string) => proposals.find((p) => p.targetGoalId === goalId);

  // 대표 지표 라벨 정리 (부문명 · 괄호 제거는 OverviewWorkspace 와 같은 규칙)
  const headlineLabel = (d: DomainCardInfo) => (d.headline ? d.headline.label.replace(/\(.*\)/, "").replace(d.name, "").trim() || "규모" : "");

  const selIssues = useMemo(() => (selActive ? issuesOf(selected) : []), [selected, selActive]); // eslint-disable-line react-hooks/exhaustive-deps
  const selGoalCount = selActive ? goalsOf(selected).length : 0;
  const selVerdict = selActive && selIssues[0]?.gapVerdict ? GOAL_VERDICT[selIssues[0].gapVerdict as Verdict] : { label: "정상", tone: "success" as const };

  // 띠 오른쪽 신용RWA 값 색 — 문제일 때만 상태 색
  const toneText = (t: Tone) => (t === "critical" ? "!text-critical" : t === "attention" ? "!text-attention" : "!text-ink-deep");
  const goalTitle = (g: Goal) => g.metricLabel || resolveGoal(g, overrides[g.id]).title;

  return (
    <div className="shell flex flex-col pb-6 pt-5">
      {/* 제목 줄 */}
      <header className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3">
        <div className="flex min-w-0 flex-wrap items-center gap-y-2">
          <h1 className="text-[22px] font-bold leading-[1.25] text-ink-deep">경영 현황·목표</h1>
          <span aria-hidden="true" className="mx-4 h-[14px] w-px bg-hairline-soft" />
          <span className="text-[13px] font-medium text-steel">연간 경과</span>
          <div className="ml-2.5 h-1 w-20 overflow-hidden rounded-pill bg-track" role="presentation">
            <div className="h-full origin-left rounded-pill bg-steel motion-safe:animate-grow-x" style={{ width: `${Math.min(100, Math.max(0, elapsed ?? 0))}%` }} />
          </div>
          <span className="ml-2.5 tnum text-[13px] font-bold text-ink-deep">
            {elapsedFig ? <FigureText figure={elapsedFig} plain strong /> : <span className="text-steel">{NO_VALUE}</span>}
          </span>
          {month !== null ? <span className="ml-1 tnum text-[13px] text-steel">({month}/12월)</span> : null}
        </div>
        {/* 기준월 선택 · 기준 · 최종 분석 · 내보내기 — 1 · 2 · 3단계 공통 AsOfTools */}
        {tools}
      </header>

      {/* 은행 종합목표 띠 — 136px · 대표 칸 440px(primary/50) + 3칸 */}
      <section aria-label="은행 종합목표" className="mt-[15px] h-[136px] overflow-hidden rounded-[12px] border border-hairline-soft bg-canvas">
        <div className="flex h-full">
          {/* 대표 칸 — 옆 3칸과 같은 세로 격자(BAND_CELL): 제목 줄 22px 위 · 설명 줄 아래 고정, 값은 그 사이 가운데.
              배경은 primary/100(info-soft) — primary/50 는 페이지 배경(neutral/25)과 거의 같아 묻혔다 */}
          <div className={clsx(BAND_CELL, "w-[440px] shrink-0 bg-info-soft px-7")}>
            <p className="flex h-[22px] items-center gap-x-[19px] whitespace-nowrap">
              <span className="text-[13px] font-bold text-primary-deep">은행 종합목표</span>
              <span className="truncate text-[12px] text-steel">
                {revenueGoal?.metricLabel || "여신 이자마진 수익"}
                {revenueGoal?.targetFigure ? <span className="tnum"> · 연간 {formatFigure(revenueGoal.targetFigure)}</span> : null}
              </span>
            </p>
            <div className="flex flex-1 items-center gap-[11px]">
              {revenueProgressFig ? <Fig figure={revenueProgressFig} size={40} /> : <span className="text-[40px] font-bold leading-[1.15] text-steel">{NO_VALUE}</span>}
              {paceGap ? (
                <span className="self-end pb-[9px] whitespace-nowrap text-[13px] font-bold text-ink-deep">
                  경과 대비 <FigureText figure={paceGap} signed plain strong />
                </span>
              ) : null}
            </div>
            <div className="relative h-[6px] w-full rounded-pill bg-canvas">
              <div className="h-full origin-left rounded-pill bg-primary motion-safe:animate-grow-x" style={{ width: `${Math.min(100, Math.max(0, revenueProgress ?? 0))}%` }} />
              {elapsed !== null ? (
                <span aria-hidden="true" className="absolute top-1/2 h-3 w-[2px] -translate-x-1/2 -translate-y-1/2 rounded-[1px] bg-ink-deep" style={{ left: `${Math.min(100, Math.max(0, elapsed))}%` }} />
              ) : null}
            </div>
            <p className={clsx(BAND_FOOT, "gap-x-3")}>
              <span>
                누적 {revenueGoal?.actual ? <FigureText figure={revenueGoal.actual} plain strong className="ml-1.5" /> : NO_VALUE}
              </span>
              <span>
                연말 예상{" "}
                <span className="ml-1 tnum font-bold text-ink-deep">
                  {yearEndEst !== null ? `${tn(yearEndEst)}${revUnit}` : NO_VALUE}
                  {yearEndAchievePct?.value != null ? ` (${yearEndAchievePct.value.toFixed(1)}%)` : ""}
                </span>
              </span>
            </p>
          </div>

          <span aria-hidden="true" className="w-px shrink-0 bg-info-line-soft" />

          <BandCell
            title="총자산 증가율"
            tag={<Tag tone={bankStat.tone}>{bankStat.label}</Tag>}
            value={<Fig figure={bank.value} size={28} />}
            bar={<Bar percent={bankPct ?? 0} tone={bankStat.tone} />}
            footLeft={
              <>
                {bank.ceiling.label || "지주 한도"} {formatFigure(bank.ceiling)}
              </>
            }
            footRight={
              <span className={clsx("font-bold", bankStat.tone === "attention" || bankStat.tone === "critical" ? "text-attention" : "text-ink-deep")}>
                소진 {bankPctFig ? formatFigure(bankPctFig) : NO_VALUE}
              </span>
            }
          />

          <span aria-hidden="true" className="my-5 w-px shrink-0 bg-hairline-soft" />

          <BandCell
            title="여신 신용RWA 소진"
            tag={<Tag tone={rwaStat.tone}>{rwaStat.label}</Tag>}
            value={rwaWorstRow ? <Fig figure={rwaWorstRow.used} size={28} /> : <span className="text-[28px] font-bold text-steel">{NO_VALUE}</span>}
            bar={<Bar percent={rwaWorst ?? 0} tone={rwaStat.tone} />}
            footLeft={rwaWorstRow ? <>배분 {formatFigure(rwaWorstRow.allocated)} · {rwaWorstRow.org}</> : "배분 · 사용 자료 없음"}
            footRight={rwaWorstRow ? <FigureText figure={rwaWorstRow.usageRate} plain strong className={toneText(rwaStat.tone)} /> : null}
          />

          <span aria-hidden="true" className="my-5 w-px shrink-0 bg-hairline-soft" />

          <BandCell
            title="전사 경영목표"
            tag={attentionCount > 0 ? <Tag tone="attention">확인 {attentionCount}건</Tag> : <Tag tone="neutral">모두 정상</Tag>}
            value={<Fig figure={totalGoalsFig} size={28} />}
            bar={<GoalCells counts={totalCounts} />}
            footLeft={
              <>
                {domains.length}개 부문 · 정상 {totalCounts.on_track}건
              </>
            }
          />
        </div>
      </section>

      {/* 본문 2단 — 표(900) · 상세(460), 간격 16, 높이 맞춤 */}
      <div className="mt-6 grid grid-cols-1 items-stretch gap-4 xl:grid-cols-[900fr_460fr]">
        {/* 사업부문별 목표 상태 */}
        <section aria-labelledby="ovm-sector" className="flex h-full min-w-0 flex-col rounded-[10px] border border-hairline-soft bg-canvas px-6 pb-6 pt-5">
          <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
            <div className="flex flex-wrap items-baseline gap-x-[34px] gap-y-1">
              <h2 id="ovm-sector" className="text-[16px] font-bold leading-[1.45] text-ink-deep">
                사업부문별 목표 상태
              </h2>
              <p className="text-[12px] text-steel">행을 선택하면 오른쪽에 상세가 표시됩니다</p>
            </div>
            <p className="text-[13px]">
              <span className="font-medium text-steel">
                정상 <span className="tnum">{normalDomainCount}</span>
                {"  ·  "}
              </span>
              <b className="tnum text-attention">확인 필요 {reviewDomainCount}</b>
            </p>
          </div>

          <div role="table" aria-label="사업부문별 목표 상태" className="-mx-2 mt-[13px]">
            <div role="row" className={clsx(GRID, "h-9 items-center rounded-lg bg-surface-soft text-[12px] font-bold text-steel")}>
              <span role="columnheader" className="pl-4">부문</span>
              <span role="columnheader">대표 지표 (부문별 상이)</span>
              <span role="columnheader">목표 상태</span>
              <span role="columnheader">가장 시급한 목표</span>
              <span role="columnheader" className="pl-2">판정</span>
            </div>

            <div role="rowgroup" className="mt-1.5">
              {sortedDomains.map((d, idx) => {
                const ready = d.status === "active";
                const on = ready && d.domainCode === selected;
                const prev = sortedDomains[idx - 1];
                const prevOn = prev ? prev.status === "active" && prev.domainCode === selected : false;
                const line = idx > 0 && !on && !prevOn;

                if (!ready) {
                  // 준비 중 — 데이터 있는 행과 같은 높이·같은 5칸. 수치 대신 상태 글자만.
                  return (
                    <div key={d.domainCode} role="row" className={clsx(GRID, "relative h-16 items-center")}>
                      {line ? <span aria-hidden="true" className="absolute inset-x-2 top-0 h-px bg-track" /> : null}
                      <span role="cell" className="flex flex-col pl-4">
                        <span className="text-[15px] font-bold leading-[21px] text-ink-deep">{d.name}</span>
                        <span className="mt-px text-[12px] leading-[17px] text-steel">목표 0건</span>
                      </span>
                      <span role="cell" className="flex flex-col">
                        <span className="text-[12px] leading-[17px] text-steel">대표 지표</span>
                        <span className="text-[16px] font-bold leading-[19px] text-steel">{NO_VALUE}</span>
                      </span>
                      <span role="cell" className="text-[12px] text-steel">자료 준비 중</span>
                      <span role="cell" className="text-[13px] text-steel">등록된 경영목표 없음</span>
                      <span role="cell">
                        <Tag tone="neutral">준비 중</Tag>
                      </span>
                    </div>
                  );
                }

                const dCounts = countsOf(d.domainCode);
                const dIssues = issuesOf(d.domainCode);
                const top = dIssues[0];
                const topView = top ? resolveGoal(top, overrides[top.id]) : null;
                const topVerdict = top?.gapVerdict ? GOAL_VERDICT[top.gapVerdict as Verdict] : null;
                return (
                  <div
                    key={d.domainCode}
                    role="row"
                    aria-selected={on}
                    tabIndex={0}
                    onClick={() => setSelected(d.domainCode)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        setSelected(d.domainCode);
                      }
                    }}
                    className={clsx(GRID, "group relative h-16 cursor-pointer items-center outline-none")}
                  >
                    {line ? <span aria-hidden="true" className="absolute inset-x-2 top-0 h-px bg-track" /> : null}
                    <span
                      aria-hidden="true"
                      className={clsx("absolute inset-x-0 bottom-1 top-0 -z-0 rounded-lg transition-colors", on ? "bg-info-faint" : "group-hover:bg-surface-soft group-focus-visible:bg-surface-soft")}
                    />
                    <span role="cell" className="relative flex flex-col pl-4">
                      <span className="flex items-start gap-[3px] text-[15px] font-bold leading-[21px] text-ink-deep">
                        {d.name}
                        {flagged[d.domainCode] && !on ? <span aria-label="확인하지 않은 이슈가 있어요" className="h-[7px] w-[7px] rounded-circle bg-critical" /> : null}
                      </span>
                      <span className="mt-px tnum text-[12px] leading-[17px] text-steel">목표 {goalsOf(d.domainCode).length}건</span>
                    </span>
                    <span role="cell" className="relative flex flex-col">
                      {d.headline ? (
                        <>
                          <span className="text-[12px] leading-[17px] text-steel">{headlineLabel(d)}</span>
                          <Fig figure={d.headline} size={16} />
                        </>
                      ) : (
                        <span className="text-[13px] text-steel">{NO_VALUE}</span>
                      )}
                    </span>
                    <span role="cell" className="relative flex flex-col">
                      <GoalCells counts={dCounts} size="row" />
                      {dIssues.length > 0 ? (
                        <span className="mt-[7px] text-[12px] font-bold leading-[17px] text-ink-deep">확인 {dIssues.length}건</span>
                      ) : (
                        <span className="mt-[7px] text-[12px] leading-[17px] text-steel">모두 정상</span>
                      )}
                    </span>
                    <span role="cell" className="relative flex min-w-0 flex-col">
                      {top && topView ? (
                        <>
                          <span className="truncate text-[13px] font-bold leading-[18px] text-ink-deep">{goalTitle(top)}</span>
                          <GoalLine goal={top} targetLabel={topView.targetLabel} />
                        </>
                      ) : (
                        <span className="text-[13px] text-steel">확인이 필요한 목표 없음</span>
                      )}
                    </span>
                    <span role="cell" className="relative flex items-center gap-[3px]">
                      {topVerdict ? <Tag tone={topVerdict.tone}>{topVerdict.label}</Tag> : <Tag tone="neutral">정상</Tag>}
                      <span aria-hidden="true" className="text-[18px] font-medium leading-none text-icon">
                        ›
                      </span>
                    </span>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="mt-auto flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-t border-hairline-soft pt-2.5 text-[12px] text-steel">
            <p>부문마다 목표 지표가 달라, 지표 대신 ‘목표 단위 상태’로 비교합니다.</p>
            <ul className="flex flex-wrap items-center gap-x-[14px] gap-y-1 text-[11px]">
              {([
                ["정상", "on_track"],
                ["한도 근접", "near_limit"],
                ["목표 미달", "below"],
                ["한도 초과", "breach"],
              ] as [string, Verdict][]).map(([label, v]) => (
                <li key={label} className="inline-flex items-center gap-1">
                  <span aria-hidden className={clsx("h-1.5 w-2.5 rounded-[2px]", SEG_BG[v])} />
                  {label}
                </li>
              ))}
            </ul>
          </div>
        </section>

        {/* 선택 부문 상세 */}
        <section aria-label="선택 부문 상세" className="flex h-full min-w-0 flex-col rounded-[10px] border border-hairline-soft bg-canvas px-6 pb-6 pt-5">
          <div className="flex items-start justify-between gap-x-4">
            <div>
              <p className="text-[12px] leading-[17px] text-steel">선택한 부문</p>
              <div className="mt-px flex items-center gap-2.5">
                <h2 className="text-[20px] font-bold leading-[25px] text-ink-deep">{selDomain?.name ?? "부문"}</h2>
                {selActive ? <Tag tone={selVerdict.tone}>{selVerdict.label}</Tag> : null}
              </div>
            </div>
            <Link
              href="/hq/analysis"
              className="mt-1.5 inline-flex h-[34px] shrink-0 items-center rounded-md bg-primary px-3.5 text-[13px] font-bold text-white transition-colors hover:bg-primary-deep"
            >
              분석 시작 ›
            </Link>
          </div>

          {!selActive ? (
            <div className="mt-6 flex flex-1 flex-col items-center justify-center rounded-lg bg-surface-soft px-5 py-10 text-center">
              <p className="text-[14px] font-bold text-ink-deep">이 부문에 적용된 경영목표가 없어요</p>
              <p className="mt-1 text-[13px] text-steel">3단계 경영목표 설정에서 목표를 추가하면 현황이 여기에 표시돼요.</p>
            </div>
          ) : (
            <>
              <div className="mt-[25px] flex items-baseline justify-between gap-x-3">
                <h3 className="text-[14px] font-bold leading-[20px] text-ink-deep">
                  여신 이자마진 수익 누적 <span className="ml-6 text-[12px] font-normal text-steel">{revUnit}</span>
                </h3>
                <p className="whitespace-pre text-[11px] text-steel">{"— 실적   - - 계획   ··· 연말 예상"}</p>
              </div>
              <div className="mt-1">
                {hasChart && month !== null ? (
                  <MockTrend
                    values={chartPts.map((p) => p.value)}
                    plan={planVals}
                    proj={projVals}
                    yTicks={yTicks}
                    current={month - 1}
                    tip={(i) => {
                      const v = chartPts[i].value;
                      const plan = planVals?.[i] ?? null;
                      if (v === null) return "";
                      return `${i + 1}월 ${tn(v)}${revUnit}${plan ? ` · 계획 대비 ${((v / plan) * 100).toFixed(1)}%` : ""}`;
                    }}
                  />
                ) : (
                  <p className="rounded-lg bg-surface-soft px-5 py-8 text-center text-[13px] text-steel">누적 실적 자료가 없어요.</p>
                )}
              </div>

              <dl className="mt-4 grid grid-cols-3 gap-2">
                <SummaryTile label="연간 목표" figure={revenueGoal?.targetFigure} />
                <SummaryTile label="계획 대비" figure={planVsActualPct} />
                <SummaryTile label="연말 예상 달성" figure={yearEndAchievePct} />
              </dl>

              <div className="mt-[22px]">
                <div className="flex items-baseline justify-between gap-x-3">
                  <h3 className="text-[14px] font-bold leading-[20px] text-ink-deep">확인 필요 목표</h3>
                  <p className="tnum text-[12px] text-steel">
                    {selGoalCount}건 중 {selIssues.length}건
                  </p>
                </div>
                {selIssues.length === 0 ? (
                  <p className="mt-4 rounded-lg bg-surface-soft px-5 py-6 text-center text-[13px] text-steel">지금 확인할 이슈가 없어요.</p>
                ) : (
                  <ul className="mt-4">
                    {selIssues.slice(0, 4).map((g) => {
                      const view = resolveGoal(g, overrides[g.id]);
                      const verdict = GOAL_VERDICT[g.gapVerdict as Verdict];
                      const p = proposalOf(g.id);
                      return (
                        <li key={g.id} className="flex items-center justify-between gap-x-3 border-t border-track pb-[3px] pt-2 first:border-t-0 first:pt-0">
                          <div className="min-w-0">
                            <h4 className="text-[13px] font-bold leading-[18px] text-ink-deep">{goalTitle(g)}</h4>
                            <GoalLine goal={g} targetLabel={view.targetLabel} lead={<StatusMark tone={VERDICT_MARK[g.gapVerdict as Verdict] ?? "neutral"} label={verdict.label} />} />
                          </div>
                          {p ? (
                            // 오른쪽 칸 폭 고정 — 담기 · 취소로 상태가 바뀌어도 행이 흔들리지 않게
                            <div className="flex min-w-[140px] shrink-0 items-center justify-end gap-1.5">
                              {proposalActions[p.id] ? (
                                <>
                                  <Tag tone="neutral">처리 완료</Tag>
                                  <button
                                    type="button"
                                    onClick={() => setRevertId(g.id)}
                                    className="inline-flex h-[29px] items-center px-1 text-[12px] font-bold text-steel underline underline-offset-2 hover:text-ink-deep"
                                  >
                                    되돌리기
                                  </button>
                                </>
                              ) : staged[p.id] ? (
                                <>
                                  <button
                                    type="button"
                                    onClick={() => setReviewId(p.id)}
                                    aria-label="조정안에 담김 — 제안 다시 보기"
                                    className={clsx("inline-flex h-[22px] items-center whitespace-nowrap rounded-pill px-2 text-[12px] font-bold hover:underline", TAG_TONE.info)}
                                  >
                                    {/* 태그처럼 보이지만 눌러서 제안을 다시 연다 — › 로 누를 수 있음을 알린다 */}
                                    조정안에 담김 ›
                                  </button>
                                  <button
                                    type="button"
                                    onClick={() => {
                                      unstageProposal(p.id);
                                      showToast("조정안에서 뺐어요");
                                    }}
                                    className="inline-flex h-[29px] items-center px-1 text-[12px] font-bold text-steel underline underline-offset-2 hover:text-ink-deep"
                                  >
                                    취소
                                  </button>
                                </>
                              ) : (
                                <button
                                  type="button"
                                  onClick={() => setReviewId(p.id)}
                                  className="inline-flex h-[29px] items-center rounded-md border border-hairline-soft bg-canvas px-[11px] text-[12px] font-bold text-ink-deep hover:bg-surface-soft"
                                >
                                  제안 검토 ›
                                </button>
                              )}
                            </div>
                          ) : null}
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>
            </>
          )}
        </section>
      </div>

      {revertId ? <GoalChangeDialog request={{ mode: "revert", goalId: revertId }} goal={allGoals.find((g) => g.id === revertId)} onClose={() => setRevertId(null)} /> : null}
      {reviewProposal ? <ProposalPopup proposal={reviewProposal} goal={goals.find((g) => g.id === reviewProposal.targetGoalId)} onClose={() => setReviewId(null)} /> : null}
    </div>
  );
}

/** 표 5칸 — 시안 3 열 위치(152 · 210 · 182 · 240 · 84) */
const GRID = "grid grid-cols-[152fr_210fr_182fr_240fr_84fr]";

/** 목표 한 줄 — '실적 / 한도(목표) 값' 회색 + 차이(문제 색). 한도 근접은 '여유 …' */
function GoalLine({ goal, targetLabel, lead }: { goal: Goal; targetLabel: string; lead?: ReactNode }) {
  const tone = goal.gapVerdict === "breach" ? "!text-critical" : "!text-attention";
  const near = goal.gapVerdict === "near_limit";
  const gapAbs = goal.gap && goal.gap.value != null ? { ...goal.gap, value: Math.abs(goal.gap.value) } : null;
  return (
    <p className="mt-1 flex flex-wrap items-baseline gap-x-2 text-[12px] leading-[17px] text-steel">
      {/* 앞머리(선택) — 확인 필요 목표 목록의 상태 표시(점 + 판정) */}
      {lead}
      <span className="tnum">
        {goal.actual ? <FigureText figure={goal.actual} plain className="!font-normal !text-steel" /> : NO_VALUE} / {goal.targetType === "limit" ? "한도" : "목표"} {targetLabel}
      </span>
      {goal.gap ? (
        near && gapAbs ? (
          <span className={clsx("font-bold", "text-attention")}>
            여유 <FigureText figure={gapAbs} plain strong className={tone} />
          </span>
        ) : (
          <FigureText figure={goal.gap} signed={goal.gapSigned ?? true} plain strong className={tone} />
        )
      ) : null}
    </p>
  );
}

/** 띠 칸 — 지표명+태그 / 값 / 막대 / 설명 */
function BandCell({ title, tag, value, bar, footLeft, footRight }: { title: string; tag: ReactNode; value: ReactNode; bar: ReactNode; footLeft: ReactNode; footRight?: ReactNode }) {
  return (
    <div className={clsx(BAND_CELL, "flex-1 px-6")}>
      <div className="flex h-[22px] items-center justify-between gap-2">
        <h3 className="truncate text-[13px] font-medium text-steel">{title}</h3>
        {tag}
      </div>
      <div className="flex flex-1 items-center">{value}</div>
      {/* 대표 칸 막대(6px)와 같은 줄 높이에 가운데 맞춤 — 막대 굵기가 달라도 위치는 같다 */}
      <div className="flex h-[6px] items-center">{bar}</div>
      <p className={clsx(BAND_FOOT, "gap-x-2")}>
        <span className="min-w-0 truncate tnum">{footLeft}</span>
        {footRight ? <span className="shrink-0 tnum">{footRight}</span> : null}
      </p>
    </div>
  );
}

/** 누적 추이 — 실적 실선 + 아래 면(primary/100) · 계획 점선 · 연말 예상 짧은 점선 · 기준월 말풍선 상시 */
function MockTrend({
  values,
  plan,
  proj,
  yTicks,
  current,
  tip,
}: {
  values: (number | null)[];
  plan: number[] | null;
  proj: (number | null)[] | null;
  yTicks: number[];
  current: number;
  tip: (i: number) => string;
}) {
  const W = 412;
  const H = 150;
  const L = 30;
  const R = 10;
  const T = 8;
  const B = 22;
  const n = values.length;
  const box = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<number | null>(null);
  const yMax = yTicks[yTicks.length - 1] || 1;
  const x = (i: number) => L + ((W - L - R) * i) / Math.max(1, n - 1);
  const y = (v: number) => T + (H - T - B) * (1 - v / yMax);
  const pts = (arr: (number | null)[]) => arr.map((v, i) => (v === null || v === undefined ? null : `${x(i).toFixed(1)},${y(v).toFixed(1)}`)).filter(Boolean).join(" ");
  const act = values.slice(0, current + 1);
  const active = hover !== null && values[hover] !== null ? hover : current;
  const av = values[active];
  const ax = x(active);
  const ay = av !== null ? y(av) : 0;
  const left = ax / W < 0.45;

  return (
    <div
      ref={box}
      className="relative"
      onMouseMove={(e) => {
        const r = box.current?.getBoundingClientRect();
        if (!r) return;
        const px = ((e.clientX - r.left) / r.width) * W;
        let best = 0;
        for (let i = 1; i <= current; i++) if (Math.abs(x(i) - px) < Math.abs(x(best) - px)) best = i;
        setHover(best);
      }}
      onMouseLeave={() => setHover(null)}
    >
      <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full" role="img" aria-label={tip(current)}>
        {yTicks.map((t) => (
          <g key={t}>
            <line x1={L} x2={W - 4} y1={y(t)} y2={y(t)} stroke="var(--chart-grid)" strokeWidth="1" />
            <text x={L - 8} y={y(t) + 3.5} textAnchor="end" fontSize="10" fill="var(--color-steel)" className="tnum">
              {t === 0 ? "0" : t.toFixed(1)}
            </text>
          </g>
        ))}
        {values.map((_, i) => (
          <text key={i} x={x(i)} y={H - 4} textAnchor="middle" fontSize="10" fontWeight={i === active ? 700 : 400} fill={i === active ? "var(--color-ink-deep)" : "var(--color-steel)"}>
            {i + 1}월
          </text>
        ))}
        {/* 등장 애니메이션 — 다른 추이 차트(TrendChart)와 같게: 실적 선이 왼쪽 → 오른쪽으로 그려지고,
            채움 · 계획 · 연말 예상 · 점 · 말풍선은 선이 그려진 뒤 나타난다 ('동작 줄이기'면 바로 보임) */}
        {act.length > 1 ? <polygon points={`${x(0)},${y(0)} ${pts(act)} ${x(current)},${y(0)}`} fill="var(--color-info-soft)" className="motion-safe:animate-fade-late" /> : null}
        {plan ? <polyline points={pts(plan)} fill="none" stroke="var(--color-icon)" strokeWidth="1.2" strokeDasharray="4 3" className="motion-safe:animate-fade-late" /> : null}
        {proj ? <polyline points={pts(proj)} fill="none" stroke="var(--color-primary)" strokeWidth="1.5" strokeDasharray="2 3" strokeLinecap="round" className="motion-safe:animate-fade-late" /> : null}
        {act.length > 1 ? (
          <polyline points={pts(act)} fill="none" stroke="var(--color-primary)" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" pathLength={100} strokeDasharray="100 100" className="motion-safe:animate-draw" />
        ) : null}
        {av !== null ? <circle cx={ax} cy={ay} r="4" fill="var(--color-canvas)" stroke="var(--color-primary)" strokeWidth="2" className="motion-safe:animate-fade-late" /> : null}
      </svg>
      {av !== null ? (
        <div
          role="status"
          className="pointer-events-none absolute z-10 whitespace-nowrap rounded-md bg-ink-deep px-2.5 py-[5px] text-[11px] font-bold leading-[14px] text-white motion-safe:animate-fade-late"
          style={{
            left: `${(ax / W) * 100}%`,
            top: `${(ay / H) * 100}%`,
            transform: left ? "translate(12px, calc(-100% - 10px))" : "translate(calc(-100% - 12px), calc(-100% - 10px))",
          }}
        >
          {tip(active)}
        </div>
      ) : null}
    </div>
  );
}
