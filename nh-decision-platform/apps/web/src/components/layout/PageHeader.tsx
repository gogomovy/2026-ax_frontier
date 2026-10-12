import type { ReactNode } from "react";
import { Breadcrumbs } from "@/components/ui/Layout";

export interface Crumb {
  label: string;
  href?: string;
}

/**
 * 화면 머리말.
 * 경로(선택) · 단계 표시(선택) · 제목 · 한 줄 설명 · 우측 액션, 그 아래 화면 내부 탭(children).
 * 기준일·데이터 성격은 셸에서 고지하므로 여기서는 반복하지 않는다.
 */
export function PageHeader({
  crumbs,
  eyebrow,
  title,
  description,
  actions,
  children,
}: {
  crumbs?: Crumb[];
  eyebrow?: string;
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <div className="shell pb-lg pt-xl">
      {/* 위치 표시 — 관리자 화면과 같은 구성 요소 (C.9 · UX-21) */}
      {crumbs && crumbs.length > 0 ? <Breadcrumbs items={crumbs} className="mb-2.5" /> : null}

      <div className="flex flex-wrap items-end justify-between gap-base">
        <div className="min-w-0">
          {eyebrow ? <p className="mb-1 text-[12px] font-bold text-primary">{eyebrow}</p> : null}
          <h1 className="text-[26px] font-bold leading-tight text-ink-deep">{title}</h1>
          {description ? (
            <p className="mt-1.5 max-w-[760px] text-[13.5px] leading-relaxed text-steel">{description}</p>
          ) : null}
        </div>
        {actions ? <div className="flex shrink-0 flex-wrap items-center gap-xs">{actions}</div> : null}
      </div>

      {children ? <div className="mt-lg">{children}</div> : null}
    </div>
  );
}
