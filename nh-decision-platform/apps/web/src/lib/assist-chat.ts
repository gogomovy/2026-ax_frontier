/**
 * 질문하기 대화 모델 — 서버는 대화를 저장하지 않는다(요구사항 ASK-03 · Q120). 대화 목록은 이 브라우저 탭의 sessionStorage 에만 두고
 * (탭을 닫으면 사라지고, 사용자별 키라 다른 사람이 같은 탭에서 로그인해도 보이지 않으며 로그인 때 다른 사용자의 기록은 지운다), 서버에는 후속 질문용 최근 3턴만 보낸다.
 */
import type { CiteKind } from "@/lib/markdown";

export interface AssistMetric {
  code: string;
  label: string;
  display: string;
  unit: string;
  previous: number | null;
  formula: string;
  calcRunId: string;
}
export interface AssistEvidence {
  origin: "bank" | "ext";
  title: string;
  docClass: string;
  page: number | null;
  sectionPath?: string | null;
  text: string;
  collectionLabel?: string | null;
  owned?: boolean;
  no?: number;
}
export interface AssistAnalysis {
  kind: "analysis" | "glossary" | "catalog";
  type: string;
  collection: string;
  collectionLabel: string;
  owned: boolean;
  title: string;
  artifactTitle?: string | null;
  sectionPath?: string | null;
  text: string;
  sourceKey: string;
  href?: string | null;
  asOf?: string | null;
  severity?: string | null;
  score: number;
  no?: number;
}
export interface ChannelState {
  on: boolean;
  candidates: number;
  reason?: string;
  docGraph?: boolean;
}
export interface AssistRetrieval {
  channels: { keyword?: ChannelState; vector?: ChannelState; graph?: ChannelState };
  semantic: boolean;
  graph: boolean;
  expanded: string[];
  rewritten: string | null;
  rewriteBy: "rule" | "llm" | null;
  timingsMs?: Record<string, number>;
  /** 실제로 쓴 검색 엔진 — ES 가 안 되어 폴백했으면 pg (없으면 pg) */
  backend?: "pg" | "es";
}
export interface ScopeItem {
  code: string;
  label: string;
  kind: string;
  owned: boolean;
  partial: boolean;
}
/** 답을 쓰기 전에 알 수 있는 것(meta 이벤트) — 출처 · 수치 · 검색 상태 */
export interface AssistMeta {
  question: string;
  concepts: string[];
  metrics: AssistMetric[];
  evidence: AssistEvidence[];
  analysis: AssistAnalysis[];
  collections: { code: string; label: string; owned: boolean; count: number }[];
  retrieval: AssistRetrieval;
  missingCategories?: string[];
}
/** 최종 응답(done 이벤트 · POST /assist 응답) */
export interface AssistAnswer extends AssistMeta {
  mode: "llm" | "fallback";
  model?: string;
  answer: string;
  reason?: string;
  verification: { passed: boolean; unverified: string[]; userSupplied?: string[] };
  toolResults?: { tool: string; result: Record<string, unknown> }[];
}

export type MsgStatus = "streaming" | "done" | "error" | "stopped";
export interface UserMsg {
  id: string;
  role: "user";
  text: string;
  at: number;
}
export interface BotMsg {
  id: string;
  role: "assistant";
  /** 화면에 보이는 답 글자 — 스트리밍 중에는 지금까지 받은 것, 끝나면 최종 답 */
  text: string;
  at: number;
  status: MsgStatus;
  stage?: string;
  meta?: AssistMeta;
  final?: AssistAnswer;
  error?: string;
  /** true=도움이 됨 · false=아님 · undefined=아직 */
  feedback?: boolean;
  /** 이 답을 만든 질문 — 다시 생성에 쓴다 */
  question: string;
}
export type Msg = UserMsg | BotMsg;

export interface Conversation {
  id: string;
  title: string;
  updatedAt: number;
  messages: Msg[];
}

let seq = 0;
export const newId = (prefix: string) => `${prefix}${Date.now().toString(36)}${(seq++).toString(36)}${Math.random().toString(36).slice(2, 6)}`;

export const titleOf = (q: string) => {
  const t = q.replace(/\s+/g, " ").trim();
  return t.length > 30 ? `${t.slice(0, 30)}…` : t || "새 대화";
};

/** 서버에 보낼 최근 대화(후속 질문 재작성용) — 끝난 질문 · 답 쌍만 최근 limit 개 */
export function historyFor(messages: Msg[], limit = 3): { q: string; a: string }[] {
  const out: { q: string; a: string }[] = [];
  for (let i = 0; i < messages.length - 1; i++) {
    const u = messages[i];
    const b = messages[i + 1];
    if (u.role === "user" && b.role === "assistant" && b.status === "done" && b.text.trim()) out.push({ q: u.text.slice(0, 300), a: b.text.slice(0, 400) });
  }
  return out.slice(-limit);
}

const MAX_CONVERSATIONS = 30;
const MAX_MESSAGES = 40;
const KEY = "nhdip.assist.v1";

/** 저장할 때 줄인다 — 도구 결과 · 긴 본문은 빼고(다시 열었을 때 답과 출처 카드는 보인다), 진행 중인 답은 중지된 것으로 */
export function slimForStorage(list: Conversation[]): Conversation[] {
  return list
    .slice(0, MAX_CONVERSATIONS)
    .map((c) => ({
      ...c,
      messages: c.messages.slice(-MAX_MESSAGES).map((m): Msg => {
        if (m.role === "user") return m;
        const { final, ...rest } = m;
        const slim = final ? ({ ...final, toolResults: undefined } as AssistAnswer) : undefined;
        return { ...rest, status: m.status === "streaming" ? "stopped" : m.status, stage: undefined, final: slim };
      }),
    }));
}

export function storageKey(empNo: string) {
  return `${KEY}:${empNo}`;
}

/** 다른 사용자의 기록은 지우고 내 기록을 읽는다(같은 탭에서 사용자가 바뀌어도 이전 사용자의 질문 · 답이 남지 않게) */
export function loadConversations(store: Pick<Storage, "getItem" | "removeItem" | "key" | "length">, empNo: string): Conversation[] {
  try {
    const mine = storageKey(empNo);
    const stale: string[] = [];
    for (let i = 0; i < store.length; i++) {
      const k = store.key(i);
      if (k && k.startsWith(`${KEY}:`) && k !== mine) stale.push(k);
    }
    stale.forEach((k) => store.removeItem(k));
    const raw = store.getItem(mine);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    return (parsed as Conversation[]).filter((c) => c && typeof c.id === "string" && Array.isArray(c.messages)).slice(0, MAX_CONVERSATIONS);
  } catch {
    return [];
  }
}

export function saveConversations(store: Pick<Storage, "setItem" | "removeItem">, empNo: string, list: Conversation[]): void {
  try {
    const slim = slimForStorage(list.filter((c) => c.messages.length));
    if (!slim.length) store.removeItem(storageKey(empNo));
    else store.setItem(storageKey(empNo), JSON.stringify(slim));
  } catch {
    /* 저장 공간이 부족하면 조용히 — 대화는 화면에서 계속된다 */
  }
}

/** 답변의 인용 표시 → 출처 연결 */
export interface CiteTarget {
  /** 화면에 보이는 번호(처음 나온 순서) */
  n: number;
  label: string;
  kind: CiteKind;
  /** 출처 카드의 번호(sources 의 no) — 없으면 수치 */
  sourceNo?: number;
  href?: string | null;
  metricCode?: string;
}

const norm = (s: string) => s.replace(/\s+/g, "").toLowerCase();

/** 인용 한 건을 출처에서 찾는다 — 제목이 정확히 같거나 한쪽이 다른 쪽을 포함하면 연결(모델이 제목을 줄여 쓰는 경우). 못 찾으면 null(번호를 꾸며내지 않는다) */
export function resolveCite(kind: CiteKind, ref: string, meta: Pick<AssistMeta, "metrics" | "analysis" | "evidence"> | undefined): Omit<CiteTarget, "n"> | null {
  if (!meta) return null;
  const r = norm(ref);
  if (kind === "metric") {
    const m = meta.metrics.find((x) => x.code === ref) ?? meta.metrics.find((x) => norm(x.label) === r);
    return m ? { kind, label: `${m.label} ${m.display}${m.unit}`, metricCode: m.code } : null;
  }
  const hit = <T extends { title: string; artifactTitle?: string | null }>(xs: T[]) =>
    xs.find((x) => norm(x.title) === r || (x.artifactTitle && norm(x.artifactTitle) === r)) ??
    xs.find((x) => r.length >= 3 && (norm(x.title).includes(r) || r.includes(norm(x.title)) || (x.artifactTitle && (norm(x.artifactTitle).includes(r) || r.includes(norm(x.artifactTitle))))));
  if (kind === "analysis") {
    const a = hit(meta.analysis);
    return a ? { kind, label: a.artifactTitle && a.artifactTitle !== a.title ? `${a.artifactTitle} › ${a.title}` : a.title, sourceNo: a.no, href: a.href } : null;
  }
  if (kind === "doc") {
    const e = hit(meta.evidence);
    return e ? { kind, label: e.title + (e.page ? ` p.${e.page}` : ""), sourceNo: e.no } : null;
  }
  // [n] — 출처 카드 번호
  const no = parseInt(ref, 10);
  const a = meta.analysis.find((x) => x.no === no);
  if (a) return { kind: "analysis", label: a.artifactTitle && a.artifactTitle !== a.title ? `${a.artifactTitle} › ${a.title}` : a.title, sourceNo: no, href: a.href };
  const e = meta.evidence.find((x) => x.no === no);
  return e ? { kind: "doc", label: e.title, sourceNo: no } : null;
}

/** 인용 목록(처음 나온 순서) → 번호 부여. 같은 출처를 다른 표기로 두 번 인용해도 한 번호로 합친다 */
export function numberCites(cites: { kind: CiteKind; ref: string }[], meta: Parameters<typeof resolveCite>[2]): Map<string, CiteTarget> {
  const out = new Map<string, CiteTarget>();
  const byTarget = new Map<string, number>();
  let n = 0;
  for (const c of cites) {
    const t = resolveCite(c.kind, c.ref, meta);
    if (!t) continue;
    const id = t.metricCode ? `m:${t.metricCode}` : `s:${t.sourceNo}`;
    let no = byTarget.get(id);
    if (no === undefined) {
      no = ++n;
      byTarget.set(id, no);
    }
    out.set(`${c.kind}:${c.ref}`, { ...t, n: no });
  }
  return out;
}
