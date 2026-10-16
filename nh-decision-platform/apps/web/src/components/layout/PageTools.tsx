"use client";

import { useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useId, useMemo, useRef, useState, useTransition, type ReactNode } from "react";
import clsx from "clsx";
import { useSession } from "@/components/providers/SessionProvider";
import { IconChevronDown, IconChevronLeft, IconRefresh } from "@/components/ui/icons";
import { IconDownload } from "@/components/ui/primitives";
import { formatKstShort, formatYearMonth } from "@/lib/format";
import { NO_VALUE } from "@/lib/period";
import { printFitOnePage } from "@/lib/printPage";
import { useDismiss } from "@/lib/useDismiss";

/* ── 기준월 선택 (화면 공용) ──────────────────────────────
 * 고를 수 있는 달 = 화면 자료가 있는 달만. 자료가 없는 달은 회색으로 두고 누를 수 없게 한다(안내 문구 없음).
 * 지금 화면 API 에는 기준월 인자가 없어 자료가 있는 달은 현재 자료 기준월 하나다 —
 * 기준월별 화면 자료를 내려주게 되면 availableMonths 에 그 달들을 넣으면 된다. */
type YearMonth = { year: number; month: number };
const AsOfSelectionContext = createContext<{ selected: YearMonth | null; select: (ym: YearMonth | null) => void } | null>(null);

/** 기준월 선택 공유 — 루트 레이아웃에서 한 번 감싼다 */
export function AsOfSelectionProvider({ children }: { children: ReactNode }) {
  const [selected, setSelected] = useState<YearMonth | null>(null);
  const value = useMemo(() => ({ selected, select: setSelected }), [selected]);
  return <AsOfSelectionContext.Provider value={value}>{children}</AsOfSelectionContext.Provider>;
}

/** 고른 기준월 (null = 자료 기준월 그대로) */
export function useAsOfSelection() {
  const ctx = useContext(AsOfSelectionContext);
  if (!ctx) throw new Error("useAsOfSelection 은 AsOfSelectionProvider 안에서만 쓸 수 있어요");
  return ctx;
}

/** 'YYYY-MM-DD…' → 연 · 월 (형식이 다르면 null) */
function parseYearMonth(iso: string): YearMonth | null {
  const m = /^(\d{4})-(\d{2})/.exec(iso);
  return m ? { year: Number(m[1]), month: Number(m[2]) } : null;
}
const ymIso = (ym: YearMonth) => `${ym.year}-${String(ym.month).padStart(2, "0")}-01`;
const MONTHS = Array.from({ length: 12 }, (_, i) => i + 1);
const ymKey = (ym: YearMonth) => ym.year * 100 + ym.month;

/** 화면 자료가 있는 달 — 지금은 자료 기준월 하나 (위 설명 참고) */
function availableMonths(data: YearMonth): YearMonth[] {
  return [data];
}

/** 기준월 선택 — 글자 + 꺾쇠, 누르면 연도 · 월 고르기 팝오버 */
function AsOfPicker({ data }: { data: YearMonth }) {
  const { selected, select } = useAsOfSelection();
  const available = availableMonths(data);
  const availableKeys = new Set(available.map(ymKey));
  const years = available.map((a) => a.year);
  const minYear = Math.min(...years);
  const maxYear = Math.max(...years);
  // 고른 달이 (자료 변경 등으로) 더는 고를 수 없으면 자료 기준월로 본다
  const current = selected && availableKeys.has(ymKey(selected)) ? selected : data;
  const [open, setOpen] = useState(false);
  const [viewYear, setViewYear] = useState(current.year);
  const box = useRef<HTMLDivElement>(null);
  const id = useId();
  const close = useCallback(() => setOpen(false), []);
  useDismiss(box, open, close);

  return (
    <div ref={box} className="relative">
      <button
        type="button"
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => {
          setViewYear(current.year);
          setOpen((v) => !v);
        }}
        className="inline-flex h-[31px] items-center gap-1 rounded-md text-[13px] font-bold text-ink-deep focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
      >
        {formatYearMonth(ymIso(current))} 기준
        <IconChevronDown size={12} className="text-steel" />
      </button>
      {open ? (
        <div id={id} role="dialog" aria-label="기준월 선택" className="absolute right-0 top-[calc(100%+6px)] z-50 w-[232px] animate-pop-in rounded-xl border border-hairline-soft bg-canvas p-3 shadow-tooltip">
          <div className="flex items-center justify-between">
            <button
              type="button"
              aria-label="이전 연도"
              disabled={viewYear <= minYear}
              onClick={() => setViewYear((y) => Math.max(minYear, y - 1))}
              className="inline-flex h-7 w-7 items-center justify-center rounded-md text-steel hover:bg-surface-soft hover:text-ink-deep focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:cursor-not-allowed disabled:text-icon disabled:hover:bg-transparent"
            >
              <IconChevronLeft />
            </button>
            <span className="tnum text-[13px] font-bold text-ink-deep" aria-live="polite">
              {viewYear}년
            </span>
            <button
              type="button"
              aria-label="다음 연도"
              disabled={viewYear >= maxYear}
              onClick={() => setViewYear((y) => Math.min(maxYear, y + 1))}
              className="inline-flex h-7 w-7 items-center justify-center rounded-md text-steel hover:bg-surface-soft hover:text-ink-deep focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:cursor-not-allowed disabled:text-icon disabled:hover:bg-transparent"
            >
              <IconChevronLeft className="rotate-180" />
            </button>
          </div>
          <div className="mt-2 grid grid-cols-4 gap-1">
            {MONTHS.map((m) => {
              const on = viewYear === current.year && m === current.month;
              // 자료가 없는 달 — 회색 · 누를 수 없음
              const unavailable = !availableKeys.has(viewYear * 100 + m);
              return (
                <button
                  key={m}
                  type="button"
                  aria-pressed={on}
                  disabled={unavailable}
                  title={unavailable ? "이 달은 아직 자료가 없어요" : undefined}
                  onClick={() => {
                    const ym = { year: viewYear, month: m };
                    // 자료 기준월을 고르면 선택을 지워 '최신' 상태로 둔다
                    select(ym.year === data.year && ym.month === data.month ? null : ym);
                    setOpen(false);
                  }}
                  className={clsx(
                    "h-8 rounded-md text-[13px] tnum focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary",
                    on ? "bg-info-faint font-bold text-primary-deep" : unavailable ? "cursor-not-allowed text-icon" : "font-medium text-ink-deep hover:bg-surface-soft",
                  )}
                >
                  {m}월
                </button>
              );
            })}
          </div>
        </div>
      ) : null}
    </div>
  );
}

/**
 * 화면 머리말 오른쪽 도구 (1 · 2 · 3단계 공통) — 기준월 선택 · '기준 YYYY.MM 마감 · 최종 분석' + 새로고침 · 화면별 버튼.
 * 메타 글자는 언제나 실제 자료 기준월 · 분석 시각을 보여 준다.
 */
export function AsOfTools({ children }: { children?: ReactNode }) {
  const { menu, generatedAt } = useSession();
  const router = useRouter();
  const [pending, start] = useTransition();
  // 기준월 · 최종 분석 시각은 서버가 준 값만 쓴다 — 없으면 '–' (하드코딩 없음 · Phase I)
  const asOf = menu?.asOf ?? "";
  const data = parseYearMonth(asOf);
  const asOfDot = data ? `${data.year}.${String(data.month).padStart(2, "0")}` : NO_VALUE;
  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-1">
      {data ? <AsOfPicker data={data} /> : <span className="text-[13px] font-bold text-ink-deep">기준일 {NO_VALUE}</span>}
      <span className="inline-flex items-center gap-0.5 tnum text-[12px] text-steel">
        기준 {asOfDot} 마감
        {generatedAt ? <> · 최종 분석 {formatKstShort(generatedAt)}</> : null}
        <button
          type="button"
          onClick={() => start(() => router.refresh())}
          aria-label="화면 데이터 새로고침"
          title="새로고침"
          className="no-print inline-flex h-[26px] w-7 items-center justify-center rounded-md text-steel hover:bg-surface-soft hover:text-ink-deep focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
        >
          <IconRefresh size={16} className={clsx(pending && "animate-spin")} />
        </button>
      </span>
      {children ? <div className="flex flex-wrap items-center gap-1">{children}</div> : null}
    </div>
  );
}

/** 보조 도구 단추 — 고스트 (도구 모음, hover neutral/50) */
export function ToolButton({ onClick, icon, children, ...rest }: { onClick?: () => void; icon?: ReactNode; children: ReactNode; "data-tool"?: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      {...rest}
      className="inline-flex h-[31px] items-center gap-[5px] rounded-md px-1.5 text-[14px] font-medium text-ink-deep transition-colors hover:bg-surface-soft no-print"
    >
      {icon}
      {children}
    </button>
  );
}

/**
 * 내보내기 — 지금 화면을 한 장 PDF 로. 인쇄 배치를 먼저 만들어 내용 크기를 재고, 그 크기의 한 쪽으로 인쇄한다(잘리지 않고 쪽이 나뉘지 않음).
 * 인쇄 창에서 대상을 "PDF 로 저장"으로 고르면 된다 (EXP-01).
 */
export function ExportButton() {
  const [busy, setBusy] = useState(false);
  return (
    <ToolButton
      icon={<IconDownload />}
      onClick={() => {
        if (busy) return;
        setBusy(true);
        printFitOnePage()
          .catch(() => window.print()) // 준비에 실패하면 브라우저 기본 인쇄로
          .finally(() => setBusy(false));
      }}
    >
      {busy ? "준비 중…" : "내보내기"}
    </ToolButton>
  );
}
