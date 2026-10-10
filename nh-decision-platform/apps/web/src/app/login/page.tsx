"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState, type FormEvent } from "react";
import { AuthFrame, Field, FormError } from "@/components/auth/AuthFrame";
import { Button } from "@/components/ui/primitives";
import { api, apiPost } from "@/lib/api-client";

/** SSO 실패 사유 (서버 → /login?sso_error=) */
const SSO_ERROR: Record<string, string> = {
  denied: "SSO 로그인이 취소되었거나 거부되었습니다.",
  state: "로그인 요청이 만료되었습니다. 다시 시도해 주세요.",
  token: "SSO 인증 정보를 확인하지 못했습니다. 잠시 후 다시 시도해 주세요.",
  account: "SSO 계정과 연결된 사용 가능한 사번이 없습니다. 가입 신청 또는 관리자 승인을 확인해 주세요.",
  disabled: "SSO 로그인이 설정되어 있지 않습니다.",
};

/** 로그인 — 사번 8자리 + 비밀번호 (요구사항 AUTH-06) */
export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}

function LoginForm() {
  const params = useSearchParams();
  const [empNo, setEmpNo] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [sso, setSso] = useState<{ enabled: boolean; label: string; localLogin: string } | null>(null);
  useEffect(() => {
    api<{ enabled: boolean; label: string; localLogin: string }>("/auth/oidc/config")
      .then(setSso)
      .catch(() => setSso(null));
  }, []);
  const ssoError = params.get("sso_error");
  const nextParam = params.get("next");
  const ssoHref = `/backend/auth/oidc/login${nextParam && nextParam.startsWith("/") && !nextParam.startsWith("//") ? `?next=${encodeURIComponent(nextParam)}` : ""}`;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!/^\d{8}$/.test(empNo)) return setError("사번은 숫자 8자리입니다.");
    setBusy(true);
    try {
      const res = await apiPost<{ home: string }>("/auth/login", { emp_no: empNo, password });
      const next = params.get("next");
      // 외부 주소로의 이동을 막는다. 레이아웃 세션 데이터를 새로 받기 위해 전체 새로고침
      window.location.href = next && next.startsWith("/") && !next.startsWith("//") ? next : res.home;
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  };

  return (
    <AuthFrame title="로그인" description="사번과 비밀번호로 로그인합니다. 소속 부서의 권한에 따라 화면이 열립니다.">
      {sso?.enabled ? (
        <div className="mb-lg flex flex-col gap-xs">
          <a
            href={ssoHref}
            className="inline-flex w-full items-center justify-center rounded-pill bg-ink-deep px-6 py-2.5 text-[13px] font-bold text-white"
            data-sso-login
          >
            {sso.label}
          </a>
          {sso.localLogin !== "all" ? (
            <p className="text-center text-[11.5px] text-steel">
              {sso.localLogin === "admin" ? "사번 · 비밀번호 로그인은 관리자 비상 로그인에만 사용합니다." : "SSO 로 로그인합니다."}
            </p>
          ) : null}
        </div>
      ) : null}
      {ssoError ? <FormError message={SSO_ERROR[ssoError] ?? "SSO 로그인에 실패했습니다."} /> : null}
      {sso?.enabled && sso.localLogin === "none" ? null : (
        <form onSubmit={submit} className="flex flex-col gap-base" noValidate>
        <Field label="사번" htmlFor="emp_no" hint="숫자 8자리">
          <input
            id="emp_no"
            className="input tnum"
            inputMode="numeric"
            autoComplete="username"
            maxLength={8}
            value={empNo}
            onChange={(e) => setEmpNo(e.target.value.replace(/\D/g, ""))}
            required
            autoFocus
          />
        </Field>
        <Field label="비밀번호" htmlFor="password">
          <input
            id="password"
            type="password"
            className="input"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </Field>
        <FormError message={error} />
        <Button type="submit" variant="confirm" disabled={busy} className="mt-xs w-full">
          {busy ? "확인 중…" : "로그인"}
        </Button>
        </form>
      )}
      <p className="mt-lg text-center text-[12.5px] text-steel">
        처음 사용하시나요?{" "}
        <Link href="/signup" className="font-bold text-primary">
          가입 신청
        </Link>
      </p>
    </AuthFrame>
  );
}
