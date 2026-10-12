import type { ReactNode } from "react";
import { KeyValueList } from "@/components/ui/Layout";

/*
 * 구조화 값 보기 (Phase C · ADM-03) — 규칙 본문 · 설정값 · 노드 설정 같은 JSON 을 사람이 읽는 모양으로.
 * 원시 JSON 은 각 화면의 '고급' 접기 안에 따로 둔다.
 *  - 글 · 숫자 · 참거짓 → 값
 *  - 글 · 숫자 목록 → 칩
 *  - 같은 모양 객체 목록 → 작은 표
 *  - 객체 → 항목 목록(깊이 2 까지, 더 깊으면 요약)
 */

const MAX_ITEMS = 24;

function isScalar(v: unknown): v is string | number | boolean | null {
  return v === null || ["string", "number", "boolean"].includes(typeof v);
}

export function scalarText(v: unknown): string {
  if (v === null || v === undefined) return "-";
  if (typeof v === "boolean") return v ? "예" : "아니오";
  if (typeof v === "number") return v.toLocaleString("ko-KR", { maximumFractionDigits: 6 });
  return String(v) || "(빈 값)";
}

/** 한 줄 요약 — 깊은 구조를 펼치지 않고 무엇이 있는지 */
export function valueSummary(v: unknown): string {
  if (isScalar(v) || v === undefined) return scalarText(v);
  if (Array.isArray(v)) return `목록 ${v.length}개`;
  const keys = Object.keys(v as object);
  return keys.length ? `${keys.slice(0, 4).join(" · ")}${keys.length > 4 ? ` 외 ${keys.length - 4}` : ""}` : "비어 있음";
}

function Chips({ values }: { values: (string | number | boolean | null)[] }) {
  if (!values.length) return <span className="text-stone">비어 있음</span>;
  return (
    <span className="flex flex-wrap gap-1">
      {values.slice(0, MAX_ITEMS).map((x, i) => (
        <span key={i} className="rounded-md bg-surface-soft px-1.5 py-0.5 font-mono text-[11px] text-charcoal">
          {scalarText(x)}
        </span>
      ))}
      {values.length > MAX_ITEMS ? <span className="text-[11px] text-stone">외 {values.length - MAX_ITEMS}개</span> : null}
    </span>
  );
}

function ObjTable({ rows }: { rows: Record<string, unknown>[] }) {
  const cols = Array.from(new Set(rows.flatMap((r) => Object.keys(r)))).slice(0, 8);
  return (
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
          {rows.slice(0, MAX_ITEMS).map((r, i) => (
            <tr key={i} className="border-b border-hairline-soft">
              {cols.map((c) => (
                <td key={c} className="px-2 py-1 align-top text-charcoal">
                  {isScalar(r[c]) || r[c] === undefined ? scalarText(r[c]) : valueSummary(r[c])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length > MAX_ITEMS ? <p className="mt-1 text-[11px] text-stone">외 {rows.length - MAX_ITEMS}행</p> : null}
    </div>
  );
}

export function ValueView({ value, depth = 0, labels }: { value: unknown; depth?: number; labels?: Record<string, string> }): ReactNode {
  if (isScalar(value) || value === undefined) return <span className="tnum">{scalarText(value)}</span>;
  if (Array.isArray(value)) {
    if (value.every(isScalar)) return <Chips values={value as (string | number | boolean | null)[]} />;
    if (value.every((x) => x && typeof x === "object" && !Array.isArray(x))) return depth > 1 ? <span>{valueSummary(value)}</span> : <ObjTable rows={value as Record<string, unknown>[]} />;
    return <span>{valueSummary(value)}</span>;
  }
  const entries = Object.entries(value as Record<string, unknown>);
  if (!entries.length) return <span className="text-stone">비어 있음</span>;
  if (depth > 1) return <span>{valueSummary(value)}</span>;
  return (
    <KeyValueList
      dense
      columns={depth === 0 && entries.length > 6 ? 2 : 1}
      items={entries.slice(0, 40).map(([k, v]) => ({
        label: (
          <span title={k}>
            {labels?.[k] ?? <span className="font-mono text-[11.5px]">{k}</span>}
          </span>
        ),
        value: <ValueView value={v} depth={depth + 1} labels={labels} />,
      }))}
    />
  );
}
