"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError, apiDelete, apiGetC } from "@/lib/api-client";
import {
  fromServerList,
  fromServerMessages,
  historyFor,
  newId,
  titleOf,
  type AssistAnswer,
  type AssistMeta,
  type BotMsg,
  type Conversation,
  type ServerConversation,
  type ServerMessage,
  type UserMsg,
} from "@/lib/assist-chat";
import { streamAsk, type AskBody } from "@/lib/assist-stream";

/** 스트리밍 글자를 화면에 반영하는 간격(ms) — 조각마다 다시 그리지 않고 모아서 */
const FLUSH_MS = 40;
/** 예전(서버 저장 전) 이 탭에만 두던 기록의 키 — 읽지 않고 지운다 */
const LEGACY_KEY = "nhdip.assist.v1";

type ServerDetail = ServerConversation & { summary?: string | null; messages: ServerMessage[] };
type Done = AssistAnswer & { conversationId?: string; conversation?: ServerConversation };

/** 대화를 떠날 때 — 서버가 아직 요약에 안 들어간 원문까지 전체 요약을 저장한다. 창을 닫는 중에도 끝까지 가도록 keepalive */
function closeRemote(id: string) {
  try {
    void fetch(`/backend/assist/conversations/${encodeURIComponent(id)}/close`, { method: "POST", credentials: "same-origin", keepalive: true }).catch(() => undefined);
  } catch {
    /* 창을 닫는 중 — 다음에 열 때 서버가 맥락 예산 안에서 다시 정리한다 */
  }
}

/**
 * 질문하기 대화 상태 + 스트리밍 — 패널을 닫아도 진행 중인 답은 이어진다(패널 바깥에서 쓴다).
 * 대화는 서버에 사번별로 저장된다(knowledge.memory) — 질문마다 대화 id 를 보내면 서버가 누적 요약 + 원문으로 멀티턴 맥락을 만들고 이번 턴을 저장한다.
 * 다른 대화 · 새 대화로 옮기거나 창을 닫으면 그 대화를 '떠남'으로 알려 전체 요약을 남긴다(다시 열면 그 요약으로 이어 간다).
 */
export function useAssistChat(empNo: string | null, screen: string | undefined) {
  const [convs, setConvs] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null); // 답을 쓰고 있는 봇 메시지 id
  const [loadingId, setLoadingId] = useState<string | null>(null); // 메시지를 불러오는 대화 id
  const loadedFor = useRef<string | null>(null); // 목록을 불러온 사번
  const dirty = useRef(new Set<string>()); // 마지막 '떠남' 뒤로 새 턴이 저장된 대화
  const abortRef = useRef<AbortController | null>(null);
  const buf = useRef<{ botId: string; convId: string; text: string; timer: number | null }>({ botId: "", convId: "", text: "", timer: null });
  const screenRef = useRef(screen);
  useEffect(() => {
    screenRef.current = screen;
  }, [screen]);

  /** 내 대화 목록 — 패널을 처음 열 때 한 번(서버 렌더와 어긋나지 않게 이벤트에서). 사용자가 바뀌었으면 이전 사용자의 화면 상태를 비운다 */
  const load = useCallback(() => {
    if (!empNo || loadedFor.current === empNo) return;
    if (loadedFor.current !== null) {
      setConvs([]);
      setActiveId(null);
      dirty.current.clear();
    }
    loadedFor.current = empNo;
    try {
      const store = window.sessionStorage;
      const stale: string[] = [];
      for (let i = 0; i < store.length; i++) {
        const k = store.key(i);
        if (k && k.startsWith(LEGACY_KEY)) stale.push(k);
      }
      stale.forEach((k) => store.removeItem(k));
    } catch {
      /* 저장소를 못 쓰는 환경 */
    }
    apiGetC<{ items: ServerConversation[] }>("/assist/conversations")
      .then((r) => {
        if (loadedFor.current !== empNo) return;
        const remote = fromServerList(r.items ?? []);
        setConvs((prev) => {
          const have = new Set(prev.map((c) => c.id));
          return [...prev, ...remote.filter((c) => !have.has(c.id))].sort((a, b) => b.updatedAt - a.updatedAt);
        });
      })
      .catch(() => {
        if (loadedFor.current === empNo) loadedFor.current = null; // 다음에 열 때 다시
      });
  }, [empNo]);

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

  /** 서버에 저장된 턴 — 대화를 '떠날 때 요약' 대상으로 표시하고 목록 정보(개수 · 요약 여부 · 제목)를 맞춘다 */
  const saved = useCallback((convId: string, f: Done) => {
    if (!f.conversationId) return;
    dirty.current.add(convId);
    const s = f.conversation;
    setConvs((prev) => prev.map((c) => (c.id === convId ? { ...c, remote: true, loaded: true, ...(s ? { title: s.title || c.title, messageCount: s.messageCount, hasSummary: s.hasSummary } : {}) } : c)));
  }, []);

  const run = useCallback(
    async (convId: string, botId: string, body: Omit<AskBody, "screen">) => {
      const ac = new AbortController();
      abortRef.current = ac;
      setBusyId(botId);
      buf.current = { botId, convId, text: "", timer: null };
      let finished = false;
      try {
        await streamAsk(
          { ...body, screen: screenRef.current },
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
                const f = d as unknown as Done;
                patchBot(convId, botId, { text: f.answer ?? "", status: "done", stage: undefined, final: f, meta: f, error: undefined });
                saved(convId, f);
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
    [flush, patchBot, saved],
  );

  const send = useCallback(
    (question: string) => {
      const q = question.trim();
      if (q.length < 2 || busyId || (activeId && loadingId === activeId)) return false;
      const now = Date.now();
      const user: UserMsg = { id: newId("u"), role: "user", text: q, at: now };
      const bot: BotMsg = { id: newId("b"), role: "assistant", text: "", at: now, status: "streaming", stage: "질문 받음", question: q };
      let convId = activeId;
      let history: { q: string; a: string }[] = [];
      const cur = convs.find((c) => c.id === convId);
      if (cur) {
        history = historyFor(cur.messages); // 대화 기억이 꺼져 있을 때만 서버가 쓴다
        setConvs((prev) => prev.map((c) => (c.id === cur.id ? { ...c, updatedAt: now, messages: [...c.messages, user, bot] } : c)));
      } else {
        convId = newId("c");
        const conv: Conversation = { id: convId, title: titleOf(q), updatedAt: now, messages: [user, bot], loaded: true };
        setConvs((prev) => [conv, ...prev]);
        setActiveId(convId);
      }
      void run(convId!, bot.id, { question: q, history, conversationId: convId! });
      return true;
    },
    [activeId, busyId, convs, loadingId, run],
  );

  /** 마지막 답을 지우고 같은 질문으로 다시 만든다 — 서버도 마지막 턴(같은 질문)을 새 답으로 바꾼다 */
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
      void run(active.id, bot.id, { question: q, history, conversationId: active.id, replaceLast: true });
    },
    [active, busyId, run],
  );

  const stop = useCallback(() => abortRef.current?.abort(), []);

  /** 대화를 떠난다 — 새 턴이 있었으면 서버에 전체 요약을 남기게 한다 */
  const leave = useCallback((id: string | null) => {
    if (id && dirty.current.delete(id)) closeRemote(id);
  }, []);

  const newChat = useCallback(() => {
    if (busyId) return; // 답을 쓰는 중에는 대화를 바꾸지 않는다(중지하면 가능)
    leave(activeId);
    setActiveId(null);
  }, [activeId, busyId, leave]);

  const fetchConv = useCallback((id: string) => {
    setLoadingId(id);
    apiGetC<ServerDetail>(`/assist/conversations/${encodeURIComponent(id)}`)
      .then((d) =>
        setConvs((prev) =>
          prev.map((c) => (c.id === id ? { ...c, title: d.title || c.title, messages: fromServerMessages(d.messages ?? []), loaded: true, messageCount: d.messageCount, hasSummary: d.hasSummary } : c)),
        ),
      )
      .catch((e) => {
        if (e instanceof ApiError && e.status === 404) {
          setConvs((prev) => prev.filter((c) => c.id !== id)); // 지워졌거나 내 대화가 아님
          setActiveId((cur) => (cur === id ? null : cur));
        }
      })
      .finally(() => setLoadingId((cur) => (cur === id ? null : cur)));
  }, []);

  const open = useCallback(
    (id: string) => {
      if (busyId || id === activeId) return;
      leave(activeId);
      setActiveId(id);
      const c = convs.find((x) => x.id === id);
      if (c?.remote && !c.loaded) fetchConv(id);
    },
    [activeId, busyId, convs, fetchConv, leave],
  );

  const remove = useCallback(
    (id: string) => {
      if (busyId && active?.id === id) abortRef.current?.abort();
      dirty.current.delete(id);
      setConvs((prev) => prev.filter((c) => c.id !== id));
      setActiveId((cur) => (cur === id ? null : cur));
      apiDelete(`/assist/conversations/${encodeURIComponent(id)}`).catch(() => undefined); // 아직 저장 전이면 404
    },
    [active, busyId],
  );

  const clearAll = useCallback(() => {
    abortRef.current?.abort();
    dirty.current.clear();
    setConvs([]);
    setActiveId(null);
    apiDelete("/assist/conversations").catch(() => undefined);
  }, []);

  const setFeedback = useCallback((convId: string, botId: string, helpful: boolean) => patchBot(convId, botId, { feedback: helpful }), [patchBot]);

  // 창을 닫거나 다른 사이트로 갈 때 — 진행 중인 요청을 끊고, 새 턴이 있던 대화는 전체 요약을 남긴다
  useEffect(() => {
    const set = dirty.current;
    const onHide = () => {
      set.forEach((id) => closeRemote(id));
      set.clear();
    };
    window.addEventListener("pagehide", onHide);
    return () => {
      window.removeEventListener("pagehide", onHide);
      onHide();
      abortRef.current?.abort();
    };
  }, []);

  return { convs, active, activeId, busyId, loadingId, load, send, stop, regenerate, newChat, open, remove, clearAll, setFeedback };
}
