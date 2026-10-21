/** 관리자 [조직 · 인사 동기화] 표시 도우미 (Phase R) — 서버 /admin/data-sync 응답을 화면 글로 바꾼다 */

export type SyncKind = "organization" | "employee";

export interface SyncCounts {
  totalProcessed?: number;
  matched?: number;
  inserted?: number;
  updated?: number;
  unchanged?: number;
  deactivated?: number;
  reactivated?: number;
  skipped?: number;
  /** 관리자가 정한 업무 소속을 유지한 사용자(인사 사무소와 다름) */
  keptAssigned?: number;
}

export interface SyncResult extends SyncCounts {
  file: string;
  kind: SyncKind;
  dryRun: boolean;
  encoding: string;
  errors: string[];
  warnings: string[];
}

export const KIND_LABEL: Record<SyncKind, string> = { organization: "조직", employee: "인사" };

/** 감사 로그 동작 → (대상 · 방식) — admin.sync.organization(.dry_run) · admin.sync.employee(.dry_run) · admin.sync.settings */
export function syncActionLabel(action: string): { target: string; mode: string } {
  const rest = action.replace(/^admin\.sync\./, "");
  if (rest === "settings") return { target: "설정", mode: "변경" };
  const dry = rest.endsWith(".dry_run");
  const kind = rest.replace(/\.dry_run$/, "") as SyncKind;
  return { target: KIND_LABEL[kind] ?? rest, mode: dry ? "미리보기" : "반영" };
}

/** 결과 한 줄 — 0 인 항목은 뺀다 */
export function countsLine(c: SyncCounts | null | undefined, kind?: SyncKind): string {
  if (!c) return "-";
  const off = kind === "organization" ? "사용 안 함" : "사용 중지";
  const parts: [string, number | undefined][] = [
    ["처리", c.totalProcessed],
    ["대상", c.matched],
    ["신규", c.inserted],
    ["변경", c.updated],
    ["그대로", c.unchanged],
    [off, c.deactivated],
    ["다시 사용", c.reactivated],
    ["건너뜀", c.skipped],
    ["지정 소속 유지", c.keptAssigned],
  ];
  const shown = parts.filter(([, n]) => typeof n === "number" && n > 0).map(([k, n]) => `${k} ${n!.toLocaleString("ko-KR")}`);
  return shown.length ? shown.join(" · ") : "변경 없음";
}

/** 설정값(JSON 목록 또는 JSON 문자열) → 목록 — 읽을 수 없으면 null(편집기에 원문을 그대로 보여 고치게) */
export function asRuleList(v: unknown): unknown[] | null {
  if (v === null || v === undefined || v === "") return [];
  if (Array.isArray(v)) return v;
  if (typeof v === "string") {
    try {
      const p = JSON.parse(v);
      return Array.isArray(p) ? p : null;
    } catch {
      return null;
    }
  }
  return null;
}

/** 붙여 넣은 .dat 본문 미리 점검 — 줄 수(빈 줄 제외) · 첫 줄 칸 수('|' 구분) · 칸 수가 다른 줄 수. 서버 파서와 같은 줄 나눔(CRLF · CR · LF) */
export function pasteStats(text: string): { lines: number; fields: number; ragged: number } {
  const rows = text
    .replace(/\r\n?/g, "\n")
    .split("\n")
    .filter((l) => l.trim() !== "");
  if (!rows.length) return { lines: 0, fields: 0, ragged: 0 };
  const fields = rows[0].split("|").length;
  return { lines: rows.length, fields, ragged: rows.filter((r) => r.split("|").length !== fields).length };
}

/** 조직 · 인사 .dat 의 최소 칸 수 (서버 orgsync 와 같음) — 붙여 넣은 줄이 이보다 짧으면 안내 */
export const MIN_FIELDS: Record<SyncKind, number> = { organization: 15, employee: 21 };
