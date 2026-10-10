"use client";

import clsx from "clsx";
import { useState, type FormEvent } from "react";
import { Sheet } from "@/components/ui/Sheet";
import { Badge, Button } from "@/components/ui/primitives";
import { apiPost } from "@/lib/api-client";

interface AssistMetric {
  code: string;
  label: string;
  display: string;
  unit: string;
  previous: number | null;
  formula: string;
  calcRunId: string;
}
interface AssistEvidence {
  origin: "bank" | "ext";
  title: string;
  docClass: string;
  page: number | null;
  sectionPath?: string | null;
  text: string;
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
  verification: { passed: boolean; unverified: string[]; userSupplied?: string[] };
  missingCategories?: string[];
  toolResults?: { tool: string; result: Record<string, unknown> }[];
}

const MISSING_LABEL: Record<string, string> = { external_policy: "외부 정책", internal_direction: "내부 경영방향" };

const EXAMPLES = ["포용금융 충당금 비중은 얼마인가요?", "소기업 6B 등급 부도율은 예측 대비 어떤가요?", "기업여신 증가율과 목표 대비 이탈은?", "가계부채 관리 기조 관련 근거를 알려줘"];

/** 자연어 질의 패널 (UX-06) — 확정 수치(계산 커널)와 근거 문서만으로 답한다 */
export function AssistPanel() {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<AssistAnswer[]>([]);

  const ask = async (question: string) => {
    if (!question.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const r = await apiPost<AssistAnswer>("/assist", { question: question.trim() });
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
        className="fixed bottom-6 right-6 z-40 flex items-center gap-2 rounded-pill bg-ink-deep px-5 py-3 text-[13px] font-bold text-white shadow-pop no-print"
        aria-haspopup="dialog"
      >
        <span aria-hidden="true">?</span> 질문하기
      </button>
      <Sheet open={open} onClose={() => setOpen(false)} eyebrow="AI 질의" title="데이터에 질문하기" meta="확정 수치(계산 커널)와 근거 문서만으로 답합니다. 권한이 있는 화면의 수치만 포함됩니다." width="lg">
        <form onSubmit={submit} className="flex flex-col gap-xs">
          <label htmlFor="assist-q" className="text-[12px] font-bold text-steel">
            질문
          </label>
          <textarea id="assist-q" className="input text-[13.5px]" rows={3} maxLength={500} value={q} onChange={(e) => setQ(e.target.value)} placeholder="예: 포용금융 충당금 비중은 얼마인가요?" />
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

function AnswerCard({ a }: { a: AssistAnswer }) {
  return (
    <article className="rounded-2xl border border-hairline-soft p-base">
      <p className="text-[12px] font-bold text-steel">Q. {a.question}</p>
      <div className="mt-xs flex flex-wrap items-center gap-1.5">
        {a.mode === "llm" ? <Badge tone="info">LLM · {a.model}</Badge> : <Badge tone="attention">LLM 미연결 — 수치·근거만</Badge>}
        {a.verification.passed ? <Badge tone="success">수치 출처 확인</Badge> : <Badge tone="critical">출처 없는 숫자 {a.verification.unverified.join(", ")}</Badge>}
        {a.concepts.map((c) => (
          <Badge key={c}>{c}</Badge>
        ))}
      </div>
      <p className="mt-md whitespace-pre-wrap text-[13.5px] leading-relaxed text-ink">{a.answer}</p>
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
      {a.evidence.length ? (
        <div className="mt-md">
          <p className="mb-1 text-[11.5px] font-bold text-steel">근거 문서</p>
          <ul className="flex flex-col gap-xs">
            {a.evidence.map((e, i) => (
              <li key={i} className="rounded-lg bg-surface-soft px-md py-2">
                <p className="flex flex-wrap items-center gap-1.5 text-[12px] font-bold text-ink-deep">
                  <span className={clsx("rounded-pill px-1.5 py-0.5 text-[9.5px] text-white", e.origin === "bank" ? "bg-ink-deep" : "bg-primary")}>{e.origin === "bank" ? "당행" : "외부"}</span>
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
    </article>
  );
}
