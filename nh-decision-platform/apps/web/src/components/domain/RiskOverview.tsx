"use client";

import { useMemo, useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import clsx from "clsx";
import { FigureText } from "@/components/data/FigureText";
import { TermText } from "@/components/data/TermText";
import { Fig, Tag, type MarkTone, type Tone } from "@/components/domain/overviewKit";
import { useSession } from "@/components/providers/SessionProvider";
import { IconChevron, SEVERITY_TEXT } from "@/components/ui/primitives";
import { derivedFigure } from "@/lib/derived";
import { UNIT_LABEL, formatFigure, formatValue } from "@/lib/format";
import { NO_VALUE } from "@/lib/period";
import type { AnalysisTab, DefaultRateSeries, DefaultRateTrend, Figure, Insight, ModelSummaryRow, RiskDashboard, Severity } from "@/lib/types";

/* ── 상태(심각도) 규칙 — 이 화면의 색 · 글자는 모두 여기서 ─────────────
 * 정상 < 관찰 < 주의 < 긴급. 판정은 태그로, 상태 색 글자는 '주의 이상'(문제 값)에만. */
const SEV_ORDER: Severity[] = ["info", "watch", "caution", "critical"];
const sevRank = (s: Severity) => SEV_ORDER.indexOf(s);
const isProblem = (s: Severity) => sevRank(s) >= sevRank("caution");
const SEV: Record<Severity, { tag: Tone; text: string }> = {
  info: { tag: "neutral", text: "" },
  watch: { tag: "attention", text: "" },
  caution: { tag: "attention", text: "!text-attention" },
  critical: { tag: "critical", text: "!text-critical" },
};
/** 모형 판정 → 상태 표시 (적정은 무채색 · 조건부 적정 주의 · 미흡/재개발 긴급) */
const MODEL_MARK: Record<Severity, MarkTone | null> = { info: null, watch: "attention", caution: "critical", critical: "critical" };
/** 기준 이탈 점 색 — 판정 태그 색과 같다 */
const MARK_DOT: Record<MarkTone, string> = { neutral: "bg-icon", attention: "bg-attention", critical: "bg-critical" };
/** 모형군 표기 */
const PORTFOLIO_LABEL: Record<ModelSummaryRow["portfolio"], string> = { corp: "일반기업", retail: "소매" };
/** 판정 근거 문구의 지표 · 판정어 → 기준 이탈 지표 (서버 판정 근거 문구 '지표 값(판정어)' 기준 — 화면이 경계 숫자를 갖지 않는다) */
const METRIC_KEY: Record<string, MetricKey> = { PSI: "psi", AR: "ar", "AR 하락률": "arDecline", "K-S": "ks", AUROC: "auroc" };
const OUT_QUALIFIERS = new Set(["큰 하락", "불안정", "하락 주의"]);

type MetricKey = "psi" | "ar" | "arDecline" | "ks" | "auroc";
const METRICS: MetricKey[] = ["psi", "ar", "arDecline", "ks", "auroc"];
const METRIC_LABEL: Record<MetricKey, string> = { psi: "PSI", ar: "AR", arDecline: "하락률", ks: "K-S", auroc: "AUROC" };

/** '… 증감(2025.09 대비)' → '2025.09' — 증감 수치의 비교 시점 (없으면 첫 시점 라벨) */
function basisOf(s: DefaultRateSeries | undefined): string | null {
  if (!s) return null;
  const m = /\(([^()]*?)\s*대비\)/.exec(s.deltaPP.label ?? "");
  return m?.[1] ?? s.points[0]?.label ?? null;
}
/** '2025.09' → '25.09' (다른 형식은 그대로) */
const shortYm = (label: string) => (/^\d{4}\.\d{2}$/.test(label) ? label.slice(2) : label);
const ymDot = (iso: string) => (/^\d{4}-\d{2}/.test(iso) ? iso.slice(0, 7).replace("-", ".") : iso);

/** 판정 기준을 벗어난 지표 (판정 근거 문구에서) */
function outMetrics(row: ModelSummaryRow): Set<MetricKey> {
  const out = new Set<MetricKey>();
  for (const part of row.verdictBasis.split("·")) {
    const m = /^\s*(.+?)\s+[-+]?[\d.,]+%?\s*\(([^)]+)\)\s*$/.exec(part);
    if (!m) continue;
    const key = METRIC_KEY[m[1]];
    if (key && OUT_QUALIFIERS.has(m[2].trim())) out.add(key);
  }
  return out;
}

/** 적용 경영목표 1건 → 라벨 · 값 줄 · 판 ('기업여신 전년 대비 +7.0% 이상 확대' · '+7.0%' · '… · v3') */
function goalParts(g: RiskDashboard["appliedGoals"][number]) {
  const at = g.value ? g.title.indexOf(g.value) : -1;
  const label = at > 0 ? g.title.slice(0, at).trim() : "";
  const line = at >= 0 ? g.title.slice(at).trim() : g.title;
  const version = /\bv\d+\b/.exec(g.source)?.[0] ?? "";
  const org = g.source.split("·")[0]?.trim() ?? "";
  return { label, line, version, org };
}

/** 'y축 눈금' — 0 기준, 데이터 최댓값을 nice step 으로 올린 균등 눈금 */
function ticksFor(max: number): number[] {
  const raw = max / 4 || 1;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const norm = raw / mag;
  const step = (norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 2.5 ? 2.5 : norm <= 5 ? 5 : 10) * mag;
  const n = Math.max(1, Math.ceil(max / step));
  return Array.from({ length: n + 1 }, (_, k) => Number((step * k).toFixed(4)));
}

/** 카드 공통 — 흰 바탕 · 10px 모서리 · 옅은 테두리 */
const CARD = "min-w-0 rounded-[10px] border border-hairline-soft bg-canvas";
/** 카드 제목 줄 — 16px 제목 + 12px 보조 글자 */
function CardHead({ id, title, hint, right }: { id?: string; title: string; hint?: ReactNode; right?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
      <div className="flex min-w-0 flex-wrap items-baseline gap-x-3 gap-y-1">
        <h2 id={id} className="text-[16px] font-bold leading-[1.4] text-ink-deep">
          {title}
        </h2>
        {hint ? <p className="tnum text-[12px] text-steel">{hint}</p> : null}
      </div>
      {right}
    </div>
  );
}

/**
 * 사업부서(신용리스크관리부) 1단계 현황 — Figma '신용리스크관리부 · 1단계 현황 · 개선안'(321:2).
 * 제목 줄 · (왼쪽) 기업규모별 부도율 표 · (오른쪽) 선택 규모 상세 + 5개 규모 추이
 * · 모형 모니터링 지표 · 현재 적용 경영목표. 수치는 모두 산출물(Figure · 계열 · 집계)에서만 온다.
 */
export function RiskOverview({
  dashboard,
  trend,
  tabs,
  tools,
  children,
}: {
  dashboard: RiskDashboard;
  trend: DefaultRateTrend;
  tabs: AnalysisTab[];
  tools?: ReactNode;
  /** 경영목표 다음에 둘 내용 (최근 감지된 변화 · 다음 단계) */
  children?: ReactNode;
}) {
  const { menu } = useSession();
  const pathname = usePathname();
  // 제목 — 이 화면이 속한 메뉴 묶음(부서) 이름
  const section = menu?.sections.find((s) => s.flow.some((i) => i.href === pathname));
  const orgName = section?.orgName ?? section?.section ?? "";

  const segs = trend.corpSegments;
  const asOf = dashboard.asOf;
  const months = Math.max(0, ...segs.map((s) => s.points.length));
  const basis = basisOf(segs[0]);
  // 상태(severity) 판정은 서버가 12개월 비교 시점(basis) 대비 상승폭으로 매긴다
  const compare = basis ? `${basis} 대비` : "증감";
  // 화면에 보이는 증감 = 진짜 전월 대비(월별 계열의 마지막 두 시점) — 시안 라벨 '전월 대비'
  const MOM = "전월 대비";
  const lastTwo = (s: DefaultRateSeries) => {
    const pts = s.points.filter((p) => p.value !== null && p.value !== undefined);
    return pts.length >= 2 ? { prev: pts[pts.length - 2], cur: pts[pts.length - 1] } : null;
  };
  /** 전월 대비 증감(%p) — 당월 − 전월 */
  const momOf = (s: DefaultRateSeries): Figure => {
    const t = lastTwo(s);
    const dec = s.latest.decimals ?? 3;
    return derivedFigure({
      id: `risk_mom_${s.key}`,
      label: `${s.label} 부도율 전월 대비`,
      value: t ? Number(((t.cur.value as number) - (t.prev.value as number)).toFixed(dec)) : null,
      unit: "PP",
      decimals: dec,
      expression: "당월 부도율 − 전월 부도율",
      inputs: t
        ? [
            { key: "cur", label: `당월(${t.cur.label})`, value: String(t.cur.value), unit: "%", source: "월별 부도율 계열" },
            { key: "prev", label: `전월(${t.prev.label})`, value: String(t.prev.value), unit: "%", source: "월별 부도율 계열" },
          ]
        : [],
      asOf: trend.asOf,
    });
  };
  /** 전월 대비 색 — 오른 경우에만 상태색(주의 이상), 내렸거나 같으면 중립 (on: 강조 줄의 중립은 진한 글자) */
  const momTone = (s: DefaultRateSeries, on = true) => ((momOf(s).value ?? 0) > 0 && SEV[s.severity].text) || (on ? "!text-ink-deep" : "!text-steel");

  /* ── 가장 시급한 규모 = 상태가 가장 높고, 같으면 상승폭이 큰 규모 ── */
  const ranked = useMemo(
    () => [...segs].sort((a, b) => sevRank(b.severity) - sevRank(a.severity) || (b.deltaPP.value ?? 0) - (a.deltaPP.value ?? 0)),
    [segs],
  );
  const urgent = ranked[0];
  const [selectedKey, setSelectedKey] = useState(urgent?.key ?? "");
  const sel = segs.find((s) => s.key === selectedKey) ?? urgent;
  const problemCount = segs.filter((s) => isProblem(s.severity)).length;

  const countFig = (id: string, label: string, value: number, expression: string): Figure =>
    derivedFigure({ id, label, value, unit: "CNT", decimals: 0, expression, inputs: [], asOf });

  /* ── 새 분석 결과 ── */
  const opinions = dashboard.opinions;
  const opinionCounts = SEV_ORDER.map((s) => [s, opinions.filter((o) => o.severity === s).length] as const).filter(([, n]) => n > 0);
  const tabHref = (o: Insight) => {
    const key = tabs.find((t) => t.insightId === o.id)?.tabKey ?? o.tabKey;
    return key ? `/risk/analysis/${key}` : "/risk/analysis";
  };
  /** 선택 규모와 관련된 분석 — 제목에 규모 이름이 있는 분석(더 긴 이름이 겹치면 제외), 없으면 상태가 가장 높은 분석 */
  const relatedOf = (s: DefaultRateSeries | undefined): { item: Insight; matched: boolean } | null => {
    if (!s) return null;
    const hit = opinions.find((o) => o.title.includes(s.label) && !segs.some((x) => x.key !== s.key && x.label.includes(s.label) && o.title.includes(x.label)));
    if (hit) return { item: hit, matched: true };
    const top = [...opinions].sort((a, b) => sevRank(b.severity) - sevRank(a.severity) || (b.rankScore ?? 0) - (a.rankScore ?? 0))[0];
    return top ? { item: top, matched: false } : null;
  };
  const relatedHit = relatedOf(sel);
  const related = relatedHit?.item ?? null;
  // 규모 이름이 맞는 분석이 없으면 '관련'이라 부르지 않는다 — 가장 시급한 분석으로 안내
  const relatedLabel = relatedHit?.matched ? "✦ 관련 분석 결과" : "✦ 우선 검토 분석";

  /* ── 모형 ── */
  const models = [...dashboard.corpModels, ...dashboard.retailModels];
  const verdictShort = (m: ModelSummaryRow) => m.verdict.split("—")[0].trim();
  const groups = (["corp", "retail"] as const).map((p) => ({ key: p, label: PORTFOLIO_LABEL[p], rows: p === "corp" ? dashboard.corpModels : dashboard.retailModels })).filter((g) => g.rows.length > 0);
  const groupLine = groups.map((g) => `${g.label} ${g.rows.length}`).join(" · ");

  /* ── 경영목표 ── */
  const goals = dashboard.appliedGoals.map((g) => ({ ...goalParts(g), raw: g }));


  /* ── 차트 축 (막대 · 추이 공통 0 ~ yMax) ── */
  const allMax = Math.max(0, ...segs.flatMap((s) => s.points.map((p) => p.value ?? 0)));
  const yTicks = ticksFor(allMax);
  const yMax = yTicks[yTicks.length - 1] || 1;
  const pctUnit = segs[0]?.latest.unit === "PCT" ? "%" : "";
  const axisText = `${yTicks[0]}–${yMax}${pctUnit}`;

  /** 전월 부도율 — 월별 계열의 직전 시점 값 */
  const prevFig = (s: DefaultRateSeries): Figure | null => {
    const t = lastTwo(s);
    return t
      ? derivedFigure({
          id: `risk_prev_${s.key}`,
          label: `${s.label} 전월 부도율(${t.prev.label})`,
          value: t.prev.value as number,
          unit: s.latest.unit,
          decimals: s.latest.decimals,
          expression: "월별 부도율 계열의 직전 시점",
          inputs: [{ key: "prev", label: t.prev.label, value: String(t.prev.value), unit: "%", source: "월별 부도율 계열" }],
          asOf,
        })
      : null;
  };
  /** 비교 시점(basis) 부도율 — 서버 증감(deltaPP)의 기준 값 */
  const basisFig = (s: DefaultRateSeries): Figure | null => {
    const b = basisOf(s);
    const p = s.points.find((x) => x.label === b);
    return p && typeof p.value === "number"
      ? derivedFigure({
          id: `risk_basis_${s.key}`,
          label: `${s.label} 부도율(${p.label})`,
          value: p.value,
          unit: s.latest.unit,
          decimals: s.latest.decimals,
          expression: "월별 부도율 계열의 비교 시점 값",
          inputs: [{ key: "basis", label: p.label, value: String(p.value), unit: "%", source: "월별 부도율 계열" }],
          asOf,
        })
      : null;
  };

  return (
    <>
      {/* 제목 줄 — 종합기획부 현황·목표와 같은 22px 제목 · 기준월 선택 · 내보내기 */}
      <header className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3">
        <div className="flex min-w-0 flex-wrap items-center gap-y-2">
          <h1 className="text-[22px] font-bold leading-[1.25] text-ink-deep">{orgName ? `${orgName} 현황` : "현황"}</h1>
          <span aria-hidden="true" className="mx-4 h-[14px] w-px bg-hairline-soft" />
          <span className="text-[13px] font-medium text-steel">기업여신 신용리스크 · 부도율 · 평가모형</span>
        </div>
        {tools}
      </header>

      {/* 본문 2단 — 표(1640) · 상세(1080), 간격 16, 높이 맞춤 */}
      <div className="mt-[15px] grid grid-cols-1 items-stretch gap-4 xl:grid-cols-[1640fr_1080fr]">
        <section aria-labelledby="risk-dr" className={clsx(CARD, "flex h-full flex-col px-6 pb-4 pt-5")}>
          <CardHead
            id="risk-dr"
            title="기업규모별 부도율"
            hint={`${months ? `최근 ${months}개월 · ` : ""}${MOM} 변화`}
            right={<p className="tnum text-[12px] font-medium text-steel">주의 이상 {problemCount}개 규모</p>}
          />

          <div className="-mx-2 mt-3 overflow-x-auto">
            <div role="table" aria-label="기업규모별 부도율" className="min-w-[640px]">
              <div role="row" className={clsx(DR_GRID, "h-8 items-center rounded-lg bg-surface-soft text-[11px] font-bold text-steel")}>
                <span role="columnheader">기업규모</span>
                <span role="columnheader">부도율</span>
                <span role="columnheader">
                  <span className="sr-only">부도율 막대</span>
                </span>
                <span role="columnheader">{MOM}</span>
                <span role="columnheader">{months ? `${months}개월 추이` : "추이"}</span>
                {/* 태그 안쪽 여백(px-2)만큼 들여 '정상' 글자 시작점과 맞춘다 */}
                <span role="columnheader" className="pl-2">판정</span>
                <span role="columnheader">
                  <span className="sr-only">선택</span>
                </span>
              </div>
              <div role="rowgroup" className="mt-1">
                {segs.map((s, idx) => {
                  const on = s.key === sel?.key;
                  const prevOn = idx > 0 && segs[idx - 1].key === sel?.key;
                  const line = idx > 0 && !on && !prevOn;
                  const v = s.latest.value ?? 0;
                  return (
                    <div
                      key={s.key}
                      role="row"
                      aria-selected={on}
                      tabIndex={0}
                      onClick={() => setSelectedKey(s.key)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          setSelectedKey(s.key);
                        }
                      }}
                      className={clsx(DR_GRID, "group relative h-[52px] cursor-pointer items-center outline-none")}
                    >
                      {line ? <span aria-hidden="true" className="absolute inset-x-2 top-0 h-px bg-track" /> : null}
                      {/* 선택 줄 — 옅은 바탕만 (왼쪽 강조선 없음 · 팀 규칙) */}
                      <span
                        aria-hidden="true"
                        className={clsx(
                          "absolute inset-x-0 inset-y-[2px] rounded-lg transition-colors",
                          on ? "bg-info-faint" : "group-hover:bg-surface-soft group-focus-visible:bg-surface-soft",
                          "group-focus-visible:ring-2 group-focus-visible:ring-primary",
                        )}
                      />
                      <span role="cell" className={clsx("relative text-[14px] leading-[20px] text-ink-deep", on ? "font-bold" : "font-medium")}>
                        {s.label}
                      </span>
                      <span role="cell" className="relative">
                        <Fig figure={s.latest} size={15} />
                      </span>
                      <span role="cell" className="relative pr-10">
                        <span className="block h-1.5 w-full max-w-[130px] overflow-hidden rounded-pill bg-track" role="presentation">
                          <span
                            className={clsx("block h-full origin-left rounded-pill motion-safe:animate-grow-x", on ? "bg-primary" : "bg-icon")}
                            style={{ width: `${Math.min(100, Math.max(0, (v / yMax) * 100))}%`, ["--i" as string]: idx }}
                          />
                        </span>
                      </span>
                      <span role="cell" className="relative text-[13px]">
                        <FigureText figure={momOf(s)} signed plain strong className={clsx(momTone(s, on), !on && "!font-medium")} />
                      </span>
                      <span role="cell" className="relative pr-10">
                        <Spark values={s.points.map((p) => p.value)} color={on ? "var(--color-primary)" : "var(--color-icon)"} label={`${s.label} 부도율 ${s.points.length}개월 추이`} />
                      </span>
                      <span role="cell" className="relative">
                        <Tag tone={SEV[s.severity].tag}>{SEVERITY_TEXT[s.severity]}</Tag>
                      </span>
                      <span role="cell" aria-hidden="true" className="relative flex justify-end text-icon">
                        <IconChevron />
                      </span>
                    </div>
                  );
                })}
              </div>
              <span aria-hidden="true" className="mx-2 mt-2 block h-px bg-track" />
            </div>
          </div>

          <p className="mt-auto pt-3 text-[11px] leading-[16px] text-steel">
            판정: {compare} 상승폭 기준 ({SEV_ORDER.map((s) => SEVERITY_TEXT[s]).join(" < ")}) · 막대 {axisText} 공통 축 · 추이선은 규모별 개별 축
          </p>
        </section>

        {/* 선택 규모 상세 */}
        <section aria-label="선택한 규모 상세" className={clsx(CARD, "flex h-full flex-col overflow-hidden")}>
          {sel ? (
            <>
              <div className="flex flex-1 flex-col px-6 pb-4 pt-5">
                {/* 사용자 결정: 상세 패널의 '분석 결과 보기' 버튼은 두지 않는다 (아래 '관련 분석 결과' 줄과 하단 '다음 단계'로 이동) */}
                <div className="flex min-w-0 items-center gap-2.5">
                  <h2 className="truncate text-[18px] font-bold leading-[1.25] text-ink-deep">{sel.label} 부도율</h2>
                  <Tag tone={SEV[sel.severity].tag}>{SEVERITY_TEXT[sel.severity]}</Tag>
                </div>

                <div className="mt-4 flex flex-wrap items-baseline gap-x-4 gap-y-1">
                  <Fig key={`now-${sel.key}`} figure={sel.latest} size={28} />
                  <p className="tnum text-[12px] text-steel">
                    {prevFig(sel) ? (
                      <>
                        전월 <FigureText figure={prevFig(sel) as Figure} plain className="!font-normal !text-steel" /> 대비{" "}
                        <FigureText figure={momOf(sel)} signed plain strong className={momTone(sel)} />
                      </>
                    ) : null}
                    {basisFig(sel) ? (
                      <>
                        {prevFig(sel) ? (
                          <span aria-hidden="true" className="mx-2">
                            ·
                          </span>
                        ) : null}
                        {basisOf(sel)} <FigureText figure={basisFig(sel) as Figure} plain className="!font-normal !text-steel" /> 대비{" "}
                        <FigureText figure={sel.deltaPP} signed plain strong className="!text-ink-deep" />
                      </>
                    ) : null}
                  </p>
                </div>

                <span aria-hidden="true" className="mt-4 block h-px bg-track" />

                <div className="mt-3.5 flex items-baseline justify-between gap-x-3">
                  <h3 className="text-[14px] font-bold leading-[20px] text-ink-deep">월별 부도율 추이 · {segs.length}개 규모</h3>
                  <p className="text-[11px] text-steel">선택한 규모만 강조</p>
                </div>
                <div className="mt-3">
                  <RiskTrend key={sel.key} segs={segs} selected={sel} yTicks={yTicks} />
                </div>
              </div>

              {related ? (
                <Link
                  href={tabHref(related)}
                  className="group flex h-12 shrink-0 items-center gap-4 border-t border-hairline-soft bg-surface-soft px-6 text-[13px] transition-colors hover:bg-track focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary"
                >
                  <span className="shrink-0 text-[12px] font-bold text-primary-deep">{relatedLabel}</span>
                  <span className="flex min-w-0 items-center gap-2">
                    <span className="truncate font-medium text-ink-deep group-hover:underline">{related.title}</span>
                    <Tag tone={SEV[related.severity].tag}>{SEVERITY_TEXT[related.severity]}</Tag>
                  </span>
                  <IconChevron className="ml-auto shrink-0 text-icon" />
                </Link>
              ) : null}
            </>
          ) : (
            <p className="m-6 rounded-lg bg-surface-soft px-5 py-8 text-center text-[13px] text-steel">부도율 자료가 없어요.</p>
          )}
        </section>
      </div>

      {/* 모형 모니터링 지표 — 전체 폭 */}
      <section aria-labelledby="risk-models" className={clsx(CARD, "mt-6 px-6 pb-4 pt-5")}>
        <CardHead id="risk-models" title="모형 모니터링 지표" hint={`기준 ${ymDot(asOf)} · ${models.length}개 모형`} />
        <div className="-mx-2 mt-3 overflow-x-auto">
          <table className="w-full min-w-[880px] table-fixed border-collapse text-[13.5px]">
            <colgroup>
              {MODEL_COLS.map((w, i) => (
                <col key={i} style={{ width: w }} />
              ))}
            </colgroup>
            <thead>
              <tr className="text-left text-[11px] font-bold text-steel [&>th:first-child]:rounded-l-lg [&>th:last-child]:rounded-r-lg [&>th]:bg-surface-soft">
                <th scope="col" className="h-8 pl-4 font-bold">
                  구분
                </th>
                <th scope="col" className="h-8 pl-4 font-bold">
                  모형
                </th>
                <MetricHead code="PSI" label="PSI" />
                <MetricHead code="AR" label="AR" />
                <MetricHead code="AR_DECLINE" label="하락률" />
                <MetricHead code="KS" label="K-S" />
                <MetricHead code="AUROC" label="AUROC" />
                <th scope="col" className="h-8 font-bold">
                  이탈 지표
                </th>
                <th scope="col" className="h-8 pl-2 font-bold">
                  판정
                </th>
              </tr>
            </thead>
            {groups.map((g, gi) => (
              <tbody key={g.key} className={clsx(gi > 0 && "border-t border-hairline")}>
                {g.rows.map((row, i) => {
                  const out = outMetrics(row);
                  const mark = MODEL_MARK[row.verdictSeverity];
                  const off = METRICS.filter((k) => out.has(k));
                  const rowLine = i > 0 ? "border-t border-track" : "";
                  return (
                    <tr key={row.modelCode} className="h-[38px]">
                      {i === 0 ? (
                        <th scope="rowgroup" rowSpan={g.rows.length} className="bg-page pl-4 text-left align-middle">
                          <span className="block text-[13px] font-bold leading-[18px] text-ink-deep">{g.label}</span>
                          <span className="tnum block text-[11px] font-normal leading-[16px] text-steel">{g.rows.length}개 모형</span>
                        </th>
                      ) : null}
                      <th scope="row" className={clsx(rowLine, "pl-4 text-left text-[14px] font-medium text-ink-deep")} title={row.name}>
                        {row.segment}
                      </th>
                      {METRICS.map((k) => {
                        const f = row[k];
                        const isOut = out.has(k);
                        return (
                          <td key={k} className={clsx(rowLine, "tnum")}>
                            {f ? (
                              <span className="inline-flex items-center gap-1.5">
                                {/* 사용자 결정: 지표 값은 글자만 — 호버 설명은 머리글(용어)에만 둔다 */}
                                <span className={isOut ? "font-bold text-ink-deep" : "font-normal text-ink-deep"}>{formatFigure(f)}</span>
                                {isOut ? <span aria-label="판정 기준 이탈" role="img" className={clsx("h-[5px] w-[5px] shrink-0 rounded-circle", MARK_DOT[mark ?? "neutral"])} /> : null}
                              </span>
                            ) : (
                              <span className="text-steel">{NO_VALUE}</span>
                            )}
                          </td>
                        );
                      })}
                      <td className={clsx(rowLine, "text-[13px]")}>
                        {off.length ? <span className="font-medium text-ink-deep">{off.map((k) => METRIC_LABEL[k]).join(" · ")}</span> : <span className="text-steel">{NO_VALUE}</span>}
                      </td>
                      <td className={rowLine}>
                        <Tag tone={mark ?? "neutral"}>{verdictShort(row)}</Tag>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            ))}
          </table>
          <span aria-hidden="true" className="block h-px bg-track" />
        </div>
        <p className="mt-2.5 flex items-center gap-1.5 text-[11px] leading-[16px] text-steel">
          <span aria-hidden="true" className="h-[5px] w-[5px] rounded-circle bg-steel" />
          판정 기준을 벗어난 지표 (색은 판정 태그와 같음)
        </p>
      </section>

      {/* 현재 적용 경영목표 */}
      <section aria-labelledby="risk-goals" className={clsx(CARD, "mt-4 px-6 pb-6 pt-5")}>
        {/* 사용자 결정: '전체 목표 관리' 링크는 두지 않는다 (사업부서 화면에서 종합기획부 목표 화면으로 보내지 않는다) */}
        <CardHead id="risk-goals" title="현재 적용 경영목표" />
        {goals.length === 0 ? (
          <p className="mt-4 rounded-lg bg-page py-6 text-center text-[13px] text-steel">적용 중인 경영목표가 없어요.</p>
        ) : (
          <ul className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-3 xl:grid-cols-4">
            {goals.map((g) => (
              <li key={g.raw.title} className="flex h-[62px] min-w-0 flex-col justify-center rounded-lg bg-page px-3.5">
                <span className="flex items-baseline justify-between gap-3">
                  <span className="truncate text-[11px] leading-[16px] text-steel">{g.label || g.org}</span>
                  {g.version ? <span className="shrink-0 text-[11px] font-medium leading-[16px] text-steel">{g.version}</span> : null}
                </span>
                <span className="mt-0.5 truncate tnum text-[15px] font-bold leading-[21px] text-ink-deep">{g.line}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {children}

    </>
  );
}

/** 부도율 표 7칸 — 기업규모 · 부도율 · 막대 · 전월 대비 · 추이 · 판정 · › (시안 321:77 열 위치) */
const DR_GRID = "grid grid-cols-[168fr_80fr_170fr_100fr_170fr_64fr_24fr] px-4";
/** 모형 표 열 폭 — 구분 · 모형 · PSI · AR · 하락률 · K-S · AUROC · 이탈 지표 · 판정 (시안 321:194) */
const MODEL_COLS = ["8.8%", "11.9%", "9.7%", "9.7%", "9.7%", "9.7%", "11.2%", "12.6%", "16.7%"];


/** 지표 머리 — 밑줄 용어(호버 설명)만. 같은 설명의 ⓘ 아이콘은 두지 않는다 */
function MetricHead({ code, label }: { code: string; label: string }) {
  return (
    <th scope="col" className="h-8 font-bold">
      <TermText code={code} label={label} />
    </th>
  );
}

/** 12개월 스파크라인 — 130×20, 규모별 개별 축 · 왼쪽 → 오른쪽으로 그려진다 */
function Spark({ values, color, label }: { values: (number | null)[]; color: string; label: string }) {
  const W = 130;
  const H = 20;
  const nums = values.filter((v): v is number => typeof v === "number");
  if (nums.length < 2) return <span className="text-[12px] text-steel">{NO_VALUE}</span>;
  const min = Math.min(...nums);
  const max = Math.max(...nums);
  const span = max - min || 1;
  const pts = values
    .map((v, i) => (typeof v === "number" ? `${((W - 2) * i) / Math.max(1, values.length - 1) + 1},${(H - 2 - ((v - min) / span) * (H - 4)).toFixed(1)}` : null))
    .filter(Boolean)
    .join(" ");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="img" aria-label={label} className="block max-w-full">
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" pathLength={100} strokeDasharray="100 100" className="motion-safe:animate-draw" />
    </svg>
  );
}

/** 월별 부도율 — 5개 규모를 한 축(0 ~ yMax)에. 선택 규모는 primary 선(왼쪽 → 오른쪽 그리기) · 끝점 · 굵은 라벨, 나머지는 회색 선 + 끝 라벨 */
function RiskTrend({ segs, selected, yTicks }: { segs: DefaultRateSeries[]; selected: DefaultRateSeries; yTicks: number[] }) {
  const W = 492;
  const H = 180;
  const L = 28;
  const PLOT_R = 380; // 선 끝 x — 오른쪽은 끝 라벨 자리
  const T = 6;
  const B = 26;
  const n = Math.max(0, ...segs.map((s) => s.points.length));
  const yMax = yTicks[yTicks.length - 1] || 1;
  const x = (i: number) => L + ((PLOT_R - L) * i) / Math.max(1, n - 1);
  const y = (v: number) => T + (H - T - B) * (1 - v / yMax);
  const pts = (s: DefaultRateSeries) =>
    s.points
      .map((p, i) => (typeof p.value === "number" ? `${x(i).toFixed(1)},${y(p.value).toFixed(1)}` : null))
      .filter(Boolean)
      .join(" ");
  const labels = selected.points.map((p) => p.label);
  const lastIdx = selected.points.length - 1;
  const last = selected.points[lastIdx];
  const unit = selected.latest.unit === "PCT" ? "%" : "";
  const decimals = yTicks.some((t) => !Number.isInteger(t)) ? 1 : 0;

  // 끝 라벨 — 값 위치에 두고, 겹치면 최소 간격(13)으로 밀어낸다
  const ends = segs
    .map((s) => {
      const i = s.points.length - 1;
      const v = s.points[i]?.value;
      return typeof v === "number" ? { s, i, v, cy: y(v), ly: y(v) } : null;
    })
    .filter((e): e is NonNullable<typeof e> => e !== null)
    .sort((a, b) => a.cy - b.cy);
  for (let k = 1; k < ends.length; k++) ends[k].ly = Math.max(ends[k].ly, ends[k - 1].ly + 13);
  const others = ends.filter((e) => e.s.key !== selected.key);
  const mine = ends.find((e) => e.s.key === selected.key);
  const valueText = (s: DefaultRateSeries) => `${formatValue(s.latest)}${UNIT_LABEL[s.latest.unit]}`;

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="block h-auto w-full overflow-visible"
      role="img"
      aria-label={`월별 부도율 추이 ${segs.length}개 규모 — ${labels[0] ?? ""}부터 ${labels[lastIdx] ?? ""}까지. ${selected.label} 강조, 최근 ${last?.value ?? NO_VALUE}${unit}. ${others.map((e) => `${e.s.label} ${valueText(e.s)}`).join(", ")}`}
    >
      {yTicks.map((t, k) => (
        <g key={t}>
          <line x1={L} x2={PLOT_R} y1={y(t)} y2={y(t)} stroke={k === 0 ? "var(--chart-axis)" : "var(--chart-grid)"} strokeWidth="1" />
          <text x={L - 8} y={y(t) + 3.5} textAnchor="end" fontSize="10" fill="var(--color-steel)" className="tnum">
            {t.toFixed(decimals)}
            {unit}
          </text>
        </g>
      ))}
      {labels.map((l, i) =>
        i % 3 === 0 || i === lastIdx ? (
          <text
            key={l}
            x={x(i)}
            y={H - 8}
            textAnchor="middle"
            fontSize="10"
            fontWeight={i === lastIdx ? 700 : 400}
            fill={i === lastIdx ? "var(--color-ink-deep)" : "var(--color-steel)"}
            className="tnum"
          >
            {shortYm(l)}
          </text>
        ) : null,
      )}
      {others.map((e) => (
        <g key={e.s.key} className="motion-safe:animate-fade-late">
          <polyline points={pts(e.s)} fill="none" stroke="var(--color-icon)" strokeWidth="1.2" strokeLinejoin="round" strokeLinecap="round" />
          <circle cx={x(e.i)} cy={e.cy} r="2.5" fill="var(--color-icon)" />
          <text x={PLOT_R + 12} y={e.ly + 3.5} fontSize="11" fill="var(--color-steel)" className="tnum">
            <tspan fontWeight={500}>{e.s.label}</tspan>
            <tspan dx="5" fontWeight={700}>
              {valueText(e.s)}
            </tspan>
          </text>
        </g>
      ))}
      <polyline points={pts(selected)} fill="none" stroke="var(--color-primary)" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" pathLength={100} strokeDasharray="100 100" className="motion-safe:animate-draw" />
      {mine ? (
        <g className="motion-safe:animate-fade-late">
          <circle cx={x(mine.i)} cy={mine.cy} r="4.5" fill="var(--color-primary)" stroke="var(--color-canvas)" strokeWidth="2" />
          <text x={PLOT_R + 12} y={mine.ly + 3.5} fontSize="11" fontWeight={700} fill="var(--color-primary-deep)" className="tnum">
            {selected.label}
            <tspan dx="5">{valueText(selected)}</tspan>
          </text>
        </g>
      ) : null}
    </svg>
  );
}
