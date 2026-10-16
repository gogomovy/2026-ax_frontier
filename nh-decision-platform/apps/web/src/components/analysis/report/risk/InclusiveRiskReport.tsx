"use client";
/**
 * 신용리스크관리부 2단계 · 포용금융 확대 관련 신용리스크 (시안 352:2) — Agent 의견 → 충당금 비중 변화 → 상품별 증가 기여 → 건전성 현황 → 관리방안 → 근거 · 상세 데이터.
 * 숫자 · 표 · 문장은 모두 보고서(inclusive_risk)에서 온다. 관리 임계(+%p)는 화면 자료에 없어 '–' 로 둔다.
 */
import Link from "next/link";
import type { ReactNode } from "react";
import clsx from "clsx";
import { FigureText } from "@/components/data/FigureText";
import { RichText } from "@/components/data/RichText";
import { toPoliteText } from "@/lib/sentence";
import { Fig } from "@/components/domain/overviewKit";
import {
  AgentOpinionBox,
  BeforeAfter,
  ChartBlock,
  ColumnRule,
  DetailAccordion,
  GroupedColumns,
  Legend,
  MiniTag,
  NoValue,
  SectionCard,
  TEXT_LINK,
  TwoColumns,
  ZERO_LABEL,
  combine,
  figText,
  fmtNum,
  isBarValue,
  type DetailRowSpec,
} from "@/components/analysis/report/kit";
import { Waterfall } from "@/components/analysis/report/risk/riskCharts";
import { IconChevron, IconInfo } from "@/components/ui/primitives";
import { calloutOf, chartOf, kvOf, labelParts, listItems, num, politeTitle, sectionById, splitGuideItem, tableOf } from "@/lib/analysisReport";
import { UNIT_LABEL, formatFigure } from "@/lib/format";
import { NO_VALUE } from "@/lib/period";
import type { Figure, ReportDoc } from "@/lib/types";

/** 보고서 섹션 위치 (보고서 문서의 섹션 id) */
const SEC = { scope: "i1-scope", data: "i2-data", group: "i3-group", product: "i3-product", exposure: "i4-exposure", opinion: "i5-opinion" } as const;
/** 근거 · 상세 데이터 줄 (시안 383:467) — 대상 상품군 표 · 데이터 및 산출 기준 · 상품별 기여도 표 */
const DETAIL_ROWS: DetailRowSpec[] = [{ section: SEC.scope }, { section: SEC.data }, { section: SEC.product, title: "caption" }];
/** 상품군 비중 증감 수치 id 앞말 */
const GROUP_DELTA = /^inc_grp_.+_delta$/;
/** 수행방안(진행사업) 화면 */
const GUIDES_HREF = "/risk/guides";
/** 단위 환산 — 1억원 = 100백만원 · 1조원 = 10,000억원 */
const MN_PER_EOK = 100;
const EOK_PER_JO = 10000;

/** 백만원 수치 → 억원 수치 (계산 추적은 원래 수치 그대로) */
function asEok(f: Figure | undefined): Figure | null {
  if (!f) return null;
  return f.unit === "KRW_MN" && f.value != null ? { ...f, value: f.value / MN_PER_EOK, unit: "KRW_BN", decimals: 0 } : f;
}
/** 백만원 → '3조 4,122억원' */
function joEok(f: Figure | undefined): string {
  if (!f || f.value == null || f.unit !== "KRW_MN") return f ? figText(f) : NO_VALUE;
  const eok = Math.round(f.value / MN_PER_EOK);
  const jo = Math.floor(eok / EOK_PER_JO);
  const rest = eok % EOK_PER_JO;
  return jo > 0 ? `${fmtNum(jo)}조${rest ? ` ${fmtNum(rest)}억원` : "원"}` : `${fmtNum(rest)}억원`;
}

export function InclusiveRiskReport({ report, rerun }: { report: ReportDoc; rerun?: string | null }) {
  const f = report.figures;
  const op = report.opinions[0];
  return (
    <>
      {op ? (
        <AgentOpinionBox
          opinion={op}
          headline={politeTitle(op.title, op.figures)}
          evidence={report.evidence}
          evidenceTitle={`${report.title} 근거`}
          rerun={rerun}
          kpis={[
            {
              key: "share",
              label: "포용금융 충당금 비중",
              value: <BeforeAfter before={f.share_base} after={f.share_now} />,
              sub: (
                <>
                  {figText(f.share_delta_pp, undefined, true)} · 관리 임계 <span className="text-steel">{NO_VALUE}</span>
                </>
              ),
            },
            {
              key: "prov",
              label: "포용금융 상품 충당금",
              value: <BeforeAfter before={asEok(f.prov_inclusive_base)} after={asEok(f.prov_inclusive_now)} />,
              sub: `${f.share_delta_pct?.label ?? ""} ${figText(f.share_delta_pct, undefined, true)} · 전체 충당금 ${joEok(f.prov_total_now)}`,
            },
            {
              key: "exposure",
              label: "해당 풀 익스포저",
              value: f.inc_exposure_cnt_now ? (
                <span className="inline-flex items-baseline gap-1">
                  <Fig figure={f.inc_exposure_cnt_now} size={22} valueClass="text-primary-deep" unitLabel="" />
                  <span className="text-[12px] font-bold text-primary-deep">{UNIT_LABEL[f.inc_exposure_cnt_now.unit]}</span>
                </span>
              ) : (
                <NoValue className="text-[22px]" />
              ),
              sub: `기준시점 대비 ${figText(f.inc_exposure_cnt_growth, undefined, true)} · ${figText(f.inc_exposure_amt_now)}`,
            },
          ]}
        />
      ) : null}
      <ShareChange report={report} />
      <Products report={report} />
      <Soundness report={report} />
      <Plans report={report} />
      <DetailAccordion report={report} rows={DETAIL_ROWS} />
    </>
  );
}

/** 충당금 비중 변화 — 상품군별 충당금(2시점) · 비중 변화 폭포 */
function ShareChange({ report }: { report: ReportDoc }) {
  const f = report.figures;
  const chart = chartOf(sectionById(report, SEC.group));
  if (!chart || chart.series.length === 0) return null;
  const [base, now] = chart.series;
  const cats = base.points.map((p) => p.label);
  const growth = cats.map((c, i) =>
    combine({
      id: `inc_grp_growth_${i}`,
      label: `${c} 충당금 증가율`,
      inputs: [
        { id: `${c}_now`, label: `${c} 충당금(${now?.name ?? ""})`, value: now?.points[i]?.value ?? null, unit: chart.unit, decimals: 0, dataOrigin: report.dataOrigin },
        { id: `${c}_base`, label: `${c} 충당금(${base.name})`, value: base.points[i]?.value ?? null, unit: chart.unit, decimals: 0, dataOrigin: report.dataOrigin },
      ],
      calc: ([a, b]) => (b ? (a / b - 1) * 100 : 0),
      expression: "(비교시점 ÷ 기준시점 − 1) × 100",
      unit: "PCT",
      decimals: 1,
      asOf: report.asOf,
    }),
  );
  const g = growth.map((x) => x?.value ?? null);
  const fastest = g.length ? g.indexOf(Math.max(...g.map((v) => v ?? -Infinity))) : -1;
  const formula = kvOf(sectionById(report, SEC.data)).find((k) => k.label.includes("산출식"))?.value;
  const deltas = Object.values(f)
    .filter((x) => GROUP_DELTA.test(x.id) && x.value != null)
    .sort((a, b) => (b.value ?? 0) - (a.value ?? 0));
  const top = deltas[0];
  const topShare = top && f.share_delta_pp?.value ? Math.round(((top.value ?? 0) / f.share_delta_pp.value) * 100) : null;
  const unitLabel = labelParts(chart.title).qualifier ?? "";
  return (
    <SectionCard title="충당금 비중 변화" hint={`${formula ? `${formula.replace(/\s*×\s*100$/, "")} · ` : ""}${chart.series.map((s) => s.name).join(" → ")}`}>
      <TwoColumns>
        <ChartBlock
          title={chart.title.split(" — ")[0]}
          right={
            <span className="inline-flex items-center gap-2">
              <Legend
                items={[
                  { label: base.name, swatch: "bg-hairline-soft" },
                  ...(now ? [{ label: now.name, swatch: "bg-info-line" }] : []),
                ]}
              />
              {unitLabel ? <span>· {unitLabel}</span> : null}
            </span>
          }
          caption={fastest >= 0 && g.every((v) => (v ?? 0) > 0) ? `${cats.length}개 상품군 모두 충당금이 늘었고, ${cats[fastest]}이 ${fmtNum(g[fastest], 1, true)}%로 가장 빠르게 늘었어요.` : null}
        >
          <GroupedColumns
            ariaLabel={chart.title}
            categories={cats}
            strong={fastest >= 0 ? fastest : null}
            decimals={0}
            tickFormat={(v) => (v >= 1000 ? `${fmtNum(v / 1000)}천` : fmtNum(v))}
            series={[
              { name: base.name, values: base.points.map((p) => p.value), tone: "bg-hairline-soft" },
              ...(now ? [{ name: now.name, values: now.points.map((p) => p.value), tone: "bg-info-line", strongTone: "bg-primary" }] : []),
            ]}
            footer={(i) => (growth[i] ? <FigureText figure={growth[i] as Figure} signed plain className={clsx("text-[11px] !text-primary-deep")} /> : null)}
          />
        </ChartBlock>
        <ColumnRule />
        <ChartBlock
          title={`비중 ${figText(f.share_base)} → ${figText(f.share_now)} · 상품군별 기여`}
          right="%p"
          caption={top && topShare !== null ? `상승분 ${figText(f.share_delta_pp)} 가운데 ${topShare}%(${figText(top, undefined, true)})가 ${top.label.replace(/\s*비중 증감$/, "")} 몫이에요.` : null}
        >
          {f.share_base?.value != null && f.share_now?.value != null ? (
            <Waterfall
              ariaLabel="포용금융 충당금 비중 변화 — 상품군별 기여"
              steps={[
                { key: "start", label: base.name, value: f.share_base.value, kind: "start" },
                ...deltas.map((d) => ({ key: d.id, label: d.label.replace(/\s*비중 증감$/, ""), value: d.value as number, kind: "delta" as const })),
                { key: "end", label: now?.name ?? "", value: f.share_now.value, kind: "end" },
              ]}
            />
          ) : (
            <NoValue />
          )}
        </ChartBlock>
      </TwoColumns>
    </SectionCard>
  );
}

/** 상품별 증가 기여 — 상위 10건 가로 막대 (상위 상품과 같은 상품군은 강조) */
function Products({ report }: { report: ReportDoc }) {
  const t = tableOf(sectionById(report, SEC.product));
  if (!t || t.rows.length === 0) return null;
  const rows = t.rows.map((r) => ({ name: String(r.name ?? ""), group: String(r.group ?? ""), diff: num(r.diff ?? null), diffRaw: String(r.diff ?? ""), share: num(r.contribution ?? null), shareRaw: String(r.contribution ?? "") }));
  const max = Math.max(0, ...rows.map((r) => r.diff ?? 0));
  const lead = rows[0]?.group;
  const strong = rows.filter((r) => r.group === lead);
  const sum = strong.reduce((a, r) => a + (r.share ?? 0), 0);
  const unit = /단위\s*([^.\s]+)/.exec(t.note ?? "")?.[1];
  const formula = /기여도\s*=\s*([^.]+)/.exec(t.note ?? "")?.[0];
  return (
    <SectionCard title="상품별 증가 기여" hint={[t.caption, formula].filter(Boolean).join(" · ")}>
      <ul className="flex flex-col gap-2.5">
        {rows.map((r, i) => {
          const on = r.group === lead;
          return (
            <li key={r.name} className="grid grid-cols-[minmax(0,200px)_minmax(0,1fr)_56px] items-center gap-4">
              <span className={clsx("truncate text-[12px]", on ? "font-bold text-ink-deep" : "text-charcoal")}>{r.name}</span>
              <span className="flex min-w-0 items-center gap-2">
                {isBarValue(r.diff) && max > 0 ? (
                  <span className={clsx("block h-2 shrink-0 origin-left rounded-pill motion-safe:animate-grow-x", on ? "bg-primary" : "bg-hairline-soft")} style={{ width: `${(Math.max(0, r.diff) / max) * 82}%`, ["--i" as string]: i }} />
                ) : null}
                <span className={clsx("tnum shrink-0 whitespace-nowrap text-[11px]", on ? "font-bold text-primary-deep" : "text-steel")}>{isBarValue(r.diff) ? r.diffRaw : ZERO_LABEL}</span>
              </span>
              <span className={clsx("tnum text-right text-[12px]", on ? "font-bold text-primary-deep" : "text-steel")}>{r.shareRaw}%</span>
            </li>
          );
        })}
      </ul>
      <p className="tnum mt-4 text-[12px] leading-[1.5] text-slate">
        {unit ? `단위 ${unit} · ` : ""}
        {lead && strong.length > 0 ? `${lead} ${strong.length}개 상품이 전체 증가분의 ${fmtNum(sum, 1)}%를 차지해요.` : null}
      </p>
    </SectionCard>
  );
}

/** 원 숫자(①…) — 관리방안 번호 */
const CIRCLED_ONE = 0x2460;
/** 건전성 카드 막대가 쓰는 폭(나머지는 값 글자 자리) */
const CARD_BAR_ROOM = 0.8;
/** 천 단위 글자 ('184.2천') */
const thousands = (v: number | null | undefined) => (v === null || v === undefined || !Number.isFinite(v) ? NO_VALUE : `${fmtNum(v / 1000, 1)}천`);

/** 건전성 현황 (시안 353:47 · 384) — 옅은 회색 카드 3장: 익스포저(2시점 막대) · 평균 신용등급(소매 vs 포용금융 풀) · 연체율(미제공 점선 카드) */
function Soundness({ report }: { report: ReportDoc }) {
  const f = report.figures;
  const series = chartOf(sectionById(report, SEC.group))?.series ?? [];
  const [baseName, nowName] = [series[0]?.name ?? "", series[1]?.name ?? ""];
  // 기준시점 건수는 화면 자료에 없어 증가율로 역산한다(계산 추적 포함)
  const cntBase = combine({
    id: "inc_exposure_cnt_base",
    label: `포용금융 익스포저 건수(${baseName})`,
    inputs: [f.inc_exposure_cnt_now, f.inc_exposure_cnt_growth],
    calc: ([n, g]) => n / (1 + g / 100),
    expression: "비교시점 건수 ÷ (1 + 증가율 ÷ 100)",
    unit: "CNT",
    decimals: 0,
    asOf: report.asOf,
  });
  const gap = combine({
    id: "inc_grade_gap",
    label: "소매 평균 대비 등급 차",
    inputs: [f.inc_avg_grade, f.retail_avg_grade],
    calc: ([a, b]) => a - b,
    expression: "해당 풀 평균 신용등급 − 소매 전체 평균 신용등급",
    unit: "RATIO",
    decimals: 1,
    asOf: report.asOf,
  });
  const callout = calloutOf(sectionById(report, SEC.exposure));
  const after = callout ? callout.split(/,\s*/).slice(1).join(", ") : "";
  const dlq = f.inc_delinquency;
  const plans = listItems(sectionById(report, SEC.opinion));
  const dlqPlan = plans.findIndex((t) => t.includes("연체"));
  const short = (x?: Figure) => (x ? labelParts(x.label).text.replace(/익스포저\s*/, "").replace(/\s*평균 신용등급$/, "") : "");
  return (
    <SectionCard title="건전성 현황" hint="해당 풀 익스포저 · 신용등급 · 연체율">
      <div className="grid grid-cols-1 items-start gap-3 lg:grid-cols-3">
        <SoundCard label="해당 풀 익스포저">
          <p className="flex items-baseline gap-1">
            {f.inc_exposure_cnt_now ? <Fig figure={f.inc_exposure_cnt_now} size={22} unitLabel="" /> : <NoValue className="text-[22px]" />}
            {f.inc_exposure_cnt_now?.value != null ? <span className="text-[11px] font-bold text-steel">{UNIT_LABEL[f.inc_exposure_cnt_now.unit]}</span> : null}
            {f.inc_exposure_cnt_growth?.value != null ? (
              <span className="ml-2 inline-flex h-[18px] items-center self-center rounded-pill bg-info-soft px-1.5 text-[10px] font-bold text-primary-deep">{figText(f.inc_exposure_cnt_growth, undefined, true)}</span>
            ) : null}
          </p>
          <CardBars
            rows={[
              { key: "base", label: baseName, value: cntBase?.value ?? null, text: thousands(cntBase?.value) },
              { key: "now", label: nowName, value: f.inc_exposure_cnt_now?.value ?? null, text: thousands(f.inc_exposure_cnt_now?.value), strong: true },
            ]}
          />
          <p className="tnum mt-3 text-[10px] leading-[1.4] text-steel">
            규모 {figText(f.inc_exposure_amt_now)}
            {cntBase ? ` · ${baseName} 건수는 증가율로 역산한 값` : ""}
          </p>
        </SoundCard>
        <SoundCard label="평균 신용등급" right="클수록 위험">
          <p className="flex items-baseline gap-1">
            {f.inc_avg_grade ? <Fig figure={f.inc_avg_grade} size={22} unitLabel="" /> : <NoValue className="text-[22px]" />}
            {f.inc_avg_grade?.value != null ? <span className="text-[11px] font-bold text-steel">등급</span> : null}
          </p>
          <CardBars
            rows={[
              { key: "retail", label: short(f.retail_avg_grade), value: f.retail_avg_grade?.value ?? null, text: figText(f.retail_avg_grade, "") },
              { key: "inc", label: short(f.inc_avg_grade), value: f.inc_avg_grade?.value ?? null, text: figText(f.inc_avg_grade, ""), strong: true },
            ]}
          />
          <p className="tnum mt-3 text-[10px] leading-[1.4] text-steel">{gap?.value != null ? `소매 평균보다 ${fmtNum(Math.abs(gap.value), 1)}등급 ${gap.value > 0 ? "낮아요" : gap.value < 0 ? "높아요" : "같아요"}` : NO_VALUE}</p>
        </SoundCard>
        <div className="min-w-0 rounded-lg border border-dashed border-hairline bg-canvas px-4 py-3.5">
          <p className="text-[11px] font-medium leading-[1.4] text-steel">{dlq?.label ?? "연체율"}</p>
          <p className="mt-1 flex items-center gap-2">
            {dlq?.value != null ? <Fig figure={dlq} size={22} /> : <NoValue className="text-[22px]" />}
            {dlq && dlq.value == null ? <MiniTag tone="neutral">{formatFigure(dlq)}</MiniTag> : null}
          </p>
          {after ? <RichText text={politeTitle(after, f)} figures={f} className="mt-3 text-[11px] leading-[1.5] text-steel" /> : null}
          {dlqPlan >= 0 ? (
            <p className="mt-3 text-[10px] leading-[1.4] text-steel">
              관리방안 {String.fromCharCode(CIRCLED_ONE + dlqPlan)} · {splitGuideItem(plans[dlqPlan], f).title}
            </p>
          ) : null}
        </div>
      </div>
    </SectionCard>
  );
}
function SoundCard({ label, right, children }: { label: string; right?: string; children: ReactNode }) {
  return (
    <div className="min-w-0 rounded-lg bg-page px-4 py-3.5">
      <div className="flex items-baseline justify-between gap-2">
        <p className="text-[11px] font-medium leading-[1.4] text-steel">{label}</p>
        {right ? <p className="text-[10px] leading-[1.4] text-steel">{right}</p> : null}
      </div>
      <div className="mt-1">{children}</div>
    </div>
  );
}
/** 카드 안 두 줄 막대 — 이름 · 막대(오른쪽만 둥글게) · 값. 값이 없거나 0 이면 막대 없이 '0' */
function CardBars({ rows }: { rows: { key: string; label: string; value: number | null; text: string; strong?: boolean }[] }) {
  const max = Math.max(0, ...rows.map((r) => r.value ?? 0));
  return (
    <ul className="mt-3 flex flex-col gap-1.5">
      {rows.map((r, i) => {
        const has = isBarValue(r.value);
        return (
          <li key={r.key} className="flex items-center gap-2 text-[10px] leading-[1.4]">
            <span className={clsx("w-[75px] shrink-0 truncate", r.strong ? "font-bold text-primary-deep" : "text-steel")}>{r.label}</span>
            <span className="flex min-w-0 flex-1 items-center gap-1.5">
              {has && max > 0 ? (
                <span className={clsx("block h-2 shrink-0 origin-left rounded-r-pill motion-safe:animate-grow-x", r.strong ? "bg-primary" : "bg-hairline")} style={{ width: `${((r.value as number) / max) * CARD_BAR_ROOM * 100}%`, ["--i" as string]: i }} />
              ) : null}
              <span className={clsx("tnum shrink-0 whitespace-nowrap", r.strong ? "font-bold text-primary-deep" : "text-steel")}>{has ? r.text : ZERO_LABEL}</span>
            </span>
          </li>
        );
      })}
    </ul>
  );
}

/** 관리방안 시점 — 'X 단위' 의 X → 태그 글자 */
const PERIOD_TAG: Record<string, string> = { 월: "매월", 주: "매주", 분기: "매분기", 연: "매년" };
/** 관리방안 한 줄 앞머리의 시점 · 조건 (찾은 부분은 제목에서 뺀다) */
const PLAN_WHEN: { re: RegExp; tag: (m: RegExpExecArray) => string }[] = [
  { re: /^(월|주|분기|연) 단위\s+/, tag: (m) => PERIOD_TAG[m[1]] },
  { re: /^(?:\S+\s+)?(취급 후\s*[\d·,]+개월)(?:\s*경과)?(?:\s*시점의)?\s+/, tag: (m) => m[1] },
  { re: /^.*?(\S+)\s+(초과|미만|이상|이하)\s*시\s+/, tag: (m) => `${m[1]} ${m[2]} 시` },
];
/** 한글이 든 괄호 = 대상 · 기준 메모 ('(Vintage)' 같은 용어 괄호는 제목에 둔다) */
const PLAN_NOTE = /\s*\(([^()]*[가-힣][^()]*)\)/;
/** 메모가 '이름 수치' 이면 기준 — '설정값 +0.5%p' → '+0.5%p (설정값)' */
const NOTE_FIGURE = /^(\S+)\s+([+−-]?\d.*)$/;
interface PlanCard {
  key: string;
  when: string | null;
  title: string;
  noteLabel: string;
  note: string | null;
}
/** 관리방안 한 줄 → 시점 태그 · 제목 · 대상(또는 기준) — 보고서 목록 글자를 나눠 쓴다 */
function splitPlan(text: string, i: number, figures: Record<string, Figure>): PlanCard {
  let t = text.replace(/\s+/g, " ").trim();
  const n = PLAN_NOTE.exec(t);
  const raw = n ? n[1].trim() : null;
  if (n) t = t.replace(n[0], "").replace(/\s+/g, " ").trim();
  let when: string | null = null;
  for (const w of PLAN_WHEN) {
    const m = w.re.exec(t);
    if (m) {
      when = w.tag(m);
      t = t.slice(m[0].length);
      break;
    }
  }
  const fig = raw ? NOTE_FIGURE.exec(raw) : null;
  return { key: String(i), when, title: politeTitle(t, figures), noteLabel: fig ? "기준" : "대상", note: fig ? `${fig[2]} (${fig[1]})` : raw };
}

/** 관리방안 (시안 394:42) — 옅은 회색 카드 3장: 번호 · 시점 태그 · 제목 · 설명 · 대상(기준) + 상위 기준 정합 메모 · 진행사업 보기 */
function Plans({ report }: { report: ReportDoc }) {
  const section = sectionById(report, SEC.opinion);
  const f = report.figures;
  const cards = listItems(section).map((text, i) => splitPlan(text, i, f));
  if (cards.length === 0) return null;
  const align = report.opinions[0]?.verifications.find((v) => v.checkCode === "alignment");
  const standards = report.evidence.filter((e) => e.doc && e.category !== "bank_data").length;
  const note = calloutOf(section);
  return (
    <SectionCard
      title="관리방안"
      hint={align ? `상위 기준${standards ? ` ${standards}건` : ""}과 정합 ${align.passed === false ? "확인 필요" : "확인"}` : null}
      right={
        <Link href={GUIDES_HREF} className={TEXT_LINK}>
          진행사업 보기
          <IconChevron className="h-3 w-3" />
        </Link>
      }
    >
      <ol className="grid grid-cols-1 gap-2.5 md:grid-cols-3">
        {cards.map((c, i) => (
          <li key={c.key} className="flex min-w-0 flex-col rounded-lg bg-page px-4 pb-4 pt-[15px]">
            <div className="flex items-center gap-1.5">
              <span aria-hidden="true" className="tnum flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-circle bg-info-soft text-[10px] font-bold text-primary-deep">
                {i + 1}
              </span>
              <span className="inline-flex h-[18px] items-center whitespace-nowrap rounded-pill bg-track px-[7px] text-[10px] font-bold leading-none text-slate">{c.when ?? NO_VALUE}</span>
            </div>
            <RichText text={c.title} figures={f} className="mt-[11px] text-[13px] font-bold leading-[1.4] text-ink-deep" />
            <p className="mt-[5px] text-[11px] leading-[1.5] text-steel">{NO_VALUE}</p>
            <div className="mt-auto pt-2.5">
              <div className="flex items-baseline gap-2 border-t border-hairline-soft pt-2 text-[11px] font-medium leading-[1.4]">
                <span className="w-8 shrink-0 text-steel">{c.noteLabel}</span>
                <span className={clsx("min-w-0", c.note ? "text-ink-deep" : "text-steel")}>{c.note ?? NO_VALUE}</span>
              </div>
            </div>
          </li>
        ))}
      </ol>
      {note ? (
        <div className="mt-3 flex items-start gap-[5px] text-steel">
          <IconInfo className="mt-[2px] h-2.5 w-2.5 shrink-0" />
          <RichText text={toPoliteText(note)} figures={f} className="text-[11px] leading-[1.4]" />
        </div>
      ) : null}
    </SectionCard>
  );
}
