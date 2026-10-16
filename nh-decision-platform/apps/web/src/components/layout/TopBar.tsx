"use client";

import Link from "next/link";
import clsx from "clsx";
import { IconChevronLeft, IconGear } from "@/components/ui/icons";
import { IconMenu } from "@/components/ui/primitives";
import { activeHref, type NavItem } from "@/lib/nav";
import { ICON_BUTTON, NotificationBell, ReferenceDbMenu, UserMenu } from "./HeaderMenus";
import { NaviBrand } from "./NaviBrand";
import { OrgChip, ScopeSwitcher } from "./ScopeSwitcher";
import { officeHrefOf, type NavModel } from "./nav-model";


/** 서비스 브랜드 — 어느 화면(업무 · 관리자 · 모바일 서랍)이든 NH NAVI 로고 하나만 쓴다 */
export function Brand({ href = "/" }: { href?: string; compact?: boolean }) {
  return <NaviBrand href={href} />;
}

/** 단계 링크 — 번호 원 + 이름. 선택하면 원이 보라로 채워지고 이름이 Bold (가이드 G04 헤더 단계) */
export function StepLink({ item, href, active }: { item: NavItem; href: string; active: boolean }) {
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={clsx("group flex shrink-0 items-center gap-2 py-2 text-[14px] transition-colors", active ? "font-bold text-ink-deep" : "font-medium text-steel hover:text-ink-deep")}
    >
      {item.step ? (
        <span
          aria-hidden="true"
          className={clsx(
            "flex h-[22px] w-[22px] shrink-0 items-center justify-center rounded-circle text-[12px] font-bold transition-colors",
            active ? "bg-ink-deep text-white" : "bg-track text-steel group-hover:bg-hairline-soft",
          )}
        >
          {item.step}
        </span>
      ) : null}
      <span className="whitespace-nowrap">{item.label}</span>
    </Link>
  );
}

/** 단계 · 참고 · 관리 — 현재 업무 영역의 흐름 */
export function PrimaryNav({ model, className }: { model: NavModel; className?: string }) {
  const hrefOf = officeHrefOf(model);
  const scope = model.current;
  const flow = scope?.flow ?? [];
  // 참고 메뉴는 우측 DB 아이콘(ReferenceDbMenu)으로 옮겼으므로, 단계 활성 계산도 참고를 포함해 기존과 동일하게 유지한다.
  const reference = [...(scope?.reference ?? []), ...model.sharedReference].filter((i) => i.href !== "/knowledge");
  const flowActive = activeHref([...flow, ...reference], model.pathname);

  return (
    <nav aria-label="업무 단계" className={clsx("items-center gap-4 xl:gap-7", className)}>
      {flow.map((item) => (
        <StepLink
          key={item.href}
          item={item}
          href={hrefOf(item)}
          active={item.href === flowActive}
        />
      ))}
    </nav>
  );
}

/** 관리 — 눌러서 관리자 영역(별도 화면)으로 들어간다. 관리자 영역 셸에서만 쓰인다(업무 영역 헤더는 스코프 드롭다운의 '관리자' 항목으로 들어간다). */
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
  const hrefOf = officeHrefOf(model);
  const scope = model.current;
  const home = adminShell ? "/admin" : (scope?.home ?? "/");
  const multi = model.scopes.length > 1;
  const flow = scope?.flow ?? [];
  const flowActive = activeHref(flow, model.pathname);
  const knowledgeOn = model.pathname.startsWith("/knowledge");
  // 참고 화면(데이터베이스 제외) — 우측 DB 아이콘 팝오버로 보여 준다. 활성 계산은 기존 PrimaryNav 로직 그대로.
  const reference = [...(scope?.reference ?? []), ...model.sharedReference].filter((i) => i.href !== "/knowledge");
  const refActive = activeHref([...flow, ...reference], model.pathname);

  return (
    <header className="sticky top-0 z-30 border-b border-hairline-soft bg-canvas no-print">
      <div className="shell flex h-header items-center gap-4 lg:gap-6">
        <button type="button" onClick={onOpenMenu} aria-label="메뉴 열기" className={clsx(ICON_BUTTON, "lg:hidden")}>
          <IconMenu />
        </button>
        <Brand href={home} />

        {/* 관리자 영역은 가운데 단계 메뉴 대신 '업무 화면' 바로가기를 둔다(오른쪽 영역 드롭다운으로도 돌아갈 수 있다).
            업무 화면이 하나도 없으면(관리자가 모든 업무 화면을 끈 경우) 화면 권한으로 안내한다 */}
        {adminShell ? (
          scope ? (
            <Link
              href={scope.home}
              data-to-business
              className="hidden h-9 items-center gap-1 rounded-lg px-2.5 text-[14px] font-medium text-steel transition-colors hover:bg-surface-soft hover:text-ink-deep lg:inline-flex"
            >
              <IconChevronLeft />
              업무 화면
            </Link>
          ) : (
            <Link
              href="/admin/screens"
              title="켜진 업무 화면이 없습니다 — [화면 권한]에서 화면을 켜세요"
              data-no-business-screens
              className="hidden h-9 items-center gap-1 rounded-lg px-2.5 text-[14px] font-medium text-attention transition-colors hover:bg-surface-soft lg:inline-flex"
            >
              업무 화면 없음
            </Link>
          )
        ) : flow.length < 2 ? null : (
          // 단계가 하나뿐인 영역(영업본부 · 시안 386:2)은 단계 메뉴를 그리지 않는다
          <PrimaryNav model={model} className="hidden lg:flex" />
        )}

        {/* 모든 화면 같은 순서: 참고(DB 아이콘) → 알림 벨 → 영역 드롭다운 → 사용자 */}
        <div className="ml-auto flex items-center gap-2 lg:gap-3">
          <ReferenceDbMenu items={reference} activeHref={refActive} hrefOf={hrefOf} knowledgeHref={model.knowledgeHref} knowledgeOn={knowledgeOn} />
          <NotificationBell model={model} />
          {scope ? (
            <div className="hidden lg:block">
              {multi || model.user?.isAdmin ? <ScopeSwitcher scopes={model.scopes} currentId={adminShell ? null : scope.id} admin={model.user?.isAdmin} inAdmin={model.inAdmin} /> : <OrgChip scope={scope} />}
            </div>
          ) : null}
          <UserMenu model={model} />
        </div>
      </div>

      {/* 좁은 화면 — 단계 줄 (가로 스크롤). 단계가 하나뿐이면 두지 않는다 */}
      {!adminShell && flow.length > 1 ? (
        <nav aria-label="업무 단계" className="border-t border-hairline-soft lg:hidden">
          <div className="shell no-scrollbar flex gap-6 overflow-x-auto py-1">
            {flow.map((item) => (
              <StepLink
                key={item.href}
                item={item}
                href={hrefOf(item)}
                active={item.href === flowActive}
              />
            ))}
          </div>
        </nav>
      ) : null}
    </header>
  );
}
