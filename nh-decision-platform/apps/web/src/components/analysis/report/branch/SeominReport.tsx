"use client";
/**
 * 영업점 2단계 · 서민금융 (시안 348:2) — Agent 의견 → 실적 진단 → 적정 유치 규모 → 영업 유의사항 → 근거 · 상세 데이터.
 * 숫자 · 표 · 문장은 모두 보고서(branch_seomin)에서 온다.
 */
import clsx from "clsx";
import { RichText } from "@/components/data/RichText";
import { Cautions } from "@/components/analysis/report/branch/PrimeCorpReport";
import {
  AgentOpinionBox,
  BeforeAfter,
  CHART_TITLE,
  ChartBlock,
  ColumnRule,
  CompareBars,
  DetailAccordion,
  GroupedColumns,
  Legend,
  MiniTag,
  SectionCard,
  StackProgress,
  TwoColumns,
  combine,
  figText,
  ZERO_LABEL,
  fmtNum,
  isBarValue,
  type DetailRowSpec,
} from "@/components/analysis/report/kit";
import { chartOf, findTable, kvOf, labelParts, num, politeTitle, sectionById, stripTrailingParen } from "@/lib/analysisReport";
import { UNIT_LABEL } from "@/lib/format";
import type { Figure, ReportDoc } from "@/lib/types";

/** 보고서 섹션 위치 (보고서 문서의 섹션 id) */
const SEC = { change: "bs-change", portfolio: "bs-portfolio", size: "bs-size", effect: "bs-effect", caution: "bs-caution" } as const;
/** 근거 · 상세 데이터 줄 (시안 383:2) — 신설 기준 항목 · Pool별 표 · 한도별 표 · 기대 효과 항목 */
const DETAIL_ROWS: DetailRowSpec[] = [
  { section: SEC.change },
  { section: SEC.portfolio, title: "caption", kv: false },
  { section: SEC.size, title: "caption", kv: false },
  { section: SEC.effect, notes: false },
];
/** 한도별 비교 표의 열 키 */
const LIMIT_KEYS = ["limit", "basis", "amount", "count", "applied"];
/** 보유 수준 비교 — 지점 · 전행 짝 (보고서 수치 id) */
const LEVEL_PAIRS: [string, string][] = [
  ["br_seomin_share", "bank_seomin_share"],
  ["br_seomin_cnt_share", "bank_seomin_cnt_share"],
  ["br_lowcredit_share", "bank_lowcredit_share"],
];

export function SeominReport({ report, rerun }: { report: ReportDoc; rerun?: string | null }) {
  const f = report.figures;
  const op = report.opinions[0];
  const cntAfter = combine({
    id: "br_seomin_actual_after",
    label: "권고 규모 유치 후 서민금융 신규 건수",
    inputs: [f.br_seomin_actual, f.br_seomin_rec_cnt],
    calc: ([a, b]) => a + b,
    // 평가 기간은 규칙(BRANCH_SCOPE.period_label)에서 — 상반기 · 하반기를 코드에 두지 않는다
    expression: `${f.br_seomin_actual?.label ?? "평가 기간 신규 실적"} + 권고 신규 유치 건수`,
    unit: f.br_seomin_actual?.unit ?? "CNT",
    decimals: 0,
    asOf: report.asOf,
  });
  const basis = f.br_seomin_share ? labelParts(f.br_seomin_share.label).qualifier : null;
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
              key: "score",
              label: "서민금융 득점",
              value: <BeforeAfter before={f.br_seomin_score_now} after={f.br_seomin_score_after} unit="점" />,
              sub: `${figText(f.br_seomin_uplift, "점", true)} · 배점 ${figText(f.br_seomin_points, "점")}`,
            },
            {
              key: "count",
              label: "서민금융 신규 건수",
              value: <BeforeAfter before={f.br_seomin_actual} after={cntAfter} />,
              sub: `${figText(f.br_seomin_rec_cnt, undefined, true)} · 만점 목표 ${figText(f.br_seomin_target)}`,
            },
            {
              key: "share",
              label: "지점 서민금융 비중",
              value: <BeforeAfter before={f.br_seomin_share} after={f.br_seomin_share_after} />,
              sub: `전행 평균 ${figText(f.bank_seomin_share)}${basis ? ` · ${basis} 기준` : ""}`,
            },
          ]}
        />
      ) : null}
      <Diagnosis report={report} />
      <RightSize report={report} cntAfter={cntAfter} />
      <Cautions report={report} sectionId={SEC.caution} />
      <DetailAccordion report={report} rows={DETAIL_ROWS} />
    </>
  );
}

/** 실적 진단 — 상품군별 금액 비중 · 서민금융 보유 수준 */
function Diagnosis({ report }: { report: ReportDoc }) {
  const f = report.figures;
  const op = report.opinions[0];
  const chart = chartOf(sectionById(report, SEC.portfolio));
  const [ours, bank] = chart?.series ?? [];
  if (!chart || !ours) return null;
  const names = chart.series.map((s) => s.name);
  const cats = ours.points.map((p) => p.label);
  // 강조 상품군 = 의견 제목에 나온 상품군 (여럿이면 가장 긴 이름)
  const hit = cats.filter((c) => op?.title.includes(c)).sort((a, b) => b.length - a.length)[0];
  const focus = hit ? cats.indexOf(hit) : -1;
  const bankAt = (i: number) => bank?.points[i]?.value ?? null;
  // 지점이 전행보다 가장 높은 상품군 (해설 문장)
  const diffs = cats.map((c, i) => (ours.points[i].value ?? 0) - (bankAt(i) ?? 0));
  const lead = diffs.length ? cats[diffs.indexOf(Math.max(...diffs))] : null;
  const pool = findTable(report, ["pool", "seomin"]);
  const poolName = f.br_seomin_amt ? (/\(([^()]+)\)/.exec(f.br_seomin_amt.label)?.[1] ?? null) : null;
  const recognized = pool?.rows.filter((r) => String(r.seomin) === "인정").map((r) => String(r.name)) ?? [];
  const pairs = LEVEL_PAIRS.map(([a, b]) => ({ ours: f[a], bank: f[b] })).filter((p): p is { ours: Figure; bank: Figure } => Boolean(p.ours && p.bank));
  const allLower = pairs.length > 0 && pairs.every((p) => (p.ours.value ?? 0) < (p.bank.value ?? 0));
  const rowName = (label: string) => {
    const name = label.replace(/^지점\s*/, "");
    const parts = labelParts(name);
    return hit && parts.text.startsWith(`${hit} `) && parts.qualifier ? `${parts.qualifier} ${parts.text.slice(hit.length + 1)}` : parts.text;
  };
  return (
    <SectionCard title="실적 진단" hint={`${names.join(" vs ")} · 소매여신 Pool 기준`}>
      <TwoColumns>
        <ChartBlock
          title={chart.title.split(" — ")[0]}
          right={
            <Legend
              items={[
                { label: names[0], swatch: "bg-info-line" },
                ...(names[1] ? [{ label: names[1], swatch: "bg-hairline-soft" }] : []),
              ]}
            />
          }
          caption={
            lead && focus >= 0 ? `${lead} 비중이 ${names[1] ?? ""}보다 높고, ${cats[focus]}은 ${fmtNum(ours.points[focus].value, 1)}%(${names[1] ?? ""} ${fmtNum(bankAt(focus), 1)}%)예요.` : null
          }
        >
          <GroupedColumns
            ariaLabel={chart.title}
            categories={cats}
            highlight={focus >= 0 ? focus : null}
            tickUnit="%"
            series={[
              { name: names[0], values: ours.points.map((p) => p.value), tone: "bg-info-line", strongTone: "bg-primary" },
              ...(bank ? [{ name: names[1], values: bank.points.map((p) => p.value), tone: "bg-hairline-soft" }] : []),
            ]}
          />
        </ChartBlock>
        <ColumnRule />
        <ChartBlock
          title={hit ? `${hit} 보유 수준` : "보유 수준"}
          right={poolName ? `${poolName}${recognized.length ? ` (${recognized.join(" · ")})` : ""} 기준` : null}
          caption={
            <RichText
              as="span"
              figures={f}
              text={`${allLower ? `${pairs.map((p) => rowName(p.ours.label)).join(" · ")} 모두 ${names[1] ?? ""}보다 낮아요. ` : ""}현재 ${hit ?? ""} Pool은 [[fig:br_seomin_cnt]] · [[fig:br_seomin_amt]] 규모예요.`}
            />
          }
        >
          <ul className="flex flex-col gap-5 pt-2">
            {pairs.map((p, i) => (
              <li key={p.ours.id} className="grid grid-cols-[120px_minmax(0,1fr)] items-center gap-3">
                <span className="text-[12px] font-medium text-ink-deep">{rowName(p.ours.label)}</span>
                <CompareBars
                  hideLabels
                  i0={i * 2}
                  rows={[
                    { key: "ours", label: names[0], value: p.ours.value, text: figText(p.ours), strong: i === 0, tone: "bg-info-line" },
                    { key: "bank", label: names[1] ?? "", value: p.bank.value, text: figText(p.bank) },
                  ]}
                />
              </li>
            ))}
          </ul>
        </ChartBlock>
      </TwoColumns>
    </SectionCard>
  );
}

/** 적정 유치 규모 — 신규 건수 진행 + 한도별 최대 유치 가능 규모 + 산정 가정 */
function RightSize({ report, cntAfter }: { report: ReportDoc; cntAfter: Figure | null }) {
  const f = report.figures;
  const section = sectionById(report, SEC.size);
  const t = findTable(report, LIMIT_KEYS);
  if (!section || !t) return null;
  const intro = section.blocks.find((b) => b.type === "p")?.text ?? "";
  const hint = intro ? politeTitle(intro.split(/(?<=다\.)\s+/)[0] ?? "") : null;
  const summary = t.highlightRowKey ? t.rows.find((r) => String(r[t.highlightRowKey!]) === String(t.highlightRowValue)) : undefined;
  const candidates = t.rows.filter((r) => r !== summary);
  const recAmount = num(summary?.amount ?? null);
  const maxAmount = Math.max(0, ...candidates.map((r) => num(r.amount ?? null) ?? 0));
  const amountUnit = labelParts(t.columns.find((c) => c.key === "amount")?.label ?? "").unit ?? "";
  const countUnit = f.br_seomin_rec_cnt ? UNIT_LABEL[f.br_seomin_rec_cnt.unit] : "";
  const chips: { key: string; text: string }[] = [
    ...(f.br_seomin_ticket ? [{ key: f.br_seomin_ticket.id, text: `${stripTrailingParen(f.br_seomin_ticket.label).replace(/^권고 산정\s*/, "")} [[fig:${f.br_seomin_ticket.id}]]` }] : []),
    ...kvOf(section).map((kv) => ({ key: kv.label, text: `${stripTrailingParen(kv.label)} ${kv.value.replace(/\s*\(시뮬레이션 가정\)\s*$/, "")}` })),
  ];
  return (
    <SectionCard title="적정 유치 규모" hint={hint}>
      <div className="flex flex-wrap items-baseline justify-between gap-2 text-[12px]">
        <span className="text-steel">서민금융 신규 건수</span>
        <span className="tnum text-steel">
          {figText(f.br_seomin_actual, "")} → <b className="font-bold text-primary-deep">{figText(cntAfter)}</b>
          <span className="mx-1.5">·</span>득점 {figText(f.br_seomin_score_now, "")} → <b className="font-bold text-primary-deep">{figText(f.br_seomin_score_after, "점")}</b>
        </span>
      </div>
      <div className="mt-2">
        <StackProgress
          now={f.br_seomin_actual?.value ?? null}
          add={f.br_seomin_rec_cnt?.value ?? null}
          max={f.br_seomin_target?.value ?? null}
          leftLabel={`현재 ${figText(f.br_seomin_actual)}`}
          addLabel={`권고 ${figText(f.br_seomin_rec_cnt, undefined, true)}`}
          rightLabel={`만점 ${figText(f.br_seomin_target)}`}
        />
      </div>
      <h3 className={clsx("mt-7", CHART_TITLE)}>한도별 최대 유치 가능 규모</h3>
      <ul className="mt-3 flex flex-col gap-1">
        {candidates.map((r, i) => {
          const amount = num(r.amount ?? null);
          const rec = recAmount !== null && amount === recAmount;
          const w = maxAmount > 0 && amount !== null ? (amount / maxAmount) * 100 : 0;
          return (
            <li key={String(r.limit ?? i)} className={clsx("grid grid-cols-1 items-center gap-x-4 gap-y-1.5 rounded-lg px-3 py-2.5 md:grid-cols-[minmax(0,320px)_minmax(0,1fr)]", rec && "bg-info-faint")}>
              <div className="min-w-0">
                <p className="flex flex-wrap items-center gap-2">
                  <span className={clsx("text-[14px] leading-[1.4]", rec ? "font-bold text-primary-deep" : "font-medium text-ink-deep")}>{String(r.limit ?? "")}</span>
                  {rec && summary ? <MiniTag tone="info" className="h-4 px-1.5 text-[10px] text-primary-deep">{`${summary.limit} · ${summary.basis}`}</MiniTag> : null}
                </p>
                <p className="mt-0.5 text-[12px] leading-[1.4] text-steel">{String(r.basis ?? "")}</p>
              </div>
              <div className="flex min-w-0 items-center gap-2">
                <span className="relative h-2 min-w-0 flex-1">
                  {isBarValue(amount) ? <span className={clsx("absolute inset-y-0 left-0 origin-left rounded-pill motion-safe:animate-grow-x", rec ? "bg-primary" : "bg-hairline-soft")} style={{ width: `${w * 0.8}%`, ["--i" as string]: i }} /> : null}
                </span>
                <span className={clsx("tnum w-[132px] shrink-0 whitespace-nowrap text-[12px]", rec ? "font-bold text-primary-deep" : "text-steel")}>
                  {isBarValue(amount) ? `${r.amount ?? ""}${amountUnit} · ${r.count ?? ""}${countUnit}` : ZERO_LABEL}
                </span>
              </div>
            </li>
          );
        })}
      </ul>
      {chips.length > 0 ? (
        <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-hairline-soft pt-4">
          <span className="mr-2 text-[12px] text-steel">산정 가정</span>
          {chips.map((c) => (
            <RichText key={c.key} as="span" figures={f} text={c.text} className="inline-block rounded-pill border border-hairline-soft px-2.5 py-[3px] text-[11px] leading-[1.4] text-slate" />
          ))}
        </div>
      ) : null}
    </SectionCard>
  );
}
