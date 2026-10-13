import { describe, expect, it } from "vitest";
import { historyFor, loadConversations, numberCites, resolveCite, saveConversations, slimForStorage, storageKey, titleOf, type AssistAnswer, type AssistMeta, type BotMsg, type Conversation, type Msg } from "./assist-chat";
import { parseSse } from "./assist-stream";

const meta: AssistMeta = {
  question: "q",
  concepts: [],
  metrics: [{ code: "share_now", label: "충당금 비중", display: "9.16", unit: "%", previous: null, formula: "f", calcRunId: "abcdef123456" }],
  analysis: [
    { kind: "analysis", type: "분석", collection: "analysis.risk", collectionLabel: "신용리스크", owned: true, title: "포용금융 충당금", artifactTitle: "포용금융 확대 관련 분석", text: "t", sourceKey: "insights", href: "/risk/analysis", score: 1, no: 1 },
  ],
  evidence: [{ origin: "ext", title: "포용적 금융 확대방안", docClass: "gov_policy", page: 3, text: "t", no: 2 }],
  collections: [],
  retrieval: { channels: {}, semantic: false, graph: false, expanded: [], rewritten: null, rewriteBy: null },
};

describe("SSE 파서", () => {
  it("완성된 이벤트만 꺼내고 남은 조각은 돌려준다", () => {
    const a = parseSse('event: stage\ndata: {"stage":"scope"}\n\nevent: delta\ndata: {"text":"안');
    expect(a.events).toEqual([{ event: "stage", data: { stage: "scope" } }]);
    expect(a.rest).toBe('event: delta\ndata: {"text":"안');
    const b = parseSse(a.rest + '녕"}\n\n');
    expect(b.events).toEqual([{ event: "delta", data: { text: "안녕" } }]);
    expect(b.rest).toBe("");
  });
  it("주석 · CRLF · 깨진 JSON 은 건너뛴다", () => {
    const r = parseSse(': 연결됨\n\nevent: done\r\ndata: {"a":1}\r\n\r\nevent: x\ndata: {깨짐\n\nevent: y\ndata: {"ok":true}\n\n');
    expect(r.events.map((e) => e.event)).toEqual(["done", "y"]);
  });
  it("여러 줄 data 는 이어 붙인다", () => {
    expect(parseSse('event: e\ndata: {"a":\ndata: 1}\n\n').events[0].data).toEqual({ a: 1 });
  });
});

describe("대화", () => {
  const u = (t: string): Msg => ({ id: t, role: "user", text: t, at: 1 });
  const b = (t: string, status: BotMsg["status"] = "done"): Msg => ({ id: `b${t}`, role: "assistant", text: t, at: 1, status, question: "q" });

  it("제목은 질문 앞 30자", () => {
    expect(titleOf("  포용금융   충당금 비중은 얼마인가요?  ")).toBe("포용금융 충당금 비중은 얼마인가요?");
    expect(titleOf("가".repeat(40))).toBe(`${"가".repeat(30)}…`);
    expect(titleOf("   ")).toBe("새 대화");
  });

  it("서버로 보내는 이력은 끝난 질문·답 쌍의 최근 3개", () => {
    const msgs = [u("1"), b("a1"), u("2"), b("a2"), u("3"), b("a3"), u("4"), b("a4"), u("5"), b("", "error"), u("6"), b("부분", "stopped")];
    expect(historyFor(msgs)).toEqual([
      { q: "2", a: "a2" },
      { q: "3", a: "a3" },
      { q: "4", a: "a4" },
    ]);
    expect(historyFor([u("x".repeat(400)), b("y".repeat(500))])[0]).toEqual({ q: "x".repeat(300), a: "y".repeat(400) });
  });

  it("저장할 때 진행 중인 답은 중지로, 도구 결과는 뺀다", () => {
    const final = { ...meta, mode: "llm", answer: "a", verification: { passed: true, unverified: [] }, toolResults: [{ tool: "t", result: {} }] } as AssistAnswer;
    const conv: Conversation = { id: "c", title: "t", updatedAt: 1, messages: [u("q"), { ...(b("a", "streaming") as BotMsg), stage: "search", final }] };
    const [s] = slimForStorage([conv]);
    const bot = s.messages[1] as BotMsg;
    expect(bot.status).toBe("stopped");
    expect(bot.stage).toBeUndefined();
    expect(bot.final?.toolResults).toBeUndefined();
    expect(bot.final?.answer).toBe("a");
  });

  it("저장소: 내 기록만 읽고 다른 사용자의 기록은 지운다", () => {
    const mem = new Map<string, string>();
    const store = {
      get length() {
        return mem.size;
      },
      key: (i: number) => [...mem.keys()][i] ?? null,
      getItem: (k: string) => mem.get(k) ?? null,
      setItem: (k: string, v: string) => void mem.set(k, v),
      removeItem: (k: string) => void mem.delete(k),
    };
    const conv: Conversation = { id: "c1", title: "t", updatedAt: 1, messages: [u("q"), b("a")] };
    saveConversations(store, "20250001", [conv]);
    saveConversations(store, "20250002", [{ ...conv, id: "c2" }]);
    mem.set("다른키", "유지");
    expect(loadConversations(store, "20250001").map((c) => c.id)).toEqual(["c1"]);
    expect(mem.has(storageKey("20250002"))).toBe(false); // 다른 사용자의 기록은 지워진다
    expect(mem.get("다른키")).toBe("유지");
    saveConversations(store, "20250001", []);
    expect(mem.has(storageKey("20250001"))).toBe(false); // 빈 목록은 키도 지운다
    mem.set(storageKey("20250001"), "{깨짐");
    expect(loadConversations(store, "20250001")).toEqual([]);
  });
});

describe("인용", () => {
  it("분석 · 문서 · 지표 · 번호를 출처에 연결한다", () => {
    expect(resolveCite("analysis", "포용금융 확대 관련 분석", meta)).toMatchObject({ sourceNo: 1, href: "/risk/analysis" });
    expect(resolveCite("analysis", "포용금융 충당금", meta)).toMatchObject({ sourceNo: 1 });
    expect(resolveCite("analysis", "포용금융 확대", meta)).toMatchObject({ sourceNo: 1 }); // 줄여 쓴 제목
    expect(resolveCite("doc", "포용적 금융 확대방안", meta)).toMatchObject({ sourceNo: 2, label: "포용적 금융 확대방안 p.3" });
    expect(resolveCite("metric", "share_now", meta)).toMatchObject({ metricCode: "share_now", label: "충당금 비중 9.16%" });
    expect(resolveCite("num", "2", meta)).toMatchObject({ kind: "doc", sourceNo: 2 });
  });
  it("찾지 못하면 null — 없는 번호를 꾸며내지 않는다", () => {
    expect(resolveCite("analysis", "전혀 다른 제목", meta)).toBeNull();
    expect(resolveCite("doc", "x", meta)).toBeNull();
    expect(resolveCite("num", "9", meta)).toBeNull();
    expect(resolveCite("metric", "없는지표", meta)).toBeNull();
    expect(resolveCite("analysis", "포용", meta)).toBeNull(); // 너무 짧은 부분 일치는 연결하지 않는다
    expect(resolveCite("analysis", "x", undefined)).toBeNull();
  });
  it("같은 출처를 다른 표기로 인용해도 한 번호", () => {
    const m = numberCites(
      [
        { kind: "analysis", ref: "포용금융 확대 관련 분석" },
        { kind: "metric", ref: "share_now" },
        { kind: "num", ref: "1" },
        { kind: "doc", ref: "포용적 금융 확대방안" },
        { kind: "analysis", ref: "없는 출처" },
      ],
      meta,
    );
    expect(m.get("analysis:포용금융 확대 관련 분석")?.n).toBe(1);
    expect(m.get("metric:share_now")?.n).toBe(2);
    expect(m.get("num:1")?.n).toBe(1);
    expect(m.get("doc:포용적 금융 확대방안")?.n).toBe(3);
    expect(m.has("analysis:없는 출처")).toBe(false);
  });
});
