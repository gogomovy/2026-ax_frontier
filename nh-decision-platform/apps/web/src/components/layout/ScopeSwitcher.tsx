"use client";

import Link from "next/link";
import clsx from "clsx";
import { useCallback, useId, useRef, useState } from "react";
import { IconBriefcase, IconBuilding, IconChevronDown, IconLayers, IconTarget } from "@/components/ui/icons";
import { IconCheck } from "@/components/ui/primitives";
import { useDismiss } from "@/lib/useDismiss";
import { rememberScope, type Scope, type ScopeKind, type ScopeUnit } from "./nav-model";

const ICON: Record<ScopeKind, (p: { className?: string; size?: number }) => React.ReactElement> = {
  hq: IconTarget,
  dept: IconBriefcase,
  branch: IconBuilding,
  other: IconLayers,
};

/** 단위 링크 — 지점은 주소 인자(?office=)가 바뀌므로 전체 이동(a), 부서는 화면 이동(Link). 준비 중이면 고를 수 없다 */
function UnitLink({ scope, unit, on, onPick, className, children }: { scope: Scope; unit: ScopeUnit; on: boolean; onPick?: () => void; className: string; children: React.ReactNode }) {
  if (!unit.available || !unit.home) {
    return (
      <span aria-disabled="true" className={clsx(className, "cursor-not-allowed opacity-60")}>
        {children}
      </span>
    );
  }
  const pick = () => {
    rememberScope(scope.id);
    onPick?.();
  };
  return unit.office ? (
    <a href={unit.home} onClick={pick} aria-current={on ? "true" : undefined} className={className}>
      {children}
    </a>
  ) : (
    <Link href={unit.home} onClick={pick} aria-current={on ? "true" : undefined} className={className}>
      {children}
    </Link>
  );
}

/** 영역 칸의 단위 메뉴 — 사업부서 · 지점이 둘 이상일 때 (Phase K · SCP-02 · SCP-03) */
function UnitMenu({ scope, active }: { scope: Scope; active: boolean }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const id = useId();
  const close = useCallback(() => setOpen(false), []);
  useDismiss(ref, open, close);
  const noun = scope.kind === "branch" ? "지점" : "부서";
  return (
    <div ref={ref} className="relative z-10">
      <button
        type="button"
        aria-haspopup="true"
        aria-expanded={open}
        aria-controls={id}
        aria-current={active ? "true" : undefined}
        title={`${scope.label} — ${scope.orgName}`}
        onClick={() => setOpen((v) => !v)}
        data-scope-menu={scope.kind}
        className={clsx(
          "flex h-8 w-full items-center justify-center gap-1.5 whitespace-nowrap rounded-md px-2 text-[13px] transition-colors xl:px-3.5",
          active ? "font-bold text-ink-deep" : "font-medium text-steel hover:text-ink-deep",
        )}
      >
        {scope.label}
        {active ? <span className="hidden max-w-[120px] truncate font-medium text-steel 2xl:inline">· {scope.orgName}</span> : null}
        <IconChevronDown className={clsx("transition-transform", open && "rotate-180")} />
      </button>
      {open ? (
        <div id={id} className="absolute right-0 top-[calc(100%+8px)] z-50 w-[248px] animate-pop-in rounded-xl border border-hairline-soft bg-canvas p-1.5 shadow-tooltip">
          <p className="px-2.5 pb-1 pt-1.5 text-[12px] font-bold text-steel">
            {scope.label} · {noun} {scope.units.length}곳
          </p>
          <ul className="max-h-[320px] overflow-y-auto">
            {scope.units.map((u) => {
              const on = active && u.id === scope.unitId;
              return (
                <li key={u.id}>
                  <UnitLink
                    scope={scope}
                    unit={u}
                    on={on}
                    onPick={close}
                    className={clsx("flex items-center justify-between gap-2 rounded-md px-2.5 py-2 text-[14px] hover:bg-surface-soft", on ? "bg-info-faint font-bold text-ink-deep" : "font-medium text-ink")}
                  >
                    <span className="min-w-0 truncate">{u.name}</span>
                    {on ? <IconCheck className="shrink-0 text-primary" /> : !u.available ? <span className="shrink-0 text-[12px] text-steel">준비 중</span> : null}
                  </UnitLink>
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

/** 드롭다운 안의 영역 한 줄 — 영역마다 한 줄, 누르면 그 영역 첫 화면으로 바로 이동한다.
 *  하위 부서 · 지점 목록은 펼치지 않는다(사용자는 로그인한 소속으로 자동 연결 · 관리자는 영역 첫 화면으로). */
function ScopeRow({ scope, active, onPick }: { scope: Scope; active: boolean; onPick: () => void }) {
  return (
    <li>
      <Link
        href={scope.home}
        onClick={() => {
          rememberScope(scope.id);
          onPick();
        }}
        aria-current={active ? "true" : undefined}
        title={scope.orgName}
        className={clsx(
          "flex w-full items-center gap-2 rounded-md px-2.5 py-2 text-left text-[14px] hover:bg-surface-soft",
          active ? "bg-info-faint font-bold text-ink-deep" : "font-medium text-ink",
        )}
      >
        <span className="min-w-0 flex-1 truncate">{scope.label}</span>
        {active ? <IconCheck className="shrink-0 text-primary" /> : null}
      </Link>
    </li>
  );
}

/**
 * 업무 영역 전환 — 종기부(종합기획부) · 사업부서 · 영업점(이름은 관리자 [화면 설정 › 업무 영역]).
 * 피그마 시안대로 세그먼트 분할 대신 단일 드롭다운('종합기획부 ▾')으로 둔다 — 버튼은 현재 영역 라벨, 눌러서 전체 목록에서 전환.
 * 단위(부서 · 지점)가 둘 이상인 영역은 목록 아래에 단위를 펼쳐 고른다 — 화면이 아직 없는 부서는 '준비 중'.
 * 관리자(admin)면 목록 아래 구분선 뒤에 '관리자' 항목을 둔다.
 */
export function ScopeSwitcher({ scopes, currentId, admin, inAdmin }: { scopes: Scope[]; currentId: string | null; admin?: boolean; inAdmin?: boolean }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const id = useId();
  const close = useCallback(() => setOpen(false), []);
  useDismiss(ref, open, close);
  const current = scopes.find((s) => s.id === currentId) ?? scopes[0] ?? null;
  // 관리자 영역에 있을 때는 버튼에 '관리자'를 보여 준다(같은 드롭다운으로 업무 영역에 돌아간다)
  const label = admin && inAdmin ? "관리자" : (current?.label ?? "업무 영역");
  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        aria-haspopup="true"
        aria-expanded={open}
        aria-controls={id}
        title={current ? `${label} — ${current.orgName}` : "업무 영역 전환"}
        onClick={() => setOpen((v) => !v)}
        className="inline-flex h-9 shrink-0 items-center gap-1 whitespace-nowrap rounded-lg border border-hairline-soft bg-surface-soft px-2.5 text-[13px] font-bold text-ink-deep transition-colors hover:bg-track"
      >
        {label}
        <IconChevronDown className={clsx("text-icon transition-transform", open && "rotate-180")} />
      </button>
      {open ? (
        <div id={id} className="absolute right-0 top-[calc(100%+8px)] z-50 w-[180px] animate-pop-in rounded-xl border border-hairline-soft bg-canvas p-1.5 shadow-tooltip">
          <ul>
            {scopes.map((s) => (
              <ScopeRow key={s.id} scope={s} active={s.id === currentId} onPick={close} />
            ))}
          </ul>
          {admin ? (
            <>
              <span aria-hidden="true" className="my-1 block h-px bg-hairline-soft" />
              <Link
                href="/admin"
                onClick={close}
                aria-current={inAdmin ? "page" : undefined}
                className={clsx(
                  "flex items-center gap-2 rounded-md px-2.5 py-2 text-[14px] hover:bg-surface-soft",
                  inAdmin ? "bg-info-faint font-bold text-ink-deep" : "font-medium text-ink",
                )}
              >
                관리자
              </Link>
            </>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

/** 모바일 메뉴용 — 세로 목록. 단위가 둘 이상이면 영역 아래에 단위를 펼쳐 보여 준다 */
export function ScopeList({ scopes, currentId }: { scopes: Scope[]; currentId: string | null }) {
  return (
    <nav aria-label="업무 영역 전환" className="flex flex-col gap-1.5">
      {scopes.map((s) => {
        const on = s.id === currentId;
        const Icon = ICON[s.kind];
        const head = (
          <>
            <span className={clsx("flex h-8 w-8 shrink-0 items-center justify-center rounded-md", on ? "bg-info-soft text-primary" : "bg-track text-steel")}>
              <Icon size={16} />
            </span>
            <span className="min-w-0 flex-1">
              <span className={clsx("block text-[14px]", on ? "font-bold text-ink-deep" : "font-medium text-ink")}>{s.label}</span>
              <span className="block truncate text-[12px] text-steel">{s.orgName}</span>
            </span>
          </>
        );
        const box = clsx("flex items-center gap-3 rounded-lg border px-3 py-2.5 transition-colors", on ? "border-primary bg-info-faint" : "border-hairline-soft bg-canvas hover:bg-surface-soft");
        if (s.units.length <= 1) {
          return (
            <Link key={s.id} href={s.home} onClick={() => rememberScope(s.id)} aria-current={on ? "true" : undefined} className={box}>
              {head}
            </Link>
          );
        }
        return (
          <div key={s.id} className={clsx(box, "flex-col items-stretch")}>
            <div className="flex items-center gap-3">{head}</div>
            <ul className="mt-1 flex flex-col gap-0.5 pl-11">
              {s.units.map((u) => {
                const uon = on && u.id === s.unitId;
                return (
                  <li key={u.id}>
                    <UnitLink scope={s} unit={u} on={uon} className={clsx("flex items-center justify-between gap-2 rounded-md px-2 py-1.5 text-[13px] hover:bg-surface-soft", uon ? "font-bold text-ink-deep" : "text-ink")}>
                      <span className="min-w-0 truncate">{u.name}</span>
                      {uon ? <IconCheck className="shrink-0 text-primary" /> : !u.available ? <span className="shrink-0 text-[12px] text-steel">준비 중</span> : null}
                    </UnitLink>
                  </li>
                );
              })}
            </ul>
          </div>
        );
      })}
    </nav>
  );
}

/** 영역이 하나뿐인 사용자 — 전환 컨트롤 대신 현재 소속만 알려 준다. 단위(지점)가 둘 이상이면 단위 메뉴 */
export function OrgChip({ scope }: { scope: Scope }) {
  // 사용자 결정: 헤더 영역 칸에는 아이콘을 두지 않는다 (관리자 · 모든 계정 동일)
  if (scope.units.length > 1) {
    return (
      <div className="rounded-lg border border-hairline-soft bg-surface-soft p-[3px]">
        <UnitMenu scope={scope} active />
      </div>
    );
  }
  return (
    <span className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-hairline-soft bg-surface-soft px-3 text-[13px] font-medium text-ink-deep" title="내 업무 영역">
      {scope.orgName}
    </span>
  );
}
