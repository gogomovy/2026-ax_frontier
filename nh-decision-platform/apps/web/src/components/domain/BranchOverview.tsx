"use client";

import { useId, useState, type ReactNode } from "react";
import Link from "next/link";
import clsx from "clsx";
import { FigureText } from "@/components/data/FigureText";
import { RichText } from "@/components/data/RichText";
import { Fig } from "@/components/domain/overviewKit";
import { IconChevronDown, IconSparkle } from "@/components/ui/icons";
import { IconCheck, IconChevron } from "@/components/ui/primitives";
import { withOffice } from "@/lib/branchOffice";
import { derivedFigure } from "@/lib/derived";
import { formatFigure, formatValue } from "@/lib/format";
import { NO_VALUE } from "@/lib/period";
import type { BranchDashboard, BranchKpiAlert, DomainCardInfo, Evidence, Figure, KpiGroup, KpiItem } from "@/lib/types";

/** 득점 표기 — 소수 둘째 자리까지 (배점표 득점) */
const pts = new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 2 });
const fmt = (n: number | null | undefined) => (n === null || n === undefined ? NO_VALUE : pts.format(n));
/** 음수는 수학 기호 '−' 로 */
const signedPts = (n: number | null | undefined) => (n === null || n === undefined ? NO_VALUE : n > 0 ? `+${fmt(n)}` : n < 0 ? `−${fmt(-n)}` : fmt(n));
const pct = (score: number | null | undefined, max: number | null | undefined) => (typeof score === "number" && max ? Math.max(0, Math.min(100, (score / max) * 100)) : 0);
const decimalsOf = (n: number | null | undefined) => (typeof n === "number" && !Number.isInteger(n) ? Math.min(2, String(n).split(".")[1]?.length ?? 0) : 0);

/** 배점 대비 득점이 이 비율(%) 미만이면 강조 — 시안 범례 '배점 대비 30% 미만' (화면 표시 규칙 · 판정 아님) */
const LOW_SHARE_PCT = 30;
const isLow = (score: number | null | undefined, max: number | null | undefined) => typeof score === "number" && !!max && (score / max) * 100 < LOW_SHARE_PCT;

/** 카드 공통 — 흰 바탕 · 10px 모서리 · 옅은 테두리 (사업부서 현황과 같은 카드) */
const CARD = "min-w-0 rounded-[10px] border border-hairline-soft bg-canvas";

/** 카드 제목 줄 — 14px 제목 + 12px 보조 글자 (시안 326:2) */
function CardHead({ id, title, hint, right }: { id?: string; title: ReactNode; hint?: ReactNode; right?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
      <div className="flex min-w-0 flex-wrap items-baseline gap-x-[7px] gap-y-1">
        <h2 id={id} className="flex items-center gap-1 text-[14px] font-bold leading-[1.4] text-ink-deep">
          {title}
        </h2>
        {hint ? <p className="tnum text-[12px] leading-[1.4] text-steel">{hint}</p> : null}
      </div>
      {right}
    </div>
  );
}

/** 오른쪽 위 글자 링크 — 12px · primary/700 · › */
function CardLink({ href, children, label }: { href: string; children: ReactNode; label?: string }) {
  return (
    <Link
      href={href}
      aria-label={label}
      className="inline-flex shrink-0 items-center gap-1 rounded-sm text-[12px] font-medium leading-[1.4] text-primary-deep hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
    >
      {children}
      <IconChevron className="h-2.5 w-2.5" />
    </Link>
  );
}

/** 현재 · AI 가이드 반영 두 겹 막대 — 진한 primary(현재) 위에 옅은 primary(반영 시) */
function TwinBar({ now, after, max, h, i = 0 }: { now: number | null | undefined; after: number | null | undefined; max: number | null | undefined; h: number; i?: number }) {
  return (
    <div className="relative w-full overflow-hidden rounded-pill bg-track" style={{ height: h }} role="presentation">
      <span className="absolute inset-y-0 left-0 origin-left rounded-pill bg-info-line-soft motion-safe:animate-grow-x" style={{ width: `${pct(after, max)}%`, ["--i" as string]: i + 1 }} />
      <span className="absolute inset-y-0 left-0 origin-left rounded-pill bg-primary motion-safe:animate-grow-x" style={{ width: `${pct(now, max)}%`, ["--i" as string]: i }} />
    </div>
  );
}

/** 한 겹 득점 막대 */
function ScoreBar({ score, max, h, tone, i = 0 }: { score: number | null | undefined; max: number | null | undefined; h: number; tone: string; i?: number }) {
  return (
    <div className="w-full overflow-hidden rounded-pill bg-track" style={{ height: h }} role="presentation">
      <div className={clsx("h-full origin-left rounded-pill motion-safe:animate-grow-x", tone)} style={{ width: `${pct(score, max)}%`, ["--i" as string]: i }} />
    </div>
  );
}

/** 신설 · 변경 표식 — 9px Bold 알약 (시안 KPI 표) */
function ChangeTag({ type }: { type?: string | null }) {
  if (!type) return null;
  return (
    <span className={clsx("inline-flex h-[14px] shrink-0 items-center rounded-pill px-[5px] text-[9px] font-bold leading-none", type === "신설" ? "bg-info-soft text-primary-deep" : "bg-track text-slate")}>
      {type}
    </span>
  );
}

/** 'YYYY.MM.DD (하반기 n개월 경과)' → { date, elapsed } */
function splitAsOf(label: string) {
  const m = /^(.*?)\s*\(([^()]*)\)\s*$/.exec(label);
  return m ? { date: m[1].trim(), elapsed: m[2].trim() } : { date: label, elapsed: "" };
}

/** 실적 · 목표 금액 표기 — '백만원(가중)' 단위는 억원으로 올려 쓰고 괄호 말은 뒤에 붙인다 */
function amountParts(unit: string | undefined) {
  const u = unit ?? "";
  return { base: u.replace(/\(.*?\)/g, "").trim(), note: /\(([^)]*)\)/.exec(u)?.[1] ?? "" };
}
/** 단위 상수 — 백만원 → 억원 */
const MILLION_PER_EOK = 100;
function amountText(v: number | null | undefined, unit: string | undefined) {
  if (v === null || v === undefined) return NO_VALUE;
  const { base } = amountParts(unit);
  // 단위 환산: 1억원 = 100백만원. 1억원 이상이면 억원으로 보여 준다
  if (base === "백만원" && Math.abs(v) >= MILLION_PER_EOK) return `${pts.format(v / MILLION_PER_EOK)}억원`;
  return `${pts.format(v)}${base}`;
}

/** 득점표에서 항목 찾기 (하위 항목 포함) */
function findItem(groups: KpiGroup[], code: string): KpiItem | undefined {
  for (const g of groups) {
    for (const it of g.items) {
      if (it.code === code) return it;
      const d = it.details?.find((x) => x.code === code);
      if (d) return d;
    }
  }
  return undefined;
}

/** 가이드 반영 후 득점 — 상향 계산의 입력(유치 후 득점)이 있으면 그 값, 없으면 현재 + 상향 */
function afterScore(alert: BranchKpiAlert, now: number | null | undefined): number | null {
  const a = alert.uplift.calc?.inputs.find((x) => x.key === "a");
  const v = a ? Number(a.value) : NaN;
  if (Number.isFinite(v)) return v;
  return typeof now === "number" && typeof alert.uplift.value === "number" ? now + alert.uplift.value : null;
}

/**
 * 영업점 1단계 현황 — Figma '영업점 · 1단계 현황 · 개선안'(326:2).
 * 제목 줄 · 업적평가 총득점 · 가점 확보 방안(AI 영업 가이드) · KPI별 득점 · 사업부문.
 * 수치는 모두 영업점 산출물(득점표 · 알림 · 부문 · 여신 집계)에서만 온다.
 */
export function BranchOverview({
  dashboard,
  office,
  guideEvidence,
  picker,
  tools,
  children,
}: {
  dashboard: BranchDashboard;
  office?: string | null;
  /** 가이드별 근거 (분석 탭 키 → 근거) — 분석 보고서의 AI 의견 근거 */
  guideEvidence: Record<string, Evidence[]>;
  /** 지점 선택 (볼 수 있는 지점이 둘 이상일 때만 보임) */
  picker?: ReactNode;
  tools?: ReactNode;
  /** 사업부문 다음에 둘 내용 (최근 감지된 변화 · 다음 단계) */
  children?: ReactNode;
}) {
  const { scorecard, alerts, periodLabel } = dashboard;
  const asOf = splitAsOf(dashboard.asOfLabel);
  const scoreHint = asOf.elapsed ? `${asOf.elapsed} · ${asOf.date}` : asOf.date;
  const changeTypes = [...new Set(alerts.map((a) => a.changeType).filter(Boolean))].join(" · ");

  return (
    <>
      {/* 제목 줄 — 종합기획부 · 사업부서 현황과 같은 22px 제목 · 기준월 선택 · 내보내기(아이콘) */}
      <header className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3">
        <div className="flex min-w-0 flex-wrap items-center gap-y-2">
          <h1 className="text-[22px] font-bold leading-[1.25] text-ink-deep">{dashboard.office.name} 현황</h1>
          <span aria-hidden="true" className="mx-4 h-[14px] w-px bg-hairline-soft" />
          <span className="text-[13px] font-medium text-steel">{periodLabel ? `${periodLabel} 업적평가 · 사업부문` : "업적평가 · 사업부문"}</span>
        </div>
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
          {picker}
          {tools}
        </div>
      </header>

      {/* ① 업적평가 총득점 */}
      <section aria-labelledby="br-total" className={clsx(CARD, "mt-[15px] px-6 pb-6 pt-[19px]")}>
        <CardHead id="br-total" title={`${periodLabel ? `${periodLabel} ` : ""}업적평가 총득점`} hint={scoreHint} />
        <div className="mt-2.5 flex flex-wrap items-end gap-x-[22px] gap-y-2">
          <p className="flex items-baseline gap-2.5">
            <Fig figure={scorecard.total} size={44} />
            <span className="tnum text-[16px] font-bold text-steel">/ {formatValue(scorecard.max)}점</span>
          </p>
          <svg viewBox="0 0 24 24" width="24" height="24" aria-hidden="true" className="mb-2.5 text-icon">
            <path d="M4 12h15m-6-6 6 6-6 6" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <div>
            <p className="text-[11px] font-medium leading-[1.4] text-steel">AI 가이드 반영 시</p>
            <p className="mt-0.5 flex items-center gap-2.5">
              <Fig figure={scorecard.totalAfter} size={28} valueClass="text-primary-deep" unitLabel="점" />
              {scorecard.uplift.value !== null ? (
                <span className="inline-flex h-[18px] items-center rounded-pill bg-info-soft px-[7px] text-[11px] font-bold text-primary-deep">
                  <FigureText figure={scorecard.uplift} signed plain strong className="!text-primary-deep" />점
                </span>
              ) : null}
            </p>
          </div>
        </div>
        <div className="mt-5">
          <TwinBar now={scorecard.total.value} after={scorecard.totalAfter.value} max={scorecard.max.value} h={8} />
        </div>
      </section>

      {/* ② 가점 확보 방안 — AI 영업 가이드 (기준 변경 알림) */}
      {alerts.length > 0 ? (
        <section aria-labelledby="br-guides" className={clsx(CARD, "mt-4 px-6 pb-6 pt-[19px]")}>
          <CardHead
            id="br-guides"
            title="가점 확보 방안"
            hint={`AI 영업 가이드${periodLabel ? ` · ${periodLabel}` : ""}${changeTypes ? ` ${changeTypes}` : ""} 평가기준`}
          />
          {/* 카드는 제 높이만 — 한쪽 근거를 펼쳐도 옆 카드는 늘어나지 않는다 (items-start) */}
          <ul className="mt-3.5 grid grid-cols-1 items-start gap-3 lg:grid-cols-2">
            {alerts.map((a, i) => (
              <GuideCard key={a.id} alert={a} index={i} dashboard={dashboard} office={office} evidence={guideEvidence[a.tabKey] ?? []} />
            ))}
          </ul>
        </section>
      ) : null}

      {/* ③ KPI별 득점 */}
      <KpiScores dashboard={dashboard} office={office} />

      {/* ④ 사업부문 */}
      <Segments dashboard={dashboard} office={office} />

      {children}
    </>
  );
}

/** 가이드 1건 — 상향 점수 · 할 일 · AI 설명 · 항목 득점 변화 · 실적/목표 · 근거 펼치기 */
function GuideCard({ alert, index, dashboard, office, evidence }: { alert: BranchKpiAlert; index: number; dashboard: BranchDashboard; office?: string | null; evidence: Evidence[] }) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const item = findItem(dashboard.scorecard.groups, alert.itemCode);
  const now = item?.score;
  const after = afterScore(alert, now);
  const href = withOffice(`/branch/analysis/${alert.tabKey}`, office);
  const unitNote = amountParts(item?.actualUnit).note;

  return (
    <li className="flex min-w-0 flex-col rounded-[8px] bg-page px-[18px] pb-4 pt-[15px]">
      <div className="flex flex-wrap items-start gap-x-3 gap-y-1">
        <span className="shrink-0">
          <Fig figure={alert.uplift} size={22} signed valueClass="text-primary-deep" unitLabel="점" />
        </span>
        <h3 className="order-last min-w-0 basis-full text-[15px] sm:order-none sm:basis-0 sm:flex-1 sm:pt-[2px] font-bold leading-[1.4] text-ink-deep">{alert.title}</h3>
        <span className="ml-auto pt-[3px] sm:ml-0">
          <CardLink href={href} label={`의견 보기 — ${alert.title} 분석 결과`}>
            의견 보기
          </CardLink>
        </span>
      </div>
      <p className="mt-2 flex items-start gap-1.5 text-[12px] leading-[1.6] text-slate">
        {/* AI 표식 — 글자(✦) 대신 SVG, 첫 줄 가운데(19px 줄 · 12px 아이콘)에 맞춘다 */}
        <IconSparkle size={12} className="mt-[3.5px] h-3 w-3 shrink-0 text-primary" />
        <RichText as="span" text={alert.summary} figures={dashboard.figures} className="min-w-0" />
      </p>

      <div className="pt-4">
        <div className="flex items-baseline justify-between gap-3 text-[11px] font-medium leading-[1.4] text-steel">
          <span className="min-w-0 truncate">
            {item?.label ?? alert.path}
            {alert.changeType ? ` (${alert.changeType})` : ""}
            {item?.max != null ? ` · 배점 ${fmt(item.max)}점` : ""}
          </span>
          <span className="tnum shrink-0 text-[12px]">
            {fmt(now)} → <b className="font-bold text-primary-deep">{fmt(after)}점</b>
          </span>
        </div>
        <div className="mt-2">
          <TwinBar now={now} after={after} max={item?.max} h={8} i={index} />
        </div>
        {item?.actual != null || item?.target != null ? (
          <p className="tnum mt-2 text-[11px] leading-[1.4] text-steel">
            실적 {amountText(item?.actual, item?.actualUnit)} / 목표 {amountText(item?.target, item?.actualUnit)}
            {unitNote ? ` (${unitNote})` : ""}
          </p>
        ) : null}

        {evidence.length > 0 ? (
          <>
            <button
              type="button"
              aria-expanded={open}
              aria-controls={panelId}
              onClick={() => setOpen((v) => !v)}
              className="mt-3 inline-flex items-center gap-1 rounded-sm text-[11px] font-medium leading-[1.4] text-primary-deep hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
            >
              {open ? "근거 접기" : "근거 보기"}
              <IconChevronDown size={10} className={clsx("transition-transform", open && "rotate-180")} />
            </button>
            {open ? (
              <ul id={panelId} className="mt-2 flex flex-col gap-2 border-t border-track pt-2.5">
                {evidence.map((e) => (
                  <li key={e.id} className="text-[11px] leading-[1.55]">
                    <p className="font-bold text-ink-deep">{e.label}</p>
                    {e.snippet ? <p className="mt-0.5 text-steel">{e.snippet}</p> : null}
                  </li>
                ))}
              </ul>
            ) : null}
          </>
        ) : null}
      </div>
    </li>
  );
}

/** KPI 대분류 득점 Figure — 큰 숫자 롤링 · 계산 추적 */
function groupFigure(g: KpiGroup, asOf: string, total: Figure): Figure {
  return derivedFigure({
    id: `br_kpi_group_${g.code}`,
    label: `${g.label} 득점`,
    value: g.score,
    unit: "NONE",
    decimals: decimalsOf(g.score),
    expression: "평가 항목 득점 합",
    inputs: g.items.map((it) => ({ key: it.code, label: it.label, value: String(it.score ?? ""), unit: "점", source: "배점표 득점" })),
    asOf,
    from: [total],
  });
}

/** KPI별 득점 — (왼쪽) 배점이 가장 큰 대분류 · (오른쪽) 나머지 대분류 */
function KpiScores({ dashboard, office }: { dashboard: BranchDashboard; office?: string | null }) {
  const { scorecard, alerts } = dashboard;
  const kpis = scorecard.groups.filter((g) => g.kind === "kpi");
  const adj = scorecard.groups.find((g) => g.kind === "adjustment");
  const lead = [...kpis].sort((a, b) => (b.max ?? 0) - (a.max ?? 0))[0];
  const rest = kpis.filter((g) => g !== lead);
  // 득점표 항목 → 그 항목의 기준 변경 분석 탭
  const tabOf = (code: string) => alerts.find((a) => a.itemCode === code)?.tabKey;

  const block = (g: KpiGroup) => <KpiBlock key={g.code} group={g} figure={groupFigure(g, dashboard.asOf, scorecard.total)} tabOf={tabOf} office={office} />;

  return (
    <section aria-labelledby="br-kpi" className={clsx(CARD, "mt-4 px-6 pb-[15px] pt-[19px]")}>
      <CardHead
        id="br-kpi"
        title="KPI별 득점"
        hint="배점 대비 득점"
        right={
          <p className="inline-flex items-center gap-1.5 text-[11px] text-steel">
            <span aria-hidden="true" className="h-[7px] w-[7px] rounded-[1px] bg-primary" />
            배점 대비 {LOW_SHARE_PCT}% 미만
          </p>
        }
      />
      {kpis.length === 0 ? (
        <p className="mt-4 rounded-lg bg-page py-6 text-center text-[13px] text-steel">득점 자료가 없어요.</p>
      ) : (
        <div className="mt-[18px] grid grid-cols-1 gap-y-8 lg:grid-cols-[1fr_1px_1fr] lg:gap-x-6">
          <div className="min-w-0">{lead ? block(lead) : null}</div>
          <span aria-hidden="true" className="hidden bg-track lg:block" />
          <div className="flex min-w-0 flex-col">
            {rest.map((g, i) => (
              <div key={g.code}>
                {i > 0 ? <span aria-hidden="true" className="my-7 block h-px bg-hairline-soft" /> : null}
                {block(g)}
              </div>
            ))}
          </div>
        </div>
      )}
      {adj && adj.items.length > 0 ? (
        <p className="tnum mt-[18px] border-t border-track pt-2.5 text-[11px] leading-[1.4] text-steel">
          {adj.items.map((a) => `${a.label} ${signedPts(a.score)}${a.note ? ` (${a.note})` : ""}`).join(" · ")}은 총득점에 별도 반영
        </p>
      ) : null}
    </section>
  );
}

/** 대분류 1개 — 제목 · 큰 득점 · 굵은 막대 · 항목 줄(하위 항목은 옅은 묶음 안) */
function KpiBlock({ group, figure, tabOf, office }: { group: KpiGroup; figure: Figure; tabOf: (code: string) => string | undefined; office?: string | null }) {
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="text-[13px] font-bold leading-[1.4] text-ink-deep">{group.label}</h3>
        <p className="flex items-baseline gap-1">
          <Fig figure={figure} size={19} />
          <span className="tnum text-[11px] text-steel">/ {fmt(group.max)}점</span>
        </p>
      </div>
      <div className="mt-2">
        <ScoreBar score={group.score} max={group.max} h={5} tone="bg-slate" />
      </div>
      <ul className="mt-[19px] flex flex-col gap-[15px]">
        {group.items.map((item, i) => {
          const low = isLow(item.score, item.max);
          const details = item.details ?? [];
          return (
            <li key={item.code}>
              <ScoreRow item={item} low={low} level={1} i={i} tab={tabOf(item.code)} office={office} />
              {details.length > 0 ? (
                <ul className="relative mt-2.5 flex flex-col gap-[11px] rounded-[6px] bg-page py-2 pl-[15px] pr-3">
                  <span aria-hidden="true" className="absolute bottom-2 left-2 top-2 w-px bg-hairline-soft" />
                  {details.map((d, j) => (
                    <li key={d.code}>
                      <ScoreRow item={d} low={isLow(d.score, d.max)} level={2} i={j} tab={tabOf(d.code)} office={office} />
                    </li>
                  ))}
                </ul>
              ) : null}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/** 항목 줄 — 이름 + 신설/변경 · 득점 / 배점 · 얇은 막대 (30% 미만은 primary) */
function ScoreRow({ item, low, level, i, tab, office }: { item: KpiItem; low: boolean; level: 1 | 2; i: number; tab?: string; office?: string | null }) {
  const sub = level === 2;
  const name = <span className={clsx("truncate", sub ? "text-[11px] text-slate" : "text-[12px] font-medium text-ink-deep")}>{item.label}</span>;
  return (
    <div className="flex flex-col gap-[6px]">
      <div className="flex items-baseline justify-between gap-2 leading-[1.4]">
        <span className="flex min-w-0 items-center gap-1.5">
          {tab ? (
            <Link href={withOffice(`/branch/analysis/${tab}`, office)} className="min-w-0 truncate rounded-sm hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary">
              {name}
            </Link>
          ) : (
            name
          )}
          <ChangeTag type={item.changeType} />
        </span>
        <span className="tnum shrink-0">
          <b className={clsx("font-bold", sub ? "text-[11px]" : "text-[12px]", low ? "text-primary-deep" : "text-ink-deep")}>{fmt(item.score)}</b>
          <span className={clsx("text-steel", sub ? "text-[10px]" : "text-[11px]")}> / {fmt(item.max)}</span>
        </span>
      </div>
      <ScoreBar score={item.score} max={item.max} h={sub ? 2 : 3} tone={low ? "bg-primary" : sub ? "bg-hairline" : "bg-icon"} i={i} />
    </div>
  );
}

/** 부문 대표 지표 이름 — 부문명 · 괄호를 뺀 짧은 이름 ('여신 잔액(기업 + 소매)' → '잔액') */
const headlineLabel = (d: DomainCardInfo) => (d.headline ? d.headline.label.replace(/\(.*\)/, "").replace(d.name, "").trim() : "");

/** 사업부문 — 부문 타일 5개 + 선택 부문 지표 4칸 */
function Segments({ dashboard, office }: { dashboard: BranchDashboard; office?: string | null }) {
  const { segments, loan } = dashboard;
  // 처음 선택 = 상세가 준비된 첫 부문 (부문 코드를 코드에 두지 않는다)
  const firstReady = segments.find((s) => s.status === "active") ?? segments[0];
  const [picked, setPicked] = useState<string | null>(null);
  const selected = picked ?? firstReady?.domainCode ?? "";
  const active = segments.find((s) => s.domainCode === selected);
  const ready = active?.status === "active";
  const elapsed = splitAsOf(dashboard.asOfLabel).elapsed;

  const metrics: { label: string; figure: Figure; unit?: string; caption: string }[] = [
    { label: loan.total.label.replace(/\(/, " (").replace(/^지점\s*/, ""), figure: loan.total, caption: elapsed || dashboard.asOfLabel },
    { label: "기업여신 대출잔액", figure: loan.corp, caption: `차주 ${formatFigure(loan.corpCount)}` },
    { label: "소매여신 익스포저", figure: loan.retail, caption: `차주 ${formatFigure(loan.retailCount)}` },
    { label: "기업여신 평균 신용등급", figure: loan.avgGrade, unit: "등급", caption: `전행 평균 ${formatValue(loan.bankAvgGrade)} · 값이 클수록 위험` },
  ];

  return (
    <section aria-labelledby="br-seg" className={clsx(CARD, "mt-4 px-6 pb-6 pt-[19px]")}>
      <CardHead
        id="br-seg"
        title="사업부문"
        hint={`${dashboard.office.name} 기준 · 부문을 선택하면 아래 지표가 바뀝니다`}
        right={ready && active ? <CardLink href={withOffice("/branch/analysis", office)}>{active.name} 상세 분석</CardLink> : null}
      />
      <div role="group" aria-label="사업부문 선택" className="mt-3.5 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
        {segments.map((s) => {
          const on = s.domainCode === selected;
          // 상세 자료가 있는 부문만 고를 수 있다 (아래 지표 칸과 같은 조건) — 없으면 회색 · 누를 수 없음
          const off = s.status !== "active";
          const sub = headlineLabel(s) || s.note;
          return (
            <button
              key={s.domainCode}
              type="button"
              onClick={off ? undefined : () => setPicked(s.domainCode)}
              disabled={off}
              aria-disabled={off || undefined}
              aria-pressed={off ? undefined : on}
              className={clsx(
                "flex h-[58px] min-w-0 items-center gap-2 rounded-[8px] border-[1.5px] px-[15px] text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-1",
                off ? "cursor-default border-hairline-soft bg-surface-soft" : on ? "border-primary bg-info-faint" : "border-hairline-soft bg-canvas hover:bg-surface-soft",
              )}
            >
              <span className="flex min-w-0 flex-1 flex-col gap-[3px]">
                <span className={clsx("text-[14px] font-bold leading-[1.4]", off ? "text-steel" : on ? "text-primary-deep" : "text-ink-deep")}>{s.name}</span>
                <span className={clsx("truncate tnum text-[11px] leading-[1.3]", on && !off ? "text-primary-deep" : "text-steel")}>
                  <b className={clsx("font-bold", off ? "text-steel" : on ? "text-primary-deep" : "text-ink-deep")}>{s.headline ? formatFigure(s.headline) : "준비 중"}</b>
                  {s.headline && sub ? ` · ${sub}` : ""}
                </span>
                {off ? <span className="sr-only">상세 데이터 준비 중</span> : null}
              </span>
              {off ? null : on ? <IconCheck className="shrink-0 text-primary-deep" /> : <IconChevron className="h-3 w-3 shrink-0 text-icon" />}
            </button>
          );
        })}
      </div>

      {ready ? (
        <dl className="mt-[9px] grid grid-cols-1 rounded-[8px] bg-info-faint sm:grid-cols-2 xl:grid-cols-4">
          {metrics.map((m, i) => (
            <div key={m.label} className="relative min-w-0 px-5 pb-4 pt-4">
              {i > 0 ? <span aria-hidden="true" className="absolute bottom-[17px] left-0 top-[18px] hidden w-px bg-hairline xl:block" /> : null}
              <dt className="truncate text-[12px] font-medium leading-[1.4] text-steel">{m.label}</dt>
              <dd className="mt-1.5">
                <Fig figure={m.figure} size={24} unitLabel={m.unit} />
              </dd>
              <dd className="mt-1.5 truncate tnum text-[11px] leading-[1.4] text-steel">{m.caption}</dd>
            </div>
          ))}
        </dl>
      ) : (
        // 대비용 — 상세 자료가 있는 부문이 하나도 없을 때만 보인다 (자료 없는 부문은 고를 수 없음)
        <div className="mt-[9px] flex min-h-[104px] flex-col items-center justify-center gap-1 rounded-[8px] bg-info-faint px-6 py-5 text-center">
          <p className="text-[14px] font-bold leading-[1.4] text-ink-deep">{active?.name} 부문 상세는 준비 중입니다</p>
          {active?.headline ? (
            <p className="text-[12px] leading-[1.4] text-steel">
              {active.headline.label} <FigureText figure={active.headline} />
            </p>
          ) : null}
          <p className="max-w-[520px] text-[12px] leading-[1.4] text-steel">이 부문의 영업점 데이터셋과 지표를 등록하면 같은 구조로 동작합니다.</p>
        </div>
      )}
    </section>
  );
}
