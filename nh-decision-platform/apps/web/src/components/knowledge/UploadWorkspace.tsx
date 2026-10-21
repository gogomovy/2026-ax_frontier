"use client";

import clsx from "clsx";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { NewDatasetPanel, definitionPayload, type PanelSubmit } from "@/components/knowledge/NewDatasetPanel";
import { useApiSession } from "@/components/providers/SessionProvider";
import { useUi } from "@/components/providers/UiProvider";
import { FileDrop } from "@/components/ui/FileDrop";
import { Advanced, EmptyState, KeyValueList, Notice } from "@/components/ui/Layout";
import { Badge, Button } from "@/components/ui/primitives";
import { api } from "@/lib/api-client";
import { confidentSuggestion, kindOfContent, suggestDatasets, titleFromFile, type DatasetSuggestion } from "@/lib/upload-match";

/*
 * 업무 자료 올리기 (Phase C · UPL-01~03 · Q99 → Phase E · UXF-01~05 · Q121)
 * ① 파일 올리기(끌어다 놓기 · 고르기) → ② 무엇인지 확인(파일 이름으로 추천 · 근거, 사용자가 바꿀 수 있음)
 * → ③ 기준 정보 → ④ 검사 후 승인 요청. 부서 데이터 책임자 또는 관리자가 승인하면 반영.
 * 아래 '내 요청' 에서 상태(승인 대기 · 승인 · 반려 · 실패)를 본다. `?target=코드` 로 들어오면 그 자료를 미리 고른다.
 */

/** 승인 주체 문구 — 화면 여러 곳이 같은 말을 쓴다 (Phase E · TXT-01) */
export const APPROVER_TEXT = "부서 데이터 책임자 또는 관리자";
/** 처음 보이는 자료 수 — 나머지는 [전체 목록 보기] (Phase E · LAY-01) */
const LIST_HEAD = 6;

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
  /** 맞는 자료가 없을 때 파일에서 추론한 정의로 새 종류 자료를 제안할 수 있는가 (설정 upload.user_targets.new_datasets) */
  canPropose?: boolean;
  accept: { dataset: string; document: string };
  /** 업로드 용량 한도(설정 upload.policy.max_mb) — 파일 놓기 영역이 먼저 알려 준다 */
  maxMb?: number;
}
interface Check {
  rule: string;
  passed: boolean;
  detail: string;
  severity: string;
}
/** 반영 미리보기 (Phase P · UPV-02) — 이 파일이 같은 자료의 어느 판으로 들어가는지 */
export interface Placement {
  typedAsOf: string | null;
  versionAsOf: string | null;
  fileFrom: string | null;
  fileTo: string | null;
  fileDates: number;
  noAsOfColumn: boolean;
  action: "add" | "replace";
  replaces: { version: number; asOf: string | null; memo: string | null; rows: number; committedAt: string | null } | null;
  overlaps: { asOf: string; version: number }[];
  duplicateOf: { version: number } | null;
  existing: { asOf: string | null; version: number; rows: number; memo: string | null }[];
  messages: string[];
}

/** 반영 미리보기 — 새 기준일로 추가 / 같은 기준일 판 교체 · 겹치는 기간 · 같은 파일 */
export function PlacementNote({ p }: { p: Placement }) {
  const tone = p.duplicateOf ? "attention" : p.action === "replace" ? "attention" : "info";
  const title = p.duplicateOf
    ? `같은 파일이 이미 현재 판(v${p.duplicateOf.version})입니다`
    : p.action === "replace"
      ? `같은 기준일(${p.replaces?.asOf ?? "기준일 없음"}) 판 v${p.replaces?.version} 을(를) 교체합니다`
      : `새 기준일(${p.versionAsOf ?? "기준일 없음"})로 추가합니다`;
  return (
    <Notice tone={tone} title={title}>
      <span data-upload-placement={p.action}>
        {p.fileFrom ? `파일 기간 ${p.fileFrom === p.fileTo ? p.fileFrom : `${p.fileFrom} ~ ${p.fileTo} (${p.fileDates}개)`}. ` : ""}
        {p.messages.join(" ")}
      </span>
    </Notice>
  );
}

export interface UploadReq {
  id: number;
  kind: "dataset" | "document";
  target: string;
  targetLabel: string;
  origin: string;
  fileName: string;
  meta: Record<string, string | null> & { proposal?: { code: string; name: string; columns: { name: string; label: string; type: string; required?: boolean }[]; key_columns: string[]; as_of_column: string | null } };
  preview: { rows?: number; quality?: { status?: string; checks?: Check[] }; chars?: number; pages?: number; excerpt?: string; headers?: string[]; columns?: string[]; sample?: Record<string, unknown>[]; placement?: Placement | null };
  status: "pending" | "approved" | "rejected" | "failed";
  statusLabel: string;
  requestedBy: string;
  requestedByName?: string | null;
  requestedOrgName?: string | null;
  reviewedByName?: string | null;
  reviewedAt: string | null;
  reviewNote: string | null;
  result: { version?: number; rows?: number; docCode?: string; error?: string; isCurrent?: boolean; via?: "admin" | "steward"; createdDataset?: string };
  /** 부서 데이터 책임자 검토 목록 — 이 사람이 처리할 수 있는지(본인 요청 제외) */
  canReview?: boolean;
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
      {r.preview.placement ? <PlacementNote p={r.preview.placement} /> : null}
      <KeyValueList
        dense
        items={[
          { label: "행", value: `${(r.preview.rows ?? 0).toLocaleString("ko-KR")}행` },
          { label: "품질 검사", value: <QualityBadge status={r.preview.quality?.status} />, hint: checks.length ? `${checks.length}개 중 통과 ${checks.length - notPassed.length}` : undefined },
          ...(r.meta.asOf ? [{ label: "기준일", value: r.meta.asOf }] : r.preview.placement?.versionAsOf ? [{ label: "기준일", value: `${r.preview.placement.versionAsOf} (파일 기간에서)` }] : []),
          ...(r.meta.note ? [{ label: "메모", value: r.meta.note }] : []),
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
        {done ? "✓" : n}
      </span>
      <h2 className="mb-md pt-1 text-[15px] font-bold text-ink-deep">
        <span className="sr-only">
          {n}단계{done ? "(완료)" : ""} ·{" "}
        </span>
        {title}
      </h2>
      {children}
    </li>
  );
}

function versionText(d: DatasetOpt) {
  const c = d.current[0];
  return c ? `현재 v${c.version}${c.asOf ? ` · ${c.asOf.slice(0, 10)}` : ""} · ${c.rows.toLocaleString("ko-KR")}행` : "현재 자료 없음";
}

/** 추천으로 표시할 최소 점수 — 낱말 하나(예: '상품')만 겹치는 것은 잡음이라 뺀다. '추천' 배지는 확실한 것(50 이상)만 */
const SHOW_MIN = 20;
const STRONG_MIN = 50;

/** 자료 고르기 단추(라디오) — 추천 근거를 함께 보인다 */
function DatasetOption({ d, on, onPick, suggestion }: { d: DatasetOpt; on: boolean; onPick: () => void; suggestion?: DatasetSuggestion }) {
  const strong = Boolean(suggestion && suggestion.score >= STRONG_MIN);
  return (
    <button
      type="button"
      role="radio"
      aria-checked={on}
      onClick={onPick}
      className={clsx("w-full rounded-xl border px-md py-2.5 text-left transition-colors", on ? "border-primary bg-info-faint ring-1 ring-primary" : "border-hairline-soft hover:bg-surface-soft")}
      data-upload-target={d.code}
      data-upload-suggested={suggestion ? (strong ? "strong" : "weak") : undefined}
    >
      <span className="flex flex-wrap items-center gap-1.5">
        <span className="text-[13px] font-bold text-ink-deep">{d.name}</span>
        <Badge tone={d.origin === "bank" ? "dark" : "info"}>{d.origin === "bank" ? "당행" : "외부"}</Badge>
        {suggestion ? strong ? <Badge tone="success">추천</Badge> : <Badge>이름 비슷</Badge> : null}
      </span>
      <span className="mt-0.5 block font-mono text-[10.5px] text-stone">{d.code}</span>
      <span className="mt-0.5 block text-[11.5px] text-steel">
        {versionText(d)}
        {d.refreshCycle ? ` · ${d.refreshCycle} 갱신` : ""}
      </span>
      {suggestion ? <span className={clsx("mt-0.5 block text-[11.5px]", strong ? "font-bold text-success" : "text-steel")}>근거: {suggestion.reasons.join(" · ")}</span> : null}
    </button>
  );
}

interface PeriodRow {
  version: number;
  asOf: string | null;
  rows: number;
  memo: string | null;
  committedAt: string | null;
  requestedByName?: string | null;
  owner: { code: string; name: string } | null;
}

/** 보관 중인 기준일 (Phase P · UPV-07) — 이 자료의 현재 판(기준일마다 하나 · 영업점 자료는 영업점마다) */
function PeriodList({ code }: { code: string }) {
  const [data, setData] = useState<{ asOfColumn: string | null; periods: PeriodRow[] } | null>(null);
  useEffect(() => {
    let alive = true;
    api<{ asOfColumn: string | null; periods: PeriodRow[] }>(`/db/datasets/${encodeURIComponent(code)}/periods`)
      .then((d) => alive && setData(d))
      .catch(() => alive && setData(null));
    return () => {
      alive = false;
    };
  }, [code]);
  if (!data) return null;
  if (!data.periods.length) return <p className="text-[12px] text-stone">아직 반영된 판이 없습니다 — 이 파일이 첫 판이 됩니다.</p>;
  return (
    <div data-upload-periods={data.periods.length}>
      <p className="mb-1 text-[12px] font-bold text-steel">
        보관 중인 기준일 {new Set(data.periods.map((p) => p.asOf)).size}개{data.asOfColumn ? "" : " · 기준일 열이 없는 자료(계산은 가장 늦은 기준일 판만)"}
      </p>
      <ul className="flex max-h-[180px] flex-col gap-0.5 overflow-y-auto text-[12px]">
        {[...data.periods].reverse().map((p) => (
          <li key={`${p.version}`} className="flex flex-wrap items-baseline gap-x-2 border-b border-hairline-soft py-1">
            <span className="font-bold text-ink-deep tnum">{p.asOf ?? "기준일 없음"}</span>
            <span className="text-steel tnum">
              v{p.version} · {p.rows.toLocaleString("ko-KR")}행 · {fmtDateTime(p.committedAt)}
            </span>
            {p.owner ? <span className="text-stone">{p.owner.name}</span> : null}
            {p.memo ? <span className="text-charcoal">메모: {p.memo}</span> : null}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function UploadWorkspace({ initial, initialTarget }: { initial: Uploadable; initialTarget?: string }) {
  const { showToast } = useUi();
  const me = useApiSession().user;
  const opts = initial;
  const preset = initialTarget && opts.datasets.some((d) => d.code === initialTarget) ? initialTarget : "";
  const [mine, setMine] = useState<UploadReq[] | null>(null);
  const [mineError, setMineError] = useState<string | null>(null);
  const [kind, setKind] = useState<"dataset" | "document">("dataset");
  const [target, setTarget] = useState(preset);
  // 사용자가 직접(또는 주소로) 고른 자료 — 파일을 바꿔도 추천으로 덮지 않는다
  const [pinned, setPinned] = useState(Boolean(preset));
  const [textMode, setTextMode] = useState(false);
  const [browse, setBrowse] = useState(Boolean(preset));
  const [showAll, setShowAll] = useState(false);
  const [q, setQ] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [autoTitle, setAutoTitle] = useState("");
  const [form, setForm] = useState({ data_origin: "actual", as_of: "", note: "", title: "", issuer: "", published_at: "", text: "" });
  const [busy, setBusy] = useState(false);
  const [last, setLast] = useState<UploadReq | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  // 맞는 자료가 없는 새 종류 파일 — 파일에서 추론한 정의를 확인하고 새 자료로 등록 요청 (DEF-03)
  const [proposing, setProposing] = useState(false);
  // 정의를 미리 만들 필요 없이 올리기(M.24 · DOB-16) — 대상 없이 보내면 서버가 맞는 자료를 찾고, 없으면 파일에서 정의를 만들어 승인 때 등록한다
  const [autoNew, setAutoNew] = useState(false);
  const resultRef = useRef<HTMLDivElement>(null);

  const loadMine = useCallback(async () => {
    setMineError(null);
    try {
      setMine(await api<UploadReq[]>("/db/uploads/mine"));
    } catch (e) {
      setMineError((e as Error).message || "불러오지 못했습니다");
    }
  }, []);
  useEffect(() => {
    let alive = true;
    api<UploadReq[]>("/db/uploads/mine")
      .then((m) => alive && setMine(m))
      .catch((e: Error) => alive && setMineError(e.message || "불러오지 못했습니다"));
    return () => {
      alive = false;
    };
  }, []);
  // 요청 결과로 초점 이동 — 화면 낭독기 · 키보드 사용자가 결과를 바로 듣는다 (UXF-04)
  useEffect(() => {
    if (last) resultRef.current?.focus();
  }, [last]);

  const suggestions = useMemo(() => (file && kind === "dataset" ? suggestDatasets(file.name, opts.datasets).filter((s) => s.score >= SHOW_MIN) : []), [file, kind, opts.datasets]);
  const sugMap = useMemo(() => new Map(suggestions.map((s) => [s.code, s])), [suggestions]);
  const best = confidentSuggestion(suggestions);
  const ds = opts.datasets.find((d) => d.code === target) ?? null;
  const cls = opts.docClasses.find((c) => c.key === target) ?? null;

  const ordered = useMemo(() => {
    const low = q.trim().toLowerCase();
    const hit = opts.datasets.filter((d) => !low || `${d.code} ${d.name} ${d.description}`.toLowerCase().includes(low));
    // 추천(점수 순) → 고른 자료 → 나머지(원래 순서)
    const rank = (d: DatasetOpt) => (sugMap.has(d.code) ? 0 : d.code === target ? 1 : 2);
    return [...hit].sort((a, b) => rank(a) - rank(b) || (sugMap.get(b.code)?.score ?? 0) - (sugMap.get(a.code)?.score ?? 0));
  }, [opts.datasets, q, sugMap, target]);
  const visible = showAll || q.trim() ? ordered : ordered.slice(0, LIST_HEAD);

  const pickFile = async (f: File | null) => {
    setFailure(null);
    setFile(f);
    setProposing(false);
    if (!f) {
      if (!pinned && kind === "dataset") setTarget("");
      setAutoNew(false);
      return;
    }
    setTextMode(false);
    // .md 는 내용으로 구분 — 표가 있으면 정형 자료(DRM 엑셀을 변환한 파일), 없으면 문서 (Phase Q · MD-04). 표 기호는 ASCII 라 인코딩과 관계없다
    const mdText = /\.md$/i.test(f.name) ? await f.text().catch(() => null) : null;
    const k = kindOfContent(f.name, mdText, opts.accept) ?? "dataset";
    if (k === "document") {
      if (kind !== "document") {
        setKind("document");
        setTarget("");
        setPinned(false);
      }
      const t = titleFromFile(f.name);
      // 제목이 비었거나 이전 파일 이름에서 채운 그대로면 새 파일 이름으로
      if (!form.title.trim() || form.title === autoTitle) setForm((x) => ({ ...x, title: t }));
      setAutoTitle(t);
      return;
    }
    // 정형 자료 — 직접 고른 자료가 없으면 확실한 추천(이름 규칙 · 코드 · 보고서 번호)을 골라 둔다(확정은 사용자가 · Q121)
    const wasDoc = kind !== "dataset";
    if (wasDoc) {
      setKind("dataset");
      setPinned(false);
    }
    if (wasDoc || !pinned) {
      const sure = confidentSuggestion(suggestDatasets(f.name, opts.datasets))?.code ?? "";
      setTarget(sure);
      // 확실한 자료가 없으면 '새 종류 자료(정의 자동)'로 — 서버가 머리글로 한 번 더 찾고, 없으면 파일에서 정의를 만든다
      setAutoNew(!sure && Boolean(opts.canPropose));
    }
  };
  const pickTarget = (code: string) => {
    setTarget(code);
    setPinned(true);
    setAutoNew(false);
    setFailure(null);
  };
  const pickAutoNew = () => {
    setTarget("");
    setPinned(true);
    setAutoNew(true);
    setFailure(null);
  };
  const startText = () => {
    setTextMode(true);
    setFile(null);
    setKind("document");
    setTarget("");
    setPinned(false);
  };
  const stopText = () => {
    setTextMode(false);
    setKind("dataset");
    setTarget(preset);
    setPinned(Boolean(preset));
    setForm((x) => ({ ...x, text: "" }));
  };

  const blocker =
    kind === "dataset"
      ? !file
        ? "1단계에서 파일을 고르세요."
        : !ds && !autoNew
          ? "2단계에서 이 파일이 어떤 자료인지 고르세요."
          : null
      : !file && !textMode
        ? "1단계에서 파일을 고르세요."
        : !cls
          ? "2단계에서 문서 분류를 고르세요."
          : !form.title.trim()
            ? "2단계에서 문서 제목을 입력하세요."
            : !file && !form.text.trim()
              ? "3단계에서 문서 본문을 붙여 넣으세요."
              : null;
  const ready = blocker === null;

  const propose = async ({ definition, dataOrigin, note }: PanelSubmit) => {
    if (!file) return;
    setFailure(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("definition", JSON.stringify(definitionPayload(definition)));
      fd.append("data_origin", dataOrigin);
      if (form.as_of) fd.append("as_of", form.as_of);
      if (note) fd.append("note", note);
      const r = await api<UploadReq>("/db/uploads/dataset-proposal", { method: "POST", body: fd });
      setLast(r);
      showToast(`새 종류 자료 등록을 요청했습니다 — ${APPROVER_TEXT}가 승인하면 데이터셋이 만들어지고 이 파일이 첫 버전이 됩니다`, "success");
      setProposing(false);
      setFile(null);
      await loadMine();
    } catch (e) {
      setFailure((e as Error).message);
    }
  };

  const submit = async () => {
    setBusy(true);
    setFailure(null);
    try {
      const fd = new FormData();
      if (file) fd.append("file", file);
      if (kind === "dataset") {
        if (!autoNew) fd.append("target", target);
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
      showToast(
        r.meta?.proposal
          ? `새 종류 자료로 요청했습니다 — ${APPROVER_TEXT}가 승인하면 파일에서 만든 정의로 '${r.meta.proposal.name}' 이(가) 만들어지고 이 파일이 첫 버전이 됩니다`
          : autoNew && kind === "dataset"
            ? `'${r.targetLabel}' 의 새 버전으로 요청했습니다(머리글이 맞는 자료) — ${APPROVER_TEXT}가 승인하면 반영됩니다`
            : `승인 요청을 보냈습니다 — ${APPROVER_TEXT}가 승인하면 반영됩니다`,
        "success",
      );
      setFile(null);
      setAutoNew(false);
      setAutoTitle("");
      setForm((f) => ({ ...f, note: "", title: "", issuer: "", published_at: "", text: "" }));
      await loadMine();
    } catch (e) {
      setFailure((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const acceptAll = `${opts.accept.dataset},${opts.accept.document}`;
  const fmt = (s: string) => s.replaceAll(",", " · ");
  const showChooser = kind === "dataset" && (Boolean(file) || browse || Boolean(target));

  return (
    <div className="grid grid-cols-1 gap-xl xl:grid-cols-[minmax(0,1fr)_380px]">
      <section aria-label="자료 올리기" className="rounded-2xl border border-hairline-soft bg-canvas p-lg" data-upload-workspace>
        <ol className="flex flex-col gap-xl">
          <Step n={1} title="파일 올리기" done={Boolean(file) || (textMode && Boolean(form.text.trim()))}>
            {textMode ? (
              <div className="flex flex-wrap items-center gap-sm rounded-2xl border border-hairline-soft bg-surface-soft px-md py-3">
                <p className="flex-1 text-[12.5px] text-charcoal">파일 없이 문서 본문을 붙여 넣습니다. 3단계에 본문을 넣으세요.</p>
                <Button size="sm" variant="ghost" onClick={stopText}>
                  파일로 올리기
                </Button>
              </div>
            ) : (
              <>
                <FileDrop
                  id="up-file"
                  accept={acceptAll}
                  maxMb={opts.maxMb}
                  file={file}
                  onFile={(f) => void pickFile(f)}
                  label="올릴 파일을 여기로 끌어다 놓거나 눌러서 고르세요"
                  hint={`정형 자료 ${fmt(opts.accept.dataset)} · 문서 ${fmt(opts.accept.document)}${opts.maxMb ? ` · 최대 ${opts.maxMb}MB` : ""} — 파일 이름으로 어떤 자료인지 추천합니다${
                    opts.accept.dataset.includes(".md") ? ". .md 는 표(| 열 | 아래 |---|)가 있으면 정형 자료, 없으면 문서로 올라갑니다(DRM 엑셀을 표로 바꾼 파일)" : ""
                  }`}
                  data-testid="upload"
                />
                {!file ? (
                  <button type="button" onClick={startText} className="mt-sm text-[12px] font-bold text-primary underline-offset-2 hover:underline" data-upload-text-mode>
                    파일 없이 문서 본문 붙여 넣기
                  </button>
                ) : null}
              </>
            )}
          </Step>

          <Step n={2} title={kind === "dataset" ? "어떤 자료인지 확인" : "문서 분류와 제목"} done={kind === "dataset" ? Boolean(ds) || (autoNew && Boolean(file)) : Boolean(cls && form.title.trim())}>
            {kind === "dataset" ? (
              !showChooser ? (
                <div className="flex flex-wrap items-center gap-sm">
                  <p className="text-[12.5px] text-stone">파일을 고르면 파일 이름으로 맞는 자료를 찾아 드립니다.</p>
                  <Button size="sm" variant="quiet" onClick={() => setBrowse(true)} data-upload-browse>
                    목록에서 먼저 고르기
                  </Button>
                </div>
              ) : (
                <div className="flex flex-col gap-sm">
                  {file && best && target === best.code ? (
                    <p className="text-[12.5px] text-success" role="status" data-upload-suggestion>
                      파일 이름으로 <strong className="font-bold">{ds?.name}</strong>을(를) 골라 두었습니다. 맞는지 확인하고, 다르면 아래에서 바꾸세요.
                    </p>
                  ) : null}
                  {file && pinned && best && target !== best.code ? (
                    <Notice tone="attention" title="고른 자료와 파일 이름이 다릅니다">
                      <span>
                        파일 이름은 <strong>{opts.datasets.find((d) => d.code === best.code)?.name}</strong>에 더 가깝습니다({best.reasons.join(" · ")}).{" "}
                      </span>
                      <button type="button" className="font-bold text-primary underline" onClick={() => pickTarget(best.code)} data-upload-use-suggestion>
                        추천 자료로 바꾸기
                      </button>
                    </Notice>
                  ) : null}
                  {file && autoNew ? (
                    <Notice tone="info" title="새 종류 자료로 올립니다 — 정의를 미리 만들 필요가 없습니다">
                      <span data-upload-auto-new>
                        보내면 머리글로 맞는 자료를 한 번 더 찾고, 없으면 파일의 머리글 · 값으로 정의(열 · 타입 · 키 · 기준일)를 만들어 함께 요청합니다. {APPROVER_TEXT}가 승인하면 그 정의로 데이터셋이 만들어지고 이 파일이 첫 버전이
                        됩니다. 다음 달 파일은 같은 자료로 이어집니다. 기존 자료의 새 버전이라면 아래 목록에서 고르세요.{" "}
                      </span>
                      <button type="button" className="font-bold text-primary underline" onClick={() => setProposing(true)} data-upload-propose>
                        만들 정의 미리 보기 · 고치기
                      </button>
                    </Notice>
                  ) : null}
                  {file && !autoNew && !ds && opts.canPropose ? (
                    <div className="flex flex-wrap items-center gap-sm" role="status" data-upload-no-suggestion>
                      <p className="text-[12.5px] text-attention">{suggestions.length ? "추천 자료가 맞지 않으면" : "파일 이름으로 맞는 자료를 찾지 못했습니다."} 아래 목록에서 고르거나 새 종류 자료로 올리세요.</p>
                      <Button size="sm" variant="quiet" onClick={pickAutoNew} data-upload-pick-auto>
                        새 종류 자료로 올리기(정의 자동)
                      </Button>
                    </div>
                  ) : file && !suggestions.length && !target && !autoNew ? (
                    <p className="text-[12.5px] text-attention" role="status">
                      파일 이름으로 맞는 자료를 찾지 못했습니다. 아래 목록에서 고르세요.
                    </p>
                  ) : null}
                  <input className="input !h-9 w-full max-w-[360px] text-[13px]" placeholder="자료 이름 · 코드로 찾기" aria-label="자료 찾기" value={q} onChange={(e) => setQ(e.target.value)} />
                  {visible.length ? (
                    <div className="grid grid-cols-1 gap-xs md:grid-cols-2" role="radiogroup" aria-label="올릴 자료">
                      {visible.map((d) => (
                        <DatasetOption key={d.code} d={d} on={d.code === target} onPick={() => pickTarget(d.code)} suggestion={sugMap.get(d.code)} />
                      ))}
                    </div>
                  ) : (
                    <EmptyState
                      compact
                      title={opts.datasets.length ? "맞는 자료가 없습니다" : "아직 등록된 자료가 없습니다"}
                      description={opts.canPropose ? "그대로 보내면 새 종류 자료로 올라갑니다 — 파일에서 정의를 만들어 승인 때 등록합니다." : "새 종류의 자료라면 관리자에게 데이터셋 등록을 요청하세요."}
                    />
                  )}
                  {opts.canPropose && file && proposing ? (
                    <NewDatasetPanel file={file} inferPath="/db/uploads/dataset-infer" submitLabel="이 정의로 새 자료 등록 요청" onSubmit={propose} onClose={() => setProposing(false)} />
                  ) : null}
                  {!q.trim() && ordered.length > LIST_HEAD ? (
                    <div>
                      <Button size="sm" variant="ghost" onClick={() => setShowAll((v) => !v)} aria-pressed={showAll} data-upload-show-all>
                        {showAll ? "접기" : `전체 목록 보기 (${ordered.length}개)`}
                      </Button>
                    </div>
                  ) : null}
                </div>
              )
            ) : (
              <div className="flex flex-col gap-md">
                <div className="flex flex-wrap gap-xs" role="radiogroup" aria-label="문서 분류">
                  {opts.docClasses.map((c) => (
                    <button
                      key={c.key}
                      type="button"
                      role="radio"
                      aria-checked={c.key === target}
                      onClick={() => pickTarget(c.key)}
                      className={clsx("rounded-xl border px-md py-2 text-[12.5px] font-bold", c.key === target ? "border-primary bg-info-faint text-primary ring-1 ring-primary" : "border-hairline-soft text-charcoal hover:bg-surface-soft")}
                      data-upload-doc-class={c.key}
                    >
                      {c.label}
                      <span className="ml-1.5 text-[11px] font-medium text-stone">{c.origin === "ext" ? "외부" : "당행"}</span>
                    </button>
                  ))}
                </div>
                <Field label="제목" htmlFor="up-title" hint={file && form.title === autoTitle ? "파일 이름으로 채웠습니다 — 필요하면 고치세요" : undefined}>
                  <input id="up-title" className="input !h-9 text-[13px]" value={form.title} maxLength={200} onChange={(e) => setForm({ ...form, title: e.target.value })} />
                </Field>
              </div>
            )}
          </Step>

          <Step n={3} title="기준 정보" done={false}>
            {kind === "dataset" ? (
              ds || (autoNew && file) ? (
                <div className="flex flex-col gap-md" data-upload-selected={ds?.code ?? "auto"}>
                  {ds ? (
                    <p className="text-[12.5px] leading-relaxed text-steel">
                      <strong className="font-bold text-ink-deep">{ds.name}</strong> · {versionText(ds)} — 승인되면 새 버전이 됩니다. 정의에 없는 열이 있으면 승인 때 정의에 더해 함께 저장합니다. {ds.description}
                    </p>
                  ) : (
                    <p className="text-[12.5px] leading-relaxed text-steel">
                      새 종류 자료 — 승인되면 파일에서 만든 정의로 데이터셋이 만들어지고 이 파일이 첫 버전이 됩니다.
                    </p>
                  )}
                  <div className="grid grid-cols-1 gap-md md:grid-cols-3">
                    <Field label="자료 성격" htmlFor="up-origin">
                      <select id="up-origin" className="input !h-9 text-[13px]" value={form.data_origin} onChange={(e) => setForm({ ...form, data_origin: e.target.value })}>
                        <option value="actual">실데이터</option>
                        <option value="simulated">시뮬레이션</option>
                      </select>
                    </Field>
                    <Field label="기준일(선택)" htmlFor="up-asof" hint="판을 구분하는 날짜 — 비우면 파일 기간의 마지막 날">
                      <input id="up-asof" className="input !h-9 text-[13px]" type="date" value={form.as_of} onChange={(e) => setForm({ ...form, as_of: e.target.value })} />
                    </Field>
                    <Field label="메모(선택)" htmlFor="up-note" hint="판 설명으로 남음(판 구분에는 쓰지 않음)">
                      <input id="up-note" className="input !h-9 text-[13px]" value={form.note} maxLength={500} placeholder="예: 8월 정정본" onChange={(e) => setForm({ ...form, note: e.target.value })} />
                    </Field>
                  </div>
                  {/* 같은 자료를 날짜만 바꿔 올릴 때 (Phase P · UPV-01 · UPV-07) — 기준일이 판을 가른다 · 보관 중인 기준일 */}
                  <p className="rounded-lg bg-surface-soft px-md py-2 text-[12px] leading-relaxed text-charcoal" data-upload-period-rule>
                    같은 자료의 판은 <strong className="font-bold">기준일</strong>로 구분됩니다 — 기준일이 같으면 그 판을 새 파일로 교체하고, 다르면 날짜별로 함께 보관해 날짜별 비교(전월 · 전년 동기 대비)에 씁니다.
                    비교할 달이 없으면 가장 가까운 보관 기준일과 견주고, 화면 · 목표 판정에 실제로 견준 기간을 밝힙니다.
                    메모는 판 설명이고, 시행일은 문서에만 있습니다. 입력한 기준일의 달이 파일 기간에 없으면 요청하지 않습니다.
                  </p>
                  {ds ? <PeriodList code={ds.code} /> : null}
                  {ds ? (
                    <Advanced label={`이 자료의 열 ${ds.columns.length}개${ds.filePattern ? " · 파일 이름 규칙" : ""}`}>
                      {ds.filePattern ? (
                        <p className="mb-xs text-[11.5px] text-steel">
                          파일 이름 규칙 <code className="font-mono text-charcoal">{ds.filePattern}</code>
                        </p>
                      ) : null}
                      <ul className="grid grid-cols-1 gap-x-lg gap-y-0.5 text-[11.5px] md:grid-cols-2">
                        {ds.columns.map((c) => (
                          <li key={c.name}>
                            <code className="font-mono text-charcoal">{c.name}</code> <span className="text-stone">{c.label}</span>
                          </li>
                        ))}
                      </ul>
                    </Advanced>
                  ) : null}
                </div>
              ) : (
                <p className="text-[12.5px] text-stone">2단계에서 자료를 고르면 기준 정보를 넣을 수 있습니다.</p>
              )
            ) : (
              <div className="flex flex-col gap-md">
                <div className="grid grid-cols-1 gap-md md:grid-cols-3">
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
                {textMode ? (
                  <Field label="문서 본문" htmlFor="up-text">
                    <textarea id="up-text" className="input text-[12.5px]" rows={6} value={form.text} onChange={(e) => setForm({ ...form, text: e.target.value })} />
                  </Field>
                ) : (
                  <p className="text-[11.5px] text-stone">스캔 PDF 는 글자 인식(OCR) 후 올려 주세요.</p>
                )}
              </div>
            )}
          </Step>

          <Step n={4} title="검사 후 승인 요청">
            <p className="mb-md text-[12.5px] leading-relaxed text-steel">
              보내면 바로 보안 · 형식 · 품질 검사를 합니다. 품질 검사에 실패한 자료는 요청되지 않습니다. {APPROVER_TEXT}가 승인해야 화면 수치와 분석에 반영됩니다.
            </p>
            {me ? (
              <p className="mb-md text-[12.5px] text-charcoal" data-upload-owner>
                이 자료는 <b>{me.org.name}</b> 자료로 등록됩니다(소속 팀 기준 — 데이터베이스 목록에 소유 팀으로 표시).
              </p>
            ) : null}
            <div className="flex flex-wrap items-center gap-md">
              <Button variant="confirm" disabled={!ready || busy} onClick={submit} aria-describedby={blocker ? "up-blocker" : undefined} data-upload-submit>
                {busy ? "검사 중…" : "검사하고 승인 요청"}
              </Button>
              {blocker ? (
                <p id="up-blocker" className="text-[12px] text-steel" data-upload-blocker>
                  {blocker}
                </p>
              ) : null}
            </div>
            {failure ? (
              <div className="mt-md">
                <Notice tone="critical" title="요청하지 못했습니다">
                  {failure}
                </Notice>
              </div>
            ) : null}
            {last ? (
              <div ref={resultRef} tabIndex={-1} className="mt-md flex flex-col gap-xs rounded-xl border border-success-line bg-success-faint p-md outline-none focus-visible:ring-2 focus-visible:ring-primary" data-upload-last role="status">
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
          <Button size="sm" variant="quiet" onClick={() => void loadMine()}>
            새로고침
          </Button>
        </div>
        {mineError ? (
          <div role="alert" className="flex flex-col items-start gap-xs rounded-xl border border-critical-line bg-critical-faint p-md" data-my-uploads-error>
            <p className="text-[12.5px] font-bold text-critical">내 요청을 불러오지 못했습니다</p>
            <p className="text-[11.5px] text-steel">{mineError}</p>
            <Button size="sm" variant="ghost" onClick={() => void loadMine()}>
              다시 시도
            </Button>
          </div>
        ) : !mine ? (
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
                {r.status === "rejected" && r.kind === "dataset" ? (
                  <Link href={`/knowledge/upload?target=${encodeURIComponent(r.target)}`} className="mt-0.5 inline-block text-[11.5px] font-bold text-primary">
                    고쳐서 다시 올리기
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
