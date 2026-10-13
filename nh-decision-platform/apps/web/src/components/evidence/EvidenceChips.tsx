"use client";

import clsx from "clsx";
import { useUi } from "@/components/providers/UiProvider";
import { IconChevronDown } from "@/components/ui/icons";
import { IconChevron, IconDoc } from "@/components/ui/primitives";
import { EVIDENCE_CATEGORY_LABEL } from "@/lib/format";
import type { Evidence, EvidenceCategory } from "@/lib/types";

const ORDER: EvidenceCategory[] = ["bank_data", "internal_direction", "external_policy"];

/** 색은 의미 있는 값에만 — 근거 범주는 보라 계열 농도와 무채색으로만 구분한다 */
const CATEGORY_DOT: Record<EvidenceCategory, string> = {
  bank_data: "bg-primary",
  internal_direction: "bg-chart-5",
  external_policy: "bg-icon",
};

/**
 * 근거 줄 (가이드 7156) — "근거 [당행 Data 1] [내부 경영방향 1] 외부 정책·환경 없음 · 해설 전문 보기 ⌄ · 원문 확인 ›"
 * 범주 칩을 누르면 그 범주의 첫 근거가 선택된 상태로 서랍이 열리고, 근거가 없는 범주는 글로 "없음"을 알린다.
 */
export function EvidenceRow({
  items,
  title,
  statement,
  expanded,
  onToggleFull,
}: {
  items: Evidence[];
  title: string;
  /** 서랍 위쪽에 인용할 AI 결론 문장 */
  statement?: string;
  expanded?: boolean;
  onToggleFull?: () => void;
}) {
  const { openDrawer } = useUi();
  const open = (selectedId?: string) => openDrawer({ kind: "evidence", title, items, selectedId, statement });
  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-2 text-[12px] text-steel">
      <span className="mr-0.5">근거</span>
      {ORDER.map((c) => {
        const group = items.filter((i) => i.category === c);
        return group.length ? (
          <button
            key={c}
            type="button"
            onClick={() => open(group[0].id)}
            className="inline-flex h-7 items-center gap-1.5 rounded-pill border border-hairline-soft bg-canvas px-3 font-bold text-ink-deep hover:bg-surface-soft"
          >
            <span aria-hidden="true" className={clsx("h-1.5 w-1.5 rounded-circle", CATEGORY_DOT[c])} />
            {EVIDENCE_CATEGORY_LABEL[c]} <span className="tnum">{group.length}</span>
          </button>
        ) : (
          <span key={c} className="px-1">
            {EVIDENCE_CATEGORY_LABEL[c]} 없음
          </span>
        );
      })}
      {onToggleFull ? (
        <button type="button" onClick={onToggleFull} aria-expanded={expanded} className="inline-flex items-center gap-0.5 font-bold text-primary hover:underline">
          해설 전문 보기
          <IconChevronDown className={clsx("transition-transform", expanded && "rotate-180")} />
        </button>
      ) : null}
      <span aria-hidden="true" className="text-icon">
        ·
      </span>
      <button type="button" onClick={() => open()} className="inline-flex items-center gap-0.5 font-bold text-primary hover:underline">
        원문 확인
        <IconChevron />
      </button>
    </div>
  );
}

function countOf(items: Evidence[], category: EvidenceCategory) {
  return items.filter((i) => i.category === category).length;
}

/**
 * 근거 요약 버튼 (요구사항 PRIN-03 / PRIN-10).
 * 목록·본문 안에서는 한 개의 버튼으로 줄이고, 범주별 유무는 점 3개로 보여준다.
 * 비어 있는 범주는 회색 점 + 툴팁/라벨에 `없음`으로 명시한다(공백 금지).
 */
export function EvidenceChips({
  items,
  title,
  className,
}: {
  items: Evidence[];
  title: string;
  className?: string;
}) {
  const { openDrawer } = useUi();
  const summary = ORDER.map((c) => `${EVIDENCE_CATEGORY_LABEL[c]} ${countOf(items, c) || "없음"}`).join(" · ");

  return (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation();
        openDrawer({ kind: "evidence", title, items });
      }}
      title={summary}
      aria-label={`근거 ${items.length}건 보기 — ${summary}`}
      className={clsx(
        "inline-flex h-7 items-center gap-2 rounded-pill border border-hairline-soft bg-canvas px-3 text-[12px] font-bold text-ink-deep hover:bg-surface-soft",
        className,
      )}
    >
      <span className="flex items-center gap-1" aria-hidden="true">
        {ORDER.map((c) => (
          <span
            key={c}
            className={clsx("h-1.5 w-1.5 rounded-circle", countOf(items, c) > 0 ? CATEGORY_DOT[c] : "bg-hairline")}
          />
        ))}
      </span>
      근거 {items.length}건
    </button>
  );
}

/**
 * 근거 3범주 블록 — 상세 시트 등 근거를 자세히 보여줄 자리에서 사용한다.
 */
export function EvidenceSummary({ items, title }: { items: Evidence[]; title: string }) {
  const { openDrawer } = useUi();

  return (
    <ul className="flex flex-col divide-y divide-hairline-soft overflow-hidden rounded-xl border border-hairline-soft">
      {ORDER.map((category) => {
        const group = items.filter((i) => i.category === category);
        const first = group[0];
        return (
          <li key={category}>
            {first ? (
              <button
                type="button"
                onClick={() => openDrawer({ kind: "evidence", title, items, selectedId: first.id })}
                className="flex w-full items-center gap-md px-base py-3 text-left"
              >
                <span className={clsx("h-2 w-2 shrink-0 rounded-circle", CATEGORY_DOT[category])} aria-hidden="true" />
                <span className="w-[92px] shrink-0 text-[12px] font-bold text-charcoal">
                  {EVIDENCE_CATEGORY_LABEL[category]}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[12.5px] font-medium text-ink">{first.label}</span>
                  {group.length > 1 ? (
                    <span className="block text-[11px] text-stone">외 {group.length - 1}건</span>
                  ) : null}
                </span>
                <IconDoc className="shrink-0 text-stone" />
                <IconChevron className="shrink-0 text-stone" />
              </button>
            ) : (
              <div className="flex items-center gap-md px-base py-3">
                <span className="h-2 w-2 shrink-0 rounded-circle bg-hairline" aria-hidden="true" />
                <span className="w-[92px] shrink-0 text-[12px] font-bold text-stone">
                  {EVIDENCE_CATEGORY_LABEL[category]}
                </span>
                <span className="text-[12px] text-stone">해당 범주 근거 없음</span>
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
