/**
 * 3-way 검색 구성(설계 §24) 표시 — PostgreSQL(원장) · Elasticsearch(키워드 · 의미) · Neo4j(그래프).
 * AI 어시스턴트 답의 '어디서 찾았는지' 한 줄과 관리자 [AI 어시스턴트 색인]의 구성 카드가 같은 규칙을 쓴다.
 */

export type StoreEngine = "es" | "pg";
export type GraphEngine = "neo4j" | "postgres";

/** 답변 한 건의 검색 엔진(서버 retrieval.engines) — 분석 결과 범위가 없는 사용자는 analysis = null */
export interface RetrievalEngines {
  analysis?: StoreEngine | null;
  documents?: StoreEngine | null;
  graph?: GraphEngine | null;
}

const STORE: Record<StoreEngine, string> = { es: "Elasticsearch", pg: "PostgreSQL" };

/** 답변 아래 한 줄 — 예: "Elasticsearch · 그래프 Neo4j", "분석 결과 Elasticsearch · 문서 PostgreSQL". engines 가 없으면(이전 서버) backend 로 */
export function engineLabel(engines: RetrievalEngines | null | undefined, backend?: StoreEngine): string | null {
  if (!engines) return backend === "es" ? STORE.es : null;
  const parts: string[] = [];
  const a = engines.analysis ?? null;
  const d = engines.documents ?? null;
  if (a && d && a !== d) parts.push(`분석 결과 ${STORE[a]} · 문서 ${STORE[d]}`);
  else if (a || d) parts.push(STORE[(a ?? d) as StoreEngine]);
  if (engines.graph === "neo4j") parts.push("그래프 Neo4j");
  else if (engines.graph === "postgres") parts.push("그래프 PostgreSQL(개념 태그)");
  return parts.length ? parts.join(" · ") : null;
}

interface IndexPart {
  es_docs?: number | null;
  pg_chunks?: number;
  lag?: number | null;
  state?: { analyzer?: string | null; dictionary?: number | null; synced_at?: string | null } | null;
}

/** 관리자 상태의 searchBackend (GET /admin/knowledge/status) */
export interface SearchBackendStatus {
  setting: string;
  configured: boolean;
  engines?: { analysis?: StoreEngine; documents?: StoreEngine; graph?: GraphEngine };
  es?: IndexPart & { up: boolean; error?: string; documents?: IndexPart };
}

export interface EngineCard {
  key: "pg" | "es" | "neo4j";
  label: string;
  role: string;
  value: string;
  hint: string;
  tone: "success" | "attention" | "default";
}

function idx(name: string, p: IndexPart | undefined): string {
  if (!p) return `${name} -`;
  const synced = p.state?.synced_at ? "" : " (동기화 전)";
  return `${name} ${p.es_docs ?? 0}/${p.pg_chunks ?? 0}${synced}`;
}

/** 3-way 구성 카드 세 장 — 각 저장소가 맡은 일 · 지금 상태 · 축소 동작 여부 */
export function threeWayCards(
  sb: SearchBackendStatus | undefined,
  graph: { ok: boolean; nodes?: number; relationships?: number },
  totals: { chunks: number; documentChunks?: number },
): EngineCard[] {
  const es = sb?.es;
  const mode = sb?.setting ?? "auto";
  const using = sb?.engines;
  const pgOnly = mode === "pg";
  const pg: EngineCard = {
    key: "pg",
    label: "PostgreSQL",
    role: "원장 · 권한 판정 · 임베딩 값",
    value: "원장",
    hint: `분석 결과 조각 ${totals.chunks.toLocaleString("ko-KR")}개${totals.documentChunks != null ? ` · 문서 조각 ${totals.documentChunks.toLocaleString("ko-KR")}개` : ""} · ES 결과도 여기서 권한을 다시 확인`,
    tone: "success",
  };
  let esCard: EngineCard;
  if (pgOnly) {
    esCard = { key: "es", label: "Elasticsearch", role: "키워드(nori) · 의미(kNN)", value: "쓰지 않음", hint: "검색 설정 pg — 키워드 · 의미 검색을 PostgreSQL 로", tone: "default" };
  } else if (!sb?.configured) {
    esCard = { key: "es", label: "Elasticsearch", role: "키워드(nori) · 의미(kNN)", value: "미구성", hint: "ES_URL 없음 — PostgreSQL 로 축소 동작 중(3-way 표준 구성 아님)", tone: "attention" };
  } else if (!es?.up) {
    esCard = { key: "es", label: "Elasticsearch", role: "키워드(nori) · 의미(kNN)", value: "연결 안 됨", hint: `PostgreSQL 로 폴백 중${es?.error ? ` — ${es.error}` : ""}`, tone: "attention" };
  } else {
    const both = using?.analysis === "es" && using?.documents === "es";
    const analyzer = es.state?.analyzer ?? "-";
    const dict = es.state?.dictionary ?? 0;
    esCard = {
      key: "es",
      label: "Elasticsearch",
      role: "키워드(nori) · 의미(kNN)",
      value: both ? "사용 중" : "일부 사용",
      hint: `${idx("분석 결과", es)} · ${idx("문서", es.documents)} · 분석기 ${analyzer} · 사용자 사전 ${dict}낱말${both ? "" : " — 동기화 전인 색인은 PostgreSQL 로"}`,
      tone: both && analyzer === "nori" ? "success" : "attention",
    };
  }
  const neo: EngineCard = graph.ok
    ? { key: "neo4j", label: "Neo4j", role: "개념 그래프(확장 · 문서 ↔ 개념)", value: "연결됨", hint: `노드 ${graph.nodes ?? 0} · 관계 ${graph.relationships ?? 0}`, tone: "success" }
    : { key: "neo4j", label: "Neo4j", role: "개념 그래프(확장 · 문서 ↔ 개념)", value: "연결 안 됨", hint: "개념 확장은 PostgreSQL 개념 태그 · 데이터셋 매핑 간선으로 계속 동작", tone: "attention" };
  return [pg, esCard, neo];
}
