"use client";
/**
 * 분석 에이전트 보고서(kind "dynamic") 본문 — 다른 2단계 분석 결과 화면(시안 kit)과 같은 배치로 그린다.
 * Agent 의견(지표 3칸 · 근거 보기 · 다시 실행) → 절마다 흰 카드(지표 · 해설 · 비교 막대 · 표) → 근거 · 상세 데이터 → 각주.
 * 전용 시안이 있는 분석(상품별 충당금 비중 등)은 그 화면을 쓰고, 그 밖의 분석 에이전트 탭은 모두 이 본문을 쓴다.
 */
import { useId, useState } from "react";
import clsx from "clsx";
import { Chart } from "@/components/charts/Chart";
import { RichText } from "@/components/data/RichText";
import { Fig } from "@/components/domain/overviewKit";
import { Block, StaleNotice } from "@/components/domain/ReportView";
import { IconChevron, SEVERITY_TEXT } from "@/components/ui/primitives";
import { AgentOpinionBox, ChartBlock, CompareBars, DetailAccordion, DetailTable, MiniTag, SectionCard, TEXT_LINK, type DetailRowSpec, type KpiCardItem } from "@/components/analysis/report/kit";
import { barRows, bodySections, isCompareChart, kpiFigureIds, sectionParts, severityTone } from "@/lib/dynamicReport";
import { asOfDayDots } from "@/lib/provisionShare";
import { toPoliteText } from "@/lib/sentence";
import type { DataOrigin, Figure, ReportBlock, ReportDoc, ReportTableBlock } from "@/lib/types";

const ORIGIN_LABEL: Partial<Record<DataOrigin, string>> = { actual: "실데이터", simulated: "시뮬레이션 데이터", mixed: "실데이터 · 시뮬레이션 혼합" };

export function DynamicReport({ report, rerun }: { report: ReportDoc; rerun?: string | null }) {
  const op = report.opinions[0];
  const sections = bodySections(report);
  const kpis: KpiCardItem[] = kpiFigureIds(report).map((id) => ({ key: id, label: report.figures[id].label, value: <Fig figure={report.figures[id]} size={22} /> }));
  // 표는 절 카드 안('표로 보기' · 그래프 없는 표)에서 보이므로, '근거 · 상세 데이터' 는 근거 문서만 (같은 표를 두 번 그리지 않게)
  const detailRows: DetailRowSpec[] = [];
  const origin = ORIGIN_LABEL[report.dataOrigin];
  return (
    <>
      {op ? (
        <AgentOpinionBox opinion={op} headline={op.title} evidence={report.evidence} evidenceTitle={`${report.title} 근거`} rerun={rerun} kpis={kpis} />
      ) : null}
      {report.opinions.length > 1 ? <MoreOpinions report={report} /> : null}
      {sections.map((s) => (
        <DynamicSection key={s.id} id={s.id} heading={s.heading} blocks={s.blocks} report={report} />
      ))}
      {report.evidence.length > 0 ? <DetailAccordion report={report} rows={detailRows} /> : null}
      <div className="flex flex-col items-end gap-1" data-report-footnote>
        <p className="tnum text-right text-[11px] leading-[1.4] text-steel">
          데이터 기준 {asOfDayDots(report.asOf)}
          {origin ? ` · ${origin}` : ""}
          {report.analysisAgent ? ` · 맞춤 분석 v${report.analysisAgent.version}` : ""}
        </p>
        {report.limitations.map((l, i) => (
          <p key={i} className="max-w-[920px] text-right text-[10.5px] leading-[1.5] text-steel">
            {l}
          </p>
        ))}
      </div>
    </>
  );
}

/** 두 번째부터의 의견 — 같은 카드 안에 태그 · 제목 · 해설 */
function MoreOpinions({ report }: { report: ReportDoc }) {
  return (
    <SectionCard titleSize={16} title="함께 볼 의견" hint={`${report.opinions.length - 1}건`}>
      <ul className="grid grid-cols-1 gap-x-8 gap-y-5 md:grid-cols-2">
        {report.opinions.slice(1).map((o) => (
          <li key={o.id} className="min-w-0">
            <p className="flex items-center gap-2">
              <MiniTag tone={severityTone(o.severity)}>{SEVERITY_TEXT[o.severity]}</MiniTag>
              <span className="truncate text-[14px] font-bold leading-[1.4] text-ink-deep">{toPoliteText(o.title)}</span>
            </p>
            <RichText text={toPoliteText(o.statement)} figures={{ ...report.figures, ...o.figures }} className="mt-1.5 text-[12px] leading-[1.6] text-slate" />
          </li>
        ))}
      </ul>
    </SectionCard>
  );
}

/** 절 하나 — 흰 카드: 지표 카드 → 해설 → 그래프(비교 막대) + '표로 보기' → 그래프 없는 표 → 그 밖의 블록 */
function DynamicSection({ id, heading, blocks, report }: { id: string; heading: string; blocks: ReportBlock[]; report: ReportDoc }) {
  const p = sectionParts({ id, heading, level: 2, blocks }, report.figures);
  const [open, setOpen] = useState(false);
  const panel = useId();
  const pairTables = p.chartTables;
  return (
    <SectionCard
      id={id}
      titleSize={16}
      title={heading}
      right={
        pairTables.length > 0 ? (
          <button type="button" aria-expanded={open} aria-controls={panel} className={clsx(TEXT_LINK, "no-print")} onClick={() => setOpen((v) => !v)}>
            {open ? "표 접기" : "표로 보기"}
            <IconChevron className={clsx("h-3 w-3 transition-transform", open && "rotate-90")} />
          </button>
        ) : null
      }
    >
      <div className="flex flex-col gap-5">
        {p.metrics.length > 0 ? <MetricCards ids={p.metrics} figures={report.figures} /> : null}
        {p.texts.map((t, i) => (
          <RichText key={i} text={toPoliteText(t)} figures={report.figures} className="max-w-[1120px] text-[13px] leading-[1.6] text-slate" />
        ))}
        {p.charts.map((c, i) => (
          <div key={i} className="min-w-0">
            {c.stale ? <StaleNotice reason={c.staleReason} what="그래프" /> : null}
            {isCompareChart(c) ? (
              <ChartBlock title={c.title}>
                <CompareBars rows={barRows(c)} labelWidth={140} />
              </ChartBlock>
            ) : (
              // 선 · 여러 계열 · 음수가 있는 그래프는 일반 그래프(제목 · 표로 보기 포함)
              <Chart kind={c.kind === "line" ? "line" : "bar"} title={c.title} series={c.series} unit={c.unit} decimals={c.unit === "KRW_MN" ? 0 : undefined} />
            )}
          </div>
        ))}
        {pairTables.length > 0 ? (
          <div id={panel} className={clsx(open ? "flex" : "hidden print:flex", "flex-col gap-4")}>
            {pairTables.map((t, i) => (
              <TableWithNote key={i} table={t} figures={report.figures} />
            ))}
          </div>
        ) : null}
        {p.tables.map((t, i) => (
          <TableWithNote key={i} table={t} figures={report.figures} />
        ))}
        {p.others.map((b, i) => (
          <Block key={i} block={b} report={report} />
        ))}
      </div>
    </SectionCard>
  );
}

/** 지표 카드 — 의견 상자 지표 카드와 같은 모양(흰 판 대신 옅은 바탕) · 숫자를 누르면 계산 추적 */
function MetricCards({ ids, figures }: { ids: string[]; figures: Record<string, Figure> }) {
  return (
    <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3" data-report-metrics>
      {ids.map((id) => (
        <li key={id} className="flex min-w-0 flex-col rounded-lg bg-page px-4 pb-3.5 pt-3">
          <p className="truncate text-[12px] font-medium leading-[1.4] text-steel">{figures[id].label}</p>
          <div className="mt-1.5">
            <Fig figure={figures[id]} size={22} />
          </div>
        </li>
      ))}
    </ul>
  );
}

function TableWithNote({ table, figures }: { table: ReportTableBlock; figures: Record<string, Figure> }) {
  return (
    <div className="min-w-0">
      {table.stale ? <StaleNotice reason={table.staleReason} what="표" /> : null}
      {table.caption ? <p className="mb-2 text-[11px] font-medium leading-[1.4] text-steel">{table.caption}</p> : null}
      <DetailTable table={table} fill />
      {table.note ? <RichText text={table.note} figures={figures} className="mt-2 text-[10px] leading-[1.5] text-steel" /> : null}
    </div>
  );
}
