/**
 * 온톨로지 구성 지도 — 형식 · 투영 수학 · 색 (Phase G · 설계 §23.5). 화면 없이 시험한다(lib 처럼 순수 함수).
 */

export interface MapClass {
  label: string;
  ko: string;
  count: number;
  total: number;
  description: string;
  color: number;
}
export interface MapCluster {
  id: number;
  label: string;
  size: number;
  classes: Record<string, number>;
  main: string;
  center3: number[] | null;
  center2: number[] | null;
  small: boolean;
}
export interface MapNode {
  id: string;
  cls: string;
  key: string;
  name: string;
  deg: number;
  c: number;
  p3: [number, number, number];
  p2: [number, number];
  src: string;
  kind?: string | null;
  by?: string | null;
  origin?: string | null;
  props: Record<string, unknown>;
  evidence?: string;
  evidencePage?: number | null;
  evidenceDoc?: string | null;
}
export interface OntologyMapData {
  classes: MapClass[];
  relTypes: string[];
  relations: { type: string; count: number }[];
  schema: { from: string; type: string; to: string; count: number }[];
  clusters: MapCluster[];
  nodes: MapNode[];
  links: [number, number, number][];
  truncated: boolean;
  total: { nodes: number; links: number };
  neo4j?: { ok: boolean; nodes?: number; relationships?: number; error?: string };
  generatedAt?: string;
  elapsedMs?: number;
  cached?: boolean;
  schemaVersion?: number | null;
  empty?: string;
}

/** 어두운 바탕에서 서로 구분되는 16색 (색만으로 구분하지 않도록 범례 · 상세에 이름을 함께 쓴다) */
export const CLASS_COLORS = [
  "#60a5fa", "#f87171", "#4ade80", "#fbbf24", "#a78bfa", "#22d3ee", "#f472b6", "#a3e635",
  "#fb923c", "#818cf8", "#2dd4bf", "#fca5a5", "#c084fc", "#facc15", "#94a3b8", "#f9a8d4",
];
export const colorOf = (i: number) => CLASS_COLORS[((i % CLASS_COLORS.length) + CLASS_COLORS.length) % CLASS_COLORS.length];

function hexRgb(hex: string): [number, number, number] | null {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) return null;
  const v = parseInt(m[1], 16);
  return [(v >> 16) & 255, (v >> 8) & 255, v & 255];
}

/** '#rrggbb' → 'rgba(r, g, b, a)' (형식이 다르면 그대로) */
export function rgba(hex: string, a: number): string {
  const c = hexRgb(hex);
  return c ? `rgba(${c[0]}, ${c[1]}, ${c[2]}, ${a})` : hex;
}

/** 두 색을 t(0~1) 만큼 섞은 '#rrggbb' */
export function mixHex(a: string, b: string, t: number): string {
  const x = hexRgb(a);
  const y = hexRgb(b);
  if (!x || !y) return a;
  const k = Math.min(1, Math.max(0, t));
  return `#${x.map((v, i) => Math.round(v + (y[i] - v) * k).toString(16).padStart(2, "0")).join("")}`;
}

/** 배경 별 — 단위 구 위의 방향 · 밝기 · 크기 (고정 시드라 매번 같은 하늘) */
export function starfield(count: number, seed = 7): { d: [number, number, number]; b: number; s: number }[] {
  let x = seed >>> 0 || 1;
  const rnd = () => {
    x = (Math.imul(x, 1664525) + 1013904223) >>> 0;
    return x / 4294967296;
  };
  return Array.from({ length: count }, () => {
    const z = rnd() * 2 - 1;
    const t = rnd() * Math.PI * 2;
    const r = Math.sqrt(1 - z * z);
    const b = rnd();
    return { d: [r * Math.cos(t), r * Math.sin(t), z] as [number, number, number], b: 0.25 + 0.75 * b * b, s: b > 0.92 ? 1.6 : 1 };
  });
}

/** 군집 이름에서 앞의 주 클래스 이름('지표 · ')을 뗀 대표 개체 부분 — 클래스는 색 · 구성 막대로 따로 보여 준다 */
export function clusterTitle(label: string, mainKo?: string): string {
  const pre = mainKo ? `${mainKo} · ` : "";
  return pre && label.startsWith(pre) && label.length > pre.length ? label.slice(pre.length) : label;
}

/** 관계 유형 업무 이름 — 스키마 유형은 영문 식별자라 보조로 */
export const REL_KO: Record<string, string> = {
  HAS_VERSION: "버전", FEEDS: "지표 입력", DERIVED_FROM: "지표 파생", USES: "사용", PRODUCES: "산출",
  READS_CLASS: "문서 분류 읽음", DESCRIBES: "설명", IN_CLASS: "분류", ISSUED_BY: "발행", MENTIONS: "언급",
  STATES_STANCE: "기조 표명", SETS_CONSTRAINT: "제약 설정", IN_GROUP: "상품군 소속", PART_OF_THEME: "정책 주제 소속",
  APPLIES_TO: "적용 대상", MEASURES: "측정", BELONGS_TO: "소속",
};
export const relKo = (t: string) => REL_KO[t] ?? t;

export interface View {
  yaw: number;
  pitch: number;
  zoom: number;
  panX: number;
  panY: number;
  center: [number, number, number];
}
export const DEFAULT_VIEW: View = { yaw: 0.6, pitch: -0.35, zoom: 1, panX: 0, panY: 0, center: [0, 0, 0] };
export const CAMERA = 3;

/** 회전(좌우 yaw → 상하 pitch) 후 좌표 */
export function rotate(p: readonly number[], yaw: number, pitch: number): [number, number, number] {
  const [x, y, z] = [p[0] ?? 0, p[1] ?? 0, p[2] ?? 0];
  const cy = Math.cos(yaw);
  const sy = Math.sin(yaw);
  const x1 = x * cy + z * sy;
  const z1 = -x * sy + z * cy;
  const cp = Math.cos(pitch);
  const sp = Math.sin(pitch);
  return [x1, y * cp - z1 * sp, y * sp + z1 * cp];
}

/** 화면 좌표 · 원근 비율 · 깊이 (깊이가 클수록 멀다) */
export function project(p: readonly number[], view: View, width: number, height: number, flat = false): { x: number; y: number; f: number; z: number } {
  const q = [(p[0] ?? 0) - view.center[0], (p[1] ?? 0) - view.center[1], flat ? 0 : (p[2] ?? 0) - view.center[2]];
  const [x, y, z] = flat ? [q[0], q[1], 0] : rotate(q, view.yaw, view.pitch);
  const f = flat ? 1 : CAMERA / Math.max(0.3, CAMERA + z);
  const s = Math.min(width, height) * 0.42 * view.zoom;
  return { x: width / 2 + x * f * s + view.panX, y: height / 2 - y * f * s + view.panY, f, z };
}

/** 점 반지름(px) — 연결 수가 많을수록 크게, 멀수록 작게 */
export function radiusOf(deg: number, f: number, zoom: number): number {
  return (2.2 + 1.5 * Math.log2(1 + Math.max(0, deg))) * f * Math.sqrt(Math.max(0.3, zoom));
}

/** 화면 좌표에서 가장 가까운 점(반지름 + 여유 안) — 없으면 -1 */
export function pick(xs: Float32Array, ys: Float32Array, rs: Float32Array, visible: Uint8Array, x: number, y: number, slack = 4): number {
  let best = -1;
  let bestD = Infinity;
  for (let i = 0; i < xs.length; i++) {
    if (!visible[i]) continue;
    const dx = xs[i] - x;
    const dy = ys[i] - y;
    const d = dx * dx + dy * dy;
    const r = rs[i] + slack;
    if (d <= r * r && d < bestD) {
      best = i;
      bestD = d;
    }
  }
  return best;
}

export interface Neighbor {
  index: number;
  type: string;
  dir: "out" | "in";
}

/** 노드별 이웃(관계 유형 · 방향) */
export function neighbors(n: number, links: readonly (readonly [number, number, number])[], relTypes: readonly string[]): Neighbor[][] {
  const out: Neighbor[][] = Array.from({ length: n }, () => []);
  for (const [a, b, t] of links) {
    if (a < n && b < n) {
      out[a].push({ index: b, type: relTypes[t] ?? String(t), dir: "out" });
      out[b].push({ index: a, type: relTypes[t] ?? String(t), dir: "in" });
    }
  }
  return out;
}

/** 이름 · 키 찾기 — 앞부분 일치를 먼저, 그다음 연결 수 */
export function search(nodes: readonly MapNode[], q: string, limit = 8): number[] {
  const s = q.trim().toLowerCase();
  if (!s) return [];
  const hits: [number, number][] = [];
  nodes.forEach((n, i) => {
    const name = n.name.toLowerCase();
    const key = n.key.toLowerCase();
    if (name.includes(s) || key.includes(s)) hits.push([i, (name.startsWith(s) || key.startsWith(s) ? 1000 : 0) + n.deg]);
  });
  return hits.sort((a, b) => b[1] - a[1] || a[0] - b[0]).slice(0, limit).map((h) => h[0]);
}

/** 원장 출처 표기 */
export function kindLabel(kind?: string | null): string {
  return ({ dataset: "데이터셋", document: "문서 추출", metric: "지표 정의", workflow: "워크플로 정의", artifact: "화면 산출물", master: "기준 정보" } as Record<string, string>)[kind ?? ""] ?? (kind || "-");
}
export function byLabel(by?: string | null): string {
  return by === "llm" ? "LLM 추출" : by === "rule" ? "규칙(결정론)" : by || "-";
}
