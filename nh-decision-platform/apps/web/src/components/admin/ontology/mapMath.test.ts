import { describe, expect, it } from "vitest";
import { byLabel, colorOf, DEFAULT_VIEW, kindLabel, neighbors, pick, project, radiusOf, relKo, rotate, search, type MapNode } from "./mapMath";

/* Phase G — 온톨로지 구성 지도: 회전 · 원근 투영 · 고르기 · 이웃 · 찾기 */
const node = (name: string, key: string, deg: number): MapNode => ({ id: `X:${key}`, cls: "X", key, name, deg, c: 0, p3: [0, 0, 0], p2: [0, 0], src: "", props: {} });

describe("투영", () => {
  it("회전은 길이를 지키고, 0 회전은 그대로", () => {
    const p = [0.3, -0.4, 0.5];
    expect(rotate(p, 0, 0)).toEqual([0.3, -0.4, 0.5]);
    const r = rotate(p, 1.1, -0.7);
    expect(Math.hypot(...r)).toBeCloseTo(Math.hypot(...p), 10);
    const [x, , z] = rotate([1, 0, 0], Math.PI / 2, 0);
    expect(x).toBeCloseTo(0, 10);
    expect(z).toBeCloseTo(-1, 10);
  });
  it("가운데 점은 화면 가운데, 가까운 점(깊이 음수)일수록 크게", () => {
    const v = { ...DEFAULT_VIEW, yaw: 0, pitch: 0, center: [0, 0, 0] as [number, number, number] };
    const c = project([0, 0, 0], v, 800, 600);
    expect(c.x).toBeCloseTo(400);
    expect(c.y).toBeCloseTo(300);
    expect(c.f).toBeCloseTo(1);
    const near = project([0, 0, -1], v, 800, 600);
    const far = project([0, 0, 1], v, 800, 600);
    expect(near.f).toBeGreaterThan(1);
    expect(far.f).toBeLessThan(1);
    expect(radiusOf(10, near.f, 1)).toBeGreaterThan(radiusOf(10, far.f, 1));
    // y 는 위가 + (화면은 아래가 +)
    expect(project([0, 0.5, 0], v, 800, 600).y).toBeLessThan(300);
  });
  it("2D 는 회전 · 원근 없이 이동 · 확대만", () => {
    const v = { ...DEFAULT_VIEW, yaw: 1, pitch: 1, zoom: 2, panX: 10, panY: -5, center: [0, 0, 0] as [number, number, number] };
    const p = project([0.5, 0, 0.9], v, 1000, 1000, true);
    expect(p.f).toBe(1);
    expect(p.x).toBeCloseTo(500 + 0.5 * 1000 * 0.42 * 2 + 10);
    expect(p.y).toBeCloseTo(495);
  });
});

describe("고르기 · 이웃 · 찾기", () => {
  it("반지름 안에서 가장 가까운 보이는 점", () => {
    const xs = Float32Array.from([10, 50, 52]);
    const ys = Float32Array.from([10, 50, 50]);
    const rs = Float32Array.from([3, 3, 3]);
    expect(pick(xs, ys, rs, Uint8Array.from([1, 1, 1]), 51.6, 50)).toBe(2);
    expect(pick(xs, ys, rs, Uint8Array.from([1, 1, 0]), 51.6, 50)).toBe(1); // 숨긴 점은 고르지 않음
    expect(pick(xs, ys, rs, Uint8Array.from([1, 1, 1]), 200, 200)).toBe(-1);
  });
  it("이웃은 방향 · 관계 유형과 함께, 범위 밖 간선은 무시", () => {
    const nb = neighbors(3, [[0, 1, 0], [2, 0, 1], [0, 9, 0]], ["IN_GROUP", "MENTIONS"]);
    expect(nb[0]).toEqual([{ index: 1, type: "IN_GROUP", dir: "out" }, { index: 2, type: "MENTIONS", dir: "in" }]);
    expect(nb[1]).toEqual([{ index: 0, type: "IN_GROUP", dir: "in" }]);
  });
  it("앞부분 일치 먼저, 그다음 연결 수 · 빈 질의는 없음", () => {
    const nodes = [node("새희망홀씨대출", "N1", 3), node("햇살론", "SUNSHINE", 2), node("근로자햇살론", "N3", 9)];
    expect(search(nodes, "햇살")).toEqual([1, 2]);
    expect(search(nodes, "sun")).toEqual([1]);
    expect(search(nodes, "  ")).toEqual([]);
  });
  it("표기 · 색", () => {
    expect(relKo("IN_GROUP")).toBe("상품군 소속");
    expect(relKo("UNKNOWN_X")).toBe("UNKNOWN_X");
    expect(kindLabel("document")).toBe("문서 추출");
    expect(byLabel("llm")).toBe("LLM 추출");
    expect(colorOf(16)).toBe(colorOf(0));
    expect(colorOf(-1)).toBe(colorOf(15));
  });
});
