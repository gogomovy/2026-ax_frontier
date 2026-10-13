"use client";

import Link from "next/link";
import clsx from "clsx";
import { IconBriefcase, IconBuilding, IconLayers, IconTarget } from "@/components/ui/icons";
import { rememberScope, type Scope, type ScopeKind } from "./nav-model";

const ICON: Record<ScopeKind, (p: { className?: string; size?: number }) => React.ReactElement> = {
  hq: IconTarget,
  dept: IconBriefcase,
  branch: IconBuilding,
  other: IconLayers,
};

/**
 * 업무 영역 전환 — 종기부 · 사업부서 · 영업점.
 * 관리자는 세 영역을 모두 볼 수 있으므로 드롭다운 대신 한눈에 보이는 분할 컨트롤로 둔다.
 * 선택한 칸은 흰 바탕 + 상단 보라 라인 + Bold (가이드의 박스 탭 선택 표현), 칸 사이는 부드럽게 미끄러진다.
 * 칸마다 주소가 있는 링크라서 새 탭으로 열 수도 있고, 마지막으로 본 영역을 기억한다.
 */
export function ScopeSwitcher({ scopes, currentId, admin }: { scopes: Scope[]; currentId: string | null; admin?: boolean }) {
  const n = scopes.length;
  const index = Math.max(0, scopes.findIndex((s) => s.id === currentId));
  return (
    <nav
      aria-label="업무 영역 전환"
      title={admin ? "관리자는 모든 업무 영역을 볼 수 있어요" : undefined}
      className="relative inline-grid rounded-lg border border-hairline-soft bg-surface-soft p-[3px]"
      style={{ gridTemplateColumns: `repeat(${n}, minmax(84px, 1fr))` }}
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
        return (
          <Link
            key={s.id}
            href={s.home}
            onClick={() => rememberScope(s.id)}
            aria-current={on ? "true" : undefined}
            title={s.orgName}
            className={clsx(
              "relative z-10 flex h-8 items-center justify-center gap-1.5 whitespace-nowrap rounded-md px-2.5 text-[13px] transition-colors",
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

/** 모바일 메뉴용 — 세로 목록. 실제 조직 이름도 함께 보여 준다 */
export function ScopeList({ scopes, currentId }: { scopes: Scope[]; currentId: string | null }) {
  return (
    <nav aria-label="업무 영역 전환" className="flex flex-col gap-1.5">
      {scopes.map((s) => {
        const on = s.id === currentId;
        const Icon = ICON[s.kind];
        return (
          <Link
            key={s.id}
            href={s.home}
            onClick={() => rememberScope(s.id)}
            aria-current={on ? "true" : undefined}
            className={clsx(
              "flex items-center gap-3 rounded-lg border px-3 py-2.5 transition-colors",
              on ? "border-primary bg-info-faint" : "border-hairline-soft bg-canvas hover:bg-surface-soft",
            )}
          >
            <span className={clsx("flex h-8 w-8 shrink-0 items-center justify-center rounded-md", on ? "bg-info-soft text-primary" : "bg-track text-steel")}>
              <Icon size={16} />
            </span>
            <span className="min-w-0 flex-1">
              <span className={clsx("block text-[14px]", on ? "font-bold text-ink-deep" : "font-medium text-ink")}>{s.label}</span>
              <span className="block truncate text-[12px] text-steel">{s.orgName}</span>
            </span>
          </Link>
        );
      })}
    </nav>
  );
}

/** 영역이 하나뿐인 사용자 — 전환 컨트롤 대신 현재 소속만 알려 준다 */
export function OrgChip({ scope }: { scope: Scope }) {
  const Icon = ICON[scope.kind];
  return (
    <span className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-hairline-soft bg-surface-soft px-3 text-[13px] font-medium text-ink-deep" title="내 업무 영역">
      <Icon size={14} className="text-primary" />
      {scope.orgName}
    </span>
  );
}
