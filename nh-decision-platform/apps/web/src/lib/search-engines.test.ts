import { describe, expect, it } from "vitest";
import { engineLabel, threeWayCards } from "./search-engines";

describe("engineLabel — 답변의 검색 엔진 한 줄", () => {
  it("분석 결과 · 문서가 같은 엔진이면 한 번만, 그래프를 덧붙인다", () => {
    expect(engineLabel({ analysis: "es", documents: "es", graph: "neo4j" })).toBe("Elasticsearch · 그래프 Neo4j");
    expect(engineLabel({ analysis: "pg", documents: "pg", graph: "postgres" })).toBe("PostgreSQL · 그래프 PostgreSQL(개념 태그)");
  });
  it("엔진이 갈리면 저장소별로 밝힌다", () => {
    expect(engineLabel({ analysis: "es", documents: "pg", graph: null })).toBe("분석 결과 Elasticsearch · 문서 PostgreSQL");
  });
  it("분석 결과 범위가 없는 사용자는 문서 엔진만", () => {
    expect(engineLabel({ analysis: null, documents: "es" })).toBe("Elasticsearch");
  });
  it("이전 서버(engines 없음)는 backend 로", () => {
    expect(engineLabel(undefined, "es")).toBe("Elasticsearch");
    expect(engineLabel(undefined, "pg")).toBeNull();
  });
});

describe("threeWayCards — 관리자 3-way 구성 카드", () => {
  const graphOk = { ok: true, nodes: 10, relationships: 20 };
  it("ES 가 연결되고 두 색인을 쓰면 '사용 중'", () => {
    const cards = threeWayCards(
      {
        setting: "auto",
        configured: true,
        engines: { analysis: "es", documents: "es", graph: "neo4j" },
        es: { up: true, es_docs: 5, pg_chunks: 5, state: { analyzer: "nori", dictionary: 12, synced_at: "t" }, documents: { es_docs: 3, pg_chunks: 3, state: { synced_at: "t" } } },
      },
      graphOk,
      { chunks: 5, documentChunks: 3 },
    );
    expect(cards.map((c) => c.key)).toEqual(["pg", "es", "neo4j"]);
    expect(cards[1].value).toBe("사용 중");
    expect(cards[1].tone).toBe("success");
    expect(cards[1].hint).toContain("문서 3/3");
    expect(cards[1].hint).toContain("사용자 사전 12낱말");
  });
  it("ES_URL 이 없으면 축소 동작을 밝힌다", () => {
    const [, es, neo] = threeWayCards({ setting: "auto", configured: false }, { ok: false }, { chunks: 1 });
    expect(es.value).toBe("미구성");
    expect(es.tone).toBe("attention");
    expect(neo.value).toBe("연결 안 됨");
  });
  it("검색 설정 pg 면 ES 는 쓰지 않음(경고 아님)", () => {
    expect(threeWayCards({ setting: "pg", configured: true, es: { up: true } }, graphOk, { chunks: 1 })[1]).toMatchObject({ value: "쓰지 않음", tone: "default" });
  });
  it("문서 색인이 동기화 전이면 '일부 사용'", () => {
    const es = threeWayCards(
      { setting: "auto", configured: true, engines: { analysis: "es", documents: "pg" }, es: { up: true, es_docs: 1, pg_chunks: 1, state: { analyzer: "nori", synced_at: "t" }, documents: { state: {} } } },
      graphOk,
      { chunks: 1 },
    )[1];
    expect(es.value).toBe("일부 사용");
    expect(es.hint).toContain("(동기화 전)");
  });
});
