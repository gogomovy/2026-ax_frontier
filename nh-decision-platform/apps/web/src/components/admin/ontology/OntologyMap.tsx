"use client";

import clsx from "clsx";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { KeyValueList } from "@/components/ui/Layout";
import { Badge, Button } from "@/components/ui/primitives";
import { byLabel, CAMERA, clusterTitle, colorOf, DEFAULT_VIEW, kindLabel, mixHex, neighbors as buildNeighbors, pick, project, radiusOf, relKo, rgba, rotate, search, starfield, type OntologyMapData, type View } from "./mapMath";

/*
 * 온톨로지 3D 군집 지도 (Phase G · 요구사항 §23 OV-02 · OV-03 · 설계 §23.5)
 * 캔버스에 직접 그린다(외부 3D 라이브러리 없음 · Q127). 점 = 개체(클래스 색 · 연결 수 크기), 선 = 관계, 군집은 서버가 모아 배치.
 * 조작: 끌기 = 회전(2D 는 이동) · 휠 / 단추 = 확대 · 방향키 = 회전 · +/− = 확대 · Esc = 선택 해제. 같은 정보는 '표' 보기와 옆 패널(목록 · 상세)에 글로 있다.
 */

type Mode = "3d" | "2d";

const BG = "#0b1220";
const BG_CENTER = "#16213d"; // 가운데가 조금 밝은 원형 그라데이션 — 깊이감
const BG_EDGE = "#04070e";
const LINK = "rgba(148, 163, 184, 0.13)";
const LINK_HL = "rgba(226, 232, 240, 0.62)";
const MAX_NEIGHBOR_LABELS = 24;
const FONT = "Pretendard, 'Noto Sans KR', system-ui, sans-serif";

/* 우주 격자 — 개체가 놓인 공간(좌표 ±1)을 감싸는 정육면체 격자 · 바닥 격자 · 교차점, 가까울수록 밝게(원근 안개) */
const GRID = 1.15; // 격자 반폭(좌표 단위) — 개체가 놓인 ±1 을 조금 넉넉히 감싼다
const GRID_STEPS = 6; // 한 변의 칸 수
const GRID_RGB = "125, 170, 255";
const STARS = starfield(420);

/* 점 그림 — 클래스 색마다 한 번 만든 구(하이라이트 · 그늘) + 은은한 빛무리 그림을 크기만 바꿔 찍는다(프레임마다 그라데이션을 만들지 않음) */
const SPRITE = 64;
const GLOW = 2.3; // 그림 반지름 ÷ 점 반지름

function makeSprite(color: string): HTMLCanvasElement | null {
  if (typeof document === "undefined") return null;
  const c = document.createElement("canvas");
  c.width = SPRITE;
  c.height = SPRITE;
  const g = c.getContext("2d");
  if (!g) return null;
  const R = SPRITE / 2;
  const core = R / GLOW;
  const halo = g.createRadialGradient(R, R, core * 0.7, R, R, R);
  halo.addColorStop(0, rgba(color, 0.32));
  halo.addColorStop(1, rgba(color, 0));
  g.fillStyle = halo;
  g.fillRect(0, 0, SPRITE, SPRITE);
  const body = g.createRadialGradient(R - core * 0.35, R - core * 0.4, core * 0.08, R, R, core);
  body.addColorStop(0, mixHex(color, "#ffffff", 0.6));
  body.addColorStop(0.5, color);
  body.addColorStop(1, mixHex(color, "#000000", 0.38));
  g.fillStyle = body;
  g.beginPath();
  g.arc(R, R, core, 0, Math.PI * 2);
  g.fill();
  return c;
}

function roundRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  const k = Math.min(r, h / 2, w / 2);
  ctx.beginPath();
  ctx.moveTo(x + k, y);
  ctx.arcTo(x + w, y, x + w, y + h, k);
  ctx.arcTo(x + w, y + h, x, y + h, k);
  ctx.arcTo(x, y + h, x, y, k);
  ctx.arcTo(x, y, x + w, y, k);
  ctx.closePath();
}

/** 배경 · 별 · 격자 — 점 · 선보다 먼저 그린다 */
function drawSpace(ctx: CanvasRenderingContext2D, view: View, w: number, h: number, flat: boolean) {
  const bg = ctx.createRadialGradient(w / 2, h * 0.45, 0, w / 2, h / 2, Math.hypot(w, h) * 0.62);
  bg.addColorStop(0, BG_CENTER);
  bg.addColorStop(1, BG_EDGE);
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, w, h);

  // 별 — 아주 먼 하늘(회전만 따르고 확대 · 이동은 따르지 않는다)
  const F = Math.min(w, h) * 0.85;
  for (const s of STARS) {
    let sx: number;
    let sy: number;
    if (flat) {
      sx = w / 2 + s.d[0] * w * 0.55;
      sy = h / 2 + s.d[1] * h * 0.55;
    } else {
      const r = rotate(s.d, view.yaw * 0.6, view.pitch * 0.6);
      if (r[2] < 0.2) continue;
      sx = w / 2 + (r[0] / r[2]) * F;
      sy = h / 2 - (r[1] / r[2]) * F;
    }
    if (sx < 0 || sy < 0 || sx > w || sy > h) continue;
    ctx.fillStyle = `rgba(226, 232, 255, ${(s.b * 0.55).toFixed(3)})`;
    ctx.fillRect(sx, sy, s.s, s.s);
  }

  const near = (f: number) => Math.min(1, Math.max(0, (f - 0.62) / 0.75)); // 0 = 멀리 · 1 = 가까이
  const P = (p: [number, number, number]) => project(p, view, w, h, flat);
  const behind = (z: number) => CAMERA + z < 0.6; // 카메라 뒤 · 너무 가까운 점은 잇지 않는다
  const seg = (a: [number, number, number], b: [number, number, number], base: number, gain: number, parts = 6) => {
    // 긴 선은 몇 토막으로 나눠 토막마다 깊이에 맞는 밝기
    let prev = P(a);
    for (let k = 1; k <= parts; k++) {
      const t = k / parts;
      const cur = P([a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t]);
      if (!behind(prev.z) && !behind(cur.z)) {
        ctx.strokeStyle = `rgba(${GRID_RGB}, ${(base + gain * near((prev.f + cur.f) / 2)).toFixed(3)})`;
        ctx.beginPath();
        ctx.moveTo(prev.x, prev.y);
        ctx.lineTo(cur.x, cur.y);
        ctx.stroke();
      }
      prev = cur;
    }
  };
  const g = GRID;
  const step = (2 * g) / GRID_STEPS;
  ctx.lineWidth = 1;
  if (flat) {
    // 2D — 모눈종이처럼 고른 격자, 두 칸마다 조금 진하게
    for (let k = 0; k <= GRID_STEPS * 2; k++) {
      const t = -g + (step / 2) * k;
      const major = k % 4 === 0;
      seg([t, -g, 0], [t, g, 0], major ? 0.09 : 0.045, 0, 1);
      seg([-g, t, 0], [g, t, 0], major ? 0.09 : 0.045, 0, 1);
    }
    return;
  }
  // 바닥 격자 — 공간 아래에 깔린 판
  for (let k = 0; k <= GRID_STEPS; k++) {
    const t = -g + step * k;
    seg([t, -g, -g], [t, -g, g], 0.05, 0.24);
    seg([-g, -g, t], [g, -g, t], 0.05, 0.24);
  }
  // 정육면체 모서리 12개 — 공간의 테두리
  const c = [-g, g];
  for (const y of c) for (const z of c) seg([-g, y, z], [g, y, z], 0.07, 0.3);
  for (const x of c) for (const z of c) seg([x, -g, z], [x, g, z], 0.07, 0.3);
  for (const x of c) for (const y of c) seg([x, y, -g], [x, y, g], 0.07, 0.3);
  // 격자 교차점 — 공간 안의 격자감(아주 옅게)
  for (let i = 0; i <= GRID_STEPS; i++)
    for (let j = 0; j <= GRID_STEPS; j++)
      for (let k = 0; k <= GRID_STEPS; k++) {
        const p = P([-g + step * i, -g + step * j, -g + step * k]);
        if (behind(p.z) || p.x < 0 || p.y < 0 || p.x > w || p.y > h) continue;
        const a = 0.08 + 0.4 * near(p.f);
        ctx.fillStyle = `rgba(${GRID_RGB}, ${a.toFixed(3)})`;
        const sz = 0.8 + 1.1 * near(p.f);
        ctx.fillRect(p.x - sz / 2, p.y - sz / 2, sz, sz);
      }
}

function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && Boolean(window.matchMedia?.("(prefers-reduced-motion: reduce)").matches);
}

/** 데이터가 바뀌면 부모가 key 로 다시 만든다(선택 · 시점 초기화) */
export function OntologyMap({ data, mode }: { data: OntologyMapData; mode: Mode }) {
  // 움직임 줄이기 설정이면 자동 회전 · 초점 이동 애니메이션을 하지 않는다 (WCAG 2.2.2 — 끄는 단추도 있음)
  const [reduced] = useState(prefersReducedMotion);
  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const viewRef = useRef<View>({ ...DEFAULT_VIEW, center: [...DEFAULT_VIEW.center] as [number, number, number] });
  const targetRef = useRef<{ center: [number, number, number]; zoom: number } | null>(null);
  const sizeRef = useRef({ w: 800, h: 600, dpr: 1 });
  const dirtyRef = useRef(true);
  const hoverRef = useRef(-1);
  const pointerRef = useRef<{ x: number; y: number; down: boolean; moved: number; px: number; py: number }>({ x: 0, y: 0, down: false, moved: 0, px: 0, py: 0 });
  const n = data.nodes.length;
  const scr = useRef({ xs: new Float32Array(n), ys: new Float32Array(n), rs: new Float32Array(n), vis: new Uint8Array(n) });
  const sprites = useRef(new Map<string, HTMLCanvasElement | null>());

  const [selected, setSelected] = useState(-1);
  const [focusCluster, setFocusCluster] = useState<number | null>(null);
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [showLabels, setShowLabels] = useState(true);
  const [autoRotate, setAutoRotate] = useState(() => !prefersReducedMotion());
  const [q, setQ] = useState("");
  const [announce, setAnnounce] = useState("");

  const classColor = useMemo(() => Object.fromEntries(data.classes.map((c) => [c.label, colorOf(c.color)])), [data.classes]);
  const classKo = useMemo(() => Object.fromEntries(data.classes.map((c) => [c.label, c.ko || c.label])), [data.classes]);
  const legend = useMemo(() => data.classes.filter((c) => c.count > 0).sort((a, b) => b.count - a.count), [data.classes]);
  const nb = useMemo(() => buildNeighbors(n, data.links, data.relTypes), [n, data.links, data.relTypes]);
  const clusterOf = useMemo(() => Object.fromEntries(data.clusters.map((c) => [c.id, c])), [data.clusters]);
  const hits = useMemo(() => search(data.nodes, q), [data.nodes, q]);
  const topByDeg = useMemo(() => [...data.nodes.keys()].sort((a, b) => data.nodes[b].deg - data.nodes[a].deg).slice(0, 36), [data.nodes]);

  // 그리기에 쓰는 최신 상태(애니메이션 루프는 다시 만들지 않는다)
  const live = useRef({ selected, focusCluster, hidden, showLabels, autoRotate, mode });
  useEffect(() => {
    live.current = { selected, focusCluster, hidden, showLabels, autoRotate, mode };
    dirtyRef.current = true;
  }, [selected, focusCluster, hidden, showLabels, autoRotate, mode]);

  const posOf = useCallback((i: number): [number, number, number] => {
    const nd = data.nodes[i];
    return live.current.mode === "2d" ? [nd.p2[0], nd.p2[1], 0] : nd.p3;
  }, [data.nodes]);

  const draw = useCallback(() => {
    const cv = canvasRef.current;
    if (!cv) return;
    const ctx = cv.getContext("2d");
    if (!ctx) return;
    const { w, h, dpr } = sizeRef.current;
    const st = live.current;
    const flat = st.mode === "2d";
    const view = viewRef.current;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    drawSpace(ctx, view, w, h, flat);
    const { xs, ys, rs, vis } = scr.current;
    const zs = new Float32Array(n);
    const fs = new Float32Array(n);
    for (let i = 0; i < n; i++) {
      const nd = data.nodes[i];
      vis[i] = st.hidden.has(nd.cls) ? 0 : 1;
      const p = project(posOf(i), view, w, h, flat);
      xs[i] = p.x;
      ys[i] = p.y;
      zs[i] = p.z;
      fs[i] = p.f;
      rs[i] = radiusOf(nd.deg, p.f, view.zoom);
    }
    // 강조: 선택 개체와 이웃 · 초점 군집
    const hl = new Uint8Array(n);
    let anyHl = false;
    if (st.selected >= 0) {
      hl[st.selected] = 1;
      for (const x of nb[st.selected] ?? []) hl[x.index] = 1;
      anyHl = true;
    } else if (st.focusCluster !== null) {
      for (let i = 0; i < n; i++) if (data.nodes[i].c === st.focusCluster) hl[i] = 1;
      anyHl = true;
    }
    // 선
    ctx.lineWidth = 1;
    ctx.strokeStyle = LINK;
    ctx.beginPath();
    const hlLinks: [number, number][] = [];
    for (const [a, b] of data.links) {
      if (!vis[a] || !vis[b]) continue;
      const touch = st.selected >= 0 ? a === st.selected || b === st.selected : st.focusCluster !== null && hl[a] && hl[b];
      if (touch) {
        hlLinks.push([a, b]);
        continue;
      }
      if (anyHl) continue;
      ctx.moveTo(xs[a], ys[a]);
      ctx.lineTo(xs[b], ys[b]);
    }
    ctx.stroke();
    if (anyHl) {
      ctx.globalAlpha = 0.08;
      ctx.beginPath();
      for (const [a, b] of data.links) {
        if (!vis[a] || !vis[b] || (hl[a] && hl[b])) continue;
        ctx.moveTo(xs[a], ys[a]);
        ctx.lineTo(xs[b], ys[b]);
      }
      ctx.strokeStyle = "rgba(148, 163, 184, 1)";
      ctx.stroke();
      ctx.globalAlpha = 1;
    }
    if (hlLinks.length) {
      ctx.strokeStyle = LINK_HL;
      ctx.lineWidth = 1.3;
      ctx.beginPath();
      for (const [a, b] of hlLinks) {
        ctx.moveTo(xs[a], ys[a]);
        ctx.lineTo(xs[b], ys[b]);
      }
      ctx.stroke();
    }
    // 점 — 먼 것부터
    const order = [...Array(n).keys()].filter((i) => vis[i]).sort((a, b) => zs[b] - zs[a]);
    for (const i of order) {
      const nd = data.nodes[i];
      const dim = anyHl && !hl[i];
      const depth = flat ? 1 : Math.min(1, Math.max(0.35, (fs[i] - 0.55) * 1.6));
      ctx.globalAlpha = dim ? 0.14 : 0.5 + 0.5 * depth;
      const color = classColor[nd.cls] ?? "#94a3b8";
      const r = Math.max(1.2, rs[i]);
      let spr = sprites.current.get(color);
      if (spr === undefined) {
        spr = makeSprite(color);
        sprites.current.set(color, spr);
      }
      if (spr && r >= 1.8) {
        const R = r * GLOW;
        ctx.drawImage(spr, xs[i] - R, ys[i] - R, R * 2, R * 2);
      } else {
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.arc(xs[i], ys[i], r, 0, Math.PI * 2);
        ctx.fill();
      }
    }
    ctx.globalAlpha = 1;
    const ring = (i: number, color: string, width: number) => {
      if (i < 0 || !vis[i]) return;
      ctx.strokeStyle = color;
      ctx.lineWidth = width;
      ctx.beginPath();
      ctx.arc(xs[i], ys[i], rs[i] + 3, 0, Math.PI * 2);
      ctx.stroke();
    };
    ring(st.selected, "#ffffff", 2);
    ring(hoverRef.current, "rgba(255,255,255,0.7)", 1.5);
    // 이름 — 겹치면 건너뜀(선택 · 마우스 올린 것은 항상)
    ctx.font = "600 12px Pretendard, 'Noto Sans KR', system-ui, sans-serif";
    ctx.textBaseline = "middle";
    const placed: [number, number, number, number][] = [];
    const label = (text: string, x: number, y: number, force: boolean, color = "#e2e8f0", bold = false) => {
      ctx.font = `${bold ? 700 : 600} ${bold ? 13 : 12}px Pretendard, 'Noto Sans KR', system-ui, sans-serif`;
      const tw = ctx.measureText(text).width;
      const box: [number, number, number, number] = [x, y - 8, x + tw, y + 8];
      if (!force && placed.some((b) => !(box[2] < b[0] || box[0] > b[2] || box[3] < b[1] || box[1] > b[3]))) return;
      placed.push(box);
      ctx.lineWidth = 3.5;
      ctx.strokeStyle = "rgba(11, 18, 32, 0.85)";
      ctx.strokeText(text, x, y);
      ctx.fillStyle = color;
      ctx.fillText(text, x, y);
    };
    if (st.selected >= 0 && vis[st.selected]) label(data.nodes[st.selected].name, xs[st.selected] + rs[st.selected] + 6, ys[st.selected], true, "#ffffff", true);
    const hv = hoverRef.current;
    if (hv >= 0 && vis[hv] && hv !== st.selected) label(`${data.nodes[hv].name} · ${classKo[data.nodes[hv].cls] ?? data.nodes[hv].cls}`, xs[hv] + rs[hv] + 6, ys[hv], true, "#ffffff");
    if (st.selected >= 0) {
      for (const x of (nb[st.selected] ?? []).slice(0, MAX_NEIGHBOR_LABELS)) if (vis[x.index]) label(data.nodes[x.index].name, xs[x.index] + rs[x.index] + 5, ys[x.index], false);
    }
    // 군집 이름 — 보이는 구성원의 화면 중심
    if (!anyHl || st.focusCluster !== null) {
      for (const c of data.clusters) {
        if (c.small || c.size < 6 || (st.focusCluster !== null && c.id !== st.focusCluster)) continue;
        let sx = 0;
        let sy = 0;
        let k = 0;
        let top = Infinity;
        for (let i = 0; i < n; i++) {
          if (data.nodes[i].c !== c.id || !vis[i]) continue;
          sx += xs[i];
          sy += ys[i];
          top = Math.min(top, ys[i]);
          k++;
        }
        if (!k) continue;
        // 군집 이름표 — 주 클래스 색 점 + 대표 개체 이름(주 클래스 이름은 색으로)
        const title = clusterTitle(c.label, classKo[c.main]);
        const text = title.length > 28 ? `${title.slice(0, 27)}…` : title;
        const color = classColor[c.main] ?? "#94a3b8";
        ctx.font = `700 12px ${FONT}`;
        const tw = ctx.measureText(text).width;
        const bw = tw + 30;
        const bh = 22;
        const cx = Math.min(w - bw / 2 - 6, Math.max(bw / 2 + 6, sx / k));
        const cy = Math.max(16, Math.min(top - 18, sy / k - 40));
        const box: [number, number, number, number] = [cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2];
        if (placed.some((b) => !(box[2] < b[0] || box[0] > b[2] || box[3] < b[1] || box[1] > b[3]))) continue;
        placed.push(box);
        roundRect(ctx, box[0], box[1], bw, bh, bh / 2);
        ctx.fillStyle = "rgba(8, 13, 28, 0.8)";
        ctx.fill();
        ctx.lineWidth = 1;
        ctx.strokeStyle = rgba(color, 0.75);
        ctx.stroke();
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.arc(box[0] + 12, cy, 3.5, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = "#f1f5f9";
        ctx.fillText(text, box[0] + 21, cy + 0.5);
      }
    }
    if (st.showLabels && !anyHl) {
      for (const i of topByDeg) if (vis[i]) label(data.nodes[i].name, xs[i] + rs[i] + 5, ys[i], false, "#cbd5e1");
    }
  }, [classColor, classKo, data.clusters, data.links, data.nodes, n, nb, posOf, topByDeg]);

  // 애니메이션 루프 — 바뀐 것이 있을 때만 그린다
  useEffect(() => {
    let raf = 0;
    const tick = () => {
      const v = viewRef.current;
      const st = live.current;
      if (st.autoRotate && st.mode === "3d" && !pointerRef.current.down && st.selected < 0) {
        v.yaw += 0.0022;
        dirtyRef.current = true;
      }
      const tg = targetRef.current;
      if (tg) {
        const k = 0.18;
        v.center = [v.center[0] + (tg.center[0] - v.center[0]) * k, v.center[1] + (tg.center[1] - v.center[1]) * k, v.center[2] + (tg.center[2] - v.center[2]) * k];
        v.zoom += (tg.zoom - v.zoom) * k;
        if (Math.abs(tg.zoom - v.zoom) < 0.005 && Math.hypot(tg.center[0] - v.center[0], tg.center[1] - v.center[1], tg.center[2] - v.center[2]) < 0.002) {
          v.center = [...tg.center] as [number, number, number];
          v.zoom = tg.zoom;
          targetRef.current = null;
        }
        dirtyRef.current = true;
      }
      if (dirtyRef.current) {
        dirtyRef.current = false;
        draw();
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [draw]);

  // 크기 · 장치 픽셀 비율
  useEffect(() => {
    const wrap = wrapRef.current;
    const cv = canvasRef.current;
    if (!wrap || !cv) return;
    const fit = () => {
      const r = wrap.getBoundingClientRect();
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      sizeRef.current = { w: Math.max(200, r.width), h: Math.max(200, r.height), dpr };
      cv.width = Math.round(sizeRef.current.w * dpr);
      cv.height = Math.round(sizeRef.current.h * dpr);
      cv.style.width = `${sizeRef.current.w}px`;
      cv.style.height = `${sizeRef.current.h}px`;
      dirtyRef.current = true;
    };
    fit();
    const ro = new ResizeObserver(fit);
    ro.observe(wrap);
    return () => ro.disconnect();
  }, []);

  // 휠 확대(페이지 스크롤 막기 — passive 아님)
  useEffect(() => {
    const cv = canvasRef.current;
    if (!cv) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const v = viewRef.current;
      v.zoom = Math.min(8, Math.max(0.35, v.zoom * Math.exp(-e.deltaY * 0.0015)));
      targetRef.current = null;
      dirtyRef.current = true;
    };
    cv.addEventListener("wheel", onWheel, { passive: false });
    return () => cv.removeEventListener("wheel", onWheel);
  }, []);

  const focusOn = useCallback((center: [number, number, number], zoom: number) => {
    targetRef.current = { center, zoom };
    if (reduced) {
      viewRef.current.center = center;
      viewRef.current.zoom = zoom;
      targetRef.current = null;
    }
    dirtyRef.current = true;
  }, [reduced]);

  const select = useCallback((i: number, focus = true) => {
    setSelected(i);
    setFocusCluster(null);
    if (i >= 0) {
      setAutoRotate(false);
      const nd = data.nodes[i];
      setAnnounce(`선택: ${nd.name} (${classKo[nd.cls] ?? nd.cls}) — 관계 ${nb[i]?.length ?? 0}개`);
      if (focus) focusOn(posOf(i), Math.max(viewRef.current.zoom, 1.9));
    } else {
      setAnnounce("선택 해제");
    }
  }, [classKo, data.nodes, focusOn, nb, posOf]);

  const reset = () => {
    viewRef.current = { ...DEFAULT_VIEW, center: [0, 0, 0] };
    targetRef.current = null;
    setSelected(-1);
    setFocusCluster(null);
    dirtyRef.current = true;
  };

  const zoomBy = (k: number) => {
    const v = viewRef.current;
    focusOn([...v.center] as [number, number, number], Math.min(8, Math.max(0.35, v.zoom * k)));
  };

  const onPointerDown = (e: React.PointerEvent<HTMLCanvasElement>) => {
    (e.target as HTMLCanvasElement).setPointerCapture?.(e.pointerId);
    pointerRef.current = { ...pointerRef.current, down: true, moved: 0, px: e.clientX, py: e.clientY };
  };
  const onPointerMove = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const rect = (e.target as HTMLCanvasElement).getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    const p = pointerRef.current;
    if (p.down) {
      const dx = e.clientX - p.px;
      const dy = e.clientY - p.py;
      p.px = e.clientX;
      p.py = e.clientY;
      p.moved += Math.abs(dx) + Math.abs(dy);
      const v = viewRef.current;
      if (live.current.mode === "3d") {
        v.yaw += dx * 0.007;
        v.pitch = Math.max(-1.45, Math.min(1.45, v.pitch + dy * 0.007));
      } else {
        v.panX += dx;
        v.panY += dy;
      }
      dirtyRef.current = true;
      return;
    }
    const s = scr.current;
    const hit = pick(s.xs, s.ys, s.rs, s.vis, x, y);
    if (hit !== hoverRef.current) {
      hoverRef.current = hit;
      dirtyRef.current = true;
      (e.target as HTMLCanvasElement).style.cursor = hit >= 0 ? "pointer" : "grab";
    }
  };
  const onPointerUp = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const p = pointerRef.current;
    p.down = false;
    if (p.moved < 5) {
      const rect = (e.target as HTMLCanvasElement).getBoundingClientRect();
      const s = scr.current;
      const hit = pick(s.xs, s.ys, s.rs, s.vis, e.clientX - rect.left, e.clientY - rect.top);
      select(hit, false);
    } else {
      setAutoRotate(false);
    }
  };
  const onKeyDown = (e: React.KeyboardEvent<HTMLCanvasElement>) => {
    const v = viewRef.current;
    const step = 0.12;
    const is3d = live.current.mode === "3d";
    let used = true;
    switch (e.key) {
      case "ArrowLeft":
        if (is3d) v.yaw -= step;
        else v.panX += 30;
        break;
      case "ArrowRight":
        if (is3d) v.yaw += step;
        else v.panX -= 30;
        break;
      case "ArrowUp":
        if (is3d) v.pitch = Math.max(-1.45, v.pitch - step);
        else v.panY += 30;
        break;
      case "ArrowDown":
        if (is3d) v.pitch = Math.min(1.45, v.pitch + step);
        else v.panY -= 30;
        break;
      case "+":
      case "=":
        v.zoom = Math.min(8, v.zoom * 1.2);
        break;
      case "-":
        v.zoom = Math.max(0.35, v.zoom / 1.2);
        break;
      case "Escape":
        select(-1);
        break;
      default:
        used = false;
    }
    if (used) {
      e.preventDefault();
      setAutoRotate(false);
      dirtyRef.current = true;
    }
  };

  const sel = selected >= 0 ? data.nodes[selected] : null;
  const groups = useMemo(() => {
    if (selected < 0) return [];
    const m = new Map<string, number[]>();
    for (const x of nb[selected] ?? []) {
      const k = `${x.dir}:${x.type}`;
      m.set(k, [...(m.get(k) ?? []), x.index]);
    }
    return [...m.entries()].sort((a, b) => b[1].length - a[1].length);
  }, [nb, selected]);

  const summary = `온톨로지 구성 지도(${mode === "3d" ? "3D" : "2D"}) — 개체 ${n.toLocaleString("ko-KR")}개, 관계 ${data.links.length.toLocaleString("ko-KR")}개, 군집 ${data.clusters.length}개. 가장 큰 군집: ${data.clusters.slice(0, 3).map((c) => `${c.label}(${c.size})`).join(", ")}. 같은 내용은 옆 목록과 '표' 보기에 있습니다.`;

  return (
    <div className="grid grid-cols-1 gap-md xl:grid-cols-[minmax(0,1fr)_340px]" data-ontology-map>
      <div className="min-w-0">
        <div className="mb-xs flex flex-wrap items-center gap-xs">
          {mode === "3d" ? (
            <Button size="sm" variant="quiet" aria-pressed={autoRotate} onClick={() => setAutoRotate((v) => !v)}>
              {autoRotate ? "자동 회전 멈춤" : "자동 회전"}
            </Button>
          ) : null}
          <Button size="sm" variant="quiet" aria-pressed={showLabels} onClick={() => setShowLabels((v) => !v)}>
            {showLabels ? "이름 줄이기" : "이름 더 보기"}
          </Button>
          <Button size="sm" variant="quiet" onClick={() => zoomBy(1.25)} aria-label="확대">
            ＋
          </Button>
          <Button size="sm" variant="quiet" onClick={() => zoomBy(0.8)} aria-label="축소">
            －
          </Button>
          <Button size="sm" variant="quiet" onClick={reset}>
            처음 위치
          </Button>
          <span className="ml-auto text-[11.5px] text-steel">
            개체 {n.toLocaleString("ko-KR")} · 관계 {data.links.length.toLocaleString("ko-KR")} · 군집 {data.clusters.length}
          </span>
        </div>
        <div ref={wrapRef} className="relative h-[560px] overflow-hidden rounded-2xl md:h-[640px]" style={{ background: BG }}>
          <canvas
            ref={canvasRef}
            role="img"
            aria-label={summary}
            aria-describedby="onto-map-help"
            tabIndex={0}
            className="block cursor-grab touch-none outline-none focus-visible:ring-2 focus-visible:ring-primary"
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
            onPointerLeave={() => {
              if (hoverRef.current >= 0) {
                hoverRef.current = -1;
                dirtyRef.current = true;
              }
            }}
            onKeyDown={onKeyDown}
            data-map-canvas
          />
          <p id="onto-map-help" className="pointer-events-none absolute bottom-2 left-3 text-[11px]" style={{ color: "rgba(203, 213, 225, 0.85)" }}>
            {mode === "3d" ? "끌어서 회전 · 휠로 확대 · 점을 누르면 상세 · 방향키 · +/− · Esc" : "끌어서 이동 · 휠로 확대 · 점을 누르면 상세 · 방향키 · +/− · Esc"}
          </p>
        </div>
        <p className="sr-only" aria-live="polite">
          {announce}
        </p>
        {/* 범례 — 노드 종류(클래스)를 개체 수 순으로 고른 칸에. 색과 이름을 함께, 누르면 그 종류를 숨김/보임 */}
        <div className="mt-sm rounded-2xl border border-hairline-soft p-sm" role="group" aria-label="노드 종류(클래스) 거르기" data-map-legend>
          <div className="mb-xs flex flex-wrap items-center gap-x-2 gap-y-1">
            <b className="text-[12.5px] text-charcoal">노드 종류 {legend.length}</b>
            <span className="text-[11px] text-stone">
              {hidden.size ? `${legend.length - legend.filter((c) => hidden.has(c.label)).length}종 표시 · ${legend.filter((c) => hidden.has(c.label)).length}종 숨김` : "모두 표시"} · 누르면 숨김/보임
            </span>
            <span className="ml-auto flex gap-1">
              <Button size="sm" variant="quiet" disabled={!hidden.size} onClick={() => setHidden(new Set())}>
                모두 보기
              </Button>
              <Button size="sm" variant="quiet" disabled={hidden.size === legend.length} onClick={() => setHidden(new Set(legend.map((c) => c.label)))}>
                모두 숨기기
              </Button>
            </span>
          </div>
          <ul className="grid grid-cols-2 gap-1 sm:grid-cols-3 lg:grid-cols-4 2xl:grid-cols-5">
            {legend.map((c) => {
              const off = hidden.has(c.label);
              return (
                <li key={c.label}>
                  <button
                    type="button"
                    aria-pressed={!off}
                    onClick={() =>
                      setHidden((s) => {
                        const next = new Set(s);
                        if (next.has(c.label)) next.delete(c.label);
                        else next.add(c.label);
                        return next;
                      })
                    }
                    // 숨긴 종류 — 글자는 흐리지 않고(대비 유지) 줄긋기 · 빈 점 · 회색 바탕으로 구분
                    className={clsx("flex w-full items-center gap-2 rounded-xl px-2 py-1.5 text-left transition-colors hover:bg-surface-soft", off && "bg-surface-soft")}
                    title={c.description || c.label}
                  >
                    <span aria-hidden="true" className="inline-block h-3 w-3 shrink-0 rounded-circle ring-2 ring-white" style={{ background: off ? "transparent" : colorOf(c.color), boxShadow: `0 0 0 1px ${colorOf(c.color)}` }} />
                    <span className="min-w-0 flex-1 leading-tight">
                      <span className={clsx("block truncate text-[12px] font-bold", off ? "text-stone line-through" : "text-charcoal")}>{c.ko}</span>
                      <span className="block truncate font-mono text-[10px] text-stone">{c.label}</span>
                    </span>
                    <span className="tnum shrink-0 text-[12px] font-bold text-steel">{c.count.toLocaleString("ko-KR")}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      </div>

      <aside className="flex min-w-0 flex-col gap-md" aria-label="지도 탐색">
        <div>
          <label htmlFor="onto-map-q" className="mb-1 block text-[12px] font-bold text-charcoal">
            개체 찾기
          </label>
          <input id="onto-map-q" className="input !h-9 w-full text-[13px]" placeholder="이름 · 키 (예: 햇살론, 포용금융)" value={q} onChange={(e) => setQ(e.target.value)} data-map-search />
          {q.trim() ? (
            hits.length ? (
              <ul className="mt-1 flex flex-col divide-y divide-hairline-soft rounded-xl border border-hairline-soft" data-map-hits>
                {hits.map((i) => (
                  <li key={data.nodes[i].id}>
                    <button type="button" className="flex w-full items-center gap-1.5 px-md py-1.5 text-left text-[12.5px] hover:bg-surface-soft" onClick={() => select(i)}>
                      <span aria-hidden="true" className="inline-block h-2 w-2 shrink-0 rounded-circle" style={{ background: classColor[data.nodes[i].cls] }} />
                      <span className="min-w-0 flex-1 truncate font-bold text-ink-deep">{data.nodes[i].name}</span>
                      <span className="shrink-0 text-[11px] text-stone">{classKo[data.nodes[i].cls]}</span>
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-1 text-[12px] text-stone">맞는 개체가 없습니다.</p>
            )
          ) : null}
        </div>

        {sel ? (
          <section className="rounded-2xl border border-hairline-soft p-md" aria-label="선택한 개체" data-map-detail>
            <div className="mb-xs flex items-start justify-between gap-xs">
              <div className="min-w-0">
                <p className="flex flex-wrap items-center gap-1.5">
                  <span aria-hidden="true" className="inline-block h-2.5 w-2.5 rounded-circle" style={{ background: classColor[sel.cls] }} />
                  <Badge>{classKo[sel.cls] ?? sel.cls}</Badge>
                  <span className="font-mono text-[10.5px] text-stone">{sel.cls}</span>
                </p>
                <h3 className="mt-1 break-words text-[15px] font-bold text-ink-deep">{sel.name}</h3>
              </div>
              <Button size="sm" variant="quiet" onClick={() => select(-1)} aria-label="선택 해제">
                닫기
              </Button>
            </div>
            <KeyValueList
              columns={1}
              dense
              items={[
                { label: "군집", value: clusterOf[sel.c]?.label ?? "-" },
                { label: "키", value: <span className="break-all font-mono text-[11px]">{sel.key}</span> },
                { label: "출처", value: <span className="break-all">{kindLabel(sel.kind)}{sel.origin ? ` · ${sel.origin === "ext" ? "외부" : "당행"}` : ""}{sel.src ? ` · ${sel.src}` : ""}</span> },
                { label: "추출 방식", value: byLabel(sel.by) },
                ...(sel.evidence ? [{ label: "근거", value: <span>“{sel.evidence}”{sel.evidenceDoc ? ` — ${sel.evidenceDoc}` : ""}{sel.evidencePage ? ` p.${sel.evidencePage}` : ""}</span> }] : []),
                ...Object.entries(sel.props).map(([k, v]) => ({ label: k, value: <span className="break-all">{Array.isArray(v) ? v.join(", ") : String(v)}</span> })),
              ]}
            />
            <h4 className="mb-1 mt-md text-[12px] font-bold text-charcoal">관계 {nb[selected]?.length ?? 0}개</h4>
            {groups.length ? (
              <div className="flex max-h-[300px] flex-col gap-xs overflow-y-auto pr-1" data-map-neighbors>
                {groups.map(([k, list]) => {
                  const [dir, type] = k.split(":");
                  return (
                    <div key={k}>
                      <p className="text-[11.5px] font-bold text-steel">
                        {dir === "out" ? "→ " : "← "}
                        {relKo(type)} <span className="font-mono font-medium text-stone">{type}</span> · {list.length}
                      </p>
                      <ul className="mt-0.5 flex flex-wrap gap-1">
                        {list.slice(0, 12).map((i) => (
                          <li key={data.nodes[i].id}>
                            <button type="button" onClick={() => select(i)} className="inline-flex max-w-[240px] items-center gap-1 rounded-pill border border-hairline-soft px-2 py-0.5 text-[11.5px] hover:bg-surface-soft">
                              <span aria-hidden="true" className="inline-block h-2 w-2 shrink-0 rounded-circle" style={{ background: classColor[data.nodes[i].cls] }} />
                              <span className="truncate">{data.nodes[i].name}</span>
                            </button>
                          </li>
                        ))}
                        {list.length > 12 ? <li className="text-[11px] text-stone">외 {list.length - 12}개</li> : null}
                      </ul>
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="text-[12px] text-stone">연결된 관계가 없습니다.</p>
            )}
          </section>
        ) : (
          <p className="rounded-2xl bg-surface-soft px-md py-sm text-[12px] leading-relaxed text-steel">점을 누르거나 찾으면 그 개체의 출처 · 근거 · 관계가 여기에 보입니다.</p>
        )}

        <section aria-label="군집" data-map-clusters>
          <div className="mb-1.5 flex items-baseline justify-between gap-xs">
            <h3 className="text-[12.5px] font-bold text-charcoal">군집 {data.clusters.filter((c) => !c.small).length}개</h3>
            <span className="text-[11px] text-stone">서로 많이 엮인 개체 묶음 · 누르면 그 군집으로 이동</span>
          </div>
          <ul className="flex flex-col gap-1.5">
            {data.clusters.map((c) => {
              const on = focusCluster === c.id;
              const comp = Object.entries(c.classes ?? {})
                .filter(([, v]) => v > 0)
                .sort((a, b) => b[1] - a[1]);
              const share = n ? Math.round((c.size / n) * 100) : 0;
              const title = c.small ? c.label : clusterTitle(c.label, classKo[c.main]);
              return (
                <li key={c.id}>
                  <button
                    type="button"
                    aria-pressed={on}
                    onClick={() => {
                      setSelected(-1);
                      setAutoRotate(false);
                      if (on) {
                        setFocusCluster(null);
                        focusOn([0, 0, 0], 1);
                      } else {
                        setFocusCluster(c.id);
                        const ctr = mode === "2d" ? [...(c.center2 ?? [0, 0]), 0] : c.center3 ?? [0, 0, 0];
                        focusOn([ctr[0] ?? 0, ctr[1] ?? 0, ctr[2] ?? 0], 1.7);
                        setAnnounce(`군집 초점: ${c.label} — 개체 ${c.size}개`);
                      }
                    }}
                    className={clsx(
                      "flex w-full flex-col gap-1 rounded-xl border px-md py-2 text-left transition-colors",
                      on ? "border-primary bg-info-faint" : c.small ? "border-dashed border-hairline bg-surface-soft/60 hover:bg-surface-soft" : "border-hairline-soft hover:bg-surface-soft",
                    )}
                  >
                    <span className="flex w-full items-start gap-xs">
                      <span aria-hidden="true" className="mt-[3px] inline-block h-2.5 w-2.5 shrink-0 rounded-circle" style={{ background: c.small ? "#94a3b8" : classColor[c.main] ?? "#94a3b8" }} />
                      <span className={clsx("min-w-0 flex-1 text-[12.5px] font-bold leading-snug [overflow-wrap:anywhere]", c.small ? "text-steel" : "text-ink-deep")}>
                        {title}
                      </span>
                      <span className="shrink-0 text-right leading-tight">
                        <span className="tnum block text-[12.5px] font-bold text-charcoal">{c.size.toLocaleString("ko-KR")}</span>
                        <span className="tnum block text-[10.5px] text-stone">{share}%</span>
                      </span>
                    </span>
                    {comp.length ? (
                      <>
                        {/* 구성 막대 — 클래스 색 비율(같은 내용은 아래 글로) */}
                        <span aria-hidden="true" className="flex h-1.5 w-full overflow-hidden rounded-pill bg-hairline-soft">
                          {comp.map(([cls, v]) => (
                            <span key={cls} style={{ width: `${(v / Math.max(1, c.size)) * 100}%`, background: classColor[cls] ?? "#94a3b8" }} />
                          ))}
                        </span>
                        <span className="text-[11px] leading-snug text-steel">
                          {comp
                            .slice(0, 3)
                            .map(([cls, v]) => `${classKo[cls] ?? cls} ${v}`)
                            .join(" · ")}
                          {comp.length > 3 ? ` 외 ${comp.length - 3}종` : ""}
                        </span>
                      </>
                    ) : null}
                  </button>
                </li>
              );
            })}
          </ul>
        </section>
      </aside>
    </div>
  );
}
