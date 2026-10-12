"use client";

import clsx from "clsx";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useUi } from "@/components/providers/UiProvider";
import { Advanced, EmptyState, KeyValueList, Notice } from "@/components/ui/Layout";
import { Badge, Button, PillTabs } from "@/components/ui/primitives";
import { api } from "@/lib/api-client";

/*
 * 업무 자료 올리기 (Phase C · UPL-01~03 · Q99)
 * 1) 무엇을 올릴지 고르기(정형 자료 = 기존 데이터셋의 새 버전 · 문서 = 분류 지정) → 2) 파일 · 정보 → 3) 검사 결과와 함께 승인 요청
 * → 관리자 [자료 승인] 후 반영. 아래 '내 요청' 에서 상태(승인 대기 · 승인 · 반려 · 실패)를 본다.
 */

interface DatasetOpt {
  code: string;
  name: string;
  origin: "bank" | "ext";
  kind: string;
  description: string;
  filePattern: string | null;
  refreshCycle: string | null;
  columns: { name: string; label: string; type?: string }[];
  current: { version: number; asOf: string | null; rows: number; dataOrigin: string }[];
}
export interface Uploadable {
  datasets: DatasetOpt[];
  docClasses: { key: string; label: string; origin: string }[];
  accept: { dataset: string; document: string };
}
interface Check {
  rule: string;
  passed: boolean;
  detail: string;
  severity: string;
}
export interface UploadReq {
  id: number;
  kind: "dataset" | "document";
  target: string;
  targetLabel: string;
  origin: string;
  fileName: string;
  meta: Record<string, string | null>;
  preview: { rows?: number; quality?: { status?: string; checks?: Check[] }; chars?: number; pages?: number; excerpt?: string; headers?: string[]; columns?: string[]; sample?: Record<string, unknown>[] };
  status: "pending" | "approved" | "rejected" | "failed";
  statusLabel: string;
  requestedBy: string;
  requestedByName?: string | null;
  requestedOrgName?: string | null;
  reviewedByName?: string | null;
  reviewedAt: string | null;
  reviewNote: string | null;
  result: { version?: number; rows?: number; docCode?: string; error?: string; isCurrent?: boolean };
  createdAt: string;
}

const STATUS_TONE = { pending: "attention", approved: "success", rejected: "critical", failed: "critical" } as const;
const QUALITY = { passed: { label: "검사 통과", tone: "success" }, warning: { label: "주의", tone: "attention" }, failed: { label: "실패", tone: "critical" } } as const;

export function fmtDateTime(iso?: string | null) {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}.${p(d.getMonth() + 1)}.${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

export function QualityBadge({ status }: { status?: string }) {
  const q = QUALITY[(status ?? "") as keyof typeof QUALITY];
  return q ? <Badge tone={q.tone}>{q.label}</Badge> : <Badge>-</Badge>;
}

export function RequestStatus({ r }: { r: Pick<UploadReq, "status" | "statusLabel" | "result"> }) {
  return (
    <Badge tone={STATUS_TONE[r.status]}>
      {r.statusLabel}
      {r.status === "approved" && r.result.version ? ` · v${r.result.version}` : ""}
    </Badge>
  );
}

/** 검사 결과 — 행 수 · 품질 · 실패 · 주의 항목 */
export function RequestPreview({ r, showSample }: { r: UploadReq; showSample?: boolean }) {
  const checks = r.preview.quality?.checks ?? [];
  const notPassed = checks.filter((c) => !c.passed);
  if (r.kind === "document") {
    return (
      <div className="flex flex-col gap-xs">
        <KeyValueList
          dense
          items={[
            { label: "제목", value: r.meta.title ?? "-" },
            { label: "본문", value: `${(r.preview.chars ?? 0).toLocaleString("ko-KR")}자 · ${r.preview.pages ?? 1}면` },
            ...(r.meta.issuer ? [{ label: "발행 기관", value: r.meta.issuer }] : []),
          ]}
        />
        {r.preview.excerpt ? <p className="line-clamp-3 rounded-lg bg-surface-soft px-md py-2 text-[12px] leading-relaxed text-charcoal">{r.preview.excerpt}</p> : null}
      </div>
    );
  }
  const sample = r.preview.sample ?? [];
  const cols = (r.preview.columns ?? []).slice(0, 8);
  return (
    <div className="flex flex-col gap-xs">
      <KeyValueList
        dense
        items={[
          { label: "행", value: `${(r.preview.rows ?? 0).toLocaleString("ko-KR")}행` },
          { label: "품질 검사", value: <QualityBadge status={r.preview.quality?.status} />, hint: checks.length ? `${checks.length}개 중 통과 ${checks.length - notPassed.length}` : undefined },
          ...(r.meta.asOf ? [{ label: "기준일", value: r.meta.asOf }] : []),
          { label: "자료 성격", value: r.meta.dataOrigin === "simulated" ? "시뮬레이션" : "실데이터" },
        ]}
      />
      {notPassed.length ? (
        <ul className="flex flex-col gap-0.5 text-[12px]">
          {notPassed.map((c, i) => (
            <li key={i} className={c.severity === "error" ? "text-critical" : "text-attention"}>
              {c.severity === "error" ? "실패" : "주의"} · {c.rule} — {c.detail}
            </li>
          ))}
        </ul>
      ) : null}
      {showSample && sample.length && cols.length ? (
        <Advanced label={`앞부분 ${sample.length}행 보기`}>
          <div className="max-w-full overflow-x-auto">
            <table className="w-full border-collapse text-[11.5px]">
              <thead>
                <tr className="bg-surface-soft">
                  {cols.map((c) => (
                    <th key={c} scope="col" className="whitespace-nowrap px-2 py-1 text-left font-bold text-charcoal">
                      {c}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {sample.map((row, i) => (
                  <tr key={i} className="border-b border-hairline-soft">
                    {cols.map((c) => (
                      <td key={c} className="whitespace-nowrap px-2 py-1 font-mono text-charcoal">
                        {row[c] === null || row[c] === undefined ? "" : String(row[c])}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Advanced>
      ) : null}
    </div>
  );
}

function Field({ label, hint, children, htmlFor }: { label: string; hint?: string; children: React.ReactNode; htmlFor?: string }) {
  return (
    <div>
      <label htmlFor={htmlFor} className="mb-1 block text-[12px] font-bold text-charcoal">
        {label}
      </label>
      {children}
      {hint ? <p className="mt-1 text-[11.5px] text-stone">{hint}</p> : null}
    </div>
  );
}

function Step({ n, title, children, done }: { n: number; title: string; children: React.ReactNode; done?: boolean }) {
  return (
    <li className="relative pl-10">
      <span aria-hidden="true" className={clsx("absolute left-0 top-0 flex h-7 w-7 items-center justify-center rounded-circle text-[12px] font-bold", done ? "bg-success-soft text-success" : "bg-ink-deep text-white")}>
        {n}
      </span>
      <h2 className="mb-md pt-1 text-[15px] font-bold text-ink-deep">
        <span className="sr-only">{n}단계 · </span>
        {title}
      </h2>
      {children}
    </li>
  );
}

export function UploadWorkspace({ initial }: { initial: Uploadable }) {
  const { showToast } = useUi();
  const opts = initial;
  const [mine, setMine] = useState<UploadReq[] | null>(null);
  const [kind, setKind] = useState<"dataset" | "document">("dataset");
  const [target, setTarget] = useState("");
  const [q, setQ] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [fileKey, setFileKey] = useState(0);
  const [form, setForm] = useState({ data_origin: "actual", as_of: "", note: "", title: "", issuer: "", published_at: "", text: "" });
  const [busy, setBusy] = useState(false);
  const [last, setLast] = useState<UploadReq | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  const loadMine = useCallback(() => api<UploadReq[]>("/db/uploads/mine").then(setMine), []);
  useEffect(() => {
    let alive = true;
    api<UploadReq[]>("/db/uploads/mine")
      .then((m) => alive && setMine(m))
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, []);

  const datasets = useMemo(() => opts.datasets.filter((d) => !q || `${d.code} ${d.name} ${d.description}`.toLowerCase().includes(q.toLowerCase())), [opts, q]);
  const ds = opts.datasets.find((d) => d.code === target) ?? null;
  const cls = opts.docClasses.find((c) => c.key === target) ?? null;
  const ready = kind === "dataset" ? Boolean(ds && file) : Boolean(cls && form.title.trim() && (file || form.text.trim()));

  const switchKind = (k: "dataset" | "document") => {
    setKind(k);
    setTarget("");
    setFile(null);
    setFileKey((n) => n + 1);
    setFailure(null);
  };

  const submit = async () => {
    setBusy(true);
    setFailure(null);
    try {
      const fd = new FormData();
      if (file) fd.append("file", file);
      if (kind === "dataset") {
        fd.append("target", target);
        fd.append("data_origin", form.data_origin);
        if (form.as_of) fd.append("as_of", form.as_of);
      } else {
        fd.append("doc_class", target);
        fd.append("title", form.title.trim());
        if (form.issuer) fd.append("issuer", form.issuer);
        if (form.published_at) fd.append("published_at", form.published_at);
        if (!file && form.text) fd.append("text", form.text);
      }
      if (form.note) fd.append("note", form.note);
      const r = await api<UploadReq>(`/db/uploads/${kind}`, { method: "POST", body: fd });
      setLast(r);
      showToast("승인 요청을 보냈습니다 — 관리자가 승인하면 반영됩니다");
      setFile(null);
      setFileKey((n) => n + 1);
      setForm((f) => ({ ...f, note: "", title: "", issuer: "", published_at: "", text: "" }));
      await loadMine();
    } catch (e) {
      setFailure((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid grid-cols-1 gap-xl xl:grid-cols-[minmax(0,1fr)_380px]">
      <section aria-label="자료 올리기" className="rounded-2xl border border-hairline-soft bg-canvas p-lg">
        <ol className="flex flex-col gap-xl">
          <Step n={1} title="무엇을 올리나요" done={Boolean(target)}>
            <PillTabs
              label="자료 종류"
              value={kind}
              onChange={switchKind}
              items={[
                { key: "dataset", label: "정형 자료(엑셀 · CSV)", count: opts.datasets.length },
                { key: "document", label: "문서(PDF · 한글 · 글)", count: opts.docClasses.length },
              ]}
            />
            {kind === "dataset" ? (
              <div className="mt-md">
                <input className="input !h-9 mb-xs w-full max-w-[360px] text-[13px]" placeholder="자료 이름 · 코드로 찾기" aria-label="자료 찾기" value={q} onChange={(e) => setQ(e.target.value)} />
                {datasets.length ? (
                  <ul className="grid max-h-[340px] grid-cols-1 gap-xs overflow-y-auto pr-1 md:grid-cols-2" role="radiogroup" aria-label="올릴 자료">
                    {datasets.map((d) => {
                      const on = d.code === target;
                      return (
                        <li key={d.code}>
                          <button
                            type="button"
                            role="radio"
                            aria-checked={on}
                            onClick={() => setTarget(d.code)}
                            className={clsx("w-full rounded-xl border px-md py-2.5 text-left transition-colors", on ? "border-primary bg-info-faint" : "border-hairline-soft hover:bg-surface-soft")}
                            data-upload-target={d.code}
                          >
                            <span className="flex items-center gap-1.5">
                              <span className="truncate text-[13px] font-bold text-ink-deep">{d.name}</span>
                              <Badge tone={d.origin === "bank" ? "dark" : "info"}>{d.origin === "bank" ? "당행" : "외부"}</Badge>
                            </span>
                            <span className="mt-0.5 block font-mono text-[10.5px] text-stone">{d.code}</span>
                            <span className="mt-0.5 block text-[11.5px] text-steel">
                              {d.current[0] ? `현재 v${d.current[0].version}${d.current[0].asOf ? ` · ${d.current[0].asOf.slice(0, 10)}` : ""} · ${d.current[0].rows.toLocaleString("ko-KR")}행` : "현재 자료 없음"}
                              {d.refreshCycle ? ` · ${d.refreshCycle} 갱신` : ""}
                            </span>
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                ) : (
                  <EmptyState compact title="맞는 자료가 없습니다" description="찾는 말을 바꾸거나, 새 종류의 자료라면 관리자에게 데이터셋 등록을 요청하세요." />
                )}
              </div>
            ) : (
              <div className="mt-md flex flex-wrap gap-xs" role="radiogroup" aria-label="문서 분류">
                {opts.docClasses.map((c) => (
                  <button
                    key={c.key}
                    type="button"
                    role="radio"
                    aria-checked={c.key === target}
                    onClick={() => setTarget(c.key)}
                    className={clsx("rounded-xl border px-md py-2 text-[12.5px] font-bold", c.key === target ? "border-primary bg-info-faint text-primary" : "border-hairline-soft text-charcoal hover:bg-surface-soft")}
                  >
                    {c.label}
                    <span className="ml-1.5 text-[11px] font-medium text-stone">{c.origin === "ext" ? "외부" : "당행"}</span>
                  </button>
                ))}
              </div>
            )}
          </Step>

          <Step n={2} title={kind === "dataset" ? "파일과 기준 정보" : "문서와 정보"} done={ready}>
            {!target ? (
              <p className="text-[12.5px] text-stone">먼저 1단계에서 {kind === "dataset" ? "올릴 자료" : "문서 분류"}를 고르세요.</p>
            ) : kind === "dataset" && ds ? (
              <div className="flex flex-col gap-md">
                <p className="text-[12.5px] leading-relaxed text-steel">{ds.description}</p>
                <Field label="파일" htmlFor="up-file" hint={`${opts.accept.dataset} · ${ds.filePattern ? `파일명 규칙 ${ds.filePattern}` : "파일명 규칙 없음"}`}>
                  <input key={fileKey} id="up-file" type="file" accept={opts.accept.dataset} onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="text-[12.5px]" />
                </Field>
                <div className="grid grid-cols-1 gap-md md:grid-cols-3">
                  <Field label="자료 성격" htmlFor="up-origin">
                    <select id="up-origin" className="input !h-9 text-[13px]" value={form.data_origin} onChange={(e) => setForm({ ...form, data_origin: e.target.value })}>
                      <option value="actual">실데이터</option>
                      <option value="simulated">시뮬레이션</option>
                    </select>
                  </Field>
                  <Field label="기준일(선택)" htmlFor="up-asof" hint="비우면 파일의 기준일 열에서 읽습니다">
                    <input id="up-asof" className="input !h-9 text-[13px]" type="date" value={form.as_of} onChange={(e) => setForm({ ...form, as_of: e.target.value })} />
                  </Field>
                  <Field label="메모(선택)" htmlFor="up-note">
                    <input id="up-note" className="input !h-9 text-[13px]" value={form.note} maxLength={500} placeholder="예: 8월 정정본" onChange={(e) => setForm({ ...form, note: e.target.value })} />
                  </Field>
                </div>
                <Advanced label={`이 자료의 열 ${ds.columns.length}개`}>
                  <ul className="grid grid-cols-1 gap-x-lg gap-y-0.5 text-[11.5px] md:grid-cols-2">
                    {ds.columns.map((c) => (
                      <li key={c.name}>
                        <code className="font-mono text-charcoal">{c.name}</code> <span className="text-stone">{c.label}</span>
                      </li>
                    ))}
                  </ul>
                </Advanced>
              </div>
            ) : cls ? (
              <div className="flex flex-col gap-md">
                <div className="grid grid-cols-1 gap-md md:grid-cols-3">
                  <div className="md:col-span-3">
                    <Field label="제목" htmlFor="up-title">
                      <input id="up-title" className="input !h-9 text-[13px]" value={form.title} maxLength={200} onChange={(e) => setForm({ ...form, title: e.target.value })} />
                    </Field>
                  </div>
                  <Field label="발행 기관(선택)" htmlFor="up-issuer">
                    <input id="up-issuer" className="input !h-9 text-[13px]" value={form.issuer} onChange={(e) => setForm({ ...form, issuer: e.target.value })} />
                  </Field>
                  <Field label="시행일(선택)" htmlFor="up-pub">
                    <input id="up-pub" className="input !h-9 text-[13px]" type="date" value={form.published_at} onChange={(e) => setForm({ ...form, published_at: e.target.value })} />
                  </Field>
                  <Field label="메모(선택)" htmlFor="up-dnote">
                    <input id="up-dnote" className="input !h-9 text-[13px]" value={form.note} maxLength={500} onChange={(e) => setForm({ ...form, note: e.target.value })} />
                  </Field>
                </div>
                <Field label="파일" htmlFor="up-dfile" hint={`${opts.accept.document} · 스캔 PDF 는 글자 인식(OCR) 후 올려 주세요`}>
                  <input key={fileKey} id="up-dfile" type="file" accept={opts.accept.document} onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="text-[12.5px]" />
                </Field>
                {!file ? (
                  <Field label="또는 본문 붙여 넣기" htmlFor="up-text">
                    <textarea id="up-text" className="input text-[12.5px]" rows={4} value={form.text} onChange={(e) => setForm({ ...form, text: e.target.value })} />
                  </Field>
                ) : null}
              </div>
            ) : null}
          </Step>

          <Step n={3} title="검사 후 승인 요청">
            <p className="mb-md text-[12.5px] leading-relaxed text-steel">
              보내면 바로 보안 · 형식 · 품질 검사를 합니다. 품질 검사에 실패한 자료는 요청되지 않습니다. 관리자가 승인해야 화면 수치와 분석에 반영됩니다.
            </p>
            <Button variant="confirm" disabled={!ready || busy} onClick={submit} data-upload-submit>
              {busy ? "검사 중…" : "검사하고 승인 요청"}
            </Button>
            {failure ? (
              <div className="mt-md">
                <Notice tone="critical" title="요청하지 못했습니다">
                  {failure}
                </Notice>
              </div>
            ) : null}
            {last ? (
              <div className="mt-md flex flex-col gap-xs rounded-xl border border-success-line bg-success-faint p-md" data-upload-last role="status">
                <p className="flex flex-wrap items-center gap-xs text-[13px] font-bold text-ink-deep">
                  요청 #{last.id} · {last.targetLabel} <RequestStatus r={last} />
                </p>
                <RequestPreview r={last} showSample />
              </div>
            ) : null}
          </Step>
        </ol>
      </section>

      <aside aria-label="내 요청" className="rounded-2xl border border-hairline-soft bg-canvas p-lg">
        <div className="mb-md flex items-center justify-between">
          <h2 className="text-[15px] font-bold text-ink-deep">내 요청</h2>
          <Button size="sm" variant="quiet" onClick={() => loadMine().catch(() => undefined)}>
            새로고침
          </Button>
        </div>
        {!mine ? (
          <p className="text-[12.5px] text-stone">불러오는 중…</p>
        ) : !mine.length ? (
          <EmptyState compact title="아직 요청이 없습니다" description="자료를 올리면 승인 상태가 여기에 보입니다." />
        ) : (
          <ul className="flex flex-col divide-y divide-hairline-soft" data-my-uploads>
            {mine.map((r) => (
              <li key={r.id} className="py-2.5">
                <p className="flex flex-wrap items-center gap-1.5">
                  <RequestStatus r={r} />
                  <span className="text-[12.5px] font-bold text-ink-deep">{r.targetLabel}</span>
                </p>
                <p className="mt-0.5 truncate text-[11.5px] text-steel" title={r.fileName}>
                  #{r.id} · {r.kind === "document" ? r.meta.title : r.fileName}
                </p>
                <p className="text-[11px] text-stone">
                  {fmtDateTime(r.createdAt)}
                  {r.reviewedAt ? ` · 처리 ${fmtDateTime(r.reviewedAt)}${r.reviewedByName ? ` (${r.reviewedByName})` : ""}` : ""}
                </p>
                {r.status === "rejected" && r.reviewNote ? <p className="mt-0.5 text-[11.5px] text-critical">반려 사유: {r.reviewNote}</p> : null}
                {r.status === "failed" && r.result.error ? <p className="mt-0.5 text-[11.5px] text-critical">{r.result.error}</p> : null}
                {r.status === "approved" && r.kind === "document" ? (
                  <Link href={`/knowledge/${r.target}`} className="mt-0.5 inline-block text-[11.5px] font-bold text-primary">
                    문서 목록에서 보기
                  </Link>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </aside>
    </div>
  );
}
