"use client";

import clsx from "clsx";
import { useCallback, useEffect, useState } from "react";
import { Notice } from "@/components/ui/Layout";
import { Badge, Button } from "@/components/ui/primitives";
import { api } from "@/lib/api-client";

/*
 * 새 종류 자료 — 파일에서 추론한 데이터셋 정의 확인 · 수정 (Phase J 후속 · DEF-01~05 · Q160~Q163)
 * 맞는 데이터셋이 없는 파일을 올릴 때, 서버가 머리글 · 값으로 만든 정의 초안(열 이름 · 타입 · 키 · 기준일 열)을 보여 주고
 * 사람이 고쳐 확정한다. 업무 화면은 승인 요청으로, 관리자 화면은 바로 데이터셋 저장으로 이어진다(호출한 쪽이 onSubmit 에서 처리).
 */
export type ColumnType = "str" | "int" | "num" | "date" | "bool";
export interface InferredColumn {
  name: string;
  label: string;
  type: ColumnType;
  required: boolean;
  aliases: string[];
}
export interface InferredDefinition {
  code: string;
  name: string;
  origin: "bank" | "ext";
  kind: string;
  description: string;
  file_pattern: string | null;
  refresh_cycle: string | null;
  columns: InferredColumn[];
  key_columns: string[];
  as_of_column: string | null;
  mapping: Record<string, unknown>;
  quality_rules: Record<string, unknown>[];
  parser: Record<string, unknown>;
  active?: boolean;
  notes: string[];
  samples: Record<string, string[]>;
  rows: number;
  exists?: boolean;
  codeAdjusted?: boolean;
}
export interface PanelSubmit {
  definition: InferredDefinition;
  dataOrigin: "actual" | "simulated";
  note: string;
}

const TYPE_LABEL: Record<ColumnType, string> = { str: "문자", int: "정수", num: "소수", date: "날짜", bool: "예/아니오" };
const CODE_RE = /^[A-Za-z0-9][A-Za-z0-9_-]{1,59}$/;

/** 제출 전 점검 — 서버(validate_definition)와 같은 기준으로 먼저 알려 준다. 서버가 최종 판정 */
export function definitionProblems(d: InferredDefinition): string[] {
  const out: string[] = [];
  if (!CODE_RE.test(d.code)) out.push("코드는 영문·숫자로 시작하는 2~60자(영문·숫자·_·-)입니다.");
  if (!d.name.trim()) out.push("이름을 입력하세요.");
  const seen = new Set<string>();
  for (const c of d.columns) {
    const n = c.name.trim().toLowerCase();
    if (!n) out.push(`'${c.label}' 열의 이름이 비어 있습니다.`);
    else if (seen.has(n)) out.push(`열 이름이 겹칩니다: ${c.name}`);
    seen.add(n);
  }
  return out;
}

export function NewDatasetPanel({
  file,
  inferPath,
  submitLabel,
  introText,
  onSubmit,
  onClose,
}: {
  file: File;
  inferPath: string;
  submitLabel: string;
  introText?: string;
  onSubmit: (s: PanelSubmit) => Promise<void>;
  onClose: () => void;
}) {
  const [def, setDef] = useState<InferredDefinition | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [dataOrigin, setDataOrigin] = useState<"actual" | "simulated">("actual");
  const [note, setNote] = useState("");

  const infer = useCallback(
    async (origin: "bank" | "ext") => {
      setError(null);
      setDef(null);
      try {
        const fd = new FormData();
        fd.append("file", file);
        fd.append("origin", origin);
        setDef(await api<InferredDefinition>(inferPath, { method: "POST", body: fd }));
      } catch (e) {
        setError((e as Error).message || "정의를 추론하지 못했습니다");
      }
    },
    [file, inferPath],
  );
  useEffect(() => {
    // 파일을 바꾸면 다시 추론 (추론 호출은 저장하지 않는다)
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void infer("bank");
  }, [infer]);

  if (error) {
    return (
      <Notice tone="critical" title="이 파일에서 정의를 만들 수 없습니다">
        <p>{error}</p>
        <div className="mt-sm flex gap-xs">
          <Button size="sm" variant="quiet" onClick={() => void infer("bank")}>
            다시 시도
          </Button>
          <Button size="sm" variant="ghost" onClick={onClose}>
            닫기
          </Button>
        </div>
      </Notice>
    );
  }
  if (!def) return <p className="text-[12.5px] text-stone">파일에서 열 이름 · 타입 · 키를 찾는 중…</p>;

  const patch = (p: Partial<InferredDefinition>) => setDef((d) => (d ? { ...d, ...p } : d));
  const setCol = (i: number, p: Partial<InferredColumn>) =>
    setDef((d) => {
      if (!d) return d;
      const old = d.columns[i];
      const columns = d.columns.map((c, k) => (k === i ? { ...c, ...p } : c));
      // 이름을 바꾸면 키 · 기준일 열 지정도 따라가게 한다
      const renamed = p.name !== undefined && p.name !== old.name;
      return {
        ...d,
        columns,
        key_columns: renamed ? d.key_columns.map((k) => (k === old.name ? (p.name as string) : k)) : d.key_columns,
        as_of_column: renamed && d.as_of_column === old.name ? (p.name as string) : d.as_of_column,
      };
    });
  const toggleKey = (name: string) => {
    const on = def.key_columns.includes(name);
    patch({
      key_columns: on ? def.key_columns.filter((k) => k !== name) : [...def.key_columns, name],
      // 키 · 기준일 열은 필수로 — 빠진 파일이 조용히 올라가지 않게
      columns: def.columns.map((c) => (c.name === name && !on ? { ...c, required: true } : c)),
    });
  };
  const problems = definitionProblems(def);

  const submit = async () => {
    setBusy(true);
    try {
      await onSubmit({ definition: def, dataOrigin, note });
    } finally {
      setBusy(false);
    }
  };

  return (
    <section aria-label="새 종류 자료 정의" className="flex flex-col gap-md rounded-2xl border border-hairline-soft bg-surface-soft p-md" data-new-dataset-panel>
      <p className="text-[12.5px] leading-relaxed text-steel">
        {introText ?? "맞는 자료가 없어 파일에서 정의를 만들었습니다. 열 이름 · 타입 · 키를 확인하고 필요하면 고치세요."} 전체 {def.rows.toLocaleString("ko-KR")}행을 읽어 판단했습니다. 정의에 없는 열은 저장되지 않으니, 저장할 열은 모두 아래 표에 있어야 합니다.
      </p>
      {def.codeAdjusted ? <p className="text-[12px] text-attention">같은 코드가 이미 있거나 제안 중이라 코드 끝에 번호를 붙였습니다.</p> : null}
      <div className="grid grid-cols-1 gap-md md:grid-cols-4">
        <label className="text-[12px] font-bold text-charcoal">
          코드
          <input className="input mt-1 !h-9 w-full font-mono text-[12.5px]" value={def.code} onChange={(e) => patch({ code: e.target.value.trim() })} maxLength={60} />
        </label>
        <label className="text-[12px] font-bold text-charcoal md:col-span-2">
          이름
          <input className="input mt-1 !h-9 w-full text-[13px]" value={def.name} onChange={(e) => patch({ name: e.target.value })} maxLength={150} />
        </label>
        <label className="text-[12px] font-bold text-charcoal">
          출처
          <select className="input mt-1 !h-9 w-full text-[13px]" value={def.origin} onChange={(e) => patch({ origin: e.target.value as "bank" | "ext" })}>
            <option value="bank">당행 자료</option>
            <option value="ext">외부 자료</option>
          </select>
        </label>
      </div>

      <div className="max-w-full overflow-x-auto">
        <table className="w-full min-w-[640px] border-collapse text-[12px]">
          <caption className="sr-only">추론한 열 정의 — 열 이름 · 타입 · 키 · 기준일 · 필수를 고칠 수 있습니다</caption>
          <thead>
            <tr className="bg-canvas text-left">
              <th scope="col" className="px-2 py-1.5 font-bold text-charcoal">파일의 머리글</th>
              <th scope="col" className="px-2 py-1.5 font-bold text-charcoal">열 이름</th>
              <th scope="col" className="px-2 py-1.5 font-bold text-charcoal">타입</th>
              <th scope="col" className="px-2 py-1.5 text-center font-bold text-charcoal">키</th>
              <th scope="col" className="px-2 py-1.5 text-center font-bold text-charcoal">기준일</th>
              <th scope="col" className="px-2 py-1.5 text-center font-bold text-charcoal">필수</th>
              <th scope="col" className="px-2 py-1.5 font-bold text-charcoal">예시</th>
            </tr>
          </thead>
          <tbody>
            {def.columns.map((c, i) => (
              <tr key={i} className="border-b border-hairline-soft align-top">
                <td className="px-2 py-1.5 text-charcoal">{c.label}</td>
                <td className="px-2 py-1">
                  <input aria-label={`${c.label} 열 이름`} className="input !h-8 w-full min-w-[120px] font-mono text-[12px]" value={c.name} onChange={(e) => setCol(i, { name: e.target.value.trim() })} maxLength={60} />
                </td>
                <td className="px-2 py-1">
                  <select aria-label={`${c.label} 타입`} className="input !h-8 text-[12px]" value={c.type} onChange={(e) => setCol(i, { type: e.target.value as ColumnType })}>
                    {Object.entries(TYPE_LABEL).map(([k, v]) => (
                      <option key={k} value={k}>
                        {v}
                      </option>
                    ))}
                  </select>
                </td>
                <td className="px-2 py-1.5 text-center">
                  <input type="checkbox" aria-label={`${c.label} 키 열`} checked={def.key_columns.includes(c.name)} onChange={() => toggleKey(c.name)} />
                </td>
                <td className="px-2 py-1.5 text-center">
                  <input
                    type="radio"
                    name="as-of-column"
                    aria-label={`${c.label} 기준일 열`}
                    checked={def.as_of_column === c.name}
                    onChange={() => patch({ as_of_column: c.name, columns: def.columns.map((x) => (x.name === c.name ? { ...x, required: true } : x)) })}
                  />
                </td>
                <td className="px-2 py-1.5 text-center">
                  <input type="checkbox" aria-label={`${c.label} 필수`} checked={c.required} onChange={(e) => setCol(i, { required: e.target.checked })} />
                </td>
                <td className="px-2 py-1.5 font-mono text-[11px] text-stone">{(def.samples[c.name] ?? []).join(" · ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex flex-wrap items-center gap-xs text-[12px] text-steel">
        <button type="button" className="font-bold text-primary underline-offset-2 hover:underline" onClick={() => patch({ as_of_column: null })}>
          기준일 열 없음
        </button>
        <span>· 키 {def.key_columns.length ? def.key_columns.join(", ") : "없음"}</span>
        {def.parser && Object.keys(def.parser).length ? <Badge>머리글 줄 위치 기억: {JSON.stringify(def.parser)}</Badge> : null}
      </div>
      {def.notes.length ? (
        <ul className="list-disc pl-5 text-[12px] text-attention" aria-label="확인할 내용">
          {def.notes.map((n, i) => (
            <li key={i}>{n}</li>
          ))}
        </ul>
      ) : null}

      <div className="grid grid-cols-1 gap-md md:grid-cols-3">
        <label className="text-[12px] font-bold text-charcoal">
          자료 성격
          <select className="input mt-1 !h-9 w-full text-[13px]" value={dataOrigin} onChange={(e) => setDataOrigin(e.target.value as "actual" | "simulated")}>
            <option value="actual">실데이터</option>
            <option value="simulated">시뮬레이션</option>
          </select>
        </label>
        <label className="text-[12px] font-bold text-charcoal md:col-span-2">
          메모(선택)
          <input className="input mt-1 !h-9 w-full text-[13px]" value={note} maxLength={500} onChange={(e) => setNote(e.target.value)} />
        </label>
      </div>

      {problems.length ? (
        <ul className={clsx("list-disc pl-5 text-[12px] text-critical")} role="alert">
          {problems.map((p) => (
            <li key={p}>{p}</li>
          ))}
        </ul>
      ) : null}
      <div className="flex flex-wrap items-center gap-xs">
        <Button variant="confirm" disabled={busy || problems.length > 0} onClick={submit} data-new-dataset-submit>
          {busy ? "검사 중…" : submitLabel}
        </Button>
        <Button size="sm" variant="quiet" disabled={busy} onClick={() => void infer(def.origin)}>
          다시 추론
        </Button>
        <Button size="sm" variant="ghost" disabled={busy} onClick={onClose}>
          닫기
        </Button>
      </div>
    </section>
  );
}

/** 서버로 보낼 정의 — 추론 보조 정보(안내 · 예시 · 행 수)는 빼고 저장 필드만 */
export function definitionPayload(d: InferredDefinition) {
  const { notes: _n, samples: _s, rows: _r, exists: _e, codeAdjusted: _c, ...rest } = d;
  void _n;
  void _s;
  void _r;
  void _e;
  void _c;
  return rest;
}
