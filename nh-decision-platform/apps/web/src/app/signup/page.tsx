"use client";

import Link from "next/link";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { AuthFrame, Field, FormError } from "@/components/auth/AuthFrame";
import { Button } from "@/components/ui/primitives";
import { api, apiPost } from "@/lib/api-client";

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

  useEffect(() => {
    api<{ levels: string[]; orgs: Org[] }>("/auth/orgs")
      .then((r) => {
        setOrgs(r.orgs);
        setLevels(r.levels);
      })
      .catch(() => setError("조직 정보를 불러오지 못했습니다."));
  }, []);

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

  const orgCode = path.filter(Boolean).slice(-1)[0] ?? "";
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [k]: k === "empNo" ? e.target.value.replace(/\D/g, "") : e.target.value }));

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!/^\d{8}$/.test(form.empNo)) return setError("사번은 숫자 8자리입니다.");
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
    <AuthFrame title="가입 신청" description="소속은 본부 > 부 > 국 > 팀, 지역본부 > 영업점 순서로 선택합니다. 화면 권한은 소속 조직(상위 조직 포함)에 따라 정해집니다.">
      <form onSubmit={submit} className="flex flex-col gap-base" noValidate>
        <Field label="사번" htmlFor="emp_no" hint="숫자 8자리">
          <input id="emp_no" className="input tnum" inputMode="numeric" maxLength={8} autoComplete="username" value={form.empNo} onChange={set("empNo")} required />
        </Field>
        <div className="grid grid-cols-2 gap-md">
          <Field label="이름" htmlFor="name">
            <input id="name" className="input" autoComplete="name" value={form.name} onChange={set("name")} required />
          </Field>
          <Field label="직급" htmlFor="position" hint="선택">
            <input id="position" className="input" value={form.position} onChange={set("position")} />
          </Field>
        </div>
        <fieldset>
          <legend className="mb-1.5 text-[12.5px] font-bold text-charcoal">소속</legend>
          <div className="flex flex-col gap-xs">
            {options.map((list, i) => {
              // 이 단계에서 고를 수 있는 조직 유형 (예: 본부·지역본부 / 부·국·영업점)
              const label = Array.from(new Set(list.map((o) => o.unitLabel))).join("·") || levels[i] || "조직";
              return (
              <select
                key={i}
                aria-label={label}
                className="input"
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
