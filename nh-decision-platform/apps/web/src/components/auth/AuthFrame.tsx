import type { ReactNode } from "react";

/** 로그인 · 가입 화면 공통 틀 */
export function AuthFrame({ title, description, children }: { title: string; description?: string; children: ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center px-base py-section">
      <div className="w-full max-w-[420px]">
        <div className="mb-xl flex items-center gap-2.5">
          <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-ink-deep text-[12.5px] font-bold text-white">NH</span>
          <span className="leading-tight">
            <span className="block text-[14px] font-bold text-ink-deep">경영 의사결정</span>
            <span className="block text-[11px] text-stone">AI Decision Platform</span>
          </span>
        </div>
        <h1 className="text-[24px] font-bold text-ink-deep">{title}</h1>
        {description ? <p className="mt-1.5 text-[13px] leading-relaxed text-steel">{description}</p> : null}
        <div className="mt-xl">{children}</div>
      </div>
    </div>
  );
}

export function Field({ label, htmlFor, hint, children }: { label: string; htmlFor: string; hint?: string; children: ReactNode }) {
  return (
    <div>
      <label htmlFor={htmlFor} className="mb-1.5 flex items-baseline justify-between text-[12.5px] font-bold text-charcoal">
        <span>{label}</span>
        {hint ? <span className="text-[11px] font-medium text-stone">{hint}</span> : null}
      </label>
      {children}
    </div>
  );
}

export function FormError({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p role="alert" className="rounded-lg bg-critical-faint px-md py-2.5 text-[12.5px] font-medium text-critical">
      {message}
    </p>
  );
}
