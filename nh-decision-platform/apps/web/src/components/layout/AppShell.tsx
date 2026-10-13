"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useRef, useState, useSyncExternalStore, type ReactNode } from "react";
import clsx from "clsx";
import { AssistPanel } from "@/components/assist/AssistPanel";
import { useGoalState } from "@/components/providers/GoalStateProvider";
import { usePlanState } from "@/components/providers/PlanStateProvider";
import { useSession, type MenuPayload } from "@/components/providers/SessionProvider";
import { apiPost } from "@/lib/api-client";
import { navHrefWithOffice, officeFromSearch } from "@/lib/branchOffice";
import { IconChevron, IconClose, IconMenu } from "@/components/ui/primitives";
import { formatDate, formatKstDateTime } from "@/lib/format";
import { activeHref, type NavItem } from "@/lib/nav";

/** 셸 없이 그리는 화면 (로그인 · 가입 · 권한 없음) */
const BARE_PATHS = ["/login", "/signup", "/forbidden"];

interface NavGroupSpec {
  label: string;
  items: NavItem[];
  withCounts?: boolean;
  /** 관리자 묶음 — 사이드바에서 접을 수 있다(현재 화면이 든 묶음은 펼침 · C.9 · UX-21) */
  admin?: boolean;
  /** 접을 수 있는 묶음(관리자 묶음 · 관리자에게 보이는 업무 화면 묶음) */
  collapsible?: boolean;
  /** 접을 수 있어도 처음엔 펼쳐 두는 묶음(관리자 홈) */
  defaultOpen?: boolean;
}

/**
 * 서버 메뉴 → 사이드바 그룹 (부서 섹션마다 업무 흐름 / 참고).
 * 관리자(Phase E · NAV-01 · Q122) — 관리 묶음을 먼저, 업무 화면은 '업무 화면 · 부서' 접힌 묶음으로 뒤에 둔다.
 */
export function groupsFromMenu(menu: MenuPayload): NavGroupSpec[] {
  const isAdmin = menu.user.role === "admin" && menu.sections.some((s) => s.admin);
  const multi = menu.sections.filter((s) => !s.admin && s.flow.length > 0).length > 1;
  const out: NavGroupSpec[] = [];
  for (const sec of menu.sections) {
    const toItem = (i: MenuPayload["sections"][number]["flow"][number]): NavItem => ({
      label: i.label,
      href: i.href,
      match: i.match.map((m) => m.replace(/^=/, "")),
      step: i.step ?? undefined,
      countKey: i.countKey ?? undefined,
      exact: i.match.some((m) => m.startsWith("=")),
    });
    if (sec.flow.length) {
      out.push({ label: multi || sec.admin ? sec.section : sec.flow.length > 1 ? "업무 흐름" : "업무", items: sec.flow.map(toItem), withCounts: true, admin: sec.admin });
    }
    if (sec.reference.length) {
      out.push({ label: sec.admin ? sec.section : sec.section === "공통" || !multi ? "참고" : `${sec.section} · 참고`, items: sec.reference.map(toItem), admin: sec.admin });
    }
  }
  // 같은 이름의 그룹(예: 부서 참고 + 공통 참고)은 하나로 합친다
  const merged: NavGroupSpec[] = [];
  for (const g of out) {
    const same = merged.find((m) => m.label === g.label);
    if (same) same.items = [...same.items, ...g.items];
    else merged.push({ ...g, items: [...g.items] });
  }
  if (!isAdmin) return merged.map((g) => ({ ...g, collapsible: g.admin }));
  const adminGroups = merged.filter((g) => g.admin).map((g) => ({ ...g, withCounts: true, collapsible: g.items.length > 1, defaultOpen: g.items.length === 1 }));
  const bizGroups = merged.filter((g) => !g.admin).map((g) => ({ ...g, label: `업무 화면 · ${g.label}`, collapsible: true }));
  return [...adminGroups, ...bizGroups];
}

/**
 * 앱 셸 — 좌측 사이드바(데스크톱) / 상단 바 + 드로어(모바일).
 * 메뉴 · 기준일 · 데이터 성격은 모두 서버 메뉴(`GET /me/menu`)에서 온다 — 로그인 전(메뉴 없음)엔 셸 없이 그린다.
 * 기준일·분석 시각·데이터 성격은 셸에서 한 번만 고지하고 화면마다 반복하지 않는다.
 */
export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname() ?? "/";
  const [mobileOpen, setMobileOpen] = useState(false);
  const { menu } = useSession();
  const bare = BARE_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`));

  /* 화면을 옮기면 모바일 메뉴를 닫는다 */
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setMobileOpen(false);
  }, [pathname]);

  const orgLabel = menu?.user.org.name ?? "";
  const closeMenu = useCallback(() => setMobileOpen(false), []);

  if (bare || !menu) {
    return (
      <main id="main" className="min-h-screen bg-canvas">
        {children}
      </main>
    );
  }

  return (
    <div className="min-h-screen bg-canvas">
      {/* 데스크톱 사이드바 */}
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-[248px] border-r border-hairline-soft bg-canvas lg:block no-print">
        <SidebarBody menu={menu} pathname={pathname} />
      </aside>

      {/* 모바일 상단 바 */}
      <header className="sticky top-0 z-30 flex h-14 items-center gap-md border-b border-hairline-soft bg-canvas/95 px-base backdrop-blur lg:hidden no-print">
        <button
          type="button"
          onClick={() => setMobileOpen(true)}
          aria-label="메뉴 열기"
          className="flex h-9 w-9 items-center justify-center rounded-circle bg-surface-soft text-ink"
        >
          <IconMenu />
        </button>
        <Brand compact />
        <span className="ml-auto truncate text-[12px] text-steel">{orgLabel}</span>
      </header>

      {mobileOpen ? (
        <MobileMenu onClose={closeMenu}>
          <aside className="relative h-full w-[280px] overflow-y-auto bg-canvas shadow-pop">
            <button
              type="button"
              onClick={() => setMobileOpen(false)}
              aria-label="메뉴 닫기"
              className="absolute right-3 top-3 flex h-9 w-9 items-center justify-center rounded-circle bg-surface-soft text-charcoal"
            >
              <IconClose />
            </button>
            <SidebarBody menu={menu} pathname={pathname} />
          </aside>
          <button
            type="button"
            aria-label="메뉴 닫기"
            tabIndex={-1}
            onClick={() => setMobileOpen(false)}
            className="flex-1 bg-scrim"
          />
        </MobileMenu>
      ) : null}

      <div className="lg:pl-[248px]">
        {/* 아래 여백 — 떠 있는 [질문하기] 단추가 마지막 내용을 가리지 않게 (Phase E · LAY-01) */}
        <main id="main" className="pb-32">
          {children}
        </main>
      </div>
      <AssistPanel />
    </div>
  );
}

/** 모바일 메뉴 — 대화상자(포커스 가두기 · Esc 닫기 · 닫으면 여는 버튼으로 포커스 복귀) (C.1 · UX-21) */
function MobileMenu({ onClose, children }: { onClose: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    const root = ref.current;
    const focusables = () => (root ? [...root.querySelectorAll<HTMLElement>('a[href], button:not([disabled]):not([tabindex="-1"]), select, input, [tabindex="0"]')] : []);
    focusables()[0]?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
        return;
      }
      if (e.key !== "Tab") return;
      const list = focusables();
      if (!list.length) return;
      const first = list[0];
      const last = list[list.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      opener?.focus?.();
    };
  }, [onClose]);
  return (
    <div ref={ref} role="dialog" aria-modal="true" aria-label="주요 메뉴" className="fixed inset-0 z-50 flex lg:hidden no-print">
      {children}
    </div>
  );
}

function Brand({ compact }: { compact?: boolean }) {
  return (
    <Link href="/" className="flex items-center gap-2.5">
      <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-ink-deep text-[12px] font-bold text-white">
        NH
      </span>
      <span className={clsx("leading-tight", compact && "hidden sm:block")}>
        <span className="block text-[13.5px] font-bold text-ink-deep">경영 의사결정</span>
        {!compact ? <span className="block text-[11px] text-stone">AI 의사결정 지원</span> : null}
      </span>
    </Link>
  );
}

function SidebarBody({ menu, pathname }: { menu: MenuPayload; pathname: string }) {
  const counts = useNavCounts();
  const { generatedAt } = useSession();
  const groups: NavGroupSpec[] = groupsFromMenu(menu);
  // 기준일 · 계산 시각 — 업로드 자료가 없으면 '–'
  const asOf = formatDate(menu.asOf ?? "") || "–";
  // 영업점 화면에서 고른 지점(?office=, B.47) — 사이드바 이동에도 유지. 서버 렌더 · 하이드레이션은 인자 없이(같은 글자) 그리고 그 뒤 주소에서 읽는다
  const search = useSyncExternalStore(subscribeLocation, readSearch, emptySearch);
  const office = pathname.startsWith("/branch") ? officeFromSearch(search) : null;
  // 관리자 묶음 접기 — 기본은 현재 화면이 든 묶음만 펼침(관리자 화면이 아니면 모두 접힘), 사용자가 누른 상태가 우선
  const [toggled, setToggled] = useState<Record<string, boolean>>({});
  // 현재 위치는 메뉴 전체에서 가장 길게 일치하는 하나 (Phase E · NAV-03)
  const current = activeHref(groups.flatMap((g) => g.items), pathname);
  const inside = (g: NavGroupSpec) => g.items.some((item) => item.href === current);
  const isOpen = (g: NavGroupSpec) => !g.collapsible || (toggled[g.label] ?? (Boolean(g.defaultOpen) || inside(g)));
  const origin = menu.dataOrigin ?? "simulated";

  return (
    <div className="flex h-full flex-col">
      <div className="px-lg pb-base pt-lg">
        <Brand />
      </div>

      <div className="px-md">
        <UserCard menu={menu} />
      </div>

      <nav aria-label="주요 메뉴" className="mt-lg flex-1 overflow-y-auto px-md">
        {groups.map((g) => (
          <NavGroup
            key={g.label}
            label={g.label}
            collapsible={Boolean(g.collapsible)}
            open={isOpen(g)}
            onToggle={() => setToggled((t) => ({ ...t, [g.label]: !isOpen(g) }))}
            activeInside={inside(g)}
            count={g.collapsible && g.withCounts ? g.items.reduce((n, item) => n + (item.countKey && item.countKey !== "adminTodo" ? counts[item.countKey] ?? 0 : 0), 0) : undefined}
          >
            {g.items.map((item) => (
              <NavLink
                key={item.href}
                item={item}
                href={navHrefWithOffice(item.href, office)}
                active={item.href === current}
                count={g.withCounts && item.countKey ? counts[item.countKey] : undefined}
              />
            ))}
          </NavGroup>
        ))}
      </nav>

      {/* 데이터 기준 — 전 화면 공통 고지 */}
      <div className="m-md rounded-xl bg-surface-soft px-base py-3">
        <p className="text-[11px] font-bold text-steel">데이터 기준</p>
        <p className="mt-1 text-[13px] font-bold text-ink-deep tnum">{asOf}</p>
        {generatedAt ? (
          <p className="mt-0.5 text-[11px] text-stone tnum">
            {/* KST 시각은 Intl 없이 산술로 만든다 — 서버(Node) · 브라우저 ICU 의 자정 표기 차이로 #418 (B.41) */}
            {`최근 계산 ${formatKstDateTime(generatedAt)}`}
          </p>
        ) : null}
        {/* 자료 성격 — 현재 버전 자료 기준 (Phase E · NAV-05 · Q124) */}
        {origin === "simulated" || origin === "mixed" ? (
          <p className="mt-2 flex items-center gap-1.5 text-[11px] font-bold text-attention" data-data-origin={origin}>
            <span className="h-1.5 w-1.5 rounded-circle bg-warning" aria-hidden="true" />
            {origin === "mixed" ? "시뮬레이션 자료 포함" : "시뮬레이션 데이터"}
          </p>
        ) : origin === "actual" ? (
          <p className="mt-2 flex items-center gap-1.5 text-[11px] font-bold text-success" data-data-origin={origin}>
            <span className="h-1.5 w-1.5 rounded-circle bg-success" aria-hidden="true" />
            실데이터
          </p>
        ) : null}
      </div>
    </div>
  );
}

function NavGroup({ label, children, collapsible, open = true, onToggle, activeInside, count }: { label: string; children: ReactNode; collapsible?: boolean; open?: boolean; onToggle?: () => void; activeInside?: boolean; count?: number }) {
  const id = `nav-${label.replace(/[^0-9A-Za-z가-힣]+/g, "-")}`;
  if (!collapsible) {
    return (
      <div className="mb-lg">
        <p className="mb-1.5 px-md text-[11px] font-bold text-stone">{label}</p>
        <ul className="flex flex-col gap-0.5">{children}</ul>
      </div>
    );
  }
  return (
    <div className="mb-xs">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={id}
        onClick={onToggle}
        className="flex w-full items-center gap-1.5 rounded-lg px-md py-1.5 text-left text-[11.5px] font-bold text-steel hover:bg-surface-soft"
      >
        <IconChevron className={clsx("h-3 w-3 transition-transform", open && "rotate-90")} />
        <span className="flex-1">{label}</span>
        {/* 접혀 있을 때도 처리할 건수가 보이게 (Phase E · NAV-02) */}
        {!open && count ? (
          <span className="min-w-[20px] rounded-pill bg-primary px-1.5 py-0.5 text-center text-[10.5px] font-bold text-white tnum">
            {count}
            <span className="sr-only">건 처리 대기</span>
          </span>
        ) : null}
        {activeInside && !open ? <span aria-hidden="true" className="h-1.5 w-1.5 rounded-circle bg-primary" /> : null}
      </button>
      {open ? (
        <ul id={id} className="mb-md mt-0.5 flex flex-col gap-0.5">
          {children}
        </ul>
      ) : null}
    </div>
  );
}

function subscribeLocation(onChange: () => void) {
  window.addEventListener("popstate", onChange);
  return () => window.removeEventListener("popstate", onChange);
}
const readSearch = () => window.location.search;
const emptySearch = () => "";

function NavLink({ item, href, active, count }: { item: NavItem; href: string; active: boolean; count?: number }) {
  return (
    <li>
      <Link
        href={href}
        aria-current={active ? "page" : undefined}
        className={clsx(
          "flex items-center gap-2.5 rounded-xl px-md py-2.5 text-[13.5px] transition-colors",
          active ? "bg-ink-deep font-bold text-white" : "font-medium text-charcoal",
        )}
      >
        {item.step ? (
          <span
            className={clsx(
              "flex h-5 w-5 shrink-0 items-center justify-center rounded-circle text-[10.5px] font-bold",
              active ? "bg-white/20 text-white" : "bg-surface-soft text-steel",
            )}
          >
            {item.step}
          </span>
        ) : (
          <span className={clsx("ml-1.5 mr-0.5 h-1.5 w-1.5 shrink-0 rounded-circle", active ? "bg-white" : "bg-hairline")} />
        )}
        <span className="min-w-0 flex-1 truncate">{item.label}</span>
        {count ? (
          <span
            className={clsx(
              "min-w-[20px] rounded-pill px-1.5 py-0.5 text-center text-[10.5px] font-bold tnum",
              active ? "bg-white/20 text-white" : "bg-primary text-white",
            )}
          >
            {count}
          </span>
        ) : null}
      </Link>
    </li>
  );
}

/** 사이드바 건수 — 사용자가 처리해야 할 항목만 센다 */
function useNavCounts(): Record<NonNullable<NavItem["countKey"]>, number> {
  const { proposalActions } = useGoalState();
  const { proposedPlans } = usePlanState();
  const { menu } = useSession();
  // 건수는 서버 메뉴(counts)에서만 — 없으면 0
  const c: Record<string, number> = menu?.counts ?? {};
  const proposals = c.proposalsTotal ?? 0;
  const analyses = c.analysesTotal ?? 0;
  const branchAnalyses = c.branchAnalysesTotal ?? 0;
  return {
    goalProposals: Math.max(0, proposals - Object.keys(proposalActions).length),
    analyses,
    proposedPlans: proposedPlans.length,
    branchAnalyses,
    // 관리자 처리 건수 — 서버가 관리자에게만 계산 (Phase E · NAV-02)
    adminTodo: c.adminTodo ?? 0,
    adminUsers: c.adminUsers ?? 0,
    adminUploads: c.adminUploads ?? 0,
    adminAnalyses: c.adminAnalyses ?? 0,
  };
}

/** 로그인 사용자 — 이름 · 직급 · 소속(부 > 국 > 팀) · 로그아웃 */
function UserCard({ menu }: { menu: MenuPayload }) {
  const u = menu.user;
  const [busy, setBusy] = useState(false);
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
    <div className="rounded-xl border border-hairline-soft px-md py-2.5">
      <div className="flex items-center gap-2.5">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-circle bg-surface-soft text-[12px] font-bold text-ink-deep">
          {u.name.slice(0, 1)}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[13px] font-bold text-ink-deep">
            {u.name} {u.position ?? ""}
            {u.role === "admin" ? <span className="ml-1 rounded-pill bg-ink-deep px-1.5 py-0.5 text-[9.5px] text-white">관리자</span> : null}
          </span>
          <span className="block truncate text-[11px] text-steel" title={u.orgPath.map((o) => o.name).join(" > ")}>
            {u.orgPath.map((o) => o.name).join(" > ")}
          </span>
        </span>
      </div>
      <div className="mt-2 flex items-center justify-between text-[11px]">
        <span className="text-stone tnum">사번 {u.empNo}</span>
        <button type="button" onClick={logout} disabled={busy} className="font-bold text-steel underline-offset-2 hover:underline">
          로그아웃
        </button>
      </div>
    </div>
  );
}
