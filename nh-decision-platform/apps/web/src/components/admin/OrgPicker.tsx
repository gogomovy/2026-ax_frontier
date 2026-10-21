"use client";

import clsx from "clsx";
import { useEffect, useId, useLayoutEffect, useRef, useState, type KeyboardEvent, type RefObject } from "react";
import { createPortal } from "react-dom";
import { IconChevronDown, IconSearch } from "@/components/ui/icons";
import { api } from "@/lib/api-client";
import { orgLookupPath, orgOptionText, type OrgOption } from "@/lib/orgLookup";

/**
 * 검색형 조직 선택 상자 — 인사 동기화(.dat)로 조직이 수천 곳이 되어도 멈추지 않게, 전체 목록을 그리지 않고
 * 서버 검색(/admin/orgs/lookup)으로 맞는 조직 30곳까지만 보여 준다. 표 안에 여러 개 있어도 닫혀 있을 때는 단추 하나뿐이다.
 * - 열면 검색칸에 바로 입력 · ↑↓ 이동 · Enter 선택 · Esc 닫기(콤보박스 + 목록 상자 패턴)
 * - 목록은 문서 맨 위(body)에 그려 표 · 카드의 넘침 자르기에 잘리지 않는다
 * - types: 고를 수 있는 조직 유형 · exclude: 그 조직과 하위 제외 · empty: 맨 위 '없음' 선택지 문구
 */
export function OrgPicker({
  value,
  onChange,
  label,
  ariaLabel,
  valueLabel,
  types,
  exclude,
  empty,
  placeholder = "조직 선택",
  includeInactive,
  disabled,
  className,
}: {
  value: string | null | undefined;
  onChange: (code: string, org: OrgOption | null) => void;
  label?: string;
  ariaLabel?: string;
  /** 현재 값의 이름을 이미 알면 넘긴다(따로 조회하지 않음) */
  valueLabel?: string;
  types?: string[];
  exclude?: string;
  empty?: string;
  placeholder?: string;
  includeInactive?: boolean;
  disabled?: boolean;
  className?: string;
}) {
  const uid = useId();
  const trigger = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false);
  const shown = useResolvedName(value || "", valueLabel);
  const text = value ? shown : (empty ?? placeholder);
  const name = label ?? ariaLabel ?? "조직";

  const close = (focusBack: boolean) => {
    setOpen(false);
    if (focusBack) trigger.current?.focus();
  };

  return (
    <div className={clsx("block", className)}>
      {label ? (
        <span id={`${uid}-label`} className="mb-1 block text-[11.5px] font-bold text-steel">
          {label}
        </span>
      ) : null}
      <button
        ref={trigger}
        type="button"
        disabled={disabled}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={label ? undefined : `${name}: ${text}`}
        aria-labelledby={label ? `${uid}-label ${uid}-value` : undefined}
        data-org-picker={value || ""}
        onClick={() => setOpen((v) => !v)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown" && !open) {
            e.preventDefault();
            setOpen(true);
          }
        }}
        className={clsx("input flex !h-9 items-center justify-between gap-xs text-left text-[13px]", disabled ? "cursor-not-allowed opacity-60" : "cursor-pointer")}
      >
        <span id={`${uid}-value`} className={clsx("min-w-0 truncate", !value && "text-steel")} title={text}>
          {text}
        </span>
        <IconChevronDown className="shrink-0 text-steel" />
      </button>
      {open ? (
        <OrgPopover
          anchor={trigger}
          name={name}
          value={value || ""}
          types={types}
          exclude={exclude}
          empty={empty}
          includeInactive={includeInactive}
          onPick={(code, org) => {
            close(true);
            if (code !== (value || "")) onChange(code, org);
          }}
          onClose={close}
        />
      ) : null}
    </div>
  );
}

/* ── 현재 값 이름 — 같은 순간에 뜬 상자들의 코드를 모아 한 번에 조회, 결과는 화면 전체가 같이 쓴다 ───────── */
const names = new Map<string, string>();
const waiting = new Map<string, ((name: string) => void)[]>();
let flushTimer: number | null = null;

function flush() {
  flushTimer = null;
  const codes = Array.from(waiting.keys()).slice(0, 100);
  const subs = codes.map((c) => [c, waiting.get(c) ?? []] as const);
  codes.forEach((c) => waiting.delete(c));
  if (waiting.size) flushTimer = window.setTimeout(flush, 0);
  api<{ items: OrgOption[] }>(orgLookupPath({ codes, inactive: true, limit: codes.length }))
    .then((r) => r.items.forEach((o) => names.set(o.code, o.name)))
    .catch(() => undefined)
    .finally(() => subs.forEach(([c, fns]) => fns.forEach((fn) => fn(names.get(c) ?? c))));
}

function resolveName(code: string, done: (name: string) => void) {
  const known = names.get(code);
  if (known) return done(known);
  waiting.set(code, [...(waiting.get(code) ?? []), done]);
  if (flushTimer === null) flushTimer = window.setTimeout(flush, 0);
}

/** 조직 이름을 바꾸거나 옮긴 뒤 — 기억해 둔 이름을 비운다 */
export function forgetOrgNames() {
  names.clear();
}

function useResolvedName(code: string, known?: string) {
  const [fetched, setFetched] = useState<{ code: string; name: string } | null>(null);
  useEffect(() => {
    if (!code || known) return;
    let alive = true;
    resolveName(code, (name) => alive && setFetched({ code, name }));
    return () => {
      alive = false;
    };
  }, [code, known]);
  if (!code) return "";
  if (known) return known;
  return fetched?.code === code ? fetched.name : (names.get(code) ?? code);
}

/* ── 떠 있는 검색 목록 ─────────────────────────────────────── */
const WIDTH = 360;
const LIMIT = 30;

function OrgPopover({
  anchor,
  name,
  value,
  types,
  exclude,
  empty,
  includeInactive,
  onPick,
  onClose,
}: {
  anchor: RefObject<HTMLButtonElement | null>;
  name: string;
  value: string;
  types?: string[];
  exclude?: string;
  empty?: string;
  includeInactive?: boolean;
  onPick: (code: string, org: OrgOption | null) => void;
  onClose: (focusBack: boolean) => void;
}) {
  const uid = useId();
  const box = useRef<HTMLDivElement>(null);
  const list = useRef<HTMLUListElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const [pos, setPos] = useState<{ left: number; top: number; width: number } | null>(null);
  const [q, setQ] = useState("");
  const [res, setRes] = useState<{ key: string; items: OrgOption[]; total: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [active, setActive] = useState(0);
  const typeKey = (types ?? []).join(",");
  const key = `${q.trim()}|${typeKey}|${exclude ?? ""}|${includeInactive ? 1 : 0}`;

  // 검색 — 입력이 멈추고 0.18초 뒤. 늦게 온 이전 검색 결과는 버린다(key 비교)
  useEffect(() => {
    let alive = true;
    const t = window.setTimeout(() => {
      api<{ items: OrgOption[]; total: number }>(orgLookupPath({ q: q.trim(), types: typeKey ? typeKey.split(",") : undefined, exclude, inactive: includeInactive, limit: LIMIT }))
        .then((r) => {
          if (!alive) return;
          r.items.forEach((o) => names.set(o.code, o.name));
          setRes({ key, items: r.items, total: r.total });
          setError(null);
          const at = r.items.findIndex((o) => o.code === value);
          setActive(at >= 0 ? at + (empty !== undefined ? 1 : 0) : 0);
        })
        .catch((e: Error) => alive && setError(e.message));
    }, q ? 180 : 0);
    return () => {
      alive = false;
      window.clearTimeout(t);
    };
  }, [key, q, typeKey, exclude, includeInactive, value, empty]);

  // 위치 — 아래 공간이 모자라면 위로, 좌우는 화면 안으로. 스크롤 · 창 크기 변경 때 다시 잰다
  useLayoutEffect(() => {
    const place = () => {
      const a = anchor.current?.getBoundingClientRect();
      if (!a) return;
      const margin = 8;
      const width = Math.min(Math.max(WIDTH, a.width), window.innerWidth - margin * 2);
      const h = box.current?.offsetHeight ?? 360;
      const left = Math.min(Math.max(margin, a.left), window.innerWidth - width - margin);
      const below = a.bottom + 4;
      const top = below + h > window.innerHeight - margin && a.top - 4 - h > margin ? a.top - 4 - h : below;
      setPos({ left, top, width });
    };
    place();
    // 자리를 잡은 뒤 검색칸으로 — 화면 밖 임시 위치에서 초점을 옮겨 페이지가 튀지 않게
    input.current?.focus({ preventScroll: true });
    const raf = requestAnimationFrame(place);
    window.addEventListener("scroll", place, true);
    window.addEventListener("resize", place);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("scroll", place, true);
      window.removeEventListener("resize", place);
    };
  }, [anchor]);

  // 바깥을 누르면 닫는다(기준 단추는 단추 자신이 열고 닫는다)
  useEffect(() => {
    const down = (e: MouseEvent) => {
      const t = e.target as Node;
      if (box.current?.contains(t) || anchor.current?.contains(t)) return;
      onClose(false);
    };
    document.addEventListener("mousedown", down);
    return () => document.removeEventListener("mousedown", down);
  }, [anchor, onClose]);

  const fresh = res?.key === key;
  const items = res?.items ?? [];
  const options: (OrgOption | null)[] = [...(empty !== undefined ? [null] : []), ...items];
  const optionId = (i: number) => `${uid}-opt-${i}`;

  useEffect(() => {
    list.current?.querySelector(`[data-index="${active}"]`)?.scrollIntoView({ block: "nearest" });
  }, [active]);

  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!options.length) return;
      const step = e.key === "ArrowDown" ? 1 : -1;
      setActive((i) => (i + step + options.length) % options.length);
    } else if (e.key === "Enter") {
      e.preventDefault();
      const o = options[active];
      if (o !== undefined) onPick(o?.code ?? "", o);
    } else if (e.key === "Escape") {
      e.preventDefault();
      onClose(true);
    } else if (e.key === "Tab") {
      onClose(false);
    }
  };

  if (typeof document === "undefined") return null;
  return createPortal(
    <div
      ref={box}
      role="dialog"
      aria-label={`${name} 찾기`}
      data-org-popover
      className="rounded-xl border border-hairline-soft bg-canvas p-xs"
      // 대화상자(z-70) 안에서 열어도 위에 뜨게
      style={{ position: "fixed", zIndex: 80, left: pos?.left ?? -9999, top: pos?.top ?? -9999, width: pos?.width ?? WIDTH, boxShadow: "var(--shadow-popup)" }}
    >
      <label className="relative block">
        <span className="sr-only">{name} 이름 · 코드로 찾기</span>
        <IconSearch className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-steel" />
        <input
          ref={input}
          role="combobox"
          aria-expanded="true"
          aria-controls={`${uid}-list`}
          aria-autocomplete="list"
          aria-activedescendant={options.length ? optionId(active) : undefined}
          className="input !h-9 !pl-8 text-[13px]"
          placeholder="이름 · 코드 · 상위 조직으로 찾기"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={onKey}
        />
      </label>
      <ul ref={list} id={`${uid}-list`} role="listbox" aria-label={`${name} 목록`} aria-busy={!fresh} className={clsx("mt-xs max-h-[280px] overflow-y-auto", !fresh && "opacity-60")}>
        {options.map((o, i) => (
          <li
            key={o?.code ?? "__empty"}
            id={optionId(i)}
            data-index={i}
            role="option"
            aria-selected={(o?.code ?? "") === value}
            onMouseDown={(e) => e.preventDefault()}
            onMouseEnter={() => setActive(i)}
            onClick={() => onPick(o?.code ?? "", o)}
            className={clsx("cursor-pointer rounded-lg px-2.5 py-1.5", i === active ? "bg-info-faint" : "", (o?.code ?? "") === value && "font-bold")}
          >
            {o ? (
              <>
                <span className="flex items-baseline gap-1.5 text-[12.5px] text-ink-deep">
                  <span className="min-w-0 truncate">{o.name}</span>
                  <span className="shrink-0 text-[11px] font-normal text-steel">
                    {o.unitLabel} · <span className="font-mono">{o.code}</span>
                    {o.active ? "" : " · 사용 안 함"}
                  </span>
                </span>
                {o.path.length ? <span className="block truncate text-[10.5px] font-normal text-stone">{orgOptionText(o)}</span> : null}
              </>
            ) : (
              <span className="text-[12.5px] text-charcoal">{empty}</span>
            )}
          </li>
        ))}
      </ul>
      <p role="status" aria-live="polite" className="px-2.5 pb-0.5 pt-1 text-[11px] text-stone">
        {error
          ? <span className="text-critical">{error}</span>
          : !res
            ? "찾는 중…"
            : !items.length
              ? "맞는 조직이 없습니다"
              : res.total > items.length
                ? `${res.total.toLocaleString("ko-KR")}곳 중 ${items.length}곳 — 검색어를 더 입력해 좁히세요`
                : `${res.total.toLocaleString("ko-KR")}곳`}
      </p>
    </div>,
    document.body,
  );
}
