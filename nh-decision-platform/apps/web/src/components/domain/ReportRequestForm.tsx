"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Field, FormError } from "@/components/auth/AuthFrame";
import { Badge, Button } from "@/components/ui/primitives";
import { api, apiPost } from "@/lib/api-client";
import type { ReportRequest } from "@/lib/types";

/**
 * 확인 · 보고 요청 등록 (B.32) — 영업점 · 사업부서가 본부(설정 request.to_org)로 올린다.
 * 요청 부서는 서버가 로그인 사용자 소속으로 정한다. 등록한 요청은 본부 경영목표 설정 화면의 요청 목록에 합쳐진다.
 */
export function ReportRequestForm() {
  const [types, setTypes] = useState<{ value: string; label: string }[]>([]);
  const [mine, setMine] = useState<ReportRequest[]>([]);
  const [reqType, setReqType] = useState("");
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [dueDate, setDueDate] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const apply = useCallback(([t, m]: [{ value: string; label: string }[], ReportRequest[]]) => {
    setTypes(t);
    setReqType((cur) => cur || t[0]?.value || "");
    setMine(m);
  }, []);
  const load = useCallback(
    () => Promise.all([api<{ value: string; label: string }[]>("/state/report-requests/types"), api<ReportRequest[]>("/state/report-requests/mine")]).then(apply),
    [apply],
  );

  useEffect(() => {
    Promise.all([api<{ value: string; label: string }[]>("/state/report-requests/types"), api<ReportRequest[]>("/state/report-requests/mine")])
      .then(apply)
      .catch((e: Error) => setError(e.message));
  }, [apply]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setDone(null);
    if (title.trim().length < 2 || body.trim().length < 2) return setError("제목과 내용을 입력하세요.");
    setBusy(true);
    try {
      await apiPost("/state/report-requests", { reqType, title: title.trim(), body: body.trim(), dueDate: dueDate || null });
      setTitle("");
      setBody("");
      setDueDate("");
      setDone("요청을 등록했습니다. 본부 경영목표 설정 화면에 전달됩니다.");
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid grid-cols-1 gap-lg lg:grid-cols-2">
      <form onSubmit={submit} className="flex flex-col gap-base rounded-2xl border border-hairline-soft p-lg" noValidate data-report-request-form>
        <Field label="요청 유형" htmlFor="req_type">
          <select id="req_type" className="input" value={reqType} onChange={(e) => setReqType(e.target.value)}>
            {types.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </Field>
        <Field label="제목" htmlFor="req_title">
          <input id="req_title" className="input" maxLength={200} value={title} onChange={(e) => setTitle(e.target.value)} required />
        </Field>
        <Field label="내용" htmlFor="req_body" hint="확인이 필요한 사항과 배경을 적어 주세요">
          <textarea id="req_body" className="input min-h-[110px]" maxLength={4000} value={body} onChange={(e) => setBody(e.target.value)} required />
        </Field>
        <Field label="회신 희망일" htmlFor="req_due" hint="선택">
          <input id="req_due" type="date" className="input" value={dueDate} onChange={(e) => setDueDate(e.target.value)} />
        </Field>
        <FormError message={error} />
        {done ? (
          <p role="status" className="text-[12.5px] font-bold text-success">
            {done}
          </p>
        ) : null}
        <Button type="submit" variant="confirm" disabled={busy || !reqType}>
          {busy ? "등록 중…" : "요청 등록"}
        </Button>
      </form>
      <div className="flex flex-col gap-sm">
        <p className="text-[12.5px] font-bold text-charcoal">보낸 요청 {mine.length}건</p>
        {mine.length ? (
          <ul className="flex flex-col gap-sm">
            {mine.map((r) => (
              <li key={r.id} className="rounded-xl border border-hairline-soft px-md py-sm">
                <div className="flex flex-wrap items-center gap-xs text-[11.5px] text-steel">
                  <Badge>{r.reqTypeLabel}</Badge> {r.createdAt} · {r.toOrg}
                  {r.dueDate ? ` · 회신 ${r.dueDate}` : ""}
                </div>
                <p className="mt-1 text-[13px] font-bold text-ink-deep">{r.title}</p>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-[12px] text-stone">아직 보낸 요청이 없습니다.</p>
        )}
      </div>
    </div>
  );
}
