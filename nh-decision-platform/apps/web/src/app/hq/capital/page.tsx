import { Chart } from "@/components/charts/Chart";
import { FigureText } from "@/components/data/FigureText";
import { EvidenceChips } from "@/components/evidence/EvidenceChips";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge, DataTable, IconWarn, ProgressBar, SectionHead, Td } from "@/components/ui/primitives";
import { formatDate } from "@/lib/format";
import { getCapitalView, getProfitability } from "@/lib/data";

/** 총자산·RWA 제약 + 수익성 트래킹 (요구사항 AST-01 ~ AST-06) */
export default async function CapitalPage() {
  const [capital, profitability] = await Promise.all([getCapitalView(), getProfitability()]);

  return (
    <>
      <PageHeader
        eyebrow="참고"
        title="총자산·수익성 기준"
        description="총자산·RWA 는 목표 산출의 제약, 자산군별 수익성은 최적화 방향입니다. 두 기준을 함께 반영해 자산 목표를 산출합니다."
      />

      <div className="shell flex flex-col gap-xxl">
        {/* ① 상위 제약 */}
        <section>
          <SectionHead title="상위 제약 — 지주 한도 및 내부 배분" hint="출처 문서·페이지까지 추적됩니다" />
          <div className="grid grid-cols-1 gap-2.5 md:grid-cols-3">
            {capital.constraints.map((c) => (
              <div key={c.id} className="panel px-base py-3.5">
                <div className="flex items-baseline justify-between gap-2">
                  <p className="text-[11.5px] text-steel">{c.label}</p>
                  <span className="text-[11px] text-stone">{c.scope}</span>
                </div>
                <p className="mt-1 text-[22px] font-bold leading-none text-ink-deep">
                  <FigureText figure={c.value} strong />
                </p>
                <p className="mt-1.5 text-[11px] text-stone">
                  {c.period} · {c.issuer} · {c.doc.title}
                  {c.doc.page ? ` p.${c.doc.page}` : ""} · {formatDate(c.doc.effectiveDate ?? "")}
                </p>
              </div>
            ))}
          </div>
          <EvidenceChips items={capital.evidence} title="총자산·RWA 제약 근거" className="mt-md" />
        </section>

        {/* 은행 목표 + 한도 검증 */}
        <section>
          <SectionHead title="은행 목표 총자산 증가율" hint="지주 한도를 초과하는 값은 저장이 차단됩니다" />
          <div className="grid grid-cols-1 gap-xl lg:grid-cols-2">
            <div className="soft p-lg">
              <dl className="flex flex-col gap-3">
                <div className="flex items-baseline justify-between">
                  <dt className="text-[12px] text-steel">지주 한도</dt>
                  <dd className="text-[17px] font-bold text-charcoal">
                    <FigureText figure={capital.bankTarget.ceiling} />
                  </dd>
                </div>
                <div className="flex items-baseline justify-between border-t border-hairline-soft pt-3">
                  <dt className="text-[12px] text-steel">은행 설정 목표</dt>
                  <dd className="text-[21px] font-bold text-ink-deep">
                    <FigureText figure={capital.bankTarget.value} strong />
                  </dd>
                </div>
                <div className="flex items-center justify-between border-t border-hairline-soft pt-3">
                  <dt className="text-[12px] text-steel">한도 여유</dt>
                  <dd className="flex items-center gap-2">
                    <FigureText figure={capital.bankTarget.headroom} signed />
                    <Badge tone={capital.bankTarget.passed ? "success" : "critical"}>
                      {capital.bankTarget.passed ? "한도 이내" : "한도 초과"}
                    </Badge>
                  </dd>
                </div>
              </dl>
            </div>

            <div>
              <p className="mb-2.5 text-[12px] font-bold text-charcoal">부서별 신용RWA 한도 소진율</p>
              <div className="flex flex-col gap-3">
                {capital.rwaAllocation.map((row) => (
                  <div key={row.org}>
                    <div className="mb-1 flex items-baseline justify-between text-[12px]">
                      <span className="font-bold text-ink">{row.org}</span>
                      <span className="text-steel">
                        <FigureText figure={row.used} /> / <FigureText figure={row.allocated} />
                      </span>
                    </div>
                    <ProgressBar
                      value={row.usageRate.value ?? 0}
                      tone={
                        (row.usageRate.value ?? 0) > 90
                          ? "critical"
                          : (row.usageRate.value ?? 0) > 75
                            ? "attention"
                            : "primary"
                      }
                      label={`소진율 ${row.usageRate.value}%`}
                    />
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="mt-lg">
            <p className="mb-2 text-[12px] font-bold text-charcoal">자본비율 시산</p>
            <DataTable
              dense
              columns={[
                { key: "label", label: "구분" },
                { key: "value", label: "시산값", align: "right" },
                { key: "floor", label: "기준", align: "right" },
                { key: "note", label: "비고" },
              ]}
            >
              {capital.bisSimulation.map((row) => (
                <tr key={row.label}>
                  <Td strong>{row.label}</Td>
                  <Td align="right">
                    <FigureText figure={row.value} strong />
                  </Td>
                  <Td align="right">
                    <FigureText figure={row.floor} />
                  </Td>
                  <Td>{row.note}</Td>
                </tr>
              ))}
            </DataTable>
          </div>

          {/* 대리지표 한계 (AST-04 / CMP-04) — 문구는 유지하고 표현만 낮춘다 */}
          <p className="mt-base flex items-start gap-2 rounded-xl bg-surface-soft px-base py-3 text-[12px] leading-relaxed text-charcoal">
            <IconWarn className="mt-0.5 shrink-0 text-[#8a5d00]" />
            {capital.proxyNote}
          </p>
        </section>

        {/* ② 수익성 */}
        <section>
          <SectionHead
            title="자산군별 수익성 트래킹"
            hint="3개년 · 규모 대비 수익률 기준 순위 · 제약 범위 내에서 목표 방향에 반영"
          />
          <DataTable
            columns={[
              { key: "rank", label: "순위", align: "center" },
              { key: "asset", label: "자산군" },
              { key: "balance", label: "잔액", align: "right" },
              { key: "revenue", label: "이자수익", align: "right" },
              { key: "ros", label: "규모 대비 수익률", align: "right" },
              { key: "verdict", label: "판정" },
            ]}
          >
            {profitability.map((row) => (
              <tr key={row.assetClass}>
                <Td align="center" strong>
                  {row.rank}
                </Td>
                <Td strong>{row.assetClass}</Td>
                <Td align="right">
                  <FigureText figure={row.balance} />
                </Td>
                <Td align="right">
                  <FigureText figure={row.revenue} />
                </Td>
                <Td align="right">
                  <FigureText figure={row.returnOnScale} strong />
                </Td>
                <Td>{row.verdict}</Td>
              </tr>
            ))}
          </DataTable>

          <div className="mt-lg">
            <Chart
              kind="line"
              title="자산군별 규모 대비 수익률 추이 (3개년)"
              unit="PCT"
              decimals={3}
              series={profitability.slice(0, 4).map((row) => ({ name: row.assetClass, points: row.trend }))}
            />
          </div>
        </section>
      </div>
    </>
  );
}
