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
  const Icon = ICON[scope.kind];
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
        <Icon size={14} className={active ? "text-primary" : "text-icon"} />
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

/**
 * 업무 영역 전환 — 종기부 · 사업부서 · 영업점(이름은 관리자 [화면 설정 › 업무 영역]).
 * 관리자는 영역을 모두 볼 수 있으므로 드롭다운 대신 한눈에 보이는 분할 컨트롤로 둔다.
 * 단위(부서 · 지점)가 둘 이상인 칸은 눌러서 단위를 고른다 — 화면이 아직 없는 부서는 '준비 중'.
 * 선택한 칸은 흰 바탕 + 상단 보라 라인 + Bold (가이드의 박스 탭 선택 표현), 칸 사이는 부드럽게 미끄러진다.
 */
export function ScopeSwitcher({ scopes, currentId, admin }: { scopes: Scope[]; currentId: string | null; admin?: boolean }) {
  const n = scopes.length;
  const index = Math.max(0, scopes.findIndex((s) => s.id === currentId));
  return (
    <nav
      aria-label="업무 영역 전환"
      title={admin ? "관리자는 모든 업무 영역을 볼 수 있어요" : undefined}
      className="relative inline-grid rounded-lg border border-hairline-soft bg-surface-soft p-[3px]"
      style={{ gridTemplateColumns: `repeat(${n}, minmax(max-content, 1fr))` }}
    >
      <span
        aria-hidden="true"
        className="pointer-events-none absolute inset-y-[3px] left-[3px] overflow-hidden rounded-md border border-hairline bg-canvas transition-transform duration-200 ease-out motion-reduce:transition-none"
        style={{ width: `calc((100% - 6px) / ${n})`, transform: `translateX(${index * 100}%)` }}
      >
        <span className="absolute inset-x-0 top-0 h-[2px] bg-primary" />
      </span>
      {scopes.map((s) => {
        const on = s.id === currentId;
        const Icon = ICON[s.kind];
        if (s.units.length > 1) return <UnitMenu key={s.id} scope={s} active={on} />;
        return (
          <Link
            key={s.id}
            href={s.home}
            onClick={() => rememberScope(s.id)}
            aria-current={on ? "true" : undefined}
            title={s.orgName}
            className={clsx(
              "relative z-10 flex h-8 items-center justify-center gap-1.5 whitespace-nowrap rounded-md px-2 text-[13px] transition-colors xl:px-3.5",
              on ? "font-bold text-ink-deep" : "font-medium text-steel hover:text-ink-deep",
            )}
          >
            <Icon size={14} className={on ? "text-primary" : "text-icon"} />
            {s.label}
          </Link>
        );
      })}
    </nav>
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
  const Icon = ICON[scope.kind];
  if (scope.units.length > 1) {
    return (
      <div className="rounded-lg border border-hairline-soft bg-surface-soft p-[3px]">
        <UnitMenu scope={scope} active />
      </div>
    );
  }
  return (
    <span className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-hairline-soft bg-surface-soft px-3 text-[13px] font-medium text-ink-deep" title="내 업무 영역">
      <Icon size={14} className="text-primary" />
      {scope.orgName}
    </span>
  );
}
