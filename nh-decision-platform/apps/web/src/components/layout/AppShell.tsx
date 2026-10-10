"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";
import clsx from "clsx";
import { AssistPanel } from "@/components/assist/AssistPanel";
import { useGoalState } from "@/components/providers/GoalStateProvider";
import { usePlanState } from "@/components/providers/PlanStateProvider";
import { useSession, type MenuPayload } from "@/components/providers/SessionProvider";
import { apiPost } from "@/lib/api-client";
import { API_MODE } from "@/lib/config";
import { IconChevron, IconClose, IconMenu } from "@/components/ui/primitives";
import { formatDate } from "@/lib/format";
import { PERSONAS, isActive, personaOfPath, type NavItem } from "@/lib/nav";
import type { Persona } from "@/lib/types";
import { PROPOSALS } from "@/mock/goals";
import { AS_OF, GENERATED_AT } from "@/mock/helpers";
import { BRANCH_TABS } from "@/mock/branch";
import { ANALYSIS_TABS } from "@/mock/risk";

const PERSONA_KEY = "nhdip.persona";
/** 셸 없이 그리는 화면 (로그인 · 가입 · 권한 없음) */
const BARE_PATHS = ["/login", "/signup", "/forbidden"];

interface NavGroupSpec {
  label: string;
  items: NavItem[];
  withCounts?: boolean;
}

/** 서버 메뉴 → 사이드바 그룹 (부서 섹션마다 업무 흐름 / 참고) */
function groupsFromMenu(menu: MenuPayload): NavGroupSpec[] {
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
      out.push({ label: multi || sec.admin ? sec.section : sec.flow.length > 1 ? "업무 흐름" : "업무", items: sec.flow.map(toItem), withCounts: true });
    }
    if (sec.reference.length) {
      out.push({ label: sec.admin ? sec.section : sec.section === "공통" || !multi ? "참고" : `${sec.section} · 참고`, items: sec.reference.map(toItem) });
    }
  }
  // 같은 이름의 그룹(예: 부서 참고 + 공통 참고)은 하나로 합친다
  const merged: NavGroupSpec[] = [];
  for (const g of out) {
    const same = merged.find((m) => m.label === g.label);
    if (same) same.items = [...same.items, ...g.items];
    else merged.push({ ...g, items: [...g.items] });
  }
  return merged;
}

/**
 * 앱 셸 — 좌측 사이드바(데스크톱) / 상단 바 + 드로어(모바일).
 * 기준일·분석 시각·데이터 성격은 셸에서 한 번만 고지하고 화면마다 반복하지 않는다.
 */
export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname() ?? "/";
  const [persona, setPersona] = useState<Persona>("P1");
  const [mobileOpen, setMobileOpen] = useState(false);
  const { menu } = useSession();
  const bare = BARE_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`)) || (API_MODE && !menu);

  /* 전용 화면이면 경로로, 공용 화면(데이터베이스 등)이면 직전 페르소나를 유지 */
  useEffect(() => {
    const fromPath = personaOfPath(pathname);
    if (fromPath) {
      // 목데이터 모드 전용 페르소나 — localStorage 는 마운트 후에만 읽을 수 있어 effect 에서 동기화한다
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setPersona(fromPath);
      window.localStorage.setItem(PERSONA_KEY, fromPath);
    } else {
      const saved = window.localStorage.getItem(PERSONA_KEY) as Persona | null;
      if (saved && PERSONAS[saved]) setPersona(saved);
    }
    setMobileOpen(false);
  }, [pathname]);

  const config = PERSONAS[persona];
  const orgLabel = API_MODE ? (menu?.user.org.name ?? "") : config.org;

  if (bare) {
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
        <SidebarBody persona={persona} pathname={pathname} />
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
        <div className="fixed inset-0 z-50 flex lg:hidden no-print">
          <aside className="relative h-full w-[280px] bg-canvas shadow-pop">
            <button
              type="button"
              onClick={() => setMobileOpen(false)}
              aria-label="메뉴 닫기"
              className="absolute right-3 top-3 flex h-9 w-9 items-center justify-center rounded-circle bg-surface-soft text-charcoal"
            >
              <IconClose />
            </button>
            <SidebarBody persona={persona} pathname={pathname} />
          </aside>
          <button
            type="button"
            aria-label="메뉴 닫기"
            onClick={() => setMobileOpen(false)}
            className="flex-1 bg-[rgba(10,19,23,0.32)]"
          />
        </div>
      ) : null}

      <div className="lg:pl-[248px]">
        <main id="main" className="pb-section">
          {children}
        </main>
      </div>
      {API_MODE && menu ? <AssistPanel /> : null}
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
        {!compact ? <span className="block text-[11px] text-stone">AI Decision Platform</span> : null}
      </span>
    </Link>
  );
}

function SidebarBody({ persona, pathname }: { persona: Persona; pathname: string }) {
  const config = PERSONAS[persona];
  const counts = useNavCounts();
  const { menu, generatedAt } = useSession();
  const groups: NavGroupSpec[] =
    API_MODE && menu
      ? groupsFromMenu(menu)
      : [
          { label: config.flow.length > 1 ? "업무 흐름" : "업무", items: config.flow, withCounts: true },
          ...(config.reference.length > 0 ? [{ label: "참고", items: config.reference }] : []),
        ];
  const asOf = API_MODE ? (menu?.asOf ?? AS_OF) : AS_OF;
  const genAt = API_MODE ? generatedAt : GENERATED_AT;

  return (
    <div className="flex h-full flex-col">
      <div className="px-lg pb-base pt-lg">
        <Brand />
      </div>

      <div className="px-md">{API_MODE && menu ? <UserCard menu={menu} /> : <PersonaSwitcher persona={persona} />}</div>

      <nav aria-label="주요 메뉴" className="mt-lg flex-1 overflow-y-auto px-md">
        {groups.map((g) => (
          <NavGroup key={g.label} label={g.label}>
            {g.items.map((item) => (
              <NavLink
                key={item.href}
                item={item}
                active={isActive(item, pathname)}
                count={g.withCounts && item.countKey ? counts[item.countKey] : undefined}
              />
            ))}
          </NavGroup>
        ))}
      </nav>

      {/* 데이터 기준 — 전 화면 공통 고지 */}
      <div className="m-md rounded-xl bg-surface-soft px-base py-3">
        <p className="text-[11px] font-bold text-steel">데이터 기준</p>
        <p className="mt-1 text-[13px] font-bold text-ink-deep tnum">{formatDate(asOf)}</p>
        {genAt ? (
          <p className="mt-0.5 text-[11px] text-stone tnum">
            {API_MODE ? `최근 계산 ${formatDateTime(genAt)}` : `일배치 분석 완료 ${genAt.slice(11, 16)}`}
          </p>
        ) : null}
        <p className="mt-2 flex items-center gap-1.5 text-[11px] font-bold text-[#8a5d00]">
          <span className="h-1.5 w-1.5 rounded-circle bg-warning" aria-hidden="true" />
          시뮬레이션 데이터
        </p>
      </div>
    </div>
  );
}

function NavGroup({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="mb-lg">
      <p className="mb-1.5 px-md text-[11px] font-bold text-stone">{label}</p>
      <ul className="flex flex-col gap-0.5">{children}</ul>
    </div>
  );
}

function NavLink({ item, active, count }: { item: NavItem; active: boolean; count?: number }) {
  return (
    <li>
      <Link
        href={item.href}
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
  const proposals = API_MODE ? (menu?.counts.proposalsTotal ?? 0) : PROPOSALS.length;
  const analyses = API_MODE ? (menu?.counts.analysesTotal ?? 0) : ANALYSIS_TABS.length;
  const branchAnalyses = API_MODE ? (menu?.counts.branchAnalysesTotal ?? 0) : BRANCH_TABS.current.length;
  return {
    goalProposals: Math.max(0, proposals - Object.keys(proposalActions).length),
    analyses,
    proposedPlans: proposedPlans.length,
    branchAnalyses,
  };
}

/** 서버(UTC)와 브라우저의 시간대가 달라도 같은 문자열이 나오도록 KST 로 고정 (하이드레이션 일치) */
const KST = new Intl.DateTimeFormat("ko-KR", { timeZone: "Asia/Seoul", month: "numeric", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false });
function formatDateTime(iso: string) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return KST.format(d);
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

/** 페르소나 전환 — SSO 연동 전 개발·시연용 (AUTH-01/05 대응 시 제거) */
function PersonaSwitcher({ persona }: { persona: Persona }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const config = PERSONAS[persona];

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("mousedown", onDown);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("mousedown", onDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        className="flex w-full items-center gap-2.5 rounded-xl border border-hairline-soft px-md py-2.5 text-left"
      >
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-circle bg-surface-soft text-[12px] font-bold text-ink-deep">
          {config.user.slice(0, 1)}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[13px] font-bold text-ink-deep">
            {config.user} {config.role}
          </span>
          <span className="block truncate text-[11px] text-steel">{config.org}</span>
        </span>
        <IconChevron className={clsx("shrink-0 text-stone transition-transform", open ? "-rotate-90" : "rotate-90")} />
      </button>

      {open ? (
        <div role="menu" className="absolute left-0 right-0 top-[calc(100%+6px)] z-40 rounded-xl border border-hairline-soft bg-canvas p-1.5 shadow-pop">
          <p className="px-2.5 pb-1 pt-1.5 text-[10.5px] font-bold text-stone">사용자 전환 · 시연용</p>
          {(Object.keys(PERSONAS) as Persona[]).map((code) => {
            const p = PERSONAS[code];
            const on = code === persona;
            return (
              <button
                key={code}
                type="button"
                role="menuitemradio"
                aria-checked={on}
                onClick={() => {
                  setOpen(false);
                  window.localStorage.setItem(PERSONA_KEY, code);
                  router.push(p.home);
                }}
                className={clsx(
                  "flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left",
                  on ? "bg-surface-soft" : "",
                )}
              >
                <span className="min-w-0 flex-1">
                  <span className="block text-[12.5px] font-bold text-ink">{p.org}</span>
                  <span className="block text-[11px] text-stone">
                    {p.user} {p.role}
                  </span>
                </span>
                {on ? <span className="h-1.5 w-1.5 rounded-circle bg-primary" aria-hidden="true" /> : null}
              </button>
            );
          })}
          <p className="px-2.5 pb-1 pt-1.5 text-[10.5px] leading-snug text-stone">SSO 연동 시 권한에 따라 자동 결정됩니다.</p>
        </div>
      ) : null}
    </div>
  );
}
