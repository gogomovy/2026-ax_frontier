"use client";

import { useEffect, useRef, useState } from "react";
import clsx from "clsx";
import { useUi } from "@/components/providers/UiProvider";
import { Badge, IconCalc, IconDoc, IconWarn } from "@/components/ui/primitives";
import { EVIDENCE_CATEGORY_LABEL, DB_CLASS_LABEL, formatDate, formatFigure } from "@/lib/format";
import { API_MODE } from "@/lib/config";
import type { Evidence } from "@/lib/types";
import { useFocusTrap } from "@/lib/a11y";

/** 원본 문서 뷰어 주소 — 파일명 · 제목으로 문서를 찾고, 인용문 위치를 하이라이트한다 (F.12) */
function docViewerHref(item: Evidence): string {
  const qs = new URLSearchParams();
  if (item.doc?.fileName) qs.set("file", item.doc.fileName);
  if (item.doc?.title) qs.set("title", item.doc.title);
  if (item.doc?.page) qs.set("page", String(item.doc.page));
  if (item.snippet) qs.set("q", item.snippet.slice(0, 300));
  return `/knowledge/doc?${qs.toString()}`;
}

const CATEGORY_TONE = {
  bank_data: "info",
  internal_direction: "attention",
  external_policy: "success",
} as const;

/** 근거 원문 확인 · 계산 추적 · 용어 정의를 담는 우측 패널 (DB-07, UX-02/03/04) */
export function SourceDrawer() {
  const { drawer, closeDrawer } = useUi();
  // 드로어가 새로 열리면 기본 선택(지정 근거 또는 첫 근거) — 사용자가 고른 값은 같은 드로어 안에서만 유지
  const [pick, setPick] = useState<{ for: unknown; id: string | null }>({ for: null, id: null });
  const selected =
    drawer?.kind === "evidence" ? (pick.for === drawer ? pick.id : (drawer.selectedId ?? drawer.items[0]?.id ?? null)) : null;
  const setSelected = (id: string | null) => setPick({ for: drawer, id });
  const panelRef = useRef<HTMLElement>(null);
  // 열리면 패널로 포커스, Tab 은 패널 안에서만, 닫히면 연 요소(수치 · 근거 버튼)로 복귀 (B.33)
  useFocusTrap(panelRef, Boolean(drawer));

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") closeDrawer();
    };
    if (drawer) window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [drawer, closeDrawer]);

  if (!drawer) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end no-print">
      <button
        type="button"
        aria-label="닫기"
        tabIndex={-1}
        onClick={closeDrawer}
        className="flex-1 bg-scrim"
      />
      <aside
        ref={panelRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label={drawer.title}
        className="flex h-full w-full max-w-[520px] flex-col bg-canvas shadow-pop outline-none"
      >
        <header className="flex items-start justify-between gap-base border-b border-hairline-soft px-xl py-lg">
          <div>
            <p className="text-[11px] font-bold uppercase tracking-wide text-steel">
              {drawer.kind === "evidence" ? "근거 원문" : drawer.kind === "calc" ? "계산 추적" : "용어 정의"}
            </p>
            <h2 className="mt-1 text-[17px] font-bold leading-snug text-ink-deep">{drawer.title}</h2>
          </div>
          <button
            type="button"
            onClick={closeDrawer}
            className="rounded-pill bg-surface-soft px-3 py-1.5 text-[12px] font-bold text-charcoal"
          >
            닫기
          </button>
        </header>

        <div className="flex-1 overflow-y-auto px-xl py-lg">
          {drawer.kind === "evidence" ? (
            <EvidenceBody items={drawer.items} selected={selected} onSelect={setSelected} />
          ) : null}
          {drawer.kind === "calc" ? <CalcBody payload={drawer} /> : null}
          {drawer.kind === "term" ? <TermBody payload={drawer} /> : null}
        </div>
      </aside>
    </div>
  );
}

function EvidenceBody({
  items,
  selected,
  onSelect,
}: {
  items: Evidence[];
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  const grouped = (["bank_data", "internal_direction", "external_policy"] as const).map((category) => ({
    category,
    items: items.filter((i) => i.category === category),
  }));
  const active = items.find((i) => i.id === selected) ?? items[0];

  return (
    <div className="flex flex-col gap-lg">
      {/* Agent 판단 → 근거 → 근거 문서 → 원문 경로를 명시 */}
      <ol className="soft flex items-center gap-2 px-base py-2.5 text-[11px] text-steel">
        <li className="font-bold text-charcoal">Agent 판단</li>
        <li aria-hidden>›</li>
        <li className="font-bold text-primary">판단 근거</li>
        <li aria-hidden>›</li>
        <li>근거 데이터·문서</li>
        <li aria-hidden>›</li>
        <li>원문 확인</li>
      </ol>

      {grouped.map((group) => (
        <div key={group.category}>
          <div className="mb-2 flex items-center gap-2">
            <Badge tone={CATEGORY_TONE[group.category]}>{EVIDENCE_CATEGORY_LABEL[group.category]}</Badge>
            <span className="text-[11px] text-stone">{group.items.length}건</span>
          </div>
          {group.items.length === 0 ? (
            <p className="rounded-lg border border-dashed border-hairline px-3 py-2.5 text-[12px] text-stone">
              해당 범주 근거 없음
            </p>
          ) : (
            <ul className="flex flex-col gap-2">
              {group.items.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    onClick={() => onSelect(item.id)}
                    className={clsx(
                      "w-full rounded-lg border px-3 py-2.5 text-left transition-colors",
                      active?.id === item.id
                        ? "border-primary bg-info-faint"
                        : "border-hairline-soft bg-canvas",
                    )}
                  >
                    <p className="text-[13px] font-bold text-ink">{item.label}</p>
                    {item.doc ? (
                      <p className="mt-0.5 text-[11px] text-steel">
                        {item.doc.issuer} · {formatDate(item.doc.effectiveDate ?? "")}
                        {item.doc.page ? ` · p.${item.doc.page}` : ""}
                      </p>
                    ) : item.tableRef ? (
                      <p className="mt-0.5 text-[11px] text-steel">{item.tableRef}</p>
                    ) : null}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      ))}

      {active ? <EvidenceDetail item={active} /> : null}
    </div>
  );
}

function EvidenceDetail({ item }: { item: Evidence }) {
  return (
    <div className="panel bg-surface-soft p-base">
      <div className="mb-2 flex items-center gap-2">
        {item.doc ? <IconDoc className="text-steel" /> : <IconCalc className="text-steel" />}
        <p className="text-[12px] font-bold text-charcoal">참고한 내용</p>
        {item.doc?.isOfficial ? <Badge tone="success">공식 자료</Badge> : null}
        {item.doc?.dbClass === "external_web" ? <Badge tone="warning">외부 수집 · 보조자료</Badge> : null}
      </div>

      {item.doc ? (
        <dl className="mb-3 grid grid-cols-[84px_1fr] gap-x-3 gap-y-1.5 text-[12px]">
          <dt className="text-stone">문서명</dt>
          <dd className="font-medium text-ink">{item.doc.title}</dd>
          <dt className="text-stone">출처</dt>
          <dd className="text-charcoal">{item.doc.issuer ?? "-"}</dd>
          <dt className="text-stone">기준일</dt>
          <dd className="text-charcoal">{formatDate(item.doc.effectiveDate ?? "")}</dd>
          <dt className="text-stone">구분</dt>
          <dd className="text-charcoal">{DB_CLASS_LABEL[item.doc.dbClass]}</dd>
          {item.doc.sectionPath ? (
            <>
              <dt className="text-stone">위치</dt>
              <dd className="text-charcoal">
                {item.doc.sectionPath}
                {item.doc.page ? ` (p.${item.doc.page})` : ""}
              </dd>
            </>
          ) : null}
        </dl>
      ) : (
        <dl className="mb-3 grid grid-cols-[84px_1fr] gap-x-3 gap-y-1.5 text-[12px]">
          <dt className="text-stone">데이터 위치</dt>
          <dd className="font-medium text-ink">{item.tableRef ?? item.sourceKind}</dd>
        </dl>
      )}

      {item.snippet ? (
        <blockquote className="border-l-2 border-primary pl-3 text-[12.5px] leading-relaxed text-charcoal">
          {item.snippet}
        </blockquote>
      ) : null}

      <div className="mt-3 flex items-center justify-between gap-2">
        <p className="text-[11px] text-stone">
          {item.relevance !== undefined ? `의미 적합도 ${item.relevance.toFixed(2)}` : "데이터 근거"}
        </p>
        {item.doc && API_MODE && item.doc.dbClass !== "external_web" ? (
          <a
            href={docViewerHref(item)}
            target="_blank"
            rel="noopener noreferrer"
            data-doc-open
            className="rounded-pill border-2 border-line-strong px-3 py-1.5 text-[11px] font-bold text-ink-deep"
          >
            원본 열기 · {item.doc.fileName ?? "파일"}
          </a>
        ) : item.doc ? (
          <span className="text-[11px] text-stone" title="원본 뷰어는 백엔드 연결(API 모드)에서 제공됩니다">
            {item.doc.dbClass === "external_web" ? "외부 수집 자료 · 원본 미보관" : `원본 · ${item.doc.fileName ?? "파일"}`}
          </span>
        ) : null}
      </div>
    </div>
  );
}

function CalcBody({ payload }: { payload: Extract<import("@/components/providers/UiProvider").DrawerPayload, { kind: "calc" }> }) {
  const { figure } = payload;
  const trace = payload.trace ?? figure.calc;

  return (
    <div className="flex flex-col gap-lg">
      <div className="soft p-base">
        <p className="text-[12px] text-steel">{figure.label}</p>
        <p className="mt-1 text-[26px] font-bold leading-none text-ink-deep tnum">{formatFigure(figure)}</p>
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          {figure.dataOrigin === "simulated" ? <Badge tone="warning">시뮬레이션 데이터</Badge> : null}
          {figure.dataOrigin === "actual" ? <Badge tone="neutral">실데이터</Badge> : null}
          {figure.dataOrigin === "mixed" ? <Badge tone="warning">실데이터 · 시뮬레이션 혼합</Badge> : null}
          {figure.value === null ? <Badge tone="critical">산출 불가</Badge> : null}
          {figure.stale ? <Badge tone="critical">갱신 실패 — 이전 값</Badge> : null}
        </div>
        {figure.stale && figure.staleReason ? (
          <p className="mt-2 text-[11.5px] text-critical">최근 계산 실패: {figure.staleReason}</p>
        ) : null}
      </div>

      {trace ? (
        <>
          <div>
            <p className="mb-1.5 text-[12px] font-bold text-charcoal">수식</p>
            <p className="panel bg-canvas px-3 py-2.5 font-mono text-[12.5px] text-ink">{trace.expression}</p>
            <p className="mt-1 text-[11px] text-stone">
              {trace.formulaId} v{trace.formulaVersion} · calc_id {trace.calcId}
            </p>
          </div>

          <div>
            <p className="mb-1.5 text-[12px] font-bold text-charcoal">입력값과 원천</p>
            <ul className="flex flex-col gap-2">
              {trace.inputs.map((input) => (
                <li key={input.key} className="panel px-3 py-2.5">
                  <div className="flex items-baseline justify-between gap-2">
                    <p className="text-[12px] text-steel">{input.label}</p>
                    <p className="text-[13px] font-bold text-ink tnum">
                      {input.value}
                      {input.unit ? <span className="ml-1 text-[11px] font-normal text-steel">{input.unit}</span> : null}
                    </p>
                  </div>
                  <p className="mt-1 break-all font-mono text-[11px] text-stone">{input.source}</p>
                </li>
              ))}
            </ul>
          </div>

          {trace.warnings?.length ? (
            <ul className="flex flex-col gap-1 rounded-lg bg-attention-faint px-3 py-2 text-[11.5px] text-charcoal">
              {trace.warnings.map((w) => (
                <li key={w}>확인 필요 · {w}</li>
              ))}
            </ul>
          ) : null}
          {trace.note ? (
            <p className="rounded-lg bg-info-faint px-3 py-2 text-[11.5px] text-charcoal">{trace.note}</p>
          ) : null}
          <p className="text-[11px] text-stone">계산 시각 {trace.executedAt}</p>
        </>
      ) : figure.sourceRef ? (
        <div>
          <p className="mb-1.5 text-[12px] font-bold text-charcoal">원천 데이터 위치</p>
          <p className="panel break-all px-3 py-2.5 font-mono text-[12px] text-ink">{figure.sourceRef}</p>
          <p className="mt-2 text-[11.5px] text-steel">
            원천 값을 그대로 사용한 지표입니다(계산식 미적용). 파일·셀 단위까지 추적됩니다.
          </p>
        </div>
      ) : (
        <div className="flex items-start gap-2 rounded-lg bg-warning-soft px-3 py-2.5">
          <IconWarn className="mt-0.5 text-warning" />
          <p className="text-[12px] text-warning">
            이 값은 계산 추적 정보가 연결되지 않았습니다. 실제 시스템에서는 렌더링 단계에서 차단됩니다.
          </p>
        </div>
      )}
    </div>
  );
}

function TermBody({ payload }: { payload: Extract<import("@/components/providers/UiProvider").DrawerPayload, { kind: "term" }> }) {
  const { term } = payload;
  return (
    <div className="flex flex-col gap-lg">
      <div>
        <div className="flex items-center gap-2">
          <h3 className="text-[20px] font-bold text-ink-deep">{term.prefLabel}</h3>
          <Badge tone="info">용어집</Badge>
        </div>
        {term.altLabels.length ? (
          <p className="mt-1 text-[12px] text-stone">동의어 · {term.altLabels.join(" / ")}</p>
        ) : null}
      </div>

      <div>
        <p className="mb-1 text-[12px] font-bold text-charcoal">정의</p>
        <p className="text-[13.5px] leading-relaxed text-ink">{term.definition}</p>
      </div>

      {term.formula ? (
        <div>
          <p className="mb-1 text-[12px] font-bold text-charcoal">계산방법</p>
          <p className="panel bg-surface-soft px-3 py-2.5 font-mono text-[12.5px] text-ink">{term.formula}</p>
        </div>
      ) : null}

      {term.judgement ? (
        <div>
          <p className="mb-1 text-[12px] font-bold text-charcoal">판단방법</p>
          <p className="text-[13px] leading-relaxed text-charcoal">{term.judgement}</p>
        </div>
      ) : null}

      {term.example ? (
        <div>
          <p className="mb-1 text-[12px] font-bold text-charcoal">예시</p>
          <p className="rounded-lg bg-info-faint px-3 py-2.5 text-[12.5px] text-charcoal">{term.example}</p>
        </div>
      ) : null}

      <div className="panel bg-surface-soft p-base">
        <div className="mb-1.5 flex items-center gap-2">
          <IconDoc className="text-steel" />
          <p className="text-[12px] font-bold text-charcoal">근거 문서</p>
        </div>
        <p className="text-[13px] font-medium text-ink">{term.src.title}</p>
        <p className="mt-0.5 text-[11.5px] text-steel">
          {term.src.fileName} · p.{term.src.page}
        </p>
        <p className="mt-2 text-[11px] text-stone">
          용어가 온톨로지에 등록되어 있어 보고서 본문에서 정의·수식·판단방법·근거문서로 연결됩니다.
        </p>
      </div>

      {term.relatedTerms.length ? (
        <div>
          <p className="mb-1.5 text-[12px] font-bold text-charcoal">관련 용어</p>
          <div className="flex flex-wrap gap-1.5">
            {term.relatedTerms.map((t) => (
              <Badge key={t} tone="neutral">
                {t}
              </Badge>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
