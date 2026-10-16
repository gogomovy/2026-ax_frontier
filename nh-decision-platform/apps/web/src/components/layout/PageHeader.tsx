import type { ReactNode } from "react";
import { Breadcrumbs } from "@/components/ui/Layout";

export interface Crumb {
  label: string;
  href?: string;
}

/**
 * 화면 머리말 (가이드 G02): 페이지 제목 24px Bold · 우측 도구(기준월 · 최종 분석 · 내보내기), 그 아래 하위 탭.
 * 경로(선택) · 단계 표시(선택) · 제목 · 한 줄 설명 · 우측 액션, 그 아래 화면 내부 탭(children).
 * 기준일 · 데이터 성격은 셸에서 고지하므로 여기서는 반복하지 않는다.
 */
export function PageHeader({
  crumbs,
  eyebrow,
  title,
  description,
  actions,
  children,
  compact,
}: {
  crumbs?: Crumb[];
  eyebrow?: string;
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
  /** 1 · 2 · 3단계 화면 머리말 — 제목 22px, 위 여백 20px(현황·목표 제목 줄과 같은 크기 · 위치) */
  compact?: boolean;
}) {
  const titleCls = compact ? "text-[22px] font-bold leading-[1.25] text-ink-deep" : "text-[24px] font-bold leading-[1.25] text-ink-deep";
  return (
    <div className={compact ? "shell pb-4 pt-5" : "shell pb-5 pt-8"}>
      {/* 위치 표시 — 관리자 화면과 같은 구성 요소 (C.9 · UX-21) */}
      {crumbs && crumbs.length > 0 ? <Breadcrumbs items={crumbs} className="mb-2.5" /> : null}

      <div className="flex flex-wrap items-center justify-between gap-x-base gap-y-3">
        <div className="min-w-0">
          {eyebrow ? <p className="mb-1 text-[12px] font-bold text-primary">{eyebrow}</p> : null}
          {typeof title === "string" ? (
            <h1 className={titleCls}>{title}</h1>
          ) : (
            // 제목 안에 부문 선택 같은 조작 요소가 들어가면 제목 역할만 붙인다
            <div role="heading" aria-level={1} className={titleCls}>
              {title}
            </div>
          )}
          {description ? <p className="mt-1.5 max-w-[760px] text-[14px] leading-normal text-steel">{description}</p> : null}
        </div>
        {actions ? <div className="flex min-w-0 flex-wrap items-center gap-x-4 gap-y-1 sm:gap-x-md">{actions}</div> : null}
      </div>

      {children ? <div className={compact ? "mt-4" : "mt-5"}>{children}</div> : null}
    </div>
  );
}
