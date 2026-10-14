"use client";

import Link from "next/link";
import clsx from "clsx";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { AssistPanel } from "@/components/assist/AssistPanel";
import { IconDb, IconGear } from "@/components/ui/icons";
import { IconClose } from "@/components/ui/primitives";
import { apiPost } from "@/lib/api-client";
import { formatDate, formatKstDateTime } from "@/lib/format";
import { activeHref } from "@/lib/nav";
import { AdminNav } from "./AdminNav";
import { Brand, TopBar } from "./TopBar";
import { ScopeList } from "./ScopeSwitcher";
import { officeHrefOf, useNavModel, type NavModel } from "./nav-model";

/** 셸 없이 그리는 화면 (로그인 · 가입 · 권한 없음) */
const BARE_PATHS = ["/login", "/signup", "/forbidden"];


/**
 * 앱 셸
 *  - 업무 영역: 공통 헤더(단계 흐름 · 영역 전환 · 관리) + 전체 폭 본문
 *  - 관리자 영역(/admin): 같은 헤더 + 왼쪽 관리자 사이드바 — 헤더의 [관리]로 들어가는 별도 화면
 * 기준일 · 분석 시각 · 데이터 성격은 셸 아래쪽에서 한 번만 고지하고 화면마다 반복하지 않는다.
 */
export function AppShell({ children }: { children: ReactNode }) {
  const model = useNavModel();
  const { pathname } = model;
  // 메뉴가 열린 주소를 기억해 두면, 다른 화면으로 이동하는 순간 저절로 닫힌다
  const [menuAt, setMenuAt] = useState<string | null>(null);
  const mobileOpen = menuAt === pathname;
  const bare = BARE_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`)) || model.bare;
  const adminShell = model.inAdmin && model.adminAvailable;

  if (bare) {
    return (
      <main id="main" className="min-h-screen bg-page">
        {children}
      </main>
    );
  }

  return (
    <div className="min-h-screen bg-page">
      <TopBar model={model} adminShell={adminShell} onOpenMenu={() => setMenuAt(pathname)} />

      {mobileOpen ? (
        <MobileMenu onClose={() => setMenuAt(null)}>
          <aside className="relative flex h-full w-[300px] max-w-[88vw] animate-slide-in-right flex-col overflow-y-auto bg-canvas shadow-popup">
            <div className="flex h-header shrink-0 items-center justify-between border-b border-hairline-soft px-5">
              <Brand compact href={adminShell ? "/admin" : (model.current?.home ?? "/")} />
              <button
                type="button"
                onClick={() => setMenuAt(null)}
                aria-label="메뉴 닫기"
                className="flex h-9 w-9 items-center justify-center rounded-lg bg-track text-ink-deep"
              >
                <IconClose />
              </button>
            </div>
            {adminShell ? <AdminNav model={model} onNavigate={() => setMenuAt(null)} /> : <DrawerBody model={model} />}
          </aside>
          <button type="button" aria-label="메뉴 닫기" tabIndex={-1} onClick={() => setMenuAt(null)} className="flex-1 bg-scrim" />
        </MobileMenu>
      ) : null}

      {adminShell ? (
        <div className="flex">
          <aside className="sticky top-[var(--header-h)] hidden h-[calc(100vh-var(--header-h))] w-[var(--admin-nav-w)] shrink-0 border-r border-hairline-soft bg-canvas lg:block no-print">
            <AdminNav model={model} />
          </aside>
          <div className="min-w-0 flex-1">
            <main id="main" className="min-h-[60vh]">
              {children}
            </main>
            <DataBasis model={model} />
          </div>
        </div>
      ) : (
        <>
          <main id="main" className="min-h-[60vh]">
            {children}
          </main>
          <DataBasis model={model} />
        </>
      )}
      {!model.bare ? <AssistPanel /> : null}
    </div>
  );
}

/** 데이터 기준 — 전 화면 공통 고지 (기준일 · 최근 계산 · 자료 성격) */
function DataBasis({ model }: { model: NavModel }) {
  const { asOf, generatedAt, dataOrigin } = model;
  return (
    <footer className="shell data-basis pb-28 pt-10">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-1.5 border-t border-hairline-soft pt-5 text-[12px] text-steel">
        <span>
          데이터 기준 <b className="font-bold text-ink-deep tnum">{formatDate(asOf) || "–"}</b>
        </span>
        {generatedAt ? (
          // KST 시각은 Intl 없이 산술로 만든다 — 서버(Node) · 브라우저 ICU 의 자정 표기 차이로 #418 (B.41)
          <span className="tnum">최근 계산 {formatKstDateTime(generatedAt)}</span>
        ) : null}
        {/* 자료 성격 — 현재 버전 자료 기준 (Phase E · NAV-05 · Q124) */}
        {dataOrigin === "simulated" || dataOrigin === "mixed" ? (
          <span className="inline-flex items-center gap-1.5 font-bold text-attention" data-data-origin={dataOrigin}>
            <span className="h-[7px] w-[7px] rounded-circle bg-attention" aria-hidden="true" />
            {dataOrigin === "mixed" ? "시뮬레이션 자료 포함" : "시뮬레이션 데이터"}
          </span>
        ) : dataOrigin === "actual" ? (
          <span className="inline-flex items-center gap-1.5 font-bold text-ink-deep" data-data-origin={dataOrigin}>
            <span className="h-[7px] w-[7px] rounded-circle bg-icon" aria-hidden="true" />
            실데이터
          </span>
        ) : null}
      </div>
    </footer>
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

/** 모바일 메뉴 본문 — 업무 영역 · 단계 · 참고 · 관리 · 사용자 */
function DrawerBody({ model }: { model: NavModel }) {
  const scope = model.current;
  const hrefOf = officeHrefOf(model);
  const reference = [...(scope?.reference ?? []), ...model.sharedReference].filter((i) => i.href !== "/knowledge");
  const items = [...(scope?.flow ?? []), ...reference];
  const active = activeHref(items, model.pathname);
  const [busy, setBusy] = useState(false);
  const logout = async () => {
    setBusy(true);
    try {
      await apiPost("/auth/logout");
    } finally {
      // eslint-disable-next-line @next/next/no-location-assign-relative-destination
      window.location.href = "/login";
    }
  };
  const u = model.user;

  return (
    <div className="flex flex-1 flex-col gap-5 px-5 py-5">
      {model.scopes.length > 1 || (model.scopes[0]?.units.length ?? 0) > 1 ? (
        <section>
          <h2 className="mb-2 text-[12px] font-bold text-steel">업무 영역</h2>
          <ScopeList scopes={model.scopes} currentId={scope?.id ?? null} />
        </section>
      ) : null}

      {scope ? (
        <section>
          <h2 className="mb-2 text-[12px] font-bold text-steel">{scope.orgName}</h2>
          <ul className="flex flex-col">
            {scope.flow.map((item) => {
              const on = item.href === active;
              const n = item.countKey ? model.counts[item.countKey] : 0;
              return (
                <li key={item.href}>
                  <Link
                    href={hrefOf(item)}
                    aria-current={on ? "page" : undefined}
                    className={clsx("flex items-center gap-3 rounded-md px-1 py-2.5 text-[14px]", on ? "font-bold text-primary" : "font-medium text-ink")}
                  >
                    <span aria-hidden="true" className={clsx("flex h-[22px] w-[22px] items-center justify-center rounded-circle text-[12px] font-bold", on ? "bg-primary text-white" : "bg-track text-steel")}>
                      {item.step}
                    </span>
                    <span className="flex-1">{item.label}</span>
                    {n > 0 ? <span className="inline-flex h-5 min-w-5 items-center justify-center rounded-circle bg-primary px-1 text-[12px] font-bold text-white tnum">{n}</span> : null}
                  </Link>
                </li>
              );
            })}
          </ul>
        </section>
      ) : null}

      {reference.length ? (
        <section>
          <h2 className="mb-2 text-[12px] font-bold text-steel">참고</h2>
          <ul className="flex flex-col">
            {reference.map((item) => (
              <li key={item.href}>
                <Link
                  href={hrefOf(item)}
                  aria-current={item.href === active ? "page" : undefined}
                  className={clsx("block rounded-md px-1 py-2.5 text-[14px]", item.href === active ? "font-bold text-primary" : "font-medium text-ink")}
                >
                  {item.label}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className="flex flex-col gap-2">
        {model.knowledgeHref ? (
          <Link href={model.knowledgeHref} className="flex h-10 items-center gap-2 rounded-md border border-hairline-soft px-3 text-[14px] font-medium text-ink">
            <IconDb size={16} className="text-steel" />
            데이터베이스
          </Link>
        ) : null}
        {model.adminAvailable ? (
          <Link href="/admin" className="flex h-10 items-center gap-2 rounded-md border border-hairline-soft px-3 text-[14px] font-bold text-primary">
            <IconGear size={16} />
            관리
          </Link>
        ) : null}
      </section>

      {u ? (
        <section className="mt-auto rounded-xl bg-surface-soft p-3">
          <p className="text-[14px] font-bold text-ink-deep">
            {u.name} {u.position}
          </p>
          <p className="text-[12px] text-steel">{u.orgPath}</p>
          <button
            type="button"
            onClick={logout}
            disabled={busy}
            className="mt-3 flex h-9 w-full items-center justify-center rounded-md border border-hairline bg-canvas text-[14px] font-bold text-ink-deep disabled:opacity-60"
          >
            로그아웃
          </button>
        </section>
      ) : null}
    </div>
  );
}
