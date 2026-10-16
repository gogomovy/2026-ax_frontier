"use client";
/**
 * 영업점 2단계 · 우량기업여신 (시안 346:2) — Agent 의견 → 실적 진단 → 마케팅 후보 기업 → 영업 유의사항 → 근거 · 상세 데이터.
 * 숫자 · 표 · 문장은 모두 보고서(branch_prime_corp)에서 온다.
 */
import { useState } from "react";
import clsx from "clsx";
import { RichText } from "@/components/data/RichText";
import {
  AgentOpinionBox,
  BeforeAfter,
  ChartBlock,
  ChecklistGrid,
  ColumnRule,
  DetailAccordion,
  GroupedColumns,
  Legend,
  MiniTag,
  SectionCard,
  StackProgress,
  TEXT_LINK,
  TwoColumns,
  combine,
  figText,
  ZERO_LABEL,
  isBarValue,
  openDetailRow,
  type DetailRowSpec,
} from "@/components/analysis/report/kit";
import { IconChevronDown } from "@/components/ui/icons";
import { IconChevron } from "@/components/ui/primitives";
import { chartOf, findTable, labelParts, listItems, num, politeTitle, sectionById, shortUnit, splitGuideItem, stripTrailingParen, tableOf } from "@/lib/analysisReport";
import { NO_VALUE } from "@/lib/period";
import type { Figure, ReportDoc, ReportTableBlock } from "@/lib/types";

/** 보고서 섹션 · 표 위치 (보고서 문서의 섹션 id) */
const SEC = { grade: "bp-grade", change: "bp-change", size: "bp-size", cross: "bp-cross", prospect: "bp-prospect", caution: "bp-caution" } as const;
/** 근거 · 상세 데이터 줄 (시안 380:2) — 가중치 표 · 규모별 · 등급별 · 규모 × 등급(두 표 나란히) · 상위 차주 · 후보 명세(후보 전체 명세 › 가 여는 줄) */
const DETAIL_ROWS: DetailRowSpec[] = [
  { section: SEC.change, kv: false, notes: false },
  { section: SEC.size, title: "caption" },
  { section: SEC.grade, title: "caption" },
  { section: SEC.cross, tables: [0, 1] },
  { section: SEC.cross, tables: [2], title: "caption" },
  { section: SEC.prospect, title: "caption" },
];
/** 표 열 키 */
const PROSPECT_KEYS = ["corp", "grade", "weighted"];

export function PrimeCorpReport({ report, rerun }: { report: ReportDoc; rerun?: string | null }) {
  const f = report.figures;
  const op = report.opinions[0];
  const weightedAfter = combine({
    id: "br_prime_actual_after",
    label: "후보 유치 후 등급 가중 실적",
    inputs: [f.br_prime_actual, f.br_prospect_weighted],
    calc: ([a, b]) => a + b,
    expression: "현재 실적(등급 가중) + 후보 유치 시 등급 가중 실적",
    unit: f.br_prime_actual?.unit ?? "KRW_BN",
    decimals: f.br_prime_actual?.decimals,
    asOf: report.asOf,
  });

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
              label: f.br_prime_score_now ? stripTrailingParen(f.br_prime_score_now.label.replace(/\s*현재\s*/, " ")).trim() : "득점",
              value: <BeforeAfter before={f.br_prime_score_now} after={f.br_prime_score_after} unit="점" />,
              sub: `${figText(f.br_prime_uplift, "점", true)}`,
            },
            {
              key: "weighted",
              label: "등급 가중 실적",
              value: <BeforeAfter before={f.br_prime_actual} after={weightedAfter} />,
              sub: `${figText(f.br_prospect_weighted, undefined, true)} · 만점 ${figText(f.br_prime_target)}`,
            },
            {
              key: "grade",
              label: "지점 평균 신용등급",
              value: <BeforeAfter before={f.br_avg_grade} after={f.br_avg_grade_after} unit="단계" />,
              sub: `${figText(f.br_avg_grade_improve, "단계")} 개선 · 클수록 위험`,
            },
          ]}
        />
      ) : null}
      <Diagnosis report={report} />
      <Prospects report={report} weightedAfter={weightedAfter} />
      <Cautions report={report} sectionId={SEC.caution} />
      <DetailAccordion report={report} rows={DETAIL_ROWS} />
    </>
  );
}

/** 실적 진단 — 신용등급 구간별 금액 비중(가중치 알약) · 기업규모별 금액 비중 차이 */
function Diagnosis({ report }: { report: ReportDoc }) {
  const f = report.figures;
  const chart = chartOf(sectionById(report, SEC.grade));
  const weights = tableOf(sectionById(report, SEC.change));
  const sizes = tableOf(sectionById(report, SEC.size));
  const [ours, bank] = chart?.series ?? [];
  if (!chart || !ours) return null;
  const names = chart.series.map((s) => s.name);
  const cats = ours.points.map((p) => p.label);
  const weightOf = (band: string) => weights?.rows.find((r) => String(r.band) === band);
  const up = (band: string) => {
    const r = weightOf(band);
    const a = num(r?.h2 ?? null);
    const b = num(r?.h1 ?? null);
    return a !== null && b !== null ? Math.sign(a - b) : 0;
  };
  // 가중치가 가장 큰 구간의 지점 막대를 진하게
  const weightVals = cats.map((c) => num(weightOf(c)?.h2 ?? null) ?? -Infinity);
  const topBand = weightVals.indexOf(Math.max(...weightVals));
  const bankAt = (i: number) => bank?.points[i]?.value ?? null;
  const thin = cats.filter((c, i) => up(c) > 0 && (ours.points[i].value ?? 0) < (bankAt(i) ?? 0));
  const heavy = cats.filter((c, i) => up(c) < 0 && (ours.points[i].value ?? 0) > (bankAt(i) ?? 0));

  return (
    <SectionCard title="실적 진단" hint={`${names.join(" vs ")} · 기업여신 금액 비중`}>
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
          caption={thin.length && heavy.length ? `가중치가 높은 ${thin.join(" · ")} 구간은 ${names[1] ?? ""}보다 얇고, 가중치가 낮은 ${heavy.join(" · ")} 구간에 실적이 몰려 있어요.` : null}
        >
          <GroupedColumns
            ariaLabel={chart.title}
            categories={cats}
            strong={topBand >= 0 ? topBand : null}
            tickUnit="%"
            series={[
              { name: names[0], values: ours.points.map((p) => p.value), tone: "bg-info-line", strongTone: "bg-primary" },
              ...(bank ? [{ name: names[1], values: bank.points.map((p) => p.value), tone: "bg-hairline-soft" }] : []),
            ]}
            footer={(i) => {
              const r = weightOf(cats[i]);
              if (!r) return null;
              return <MiniTag tone={up(cats[i]) > 0 ? "info" : "neutral"} className={clsx("h-4 px-1.5 text-[10px]", up(cats[i]) > 0 && "text-primary-deep")}>{`가중 ${r.h2}`}</MiniTag>;
            }}
          />
        </ChartBlock>
        <ColumnRule />
        {sizes ? <SizeDiff table={sizes} names={names} figures={f} /> : <span />}
      </TwoColumns>
    </SectionCard>
  );
}

/** 기업규모별 금액 비중 차이 — 0 기준선 양쪽 가로 막대 */
function SizeDiff({ table, names, figures }: { table: ReportTableBlock; names: string[]; figures: Record<string, Figure> }) {
  const rows = table.rows.map((r) => ({ label: String(r.size ?? ""), v: num(r.diffPp ?? null), raw: String(r.diffPp ?? "") })).filter((r) => r.v !== null) as { label: string; v: number; raw: string }[];
  const maxAbs = Math.max(0, ...rows.map((r) => Math.abs(r.v)));
  const top = rows.reduce<(typeof rows)[number] | null>((m, r) => (r.v > 0 && (!m || r.v > m.v) ? r : m), null);
  const focus = table.highlightRowKey === "size" ? String(table.highlightRowValue ?? "") : "";
  const bold = (r: (typeof rows)[number]) => r.v > 0 && (r === top || r.label === focus);
  const boldLabels = rows.filter(bold).map((r) => r.label);
  const pct = (v: number) => (maxAbs > 0 ? (Math.abs(v) / maxAbs) * 100 : 0);
  return (
    <ChartBlock
      title="기업규모별 금액 비중 차이"
      right={`${names[0] ?? ""} − ${names[1] ?? ""} (%p)`}
      caption={
        boldLabels.length ? (
          <RichText as="span" figures={figures} text={`등급이 낮은 ${boldLabels.join(" · ")} 비중이 높아 지점 평균 등급이 [[fig:br_avg_grade]]단계(${names[1] ?? ""} [[fig:bank_avg_grade]])예요.`} />
        ) : null
      }
    >
      <ul className="flex flex-col gap-3 pt-2" aria-label="기업규모별 금액 비중 차이">
        {rows.map((r, i) => (
          <li key={r.label} className="grid grid-cols-[72px_minmax(0,1fr)_minmax(0,1fr)] items-center">
            <span className="text-[12px] font-medium text-ink-deep">{r.label}</span>
            <span className="flex items-center justify-end gap-1.5 border-r border-chart-axis pr-0">
              {r.v < 0 ? (
                <>
                  <span className="tnum text-[11px] text-steel">{r.raw}</span>
                  <span className="h-5 origin-right rounded-l-[3px] bg-hairline-soft motion-safe:animate-grow-x" style={{ width: `${pct(r.v) * 0.85}%`, ["--i" as string]: i }} />
                </>
              ) : null}
            </span>
            <span className="flex items-center gap-1.5">
              {r.v > 0 ? (
                <>
                  <span className={clsx("h-5 origin-left rounded-r-[3px] motion-safe:animate-grow-x", r === top ? "bg-primary" : "bg-info-line")} style={{ width: `${pct(r.v) * 0.85}%`, ["--i" as string]: i }} />
                  <span className={clsx("tnum text-[11px]", bold(r) ? "font-bold text-primary-deep" : "text-steel")}>{r.raw}</span>
                </>
              ) : !isBarValue(r.v) ? (
                <span className="tnum whitespace-nowrap pl-1.5 text-[11px] text-steel">{ZERO_LABEL}</span>
              ) : null}
            </span>
          </li>
        ))}
        <li aria-hidden="true" className="grid grid-cols-[72px_minmax(0,1fr)_minmax(0,1fr)] text-[10px] text-steel">
          <span />
          <span className="pr-2 text-right">{names[1] ?? ""}보다 적음</span>
          <span className="pl-2">{names[1] ?? ""}보다 많음</span>
        </li>
      </ul>
    </ChartBlock>
  );
}

/** 마케팅 후보 기업 — 등급 가중 실적 진행 + 후보 표 + 제외 사유 */
function Prospects({ report, weightedAfter }: { report: ReportDoc; weightedAfter: Figure | null }) {
  const f = report.figures;
  const t = findTable(report, PROSPECT_KEYS);
  const [more, setMore] = useState(false);
  if (!t) return null;
  const [title, hint] = (t.caption ?? "마케팅 후보 기업").split(" — ");
  const col = (k: string) => t.columns.find((c) => c.key === k);
  const unitOf = (k: string) => shortUnit(labelParts(col(k)?.label ?? "").unit);
  const assumed = /가정/.test(col("loan")?.label ?? "");
  const head = (k: string) => {
    const text = labelParts(col(k)?.label ?? k).text;
    return assumed && k === "loan" ? text.replace(/\s*가정$/, "") : text;
  };
  const maxW = Math.max(0, ...t.rows.map((r) => num(r.weighted ?? null) ?? 0));
  const note = t.note ?? "";
  const firstNote = note.split(/(?<=\.)\s+/)[0] ?? "";
  const columns: { key: string; align?: "right" }[] = [
    { key: "rank" },
    { key: "corp" },
    { key: "industry" },
    { key: "model" },
    { key: "grade" },
    { key: "asset" },
    { key: "debt" },
    { key: "sales" },
    { key: "loan" },
    { key: "weight" },
    { key: "weighted", align: "right" as const },
  ].filter((c) => col(c.key));
  return (
    <SectionCard
      id={`card-${SEC.prospect}`}
      title={title}
      hint={hint}
      right={
        <button type="button" className={TEXT_LINK} onClick={() => openDetailRow(SEC.prospect)}>
          후보 전체 명세
          <IconChevron className="h-3 w-3" />
        </button>
      }
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2 text-[12px]">
        <span className="text-steel">등급 가중 실적</span>
        <span className="tnum text-steel">
          {figText(f.br_prime_actual, "")} → <b className="font-bold text-primary-deep">{figText(weightedAfter)}</b>
          <span className="mx-1.5">·</span>득점 {figText(f.br_prime_score_now, "")} → <b className="font-bold text-primary-deep">{figText(f.br_prime_score_after, "점")}</b>
        </span>
      </div>
      <div className="mt-2">
        <StackProgress
          now={f.br_prime_actual?.value ?? null}
          add={f.br_prospect_weighted?.value ?? null}
          max={f.br_prime_target?.value ?? null}
          leftLabel={`현재 ${figText(f.br_prime_actual)}`}
          addLabel={`후보 ${figText(f.br_prospect_cnt, "곳")} 유치 ${figText(f.br_prospect_weighted, undefined, true)}`}
          rightLabel={`만점 ${figText(f.br_prime_target)}`}
        />
      </div>
      <div className="thin-scroll mt-5 overflow-x-auto">
        <table className="w-full min-w-[960px] border-collapse text-[12px]">
          <caption className="sr-only">{t.caption}</caption>
          <thead>
            <tr className="bg-surface-soft">
              {columns.map((c) => (
                <th key={c.key} scope="col" className={clsx("whitespace-nowrap px-2.5 py-2 text-[11px] font-bold text-steel first:rounded-l-md last:rounded-r-md", c.align === "right" ? "text-right" : "text-left")}>
                  {head(c.key)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {t.rows.map((r, i) => {
              const w = num(r.weighted ?? null);
              return (
                <tr key={String(r.corp ?? i)} className="border-b border-hairline-soft">
                  {columns.map((c) => {
                    const v = r[c.key];
                    const cell = (() => {
                      if (v === null || v === undefined || v === "") return NO_VALUE;
                      switch (c.key) {
                        case "rank":
                          return <span className="tnum inline-flex h-5 w-5 items-center justify-center rounded-circle bg-surface-soft text-[10px] font-bold text-steel">{v}</span>;
                        case "corp":
                          return <span className="text-[13px] font-bold text-ink-deep">{v}</span>;
                        case "industry":
                          return <span className="text-steel">{stripTrailingParen(String(v))}</span>;
                        case "grade":
                          return <MiniTag tone="info" className="text-primary-deep">{v}</MiniTag>;
                        case "debt":
                          return `${v}%`;
                        case "asset":
                        case "sales":
                          return `${v}${unitOf(c.key)}`;
                        case "loan":
                          return (
                            <span className="inline-flex items-center gap-1.5">
                              {`${v}${unitOf(c.key)}`}
                              {assumed ? <MiniTag tone="neutral" className="h-4 px-1.5 text-[10px]">가정</MiniTag> : null}
                            </span>
                          );
                        case "weighted":
                          return (
                            <span className="ml-auto flex w-[120px] flex-col items-end gap-1">
                              <b className="tnum whitespace-nowrap text-[13px] font-bold text-primary-deep">{isBarValue(w) ? `+${v}${unitOf(c.key)}` : ZERO_LABEL}</b>
                              {isBarValue(w) && maxW > 0 ? <span className="block h-[3px] origin-right rounded-pill bg-info-line motion-safe:animate-grow-x" style={{ width: `${(w / maxW) * 100}%`, ["--i" as string]: i }} /> : null}
                            </span>
                          );
                        default:
                          return String(v);
                      }
                    })();
                    return (
                      <td key={c.key} className={clsx("tnum whitespace-nowrap px-2.5 py-3 text-charcoal", c.align === "right" && "text-right")}>
                        {cell}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {note ? (
        <div className="mt-3 flex items-start justify-between gap-4 text-[11px] leading-[1.5] text-steel">
          <p className={clsx("min-w-0", more ? "" : "truncate")}>{more ? note : firstNote}</p>
          <button type="button" aria-expanded={more} onClick={() => setMore((v) => !v)} className={clsx(TEXT_LINK, "no-print")}>
            {more ? "제외 사유 접기" : "제외 사유 보기"}
            <IconChevronDown size={12} className={clsx("transition-transform", more && "rotate-180")} />
          </button>
        </div>
      ) : null}
    </SectionCard>
  );
}

/** 영업 유의사항 — 보고서 유의사항 목록을 제목 · 설명으로 나눈 2열 확인 목록 */
export function Cautions({ report, sectionId }: { report: ReportDoc; sectionId: string }) {
  const items = listItems(sectionById(report, sectionId)).map((text, i) => ({ key: String(i), ...splitGuideItem(text, report.figures) }));
  if (items.length === 0) return null;
  return (
    <SectionCard title="영업 유의사항">
      <ChecklistGrid items={items} figures={report.figures} />
    </SectionCard>
  );
}
