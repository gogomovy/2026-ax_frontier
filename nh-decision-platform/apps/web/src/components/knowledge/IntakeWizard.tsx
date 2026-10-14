"use client";

/*
 * 자료 등록 (Phase M · 요구사항 §31 DOB-01~06 · Q191~Q197)
 * 파일(또는 붙여 넣은 본문) → 정형/비정형 판별 → 에이전트 분석(정의 · 문서 정보 초안) → 확인 · 고치기 → 반영(책임자 · 관리자) 또는 승인 요청 → 반영 상태(3-way 저장 · 온톨로지 구축).
 * 같은 구성 요소를 업무 [자료 올리기 › 자료 등록]과 관리자 [데이터셋·문서 › 자료 등록]에 둔다.
 */

import clsx from "clsx";
import { Fragment, useEffect, useRef, useState } from "react";
import { Connector, Step, type StepState } from "@/components/admin/flowViz";
import { Notice } from "@/components/ui/Layout";
import { Badge, Button } from "@/components/ui/primitives";
import { api, apiPatch, apiPost } from "@/lib/api-client";

type ColType = "str" | "int" | "num" | "date" | "bool";
interface DefColumn { name: string; label: string; type: ColType; required?: boolean; aliases?: string[] }
interface Definition {
  code: string; name: string; origin: "bank" | "ext"; kind: string; description: string; file_pattern: string | null; refresh_cycle: string | null;
  columns: DefColumn[]; key_columns: string[]; as_of_column: string | null; quality_rules?: unknown[]; parser?: Record<string, unknown>;
}
interface Quality { status?: string; checks?: { rule: string; passed: boolean; detail?: string; severity?: string; column?: string }[] }
interface DocInfo { title: string; doc_class: string; issuer: string | null; published_at: string | null; origin: "bank" | "ext"; summary?: string }
interface Analysis {
  kind: "structured" | "unstructured"; mode: "new" | "existing" | "document"; target: string; targetName?: string; origin: string;
  matches?: { code: string; name: string; score: number; why: string[] }[]; headers?: string[];
  definition?: Definition; samples?: Record<string, string[]>; semantics?: { columns?: Record<string, { meaning?: string }>; entity?: string | null; by?: string };
  profile?: { rows: number; keyCandidates: unknown[]; measures: string[]; dimensions: string[] };
  quality?: Quality; rows?: number; notes?: string[]; llm?: { by?: string; model?: string | null; reason?: string | null };
  document?: DocInfo; classes?: { code: string; label: string; origin: string }[]; chars?: number; pages?: number; excerpt?: string;
}
interface StorageStage { key: string; label: string; state: StepState | "done"; detail: string }
interface Intake {
  id: number; kind: "dataset" | "document"; target: string; targetLabel: string; origin: string; fileName: string; status: string; statusLabel: string;
  meta: { proposal?: Definition; asOf?: string | null; title?: string; issuer?: string | null; publishedAt?: string | null };
  result: Record<string, unknown> & { error?: string; via?: string; version?: number; rows?: number; createdDataset?: string; documentId?: number };
  intake: Analysis; canApply: boolean; applyMode: "apply" | "request"; storage: StorageStage[]; createdAt: string; reviewNote?: string | null;
}
interface MineItem { id: number; kind: string; targetLabel: string; fileName: string; status: string; statusLabel: string; mode?: string; createdAt: string }

const TYPE_LABEL: Record<ColType, string> = { str: "문자", int: "정수", num: "소수", date: "날짜", bool: "예/아니오" };
const STATUS_TONE: Record<string, "info" | "success" | "neutral" | "critical" | "attention"> = { draft: "info", pending: "attention", approved: "success", failed: "critical", rejected: "neutral", discarded: "neutral" };
const ACCEPT = ".csv,.xlsx,.json,.pdf,.docx,.txt,.md,.hwpx";

function fmt(iso?: string | null) {
  if (!iso) return "-";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : `${d.getMonth() + 1}.${d.getDate()} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

export function IntakeWizard({ context = "business" }: { context?: "business" | "admin" }) {
  const [file, setFile] = useState<File | null>(null);
  const [text, setText] = useState("");
  const [title, setTitle] = useState("");
  const [origin, setOrigin] = useState<"bank" | "ext">("bank");
  const [paste, setPaste] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [item, setItem] = useState<Intake | null>(null);
  const [mine, setMine] = useState<{ items: MineItem[]; applyMode: string } | null>(null);
  const [drag, setDrag] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const loadMine = async () => {
    try {
      setMine(await api("/db/intake/mine"));
    } catch {
      setMine(null);
    }
  };
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadMine();
  }, []);

  const act = async (fn: () => Promise<Intake | void>) => {
    setBusy(true);
    setError(null);
    try {
      const r = await fn();
      if (r) setItem(r);
      void loadMine();
    } catch (e) {
      setError((e as Error).message || "처리하지 못했습니다");
    } finally {
      setBusy(false);
    }
  };

  const analyze = () =>
    act(async () => {
      const fd = new FormData();
      if (file && !paste) fd.append("file", file);
      else {
        fd.append("text", text);
        if (title.trim()) fd.append("title", title.trim());
      }
      fd.append("origin", origin);
      return api<Intake>("/db/intake", { method: "POST", body: fd });
    });

  const reset = () => {
    setItem(null);
    setFile(null);
    setText("");
    setTitle("");
    setError(null);
    if (inputRef.current) inputRef.current.value = "";
  };

  return (
    <section className="flex flex-col gap-lg" aria-label="자료 등록" data-intake-wizard={context}>
      <ol className="grid grid-cols-1 gap-xs text-[12px] md:grid-cols-4" aria-label="자료 등록 단계">
        {["자료 놓기", "에이전트 분석", "확인 · 반영", "반영 상태"].map((s, i) => {
          const at = !item ? 0 : item.status === "draft" ? 2 : 3;
          return (
            <li key={s} className={clsx("rounded-xl border px-md py-2", i === at ? "border-primary bg-info-faint font-bold text-ink-deep" : i < at ? "border-hairline-soft text-steel" : "border-dashed border-hairline text-stone")} aria-current={i === at ? "step" : undefined}>
              <span className="mr-1 tnum">{i + 1}</span>
              {s}
            </li>
          );
        })}
      </ol>

      {error ? (
        <Notice tone="critical" title="처리하지 못했습니다">
          <p>{error}</p>
        </Notice>
      ) : null}

      {!item ? (
        <div className="rounded-2xl border border-hairline-soft bg-canvas p-lg">
          <div className="mb-md flex flex-wrap items-center gap-xs" role="group" aria-label="자료 넣는 방법">
            <Button size="sm" variant={!paste ? "primary" : "ghost"} aria-pressed={!paste} onClick={() => setPaste(false)}>
              파일
            </Button>
            <Button size="sm" variant={paste ? "primary" : "ghost"} aria-pressed={paste} onClick={() => setPaste(true)}>
              본문 붙여 넣기
            </Button>
            <label className="ml-auto flex shrink-0 items-center gap-1.5 whitespace-nowrap text-[12px] text-charcoal">
              <span className="shrink-0">출처</span>
              <select className="input !h-8 !w-auto min-w-[120px] text-[12.5px]" value={origin} onChange={(e) => setOrigin(e.target.value as "bank" | "ext")}>
                <option value="bank">당행 자료</option>
                <option value="ext">외부 자료</option>
              </select>
            </label>
          </div>
          {!paste ? (
            <div
              className={clsx("flex flex-col items-center justify-center gap-xs rounded-xl border-2 border-dashed px-lg py-xl text-center", drag ? "border-primary bg-info-faint" : "border-hairline bg-surface-soft")}
              onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
              onDragLeave={() => setDrag(false)}
              onDrop={(e) => { e.preventDefault(); setDrag(false); const f = e.dataTransfer.files?.[0]; if (f) setFile(f); }}
            >
              <p className="text-[13.5px] font-bold text-ink-deep">{file ? file.name : "파일을 끌어다 놓거나 고르세요"}</p>
              <p className="text-[12px] text-steel">정형(엑셀 · CSV · JSON)은 열을 분석해 정의를, 비정형(PDF · 워드 · 텍스트)은 제목 · 분류 · 기관 · 시행일을 제안합니다.</p>
              <label className="mt-xs cursor-pointer rounded-lg border border-hairline bg-white px-md py-1.5 text-[12.5px] font-bold text-primary">
                파일 고르기
                <input ref={inputRef} type="file" className="sr-only" accept={ACCEPT} onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
              </label>
            </div>
          ) : (
            <div className="flex flex-col gap-md">
              <label className="text-[12px] font-bold text-charcoal">
                제목(선택)
                <input className="input mt-1 !h-9 w-full text-[13px]" value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} />
              </label>
              <label className="text-[12px] font-bold text-charcoal">
                본문
                <textarea className="input mt-1 w-full text-[12.5px]" rows={8} value={text} onChange={(e) => setText(e.target.value)} />
              </label>
            </div>
          )}
          <div className="mt-md flex flex-wrap items-center gap-xs">
            <Button variant="confirm" disabled={busy || (!paste ? !file : !text.trim())} onClick={analyze} data-intake-analyze>
              {busy ? "분석 중…" : "에이전트로 분석"}
            </Button>
            <span className="text-[11.5px] text-stone">분석만으로는 아무 데이터도 반영되지 않습니다(초안).</span>
          </div>
        </div>
      ) : (
        <IntakeDetail item={item} busy={busy} act={act} onClose={reset} />
      )}

      {mine && mine.items.length ? (
        <div className="rounded-2xl border border-hairline-soft bg-canvas p-lg">
          <p className="mb-xs text-[13px] font-bold text-ink-deep">내 등록 건</p>
          <p className="mb-md text-[11.5px] text-stone">{mine.applyMode === "apply" ? "확인 후 바로 반영됩니다(부서 데이터 책임자 · 관리자)." : "확인 후 승인 요청이 됩니다 — 부서 데이터 책임자나 관리자가 승인하면 반영됩니다."}</p>
          <ul className="flex flex-col gap-1.5 text-[12.5px]">
            {mine.items.slice(0, 12).map((m) => (
              <li key={m.id} className="flex flex-wrap items-center gap-xs">
                <Badge tone={STATUS_TONE[m.status] ?? "neutral"}>{m.statusLabel}</Badge>
                <span className="text-stone tnum">#{m.id}</span>
                <span className="min-w-0 flex-1 truncate text-charcoal">{m.targetLabel} · {m.fileName}</span>
                <span className="text-stone tnum">{fmt(m.createdAt)}</span>
                <button type="button" className="font-bold text-primary" onClick={() => act(() => api<Intake>(`/db/intake/${m.id}`))}>
                  열기
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

function IntakeDetail({ item, busy, act, onClose }: { item: Intake; busy: boolean; act: (fn: () => Promise<Intake | void>) => Promise<void>; onClose: () => void }) {
  const an = item.intake;
  const draft = item.status === "draft";
  const [def, setDef] = useState<Definition | null>(() => item.meta.proposal ?? an.definition ?? null);
  const [doc, setDoc] = useState<DocInfo | null>(() => (an.document ? { ...an.document, title: item.meta.title ?? an.document.title, issuer: item.meta.issuer ?? an.document.issuer, published_at: item.meta.publishedAt ?? an.document.published_at } : null));
  const [asOf, setAsOf] = useState(item.meta.asOf ?? "");
  const [note, setNote] = useState("");
  const dirty = useRef(false);
  const sem = an.semantics?.columns ?? {};

  const save = () =>
    act(() =>
      apiPatch<Intake>(`/db/intake/${item.id}`, {
        ...(item.kind === "dataset" && def && an.mode === "new" ? { definition: def } : {}),
        ...(item.kind === "document" && doc ? { document: doc } : {}),
        ...(item.kind === "dataset" ? { asOf: asOf || "" } : {}),
      }).then((r) => { dirty.current = false; return r; }),
    );
  const submit = () =>
    act(async () => {
      if (dirty.current && draft) await save();
      return apiPost<Intake>(`/db/intake/${item.id}/submit`, { note: note || undefined });
    });
  const setCol = (i: number, p: Partial<DefColumn>) => {
    dirty.current = true;
    setDef((d) => {
      if (!d) return d;
      const old = d.columns[i];
      const renamed = p.name !== undefined && p.name !== old.name;
      return {
        ...d,
        columns: d.columns.map((c, k) => (k === i ? { ...c, ...p } : c)),
        key_columns: renamed ? d.key_columns.map((k) => (k === old.name ? (p.name as string) : k)) : d.key_columns,
        as_of_column: renamed && d.as_of_column === old.name ? (p.name as string) : d.as_of_column,
      };
    });
  };
  const patchDef = (p: Partial<Definition>) => { dirty.current = true; setDef((d) => (d ? { ...d, ...p } : d)); };
  const patchDoc = (p: Partial<DocInfo>) => { dirty.current = true; setDoc((d) => (d ? { ...d, ...p } : d)); };

  const modeLabel = an.mode === "new" ? "새 자료(정의 만들기)" : an.mode === "existing" ? `기존 자료 '${an.targetName ?? item.targetLabel}' 의 새 버전` : "문서";
  return (
    <div className="flex flex-col gap-lg rounded-2xl border border-hairline-soft bg-canvas p-lg" data-intake-detail={an.mode}>
      <div className="flex flex-wrap items-center gap-xs">
        <Badge tone={STATUS_TONE[item.status] ?? "neutral"}>{item.statusLabel}</Badge>
        <span className="text-[13.5px] font-bold text-ink-deep">#{item.id} {item.fileName}</span>
        <Badge tone="info">{an.kind === "structured" ? "정형" : "비정형"}</Badge>
        <span className="text-[12px] text-steel">{modeLabel}</span>
        <span className="ml-auto max-w-[420px] truncate text-[11.5px] text-stone" title={an.llm?.reason ?? undefined}>
          분석: {an.llm?.by === "llm" ? `에이전트(${an.llm.model ?? "LLM"})` : `규칙${an.llm?.reason ? " — AI 모델을 쓰지 못해 규칙으로 분석했습니다" : ""}`}
        </span>
      </div>

      {(an.notes ?? []).length ? (
        <ul className="list-disc pl-5 text-[12px] text-attention" aria-label="확인할 내용">
          {(an.notes ?? []).map((n, i) => <li key={i}>{n}</li>)}
        </ul>
      ) : null}

      {item.kind === "dataset" && an.mode === "new" && def ? (
        <div className="flex flex-col gap-md">
          <div className="grid grid-cols-1 gap-md md:grid-cols-4">
            <label className="text-[12px] font-bold text-charcoal">
              코드
              <input className="input mt-1 !h-9 w-full font-mono text-[12.5px]" value={def.code} disabled={!draft} maxLength={60} onChange={(e) => patchDef({ code: e.target.value.trim() })} />
            </label>
            <label className="text-[12px] font-bold text-charcoal md:col-span-3">
              이름
              <input className="input mt-1 !h-9 w-full text-[13px]" value={def.name} disabled={!draft} maxLength={150} onChange={(e) => patchDef({ name: e.target.value })} />
            </label>
            <label className="text-[12px] font-bold text-charcoal md:col-span-4">
              설명
              <input className="input mt-1 !h-9 w-full text-[13px]" value={def.description} disabled={!draft} maxLength={500} onChange={(e) => patchDef({ description: e.target.value })} />
            </label>
          </div>
          {an.semantics?.entity ? <p className="text-[12px] text-steel">행 하나가 가리키는 대상: <b className="text-ink">{an.semantics.entity}</b> · 행 {an.profile?.rows?.toLocaleString("ko-KR") ?? an.rows}개를 읽어 판단했습니다.</p> : null}
          <div className="max-w-full overflow-x-auto">
            <table className="w-full min-w-[720px] border-collapse text-[12px]">
              <caption className="sr-only">분석한 열 정의 — 업무 이름 · 열 이름 · 타입 · 키 · 기준일 · 의미</caption>
              <thead>
                <tr className="bg-surface-soft text-left">
                  <th scope="col" className="px-2 py-1.5 font-bold text-charcoal">업무 이름</th>
                  <th scope="col" className="px-2 py-1.5 font-bold text-charcoal">열 이름</th>
                  <th scope="col" className="px-2 py-1.5 font-bold text-charcoal">타입</th>
                  <th scope="col" className="px-2 py-1.5 text-center font-bold text-charcoal">키</th>
                  <th scope="col" className="px-2 py-1.5 text-center font-bold text-charcoal">기준일</th>
                  <th scope="col" className="px-2 py-1.5 font-bold text-charcoal">의미(에이전트)</th>
                  <th scope="col" className="px-2 py-1.5 font-bold text-charcoal">예시(가림)</th>
                </tr>
              </thead>
              <tbody>
                {def.columns.map((c, i) => (
                  <tr key={i} className="border-b border-hairline-soft align-top">
                    <td className="px-2 py-1">
                      <input aria-label={`${c.name} 업무 이름`} className="input !h-8 w-full min-w-[110px] text-[12px]" value={c.label} disabled={!draft} onChange={(e) => setCol(i, { label: e.target.value })} />
                    </td>
                    <td className="px-2 py-1">
                      <input aria-label={`${c.label} 열 이름`} className="input !h-8 w-full min-w-[110px] font-mono text-[12px]" value={c.name} disabled={!draft} onChange={(e) => setCol(i, { name: e.target.value.trim() })} />
                    </td>
                    <td className="px-2 py-1">
                      <select aria-label={`${c.label} 타입`} className="input !h-8 text-[12px]" value={c.type} disabled={!draft} onChange={(e) => setCol(i, { type: e.target.value as ColType })}>
                        {Object.entries(TYPE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                      </select>
                    </td>
                    <td className="px-2 py-1.5 text-center">
                      <input type="checkbox" aria-label={`${c.label} 키 열`} disabled={!draft} checked={def.key_columns.includes(c.name)}
                        onChange={() => patchDef({ key_columns: def.key_columns.includes(c.name) ? def.key_columns.filter((k) => k !== c.name) : [...def.key_columns, c.name], columns: def.columns.map((x) => (x.name === c.name ? { ...x, required: true } : x)) })} />
                    </td>
                    <td className="px-2 py-1.5 text-center">
                      <input type="radio" name={`as-of-${item.id}`} aria-label={`${c.label} 기준일 열`} disabled={!draft} checked={def.as_of_column === c.name} onChange={() => patchDef({ as_of_column: c.name })} />
                    </td>
                    <td className="px-2 py-1.5 text-charcoal">{sem[c.name]?.meaning ?? "-"}</td>
                    <td className="px-2 py-1.5 font-mono text-[11px] text-stone">{(an.samples?.[c.name] ?? []).slice(0, 3).join(" · ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}

      {item.kind === "dataset" && an.mode === "existing" ? (
        <div className="flex flex-col gap-xs text-[12.5px]">
          <p className="text-charcoal">
            <b>{an.targetName ?? item.targetLabel}</b> 정의로 같은 품질 검사(직전 버전 대비)를 미리 했습니다 — 행 {(an.rows ?? 0).toLocaleString("ko-KR")}개 · 검사 <QualityText q={an.quality} />
          </p>
          {(an.matches ?? []).length > 1 && draft ? (
            <label className="flex flex-wrap items-center gap-xs text-[12px] text-charcoal">
              다른 자료로 올리기
              <select className="input !h-8 text-[12.5px]" value={item.target} onChange={(e) => act(() => apiPatch<Intake>(`/db/intake/${item.id}`, { target: e.target.value }))}>
                {(an.matches ?? []).map((m) => <option key={m.code} value={m.code}>{m.name} ({Math.round(m.score * 100)}점 · {m.why.join(", ")})</option>)}
              </select>
            </label>
          ) : null}
        </div>
      ) : null}

      {item.kind === "dataset" && an.mode === "new" ? (
        <p className="text-[12.5px] text-charcoal">미리 한 품질 검사: <QualityText q={an.quality} /> · 행 {(an.rows ?? 0).toLocaleString("ko-KR")}개</p>
      ) : null}

      {item.kind === "dataset" ? (
        <label className="max-w-[260px] text-[12px] font-bold text-charcoal">
          기준일(선택 — 비우면 파일의 기준일 열)
          <input className="input mt-1 !h-9 w-full text-[13px]" type="date" value={asOf ?? ""} disabled={!draft} onChange={(e) => { dirty.current = true; setAsOf(e.target.value); }} />
        </label>
      ) : null}

      {item.kind === "document" && doc ? (
        <div className="grid grid-cols-1 gap-md md:grid-cols-4">
          <label className="text-[12px] font-bold text-charcoal md:col-span-4">
            제목
            <input className="input mt-1 !h-9 w-full text-[13px]" value={doc.title} disabled={!draft} maxLength={200} onChange={(e) => patchDoc({ title: e.target.value })} />
          </label>
          <label className="text-[12px] font-bold text-charcoal">
            문서 분류
            <select className="input mt-1 !h-9 w-full text-[13px]" value={doc.doc_class} disabled={!draft} onChange={(e) => patchDoc({ doc_class: e.target.value })}>
              {(an.classes ?? []).map((c) => <option key={c.code} value={c.code}>{c.label}</option>)}
            </select>
          </label>
          <label className="text-[12px] font-bold text-charcoal">
            발행 기관
            <input className="input mt-1 !h-9 w-full text-[13px]" value={doc.issuer ?? ""} disabled={!draft} onChange={(e) => patchDoc({ issuer: e.target.value || null })} />
          </label>
          <label className="text-[12px] font-bold text-charcoal">
            시행일
            <input className="input mt-1 !h-9 w-full text-[13px]" type="date" value={doc.published_at ?? ""} disabled={!draft} onChange={(e) => patchDoc({ published_at: e.target.value || null })} />
          </label>
          <label className="text-[12px] font-bold text-charcoal">
            출처
            <select className="input mt-1 !h-9 w-full text-[13px]" value={doc.origin} disabled={!draft} onChange={(e) => patchDoc({ origin: e.target.value as "bank" | "ext" })}>
              <option value="bank">당행 문서</option>
              <option value="ext">외부 기관 문서</option>
            </select>
          </label>
          {an.document?.summary ? <p className="text-[12.5px] text-steel md:col-span-4">요약(에이전트): {an.document.summary}</p> : null}
          {an.excerpt ? <p className="max-h-[120px] overflow-auto rounded-lg bg-surface-soft p-md text-[12px] leading-relaxed text-charcoal md:col-span-4">{an.excerpt}</p> : null}
          <p className="text-[11.5px] text-stone md:col-span-4">본문 {an.chars?.toLocaleString("ko-KR")}자 · {an.pages}면</p>
        </div>
      ) : null}

      {item.result?.error ? <p className="text-[12.5px] text-critical">반영 실패: {String(item.result.error)}</p> : null}

      {draft ? (
        <div className="flex flex-wrap items-end gap-xs border-t border-hairline-soft pt-md">
          <label className="min-w-[240px] flex-1 text-[12px] font-bold text-charcoal">
            메모(선택)
            <input className="input mt-1 !h-9 w-full text-[13px]" value={note} maxLength={500} onChange={(e) => setNote(e.target.value)} />
          </label>
          <Button variant="quiet" disabled={busy} onClick={save}>고친 내용 저장</Button>
          <Button variant="confirm" disabled={busy} onClick={submit} data-intake-submit>
            {item.applyMode === "apply" ? "확인 · 반영" : "승인 요청"}
          </Button>
          <Button variant="ghost" disabled={busy} onClick={() => act(async () => { await apiPost(`/db/intake/${item.id}/discard`); return api<Intake>(`/db/intake/${item.id}`); })}>
            버리기
          </Button>
        </div>
      ) : null}

      {item.storage.length ? <StoragePipeline stages={item.storage} /> : null}

      <div className="flex flex-wrap gap-xs">
        {!draft ? <Button size="sm" variant="quiet" disabled={busy} onClick={() => act(() => api<Intake>(`/db/intake/${item.id}`))}>상태 새로 보기</Button> : null}
        <Button size="sm" variant="ghost" onClick={onClose}>다른 자료 등록</Button>
      </div>
    </div>
  );
}

function QualityText({ q }: { q?: Quality }) {
  const st = q?.status;
  const fails = (q?.checks ?? []).filter((c) => !c.passed);
  return (
    <span>
      <Badge tone={st === "passed" ? "success" : st === "warning" ? "attention" : st === "failed" ? "critical" : "neutral"}>{st === "passed" ? "통과" : st === "warning" ? "주의" : st === "failed" ? "실패" : "-"}</Badge>
      {fails.length ? <span className="ml-1 text-[11.5px] text-steel">{fails.slice(0, 3).map((c) => `${c.rule}${c.column ? `(${c.column})` : ""}`).join(" · ")}</span> : null}
    </span>
  );
}

/** 반영 상태 — 원장 · 임베딩 · 검색 색인 · 온톨로지 · 그래프 · 이어진 워크플로 (DOB-06) */
function StoragePipeline({ stages }: { stages: StorageStage[] }) {
  const LABEL: Record<string, string> = { done: "완료", active: "진행 중", warn: "확인 필요", skip: "건너뜀", idle: "대기", fail: "실패" };
  return (
    <div>
      <p className="mb-xs text-[12.5px] font-bold text-ink">반영 상태</p>
      <ol className="flex flex-wrap items-stretch gap-y-xs" aria-label="반영 상태 단계">
        {stages.map((s, i) => (
          <Fragment key={s.key}>
            <li className="w-[188px]">
              <Step title={s.label} state={s.state as StepState} stateLabel={LABEL[s.state] ?? s.state} dataKey={s.key} className="h-full">
                <span className="block text-[11.5px] leading-snug text-charcoal">{s.detail}</span>
              </Step>
            </li>
            {i < stages.length - 1 ? (
              <li aria-hidden="true" className="flex">
                <Connector />
              </li>
            ) : null}
          </Fragment>
        ))}
      </ol>
    </div>
  );
}
