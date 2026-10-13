"use client";

import clsx from "clsx";
import { useId, useRef, useState } from "react";
import { acceptsFile, formatBytes } from "@/lib/upload-match";

/**
 * 파일 놓기 영역 (Phase E · UXF-01) — 끌어다 놓기 · 눌러서 고르기 · 키보드(Enter/Space).
 * 영역 전체가 숨긴 파일 입력의 label 이라 화면 낭독기 · 키보드는 기본 파일 입력처럼 동작한다.
 * 허용 형식 · 용량을 벗어나면 파일을 받지 않고 이유를 알린다(서버 보안 · 품질 검사는 그대로).
 */
export function FileDrop({
  accept,
  maxMb,
  file,
  onFile,
  label = "파일을 여기로 끌어다 놓거나 눌러서 고르세요",
  hint,
  disabled,
  compact,
  id,
  "data-testid": testId,
}: {
  accept: string;
  maxMb?: number;
  file: File | null;
  onFile: (f: File | null) => void;
  label?: string;
  hint?: string;
  disabled?: boolean;
  compact?: boolean;
  id?: string;
  "data-testid"?: string;
}) {
  const auto = useId();
  const inputId = id ?? `file-${auto}`;
  const hintId = `${inputId}-hint`;
  const errId = `${inputId}-err`;
  const inputRef = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const take = (f: File | null | undefined) => {
    if (!f) return;
    const why = !acceptsFile(f.name, accept) ? `${f.name} — 올릴 수 있는 형식이 아닙니다(${accept.replaceAll(",", " · ")})` : maxMb && f.size > maxMb * 1024 * 1024 ? `${f.name} — 용량이 ${maxMb}MB 를 넘습니다(${formatBytes(f.size)})` : null;
    if (why) {
      setError(why);
      if (inputRef.current) inputRef.current.value = "";
      return;
    }
    setError(null);
    onFile(f);
  };
  const clear = () => {
    onFile(null);
    setError(null);
    if (inputRef.current) inputRef.current.value = "";
  };

  return (
    <div data-file-drop={testId ?? true}>
      <input
        ref={inputRef}
        id={inputId}
        type="file"
        accept={accept}
        disabled={disabled}
        className="peer sr-only"
        aria-describedby={[hint ? hintId : "", error ? errId : ""].filter(Boolean).join(" ") || undefined}
        onChange={(e) => take(e.target.files?.[0])}
      />
      {file ? (
        <div className="flex flex-wrap items-center gap-sm rounded-2xl border border-success-line bg-success-faint px-md py-3 peer-focus-visible:ring-2 peer-focus-visible:ring-primary" data-file-chosen>
          <span aria-hidden="true" className="flex h-9 w-9 items-center justify-center rounded-xl bg-canvas text-[11px] font-bold text-success">
            {(file.name.split(".").pop() ?? "").toUpperCase().slice(0, 4)}
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[13.5px] font-bold text-ink-deep" title={file.name}>
              {file.name}
            </span>
            <span className="block text-[11.5px] text-steel">{formatBytes(file.size)}</span>
          </span>
          <label htmlFor={inputId} className={clsx("cursor-pointer rounded-pill bg-canvas px-4 py-2 text-[12px] font-bold text-ink-deep ring-1 ring-hairline", disabled && "pointer-events-none opacity-60")}>
            다른 파일
          </label>
          <button type="button" onClick={clear} disabled={disabled} className="rounded-pill px-3 py-2 text-[12px] font-bold text-steel hover:text-ink-deep">
            빼기
          </button>
        </div>
      ) : (
        <label
          htmlFor={inputId}
          tabIndex={-1}
          onDragEnter={(e) => {
            e.preventDefault();
            if (!disabled) setOver(true);
          }}
          onDragOver={(e) => {
            e.preventDefault();
            if (!disabled) setOver(true);
          }}
          onDragLeave={() => setOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setOver(false);
            if (!disabled) take(e.dataTransfer.files?.[0]);
          }}
          className={clsx(
            "flex cursor-pointer flex-col items-center justify-center gap-1 rounded-2xl border-2 border-dashed text-center transition-colors",
            compact ? "px-md py-md" : "px-lg py-xl",
            over ? "border-primary bg-info-faint" : "border-line-strong bg-surface-soft hover:border-primary hover:bg-info-faint",
            disabled && "pointer-events-none opacity-60",
            "peer-focus-visible:ring-2 peer-focus-visible:ring-primary peer-focus-visible:ring-offset-2",
          )}
        >
          <span aria-hidden="true" className="flex h-10 w-10 items-center justify-center rounded-circle bg-canvas text-[18px] text-primary shadow-sm">
            ↑
          </span>
          <span className="text-[14px] font-bold text-ink-deep">{label}</span>
          <span className="rounded-pill bg-ink-button px-4 py-1.5 text-[12px] font-bold text-white">파일 고르기</span>
        </label>
      )}
      {hint ? (
        <p id={hintId} className="mt-1 text-[11.5px] text-stone">
          {hint}
        </p>
      ) : null}
      {error ? (
        <p id={errId} role="alert" className="mt-1 text-[12px] font-bold text-critical" data-file-error>
          {error}
        </p>
      ) : null}
    </div>
  );
}
