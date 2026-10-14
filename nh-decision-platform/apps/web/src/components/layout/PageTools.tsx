"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition, type ReactNode } from "react";
import clsx from "clsx";
import { useSession } from "@/components/providers/SessionProvider";
import { IconCalendar, IconRefresh } from "@/components/ui/icons";
import { IconDownload } from "@/components/ui/primitives";
import { formatKstShort, formatYearMonth } from "@/lib/format";
import { NO_VALUE } from "@/lib/period";
import { printFitOnePage } from "@/lib/printPage";

/**
 * 화면 머리말 오른쪽 도구 — 기준월 · 최종 분석 시각(새로고침) · 화면별 버튼(내보내기 · 변경 이력).
 * 기준월은 서버가 정한 값이라 바꿀 수 없으므로 선택 상자처럼 보이지 않게 글자로만 둔다.
 */
export function AsOfTools({ children }: { children?: ReactNode }) {
  const { menu, generatedAt } = useSession();
  const router = useRouter();
  const [pending, start] = useTransition();
  // 기준월 · 최종 분석 시각은 서버가 준 값만 쓴다 — 없으면 '–' (하드코딩 없음 · Phase I)
  const asOf = menu?.asOf ?? "";
  const at = generatedAt;
  return (
    <>
      <span className="inline-flex items-center gap-1.5 text-[14px] font-bold text-ink-deep">
        <IconCalendar className="text-steel" />
        {asOf ? `${formatYearMonth(asOf)} 기준` : `기준일 ${NO_VALUE}`}
      </span>
      {at ? (
        <span className="inline-flex items-center gap-1.5 text-[12px] text-steel tnum">
          최종 분석 {formatKstShort(at)}
          <button
            type="button"
            onClick={() => start(() => router.refresh())}
            aria-label="화면 데이터 새로고침"
            title="새로고침"
            className="inline-flex h-6 w-6 items-center justify-center rounded-md text-steel hover:bg-surface-soft hover:text-ink-deep"
          >
            <IconRefresh className={clsx(pending && "animate-spin")} />
          </button>
        </span>
      ) : null}
      {children}
    </>
  );
}

/** 보조 도구 단추 — 고스트 (도구 모음, hover neutral/50) */
export function ToolButton({ onClick, icon, children, ...rest }: { onClick?: () => void; icon?: ReactNode; children: ReactNode; "data-tool"?: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      {...rest}
      className="inline-flex h-9 items-center gap-1.5 rounded-md px-2.5 text-[14px] font-medium text-ink-deep transition-colors hover:bg-surface-soft no-print"
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
