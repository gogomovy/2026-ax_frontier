import clsx from "clsx";
import Link from "next/link";
import { FigureText } from "@/components/data/FigureText";
import { RichText } from "@/components/data/RichText";
import { Badge, IconArrowRight, SeverityBadge } from "@/components/ui/primitives";
import type { BranchDashboard, KpiGroup, KpiItem } from "@/lib/types";

const pts = new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 2 });
const fmt = (n: number | null | undefined) => (n === null || n === undefined ? "-" : pts.format(n));
const pct = (score: number | null | undefined, max: number | null | undefined) => (score && max ? Math.max(0, Math.min(100, (score / max) * 100)) : 0);

function ChangeBadge({ item }: { item: Pick<KpiItem, "changeType" | "prevMax" | "max"> }) {
  if (!item.changeType) return null;
  return <Badge tone={item.changeType === "신설" ? "info" : "neutral"}>{item.changeType === "변경" && item.prevMax != null ? `변경 ${fmt(item.prevMax)}→${fmt(item.max)}` : item.changeType}</Badge>;
}

function ScoreBar({ score, max, highlight }: { score: number | null; max: number | null; highlight?: boolean }) {
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-pill bg-surface-soft" aria-hidden="true">
      <div className={clsx("h-full rounded-pill", highlight ? "bg-primary" : "bg-ink-deep opacity-60")} style={{ width: `${pct(score, max)}%` }} />
    </div>
  );
}

function GroupCard({ group, tabOf }: { group: KpiGroup; tabOf: (code: string) => string | undefined }) {
  return (
    <section aria-label={`${group.label} 득점`} className="flex flex-col gap-base rounded-2xl border border-hairline-soft p-lg">
      <header className="flex items-baseline justify-between gap-2">
        <h3 className="text-[15px] font-bold text-ink-deep">{group.label}</h3>
        <p className="tnum text-[13px] text-steel">
          <b className="text-[20px] text-ink-deep">{fmt(group.score)}</b> / {fmt(group.max)}점
        </p>
      </header>
      <ScoreBar score={group.score} max={group.max} />
      <ul className="flex flex-col gap-md">
        {group.items.map((item) => {
          const changed = [item, ...(item.details ?? [])].some((x) => x.changeType);
          return (
            <li key={item.code} className="flex flex-col gap-1.5">
              <div className="flex items-center justify-between gap-2 text-[13px]">
                <span className="flex min-w-0 items-center gap-1.5">
                  <span className={clsx("truncate font-bold", changed ? "text-ink-deep" : "text-charcoal")}>{item.label}</span>
                  <ChangeBadge item={item} />
                </span>
                <span className="tnum shrink-0 text-steel">
                  <b className="text-ink">{fmt(item.score)}</b> / {fmt(item.max)}
                </span>
              </div>
              <ScoreBar score={item.score} max={item.max} highlight={changed} />
              {(item.details ?? [])
                .filter((d) => d.changeType)
                .map((d) => {
                  const tab = tabOf(d.code);
                  const body = (
                    <>
                      <span className="flex min-w-0 items-center gap-1.5">
                        <span className="truncate">└ {d.label}</span>
                        <ChangeBadge item={d} />
                      </span>
                      <span className="tnum shrink-0">
                        {fmt(d.score)} / {fmt(d.max)}
                      </span>
                    </>
                  );
                  return tab ? (
                    <Link key={d.code} href={`/branch/analysis/${tab}`} className="flex items-center justify-between gap-2 rounded-lg bg-[rgba(0,100,224,0.05)] px-2.5 py-1.5 text-[12px] text-primary">
                      {body}
                    </Link>
                  ) : (
                    <div key={d.code} className="flex items-center justify-between gap-2 px-2.5 py-1 text-[12px] text-steel">
                      {body}
                    </div>
                  );
                })}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

/** 영업점 1화면 상단 — 업적평가 평가항목별 득점 · 가/감점 요약 + 기준 변경 알림 (시나리오 1화면 (1)) */
export function BranchKpiBoard({ dashboard }: { dashboard: BranchDashboard }) {
  const { scorecard, alerts } = dashboard;
  const kpis = scorecard.groups.filter((g) => g.kind === "kpi");
  const adj = scorecard.groups.find((g) => g.kind === "adjustment");
  // 득점표 항목 → 그 항목의 기준 변경 알림 탭 (산출물의 itemCode 로 연결)
  const tabOf = (code: string) => alerts.find((a) => a.itemCode === code)?.tabKey;

  return (
    <div className="flex flex-col gap-lg">
      <section aria-label="업적평가 총득점" className="flex flex-wrap items-end justify-between gap-lg rounded-2xl bg-surface-soft px-xl py-lg">
        <div>
          <p className="text-[12px] font-bold text-steel">
            {dashboard.periodLabel} 업적평가 총득점 · {dashboard.asOfLabel}
          </p>
          <p className="mt-1.5 flex items-baseline gap-2">
            <span className="text-[34px] font-bold leading-none text-ink-deep">
              <FigureText figure={scorecard.total} strong />
            </span>
            <span className="tnum text-[15px] text-steel">
              / <FigureText figure={scorecard.max} />점
            </span>
          </p>
          {adj ? (
            <p className="mt-2 flex flex-wrap gap-x-md gap-y-1 text-[12.5px] text-charcoal">
              {adj.items.map((a) => (
                <span key={a.code}>
                  {a.label} <b className="tnum">{a.score !== null && a.score > 0 ? `+${fmt(a.score)}` : fmt(a.score)}</b>
                  {a.note ? <span className="text-stone"> ({a.note})</span> : null}
                </span>
              ))}
              <span className="text-stone">가 · 감점 포함</span>
            </p>
          ) : null}
        </div>
        <div className="text-right">
          <p className="text-[12px] text-steel">Agent 의견 반영 시 예상</p>
          <p className="mt-1 text-[22px] font-bold leading-none text-primary">
            <FigureText figure={scorecard.totalAfter} strong />점
          </p>
          <p className="mt-1 text-[12px] text-steel">
            <FigureText figure={scorecard.uplift} signed />점 · 아래 기준 변경 {alerts.length}건 기준
          </p>
        </div>
      </section>

      <div className="grid grid-cols-1 gap-md lg:grid-cols-3">
        {kpis.map((g) => (
          <GroupCard key={g.code} group={g} tabOf={tabOf} />
        ))}
      </div>

      {alerts.length > 0 ? (
        <section aria-label="업적평가 기준 변경과 Agent 영업 가이드" className="overflow-hidden rounded-2xl border border-[rgba(0,100,224,0.22)] bg-[rgba(0,100,224,0.04)]">
          <div className="flex flex-wrap items-baseline gap-x-md gap-y-1 px-lg pt-base">
            <p className="text-[14px] font-bold text-ink-deep">하반기 업적평가 기준 변경 {alerts.length}건 · Agent 영업 가이드</p>
            <p className="text-[12px] text-steel">상반기 대비 신설 · 변경 항목을 분석했습니다 · 선택하면 분석 결과로 이동합니다</p>
          </div>
          <ul className="mt-2 divide-y divide-[rgba(0,100,224,0.12)] border-t border-[rgba(0,100,224,0.12)]">
            {/* 행 전체가 분석 탭 링크(stretched link) — 수치(계산 추적 버튼)는 링크 위로 올려 따로 누를 수 있게 한다 */}
            {alerts.map((a) => (
              <li key={a.id} className="row-button relative flex flex-col gap-1.5 px-lg py-3 md:flex-row md:items-center md:gap-md">
                <span className="flex shrink-0 items-center gap-1.5">
                  <SeverityBadge severity={a.severity} />
                  <Badge tone="info">{a.changeType}</Badge>
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-[11.5px] font-bold text-steel">{a.path}</span>
                  <Link href={`/branch/analysis/${a.tabKey}`} className="block text-[13.5px] font-bold text-ink-deep after:absolute after:inset-0 after:content-['']">
                    {a.title}
                  </Link>
                  <RichText as="span" text={a.summary} figures={dashboard.figures} className="relative z-10 mt-0.5 block text-[12.5px] leading-relaxed text-charcoal" />
                </span>
                <span className="relative z-10 inline-flex shrink-0 items-center gap-1 text-[12.5px] font-bold text-primary">
                  예상 <FigureText figure={a.uplift} signed />점
                  <Link href={`/branch/analysis/${a.tabKey}`} aria-label={`의견 보기 — ${a.title} 분석 결과`} className="inline-flex items-center gap-1">
                    의견 보기 <IconArrowRight />
                  </Link>
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
