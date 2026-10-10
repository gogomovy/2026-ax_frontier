"use client";

import clsx from "clsx";
import { useUi } from "@/components/providers/UiProvider";
import { IconChevron, IconDoc } from "@/components/ui/primitives";
import { EVIDENCE_CATEGORY_LABEL } from "@/lib/format";
import type { Evidence, EvidenceCategory } from "@/lib/types";

const ORDER: EvidenceCategory[] = ["bank_data", "internal_direction", "external_policy"];

const CATEGORY_DOT: Record<EvidenceCategory, string> = {
  bank_data: "bg-primary",
  internal_direction: "bg-attention",
  external_policy: "bg-success",
};

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
        "inline-flex items-center gap-2 rounded-pill border border-hairline bg-canvas px-3 py-1.5 text-[11.5px] font-bold text-charcoal",
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
