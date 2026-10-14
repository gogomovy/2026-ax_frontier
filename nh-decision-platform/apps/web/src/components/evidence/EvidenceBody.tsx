"use client";

import clsx from "clsx";
import { IconDoc, IconCalc } from "@/components/ui/primitives";
import { IconExternal } from "@/components/ui/icons";
import { Badge } from "@/components/ui/primitives";
import { DB_CLASS_LABEL, EVIDENCE_CATEGORY_LABEL, formatDate } from "@/lib/format";
import type { Evidence, EvidenceCategory } from "@/lib/types";
import { TONE_BADGE, bandOf, type Band } from "@/lib/uiConfig";
import { useUiConfig } from "@/components/providers/SessionProvider";

/** 원본 문서 뷰어 주소 — 파일명 · 제목으로 문서를 찾고, 인용문 위치를 하이라이트한다 (F.12) */
export function docViewerHref(item: Evidence): string {
  const qs = new URLSearchParams();
  if (item.doc?.fileName) qs.set("file", item.doc.fileName);
  if (item.doc?.title) qs.set("title", item.doc.title);
  if (item.doc?.page) qs.set("page", String(item.doc.page));
  if (item.snippet) qs.set("q", item.snippet.slice(0, 300));
  return `/knowledge/doc?${qs.toString()}`;
}

const ORDER: EvidenceCategory[] = ["bank_data", "internal_direction", "external_policy"];

/** 검색 적합도는 값이 없을 수 있다(undefined · null) — 그때는 라벨을 그리지 않는다. 구간 · 이름은 [화면 설정 › 판정 구간 › 근거 관련도] */
function relevanceTag(r: number | null | undefined, bands: Band[] | undefined): { label: string; tone: ReturnType<typeof toneOf> } | null {
  const b = bandOf(r, bands);
  return b ? { label: b.label, tone: toneOf(b.tone) } : null;
}
const toneOf = (t: Band["tone"]) => TONE_BADGE[t];

/**
 * 근거 원문 서랍 본문 (가이드 7157): 경로 → 검증할 해설 → 범주별 근거(선택됨 표시) → 참고한 내용.
 * 범주는 항상 세 개를 보여 주고, 근거가 없는 범주는 점선 칸으로 "없음"을 분명히 알린다(공백 금지).
 */
export function EvidenceBody({
  items,
  selected,
  onSelect,
  statement,
}: {
  items: Evidence[];
  selected: string | null;
  onSelect: (id: string) => void;
  statement?: string;
}) {
  const active = items.find((i) => i.id === selected) ?? items[0];

  return (
    <div className="flex flex-col gap-6">
      {/* AI 판단 → 근거 → 근거 문서 → 원문 경로 */}
      <ol className="flex flex-wrap items-center gap-x-2 gap-y-1 rounded-md bg-surface-soft px-3 py-2 text-[12px] text-steel">
        <li>Agent 해설</li>
        <li aria-hidden="true">›</li>
        <li>판단 근거</li>
        <li aria-hidden="true">›</li>
        <li>근거 문서</li>
        <li aria-hidden="true">›</li>
        <li className="font-bold text-primary">원문 확인</li>
      </ol>

      {statement ? (
        <blockquote className="border-l-[3px] border-primary pl-3">
          <p className="text-[12px] text-steel">검증할 해설</p>
          <p className="mt-0.5 text-[14px] font-bold leading-normal text-ink-deep">{statement}</p>
        </blockquote>
      ) : null}

      {ORDER.map((category) => {
        const group = items.filter((i) => i.category === category);
        return (
          <section key={category}>
            <h3 className="mb-2 flex items-baseline gap-1.5 text-[14px] font-bold text-ink-deep">
              {EVIDENCE_CATEGORY_LABEL[category]}
              <span className="text-[12px] font-normal text-steel tnum">{group.length}건</span>
            </h3>
            {group.length === 0 ? (
              <p className="rounded-lg border border-dashed border-hairline px-4 py-3 text-[12px] text-steel">이 해설에 연결된 {EVIDENCE_CATEGORY_LABEL[category]} 근거가 없어요.</p>
            ) : (
              <ul className="flex flex-col gap-2">
                {group.map((item) => {
                  const on = active?.id === item.id;
                  return (
                    <li key={item.id}>
                      <button
                        type="button"
                        onClick={() => onSelect(item.id)}
                        aria-pressed={on}
                        className={clsx(
                          "flex w-full items-start gap-3 rounded-lg border px-4 py-3 text-left transition-colors",
                          on ? "border-primary bg-canvas shadow-[0_0_0_1px_var(--color-primary)]" : "border-hairline-soft bg-canvas hover:bg-surface-soft",
                        )}
                      >
                        <span className="min-w-0 flex-1">
                          <span className="block text-[14px] font-bold leading-snug text-ink-deep">{item.label}</span>
                          <span className="mt-0.5 block text-[12px] text-steel">
                            {item.doc
                              ? `${item.doc.issuer ?? ""}${item.doc.effectiveDate ? ` · ${formatDate(item.doc.effectiveDate)}` : ""}${item.doc.page ? ` · p.${item.doc.page}` : ""}`
                              : (item.tableRef ?? "")}
                          </span>
                        </span>
                        {on ? <span className="shrink-0 text-[12px] font-bold text-primary">선택됨</span> : <span aria-hidden="true" className="shrink-0 text-icon">›</span>}
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        );
      })}

      {active ? <EvidenceDetail item={active} /> : null}
    </div>
  );
}

function EvidenceDetail({ item }: { item: Evidence }) {
  const rel = relevanceTag(item.relevance, useUiConfig().bands.evidenceRelevance);
  const openable = item.doc && item.doc.dbClass !== "external_web";
  return (
    <section className="rounded-xl bg-surface-soft p-5">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        {item.doc ? <IconDoc className="text-steel" /> : <IconCalc className="text-steel" />}
        <h3 className="text-[14px] font-bold text-ink-deep">참고한 내용</h3>
        {item.doc?.isOfficial ? <Badge tone="neutral">공식 자료</Badge> : null}
        {item.doc?.dbClass === "external_web" ? <Badge tone="warning">외부 수집 · 보조자료</Badge> : null}
      </div>

      <dl className="grid grid-cols-[56px_1fr] gap-x-4 gap-y-2 text-[12px]">
        {item.doc ? (
          <>
            <dt className="text-steel">문서</dt>
            <dd className="font-medium text-ink-deep">{item.doc.title}</dd>
            <dt className="text-steel">작성</dt>
            <dd className="text-ink-deep">
              {item.doc.issuer ?? "-"}
              {item.doc.effectiveDate ? ` · ${formatDate(item.doc.effectiveDate)}` : ""}
            </dd>
            <dt className="text-steel">구분</dt>
            <dd className="text-ink-deep">{DB_CLASS_LABEL[item.doc.dbClass]}</dd>
            {item.doc.sectionPath || item.doc.page ? (
              <>
                <dt className="text-steel">위치</dt>
                <dd className="text-ink-deep">
                  {item.doc.sectionPath}
                  {item.doc.page ? ` · p.${item.doc.page}` : ""}
                </dd>
              </>
            ) : null}
          </>
        ) : (
          <>
            <dt className="text-steel">위치</dt>
            <dd className="font-medium text-ink-deep">{item.tableRef ?? item.sourceKind}</dd>
          </>
        )}
      </dl>

      {item.snippet ? <blockquote className="mt-4 rounded-lg border border-hairline-soft bg-canvas px-4 py-3 text-[14px] leading-relaxed text-ink-deep">“{item.snippet}”</blockquote> : null}

      <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
        {rel ? <Badge tone={rel.tone}>{rel.label}</Badge> : <span className="text-[12px] text-steel">{item.doc ? "문서 근거" : "데이터 근거"}</span>}
        {openable && item.doc ? (
          <a
            href={docViewerHref(item)}
            target="_blank"
            rel="noopener noreferrer"
            data-doc-open
            className="inline-flex h-9 items-center gap-1.5 rounded-md border border-hairline bg-canvas px-3 text-[13px] font-bold text-ink-deep hover:bg-surface-soft"
          >
            원문 열기{item.doc.fileName ? ` (${item.doc.fileName.split(".").pop()?.toUpperCase()})` : ""}
            <IconExternal />
          </a>
        ) : item.doc ? (
          <span className="text-[12px] text-steel">{item.doc.dbClass === "external_web" ? "외부 수집 자료 · 원본 미보관" : `원본 · ${item.doc.fileName ?? "파일"}`}</span>
        ) : null}
      </div>
    </section>
  );
}
