"use client";

import clsx from "clsx";
import { useState } from "react";
import { FigureText } from "@/components/data/FigureText";
import { MetricStrip } from "@/components/data/MetricStrip";
import { SectionHead, TextLink } from "@/components/ui/primitives";
import { withOffice } from "@/lib/branchOffice";
import { formatFigure } from "@/lib/format";
import type { BranchDashboard } from "@/lib/types";

/**
 * 영업점 사업부문 (시나리오 1화면 (2)) — 종합기획부 현황 화면과 같은 부문 선택 형태, 값은 영업점 기준.
 * 여신 값은 2화면(기업 익스포저) · 3화면(소매 익스포저)과 같은 계산 결과를 쓴다.
 */
export function BranchSegments({ dashboard, office }: { dashboard: BranchDashboard; office?: string | null }) {
  const { segments, loan } = dashboard;
  // 처음 선택 = 상세가 준비된 첫 부문 (Phase K — 부문 코드를 코드에 두지 않는다)
  const firstReady = segments.find((s) => s.status === "active") ?? segments[0];
  const [picked, setSelected] = useState<string | null>(null);
  const selected = picked ?? firstReady?.domainCode ?? "";
  const active = segments.find((s) => s.domainCode === selected);
  const ready = active?.status === "active";
  const worse = (loan.avgGradeGap.value ?? 0) > 0;

  return (
    <section className="flex flex-col gap-lg">
      <div>
        <SectionHead title="사업부문" hint={`${dashboard.office.name} 기준 · 부문을 선택하면 현황이 표시됩니다`} />
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
          {segments.map((s) => {
            const on = s.domainCode === selected;
            return (
              <button
                key={s.domainCode}
                type="button"
                onClick={() => setSelected(s.domainCode)}
                aria-pressed={on}
                className={clsx(
                  "flex h-[76px] flex-col justify-between rounded-xl border px-base py-3 text-left transition-colors",
                  on ? "border-ink-deep bg-ink-deep text-white" : "border-hairline-soft bg-canvas",
                )}
              >
                <span className={clsx("text-[14px] font-bold", on ? "text-white" : "text-ink-deep")}>{s.name}</span>
                <span className={clsx("text-[12px] tnum", on ? "text-white/75" : "text-steel")}>
                  {s.headline ? formatFigure(s.headline) : "준비 중"}
                  {s.note ? <span className={clsx("ml-1", on ? "text-white/60" : "text-stone")}>{s.note}</span> : null}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {ready ? (
        <div>
          <SectionHead title={`${active?.name ?? ""} 부문 현황`} hint={`${dashboard.asOfLabel}`} right={<TextLink href={withOffice("/branch/analysis", office)}>상세 분석</TextLink>} />
          <MetricStrip
            items={[
              { label: "여신 잔액(기업 + 소매)", figure: loan.total },
              { label: "기업여신 대출잔액", figure: loan.corp, caption: `차주 ${formatFigure(loan.corpCount)}` },
              { label: "소매여신 익스포저", figure: loan.retail, caption: `차주 ${formatFigure(loan.retailCount)}` },
              {
                label: "기업여신 평균 신용등급",
                figure: loan.avgGrade,
                caption: `전행 ${formatFigure(loan.bankAvgGrade)} · 값이 클수록 위험`,
                tone: worse ? "attention" : "default",
              },
            ]}
          />
        </div>
      ) : (
        <div className="soft flex flex-col items-center gap-2 px-xl py-section text-center">
          <p className="text-[15px] font-bold text-charcoal">{active?.name} 부문 상세는 준비 중입니다</p>
          {active?.headline ? (
            <p className="text-[13px] text-steel">
              {active.headline.label} <FigureText figure={active.headline} />
            </p>
          ) : null}
          <p className="max-w-[520px] text-[13px] leading-relaxed text-steel">이 부문의 영업점 데이터셋과 지표를 등록하면 같은 구조로 동작합니다.</p>
          {firstReady && firstReady.domainCode !== selected ? (
            <button type="button" onClick={() => setSelected(firstReady.domainCode)} className="mt-2 rounded-pill bg-ink-button px-5 py-2.5 text-[13px] font-bold text-white">
              {firstReady.name} 부문 보기
            </button>
          ) : null}
        </div>
      )}
    </section>
  );
}
