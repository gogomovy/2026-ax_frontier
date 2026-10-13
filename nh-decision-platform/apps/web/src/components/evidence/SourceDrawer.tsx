"use client";

import { useEffect, useRef, useState } from "react";
import { useUi } from "@/components/providers/UiProvider";
import { Badge, IconDoc, IconWarn } from "@/components/ui/primitives";
import { formatFigure } from "@/lib/format";
import { useFocusTrap } from "@/lib/a11y";
import { EvidenceBody } from "./EvidenceBody";

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
        className="flex h-full w-full max-w-[560px] animate-slide-in-right flex-col bg-canvas shadow-popup outline-none"
      >
        <header className="flex items-start justify-between gap-base border-b border-hairline-soft px-7 py-5">
          <div className="min-w-0">
            <p className="text-[12px] text-steel">{drawer.kind === "evidence" ? "근거 원문" : drawer.kind === "calc" ? "계산 추적" : "용어 정의"}</p>
            <h2 className="mt-1 text-[20px] font-bold leading-[1.3] text-ink-deep">{drawer.title}</h2>
          </div>
          <button
            type="button"
            onClick={closeDrawer}
            className="inline-flex h-8 shrink-0 items-center rounded-md border border-hairline bg-canvas px-3 text-[13px] font-bold text-ink-deep hover:bg-surface-soft"
          >
            닫기
          </button>
        </header>

        <div className="flex-1 overflow-y-auto px-7 py-5">
          {drawer.kind === "evidence" ? (
            <EvidenceBody items={drawer.items} selected={selected} onSelect={setSelected} statement={drawer.statement} />
          ) : null}
          {drawer.kind === "calc" ? <CalcBody payload={drawer} /> : null}
          {drawer.kind === "term" ? <TermBody payload={drawer} /> : null}
        </div>
      </aside>
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
