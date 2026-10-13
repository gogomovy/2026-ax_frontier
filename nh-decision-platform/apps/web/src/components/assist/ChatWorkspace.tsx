"use client";

import clsx from "clsx";
import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { Badge } from "@/components/ui/primitives";
import { apiGetC } from "@/lib/api-client";
import type { ScopeItem } from "@/lib/assist-chat";
import { AssistantMessage, UserMessage } from "./ChatMessages";
import { ASSIST_NAME } from "./brand";
import { IconArrowDown, IconBot, IconClose, IconCollapse, IconExpand, IconList, IconPlus, IconSend, IconStop, IconTrash } from "./icons";
import type { useAssistChat } from "./useAssistChat";

const EXAMPLES = [
  { q: "포용금융 충당금 비중은 얼마인가요?", hint: "확정 수치와 분석 결과" },
  { q: "소기업 6B 등급 부도율은 예측 대비 어떤가요?", hint: "모형 모니터링" },
  { q: "기업여신 증가율과 목표 대비 이탈은?", hint: "목표 대비 현황" },
  { q: "가계부채 관리 기조 관련 근거를 알려줘", hint: "정책 근거 문서" },
];
const MAX_LEN = 500;

type Chat = ReturnType<typeof useAssistChat>;

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
  const messages = active?.messages ?? [];
  const busy = busyId !== null;
  const [q, setQ] = useState("");
  const [showList, setShowList] = useState(false);
  const [scope, setScope] = useState<ScopeItem[] | null>(null);
  const [showJump, setShowJump] = useState(false);
  const taRef = useRef<HTMLTextAreaElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const stick = useRef(true);

  // 내가 질문할 수 있는 범위 — 현재 화면 기준(권한 밖 컬렉션은 응답에 없다)
  useEffect(() => {
    let alive = true;
    apiGetC<{ collections: ScopeItem[] }>(`/assist/scope?screen=${encodeURIComponent(pathname || "/")}`)
      .then((r) => alive && setScope(r.collections))
      .catch(() => alive && setScope(null));
    return () => {
      alive = false;
    };
  }, [pathname]);

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
        <h2 id={titleId} className="flex items-center gap-2 text-[15px] font-bold text-ink-deep">
          <span aria-hidden="true" className="flex h-7 w-7 items-center justify-center rounded-circle bg-ink-deep text-white">
            <IconBot size={17} />
          </span>
          {ASSIST_NAME}
        </h2>
        <span className="hidden truncate text-[11.5px] text-stone sm:inline">확정 수치(계산 커널) · 우리 팀 분석 결과 · 근거 문서만으로 답합니다</span>
        <div className="ml-auto flex items-center gap-0.5">
          <button
            type="button"
            onClick={() => {
              chat.newChat();
              setShowList(false);
              taRef.current?.focus();
            }}
            disabled={busy}
            className="flex items-center gap-1 rounded-lg px-2.5 py-2 text-[12.5px] font-bold text-charcoal hover:bg-surface-soft disabled:cursor-not-allowed disabled:opacity-40"
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
            <p className="text-[12px] font-bold text-steel">이 탭의 대화</p>
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
                  <span className="block text-[11px] text-stone">{relTime(c.updatedAt)}</span>
                </button>
                <button type="button" onClick={() => chat.remove(c.id)} aria-label={`대화 삭제: ${c.title}`} title="삭제" className="ml-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-stone hover:bg-canvas hover:text-critical">
                  <IconTrash size={15} />
                </button>
              </li>
            ))}
            {!convs.length ? <li className="px-2.5 py-3 text-[12px] text-stone">아직 대화가 없습니다. 대화는 이 브라우저 탭에만 저장되고 탭을 닫으면 사라집니다.</li> : null}
          </ul>
        </aside>
        {showList ? <button type="button" aria-label="대화 목록 닫기" tabIndex={-1} onClick={() => setShowList(false)} className={clsx("absolute inset-0 z-10 bg-scrim", expanded && "lg:hidden")} /> : null}

        <div className="relative flex min-w-0 flex-1 flex-col">
          <div ref={scrollRef} onScroll={onScroll} role="log" aria-label="대화 내용" aria-live="off" className="min-h-0 flex-1 overflow-y-auto">
            <div className="mx-auto flex w-full max-w-[780px] flex-col gap-6 px-4 py-6">
              {!messages.length ? (
                <div className="flex flex-col items-center pt-6 text-center">
                  <span aria-hidden="true" className="flex h-14 w-14 items-center justify-center rounded-circle bg-ink-deep text-white shadow-panel">
                    <IconBot size={30} />
                  </span>
                  <p className="mt-4 text-[22px] font-bold text-ink-deep">안녕하세요, 무엇을 도와드릴까요?</p>
                  <p className="mt-1 max-w-[520px] text-[13px] leading-relaxed text-steel">
                    저는 {ASSIST_NAME}예요. 확정된 수치와 우리 팀 분석 결과, 근거 문서에서 찾아 출처와 함께 답해요. 권한이 있는 범위만 검색합니다.
                  </p>
                  {scope ? (
                    <div className="mt-4 flex max-w-[600px] flex-wrap justify-center gap-1.5" role="group" aria-label="질문할 수 있는 범위">
                      {scope.map((c) => (
                        <Badge key={c.code} tone={c.owned ? "primary" : "neutral"}>
                          {c.label}
                          {c.owned ? " · 담당" : c.partial ? " · 일부" : ""}
                        </Badge>
                      ))}
                    </div>
                  ) : null}
                  <ul className="mt-6 grid w-full max-w-[640px] grid-cols-1 gap-2 sm:grid-cols-2">
                    {EXAMPLES.map((ex) => (
                      <li key={ex.q}>
                        <button type="button" onClick={() => ask(ex.q)} disabled={busy} className="h-full w-full rounded-2xl border border-hairline-soft px-4 py-3 text-left transition-colors hover:border-hairline hover:bg-surface-soft disabled:opacity-50">
                          <span className="block text-[13px] font-medium text-ink-deep">{ex.q}</span>
                          <span className="mt-0.5 block text-[11.5px] text-stone">{ex.hint}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
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
                  placeholder="무엇이든 물어보세요  (이어서 “그럼 증가율은?” 처럼 물어도 돼요)"
                  className="max-h-[168px] min-h-[28px] flex-1 resize-none border-0 bg-transparent py-1 text-[14px] leading-relaxed text-ink outline-none placeholder:text-stone"
                />
                {busy ? (
                  <button type="button" onClick={chat.stop} aria-label="답변 생성 중지" title="중지" className="flex h-9 w-9 shrink-0 items-center justify-center rounded-circle bg-ink-deep text-white hover:opacity-90">
                    <IconStop size={15} />
                  </button>
                ) : (
                  <button type="submit" disabled={q.trim().length < 2} title="보내기 (Enter)" className="flex h-9 w-9 shrink-0 items-center justify-center rounded-circle bg-ink-deep text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:bg-disabled">
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
