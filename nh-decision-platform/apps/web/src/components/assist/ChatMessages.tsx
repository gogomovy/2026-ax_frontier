"use client";

import clsx from "clsx";
import { useId, useMemo, useState, type ReactNode } from "react";
import { Badge, LinkButton } from "@/components/ui/primitives";
import { apiPost } from "@/lib/api-client";
import { numberCites, type AssistAnalysis, type AssistEvidence, type AssistMeta, type AssistMetric, type AssistRetrieval, type BotMsg, type CiteTarget, type UserMsg } from "@/lib/assist-chat";
import { copyText } from "@/lib/clipboard";
import { collectCites, parseMarkdown, plainForCopy } from "@/lib/markdown";
import { Markdown, type CiteApi } from "./Markdown";
import { IconCheck, IconChevron, IconCopy, IconRefresh, IconSpark, IconThumbDown, IconThumbUp } from "./icons";

const SEVERITY_LABEL: Record<string, string> = { info: "정보", watch: "관찰", caution: "주의", critical: "심각" };
const SEVERITY_TONE: Record<string, "info" | "attention" | "warning" | "critical"> = { info: "info", watch: "attention", caution: "warning", critical: "critical" };
const MISSING_LABEL: Record<string, string> = { external_policy: "외부 정책", internal_direction: "내부 경영방향" };

export function Avatar() {
  return (
    <span aria-hidden="true" className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-circle bg-ink-deep text-white">
      <IconSpark size={16} />
    </span>
  );
}

export function UserMessage({ m }: { m: UserMsg }) {
  return (
    <div className="flex justify-end" data-role="user">
      <p className="max-w-[85%] whitespace-pre-wrap break-words rounded-3xl bg-surface-soft px-4 py-2.5 text-[14px] leading-relaxed text-ink-deep">
        <span className="sr-only">내 질문: </span>
        {m.text}
      </p>
    </div>
  );
}

function Dots() {
  return (
    <span aria-hidden="true" className="inline-flex items-center gap-1">
      {[0, 1, 2].map((i) => (
        <span key={i} className="h-1.5 w-1.5 rounded-circle bg-steel motion-safe:animate-pulse" style={{ animationDelay: `${i * 160}ms` }} />
      ))}
    </span>
  );
}

function IconButton({ label, onClick, pressed, disabled, children }: { label: string; onClick: () => void; pressed?: boolean; disabled?: boolean; children: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      title={label}
      {...(pressed !== undefined ? { "aria-pressed": pressed } : {})}
      className={clsx(
        "flex h-8 w-8 items-center justify-center rounded-lg text-steel transition-colors hover:bg-surface-soft hover:text-ink-deep disabled:cursor-not-allowed disabled:opacity-40",
        pressed && "bg-info-soft text-primary hover:bg-info-soft",
      )}
    >
      {children}
    </button>
  );
}

/** 검색에 쓰인 채널 — 의미 · 그래프가 꺼졌으면 이유를 함께 (RAG-06) */
function RetrievalNote({ r }: { r: AssistRetrieval }) {
  const ch = r.channels;
  const notes: string[] = [];
  if (ch.vector && !ch.vector.on) notes.push(`의미 검색 비활성${ch.vector.reason ? ` — ${ch.vector.reason}` : ""}`);
  if (ch.graph?.on && ch.graph.docGraph === false) notes.push("문서 그래프 미연결 — 분석 결과의 개념 태그로 대신 찾았습니다");
  return (
    <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-stone">
      <Badge tone="neutral">키워드 {ch.keyword?.candidates ?? 0}</Badge>
      <Badge tone={ch.vector?.on ? "info" : "neutral"}>의미 {ch.vector?.on ? ch.vector.candidates : "꺼짐"}</Badge>
      <Badge tone={ch.graph?.on ? "info" : "neutral"}>그래프 {ch.graph?.on ? ch.graph.candidates : "꺼짐"}</Badge>
      {r.expanded.length ? <span>확장 개념: {r.expanded.slice(0, 4).join(" · ")}</span> : null}
      {r.timingsMs?.total != null ? <span>검색 {r.timingsMs.total}ms{r.backend === "es" ? " · Elasticsearch" : ""}</span> : null}
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

function CiteNo({ n }: { n?: number }) {
  return n ? (
    <span aria-hidden="true" className="inline-flex h-[18px] min-w-[18px] items-center justify-center rounded-pill bg-info-soft px-1 text-[10.5px] font-bold text-primary">
      {n}
    </span>
  ) : (
    <span aria-hidden="true" className="h-1.5 w-1.5 rounded-circle bg-hairline" />
  );
}

function AnalysisCard({ s, n, id, hot }: { s: AssistAnalysis; n?: number; id: string; hot: boolean }) {
  return (
    <li id={id} className={clsx("rounded-xl border bg-canvas px-md py-2.5 transition-colors", hot ? "border-primary bg-info-soft" : "border-hairline-soft")}>
      <p className="flex flex-wrap items-center gap-1.5 text-[12px] font-bold text-ink-deep">
        <CiteNo n={n} />
        <span className="rounded-pill bg-primary px-1.5 py-0.5 text-[9.5px] text-white">{s.type}</span>
        <Badge tone={s.owned ? "primary" : "neutral"}>
          {s.collectionLabel}
          {s.owned ? " · 담당 팀" : ""}
        </Badge>
        {s.severity ? <Badge tone={SEVERITY_TONE[s.severity] ?? "neutral"}>{SEVERITY_LABEL[s.severity] ?? s.severity}</Badge> : null}
        <span>{s.artifactTitle && s.artifactTitle !== s.title ? `${s.artifactTitle} › ${s.title}` : s.title}</span>
        {s.asOf ? <span className="font-medium text-stone">기준 {s.asOf}</span> : null}
      </p>
      <p className="mt-1 line-clamp-4 whitespace-pre-line text-[12px] leading-snug text-charcoal">{s.text.split("\n").slice(1).join("\n") || s.text}</p>
      {s.href ? (
        <div className="mt-1.5">
          <LinkButton href={s.href} variant="quiet" size="sm">
            화면 열기<span className="sr-only"> — {s.title}</span>
          </LinkButton>
        </div>
      ) : null}
    </li>
  );
}

function EvidenceCard({ e, n, id, hot }: { e: AssistEvidence; n?: number; id: string; hot: boolean }) {
  return (
    <li id={id} className={clsx("rounded-xl border bg-canvas px-md py-2.5 transition-colors", hot ? "border-primary bg-info-soft" : "border-hairline-soft")}>
      <p className="flex flex-wrap items-center gap-1.5 text-[12px] font-bold text-ink-deep">
        <CiteNo n={n} />
        <span className={clsx("rounded-pill px-1.5 py-0.5 text-[9.5px] text-white", e.origin === "bank" ? "bg-ink-deep" : "bg-primary")}>{e.origin === "bank" ? "당행" : "외부"}</span>
        {e.collectionLabel ? <Badge tone={e.owned ? "primary" : "neutral"}>{e.collectionLabel}</Badge> : null}
        <span>{e.title}</span>
        {e.page ? <span className="font-medium text-stone">p.{e.page}</span> : null}
      </p>
      {e.sectionPath ? <p className="mt-0.5 text-[10.5px] text-steel">{e.sectionPath}</p> : null}
      <p className="mt-1 line-clamp-3 text-[12px] leading-snug text-charcoal">{e.text}</p>
    </li>
  );
}

function MetricList({ metrics, nOf, msgId, hotCode }: { metrics: AssistMetric[]; nOf: (code: string) => number | undefined; msgId: string; hotCode: string | null }) {
  return (
    <div className="rounded-xl border border-hairline-soft bg-surface-soft px-md py-2.5">
      <p className="mb-1 text-[11.5px] font-bold text-steel">확정 수치 <span className="font-medium text-stone">(계산 커널 결과)</span></p>
      <ul className="flex flex-col gap-1">
        {metrics.map((m) => (
          <li key={m.code} id={`met-${msgId}-${m.code}`} className={clsx("flex flex-wrap items-baseline gap-x-2 rounded-md px-1 text-[12.5px]", hotCode === m.code && "bg-info-soft")}>
            <CiteNo n={nOf(m.code)} />
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
  );
}

function FeedbackButtons({ m, onFeedback }: { m: BotMsg; onFeedback: (helpful: boolean) => void }) {
  const [failed, setFailed] = useState(false);
  const send = async (helpful: boolean) => {
    if (m.feedback !== undefined) return;
    try {
      const f = m.final;
      await apiPost("/assist/feedback", { question: m.question, helpful, mode: f?.mode, sourceCount: (f?.analysis.length ?? 0) + (f?.evidence.length ?? 0) });
      setFailed(false);
      onFeedback(helpful);
    } catch {
      setFailed(true); // 속도 제한(429) · 일시 오류 — 답변 사용에는 영향 없고, 다시 누르면 된다
    }
  };
  return (
    <>
      <IconButton label="도움이 됨" pressed={m.feedback === true} disabled={m.feedback === false} onClick={() => send(true)}>
        <IconThumbUp size={17} filled={m.feedback === true} />
      </IconButton>
      <IconButton label="도움이 안 됨" pressed={m.feedback === false} disabled={m.feedback === true} onClick={() => send(false)}>
        <IconThumbDown size={17} filled={m.feedback === false} />
      </IconButton>
      <span role="status" className="text-[11.5px] text-stone">
        {m.feedback !== undefined ? "의견을 남겼습니다. 고맙습니다." : failed ? "의견을 남기지 못했습니다. 잠시 뒤 다시 눌러 주세요." : ""}
      </span>
    </>
  );
}

export function AssistantMessage({ m, isLast, busy, onRegenerate, onFeedback }: { m: BotMsg; isLast: boolean; busy: boolean; onRegenerate: () => void; onFeedback: (helpful: boolean) => void }) {
  const streaming = m.status === "streaming";
  const meta: AssistMeta | undefined = m.final ?? m.meta;
  const srcId = useId();
  const [open, setOpen] = useState<boolean | null>(null); // null = 기본값(정리 답이면 펼침)
  const [showInfo, setShowInfo] = useState(false);
  const [hot, setHot] = useState<{ no?: number; code?: string } | null>(null);
  const [copied, setCopied] = useState(false);

  const numbered = useMemo(() => numberCites(collectCites(parseMarkdown(m.text)), meta), [m.text, meta]);
  // 인용 번호 → 출처 카드 / 수치 (같은 대상은 한 번호)
  const noBySource = useMemo(() => {
    const out = new Map<number, number>();
    const byMetric = new Map<string, number>();
    for (const t of numbered.values()) {
      if (t.sourceNo !== undefined) out.set(t.sourceNo, t.n);
      if (t.metricCode) byMetric.set(t.metricCode, t.n);
    }
    return { src: out, metric: byMetric };
  }, [numbered]);

  const fallback = m.final?.mode === "fallback";
  const sourceCount = (meta?.analysis.length ?? 0) + (meta?.evidence.length ?? 0);
  const sourcesOpen = open ?? (fallback && !streaming);

  const cites: CiteApi = {
    resolve: (kind, ref) => numbered.get(`${kind}:${ref}`),
    onOpen: (t: CiteTarget) => {
      setOpen(true);
      setHot({ no: t.sourceNo, code: t.metricCode });
      window.setTimeout(() => {
        const el = document.getElementById(t.metricCode ? `met-${m.id}-${t.metricCode}` : `src-${m.id}-${t.sourceNo}`);
        el?.scrollIntoView({ block: "nearest", behavior: "smooth" });
        el?.querySelector<HTMLElement>("a,button")?.focus({ preventScroll: true });
      }, 30);
    },
  };

  const copy = async () => {
    if (await copyText(plainForCopy(m.text))) {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    }
  };

  const waiting = streaming && !m.text;
  const metrics = meta?.metrics ?? [];
  const analysis = meta?.analysis ?? [];
  const evidence = meta?.evidence ?? [];

  return (
    <article aria-label="답변" aria-busy={streaming} className="flex gap-3" data-role="assistant" data-status={m.status}>
      <Avatar />
      <div className="min-w-0 flex-1">
        {waiting ? (
          <div role="status" className="flex items-center gap-2 py-1.5 text-[13px] text-steel">
            <Dots />
            <span>{m.stage || "답변을 준비하고 있습니다"}…</span>
          </div>
        ) : null}
        {streaming && meta && !m.text ? (
          <p className="mb-2 text-[11.5px] text-stone">
            찾은 자료: 분석 결과 {analysis.length} · 문서 {evidence.length} · 확정 수치 {metrics.length}
          </p>
        ) : null}

        {m.text || (!waiting && !m.error) ? (
          <Markdown
            source={m.text}
            cites={cites}
            trailing={streaming ? <span aria-hidden="true" className="ml-0.5 inline-block h-[1.05em] w-[2px] translate-y-[3px] bg-ink-deep motion-safe:animate-pulse" /> : undefined}
          />
        ) : null}

        {m.status === "stopped" ? <p className="mt-1 text-[12px] text-stone">{m.text ? "답변 생성을 중지했습니다." : "답변 생성을 중지했습니다. 다시 생성할 수 있습니다."}</p> : null}
        {m.status === "error" ? (
          <p role="alert" className="mt-1 rounded-xl bg-critical-faint px-md py-2 text-[12.5px] text-critical">
            {m.error ?? "답변을 만들지 못했습니다."}
          </p>
        ) : null}

        {m.status === "done" && m.final ? (
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            {m.final.mode === "llm" ? <Badge tone="info">LLM · {m.final.model}</Badge> : <Badge tone="attention">LLM 미연결 — 수치·분석·근거만</Badge>}
            {m.final.verification.passed ? <Badge tone="success">수치 출처 확인</Badge> : <Badge tone="critical">출처 없는 숫자 {m.final.verification.unverified.join(", ")}</Badge>}
            {m.final.concepts.map((c) => (
              <Badge key={c}>{c}</Badge>
            ))}
          </div>
        ) : null}

        {!streaming && metrics.length ? (
          <div className="mt-3">
            <MetricList metrics={metrics} nOf={(code) => noBySource.metric.get(code)} msgId={m.id} hotCode={hot?.code ?? null} />
          </div>
        ) : null}

        {!streaming && sourceCount > 0 ? (
          <div className="mt-3">
            <button
              type="button"
              aria-expanded={sourcesOpen}
              aria-controls={srcId}
              onClick={() => setOpen(!sourcesOpen)}
              className="inline-flex items-center gap-1.5 rounded-pill border border-hairline-soft px-3 py-1.5 text-[12px] font-bold text-charcoal hover:bg-surface-soft"
            >
              <IconChevron size={13} open={sourcesOpen} />
              출처 {sourceCount}건
              <span className="font-medium text-stone">분석 {analysis.length} · 문서 {evidence.length}</span>
            </button>
            <div id={srcId} hidden={!sourcesOpen} className="mt-2">
              {sourcesOpen ? (
                <div className="flex flex-col gap-3">
                  {analysis.length ? (
                    <section aria-label="분석 결과 · 용어 출처">
                      <p className="mb-1 text-[11.5px] font-bold text-steel">분석 결과 · 용어</p>
                      <ul className="flex flex-col gap-1.5">
                        {analysis.map((s, i) => (
                          <AnalysisCard key={`${s.sourceKey}-${i}`} s={s} id={`src-${m.id}-${s.no}`} n={s.no ? noBySource.src.get(s.no) : undefined} hot={hot?.no === s.no && s.no !== undefined} />
                        ))}
                      </ul>
                    </section>
                  ) : null}
                  {evidence.length ? (
                    <section aria-label="근거 문서 출처">
                      <p className="mb-1 text-[11.5px] font-bold text-steel">근거 문서</p>
                      <ul className="flex flex-col gap-1.5">
                        {evidence.map((e, i) => (
                          <EvidenceCard key={i} e={e} id={`src-${m.id}-${e.no}`} n={e.no ? noBySource.src.get(e.no) : undefined} hot={hot?.no === e.no && e.no !== undefined} />
                        ))}
                      </ul>
                      {meta?.missingCategories?.length ? <p className="mt-1 text-[11px] text-stone">{meta.missingCategories.map((c) => MISSING_LABEL[c] ?? c).join(" · ")} 근거는 찾지 못했습니다.</p> : null}
                    </section>
                  ) : null}
                </div>
              ) : null}
            </div>
          </div>
        ) : null}

        {m.status === "done" && !metrics.length && !sourceCount ? (
          <p className="mt-2 text-[11.5px] text-stone">내가 볼 수 있는 범위에서는 관련 자료를 찾지 못했습니다. 지표 · 상품 · 모형 이름을 넣어 다시 질문해 보세요.</p>
        ) : null}

        {!streaming ? (
          <div className="mt-2 flex flex-wrap items-center gap-0.5">
            {m.text ? (
              <IconButton label={copied ? "복사했습니다" : "답변 복사"} onClick={copy}>
                {copied ? <IconCheck size={17} /> : <IconCopy size={17} />}
              </IconButton>
            ) : null}
            {isLast ? (
              <IconButton label="다시 생성" onClick={onRegenerate} disabled={busy}>
                <IconRefresh size={17} />
              </IconButton>
            ) : null}
            {m.status === "done" ? <FeedbackButtons m={m} onFeedback={onFeedback} /> : null}
            {meta?.retrieval ? (
              <button type="button" aria-expanded={showInfo} onClick={() => setShowInfo((v) => !v)} className="ml-auto rounded-md px-2 py-1 text-[11.5px] text-stone hover:bg-surface-soft hover:text-ink-deep">
                검색 정보
              </button>
            ) : null}
          </div>
        ) : null}
        {showInfo && meta?.retrieval ? (
          <div className="mt-1 rounded-xl bg-surface-soft px-md py-2">
            <RetrievalNote r={meta.retrieval} />
          </div>
        ) : null}
      </div>
    </article>
  );
}
