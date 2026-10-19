"use client";

import Link from "next/link";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { AuthFrame, Field, FormError } from "@/components/auth/AuthFrame";
import { Button } from "@/components/ui/primitives";
import { api, apiPost } from "@/lib/api-client";
import { orgChain } from "@/lib/orgChain";

/** 인사 정보 조회 (/auth/signup/lookup · Phase R) — 조직 · 인사 .dat 동기화에 있는 사번이면 소속을 자동 선택 */
interface HrInfo {
  emp: string;
  found: boolean;
  name?: string;
  orgCode?: string;
  orgPath?: string[];
  position?: string | null;
  registered?: boolean;
  pending?: boolean;
}

interface Org {
  code: string;
  name: string;
  level: number;
  parent: string | null;
  unitType: string | null;
  unitLabel: string;
}

/** 가입 신청 — 사번 8자리 · 소속(부 > 국 > 팀) · 관리자 승인 후 로그인 (요구사항 AUTH-07) */
export default function SignupPage() {
  const [orgs, setOrgs] = useState<Org[]>([]);
  const [levels, setLevels] = useState<string[]>([]);
  const [path, setPath] = useState<string[]>([]);
  const [form, setForm] = useState({ empNo: "", name: "", position: "", password: "", confirm: "" });
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [hrResult, setHrResult] = useState<HrInfo | null>(null);

  useEffect(() => {
    api<{ levels: string[]; orgs: Org[] }>("/auth/orgs")
      .then((r) => {
        setOrgs(r.orgs);
        setLevels(r.levels);
      })
      .catch(() => setError("조직 정보를 불러오지 못했습니다."));
  }, []);

  // 사번을 8자리 이상 입력하면 인사 정보를 찾는다(입력이 멈추고 0.35초 뒤). 응답은 그 사번일 때만 쓴다(늦게 온 이전 응답 무시)
  useEffect(() => {
    const emp = form.empNo;
    if (emp.length < 8) return;
    const t = window.setTimeout(() => {
      api<Omit<HrInfo, "emp">>(`/auth/signup/lookup?emp_no=${encodeURIComponent(emp)}`)
        .then((r) => {
          setHrResult({ ...r, emp });
          if (r.found && r.orgCode) {
            const chain = orgChain(orgs, r.orgCode);
            if (chain.length) setPath(chain);
          }
        })
        .catch(() => setHrResult(null));
    }, 350);
    return () => window.clearTimeout(t);
  }, [form.empNo, orgs]);
  const hr = hrResult && hrResult.emp === form.empNo ? hrResult : null;
  const hrFound = Boolean(hr?.found && hr.orgCode);

  /** 계층별 선택지 — 상위에서 고른 조직의 하위만 */
  const options = useMemo(() => {
    const out: Org[][] = [];
    let parent: string | null = null;
    for (let lv = 1; lv <= levels.length; lv++) {
      const list = orgs.filter((o) => o.level === lv && (lv === 1 ? !o.parent : o.parent === parent));
      if (!list.length) break;
      out.push(list);
      parent = path[lv - 1] ?? null;
      if (!parent) break;
    }
    return out;
  }, [orgs, levels, path]);

  const orgCode = hrFound ? (hr?.orgCode ?? "") : (path.filter(Boolean).slice(-1)[0] ?? "");
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => {
    const v = k === "empNo" ? e.target.value.replace(/\D/g, "") : e.target.value;
    // 인사 정보로 채웠던 소속은 사번을 바꾸면 비운다(다른 사람의 소속이 남지 않게)
    if (k === "empNo" && hrFound && v !== form.empNo) setPath([]);
    setForm((f) => ({ ...f, [k]: v }));
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!hrFound && !/^\d{8}$/.test(form.empNo)) return setError("사번은 숫자 8자리입니다.");
    if (hr?.registered) return setError(hr.pending ? "이미 가입 신청이 접수된 사번입니다 (관리자 승인 대기)." : "이미 가입된 사번입니다. 로그인하세요.");
    if (!form.name.trim()) return setError("이름을 입력하세요.");
    if (!orgCode) return setError("소속을 선택하세요.");
    if (form.password !== form.confirm) return setError("비밀번호 확인이 일치하지 않습니다.");
    setBusy(true);
    try {
      const r = await apiPost<{ message: string }>("/auth/signup", {
        emp_no: form.empNo,
        name: form.name.trim(),
        position: form.position.trim() || null,
        password: form.password,
        org_code: orgCode,
      });
      setDone(r.message);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  if (done) {
    return (
      <AuthFrame title="가입 신청 완료" description={done}>
        <Link href="/login" className="inline-flex w-full justify-center rounded-pill bg-primary px-6 py-2.5 text-[13px] font-bold text-white">
          로그인 화면으로
        </Link>
      </AuthFrame>
    );
  }

  return (
    <AuthFrame title="가입 신청" description="소속은 본부 > 부 > 국 > 팀, 지역본부 > 영업점 순서로 선택합니다(인사 정보에 있는 사번은 자동 선택). 화면 권한은 소속 조직(상위 조직 포함)에 따라 정해집니다.">
      <form onSubmit={submit} className="flex flex-col gap-base" noValidate>
        <Field label="사번" htmlFor="emp_no" hint="숫자 8자리 — 인사 정보에 있는 사번이면 소속이 자동으로 선택됩니다">
          <input
            id="emp_no"
            className="input tnum"
            inputMode="numeric"
            maxLength={20}
            autoComplete="username"
            value={form.empNo}
            onChange={set("empNo")}
            aria-describedby="emp_no-hr"
            required
          />
        </Field>
        <p id="emp_no-hr" role="status" aria-live="polite" className="-mt-xs text-[12px]" data-hr-lookup={hr ? (hr.found ? "found" : hr.registered ? "registered" : "none") : undefined}>
          {hrFound ? (
            <span className="font-bold text-primary">인사 정보에서 찾았습니다 — 소속을 자동으로 선택했습니다. 이름은 인사 정보와 같게 입력하세요.</span>
          ) : hr?.registered ? (
            <span className="font-bold text-critical">{hr.pending ? "이미 가입 신청이 접수된 사번입니다 (관리자 승인 대기)." : "이미 가입된 사번입니다. 로그인하세요."}</span>
          ) : null}
        </p>
        <div className="grid grid-cols-2 gap-md">
          <Field label="이름" htmlFor="name" hint={hrFound && hr?.name ? `인사 정보 ${hr.name}` : undefined}>
            <input id="name" className="input" autoComplete="name" value={form.name} onChange={set("name")} required />
          </Field>
          <Field label="직급" htmlFor="position" hint={hrFound ? "인사 정보 기준" : "선택"}>
            <input id="position" className="input" value={hrFound ? (hr?.position ?? "") : form.position} onChange={set("position")} readOnly={hrFound} />
          </Field>
        </div>
        <fieldset>
          <legend className="mb-1.5 text-[12.5px] font-bold text-charcoal">소속</legend>
          {hrFound ? (
            <p className="mb-1.5 rounded-lg bg-info-faint px-md py-2 text-[12px] text-charcoal" data-hr-org={hr?.orgCode}>
              인사 정보 기준 소속: <span className="font-bold text-ink-deep">{(hr?.orgPath ?? []).join(" > ")}</span>
              <br />
              소속은 인사 정보로 정해집니다. 다르면 관리자에게 문의하세요.
            </p>
          ) : null}
          <div className="flex flex-col gap-xs">
            {options.map((list, i) => {
              // 이 단계에서 고를 수 있는 조직 유형 (예: 본부·지역본부 / 부·국·영업점)
              const label = Array.from(new Set(list.map((o) => o.unitLabel))).join("·") || levels[i] || "조직";
              return (
              <select
                key={i}
                aria-label={label}
                className="input"
                disabled={hrFound}
                value={path[i] ?? ""}
                onChange={(e) => setPath([...path.slice(0, i), e.target.value].filter(Boolean))}
              >
                <option value="">{label} 선택{i > 0 ? " (선택 안 하면 상위 조직 소속)" : ""}</option>
                {list.map((o) => (
                  <option key={o.code} value={o.code}>
                    {o.name} · {o.unitLabel}
                  </option>
                ))}
              </select>
              );
            })}
          </div>
        </fieldset>
        <Field label="비밀번호" htmlFor="password" hint="8자 이상 · 영문+숫자">
          <input id="password" type="password" className="input" autoComplete="new-password" value={form.password} onChange={set("password")} required />
        </Field>
        <Field label="비밀번호 확인" htmlFor="confirm">
          <input id="confirm" type="password" className="input" autoComplete="new-password" value={form.confirm} onChange={set("confirm")} required />
        </Field>
        <FormError message={error} />
        <Button type="submit" variant="confirm" disabled={busy} className="mt-xs w-full">
          {busy ? "신청 중…" : "가입 신청"}
        </Button>
      </form>
      <p className="mt-lg text-center text-[12.5px] text-steel">
        이미 계정이 있나요?{" "}
        <Link href="/login" className="font-bold text-primary">
          로그인
        </Link>
      </p>
    </AuthFrame>
  );
}
