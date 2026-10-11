"use client";

import { useState } from "react";
import clsx from "clsx";
import { Chart, PALETTE } from "@/components/charts/Chart";
import { FigureText } from "@/components/data/FigureText";
import { EvidenceChips } from "@/components/evidence/EvidenceChips";
import { PillTabs, SEVERITY_TEXT, SectionHead, StatusDot } from "@/components/ui/primitives";
import type { DefaultRateSeries, DefaultRateTrend } from "@/lib/types";

type View = "corp" | "retail";

/**
 * 월별 부도율 추이 (요구사항 MDL-13)
 *  - 기업: 규모 구분 5종 / 개인: 풀 구분 5종
 *  - 계열 타일을 눌러 차트 표시를 켜고 끈다. 계열 색은 타일과 선이 항상 같다.
 */
export function DefaultRatePanel({ trend }: { trend: DefaultRateTrend }) {
  const [view, setView] = useState<View>("corp");
  const [hidden, setHidden] = useState<string[]>([]);
  const active = view === "corp" ? trend.corpSegments : trend.retailPools;
  const note = view === "corp" ? trend.corpNote : trend.retailNote;

  const colored = active.map((s, i) => ({ series: s, color: PALETTE[i % PALETTE.length] }));
  const shown = colored.filter((c) => !hidden.includes(c.series.key));
  const toggle = (key: string) =>
    setHidden((prev) => (prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]));

  return (
    <section>
      <SectionHead
        title="월별 부도율 추이"
        hint="최근 12개월 · 모형 성능 판단의 선행 지표"
        right={
          <PillTabs
            size="sm"
            label="부도율 구분"
            items={[
              { key: "corp" as const, label: "기업 규모별" },
              { key: "retail" as const, label: "개인 풀별" },
            ]}
            value={view}
            onChange={(v) => {
              setView(v);
              setHidden([]);
            }}
          />
        }
      />

      <div className="rounded-2xl border border-hairline-soft p-lg">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-5">
          {colored.map(({ series, color }) => (
            <SeriesTile
              key={series.key}
              series={series}
              color={color}
              off={hidden.includes(series.key)}
              onClick={() => toggle(series.key)}
            />
          ))}
        </div>

        <div className="mt-lg">
          <Chart
            kind="line"
            title=""
            unit="PCT"
            decimals={3}
            height={260}
            series={shown.map(({ series, color }) => ({ name: series.label, points: series.points, color }))}
            caption={shown.length === 0 ? "표시할 계열을 선택하세요." : undefined}
          />
        </div>

        <div className="mt-md flex flex-wrap items-center justify-between gap-md border-t border-hairline-soft pt-md">
          {note ? <p className="max-w-[720px] text-[11.5px] leading-relaxed text-stone">{note}</p> : <span />}
          <EvidenceChips items={trend.evidence} title="월별 부도율 추이 근거" />
        </div>
      </div>
    </section>
  );
}

function SeriesTile({
  series,
  color,
  off,
  onClick,
}: {
  series: DefaultRateSeries;
  color: string;
  off: boolean;
  onClick: () => void;
}) {
  // 수치는 계산 추적 버튼(FigureText)이므로 타일 전체를 버튼으로 만들지 않고 라벨 행만 토글로 둔다
  return (
    <div
      className={clsx(
        "rounded-xl border px-md py-2.5 transition-opacity",
        off ? "border-dashed border-hairline opacity-50" : "border-hairline-soft",
      )}
    >
      <button
        type="button"
        onClick={onClick}
        aria-pressed={!off}
        title={`차트에서 ${off ? "다시 표시" : "숨기기"}`}
        className="flex w-full items-center gap-1.5 text-left"
      >
        <span className="h-[3px] w-3 shrink-0 rounded-pill" style={{ background: color }} aria-hidden="true" />
        <span className="min-w-0 flex-1 truncate text-[12px] font-bold text-ink-deep">{series.label}</span>{" "}
        <span className="text-[10.5px] font-bold text-stone">{off ? "숨김" : "표시"}</span>
      </button>
      <p className="mt-1.5 text-[18px] font-bold leading-none text-ink-deep">
        <FigureText figure={series.latest} strong />
      </p>
      <p className="mt-1.5 flex items-center gap-1.5 text-[11px] text-stone">
        <StatusDot severity={series.severity} />
        {SEVERITY_TEXT[series.severity]} · <FigureText figure={series.deltaPP} signed />
      </p>
    </div>
  );
}
