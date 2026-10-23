/**
 * 질문하기 스트리밍 클라이언트 — POST /assist/stream (SSE) 를 fetch 로 읽는다(EventSource 는 GET 만 되므로).
 * 이벤트: stage(진행 단계) · meta(출처 · 수치 · 검색 상태 — 글자보다 먼저) · delta(답변 글자) · reset(지금까지 글자 비움) · done(최종 응답) · error.
 * 스트림을 지원하지 않는 환경(본문 스트림 없음 · 404)이면 `/assist` 한 번 호출로 대신한다.
 */
import { api, ApiError } from "@/lib/api-client";

export interface SseEvent {
  event: string;
  data: unknown;
}

/** 버퍼에서 완성된 이벤트를 꺼낸다 — 남은 조각(아직 끝나지 않은 이벤트)은 rest 로 돌려준다. 주석(`:`)과 알 수 없는 줄은 무시. */
export function parseSse(buffer: string): { events: SseEvent[]; rest: string } {
  const norm = buffer.replace(/\r\n/g, "\n");
  const parts = norm.split("\n\n");
  const rest = parts.pop() ?? "";
  const events: SseEvent[] = [];
  for (const block of parts) {
    let event = "message";
    const data: string[] = [];
    for (const line of block.split("\n")) {
      if (line.startsWith(":")) continue;
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""));
    }
    if (!data.length) continue;
    try {
      events.push({ event, data: JSON.parse(data.join("\n")) });
    } catch {
      /* 깨진 이벤트는 건너뛴다 */
    }
  }
  return { events, rest };
}

export interface StreamHandlers {
  onEvent: (e: SseEvent) => void;
}

export interface AskBody {
  question: string;
  screen?: string;
  /** 서버에 저장되는 대화 id — 서버가 그 대화의 누적 요약 + 원문으로 멀티턴 맥락을 만든다 */
  conversationId?: string;
  /** 다시 생성 — 마지막 턴의 답을 바꾼다 */
  replaceLast?: boolean;
  /** 대화 id 를 모르는 예전 서버용 최근 대화 */
  history: { q: string; a: string }[];
}

/** 스트림으로 질문한다. signal 로 중지(AbortError). 반환: 스트림을 썼으면 true, `/assist` 로 대신했으면 false */
export async function streamAsk(body: AskBody, handlers: StreamHandlers, signal: AbortSignal): Promise<boolean> {
  let res: Response;
  try {
    res = await fetch("/backend/assist/stream", {
      method: "POST",
      credentials: "same-origin",
      cache: "no-store",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify(body),
      signal,
    });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new ApiError(0, "서버에 연결하지 못했습니다. 네트워크를 확인하고 다시 시도해 주세요.");
  }
  if (res.status === 401 && typeof window !== "undefined") {
    // 세션 만료 — api() 와 같이 전체 새로고침으로 로그인 화면 이동
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.href = `/login?next=${encodeURIComponent(window.location.pathname)}`;
    throw new ApiError(401, "세션이 만료되었습니다");
  }
  if (res.status === 404 || res.status === 405 || !res.body) {
    // 스트림을 모르는 서버 — 한 번에 받는 호출로 대신
    const full = await api<Record<string, unknown>>("/assist", { method: "POST", json: body, signal });
    handlers.onEvent({ event: "meta", data: { ...full, answer: undefined } });
    handlers.onEvent({ event: "done", data: full });
    return false;
  }
  if (!res.ok) {
    let msg = `요청 실패 (${res.status})`;
    try {
      const j = await res.json();
      const d = (j as { detail?: unknown }).detail;
      if (typeof d === "string") msg = d;
    } catch {
      /* 본문이 JSON 이 아니면 기본 문구 */
    }
    throw new ApiError(res.status, msg);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const { events, rest } = parseSse(buf);
      buf = rest;
      for (const e of events) handlers.onEvent(e);
    }
    buf += decoder.decode();
    if (buf.trim()) for (const e of parseSse(buf + "\n\n").events) handlers.onEvent(e);
  } finally {
    reader.releaseLock?.();
  }
  return true;
}
