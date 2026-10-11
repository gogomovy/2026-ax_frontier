"use client";

import clsx from "clsx";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { useUi } from "@/components/providers/UiProvider";
import { Badge, Button } from "@/components/ui/primitives";
import { api } from "@/lib/api-client";

/* ── 데이터 로드 ───────────────────────────────────────────── */
export function useApiData<T>(path: string | null, opts: { refreshMs?: number } = {}) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(Boolean(path));
  /** 응답이 온 뒤에만 상태를 바꾼다 (effect 안 동기 setState 금지 규칙) */
  const fetchData = useCallback(async () => {
    if (!path) return;
    try {
      const next = await api<T>(path);
      setData(next);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [path]);
  const reload = useCallback(async () => {
    setLoading(true);
    await fetchData();
  }, [fetchData]);
  useEffect(() => {
    if (!path) return;
    let alive = true;
    const load = () =>
      api<T>(path)
        .then((next) => {
          if (!alive) return;
          setData(next);
          setError(null);
        })
        .catch((e: Error) => alive && setError(e.message))
        .finally(() => alive && setLoading(false));
    load();
    const t = opts.refreshMs ? window.setInterval(load, opts.refreshMs) : undefined;
    return () => {
      alive = false;
      if (t) window.clearInterval(t);
    };
  }, [path, opts.refreshMs]);
  return { data, error, loading, reload, setData };
}

/** 변경 작업 실행 + 결과 토스트 + 재조회 */
export function useAction() {
  const { showToast } = useUi();
  const [busy, setBusy] = useState(false);
  const run = useCallback(
    async <T,>(fn: () => Promise<T>, ok?: string | ((r: T) => string), after?: () => unknown): Promise<T | null> => {
      setBusy(true);
      try {
        const r = await fn();
        const msg = typeof ok === "function" ? ok(r) : ok;
        if (msg) showToast(msg);
        await after?.();
        return r;
      } catch (e) {
        showToast(`실패 — ${(e as Error).message}`);
        return null;
      } finally {
        setBusy(false);
      }
    },
    [showToast],
  );
  return { run, busy };
}

/* ── 레이아웃 ───────────────────────────────────────────────── */
export function AdminPage({ title, description, actions, children }: { title: string; description?: ReactNode; actions?: ReactNode; children: ReactNode }) {
  return (
    <div className="shell pb-section pt-xl">
      <div className="mb-lg flex flex-wrap items-end justify-between gap-base">
        <div>
          <p className="mb-1 text-[12px] font-bold text-primary">관리자</p>
          <h1 className="text-[24px] font-bold text-ink-deep">{title}</h1>
          {description ? <p className="mt-1.5 max-w-[820px] text-[13px] leading-relaxed text-steel">{description}</p> : null}
        </div>
        {actions ? <div className="flex flex-wrap items-center gap-xs">{actions}</div> : null}
      </div>
      {children}
    </div>
  );
}

export function Card({ title, actions, children, className }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={clsx("mb-lg rounded-2xl border border-hairline-soft bg-canvas p-lg", className)}>
      {title || actions ? (
        <div className="mb-md flex flex-wrap items-center justify-between gap-xs">
          {title ? <h2 className="text-[15px] font-bold text-ink-deep">{title}</h2> : <span />}
          {actions ? <div className="flex flex-wrap items-center gap-xs">{actions}</div> : null}
        </div>
      ) : null}
      {children}
    </section>
  );
}

export function Loading({ error, loading }: { error?: string | null; loading?: boolean }) {
  if (error) return <p className="rounded-lg bg-[rgba(228,30,63,0.06)] px-md py-2.5 text-[12.5px] text-critical">{error}</p>;
  if (loading) return <p className="text-[12.5px] text-stone">불러오는 중…</p>;
  return null;
}

/* ── 표 ─────────────────────────────────────────────────────── */
export function Table({ head, children, dense = true }: { head: ReactNode[]; children: ReactNode; dense?: boolean }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-[12.5px]">
        <thead>
          <tr className="border-y border-hairline-soft bg-surface-soft">
            {head.map((h, i) => (
              <th key={i} scope="col" className={clsx("whitespace-nowrap px-2.5 text-left font-bold text-charcoal", dense ? "py-1.5" : "py-2.5")}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

export function C({ children, className, mono, right }: { children?: ReactNode; className?: string; mono?: boolean; right?: boolean }) {
  return <td className={clsx("border-b border-hairline-soft px-2.5 py-1.5 align-top text-charcoal", mono && "font-mono text-[11.5px]", right && "text-right tnum", className)}>{children}</td>;
}

/* ── 상태 표시 ─────────────────────────────────────────────── */
const STATUS_TONE: Record<string, "success" | "info" | "attention" | "critical" | "neutral" | "warning"> = {
  ok: "success",
  succeeded: "success",
  done: "success",
  passed: "success",
  committed: "success",
  active: "success",
  extracted: "success",
  running: "info",
  queued: "info",
  pending: "attention",
  staged: "attention",
  degraded: "attention",
  warning: "warning",
  partial: "warning",
  ingested: "info",
  skipped: "neutral",
  rolled_back: "neutral",
  disabled: "neutral",
  failed: "critical",
  error: "critical",
  rejected: "critical",
  locked: "critical",
  open: "attention",
  accepted: "success",
};

export function StatusBadge({ status, label }: { status?: string | null; label?: string }) {
  if (!status) return <Badge>-</Badge>;
  return <Badge tone={STATUS_TONE[status] ?? "neutral"}>{label ?? status}</Badge>;
}

export function OriginBadge({ origin }: { origin: string }) {
  return origin === "bank" ? <Badge tone="dark">당행</Badge> : <Badge tone="info">외부</Badge>;
}

export function Mono({ children }: { children: ReactNode }) {
  return <code className="rounded bg-surface-soft px-1.5 py-0.5 font-mono text-[11px] text-charcoal">{children}</code>;
}

export function fmtTime(iso?: string | null) {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}.${p(d.getMonth() + 1)}.${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

export function duration(a?: string | null, b?: string | null) {
  if (!a || !b) return "-";
  const ms = new Date(b).getTime() - new Date(a).getTime();
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`;
}

/* ── JSON 보기 · 편집 ──────────────────────────────────────── */
export function JsonView({ value, maxHeight = 320 }: { value: unknown; maxHeight?: number }) {
  return (
    <pre className="overflow-auto rounded-lg bg-surface-soft p-md font-mono text-[11px] leading-relaxed text-charcoal" style={{ maxHeight }}>
      {typeof value === "string" ? value : JSON.stringify(value, null, 2)}
    </pre>
  );
}

export function Collapse({ label, children, defaultOpen = false }: { label: ReactNode; children: ReactNode; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div>
      <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open} className="text-[12px] font-bold text-primary">
        {open ? "▾" : "▸"} {label}
      </button>
      {open ? <div className="mt-xs">{children}</div> : null}
    </div>
  );
}

/** JSON 편집기 — 문법 검증 후 저장 */
export function JsonEditor({ value, onSave, rows = 12, label = "저장", disabled }: { value: unknown; onSave: (v: unknown) => unknown; rows?: number; label?: string; disabled?: boolean }) {
  const [text, setText] = useState(() => JSON.stringify(value, null, 2));
  const [err, setErr] = useState<string | null>(null);
  const last = useRef(value);
  useEffect(() => {
    if (last.current !== value) {
      last.current = value;
      setText(JSON.stringify(value, null, 2));
    }
  }, [value]);
  return (
    <div>
      <textarea className="input font-mono text-[11.5px]" rows={rows} value={text} onChange={(e) => setText(e.target.value)} spellCheck={false} aria-label="JSON 편집" />
      <div className="mt-xs flex items-center gap-xs">
        <Button
          size="sm"
          variant="confirm"
          disabled={disabled}
          onClick={() => {
            try {
              const v = JSON.parse(text);
              setErr(null);
              onSave(v);
            } catch (e) {
              setErr(`JSON 형식 오류: ${(e as Error).message}`);
            }
          }}
        >
          {label}
        </Button>
        {err ? <span className="text-[12px] text-critical">{err}</span> : null}
      </div>
    </div>
  );
}

/* ── 입력 ───────────────────────────────────────────────────── */
export function TextInput({ label, value, onChange, type = "text", placeholder, className, mono }: { label?: string; value: string | number | null | undefined; onChange: (v: string) => void; type?: string; placeholder?: string; className?: string; mono?: boolean }) {
  return (
    <label className={clsx("block", className)}>
      {label ? <span className="mb-1 block text-[11.5px] font-bold text-steel">{label}</span> : null}
      <input className={clsx("input !h-9 text-[13px]", mono && "font-mono")} type={type} value={value ?? ""} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} />
    </label>
  );
}

export function Select({ label, value, onChange, options, className }: { label?: string; value: string | number | null | undefined; onChange: (v: string) => void; options: { value: string | number; label: string }[]; className?: string }) {
  return (
    <label className={clsx("block", className)}>
      {label ? <span className="mb-1 block text-[11.5px] font-bold text-steel">{label}</span> : null}
      <select className="input !h-9 text-[13px]" value={value ?? ""} onChange={(e) => onChange(e.target.value)}>
        {options.map((o) => (
          <option key={String(o.value)} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}

export function Check({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="inline-flex items-center gap-1.5 text-[12.5px] text-charcoal">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      {label}
    </label>
  );
}

export function Tabs<K extends string>({ tabs, active, onChange }: { tabs: { key: K; label: string; count?: number }[]; active: K; onChange: (k: K) => void }) {
  return (
    <div role="tablist" className="mb-lg flex flex-wrap gap-1.5">
      {tabs.map((t) => (
        <button
          key={t.key}
          type="button"
          role="tab"
          aria-selected={active === t.key}
          onClick={() => onChange(t.key)}
          className={clsx("rounded-pill px-4 py-1.5 text-[12.5px] font-bold", active === t.key ? "bg-ink-deep text-white" : "bg-surface-soft text-charcoal")}
        >
          {t.label}
          {t.count !== undefined ? <span className="ml-1 tnum opacity-70">{t.count}</span> : null}
        </button>
      ))}
    </div>
  );
}

/** 작은 추이 그래프 */
export function Sparkline({ values, width = 96, height = 24 }: { values: number[]; width?: number; height?: number }) {
  if (values.length < 2) return <span className="text-[11px] text-stone">-</span>;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * width},${height - ((v - min) / span) * (height - 4) - 2}`).join(" ");
  return (
    <svg width={width} height={height} aria-hidden="true">
      <polyline points={pts} fill="none" stroke="currentColor" strokeWidth="1.5" className="text-primary" />
    </svg>
  );
}
