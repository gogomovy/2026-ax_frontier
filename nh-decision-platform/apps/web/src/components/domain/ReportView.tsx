"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import clsx from "clsx";
import { OnDemandAnalysis } from "@/components/agent/AgentProgress";
import { Chart } from "@/components/charts/Chart";
import { RichText, renderRich } from "@/components/data/RichText";
import { TermText } from "@/components/data/TermText";
import { EvidenceChips } from "@/components/evidence/EvidenceChips";
import { VerificationRow } from "@/components/domain/Verification";
import { useUi } from "@/components/providers/UiProvider";
import { Button, DataTable, IconArrowUp, IconChevron, IconDownload, SeverityBadge, Td } from "@/components/ui/primitives";
import { api } from "@/lib/api-client";
import { API_MODE } from "@/lib/config";
import { formatDateTime } from "@/lib/format";
import { downloadReport, downloadServerReport, EXPORT_FORMAT_LABEL } from "@/lib/reportExport";
import type { ReportBlock, ReportDoc } from "@/lib/types";

/**
 * 보고서 변환·인쇄 — 화면 머리말 우측에 둔다 (MDL-07 / MDL-14)
 *  - 목업 모드: 브라우저에서 HTML 생성
 *  - API 모드: 서버 변환(F.17) — 관리자 설정 `report.export_formats` 로 켠 형식만 메뉴에 보인다
 */

export function ReportActions({ report, tabKey }: { report: ReportDoc; tabKey?: string }) {
  const { showToast } = useUi();
  const [formats, setFormats] = useState<string[] | null>(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const remote = API_MODE && Boolean(tabKey);
  useEffect(() => {
    if (!remote) return;
    api<string[]>("/reports/formats")
      .then(setFormats)
      .catch(() => setFormats([]));
  }, [remote]);
  /* 메뉴 바깥 클릭 · Esc 로 닫기 */
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey, true);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey, true);
    };
  }, [open]);
  const download = (format: string) => {
    if (!tabKey) return;
    setOpen(false);
    setBusy(true);
    downloadServerReport(tabKey, format)
      .then((fileName) => showToast(`보고서를 내려받았습니다 — ${fileName}`))
      .catch((e: Error) => showToast(`보고서를 내려받지 못했습니다 — ${e.message}`))
      .finally(() => setBusy(false));
  };
  return (
    <>
      {remote && report.workflow ? <OnDemandAnalysis workflow={report.workflow} /> : null}
      <Button variant="ghost" size="sm" onClick={() => window.print()}>
        인쇄
      </Button>
      {remote ? (
        <div ref={menuRef} className="relative" data-report-export>
          <Button size="sm" disabled={busy || !formats || formats.length === 0} onClick={() => setOpen((v) => !v)}>
            <IconDownload />
            {busy ? "변환 중…" : "보고서로 내려받기"}
          </Button>
          {open && formats && formats.length > 0 ? (
            <ul
              aria-label="내려받을 형식"
              className="absolute right-0 z-30 mt-2 min-w-[160px] overflow-hidden rounded-xl border border-hairline bg-canvas py-1 shadow-pop"
            >
              {formats.map((f) => (
                <li key={f}>
                  <button
                    type="button"
                    data-format={f}
                    className="block w-full px-4 py-2 text-left text-[13px] hover:bg-surface-soft focus-visible:bg-surface-soft"
                    onClick={() => download(f)}
                  >
                    {EXPORT_FORMAT_LABEL[f] ?? f.toUpperCase()}
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : (
        <Button
          size="sm"
          onClick={() => {
            const fileName = downloadReport(report);
            showToast(`보고서를 내려받았습니다 — ${fileName}`);
          }}
        >
          <IconDownload />
          보고서로 내려받기
        </Button>
      )}
    </>
  );
}
/**
 * 보고서 뷰 (요구사항 MDL-07 / MDL-08 / MDL-09)
 *  - 좌: 목차(데스크톱 고정) / 본문: Agent 의견 → 섹션
 *  - 의견을 누르면 관련 섹션으로 이동하고 잠시 강조한다. 의견 영역은 스크롤을 따라오지 않는다.
 */
export function ReportView({ report }: { report: ReportDoc }) {
  const [activeSection, setActiveSection] = useState<string | null>(null);
  const [highlighted, setHighlighted] = useState<string | null>(null);
  const [showTop, setShowTop] = useState(false);

  const jumpTo = useCallback((anchor: string) => {
    const el = document.getElementById(anchor);
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "start" });
    setHighlighted(anchor);
    window.setTimeout(() => setHighlighted((cur) => (cur === anchor ? null : cur)), 2600);
  }, []);

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];
        if (visible) setActiveSection(visible.target.id);
      },
      { rootMargin: "-80px 0px -70% 0px", threshold: 0 },
    );
    report.sections.forEach((s) => {
      const el = document.getElementById(s.id);
      if (el) observer.observe(el);
    });
    return () => observer.disconnect();
  }, [report.sections]);

  useEffect(() => {
    const onScroll = () => setShowTop(window.scrollY > 640);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <div className="shell grid grid-cols-1 gap-xxl lg:grid-cols-[200px_minmax(0,1fr)]">
      {/* 목차 */}
      <aside className="no-print lg:sticky lg:top-lg lg:self-start">
        <p className="mb-2 px-2.5 text-[11.5px] font-bold text-stone">목차</p>
        <nav aria-label="보고서 목차" className="flex flex-col gap-0.5">
          {report.toc.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => jumpTo(item.id)}
              aria-current={activeSection === item.id ? "true" : undefined}
              className={clsx(
                "rounded-lg px-2.5 py-1.5 text-left text-[12.5px] transition-colors",
                item.level === 3 && "pl-5 text-[12px]",
                activeSection === item.id ? "bg-surface-soft font-bold text-ink-deep" : "text-steel",
              )}
            >
              {item.label}
            </button>
          ))}
        </nav>
        <p className="mt-lg px-2.5 text-[11px] leading-snug text-stone">{formatDateTime(report.generatedAt)} 생성</p>
      </aside>

      <div className="min-w-0 max-w-[880px]">
        {/* Agent 의견 (MDL-08) */}
        <section aria-label="Agent 의견" className="mb-xxl">
          <p className="mb-2.5 text-[12px] font-bold text-steel">Agent 의견</p>
          <ul className="flex flex-col gap-md">
            {report.opinions.map((opinion) => (
              <li key={opinion.id} className="rounded-2xl bg-surface-soft px-lg py-lg">
                <div className="flex flex-wrap items-center gap-2">
                  <SeverityBadge severity={opinion.severity} />
                  <h2 className="text-[16px] font-bold leading-snug text-ink-deep">{opinion.title}</h2>
                </div>
                <div className="mt-2 text-[14px] leading-[1.7] text-charcoal">
                  {renderRich(opinion.statement, opinion.figures)}
                </div>
                <div className="mt-base flex flex-wrap items-center gap-xs">
                  <EvidenceChips items={opinion.evidence} title={opinion.title} />
                  <VerificationRow items={opinion.verifications} />
                  {opinion.reportAnchor ? (
                    <button
                      type="button"
                      onClick={() => jumpTo(opinion.reportAnchor!)}
                      className="ml-auto inline-flex items-center gap-1 text-[12.5px] font-bold text-primary no-print"
                    >
                      본문에서 보기 <IconChevron />
                    </button>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        </section>

        {/* 본문 */}
        <article className="report-body">
          <header className="mb-lg hidden print:block">
            <h1 className="text-[22px] font-bold leading-tight text-ink-deep">{report.title}</h1>
            <p className="mt-1 text-[13px] text-steel">{report.subtitle}</p>
          </header>

          {report.sections.map((section) => {
            const Tag = section.level === 2 ? "h2" : "h3";
            return (
              <section
                key={section.id}
                id={section.id}
                data-highlight={highlighted === section.id ? "true" : undefined}
                className="scroll-mt-[88px]"
              >
                <Tag>{section.heading}</Tag>
                {section.blocks.map((block, i) => (
                  <Block key={i} block={block} report={report} />
                ))}
              </section>
            );
          })}

          <footer className="mt-xxl flex flex-wrap items-center gap-md border-t border-hairline-soft pt-base">
            <span className="text-[12px] text-steel">보고서 전체 근거</span>
            <EvidenceChips items={report.evidence} title={`${report.title} 근거`} />
          </footer>
        </article>
      </div>

      {showTop ? (
        <button
          type="button"
          onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
          className="fixed bottom-8 right-8 z-30 flex h-11 w-11 items-center justify-center rounded-circle bg-ink-deep text-white shadow-pop no-print"
          aria-label="맨 위로 이동"
        >
          <IconArrowUp />
        </button>
      ) : null}
    </div>
  );
}

function Block({ block, report }: { block: ReportBlock; report: ReportDoc }) {
  switch (block.type) {
    case "p":
      return <RichText text={block.text ?? ""} figures={report.figures} />;

    case "ul":
      return (
        <ul>
          {(block.items ?? []).map((item, i) => (
            <li key={i} className="mb-1 text-[13.5px] leading-relaxed">
              {renderRich(item, report.figures)}
            </li>
          ))}
        </ul>
      );

    case "callout": {
      const tone = block.tone ?? "info";
      return (
        <div
          className={clsx(
            "my-md rounded-xl px-base py-3 text-[13.5px] leading-relaxed text-charcoal",
            tone === "info" && "bg-[rgba(0,100,224,0.05)]",
            tone === "attention" && "bg-[rgba(242,169,24,0.1)]",
            tone === "critical" && "bg-[rgba(228,30,63,0.06)]",
            tone === "success" && "bg-[rgba(49,162,76,0.07)]",
          )}
        >
          {renderRich(block.text ?? "", report.figures)}
        </div>
      );
    }

    case "kv":
      return (
        <dl className="my-md grid grid-cols-1 gap-x-xl gap-y-2 md:grid-cols-2">
          {(block.kv ?? []).map((item) => (
            <div key={item.label} className="flex gap-2 border-b border-hairline-soft pb-1.5">
              <dt className="w-[128px] shrink-0 text-[12px] text-steel">
                {item.term ? <TermText code={item.term} label={item.label} /> : item.label}
              </dt>
              <dd className="text-[12.5px] font-medium text-ink">{renderRich(String(item.value), report.figures)}</dd>
            </div>
          ))}
        </dl>
      );

    case "chart":
      return block.chart ? (
        <div className="my-lg rounded-2xl border border-hairline-soft p-lg">
          <Chart
            kind={block.chart.kind === "line" ? "line" : "bar"}
            title={block.chart.title}
            series={block.chart.series}
            unit={block.chart.unit}
            decimals={block.chart.unit === "KRW_MN" ? 0 : undefined}
          />
        </div>
      ) : null;

    case "table": {
      const t = block.table;
      if (!t) return null;
      return (
        <div className="my-lg">
          <DataTable
            dense
            caption={t.caption}
            columns={t.columns.map((c) => ({
              key: c.key,
              align: c.align,
              label: c.term ? <TermText code={c.term} label={c.label} /> : c.label,
            }))}
          >
            {t.rows.map((row, i) => {
              const highlight = Boolean(
                t.highlightRowKey && String(row[t.highlightRowKey]) === String(t.highlightRowValue),
              );
              return (
                <tr key={i} className={clsx(highlight && "bg-[rgba(242,169,24,0.12)]")}>
                  {t.columns.map((c, ci) => (
                    <Td key={c.key} align={c.align} strong={ci === 0 || highlight}>
                      {row[c.key] ?? "-"}
                    </Td>
                  ))}
                </tr>
              );
            })}
          </DataTable>
          {t.note ? <p className="mt-1.5 text-[11px] text-stone">{renderRich(t.note, report.figures)}</p> : null}
        </div>
      );
    }

    default:
      return null;
  }
}
