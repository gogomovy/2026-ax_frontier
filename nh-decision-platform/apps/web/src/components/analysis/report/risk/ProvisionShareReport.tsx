"use client";
/**
 * 신용리스크관리부 2단계 · 상품별 충당금 비중 (시안 389:2) — Agent 의견 → 충당금 집중도 → 상품별 충당금 규모 → 각주.
 * 숫자는 분석 에이전트 보고서(dynamic)의 커널 값(전체 충당금 · 상품 수 · 1위 비중 · 순위 표)이고,
 * 순위 구간 비중 · 누적 비중은 화면 파생(계산 추적 포함 · lib/provisionShare).
 */
import { useId, useState, type CSSProperties } from "react";
import clsx from "clsx";
import { Fig } from "@/components/domain/overviewKit";
import { AgentOpinionBox, DetailTable, NoValue, SectionCard, TEXT_LINK, ZERO_LABEL } from "@/components/analysis/report/kit";
import { useUi } from "@/components/providers/UiProvider";
import { IconChevron } from "@/components/ui/primitives";
import { UNIT_LABEL } from "@/lib/format";
import { COLUMN_SIZE, HALF_SHARE, MN_PER_EOK, asOfDayDots, eokText, halfDividerAfter, isRuleStatement, joEokParts, joEokText, pct1, provisionModel, provisionOpinion, rankBarWidth, type ProvisionBand, type ProvisionModel, type ProvisionRow } from "@/lib/provisionShare";
import { useRollingNumber } from "@/lib/useRollingNumber";
import type { DataOrigin, Figure, ReportDoc, ReportTableBlock } from "@/lib/types";

/** 순위 막대가 쓰는 폭 — 1위 막대 = 칸의 88% (두 칸 같은 눈금) */
const BAR_ROOM = 0.88;
/** 순위 표 아래 칸 수 — 왼쪽 1–10위 · 오른쪽 11–20위 */
const COLUMNS = 2;
/** 집중도 띠 칸 색 — 1–5위 · 6–10위 · 11–20위 · 나머지 */
const BAND_TONE = ["bg-primary", "bg-info-line", "bg-info-line-soft", "bg-hairline-soft"];
/** 자료 성격 이름표 (각주) */
const ORIGIN_LABEL: Partial<Record<DataOrigin, string>> = { actual: "실데이터", simulated: "시뮬레이션 데이터", mixed: "실데이터 · 시뮬레이션 혼합" };
const order = (i: number) => ({ ["--i" as string]: i }) as CSSProperties;

export function ProvisionShareReport({ report }: { report: ReportDoc }) {
  const model = provisionModel(report);
  if (!model) return null;
  const op = report.opinions[0];
  const composed = op ? provisionOpinion(model, op.severity) : null;
  const top = model.rows[0];
  const origin = ORIGIN_LABEL[report.dataOrigin];
  return (
    <>
      {op && composed ? (
        <AgentOpinionBox
          opinion={isRuleStatement(op) ? { ...op, statement: composed.body } : op}
          headline={composed.headline ?? op.title}
          evidence={report.evidence}
          evidenceTitle={`${report.title} 근거`}
          kpis={[
            {
              key: "total",
              label: model.total.label,
              value: <JoEokFigure figure={model.total} />,
              sub: `소매여신 ${model.n}개 상품 · 손실충당금+충당부채`,
            },
            {
              key: "half",
              label: model.half ? `상위 ${model.half.n}개 상품 비중` : "상위 상품 비중",
              value: model.half ? <PctFigure figure={model.half.share} strong /> : <NoValue className="text-[22px]" />,
              sub: model.half ? `${eokText(model.half.sum)}억원 · 누적 ${HALF_SHARE}%를 넘는 지점` : null,
            },
            {
              key: "top1",
              label: model.top1Share?.label ?? "1위 상품 비중",
              value: model.top1Share ? <PctFigure figure={model.top1Share} /> : <NoValue className="text-[22px]" />,
              sub: top ? `${top.name} · ${eokText(model.top1?.value ?? top.value)}억원` : null,
            },
          ]}
        />
      ) : null}
      <Concentration model={model} />
      <Ranking model={model} />
      <p className="tnum text-right text-[11px] leading-[1.4] text-steel">
        데이터 기준 {asOfDayDots(report.asOf)} · 손실충당금 및 충당부채 합계 · 단위 억원(백만원 ÷ {MN_PER_EOK}){origin ? ` · ${origin}` : ""}
      </p>
    </>
  );
}

/** 백만원 수치 → '3조 4,122 억원' 22px — 누르면 계산 추적 (숫자는 롤링) */
function JoEokFigure({ figure }: { figure: Figure }) {
  const { openDrawer } = useUi();
  const v = figure.value as number;
  const rolling = useRollingNumber(v, 0);
  const shown = joEokParts(rolling ?? v);
  return (
    <button
      type="button"
      onClick={() => openDrawer({ kind: "calc", title: figure.label, figure })}
      aria-label={`${figure.label} ${joEokText(v)} — 계산 추적 보기`}
      className="tnum inline-flex w-fit items-baseline gap-1 text-left font-bold leading-[1.15] decoration-icon decoration-dotted decoration-1 underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
    >
      <span aria-hidden="true" className="text-[22px] text-ink-deep">
        {shown.value}
      </span>
      <span aria-hidden="true" className="text-[12px] text-steel">
        {joEokParts(v).unit}
      </span>
    </button>
  );
}
/** 비중 22px + '%' — 강조면 값 · 단위 모두 primary/700 */
function PctFigure({ figure, strong }: { figure: Figure; strong?: boolean }) {
  return (
    <span className="inline-flex items-baseline gap-1">
      <Fig figure={figure} size={22} valueClass={strong ? "text-primary-deep" : "text-ink-deep"} unitLabel="" />
      {figure.value != null ? <span className={clsx("text-[12px] font-bold", strong ? "text-primary-deep" : "text-steel")}>{UNIT_LABEL[figure.unit]}</span> : null}
    </span>
  );
}

/** 충당금 집중도 — 순위 구간 비중 띠(오른쪽 끝만 둥글게) · 구간 이름 · 비중 · 금액 · 누적 */
function Concentration({ model }: { model: ProvisionModel }) {
  const bands = model.bands.filter((b) => b.share.value != null && b.share.value > 0);
  if (bands.length === 0) return null;
  const grow = (b: ProvisionBand) => ({ flexGrow: b.share.value as number, flexBasis: 0 });
  const summary = bands.map((b) => `${b.label} ${pct1(b.share.value)}% · ${eokText(b.sum)}억원`).join(", ");
  return (
    <SectionCard titleSize={16} title="충당금 집중도" hint={`순위 구간별 누적 비중 · 전체 ${joEokText(model.total.value)}`}>
      <div role="img" aria-label={`순위 구간별 충당금 비중 — ${summary}`} className="mt-2 flex h-3.5 gap-[2px]">
        {bands.map((b, i) => (
          <span
            key={b.key}
            className={clsx("block h-full min-w-[2px] origin-left motion-safe:animate-grow-x", BAND_TONE[i] ?? BAND_TONE[BAND_TONE.length - 1], i === bands.length - 1 && "rounded-r-pill")}
            style={{ ...grow(b), ...order(i) }}
          />
        ))}
      </div>
      <div className="mt-2 grid grid-cols-2 gap-y-3 sm:flex sm:gap-[2px]">
        {bands.map((b, i) => (
          <div key={b.key} className="relative min-w-0 pl-[7px]" style={grow(b)}>
            <span aria-hidden="true" className="absolute left-0 top-[1px] h-2.5 w-px bg-chart-axis" />
            <p className="truncate text-[11px] font-medium leading-[1.4] text-steel">{b.label}</p>
            <p className="mt-0.5 flex items-baseline gap-[5px] whitespace-nowrap">
              <span className="inline-flex items-baseline">
                <Fig figure={b.share} size={15} valueClass={i === 0 ? "text-primary-deep" : "text-ink-deep"} unitLabel="" />
                <span className={clsx("text-[15px] font-bold leading-[1.15]", i === 0 ? "text-primary-deep" : "text-ink-deep")}>%</span>
              </span>
              <span className="tnum text-[11px] text-steel">{eokText(b.sum)}억원</span>
            </p>
          </div>
        ))}
      </div>
      {model.cumulative.length > 0 ? (
        <p className="tnum mt-[18px] whitespace-pre-wrap text-[11px] leading-[1.4] text-slate">
          {`누적  ${model.cumulative.map((c) => `상위 ${c.n}개 ${pct1(c.share)}%`).join("  ·  ")}`}
        </p>
      ) : null}
    </SectionCard>
  );
}

/** 상품별 충당금 규모 — 상위 20개를 두 칸(1–10 · 11–20)으로 · 1위만 강조 · 전체 표 펼침 */
function Ranking({ model }: { model: ProvisionModel }) {
  const [open, setOpen] = useState(false);
  const panel = useId();
  const shownN = Math.min(COLUMN_SIZE * COLUMNS, model.rows.length);
  const shown = model.rows.slice(0, shownN);
  if (shown.length === 0) return null;
  const max = shown[0].value;
  const cols = Array.from({ length: COLUMNS }, (_, c) => shown.slice(c * COLUMN_SIZE, (c + 1) * COLUMN_SIZE)).filter((c) => c.length > 0);
  const rest = model.bands.find((b) => b.key === "rest");
  const table: ReportTableBlock = {
    caption: `상품별 충당금 전체 ${model.rows.length}개`,
    columns: [
      { key: "rank", label: "순위", align: "right" },
      { key: "name", label: "상품명" },
      { key: "eok", label: "충당금(억원)", align: "right" },
      { key: "share", label: "비중(%)", align: "right" },
      { key: "cum", label: "누적 비중(%)", align: "right" },
    ],
    rows: model.rows.map((r) => ({ rank: r.rank, name: r.name, eok: eokText(r.value), share: pct1(r.share), cum: pct1(r.cum) })),
  };
  return (
    <SectionCard
      titleSize={16}
      title="상품별 충당금 규모"
      hint={`상위 ${shownN}개 · 전체 ${model.n}개 상품`}
      right={
        <button type="button" aria-expanded={open} aria-controls={panel} className={clsx(TEXT_LINK, "no-print")} onClick={() => setOpen((v) => !v)}>
          {open ? "표 접기" : `전체 ${model.rows.length}개 표로 보기`}
          <IconChevron className={clsx("h-3 w-3 transition-transform", open && "rotate-90")} />
        </button>
      }
    >
      <div className="grid grid-cols-1 gap-y-6 lg:grid-cols-2 lg:gap-x-10">
        {cols.map((rows, c) => (
          <RankColumn key={c} rows={rows} max={max} lead={c === 0} flip={c > 0} half={model.half?.n ?? null} i0={c * COLUMN_SIZE} />
        ))}
      </div>
      <div className="mt-3 flex flex-wrap items-baseline justify-between gap-2 border-t border-track pt-2.5">
        {rest ? (
          <p className="tnum flex items-baseline gap-2">
            <span className="text-[12px] font-medium text-steel">나머지 {rest.to - rest.from + 1}개 상품</span>
            <span className="text-[11px] text-steel">
              {pct1(rest.share.value)}% · {eokText(rest.sum)}억원
            </span>
          </p>
        ) : (
          <span />
        )}
        <p className="text-[11px] text-steel">막대에 마우스를 올리면 상품명 · 충당금 · 누적 비중이 보여요</p>
      </div>
      <div id={panel} className={clsx("mt-4", open ? "block" : "hidden print:block")}>
        <DetailTable table={table} />
      </div>
    </SectionCard>
  );
}

/** 순위 한 칸 — 머리(구간 · 비중 · 금액) + 10행. 누적 절반을 넘는 순위가 칸 끝이 아니면 그 뒤에 구분선 */
function RankColumn({ rows, max, lead, flip, half, i0 }: { rows: ProvisionRow[]; max: number; lead: boolean; flip: boolean; half: number | null; i0: number }) {
  const [tip, setTip] = useState<number | null>(null);
  const tipId = useId();
  const first = rows[0];
  const last = rows[rows.length - 1];
  const sum = rows.reduce((a, r) => a + r.value, 0);
  const share = rows.reduce((a, r) => a + r.share, 0);
  return (
    <div className="min-w-0">
      <p className="tnum flex items-baseline gap-2">
        <span className={clsx("text-[12px] font-bold", lead ? "text-ink-deep" : "text-steel")}>{lead ? `상위 ${first.rank}–${last.rank}위` : `${first.rank}–${last.rank}위`}</span>
        <span className="text-[11px] text-steel">
          {pct1(share)}% · {eokText(sum)}억원
        </span>
      </p>
      <ul className="mt-2.5 border-t border-track pt-1.5">
        {rows.map((r, i) => {
          const shownTip = tip === r.rank;
          const w = rankBarWidth(r.value, max, BAR_ROOM);
          const has = w !== null;
          const divider = halfDividerAfter(r.rank, half, last.rank);
          return (
            <li key={r.name} className={clsx(divider && "border-b border-dashed border-info-line")}>
              <div
                tabIndex={0}
                data-provision-row={r.rank}
                aria-label={`${r.rank}위 ${r.name} · 충당금 ${eokText(r.value)}억원 · 비중 ${pct1(r.share)}% · 누적 ${pct1(r.cum)}%`}
                aria-describedby={shownTip ? tipId : undefined}
                onMouseEnter={() => setTip(r.rank)}
                onMouseLeave={() => setTip((c) => (c === r.rank ? null : c))}
                onFocus={() => setTip(r.rank)}
                onBlur={() => setTip((c) => (c === r.rank ? null : c))}
                className="grid h-6 grid-cols-[22px_minmax(0,1fr)_minmax(0,0.7fr)_48px_42px] items-center sm:grid-cols-[24px_minmax(0,166px)_minmax(0,1fr)_56px_50px] rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
              >
                <span aria-hidden="true" className={clsx("tnum text-[11px] font-medium", lead ? "text-ink-deep" : "text-steel")}>
                  {r.rank}
                </span>
                <span aria-hidden="true" className={clsx("truncate pr-3 text-[12px] font-medium", lead ? "text-ink-deep" : "text-steel")}>
                  {r.name}
                </span>
                <span className="relative flex h-full items-center">
                  {has ? <span aria-hidden="true" data-provision-bar className={clsx("block h-[7px] origin-left rounded-r-pill motion-safe:animate-grow-x", r.rank === 1 ? "bg-primary" : "bg-info-line")} style={{ width: `${w}%`, ...order(i0 + i) }} /> : null}
                  {shownTip ? <RankTip id={tipId} row={r} flip={flip} /> : null}
                </span>
                <span aria-hidden="true" className="tnum text-right text-[12px] font-medium text-ink-deep">
                  {has ? eokText(r.value) : ZERO_LABEL}
                </span>
                <span aria-hidden="true" className="tnum text-right text-[11px] text-steel">
                  {pct1(r.share)}%
                </span>
              </div>
              {divider ? <span className="sr-only">누적 비중 {HALF_SHARE}%를 넘는 지점</span> : null}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
/** 막대 위 툴팁 — 상품명 · 충당금 · 비중 · 누적 비중 (오른쪽 칸은 왼쪽으로 펼친다) */
function RankTip({ id, row, flip }: { id: string; row: ProvisionRow; flip: boolean }) {
  return (
    <div id={id} role="tooltip" className={clsx("pointer-events-none absolute bottom-[calc(100%+2px)] z-20 w-[200px] rounded-lg border border-hairline-soft bg-canvas px-3 py-2.5 shadow-tooltip", flip ? "right-0" : "left-0")}>
      <p className="truncate text-[12px] font-bold text-ink-deep">
        {row.rank}위 {row.name}
      </p>
      <dl className="tnum mt-1.5 flex flex-col gap-1 text-[11px]">
        <TipLine label="충당금" value={`${eokText(row.value)}억원`} />
        <TipLine label="비중" value={`${pct1(row.share)}%`} />
        <TipLine label="누적 비중" value={`${pct1(row.cum)}%`} />
      </dl>
    </div>
  );
}
function TipLine({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3 whitespace-nowrap">
      <dt className="text-steel">{label}</dt>
      <dd className="font-medium text-ink-deep">{value}</dd>
    </div>
  );
}
