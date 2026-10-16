"use client";

import Link from "next/link";
import clsx from "clsx";
import { useState } from "react";
import { IconChevronDown } from "@/components/ui/icons";
import { filterAdminGroups } from "@/lib/adminNav";
import { currentHref, type CountKey, type NavModel } from "./nav-model";

/**
 * 관리자 사이드바 — 상단 [관리] 메뉴로 들어온 관리자 영역의 왼쪽 메뉴 (가이드 후속 작업: 공통 헤더 + 좌측 사이드바).
 * 묶음 7개(업무 순서)는 지금 보는 화면이 든 묶음만 펼치고, 접힌 묶음 머리에 항목 수 · 처리 대기 건수를 보인다. 위쪽 '메뉴 찾기'로 거른다 (Phase P · ADM2).
 * 선택한 화면은 배경 대신 왼쪽 보라 라인 + Bold + 옅은 선택 배경 (가이드 규칙 01).
 */
export function AdminNav({ model, onNavigate }: { model: NavModel; onNavigate?: () => void }) {
  // 펼침 — 지금 보는 화면이 든 묶음만 기본으로 펼치고, 사용자가 누른 묶음은 그 선택을 따른다 (Phase P · ADM2-02)
  const [toggled, setToggled] = useState<Record<string, boolean>>({});
  const [query, setQuery] = useState("");
  const current = currentHref(
    model.adminGroups.flatMap((g) => g.items),
    model.pathname,
  );
  const countOf = (key?: CountKey) => (key ? model.counts[key] : 0);
  const groups = filterAdminGroups(model.adminGroups, query);
  const searching = query.trim().length > 0;

  return (
    <div className="flex h-full flex-col">
      <div className="px-5 pb-2 pt-6">
        <p className="text-[16px] font-bold text-ink-deep">관리자 콘솔</p>
        <p className="mt-1 text-[12px] leading-normal text-steel">데이터 반영 · 에이전트 · 운영 · 설정 · 사용자를 관리해요</p>
        {/* 메뉴 찾기 (ADM2-03) */}
        <label className="mt-3 block">
          <span className="sr-only">관리자 메뉴 찾기</span>
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="메뉴 찾기"
            data-admin-nav-search
            className="input !h-8 w-full text-[12.5px]"
          />
        </label>
      </div>
      <nav aria-label="관리자 메뉴" className="flex-1 overflow-y-auto px-3 pb-6">
        {searching && groups.length === 0 ? <p className="px-2 py-3 text-[12px] text-stone">맞는 메뉴가 없습니다</p> : null}
        {groups.map((g) => {
          const single = g.items.length === 1 && !searching;
          const hasCurrent = g.items.some((i) => i.href === current);
          const open = single || searching || (toggled[g.label] ?? hasCurrent);
          const total = g.items.reduce((n, i) => n + countOf(i.countKey), 0);
          const id = `admin-nav-${g.label.replace(/[^0-9A-Za-z가-힣]+/g, "-")}`;
          return (
            <div key={g.label} className="mt-3 first:mt-1">
              {single ? null : (
                <button
                  type="button"
                  aria-expanded={open}
                  aria-controls={id}
                  onClick={() => setToggled((c) => ({ ...c, [g.label]: !open }))}
                  className={clsx(
                    "flex w-full items-center gap-1.5 rounded-md px-2 py-1.5 text-left text-[12.5px] font-bold hover:bg-surface-soft",
                    hasCurrent ? "text-ink-deep" : "text-steel",
                  )}
                >
                  <span className="flex-1">{g.label}</span>
                  {!open ? <span className="text-[11px] font-medium text-stone tnum">{g.items.length}</span> : null}
                  {!open && total > 0 ? <CountPill n={total} /> : null}
                  <IconChevronDown className={clsx("text-icon transition-transform", !open && "-rotate-90")} />
                </button>
              )}
              {open ? (
                <ul id={id} className="mt-0.5 flex flex-col gap-0.5">
                  {g.items.map((item) => {
                    const on = item.href === current;
                    const n = countOf(item.countKey);
                    return (
                      <li key={item.href}>
                        <Link
                          href={item.href}
                          onClick={onNavigate}
                          aria-current={on ? "page" : undefined}
                          className={clsx(
                            "flex h-9 items-center gap-2 rounded-md px-3 text-[14px] transition-colors",
                            on
                              ? "bg-info-soft font-bold text-primary-deep"
                              : "font-medium text-charcoal hover:bg-surface-soft hover:text-ink-deep",
                          )}
                        >
                          <span className="min-w-0 flex-1 truncate">{item.label}</span>
                          {n > 0 ? <CountPill n={n} /> : null}
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              ) : null}
            </div>
          );
        })}
      </nav>
    </div>
  );
}

function CountPill({ n }: { n: number }) {
  return (
    <span className="inline-flex min-w-[20px] items-center justify-center rounded-pill bg-info-soft px-1.5 text-[12px] font-bold leading-[20px] text-primary tnum">
      {n}
      <span className="sr-only">건 처리 대기</span>
    </span>
  );
}
