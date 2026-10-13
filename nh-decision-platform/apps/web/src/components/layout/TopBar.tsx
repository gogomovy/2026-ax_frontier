"use client";

import Link from "next/link";
import clsx from "clsx";
import { useSyncExternalStore } from "react";
import { IconChevronLeft, IconDb, IconGear } from "@/components/ui/icons";
import { IconMenu } from "@/components/ui/primitives";
import { navHrefWithOffice, officeFromSearch } from "@/lib/branchOffice";
import { activeHref, type NavItem } from "@/lib/nav";
import { ICON_BUTTON, NotificationBell, ReferenceMenu, UserMenu } from "./HeaderMenus";
import { OrgChip, ScopeSwitcher } from "./ScopeSwitcher";
import type { NavModel } from "./nav-model";

/** 영업점 화면에서 고른 지점(?office=)을 단계 이동에도 유지 — 서버 렌더 · 하이드레이션은 인자 없이 그린 뒤 주소에서 읽는다 */
function subscribeLocation(onChange: () => void) {
  window.addEventListener("popstate", onChange);
  return () => window.removeEventListener("popstate", onChange);
}
const readSearch = () => window.location.search;
const emptySearch = () => "";

export function Brand({ href = "/", compact }: { href?: string; compact?: boolean }) {
  return (
    <Link href={href} className="flex shrink-0 items-center gap-2.5" aria-label="AI 경영 의사결정 플랫폼 홈">
      <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-ink-deep text-[12px] font-bold text-white">NH</span>
      <span className={clsx("whitespace-nowrap text-[15px] font-bold text-ink-deep", compact ? "hidden sm:block" : "hidden xl:block")}>AI 경영 의사결정 플랫폼</span>
    </Link>
  );
}

/** 단계 링크 — 번호 원 + 이름. 선택하면 원이 보라로 채워지고 이름이 Bold (가이드 G04 헤더 단계) */
export function StepLink({ item, href, active, count }: { item: NavItem; href: string; active: boolean; count?: number }) {
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={clsx("group flex shrink-0 items-center gap-2 py-2 text-[14px] transition-colors", active ? "font-bold text-primary" : "font-medium text-steel hover:text-ink-deep")}
    >
      {item.step ? (
        <span
          aria-hidden="true"
          className={clsx(
            "flex h-[22px] w-[22px] shrink-0 items-center justify-center rounded-circle text-[12px] font-bold transition-colors",
            active ? "bg-primary text-white" : "bg-track text-steel group-hover:bg-hairline-soft",
          )}
        >
          {item.step}
        </span>
      ) : null}
      <span className="whitespace-nowrap">{item.label}</span>
      {count ? (
        <span className="inline-flex h-5 min-w-5 items-center justify-center rounded-circle bg-primary px-1 text-[12px] font-bold leading-none text-white tnum">
          {count}
          <span className="sr-only">건 검토 필요</span>
        </span>
      ) : null}
    </Link>
  );
}

/** 단계 · 참고 · 관리 — 현재 업무 영역의 흐름 */
export function PrimaryNav({ model, className }: { model: NavModel; className?: string }) {
  const search = useSyncExternalStore(subscribeLocation, readSearch, emptySearch);
  const scope = model.current;
  const office = model.pathname.startsWith("/branch") ? officeFromSearch(search) : null;
  const flow = scope?.flow ?? [];
  const reference = [...(scope?.reference ?? []), ...model.sharedReference].filter((i) => i.href !== "/knowledge");
  const refActive = activeHref([...flow, ...reference], model.pathname);

  return (
    <nav aria-label="업무 단계" className={clsx("items-center gap-4 xl:gap-7", className)}>
      {flow.map((item) => (
        <StepLink
          key={item.href}
          item={item}
          href={navHrefWithOffice(item.href, office)}
          active={item.href === refActive}
          count={item.countKey ? model.counts[item.countKey] : undefined}
        />
      ))}
      <ReferenceMenu items={reference} activeHref={refActive} hrefOf={(i) => navHrefWithOffice(i.href, office)} />
      {model.adminAvailable ? (
        <>
          <span aria-hidden="true" className="h-5 w-px bg-hairline-soft" />
          <AdminLink active={model.inAdmin} />
        </>
      ) : null}
    </nav>
  );
}

/** 관리 — 눌러서 관리자 영역(별도 화면)으로 들어간다 */
export function AdminLink({ active }: { active: boolean }) {
  return (
    <Link
      href="/admin"
      aria-current={active ? "page" : undefined}
      className={clsx("group flex shrink-0 items-center gap-2 py-2 text-[14px] transition-colors", active ? "font-bold text-primary" : "font-medium text-steel hover:text-ink-deep")}
    >
      <span
        aria-hidden="true"
        className={clsx(
          "flex h-[22px] w-[22px] shrink-0 items-center justify-center rounded-circle transition-colors",
          active ? "bg-primary text-white" : "bg-track text-steel group-hover:bg-hairline-soft",
        )}
      >
        <IconGear size={13} />
      </span>
      관리
    </Link>
  );
}

/**
 * 공통 헤더 — 업무 영역에서는 단계 흐름 + 영역 전환, 관리자 영역에서는 "업무 화면으로" + 관리 표시.
 * 좁은 화면(<lg)에서는 메뉴 단추 + 단계 줄로 줄어든다.
 */
export function TopBar({ model, adminShell, onOpenMenu }: { model: NavModel; adminShell: boolean; onOpenMenu: () => void }) {
  const search = useSyncExternalStore(subscribeLocation, readSearch, emptySearch);
  const scope = model.current;
  const home = adminShell ? "/admin" : (scope?.home ?? "/");
  const multi = model.scopes.length > 1;
  const office = model.pathname.startsWith("/branch") ? officeFromSearch(search) : null;
  const flow = scope?.flow ?? [];
  const flowActive = activeHref(flow, model.pathname);
  const knowledgeOn = model.pathname.startsWith("/knowledge");

  return (
    <header className="sticky top-0 z-30 border-b border-hairline-soft bg-canvas no-print">
      <div className="shell flex h-header items-center gap-4 lg:gap-6">
        <button type="button" onClick={onOpenMenu} aria-label="메뉴 열기" className={clsx(ICON_BUTTON, "lg:hidden")}>
          <IconMenu />
        </button>
        <Brand href={home} />

        {adminShell ? (
          <div className="hidden items-center gap-5 lg:flex">
            <Link href={scope?.home ?? "/"} className="inline-flex h-9 items-center gap-1 rounded-lg px-2.5 text-[14px] font-medium text-steel transition-colors hover:bg-surface-soft hover:text-ink-deep">
              <IconChevronLeft />
              업무 화면
            </Link>
            <span aria-hidden="true" className="h-5 w-px bg-hairline-soft" />
            <AdminLink active />
          </div>
        ) : (
          <PrimaryNav model={model} className="hidden lg:flex" />
        )}

        <div className="ml-auto flex items-center gap-2 lg:gap-3">
          {!adminShell && scope ? (
            <div className="hidden lg:block">{multi ? <ScopeSwitcher scopes={model.scopes} currentId={scope.id} admin={model.user?.isAdmin} /> : <OrgChip scope={scope} />}</div>
          ) : null}
          {!adminShell && model.knowledgeHref ? (
            <Link
              href={model.knowledgeHref}
              aria-label="데이터베이스"
              title="데이터베이스"
              aria-current={knowledgeOn ? "page" : undefined}
              className={clsx(ICON_BUTTON, "hidden sm:inline-flex", knowledgeOn && "!bg-info-soft !text-primary")}
            >
              <IconDb />
            </Link>
          ) : null}
          <NotificationBell model={model} />
          <UserMenu model={model} />
        </div>
      </div>

      {/* 좁은 화면 — 단계 줄 (가로 스크롤) */}
      {!adminShell && flow.length ? (
        <nav aria-label="업무 단계" className="border-t border-hairline-soft lg:hidden">
          <div className="shell no-scrollbar flex gap-6 overflow-x-auto py-1">
            {flow.map((item) => (
              <StepLink
                key={item.href}
                item={item}
                href={navHrefWithOffice(item.href, office)}
                active={item.href === flowActive}
                count={item.countKey ? model.counts[item.countKey] : undefined}
              />
            ))}
          </div>
        </nav>
      ) : null}
    </header>
  );
}
