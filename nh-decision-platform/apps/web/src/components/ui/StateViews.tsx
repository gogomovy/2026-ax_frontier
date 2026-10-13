"use client";

import type { ReactNode } from "react";
import clsx from "clsx";
import { IconAlertCircle, IconInbox, IconRefresh } from "@/components/ui/icons";
import { Button, IconChevron } from "@/components/ui/primitives";

/**
 * 상태 화면 (가이드 G06) — 화면 전체가 아니라 카드 · 차트 영역 단위로 보여 준다. 다른 영역은 정상적으로 쓸 수 있다.
 *  - 로딩: 실제 레이아웃과 같은 자리에 neutral/100 블록. 2초가 넘으면 안내 문구.
 *  - 데이터 없음: 아이콘 + 이유 + 다음 행동 버튼 1개.
 *  - 오류: danger 아이콘 + 안내 + 다시 시도(메인) + 오류 코드 · 시각.
 */
const SHELL = "flex flex-col items-center justify-center rounded-xl border border-hairline-soft bg-canvas px-6 py-10 text-center";

export function LoadingCard({ label = "데이터를 불러오는 중이에요", className }: { label?: string; className?: string }) {
  return (
    <div className={clsx("rounded-xl border border-hairline-soft bg-canvas p-6", className)} role="status" aria-live="polite" aria-busy="true">
      <div className="skeleton h-4 w-32" />
      <div className="mt-5 flex items-end gap-6">
        <div className="skeleton h-[80px] w-[140px] rounded-t-full" />
        <div className="flex-1 space-y-2.5">
          <div className="skeleton h-7 w-40" />
          <div className="skeleton h-3 w-full" />
          <div className="skeleton h-3 w-4/5" />
        </div>
      </div>
      <div className="mt-6 flex h-[72px] items-end gap-2" aria-hidden="true">
        {[40, 62, 48, 80, 58, 90, 70, 100].map((h, i) => (
          <div key={i} className="skeleton flex-1" style={{ height: `${h}%` }} />
        ))}
      </div>
      <p className="mt-4 flex items-center gap-1.5 text-[12px] text-steel">
        <IconRefresh className="animate-spin" />
        {label}
      </p>
    </div>
  );
}

export function EmptyCard({
  title,
  description,
  actionLabel,
  onAction,
  href,
  className,
}: {
  title: string;
  description?: ReactNode;
  actionLabel?: string;
  onAction?: () => void;
  href?: string;
  className?: string;
}) {
  return (
    <div className={clsx(SHELL, className)}>
      <span className="flex h-14 w-14 items-center justify-center rounded-circle bg-track text-steel">
        <IconInbox />
      </span>
      <p className="mt-5 text-[16px] font-bold text-ink-deep">{title}</p>
      {description ? <p className="mt-2 max-w-[360px] text-[14px] leading-normal text-steel">{description}</p> : null}
      {actionLabel ? (
        href ? (
          <a href={href} className="mt-5 inline-flex h-10 items-center gap-0.5 rounded-md border border-hairline bg-canvas px-4 text-[14px] font-bold text-ink-deep hover:bg-surface-soft">
            {actionLabel}
            <IconChevron />
          </a>
        ) : (
          <Button variant="ghost" onClick={onAction} className="mt-5">
            {actionLabel}
            <IconChevron />
          </Button>
        )
      ) : null}
    </div>
  );
}

export function ErrorCard({
  title = "데이터를 불러오지 못했어요",
  description = "잠시 후 다시 시도해 주세요. 문제가 계속되면 관리자에게 아래 오류 코드를 알려주세요.",
  code,
  at,
  onRetry,
  className,
}: {
  title?: string;
  description?: ReactNode;
  code?: string;
  at?: string;
  onRetry?: () => void;
  className?: string;
}) {
  return (
    <div className={clsx(SHELL, className)} role="alert">
      <span className="flex h-14 w-14 items-center justify-center rounded-circle bg-critical-soft text-critical">
        <IconAlertCircle />
      </span>
      <p className="mt-5 text-[16px] font-bold text-ink-deep">{title}</p>
      <p className="mt-2 max-w-[400px] text-[14px] leading-normal text-steel">{description}</p>
      {onRetry ? (
        <Button onClick={onRetry} className="mt-5">
          <IconRefresh />
          다시 시도
        </Button>
      ) : null}
      {code ? (
        <p className="mt-4 text-[12px] text-steel tnum">
          오류 코드 {code}
          {at ? ` · ${at}` : ""}
        </p>
      ) : null}
    </div>
  );
}
