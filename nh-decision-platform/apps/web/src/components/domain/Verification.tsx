"use client";

import { useState } from "react";
import clsx from "clsx";
import { Badge, IconCheck, IconInfo, IconWarn } from "@/components/ui/primitives";
import { ALIGNMENT_LABEL } from "@/lib/format";
import type { AlignmentVerdict, Verification } from "@/lib/types";

const CHECK_LABEL: Record<Verification["checkCode"], string> = {
  numeric_provenance: "수치 출처",
  evidence_present: "근거 존재",
  causality_language: "인과 표현",
  alignment: "상위 기준 정합",
  goal_consistency: "목표 정합성",
};

/** Critic 검증 결과 (요구사항 AGT-06) */
export function VerificationRow({ items }: { items: Verification[] }) {
  const [open, setOpen] = useState(false);
  const allPassed = items.every((i) => i.passed);

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={clsx(
          "inline-flex items-center gap-1.5 rounded-pill px-2.5 py-1 text-[11px] font-bold",
          allPassed ? "bg-[rgba(49,162,76,0.12)] text-success" : "bg-[rgba(228,30,63,0.1)] text-critical",
        )}
        aria-expanded={open}
      >
        {allPassed ? <IconCheck /> : <IconWarn />}
        검증 {items.filter((i) => i.passed).length}/{items.length} 통과
      </button>
      {open ? (
        <div className="absolute left-0 top-[calc(100%+6px)] z-40 w-[320px] rounded-lg border border-hairline-soft bg-canvas p-3 shadow-pop">
          <p className="mb-2 text-[11px] font-bold text-steel">Critic Agent 검증 항목</p>
          <ul className="flex flex-col gap-1.5">
            {items.map((item) => (
              <li key={item.checkCode} className="flex items-start gap-2">
                <span className={clsx("mt-0.5", item.passed ? "text-success" : "text-critical")}>
                  {item.passed ? <IconCheck /> : <IconWarn />}
                </span>
                <span>
                  <span className="block text-[12px] font-bold text-ink">{CHECK_LABEL[item.checkCode]}</span>
                  {item.detail ? <span className="block text-[11px] text-steel">{item.detail}</span> : null}
                </span>
              </li>
            ))}
          </ul>
          <p className="mt-2 border-t border-hairline-soft pt-2 text-[10.5px] text-stone">
            검증 미통과 산출물은 사용자에게 노출되지 않고 재생성됩니다.
          </p>
        </div>
      ) : null}
    </div>
  );
}

/** 배치 검증 결과 (요구사항 PRIN-07 / CRM-07) */
export function AlignmentPanel({
  verdict,
  matched,
  conflicts,
  compact,
}: {
  verdict: AlignmentVerdict;
  matched: string[];
  conflicts: string[];
  compact?: boolean;
}) {
  const tone = verdict === "aligned" ? "success" : verdict === "conflict" ? "critical" : "neutral";

  if (compact) {
    return <Badge tone={tone}>{ALIGNMENT_LABEL[verdict]}</Badge>;
  }

  return (
    <div
      className={clsx(
        "rounded-xl border px-base py-3",
        verdict === "aligned" && "border-[rgba(49,162,76,0.3)] bg-[rgba(49,162,76,0.05)]",
        verdict === "conflict" && "border-[rgba(228,30,63,0.3)] bg-[rgba(228,30,63,0.04)]",
        verdict === "unknown" && "border-hairline bg-surface-soft",
      )}
    >
      <div className="flex items-center gap-2">
        {verdict === "aligned" ? (
          <IconCheck className="text-success" />
        ) : verdict === "conflict" ? (
          <IconWarn className="text-critical" />
        ) : (
          <IconInfo className="text-steel" />
        )}
        <p className="text-[12.5px] font-bold text-ink-deep">
          배치 검증 — {ALIGNMENT_LABEL[verdict]}
        </p>
      </div>
      <p className="mt-1 text-[11.5px] text-steel">
        정부정책 DB · 경영 의사결정 DB · 종합기획부 경영계획과의 방향 충돌 여부를 확인했습니다.
      </p>
      {matched.length > 0 ? (
        <ul className="mt-2 flex flex-col gap-1">
          {matched.map((m) => (
            <li key={m} className="flex items-start gap-1.5 text-[12px] text-charcoal">
              <span className="mt-[3px] text-success">
                <IconCheck />
              </span>
              {m}
            </li>
          ))}
        </ul>
      ) : null}
      {conflicts.length > 0 ? (
        <ul className="mt-2 flex flex-col gap-1">
          {conflicts.map((c) => (
            <li key={c} className="flex items-start gap-1.5 text-[12px] font-bold text-critical">
              <span className="mt-[3px]">
                <IconWarn />
              </span>
              {c}
            </li>
          ))}
        </ul>
      ) : verdict === "unknown" ? (
        <p className="mt-2 text-[12px] text-stone">관련 기준을 찾지 못했습니다. 확정 전 담당자 확인이 필요합니다.</p>
      ) : null}
    </div>
  );
}
