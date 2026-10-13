"use client";

import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { Button } from "@/components/ui/primitives";
import { useFocusTrap } from "@/lib/a11y";

/**
 * 앱 확인 대화상자 (Phase E · INT-01 · Q123) — 되돌리기 어려운 작업 전에 결과를 설명하고 한 번 더 묻는다.
 * 브라우저 confirm · prompt 대신 쓴다. 열릴 때 초점은 [취소](위험 작업의 기본 = 취소), Esc = 취소, 닫히면 연 요소로 초점 복귀.
 */
export interface ConfirmOptions {
  title: string;
  body?: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  /** danger — 확인 단추를 위험 색으로 */
  tone?: "default" | "danger";
  /** 입력이 필요한 확인(예: 새 비밀번호) — 결과는 입력 문자열 */
  input?: { label: string; type?: "text" | "password"; placeholder?: string; initial?: string; validate?: (v: string) => string | null };
}

export interface ConfirmRequest extends ConfirmOptions {
  resolve: (v: boolean | string | null) => void;
}

export function ConfirmDialog({ req, onDone }: { req: ConfirmRequest; onDone: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const titleId = useId();
  const bodyId = useId();
  const inputId = useId();
  const [value, setValue] = useState(req.input?.initial ?? "");
  const [error, setError] = useState<string | null>(null);
  useFocusTrap(ref, true, { autoFocus: false, restore: true });

  const close = (v: boolean | string | null) => {
    req.resolve(v);
    onDone();
  };

  // 열리자마자 초점(입력이 있으면 입력, 없으면 [취소]) — 포커스 가두기가 연 요소를 먼저 기억한 뒤
  useEffect(() => {
    (req.input ? inputRef.current : cancelRef.current)?.focus();
  }, [req.input]);
  // Esc = 취소 — 초점이 어디에 있든(대화상자 밖에 남아 있어도) 닫힌다
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      e.preventDefault();
      e.stopPropagation();
      req.resolve(req.input ? null : false);
      onDone();
    };
    document.addEventListener("keydown", onKey, true);
    return () => document.removeEventListener("keydown", onKey, true);
  }, [req, onDone]);
  const ok = () => {
    if (req.input) {
      const err = req.input.validate?.(value) ?? (value.trim() ? null : `${req.input.label}을(를) 입력하세요`);
      if (err) {
        setError(err);
        inputRef.current?.focus();
        return;
      }
      close(value);
      return;
    }
    close(true);
  };

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-scrim p-md no-print">
      <div
        ref={ref}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={req.body ? bodyId : undefined}
        tabIndex={-1}
        className="w-full max-w-[440px] animate-pop-in rounded-3xl bg-canvas p-xl shadow-popup"
        data-confirm-dialog
      >
        <h2 id={titleId} className="text-[17px] font-bold text-ink-deep">
          {req.title}
        </h2>
        {req.body ? (
          <div id={bodyId} className="mt-xs text-[13px] leading-relaxed text-charcoal">
            {req.body}
          </div>
        ) : null}
        {req.input ? (
          <div className="mt-md">
            <label htmlFor={inputId} className="mb-1 block text-[12px] font-bold text-charcoal">
              {req.input.label}
            </label>
            <input
              ref={inputRef}
              id={inputId}
              className="input !h-10 w-full text-[13px]"
              type={req.input.type ?? "text"}
              placeholder={req.input.placeholder}
              value={value}
              autoComplete={req.input.type === "password" ? "new-password" : "off"}
              aria-invalid={Boolean(error)}
              aria-describedby={error ? `${inputId}-err` : undefined}
              onChange={(e) => {
                setValue(e.target.value);
                setError(null);
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter") ok();
              }}
            />
            {error ? (
              <p id={`${inputId}-err`} role="alert" className="mt-1 text-[12px] text-critical">
                {error}
              </p>
            ) : null}
          </div>
        ) : null}
        <div className="mt-lg flex justify-end gap-xs">
          <button
            ref={cancelRef}
            type="button"
            onClick={() => close(req.input ? null : false)}
            className="inline-flex h-10 items-center justify-center rounded-md border border-hairline bg-canvas px-4 text-[14px] font-bold text-ink-deep hover:bg-surface-soft"
            data-confirm-cancel
          >
            {req.cancelLabel ?? "취소"}
          </button>
          <Button variant={req.tone === "danger" ? "danger" : "primary"} onClick={ok} data-confirm-ok>
            {req.confirmLabel ?? "확인"}
          </Button>
        </div>
      </div>
    </div>
  );
}
