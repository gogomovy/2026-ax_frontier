"use client";

import Link from "next/link";
import clsx from "clsx";
import { useCallback, useId, useRef, useState } from "react";
import { apiPost } from "@/lib/api-client";
import { useDismiss } from "@/lib/useDismiss";
import type { NavItem } from "@/lib/nav";
import { IconBell, IconChevronDown, IconLogout, IconShield } from "@/components/ui/icons";
import { IconChevron } from "@/components/ui/primitives";
import type { NavModel } from "./nav-model";

/** 헤더 오른쪽 아이콘 단추 — neutral/100 바탕 8px 사각 (목업) */
export const ICON_BUTTON =
  "relative inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-track text-ink-deep transition-colors hover:bg-hairline-soft";

/** 참고 화면 모음 — 단계 흐름에는 들어가지 않는 보조 화면 */
export function ReferenceMenu({ items, activeHref, hrefOf }: { items: NavItem[]; activeHref: string | null; hrefOf: (item: NavItem) => string }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const id = useId();
  const close = useCallback(() => setOpen(false), []);
  useDismiss(ref, open, close);
  if (!items.length) return null;
  const inside = items.some((i) => i.href === activeHref);
  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        aria-haspopup="true"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((v) => !v)}
        className={clsx(
          "inline-flex h-9 shrink-0 items-center gap-1 whitespace-nowrap rounded-lg px-2.5 text-[14px] transition-colors hover:bg-surface-soft",
          inside ? "font-bold text-primary" : "font-medium text-steel hover:text-ink-deep",
        )}
      >
        참고
        <IconChevronDown className={clsx("transition-transform", open && "rotate-180")} />
      </button>
      {open ? (
        <div id={id} className="absolute left-0 top-[calc(100%+8px)] z-50 w-[248px] animate-pop-in rounded-xl border border-hairline-soft bg-canvas p-1.5 shadow-tooltip">
          <p className="px-2.5 pb-1 pt-1.5 text-[12px] font-bold text-steel">참고 화면</p>
          <ul>
            {items.map((item) => {
              const on = item.href === activeHref;
              return (
                <li key={item.href}>
                  <Link
                    href={hrefOf(item)}
                    onClick={close}
                    aria-current={on ? "page" : undefined}
                    className={clsx(
                      "flex items-center justify-between gap-2 rounded-md px-2.5 py-2 text-[14px] hover:bg-surface-soft",
                      on ? "bg-info-faint font-bold text-ink-deep" : "font-medium text-ink",
                    )}
                  >
                    {item.label}
                    <IconChevron className="text-icon" />
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

interface Notice {
  key: string;
  label: string;
  count: number;
  href: string;
}

/**
 * 알림 목록 — 항목 · 이름은 관리자 [화면 설정 › 알림], 주소는 같은 건수 키를 가진 메뉴 화면(권한이 있을 때만) (Phase K · HC-02).
 * fallback 항목은 다른 알림이 하나도 없을 때만 보인다(예: 관리자 처리할 일 합계).
 */
export function buildNotices(model: Pick<NavModel, "counts" | "hrefByCount" | "config">): Notice[] {
  const counts = model.counts as Record<string, number>;
  const rows = model.config.notices
    .map((n) => ({ key: n.countKey, label: n.label, count: counts[n.countKey] ?? 0, href: model.hrefByCount[n.countKey], fallback: Boolean(n.fallback) }))
    .filter((n) => n.count > 0 && n.href);
  const main = rows.filter((n) => !n.fallback);
  return (main.length ? main : rows).map(({ key, label, count, href }) => ({ key, label, count, href: href as string }));
}

/** 알림 — 지금 처리해야 할 건수를 모아 보여 준다 */
export function NotificationBell({ model }: { model: NavModel }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const id = useId();
  const close = useCallback(() => setOpen(false), []);
  useDismiss(ref, open, close);
  const notices = buildNotices(model);
  const total = notices.reduce((n, x) => n + x.count, 0);
  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        aria-haspopup="true"
        aria-expanded={open}
        aria-controls={id}
        aria-label={total > 0 ? `알림 ${total}건` : "알림"}
        onClick={() => setOpen((v) => !v)}
        className={ICON_BUTTON}
      >
        <IconBell />
        {total > 0 ? <span aria-hidden="true" className="absolute right-1.5 top-1.5 h-2 w-2 rounded-circle bg-primary ring-2 ring-track" /> : null}
      </button>
      {open ? (
        <div id={id} className="absolute right-0 top-[calc(100%+8px)] z-50 w-[320px] animate-pop-in rounded-xl border border-hairline-soft bg-canvas p-1.5 shadow-tooltip">
          <p className="px-2.5 pb-1 pt-1.5 text-[14px] font-bold text-ink-deep">알림</p>
          {notices.length ? (
            <ul>
              {notices.map((n) => (
                <li key={n.key}>
                  <Link href={n.href} onClick={close} className="flex items-center gap-3 rounded-md px-2.5 py-2.5 hover:bg-surface-soft">
                    <span className="min-w-0 flex-1 text-[14px] font-medium text-ink">{n.label}</span>
                    <span className="inline-flex min-w-[24px] items-center justify-center rounded-pill bg-info-soft px-2 text-[12px] font-bold leading-[22px] text-primary tnum">{n.count}</span>
                    <IconChevron className="text-icon" />
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <p className="px-2.5 pb-3 pt-1 text-[13px] text-steel">지금 처리할 알림이 없어요.</p>
          )}
        </div>
      ) : null}
    </div>
  );
}

/** 사용자 — 이름 · 소속, 누르면 상세와 로그아웃 */
export function UserMenu({ model, compact }: { model: NavModel; compact?: boolean }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const id = useId();
  const close = useCallback(() => setOpen(false), []);
  useDismiss(ref, open, close);
  const u = model.user;
  if (!u) return null;

  const logout = async () => {
    setBusy(true);
    try {
      await apiPost("/auth/logout");
    } finally {
      // 레이아웃의 세션 데이터를 비우기 위해 전체 새로고침으로 이동한다
      // eslint-disable-next-line @next/next/no-location-assign-relative-destination
      window.location.href = "/login";
    }
  };

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        data-user-menu
        aria-haspopup="true"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2.5 rounded-lg py-1 pl-1 pr-1.5 text-left transition-colors hover:bg-surface-soft"
      >
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-circle bg-info-soft text-[14px] font-bold text-primary">{u.name.slice(0, 1)}</span>
        <span className={clsx("min-w-0 leading-tight", compact ? "hidden" : "hidden xl:block")}>
          <span className="block whitespace-nowrap text-[14px] font-bold text-ink-deep">
            {u.name} {u.position}
          </span>
          <span className="block whitespace-nowrap text-[12px] text-steel">{u.orgName}</span>
        </span>
      </button>
      {open ? (
        <div id={id} className="absolute right-0 top-[calc(100%+8px)] z-50 w-[288px] animate-pop-in rounded-xl border border-hairline-soft bg-canvas p-3 shadow-tooltip">
          <div className="flex items-center gap-3">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-circle bg-info-soft text-[16px] font-bold text-primary">{u.name.slice(0, 1)}</span>
            <div className="min-w-0">
              <p className="flex items-center gap-1.5 text-[14px] font-bold text-ink-deep">
                {u.name} {u.position}
                {u.isAdmin ? (
                  <span className="inline-flex items-center gap-0.5 rounded-pill bg-info-soft px-2 py-[1px] text-[12px] font-bold text-primary">
                    <IconShield size={12} />
                    관리자
                  </span>
                ) : null}
              </p>
              <p className="truncate text-[12px] text-steel" title={u.orgPath}>
                {u.orgPath}
              </p>
            </div>
          </div>
          {u.empNo ? <p className="mt-3 border-t border-hairline-soft pt-3 text-[12px] text-steel tnum">사번 {u.empNo}</p> : null}
          <button
            type="button"
            onClick={logout}
            disabled={busy}
            className="mt-3 flex h-9 w-full items-center justify-center gap-1.5 rounded-md border border-hairline bg-canvas text-[14px] font-bold text-ink-deep hover:bg-surface-soft disabled:opacity-60"
          >
            <IconLogout />
            로그아웃
          </button>
        </div>
      ) : null}
    </div>
  );
}
