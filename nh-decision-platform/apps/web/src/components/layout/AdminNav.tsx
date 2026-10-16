"use client";

import Link from "next/link";
import clsx from "clsx";
import { useState } from "react";
import { IconChevronDown } from "@/components/ui/icons";
import { currentHref, type CountKey, type NavModel } from "./nav-model";

/**
 * 관리자 사이드바 — 상단 [관리] 메뉴로 들어온 관리자 영역의 왼쪽 메뉴 (가이드 후속 작업: 공통 헤더 + 좌측 사이드바).
 * 묶음은 접을 수 있고, 처리 대기 건수는 접혀 있어도 묶음 이름 옆에 보인다.
 * 선택한 화면은 배경 대신 왼쪽 보라 라인 + Bold + 옅은 선택 배경 (가이드 규칙 01).
 */
export function AdminNav({ model, onNavigate }: { model: NavModel; onNavigate?: () => void }) {
  const [closed, setClosed] = useState<Record<string, boolean>>({});
  const current = currentHref(
    model.adminGroups.flatMap((g) => g.items),
    model.pathname,
  );
  const countOf = (key?: CountKey) => (key ? model.counts[key] : 0);

  return (
    <div className="flex h-full flex-col">
      <div className="px-5 pb-3 pt-6">
        <p className="text-[16px] font-bold text-ink-deep">관리자 콘솔</p>
        <p className="mt-1 text-[12px] leading-normal text-steel">사용자 · 데이터 · AI · 운영을 관리해요</p>
      </div>
      <nav aria-label="관리자 메뉴" className="flex-1 overflow-y-auto px-3 pb-6">
        {model.adminGroups.map((g) => {
          const single = g.items.length === 1;
          const open = single || !closed[g.label];
          const total = g.items.reduce((n, i) => n + countOf(i.countKey), 0);
          const id = `admin-nav-${g.label.replace(/[^0-9A-Za-z가-힣]+/g, "-")}`;
          return (
            <div key={g.label} className="mt-3 first:mt-1">
              {single ? null : (
                <button
                  type="button"
                  aria-expanded={open}
                  aria-controls={id}
                  onClick={() => setClosed((c) => ({ ...c, [g.label]: open }))}
                  className="flex w-full items-center gap-1.5 rounded-md px-2 py-1.5 text-left text-[12px] font-bold text-steel hover:bg-surface-soft"
                >
                  <span className="flex-1">{g.label}</span>
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
