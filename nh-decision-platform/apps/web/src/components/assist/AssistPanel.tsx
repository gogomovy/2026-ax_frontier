"use client";

import clsx from "clsx";
import { usePathname } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { Sheet } from "@/components/ui/Sheet";
import { Badge, Button, LinkButton } from "@/components/ui/primitives";
import { apiGetC, apiPost } from "@/lib/api-client";

interface AssistMetric {
  code: string;
  label: string;
  display: string;
  unit: string;
  previous: number | null;
  formula: string;
  calcRunId: string;
}
/** 근거 문서 (기존 필드 유지 + 컬렉션) */
interface AssistEvidence {
  origin: "bank" | "ext";
  title: string;
  docClass: string;
  page: number | null;
  sectionPath?: string | null;
  text: string;
  collectionLabel?: string | null;
  owned?: boolean;
}
/** 분석 결과 출처 — 팀 컬렉션에서 가져온 확정 분석 (요구사항 §21 ASK-04) */
interface AssistAnalysis {
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
}
interface ChannelState {
  on: boolean;
  candidates: number;
  reason?: string;
  docGraph?: boolean;
}
interface AssistRetrieval {
  channels: { keyword?: ChannelState; vector?: ChannelState; graph?: ChannelState };
  semantic: boolean;
  graph: boolean;
  expanded: string[];
  rewritten: string | null;
  rewriteBy: "rule" | "llm" | null;
}
interface ScopeItem {
  code: string;
  label: string;
  kind: string;
  owned: boolean;
  partial: boolean;
}
interface AssistAnswer {
  question: string;
  mode: "llm" | "fallback";
  model?: string;
  answer: string;
  reason?: string;
  concepts: string[];
  metrics: AssistMetric[];
  evidence: AssistEvidence[];
  analysis: AssistAnalysis[];
  collections: { code: string; label: string; owned: boolean; count: number }[];
  retrieval: AssistRetrieval;
  verification: { passed: boolean; unverified: string[]; userSupplied?: string[] };
  missingCategories?: string[];
  toolResults?: { tool: string; result: Record<string, unknown> }[];
}

const MISSING_LABEL: Record<string, string> = { external_policy: "외부 정책", internal_direction: "내부 경영방향" };
const SEVERITY_LABEL: Record<string, string> = { info: "정보", watch: "관찰", caution: "주의", critical: "심각" };
const SEVERITY_TONE: Record<string, "info" | "attention" | "warning" | "critical"> = { info: "info", watch: "attention", caution: "warning", critical: "critical" };

const EXAMPLES = [
  "포용금융 충당금 비중은 얼마인가요?",
  "소기업 6B 등급 부도율은 예측 대비 어떤가요?",
  "기업여신 증가율과 목표 대비 이탈은?",
  "가계부채 관리 기조 관련 근거를 알려줘",
  "우리 팀 분석 결과에서 주의할 점을 알려줘",
];
const HISTORY_TURNS = 3;

/** 자연어 질의 패널 (UX-06 · ASK) — 확정 수치(계산 커널) · 팀 분석 결과 · 근거 문서만으로 답한다 */
export function AssistPanel() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<AssistAnswer[]>([]); // 최신이 앞
  const [scope, setScope] = useState<ScopeItem[] | null>(null);

  // 내가 질문할 수 있는 범위 — 열 때마다 현재 화면 기준으로 (권한 밖 컬렉션은 응답에 없다)
  useEffect(() => {
    if (!open) return;
    let alive = true;
    apiGetC<{ collections: ScopeItem[] }>(`/assist/scope?screen=${encodeURIComponent(pathname || "/")}`)
      .then((r) => alive && setScope(r.collections))
      .catch(() => alive && setScope(null));
    return () => {
      alive = false;
    };
  }, [open, pathname]);

  const ask = async (question: string) => {
    if (!question.trim()) return;
    setBusy(true);
    setError(null);
    try {
      // 서버는 대화를 저장하지 않는다 — 후속 질문(“그럼 소기업은?”)을 위해 최근 대화만 함께 보낸다
      const recent = history
        .slice(0, HISTORY_TURNS)
        .reverse()
        .map((h) => ({ q: h.question.slice(0, 300), a: h.answer.slice(0, 400) }));
      const r = await apiPost<AssistAnswer>("/assist", { question: question.trim(), screen: pathname || undefined, history: recent });
      setHistory((h) => [r, ...h].slice(0, 20));
      setQ("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const submit = (e: FormEvent) => {
    e.preventDefault();
    ask(q);
  };

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="fixed bottom-4 right-4 z-40 flex h-12 min-w-[48px] items-center justify-center gap-2 rounded-pill bg-ink-deep px-4 text-[13px] font-bold text-white shadow-pop no-print sm:bottom-6 sm:right-6 sm:h-auto sm:px-5 sm:py-3"
        aria-haspopup="dialog"
      >
        {/* 좁은 화면은 아이콘 단추(이름은 화면 낭독기용으로 유지) — 내용을 덜 가린다 (Phase E · LAY-01) */}
        <span aria-hidden="true">?</span> <span className="max-sm:sr-only">질문하기</span>
      </button>
      <Sheet open={open} onClose={() => setOpen(false)} eyebrow="AI 질의" title="데이터에 질문하기" meta="확정 수치(계산 커널) · 우리 팀 분석 결과 · 근거 문서만으로 답합니다. 권한이 있는 범위만 검색합니다." width="lg">
        {scope ? (
          <div className="mb-md rounded-xl bg-surface-soft px-md py-2" aria-label="질문할 수 있는 범위">
            <p className="text-[11.5px] font-bold text-steel">내가 질문할 수 있는 범위</p>
            <ul className="mt-1 flex flex-wrap gap-1.5">
              {scope.map((c) => (
                <li key={c.code}>
                  <Badge tone={c.owned ? "primary" : "neutral"}>
                    {c.label}
                    {c.owned ? " · 담당" : c.partial ? " · 일부" : ""}
                  </Badge>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        <form onSubmit={submit} className="flex flex-col gap-xs">
          <label htmlFor="assist-q" className="text-[12px] font-bold text-steel">
            질문
          </label>
          <textarea id="assist-q" className="input text-[13.5px]" rows={3} maxLength={500} value={q} onChange={(e) => setQ(e.target.value)} placeholder="예: 포용금융 충당금 비중은 얼마인가요? (이어서 “그럼 증가율은?” 처럼 물어도 돼요)" />
          <div className="flex flex-wrap items-center gap-xs">
            <Button type="submit" variant="confirm" size="sm" disabled={busy || q.trim().length < 2}>
              {busy ? "확인 중…" : "질문"}
            </Button>
            {EXAMPLES.map((ex) => (
              <button key={ex} type="button" onClick={() => ask(ex)} disabled={busy} className="rounded-pill bg-surface-soft px-3 py-1 text-[11.5px] text-charcoal">
                {ex}
              </button>
            ))}
          </div>
          {error ? (
            <p role="alert" className="text-[12px] text-critical">
              {error}
            </p>
          ) : null}
        </form>
        <div className="mt-lg flex flex-col gap-lg" aria-live="polite">
          {history.map((h, i) => (
            <AnswerCard key={`${h.question}-${i}`} a={h} />
          ))}
        </div>
      </Sheet>
    </>
  );
}

/** 검색에 쓰인 채널 — 의미 · 그래프가 꺼졌으면 이유를 함께 (RAG-06) */
function RetrievalNote({ r }: { r: AssistRetrieval }) {
  const ch = r.channels;
  const notes: string[] = [];
  if (ch.vector && !ch.vector.on) notes.push(`의미 검색 비활성${ch.vector.reason ? ` — ${ch.vector.reason}` : ""}`);
  if (ch.graph?.on && ch.graph.docGraph === false) notes.push("문서 그래프 미연결 — 분석 결과의 개념 태그로 대신 찾았습니다");
  return (
    <div className="mt-xs flex flex-wrap items-center gap-1.5 text-[11px] text-stone">
      <span>검색:</span>
      <Badge tone="neutral">키워드 {ch.keyword?.candidates ?? 0}</Badge>
      <Badge tone={ch.vector?.on ? "info" : "neutral"}>의미 {ch.vector?.on ? ch.vector.candidates : "꺼짐"}</Badge>
      <Badge tone={ch.graph?.on ? "info" : "neutral"}>그래프 {ch.graph?.on ? ch.graph.candidates : "꺼짐"}</Badge>
      {r.expanded.length ? <span>확장 개념: {r.expanded.slice(0, 4).join(" · ")}</span> : null}
      {notes.map((n) => (
        <span key={n}>· {n}</span>
      ))}
      {r.rewritten ? (
        <span className="basis-full">
          이전 대화를 반영해 “{r.rewritten}”(으)로 찾았습니다{r.rewriteBy === "llm" ? " (AI 재작성)" : ""}.
        </span>
      ) : null}
    </div>
  );
}

function AnalysisSource({ s }: { s: AssistAnalysis }) {
  return (
    <li className="rounded-lg bg-surface-soft px-md py-2">
      <p className="flex flex-wrap items-center gap-1.5 text-[12px] font-bold text-ink-deep">
        <span className="rounded-pill bg-primary px-1.5 py-0.5 text-[9.5px] text-white">{s.type}</span>
        <Badge tone={s.owned ? "primary" : "neutral"}>
          {s.collectionLabel}
          {s.owned ? " · 담당 팀" : ""}
        </Badge>
        {s.severity ? <Badge tone={SEVERITY_TONE[s.severity] ?? "neutral"}>{SEVERITY_LABEL[s.severity] ?? s.severity}</Badge> : null}
        <span>{s.artifactTitle && s.artifactTitle !== s.title ? `${s.artifactTitle} › ${s.title}` : s.title}</span>
        {s.asOf ? <span className="font-medium text-stone">기준 {s.asOf}</span> : null}
      </p>
      <p className="mt-0.5 line-clamp-4 whitespace-pre-line text-[11.5px] leading-snug text-charcoal">{s.text.split("\n").slice(1).join("\n") || s.text}</p>
      {s.href ? (
        <div className="mt-1">
          <LinkButton href={s.href} variant="quiet" size="sm">
            화면 열기<span className="sr-only"> — {s.title}</span>
          </LinkButton>
        </div>
      ) : null}
    </li>
  );
}

function FeedbackRow({ a }: { a: AssistAnswer }) {
  const [sent, setSent] = useState<boolean | null>(null);
  const send = async (helpful: boolean) => {
    try {
      await apiPost("/assist/feedback", { question: a.question, helpful, mode: a.mode, sourceCount: a.analysis.length + a.evidence.length });
      setSent(helpful);
    } catch {
      /* 피드백 실패는 조용히 — 답변 사용에는 영향 없음 */
    }
  };
  if (sent !== null) return <p className="mt-md text-[11.5px] text-stone">의견을 남겼습니다. 고맙습니다.</p>;
  return (
    <div className="mt-md flex items-center gap-xs text-[11.5px] text-stone">
      <span>이 답변이 도움이 됐나요?</span>
      <Button variant="ghost" size="sm" onClick={() => send(true)}>
        도움이 됨
      </Button>
      <Button variant="ghost" size="sm" onClick={() => send(false)}>
        도움이 안 됨
      </Button>
    </div>
  );
}

function AnswerCard({ a }: { a: AssistAnswer }) {
  return (
    <article className="rounded-2xl border border-hairline-soft p-base">
      <p className="text-[12px] font-bold text-steel">Q. {a.question}</p>
      <div className="mt-xs flex flex-wrap items-center gap-1.5">
        {a.mode === "llm" ? <Badge tone="info">LLM · {a.model}</Badge> : <Badge tone="attention">LLM 미연결 — 수치·분석·근거만</Badge>}
        {a.verification.passed ? <Badge tone="success">수치 출처 확인</Badge> : <Badge tone="critical">출처 없는 숫자 {a.verification.unverified.join(", ")}</Badge>}
        {a.concepts.map((c) => (
          <Badge key={c}>{c}</Badge>
        ))}
      </div>
      <p className="mt-md whitespace-pre-wrap text-[13.5px] leading-relaxed text-ink">{a.answer}</p>
      <RetrievalNote r={a.retrieval} />
      {a.metrics.length ? (
        <div className="mt-md">
          <p className="mb-1 text-[11.5px] font-bold text-steel">확정 수치</p>
          <ul className="flex flex-col gap-1">
            {a.metrics.map((m) => (
              <li key={m.code} className="flex flex-wrap items-baseline gap-x-2 text-[12.5px]">
                <span className="text-charcoal">{m.label}</span>
                <b className="tnum text-ink-deep">
                  {m.display}
                  {m.unit}
                </b>
                <span className="font-mono text-[10.5px] text-stone">
                  {m.formula} · calc {m.calcRunId.slice(0, 8)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {a.analysis.length ? (
        <div className="mt-md">
          <p className="mb-1 text-[11.5px] font-bold text-steel">분석 결과 · 용어</p>
          <ul className="flex flex-col gap-xs">
            {a.analysis.map((s, i) => (
              <AnalysisSource key={`${s.sourceKey}-${i}`} s={s} />
            ))}
          </ul>
        </div>
      ) : null}
      {a.evidence.length ? (
        <div className="mt-md">
          <p className="mb-1 text-[11.5px] font-bold text-steel">근거 문서</p>
          <ul className="flex flex-col gap-xs">
            {a.evidence.map((e, i) => (
              <li key={i} className="rounded-lg bg-surface-soft px-md py-2">
                <p className="flex flex-wrap items-center gap-1.5 text-[12px] font-bold text-ink-deep">
                  <span className={clsx("rounded-pill px-1.5 py-0.5 text-[9.5px] text-white", e.origin === "bank" ? "bg-ink-deep" : "bg-primary")}>{e.origin === "bank" ? "당행" : "외부"}</span>
                  {e.collectionLabel ? <Badge tone={e.owned ? "primary" : "neutral"}>{e.collectionLabel}</Badge> : null}
                  {e.title} {e.page ? <span className="font-medium text-stone">p.{e.page}</span> : null}
                </p>
                {e.sectionPath ? <p className="mt-0.5 text-[10.5px] text-steel">{e.sectionPath}</p> : null}
                <p className="mt-0.5 line-clamp-3 text-[11.5px] leading-snug text-charcoal">{e.text}</p>
              </li>
            ))}
          </ul>
          {a.missingCategories?.length ? (
            <p className="mt-1 text-[11px] text-stone">
              {a.missingCategories.map((c) => MISSING_LABEL[c] ?? c).join(" · ")} 근거는 찾지 못했습니다.
            </p>
          ) : null}
        </div>
      ) : null}
      {!a.analysis.length && !a.evidence.length && !a.metrics.length ? (
        <p className="mt-md text-[11.5px] text-stone">내가 볼 수 있는 범위에서는 관련 자료를 찾지 못했습니다. 지표 · 상품 · 모형 이름을 넣어 다시 질문해 보세요.</p>
      ) : null}
      <FeedbackRow a={a} />
    </article>
  );
}
