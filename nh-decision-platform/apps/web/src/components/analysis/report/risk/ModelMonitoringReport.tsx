"use client";
/**
 * 신용리스크관리부 2단계 · 모형 모니터링 (시안 350:2) — Agent 의견(판정 4단계) → 등급 분포 변화 → 예측 이탈 등급 → 특이사항 · 가이드 → 근거 · 상세 데이터.
 * 숫자 · 표 · 문장은 보고서(model_monitoring)와 현황의 모형 판정 행에서 온다.
 */
import Link from "next/link";
import { Fig, type Tone } from "@/components/domain/overviewKit";
import { RichText } from "@/components/data/RichText";
import { toPoliteText } from "@/lib/sentence";
import { AgentOpinionBox, ChartBlock, ColumnRule, CompareBars, DetailAccordion, Legend, MiniTag, NoValue, SectionCard, TEXT_LINK, TwoColumns, figText, type DetailRowSpec } from "@/components/analysis/report/kit";
import { DivergingColumns, PdRangeChart } from "@/components/analysis/report/risk/riskCharts";
import { IconChevron, SEVERITY_TEXT } from "@/components/ui/primitives";
import { calloutOf, chartOf, kvOf, num, politeTitle, sectionById, severityFromText, tableOf } from "@/lib/analysisReport";
import { NO_VALUE } from "@/lib/period";
import type { ModelSummaryRow, ReportDoc, Severity } from "@/lib/types";

/** 보고서 섹션 위치 (보고서 문서의 섹션 id) */
const SEC = { overview: "s1-overview", psi: "s2-psi", grade: "s3-grade", calibration: "s4-calibration", findings: "s5-findings" } as const;
/** 근거 · 상세 데이터 줄 (시안 381:2) — 개요 항목 · 분포 표 · 등급별 표(6B 실제부도율 · 판정 주의 색) · 등급계량화 3단계 */
const DETAIL_ROWS: DetailRowSpec[] = [
  { section: SEC.overview },
  { section: SEC.psi, title: "caption" },
  { section: SEC.grade, title: "caption", attentionKeys: ["defaultRate", "verdict"] },
  { section: SEC.calibration, kv: "steps" },
];
/** 기여도 그래프에 보일 구간 수 */
const TOP_CONTRIBUTORS = 6;
/** 제안안이 있는 특이사항 심각도 */
const PROPOSAL_SEVERITY: Severity[] = ["caution", "critical"];
/** 수행방안(제안안 · 진행사업) 화면 */
const GUIDES_HREF = "/risk/guides";

/** 판정 글자 → 태그 색 */
function toneOfWord(word: string): Tone {
  const sev = severityFromText(word, SEVERITY_TEXT);
  return sev === "caution" ? "attention" : sev === "critical" ? "critical" : "neutral";
}
/** 모형 종합 판정 → 태그 색 (적정 = 무채색 · 그 밖 = 주의) */
const toneOfVerdict = (s: Severity | undefined): Tone => (s === "critical" ? "critical" : s && s !== "info" ? "attention" : "neutral");
/** 'PSI 0.082(관찰) · AR 하락률 19.4%(하락 주의)' 에서 항목별 판정 글자 (마지막 낱말) */
function basisWord(basis: string | undefined, key: string): string | null {
  const m = new RegExp(`${key}[^()]*\\(([^)]+)\\)`).exec(basis ?? "");
  return m ? (m[1].trim().split(/\s+/).pop() ?? null) : null;
}
const stripSuffix = (name: string) => name.replace(/\s*\([^)]*\)\s*$/, "");

export function ModelMonitoringReport({ report, model, rerun }: { report: ReportDoc; model?: ModelSummaryRow | null; rerun?: string | null }) {
  const f = report.figures;
  const op = report.opinions[0];
  const gradeT = tableOf(sectionById(report, SEC.grade));
  const focus = gradeT?.highlightRowValue != null ? String(gradeT.highlightRowValue) : null;
  const focusRow = focus && gradeT ? gradeT.rows.find((r) => String(r[gradeT.highlightRowKey ?? "grade"]) === focus) : undefined;
  const psiWord = basisWord(model?.verdictBasis, "PSI");
  const arWord = basisWord(model?.verdictBasis, "AR");
  const chiPass = f.chi_stat?.value != null && f.chi_critical?.value != null ? f.chi_stat.value <= f.chi_critical.value : null;
  const baseDate = kvOf(sectionById(report, SEC.overview)).find((k) => k.label.includes("비교 기준"))?.value.split(" ")[0];
  return (
    <>
      {op ? (
        <AgentOpinionBox
          opinion={op}
          headline={politeTitle(op.title, op.figures)}
          evidence={report.evidence}
          evidenceTitle={`${report.title} 근거`}
          rerun={rerun}
          connectors
          kpis={[
            {
              key: "psi",
              label: <b className="font-bold text-ink-deep">안정성</b>,
              qualifier: "PSI",
              tag: psiWord ? <MiniTag tone={toneOfWord(psiWord)}>{psiWord}</MiniTag> : null,
              value: f.psi_micro ? <Fig figure={f.psi_micro} size={22} /> : <NoValue className="text-[22px]" />,
              sub: baseDate ? `비교 기준 ${baseDate}` : null,
            },
            {
              key: "ar",
              label: <b className="font-bold text-ink-deep">변별력</b>,
              qualifier: f.ard_micro?.label ?? "AR 하락률",
              tag: arWord ? <MiniTag tone={toneOfWord(arWord)}>{arWord}</MiniTag> : null,
              value: f.ard_micro ? <Fig figure={f.ard_micro} size={22} /> : <NoValue className="text-[22px]" />,
              sub: `AR ${figText(f.ar_micro)} · K-S ${figText(f.ks_micro)}`,
            },
            {
              key: "chi",
              label: <b className="font-bold text-ink-deep">등급계량화</b>,
              qualifier: "χ² 검정",
              tag: chiPass === null ? null : <MiniTag tone={chiPass ? "neutral" : "attention"}>{chiPass ? "통과" : "기각"}</MiniTag>,
              value: f.chi_stat ? <Fig figure={f.chi_stat} size={22} /> : <NoValue className="text-[22px]" />,
              sub: chiPass === null ? null : `임계값 ${figText(f.chi_critical)} ${chiPass ? "이내" : "초과"}`,
            },
            {
              key: "verdict",
              label: <b className="font-bold text-ink-deep">종합 적정성</b>,
              qualifier: "판정",
              tag: model ? <MiniTag tone={toneOfVerdict(model.verdictSeverity)}>{model.verdict}</MiniTag> : null,
              value: model ? <span className={toneOfVerdict(model.verdictSeverity) === "attention" ? "text-[22px] font-bold leading-[1.15] text-attention" : "text-[22px] font-bold leading-[1.15] text-ink-deep"}>{model.verdict}</span> : <NoValue className="text-[22px]" />,
              sub: focus && focusRow?.verdict ? `${focus} 등급 ${focusRow.verdict}` : null,
            },
          ]}
        />
      ) : null}
      <Distribution report={report} focus={focus} psiWord={psiWord} />
      <Calibration report={report} focus={focus} chiPass={chiPass} />
      <Findings report={report} />
      <DetailAccordion report={report} rows={DETAIL_ROWS} />
    </>
  );
}

/** 등급 분포 변화 — 등급별 구성비 증감 · PSI 기여도 */
function Distribution({ report, focus, psiWord }: { report: ReportDoc; focus: string | null; psiWord: string | null }) {
  const f = report.figures;
  const t = tableOf(sectionById(report, SEC.psi));
  const chart = chartOf(sectionById(report, SEC.psi));
  if (!t) return null;
  const buckets = t.rows.map((r) => String(r.bucket ?? ""));
  const diffs = t.rows.map((r) => num(r.diff ?? null));
  const focusIdx = focus ? buckets.indexOf(focus) : -1;
  const periods = (chart?.series ?? []).map((s) => stripSuffix(s.name));
  const down = buckets.filter((_, i) => (diffs[i] ?? 0) < 0);
  const up = buckets.filter((_, i) => (diffs[i] ?? 0) > 0);
  const span = (xs: string[]) => (xs.length > 1 ? `${xs[0]}~${xs[xs.length - 1]}` : (xs[0] ?? ""));
  const contrib = t.rows
    .map((r) => ({ bucket: String(r.bucket ?? ""), v: num(r.contribution ?? null), raw: String(r.contribution ?? ""), diff: num(r.diff ?? null) }))
    .filter((r) => r.v !== null)
    .sort((a, b) => (b.v ?? 0) - (a.v ?? 0))
    .slice(0, TOP_CONTRIBUTORS);
  const dir = (xs: typeof contrib) => (xs.every((x) => (x.diff ?? 0) < 0) ? " 감소" : xs.every((x) => (x.diff ?? 0) > 0) ? " 증가" : "");
  const first = contrib.slice(0, 2);
  const second = contrib.slice(2, 4);
  return (
    <SectionCard
      title="등급 분포 변화"
      hint={`안정성${periods.length >= 2 ? ` · ${periods[0]} 대비 ${periods[1]}` : ""}${f.total_obs ? ` · ${f.total_obs.label} ${figText(f.total_obs)}` : ""}`}
    >
      <TwoColumns ratio="wide-left">
        <ChartBlock
          title={`등급별 구성비 증감 (${t.columns.find((c) => c.key === "diff")?.label.match(/\(([^)]+)\)/)?.[1] ?? "%p"})`}
          right={
            <Legend
              items={[
                { label: "줄어듦", swatch: "bg-hairline-soft" },
                { label: "늘어남", swatch: "bg-info-line" },
              ]}
            />
          }
          caption={
            down.length && up.length ? (
              <RichText as="span" figures={f} text={`상위 등급(${span(down)})이 줄고 하위 등급(${span(up)})이 늘었어요.${focus && f.share_6b_base && f.share_6b_now ? ` ${focus}는 [[fig:share_6b_base]] → [[fig:share_6b_now]]로 커졌어요.` : ""}`} />
            ) : null
          }
        >
          <DivergingColumns ariaLabel="등급별 구성비 증감" categories={buckets} values={diffs} focus={focusIdx >= 0 ? focusIdx : null} />
        </ChartBlock>
        <ColumnRule />
        <ChartBlock
          title="PSI 기여도"
          right={`합계 ${figText(f.psi_micro)}${psiWord ? ` · ${psiWord}` : ""}`}
          caption={first.length ? `${first.map((x) => x.bucket).join(" · ")}${dir(first)} 영향이 가장 크고${second.length ? `, ${second.map((x) => x.bucket).join(" · ")}${dir(second)}가 뒤를 이어요` : ""}.` : null}
        >
          <CompareBars
            labelWidth={32}
            thickness={10}
            rows={contrib.map((x) => ({ key: x.bucket, label: x.bucket, value: x.v, text: x.raw, strong: x.bucket === focus, tone: "bg-hairline" }))}
          />
        </ChartBlock>
      </TwoColumns>
    </SectionCard>
  );
}

/** 예측 이탈 등급 — 등급별 실제 · 예측 부도율 + 검정 결과 */
function Calibration({ report, focus, chiPass }: { report: ReportDoc; focus: string | null; chiPass: boolean | null }) {
  const f = report.figures;
  const t = tableOf(sectionById(report, SEC.grade));
  const chart = chartOf(sectionById(report, SEC.grade));
  if (!t) return null;
  const cell = (r: (typeof t.rows)[number], k: string) => (r[k] === null || r[k] === undefined ? NO_VALUE : String(r[k]));
  const rows = t.rows.map((r) => ({
    grade: String(r.grade ?? ""),
    dr: num(r.defaultRate ?? null),
    mid: num(r.pdMid ?? null),
    max: num(r.pdMax ?? null),
    text: { dr: cell(r, "defaultRate"), mid: cell(r, "pdMid"), max: cell(r, "pdMax"), obs: cell(r, "obsCount"), defaults: cell(r, "defaultCount"), verdict: r.verdict ? String(r.verdict) : "" },
  }));
  const warm = new Set(rows.map((r, i) => (r.dr !== null && r.mid !== null && r.dr > r.mid ? i : -1)).filter((i) => i >= 0));
  const muted = new Set(rows.map((r, i) => (i > 0 && r.dr !== null && rows[i - 1].dr !== null && r.dr < (rows[i - 1].dr as number) ? i : -1)).filter((i) => i >= 0));
  const date = /\(([^)]+)\)\s*$/.exec(t.caption ?? "")?.[1];
  const names = (chart?.series ?? []).map((s) => s.name);
  const kv = kvOf(sectionById(report, SEC.calibration));
  const step = (k: string) => kv.find((x) => x.label.includes(k))?.value;
  const warmGrades = [...warm].map((i) => rows[i].grade);
  const mutedNotes = [...muted].map((i) => `${rows[i].grade}등급은 ${rows[i - 1].grade}보다 부도율이 낮아 서열이 뒤집혔어요`);
  const tests: { key: string; label: string; note?: string; fig?: (typeof f)[string] }[] = [
    { key: "ar", label: "AR", note: f.ard_micro ? `개발시점 대비 −${figText(f.ard_micro)}` : undefined, fig: f.ar_micro },
    { key: "ks", label: "K-S", fig: f.ks_micro },
    { key: "auroc", label: "AUROC", fig: f.auroc_micro },
    { key: "chi", label: "χ² 검정", note: chiPass === null ? undefined : `임계값 ${figText(f.chi_critical)} ${chiPass ? "이내 · 통과" : "초과 · 기각"}`, fig: f.chi_stat },
  ];
  return (
    <SectionCard title="예측 이탈 등급" hint={`${names.slice(0, 2).join(" vs ")}${date ? ` · ${date}` : ""}`}>
      <TwoColumns ratio="wide-left">
        <ChartBlock
          title="등급별 실제 · 예측 부도율"
          right={
            <Legend
              items={[
                { label: names[0] ?? "실제부도율", swatch: "bg-ink-deep", shape: "dot" },
                ...(warm.size > 0 ? [{ label: "대표값 초과", swatch: "bg-attention", shape: "dot" as const }] : []),
                ...(muted.size > 0 ? [{ label: "서열 역전", swatch: "border-ink-deep", shape: "ring" as const }] : []),
                { label: names[1] ?? "예측 대표값", swatch: "bg-primary-deep", shape: "line" },
                { label: "대표값 ~ 최대값", swatch: "bg-info-line-soft" },
              ]}
            />
          }
          caption={calibrationCaption(warmGrades, mutedNotes)}
        >
          <PdRangeChart ariaLabel="등급별 실제 · 예측 부도율" rows={rows} warm={warm} muted={muted} />
        </ChartBlock>
        <ColumnRule />
        <ChartBlock title="검정 결과" caption={step("2단계") || step("3단계") ? [step("2단계"), step("3단계")].filter(Boolean).join(" — ") : null}>
          <ul className="flex flex-col gap-2">
            {tests.map((x) => (
              <li key={x.key} className="flex items-center gap-3 rounded-lg bg-page px-4 py-3">
                <span className="text-[12px] font-medium text-slate">{x.label}</span>
                <span className="ml-auto text-[10px] text-steel">{x.note}</span>
                {x.fig ? <Fig figure={x.fig} size={20} /> : <NoValue className="text-[20px]" />}
              </li>
            ))}
          </ul>
        </ChartBlock>
      </TwoColumns>
    </SectionCard>
  );
}

/** 점에 올리면 툴팁이 나온다는 안내 (화면 조작 안내) */
const TIP_HINT = "점에 마우스를 올리면 등급별 값이 보여요.";
/** 예측 이탈 해설 — 대표값을 넘은 등급 · 서열이 뒤집힌 등급 + 툴팁 안내 */
function calibrationCaption(warm: string[], muted: string[]): string {
  const over = warm.length ? `${warm.join(" · ")}${warm.length === 1 && hasFinalConsonant(warm[0]) ? "은" : "는"} 실제부도율이 예측 대표값을 넘었` : null;
  const body = over && muted.length ? `${over}고, ${muted.join(", ")}.` : over ? `${over}어요.` : muted.length ? `${muted.join(", ")}.` : "";
  return body ? `${body} ${TIP_HINT}` : TIP_HINT;
}
/** 등급 글자의 끝소리에 받침이 있는가 ('6B' → 비 · 없음, '8' → 팔 · 있음) — 은/는 고르기 */
function hasFinalConsonant(grade: string): boolean {
  return /[013678]$/.test(grade) || /[LMNR]$/i.test(grade);
}

/** 특이사항 · 가이드 — 탐지된 특이사항 표 → 심각도 · 특이사항 · 가이드 (+ 제안안 보기) */
function Findings({ report }: { report: ReportDoc }) {
  const section = sectionById(report, SEC.findings);
  const t = tableOf(section);
  if (!t) return null;
  const op = report.opinions[0];
  const align = op?.verifications.find((v) => v.checkCode === "alignment");
  const note = calloutOf(section);
  return (
    <SectionCard title="특이사항 · 가이드" hint={align ? `상위 기준 배치 검증 ${align.passed === false ? "확인 필요" : "완료"}${align.detail ? ` · ${align.detail}` : ""}` : null}>
      <ul className="border-t border-hairline-soft">
        {t.rows.map((r, i) => {
          const word = String(r.severity ?? "");
          const sev = severityFromText(word, SEVERITY_TEXT);
          return (
            <li key={String(r.no ?? i)} className="flex flex-wrap items-start gap-x-4 gap-y-1 border-b border-hairline-soft py-3.5">
              <span className="w-12 shrink-0 pt-0.5">{word ? <MiniTag tone={toneOfWord(word)}>{word}</MiniTag> : null}</span>
              <div className="min-w-0 flex-1">
                <RichText text={politeTitle(String(r.item ?? ""), report.figures)} figures={report.figures} className="text-[14px] font-bold leading-[1.4] text-ink-deep" />
                {r.guide ? <RichText text={politeTitle(String(r.guide), report.figures)} figures={report.figures} className="mt-1 text-[12px] leading-[1.5] text-steel" /> : null}
              </div>
              {sev && PROPOSAL_SEVERITY.includes(sev) ? (
                <Link href={GUIDES_HREF} className={TEXT_LINK}>
                  제안안 보기
                  <IconChevron className="h-3 w-3" />
                </Link>
              ) : null}
            </li>
          );
        })}
      </ul>
      {note ? <RichText text={toPoliteText(note)} figures={report.figures} className="mt-3 text-[12px] leading-[1.5] text-steel" /> : null}
    </SectionCard>
  );
}
