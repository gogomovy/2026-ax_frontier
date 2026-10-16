import type { ReactNode } from "react";

/** 로그인 · 가입 화면 공통 틀 */
export function AuthFrame({ title, description, children }: { title: string; description?: string; children: ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center px-base py-section">
      <div className="w-full max-w-[420px]">
        {/* 서비스 로고 — 헤더와 같은 NH NAVI 가로형 로고 (로그인 전에도 보이도록 proxy 공개 경로에 등록됨) */}
        <div className="mb-xl">
          {/* eslint-disable-next-line @next/next/no-img-element -- 로그인 전 화면이라 이미지 최적화 경로 대신 공개 파일을 바로 쓴다 */}
          <img src="/nh-navi-logo.png" alt="NH NAVI" width={686} height={160} className="h-8 w-auto" />
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
