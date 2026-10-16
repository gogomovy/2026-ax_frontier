"use client";

import { useState } from "react";
import { FigureText } from "@/components/data/FigureText";
import { RichText } from "@/components/data/RichText";
import { TermText } from "@/components/data/TermText";
import { Badge, PillTabs, SEVERITY_TONE, SectionHead } from "@/components/ui/primitives";
import { formatDate } from "@/lib/format";
import type { Figure, ModelSummaryRow } from "@/lib/types";
import { ScrollRegion } from "@/components/ui/ScrollRegion";
/** 판정 근거 문구의 [[fig:ID]] 마커 → 같은 행의 계산 수치 */
function rowFigures(row: ModelSummaryRow): Record<string, Figure> {
  const out: Record<string, Figure> = {};
  for (const f of [row.psi, row.ar, row.arDecline, row.ks, row.auroc]) if (f) out[f.id] = f;
  return out;
}

/**
 * 모형 모니터링 지표 (요구사항 CRM-01/02, MDL-02/03/10)
 * 1화면 하단 참고 정보 — 모형군을 탭으로 나눠 한 번에 하나의 표만 보여준다.
 */
export function ModelMonitoringPanel({ corp, retail, asOf }: { corp: ModelSummaryRow[]; retail: ModelSummaryRow[]; asOf?: string | null }) {
  const [tab, setTab] = useState<"corp" | "retail">("corp");
  const rows = tab === "corp" ? corp : retail;
  const showPsi = tab === "corp";

  return (
    <section>
      <SectionHead
        title="모형 모니터링 지표"
        hint={`${tab === "corp" ? "일반기업 규모별 모형 · 안정성·변별력·등급계량화" : "소매여신모형 · 변별력·등급계량화"}${asOf ? ` · 기준 ${formatDate(asOf)}` : ""}`}
        right={
          <PillTabs
            size="sm"
            label="모형군"
            items={[
              { key: "corp" as const, label: "일반기업", count: corp.length },
              { key: "retail" as const, label: "소매", count: retail.length },
            ]}
            value={tab}
            onChange={setTab}
          />
        }
      />
      <ScrollRegion className="overflow-x-auto rounded-2xl border border-hairline-soft">
        <table className="w-full min-w-[760px] border-collapse text-[13px]">
          <thead>
            <tr className="bg-surface-soft text-left">
              <th scope="col" className="px-lg py-2.5 font-bold text-charcoal">모형</th>
              {showPsi ? (
                <th scope="col" className="px-base py-2.5 text-right font-bold text-charcoal">
                  <span className="inline-flex items-center justify-end gap-1">
                    <TermText code="PSI" label="PSI" />
                  </span>
                </th>
              ) : null}
              <th scope="col" className="px-base py-2.5 text-right font-bold text-charcoal">
                <span className="inline-flex items-center justify-end gap-1">
                  <TermText code="AR" label="AR" />
                </span>
              </th>
              <th scope="col" className="px-base py-2.5 text-right font-bold text-charcoal">
                <span className="inline-flex items-center justify-end gap-1">
                  <TermText code="AR_DECLINE" label="AR 하락률" />
                </span>
              </th>
              <th scope="col" className="px-base py-2.5 text-right font-bold text-charcoal">
                <span className="inline-flex items-center justify-end gap-1">
                  <TermText code="KS" label="K-S" />
                </span>
              </th>
              <th scope="col" className="px-base py-2.5 text-right font-bold text-charcoal">
                <span className="inline-flex items-center justify-end gap-1">
                  <TermText code="AUROC" label="AUROC" />
                </span>
              </th>
              <th scope="col" className="px-lg py-2.5 font-bold text-charcoal">판정</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.modelCode} className="border-t border-hairline-soft align-top">
                <td className="px-lg py-3">
                  <p className="font-bold text-ink-deep">{row.name}</p>
                  <p className="mt-0.5 text-[11.5px] text-stone">{row.segment}</p>
                </td>
                {showPsi ? (
                  <td className="px-base py-3 text-right tnum">{row.psi ? <FigureText figure={row.psi} /> : "-"}</td>
                ) : null}
                <td className="px-base py-3 text-right tnum">
                  <FigureText figure={row.ar} />
                </td>
                <td className="px-base py-3 text-right tnum">
                  <FigureText figure={row.arDecline} />
                </td>
                <td className="px-base py-3 text-right tnum">
                  <FigureText figure={row.ks} />
                </td>
                <td className="px-base py-3 text-right tnum">
                  <FigureText figure={row.auroc} />
                </td>
                <td className="max-w-[300px] px-lg py-3">
                  <Badge tone={SEVERITY_TONE[row.verdictSeverity]}>{row.verdict}</Badge>
                  <RichText
                    className="mt-1 text-[11px] leading-snug text-stone"
                    text={row.verdictBasis}
                    figures={rowFigures(row)}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </ScrollRegion>
    </section>
  );
}
