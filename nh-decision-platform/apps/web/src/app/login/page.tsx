"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState, type FormEvent } from "react";
import { AuthFrame, Field, FormError } from "@/components/auth/AuthFrame";
import { Button } from "@/components/ui/primitives";
import { api, apiPost } from "@/lib/api-client";
import { safeNext } from "@/lib/safe-next";
import { SSO_ERROR, ssoStartHref, strictestLocalLogin, type SsoProvider } from "@/lib/sso";

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
  const [sso, setSso] = useState<SsoProvider | null>(null);
  // 사내 SSO(INISAFE Nexess 티켓 · Phase R) — 꺼져 있으면 버튼 없음
  const [nc, setNc] = useState<SsoProvider | null>(null);
  useEffect(() => {
    api<SsoProvider>("/auth/oidc/config")
      .then(setSso)
      .catch(() => setSso(null));
    api<SsoProvider>("/auth/nc/config")
      .then(setNc)
      .catch(() => setNc(null));
  }, []);
  const ssoError = params.get("sso_error");
  const nextParam = safeNext(params.get("next"));
  const ssoHref = ssoStartHref("/backend/auth/oidc/login", nextParam);
  const ncHref = ssoStartHref("/backend/auth/nc/init", nextParam);
  const localLogin = strictestLocalLogin([sso, nc]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    // 가입 사번(8자리) 또는 인사 정보의 개인번호(Phase R · 9자리 등)
    if (!/^\d{8,20}$/.test(empNo)) return setError("사번은 숫자 8자리 이상입니다.");
    setBusy(true);
    try {
      const res = await apiPost<{ home: string }>("/auth/login", { emp_no: empNo, password });
      // 외부 주소로의 이동을 막는다. 레이아웃 세션 데이터를 새로 받기 위해 전체 새로고침
      window.location.href = nextParam ?? res.home;
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  };

  return (
    <AuthFrame title="로그인" description="사번과 비밀번호로 로그인합니다. 소속 부서의 권한에 따라 화면이 열립니다.">
      {sso?.enabled || nc?.enabled ? (
        <div className="mb-lg flex flex-col gap-xs">
          {nc?.enabled ? (
            <a
              href={ncHref}
              className="inline-flex w-full items-center justify-center rounded-pill bg-ink-deep px-6 py-2.5 text-[13px] font-bold text-white"
              data-nc-sso-login
            >
              {nc.label}
            </a>
          ) : null}
          {sso?.enabled ? (
            <a
              href={ssoHref}
              className="inline-flex w-full items-center justify-center rounded-pill bg-ink-deep px-6 py-2.5 text-[13px] font-bold text-white"
              data-sso-login
            >
              {sso.label}
            </a>
          ) : null}
          {localLogin !== "all" ? (
            <p className="text-center text-[11.5px] text-steel">
              {localLogin === "admin" ? "사번 · 비밀번호 로그인은 관리자 비상 로그인에만 사용합니다." : "SSO 로 로그인합니다."}
            </p>
          ) : null}
        </div>
      ) : null}
      {ssoError ? <FormError message={SSO_ERROR[ssoError] ?? "SSO 로그인에 실패했습니다."} /> : null}
      {localLogin === "none" ? null : (
        <form onSubmit={submit} className="flex flex-col gap-base" noValidate>
        <Field label="사번" htmlFor="emp_no" hint="숫자 8자리 (인사 정보 개인번호도 가능)">
          <input
            id="emp_no"
            className="input tnum"
            inputMode="numeric"
            autoComplete="username"
            maxLength={20}
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
