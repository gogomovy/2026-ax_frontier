"use client";

import clsx from "clsx";
import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { useUiConfig } from "@/components/providers/SessionProvider";
import { AssistantMessage, UserMessage } from "./ChatMessages";
import { ASSIST_NAME } from "./brand";
import { IconArrowDown, IconBot, IconClose, IconCollapse, IconExpand, IconList, IconPlus, IconSend, IconStop, IconTrash } from "./icons";
import type { useAssistChat } from "./useAssistChat";


const MAX_LEN = 500;

type Chat = ReturnType<typeof useAssistChat>;

const MAX_TOPICS = 5; // 440px 도킹 폭에서 칩이 두 줄 안에 들어가는 개수
const MAX_TOPIC_QS = 4;
/** 예시 질문의 hint(관리자 설정) → 짧은 주제 칩 이름 · 함께 추천할 질문(수치를 박지 않은 일반 질문) */
const TOPIC_PRESETS: Record<string, { label: string; more: string[] }> = {
  "확정 수치와 분석 결과": { label: "핵심 수치", more: ["이번 달 주요 지표 변화를 요약해줘", "우리 팀 분석 결과 중 최근 것은?"] },
  "모형 모니터링": { label: "모형 모니터링", more: ["예측 대비 실적 차이가 큰 등급은?", "최근 모형 점검 결과를 알려줘"] },
  "목표 대비 현황": { label: "목표 대비", more: ["목표 대비 이탈이 큰 지표는?", "목표 달성률이 낮은 항목을 알려줘"] },
  "정책 근거 문서": { label: "근거 문서", more: ["최근 반영된 정책 문서는?", "관련 규정 근거를 출처와 함께 알려줘"] },
};
/** 입력창 기본 문구 — 도킹 폭(440px)에서 한 줄에 들어가는 길이만 예시로 쓴다 */
const PLACEHOLDER_MAX = 22;

function buildTopics(examples: { q: string; hint: string }[]): { label: string; qs: string[] }[] {
  const map = new Map<string, string[]>();
  for (const ex of examples) {
    const key = ex.hint || "기타";
    map.set(key, [...(map.get(key) ?? []), ex.q]);
  }
  return [...map.entries()].slice(0, MAX_TOPICS).map(([hint, qs]) => {
    const preset = TOPIC_PRESETS[hint];
    const all = [...qs, ...(preset?.more ?? [])].filter((v, i, a) => a.indexOf(v) === i);
    return { label: preset?.label ?? hint, qs: all.slice(0, MAX_TOPIC_QS) };
  });
}

function relTime(ts: number): string {
  const min = Math.floor((Date.now() - ts) / 60000);
  if (min < 1) return "방금";
  if (min < 60) return `${min}분 전`;
  const h = Math.floor(min / 60);
  return h < 24 ? `${h}시간 전` : `${Math.floor(h / 24)}일 전`;
}

/** ChatGPT 형 대화 화면 — 대화 목록 · 메시지(스트리밍) · 하단 입력창. 답변은 확정 수치 · 팀 분석 결과 · 근거 문서만으로 */
export function ChatWorkspace({ chat, pathname, expanded, onToggleExpand, onClose, titleId }: { chat: Chat; pathname: string; expanded: boolean; onToggleExpand: () => void; onClose: () => void; titleId: string }) {
  const { active, convs, busyId } = chat;
  // 예시 질문 — 관리자 [화면 설정 › 예시 질문] (Phase K · HC-02). 비어 있으면 예시를 그리지 않는다
  const examples = useUiConfig().examples.assist ?? [];
  const topics = buildTopics(examples);
  const [topic, setTopic] = useState<string | null>(null);
  const openTopic = topics.find((t) => t.label === topic) ?? null;
  const shortEx = examples.map((e) => e.q).filter((s) => s.length <= PLACEHOLDER_MAX).sort((a, b) => a.length - b.length)[0];
  const placeholder = shortEx ? `예시) ${shortEx}` : "무엇이든 물어보세요";
  const messages = active?.messages ?? [];
  const busy = busyId !== null;
  const [q, setQ] = useState("");
  const [showList, setShowList] = useState(false);
  const [showJump, setShowJump] = useState(false);
  const taRef = useRef<HTMLTextAreaElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const stick = useRef(true);

  // 열리면 입력칸으로
  useEffect(() => {
    const t = window.setTimeout(() => taRef.current?.focus(), 40);
    return () => window.clearTimeout(t);
  }, []);

  // 입력칸 높이 자동 조절(최대 6줄 안팎)
  useEffect(() => {
    const ta = taRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = `${Math.min(ta.scrollHeight, 168)}px`;
  }, [q]);

  // 새 글이 오면 맨 아래로 — 사용자가 위로 올려 읽는 중이면 따라가지 않는다
  const tail = messages[messages.length - 1];
  const sig = `${active?.id}:${messages.length}:${tail?.role === "assistant" ? `${tail.text.length}${tail.status}${tail.stage ?? ""}${tail.meta ? 1 : 0}` : ""}`;
  useEffect(() => {
    const el = scrollRef.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [sig]);
  const onScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    const near = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    stick.current = near;
    setShowJump(!near);
  };
  const jump = () => {
    const el = scrollRef.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    stick.current = true;
    setShowJump(false);
  };

  const ask = (text: string) => {
    if (chat.send(text)) {
      setQ("");
      stick.current = true;
      setShowJump(false);
      taRef.current?.focus();
    }
  };
  const submit = (e: FormEvent) => {
    e.preventDefault();
    ask(q);
  };
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    // 한글 조합 중의 Enter 는 글자 확정이지 전송이 아니다
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing && e.keyCode !== 229) {
      e.preventDefault();
      ask(q);
    }
  };

  // 화면 낭독기용 상태 안내 — 스트리밍 글자는 읽지 않고(수십 번 끊겨 읽힘) 시작 · 끝만 알린다
  const live =
    tail?.role !== "assistant"
      ? ""
      : tail.status === "streaming"
        ? "답변을 작성하고 있습니다"
        : tail.status === "done"
          ? `답변이 도착했습니다. ${tail.text.replace(/[*#|`>-]/g, "").slice(0, 160)}`
          : tail.status === "error"
            ? "답변을 만들지 못했습니다"
            : "답변 생성을 중지했습니다";

  const lastBotIdx = (() => {
    for (let i = messages.length - 1; i >= 0; i--) if (messages[i].role === "assistant") return i;
    return -1;
  })();

  const sidebarCls = clsx(
    "w-[272px] shrink-0 flex-col border-r border-hairline-soft bg-surface-soft",
    showList ? "absolute inset-y-0 left-0 z-20 flex shadow-pop" : expanded ? "hidden lg:flex" : "hidden",
    expanded && showList && "lg:static lg:shadow-none",
  );

  return (
    <>
      <header className="flex items-center gap-2 border-b border-hairline-soft px-3 py-2.5">
        <button
          type="button"
          onClick={() => setShowList((v) => !v)}
          aria-expanded={showList}
          aria-label="대화 목록"
          title="대화 목록"
          className={clsx("flex h-9 w-9 items-center justify-center rounded-lg text-charcoal hover:bg-surface-soft", expanded && "lg:hidden")}
        >
          <IconList />
        </button>
        <h2 id={titleId} className="flex shrink-0 items-center gap-2 whitespace-nowrap text-[15px] font-bold text-ink-deep">
          <span aria-hidden="true" className="flex h-7 w-7 items-center justify-center rounded-circle bg-primary text-white">
            <IconBot size={17} />
          </span>
          {ASSIST_NAME}
        </h2>
        <span className="hidden min-w-0 truncate text-[11.5px] text-stone sm:inline">확정 수치(계산 커널) · 우리 팀 분석 결과 · 근거 문서만으로 답합니다</span>
        <div className="ml-auto flex shrink-0 items-center gap-0.5">
          <button
            type="button"
            onClick={() => {
              chat.newChat();
              setShowList(false);
              taRef.current?.focus();
            }}
            disabled={busy}
            className="flex items-center gap-1 whitespace-nowrap rounded-lg px-2.5 py-2 text-[12.5px] font-bold text-charcoal hover:bg-surface-soft disabled:cursor-not-allowed disabled:opacity-40"
          >
            <IconPlus size={15} /> 새 대화
          </button>
          <button type="button" onClick={onToggleExpand} aria-pressed={expanded} aria-label={expanded ? "작게 보기" : "크게 보기"} title={expanded ? "작게 보기" : "크게 보기"} className="hidden h-9 w-9 items-center justify-center rounded-lg text-charcoal hover:bg-surface-soft sm:flex">
            {expanded ? <IconCollapse /> : <IconExpand />}
          </button>
          <button type="button" onClick={onClose} aria-label="닫기" title="닫기" className="flex h-9 w-9 items-center justify-center rounded-lg text-charcoal hover:bg-surface-soft">
            <IconClose />
          </button>
        </div>
      </header>

      <div className="relative flex min-h-0 flex-1">
        <aside aria-label="대화 목록" className={sidebarCls}>
          <div className="flex items-center justify-between px-3 pb-1 pt-3">
            <p className="text-[12px] font-bold text-steel">내 대화</p>
            {convs.length ? (
              <button type="button" onClick={chat.clearAll} className="text-[11.5px] text-stone hover:text-critical">
                모두 지우기
              </button>
            ) : null}
          </div>
          <ul className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
            {convs.map((c) => (
              <li key={c.id} className="group flex items-center">
                <button
                  type="button"
                  aria-current={c.id === chat.activeId ? "true" : undefined}
                  onClick={() => {
                    chat.open(c.id);
                    setShowList(false);
                  }}
                  disabled={busy && c.id !== chat.activeId}
                  className={clsx("min-w-0 flex-1 rounded-lg px-2.5 py-2 text-left hover:bg-canvas disabled:opacity-50", c.id === chat.activeId && "bg-canvas shadow-panel")}
                >
                  <span className="block truncate text-[13px] font-medium text-ink-deep">{c.title}</span>
                  <span className="block text-[11px] text-stone">
                    {relTime(c.updatedAt)}
                    {c.hasSummary ? <span title="이전 대화 요약이 저장되어 다시 열면 이어서 질문할 수 있습니다"> · 요약 저장됨</span> : null}
                  </span>
                </button>
                <button type="button" onClick={() => chat.remove(c.id)} aria-label={`대화 삭제: ${c.title}`} title="삭제" className="ml-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-stone hover:bg-canvas hover:text-critical">
                  <IconTrash size={15} />
                </button>
              </li>
            ))}
            {!convs.length ? <li className="px-2.5 py-3 text-[12px] text-stone">아직 대화가 없습니다. 대화는 내 계정에 저장되어 다시 열면 이전 내용(요약)을 이어 받아 질문할 수 있습니다.</li> : null}
          </ul>
        </aside>
        {showList ? <button type="button" aria-label="대화 목록 닫기" tabIndex={-1} onClick={() => setShowList(false)} className={clsx("absolute inset-0 z-10 bg-scrim", expanded && "lg:hidden")} /> : null}

        <div className="relative flex min-w-0 flex-1 flex-col">
          <div ref={scrollRef} onScroll={onScroll} role="log" aria-label="대화 내용" aria-live="off" className="min-h-0 flex-1 overflow-y-auto">
            <div className="mx-auto flex w-full max-w-[780px] flex-col gap-6 px-4 py-6">
              {!messages.length && active && chat.loadingId === active.id ? (
                <p role="status" className="pt-10 text-center text-[13px] text-stone">
                  대화를 불러오는 중…
                </p>
              ) : !messages.length ? (
                <div className="flex flex-col items-center pt-6 text-center">
                  <span aria-hidden="true" className="flex h-14 w-14 items-center justify-center rounded-circle bg-primary text-white shadow-panel">
                    <IconBot size={30} />
                  </span>
                  <p className="mt-4 text-[22px] font-bold text-ink-deep">안녕하세요, 무엇을 도와드릴까요?</p>
                  {/* 칩은 한 종류만 — 누르면 아래에 추천 질문이 열리는 주제 칩. (질문 범위 배지 줄은 헤더 안내문과 겹쳐 뺐다) */}
                  {topics.length ? (
                    <div className="mt-6 flex w-full max-w-[640px] flex-col items-center">
                      <div className="flex flex-wrap justify-center gap-1.5" role="group" aria-label="질문 주제">
                        {topics.map((t) => {
                          const on = t.label === openTopic?.label;
                          return (
                            <button
                              key={t.label}
                              type="button"
                              onClick={() => setTopic(on ? null : t.label)}
                              aria-pressed={on}
                              aria-expanded={on}
                              aria-controls="assist-topic-qs"
                              className={clsx(
                                "whitespace-nowrap rounded-pill border px-3 py-1.5 text-[12.5px] font-medium transition-colors",
                                on ? "border-primary bg-info-soft text-primary" : "border-hairline-soft text-charcoal hover:border-hairline hover:bg-surface-soft",
                              )}
                            >
                              {t.label}
                            </button>
                          );
                        })}
                      </div>
                      {openTopic ? (
                        <ul id="assist-topic-qs" aria-label={`${openTopic.label} 추천 질문`} className="mt-3 flex w-full flex-col gap-1 text-left">
                          {openTopic.qs.map((qq) => (
                            <li key={qq}>
                              <button type="button" onClick={() => ask(qq)} disabled={busy} className="w-full rounded-xl px-3 py-2 text-left text-[13px] text-ink-deep transition-colors hover:bg-surface-soft disabled:opacity-50">
                                {qq}
                              </button>
                            </li>
                          ))}
                        </ul>
                      ) : null}
                    </div>
                  ) : null}
                </div>
              ) : (
                messages.map((m, i) =>
                  m.role === "user" ? (
                    <UserMessage key={m.id} m={m} />
                  ) : (
                    <AssistantMessage key={m.id} m={m} isLast={i === lastBotIdx} busy={busy} onRegenerate={() => chat.regenerate(m.id)} onFeedback={(h) => active && chat.setFeedback(active.id, m.id, h)} />
                  ),
                )
              )}
            </div>
          </div>

          {showJump ? (
            <button type="button" onClick={jump} aria-label="최신 답변으로 이동" className="absolute bottom-[112px] left-1/2 z-10 flex h-9 w-9 -translate-x-1/2 items-center justify-center rounded-circle border border-hairline bg-canvas text-charcoal shadow-pop hover:bg-surface-soft">
              <IconArrowDown />
            </button>
          ) : null}

          <div className="border-t border-hairline-soft bg-canvas px-4 pb-3 pt-3">
            <form onSubmit={submit} className="mx-auto w-full max-w-[780px]">
              <div className="flex items-end gap-2 rounded-3xl border border-hairline bg-canvas py-2 pl-4 pr-2 shadow-panel focus-within:border-primary focus-within:ring-2 focus-within:ring-primary">
                <label htmlFor="assist-q" className="sr-only">
                  질문
                </label>
                <textarea
                  id="assist-q"
                  ref={taRef}
                  rows={1}
                  maxLength={MAX_LEN}
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  onKeyDown={onKey}
                  placeholder={placeholder}
                  className="max-h-[168px] min-h-[28px] flex-1 resize-none border-0 bg-transparent py-1 text-[14px] leading-relaxed text-ink outline-none placeholder:text-stone"
                />
                {busy ? (
                  <button type="button" onClick={chat.stop} aria-label="답변 생성 중지" title="중지" className="flex h-9 w-9 shrink-0 items-center justify-center rounded-circle bg-primary text-white hover:opacity-90">
                    <IconStop size={15} />
                  </button>
                ) : (
                  <button type="submit" disabled={q.trim().length < 2} title="보내기 (Enter)" className="flex h-9 w-9 shrink-0 items-center justify-center rounded-circle bg-primary text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:bg-disabled">
                    <IconSend size={17} />
                    <span className="sr-only">질문</span>
                  </button>
                )}
              </div>
              <p className="mt-1.5 flex flex-wrap items-center justify-center gap-x-3 text-center text-[11px] text-stone">
                <span>Enter 전송 · Shift+Enter 줄바꿈</span>
                {q.length > MAX_LEN - 80 ? <span className={q.length >= MAX_LEN ? "text-critical" : ""}>{q.length}/{MAX_LEN}</span> : null}
                <span>답변은 출처로 확인하세요 · 대화는 이 탭에만 저장됩니다</span>
              </p>
            </form>
          </div>
          <div role="status" aria-live="polite" className="sr-only">
            {live}
          </div>
        </div>
      </div>
    </>
  );
}
