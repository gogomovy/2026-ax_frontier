"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError } from "@/lib/api-client";
import { historyFor, loadConversations, newId, saveConversations, titleOf, type AssistAnswer, type AssistMeta, type BotMsg, type Conversation, type UserMsg } from "@/lib/assist-chat";
import { streamAsk } from "@/lib/assist-stream";

/** 스트리밍 글자를 화면에 반영하는 간격(ms) — 조각마다 다시 그리지 않고 모아서 */
const FLUSH_MS = 40;

/**
 * 질문하기 대화 상태 + 스트리밍 — 패널을 닫아도 진행 중인 답은 이어진다(패널 바깥에서 쓴다).
 * 대화는 이 탭의 sessionStorage 에만 둔다(서버 저장 없음).
 */
export function useAssistChat(empNo: string | null, screen: string | undefined) {
  const [convs, setConvs] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null); // 답을 쓰고 있는 봇 메시지 id
  const loaded = useRef(false);
  const abortRef = useRef<AbortController | null>(null);
  const buf = useRef<{ botId: string; convId: string; text: string; timer: number | null }>({ botId: "", convId: "", text: "", timer: null });
  const screenRef = useRef(screen);
  useEffect(() => {
    screenRef.current = screen;
  }, [screen]);

  /** 저장된 대화 읽기 — 패널을 처음 열 때 한 번(서버 렌더와 어긋나지 않게 이벤트에서). 다른 사용자의 기록은 이때 지워진다 */
  const load = useCallback(() => {
    if (!empNo || loaded.current) return;
    loaded.current = true;
    setConvs(loadConversations(window.sessionStorage, empNo));
  }, [empNo]);

  // 저장 — 답이 끝났거나 대화가 바뀔 때만(스트리밍 중 글자 하나마다 쓰지 않는다)
  const persistKey = useMemo(() => convs.map((c) => `${c.id}:${c.messages.length}:${c.messages.map((m) => (m.role === "assistant" ? `${m.status}${m.feedback === undefined ? "" : m.feedback ? "+" : "-"}` : "u")).join(",")}`).join("|"), [convs]);
  const convsRef = useRef(convs);
  useEffect(() => {
    convsRef.current = convs;
  }, [convs]);
  useEffect(() => {
    if (!empNo || !loaded.current || busyId) return;
    saveConversations(window.sessionStorage, empNo, convsRef.current); // persistKey 가 대화 구조(개수 · 상태)의 변화를 대표한다
  }, [empNo, persistKey, busyId]);

  const active = useMemo(() => convs.find((c) => c.id === activeId) ?? null, [convs, activeId]);

  const patchBot = useCallback((convId: string, botId: string, patch: Partial<BotMsg> | ((b: BotMsg) => Partial<BotMsg>)) => {
    setConvs((prev) =>
      prev.map((c) =>
        c.id !== convId
          ? c
          : { ...c, updatedAt: Date.now(), messages: c.messages.map((m) => (m.id === botId && m.role === "assistant" ? { ...m, ...(typeof patch === "function" ? patch(m) : patch) } : m)) },
      ),
    );
  }, []);

  const flush = useCallback(() => {
    const b = buf.current;
    if (b.timer !== null) {
      window.clearTimeout(b.timer);
      b.timer = null;
    }
    if (b.botId) {
      const text = b.text;
      patchBot(b.convId, b.botId, { text, stage: undefined });
    }
  }, [patchBot]);

  const run = useCallback(
    async (convId: string, botId: string, question: string, history: { q: string; a: string }[]) => {
      const ac = new AbortController();
      abortRef.current = ac;
      setBusyId(botId);
      buf.current = { botId, convId, text: "", timer: null };
      let finished = false;
      try {
        await streamAsk(
          { question, screen: screenRef.current, history },
          {
            onEvent: ({ event, data }) => {
              const d = data as Record<string, unknown>;
              if (event === "stage") patchBot(convId, botId, (b) => (b.text ? {} : { stage: String(d.label ?? "") }));
              else if (event === "meta") patchBot(convId, botId, { meta: d as unknown as AssistMeta });
              else if (event === "delta") {
                buf.current.text += String(d.text ?? "");
                if (buf.current.timer === null) buf.current.timer = window.setTimeout(flush, FLUSH_MS);
              } else if (event === "reset") {
                buf.current.text = "";
                flush();
              } else if (event === "done") {
                finished = true;
                if (buf.current.timer !== null) window.clearTimeout(buf.current.timer);
                buf.current = { botId: "", convId: "", text: "", timer: null };
                const f = d as unknown as AssistAnswer;
                patchBot(convId, botId, { text: f.answer ?? "", status: "done", stage: undefined, final: f, meta: f, error: undefined });
              } else if (event === "error") {
                finished = true;
                patchBot(convId, botId, { status: "error", stage: undefined, error: String(d.message ?? "답변을 만들지 못했습니다.") });
              }
            },
          },
          ac.signal,
        );
        if (!finished) patchBot(convId, botId, (b) => ({ status: b.text ? "stopped" : "error", stage: undefined, error: b.text ? undefined : "연결이 끊겼습니다. 다시 시도해 주세요." })); // 서버가 done 없이 끊음
      } catch (e) {
        flush();
        if ((e as Error).name === "AbortError") patchBot(convId, botId, { status: "stopped", stage: undefined });
        else patchBot(convId, botId, { status: "error", stage: undefined, error: e instanceof ApiError ? e.message : "답변을 만들지 못했습니다. 잠시 뒤 다시 시도해 주세요." });
      } finally {
        flush();
        buf.current = { botId: "", convId: "", text: "", timer: null };
        if (abortRef.current === ac) abortRef.current = null;
        setBusyId((cur) => (cur === botId ? null : cur));
      }
    },
    [flush, patchBot],
  );

  const send = useCallback(
    (question: string) => {
      const q = question.trim();
      if (q.length < 2 || busyId) return false;
      const now = Date.now();
      const user: UserMsg = { id: newId("u"), role: "user", text: q, at: now };
      const bot: BotMsg = { id: newId("b"), role: "assistant", text: "", at: now, status: "streaming", stage: "질문 받음", question: q };
      let convId = activeId;
      let history: { q: string; a: string }[] = [];
      const cur = convs.find((c) => c.id === convId);
      if (cur) {
        history = historyFor(cur.messages);
        setConvs((prev) => prev.map((c) => (c.id === cur.id ? { ...c, updatedAt: now, messages: [...c.messages, user, bot] } : c)));
      } else {
        convId = newId("c");
        const conv: Conversation = { id: convId, title: titleOf(q), updatedAt: now, messages: [user, bot] };
        setConvs((prev) => [conv, ...prev]);
        setActiveId(convId);
      }
      void run(convId!, bot.id, q, history);
      return true;
    },
    [activeId, busyId, convs, run],
  );

  /** 마지막 답을 지우고 같은 질문으로 다시 만든다 */
  const regenerate = useCallback(
    (botId: string) => {
      if (busyId || !active) return;
      const idx = active.messages.findIndex((m) => m.id === botId);
      const old = active.messages[idx];
      if (idx < 1 || !old || old.role !== "assistant") return;
      const q = (active.messages[idx - 1] as UserMsg).text;
      const bot: BotMsg = { id: newId("b"), role: "assistant", text: "", at: Date.now(), status: "streaming", stage: "질문 받음", question: q };
      const history = historyFor(active.messages.slice(0, idx - 1));
      setConvs((prev) => prev.map((c) => (c.id === active.id ? { ...c, messages: [...c.messages.slice(0, idx), bot, ...c.messages.slice(idx + 1)] } : c)));
      void run(active.id, bot.id, q, history);
    },
    [active, busyId, run],
  );

  const stop = useCallback(() => abortRef.current?.abort(), []);

  const newChat = useCallback(() => {
    if (busyId) return; // 답을 쓰는 중에는 대화를 바꾸지 않는다(중지하면 가능)
    setActiveId(null);
  }, [busyId]);

  const open = useCallback((id: string) => setActiveId(id), []);

  const remove = useCallback(
    (id: string) => {
      if (busyId && active?.id === id) abortRef.current?.abort();
      setConvs((prev) => prev.filter((c) => c.id !== id));
      setActiveId((cur) => (cur === id ? null : cur));
    },
    [active, busyId],
  );

  const clearAll = useCallback(() => {
    abortRef.current?.abort();
    setConvs([]);
    setActiveId(null);
  }, []);

  const setFeedback = useCallback((convId: string, botId: string, helpful: boolean) => patchBot(convId, botId, { feedback: helpful }), [patchBot]);

  // 탭을 떠날 때 진행 중인 요청을 끊는다
  useEffect(() => () => abortRef.current?.abort(), []);

  return { convs, active, activeId, busyId, load, send, stop, regenerate, newChat, open, remove, clearAll, setFeedback };
}
