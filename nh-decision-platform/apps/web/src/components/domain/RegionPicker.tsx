"use client";

import Link from "next/link";
import clsx from "clsx";
import { useCallback, useId, useRef, useState } from "react";
import { IconChevronDown } from "@/components/ui/icons";
import { useDismiss } from "@/lib/useDismiss";
import type { RegionKpi } from "@/lib/types";

/**
 * 제목 안 지역본부 이름 (시안 386:45) — 볼 수 있는 지역이 둘 이상(관리자)이면 눌러서 지역을 고른다.
 * 지역본부 직원은 자기 지역 하나라 이름 글자만 보인다(꺾쇠 없음).
 * 사용자 결정: 드롭다운 현재 항목에는 체크 표시를 두지 않는다 (바탕 · 굵기로만 표시).
 */
export function RegionPicker({ data }: { data: RegionKpi }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLSpanElement>(null);
  const id = useId();
  const close = useCallback(() => setOpen(false), []);
  useDismiss(box, open, close);
  const name = data.region?.name ?? "영업본부";
  if (data.regions.length < 2) return <span className="text-primary-deep">{name}</span>;

  return (
    <span ref={box} className="relative inline-flex">
      <button
        type="button"
        aria-haspopup="true"
        aria-expanded={open}
        aria-controls={id}
        aria-label={`지역본부 선택 — 지금 ${name}`}
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-1 rounded-md text-primary-deep focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
      >
        {name}
        <IconChevronDown size={12} className={clsx("mt-[3px] transition-transform", open && "rotate-180")} />
      </button>
      {open ? (
        <div id={id} className="absolute left-0 top-[calc(100%+8px)] z-50 w-[220px] animate-pop-in rounded-xl border border-hairline-soft bg-canvas p-1.5 shadow-tooltip">
          <p className="px-2.5 pb-1 pt-1.5 text-[12px] font-bold text-steel">지역본부 {data.regions.length}곳</p>
          <ul className="max-h-[320px] overflow-y-auto">
            {data.regions.map((r) => {
              const on = r.code === data.region?.code;
              return (
                <li key={r.code}>
                  <Link
                    href={`/region?region=${encodeURIComponent(r.code)}`}
                    onClick={close}
                    aria-current={on ? "true" : undefined}
                    className={clsx(
                      "flex items-center rounded-md px-2.5 py-2 text-[14px] leading-[1.4] hover:bg-surface-soft focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary",
                      on ? "bg-info-faint font-bold text-ink-deep" : "font-medium text-ink",
                    )}
                  >
                    <span className="min-w-0 truncate">{r.name}</span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}
    </span>
  );
}
