"use client";

import clsx from "clsx";
import { useId, useState } from "react";
import { Badge, IconChevron, RowEmpty, SectionHead } from "@/components/ui/primitives";
import { formatDateTime, formatFigure, formatSigned } from "@/lib/format";
import type { ChangeFeed, ChangeItem, Figure } from "@/lib/types";

/** 변화 항목의 표시용 수치 — 원천 성격 정보가 없으므로 unknown (Phase K · HC-05: 꾸며 넣지 않는다) */
const fig = (i: ChangeItem, value: number, unit: Figure["unit"] = i.unit): Figure => ({ id: i.code, label: i.label, value, unit, decimals: i.decimals ?? undefined, dataOrigin: "unknown" });

/** 펼쳐 두는 최근 변화 건수 */
const RECENT_COUNT = 3;

/**
 * 최근 감지된 변화 (B.30) — 변화 감지 에이전트가 직전 확정값 대비 유의 기준(규칙 CHANGE_SIGNIFICANCE)을 넘은 변화만 기록한다.
 * 수치는 커널 계산 결과이며, 데이터 변경은 새로 확정된 파일과 행 수 증감을 보여준다.
 */
export function ChangeFeedPanel({
  feed,
  title = "최근 감지된 변화",
  compact,
  dense,
}: {
  feed: ChangeFeed;
  title?: string;
  /** 1단계 현황 시안 3 — 16px 제목 · 10px 카드 */
  compact?: boolean;
  /** 영업점 현황 시안(326:2) — compact 카드에 14px 제목 · 빈 상태 한 줄(제목 + 설명) */
  dense?: boolean;
}) {
  // 가장 최근 3건만 펼쳐 두고 나머지는 접는다 (감지 시각 내림차순)
  const sorted = [...feed.items].sort((a, b) => (b.at ?? "").localeCompare(a.at ?? ""));
  const recent = sorted.slice(0, RECENT_COUNT);
  const older = sorted.slice(RECENT_COUNT);
  const [open, setOpen] = useState(false);
  const listId = useId();
  const hint = `변화 감지 에이전트 · 직전 확정값 대비${feed.updatedAt ? ` · ${formatDateTime(feed.updatedAt)}` : ""}`;
  const toggle =
    older.length > 0 ? (
      // 펼치기/접기 버튼은 항상 리스트 맨 아래
      <button
        type="button"
        aria-expanded={open}
        aria-controls={listId}
        onClick={() => setOpen((v) => !v)}
        className={clsx(
          "flex w-full items-center justify-center gap-1 border-t px-lg py-2.5 text-[12.5px] font-bold text-steel transition-colors hover:bg-surface-soft hover:text-ink-deep focus-visible:bg-surface-soft focus-visible:outline-none",
          compact ? "rounded-b-[10px] border-track" : "border-hairline-soft",
        )}
      >
        {open ? "이전 변화 접기" : "이전 변화 더 보기"}
        <IconChevron className={clsx("transition-transform", open ? "-rotate-90" : "rotate-90")} />
      </button>
    ) : null;

  // 1단계 현황 카드형 (Figma 321:279) — 제목은 카드 안, 줄은 이름 왼쪽 · 값 · 출처 오른쪽 정렬
  if (compact) {
    return (
      <section aria-label={title} className="rounded-[10px] border border-hairline-soft bg-canvas" data-change-feed>
        <div className={clsx("flex flex-wrap items-baseline gap-y-1 px-6 pb-3", dense ? "gap-x-[7px] pt-[19px]" : "gap-x-3 pt-5")}>
          <h2 className={clsx("font-bold leading-[1.4] text-ink-deep", dense ? "text-[14px]" : "text-[16px]")}>{title}</h2>
          <p className="tnum text-[12px] text-steel">{hint}</p>
        </div>
        {feed.items.length === 0 ? (
          dense ? (
            <p className="mx-6 mb-5 flex flex-wrap items-baseline gap-x-[7px] gap-y-1 border-t border-track pt-3.5">
              <span className="text-[13px] font-medium text-ink-deep">유의 기준을 넘은 변화가 없습니다</span>
              <span className="text-[12px] text-steel">데이터 · 규칙 · 문서가 바뀌어 수치가 유의하게 움직이면 여기에 기록됩니다.</span>
            </p>
          ) : (
            <p className="mx-6 mb-5 border-t border-track pt-4 text-[13px] text-steel">유의 기준을 넘은 변화가 없어요. 데이터 · 규칙 · 문서가 바뀌어 수치가 유의하게 움직이면 여기에 기록됩니다.</p>
          )
        ) : (
          <>
            <ul id={listId} className={clsx("mx-6 border-t border-track", !toggle && "mb-2")}>
              {(open ? sorted : recent).map((i) => compactRow(i, dense))}
            </ul>
            {toggle}
          </>
        )}
      </section>
    );
  }

  return (
    <section aria-label={title}>
      <SectionHead title={title} hint={hint} />
      {feed.items.length === 0 ? (
        <RowEmpty title="유의 기준을 넘은 변화가 없습니다" description="데이터 · 규칙 · 문서가 바뀌어 수치가 유의하게 움직이면 여기에 기록됩니다." />
      ) : (
        <div className="overflow-hidden rounded-xl border border-hairline-soft bg-canvas" data-change-feed>
          <ul id={listId} className="divide-y divide-hairline-soft">{(open ? sorted : recent).map(row)}</ul>
          {toggle}
        </div>
      )}
    </section>
  );
}

/** 카드형 한 줄 — 이름 왼쪽 · 이전 → 이후 · 굵은 증감(%) · 출처 · 시각 오른쪽 */
function compactRow(i: ChangeItem, dense?: boolean) {
  const unit = i.kind === "data" ? "CNT" : i.unit;
  return (
    <li key={i.id} className="flex flex-wrap items-center gap-x-6 gap-y-1 border-b border-track py-2 text-[13px] leading-[19px] last:border-b-0 md:h-9 md:flex-nowrap md:py-0">
      <span className="min-w-0 flex-1 truncate font-medium text-ink-deep" title={i.label}>
        {i.label}
      </span>
      <span className="tnum whitespace-nowrap text-steel">
        {i.kind === "data" ? `${formatFigure(fig(i, i.before, "CNT"))} → ${formatFigure(fig(i, i.after, "CNT"))} 행` : `${formatFigure(fig(i, i.before))} → ${formatFigure(fig(i, i.after))}`}
        <b className="ml-2 font-bold text-ink-deep">
          {formatSigned(fig(i, i.delta, unit))}
          {typeof i.deltaPct === "number" ? ` (${i.deltaPct > 0 ? "+" : ""}${i.deltaPct.toFixed(1)}%)` : ""}
        </b>
      </span>
      <span className={clsx("w-full whitespace-nowrap text-[11px] text-steel md:w-[200px] md:shrink-0 md:truncate md:text-right", dense && "truncate")} title={`${i.workflowName}${i.files?.length ? ` · ${i.files.join(", ")}` : ""}`}>
        {i.workflowName}
        {i.files?.length ? ` · ${i.files.join(", ")}` : ""} · {formatDateTime(i.at)}
      </span>
    </li>
  );
}

/** 한 줄 = 변화 1건 */
function row(i: ChangeItem) {
  return (
            <li key={i.id} className="flex flex-wrap items-center gap-x-md gap-y-1 px-lg py-2.5 text-[13px]">
              <Badge tone={i.level === "major" ? "attention" : "neutral"}>{i.level === "major" ? "주요" : "일반"}</Badge>
              <Badge tone={i.kind === "data" ? "dark" : "info"}>{i.kind === "data" ? "데이터" : "지표"}</Badge>
              <span className="min-w-0 flex-1 font-bold text-ink-deep">{i.label}</span>
              <span className="tnum text-charcoal">
                {i.kind === "data" ? `${formatFigure(fig(i, i.before, "CNT"))} → ${formatFigure(fig(i, i.after, "CNT"))} 행` : `${formatFigure(fig(i, i.before))} → ${formatFigure(fig(i, i.after))}`}
                <span className={i.direction === "down" ? "ml-1.5 text-critical" : "ml-1.5 text-primary"}>
                  ({formatSigned(fig(i, i.delta, i.kind === "data" ? "CNT" : i.unit))}
                  {typeof i.deltaPct === "number" ? ` · ${i.deltaPct > 0 ? "+" : ""}${i.deltaPct.toFixed(1)}%` : ""})
                </span>
              </span>
              <span className="w-full text-[11.5px] text-stone md:w-auto">
                {i.workflowName}
                {i.files?.length ? ` · ${i.files.join(", ")}` : ""} · {formatDateTime(i.at)}
              </span>
            </li>
  );
}
