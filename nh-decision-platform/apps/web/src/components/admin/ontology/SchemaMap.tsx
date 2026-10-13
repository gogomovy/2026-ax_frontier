"use client";

import { useMemo, useState } from "react";
import { colorOf, relKo, type OntologyMapData } from "./mapMath";

/**
 * 온톨로지 구조도 (Phase G · OV-04 · 설계 §23.5) — 클래스(원 크기 = 개체 수)와 관계 유형(화살표 굵기 = 관계 수).
 * 같은 두 클래스 사이 유형이 여럿이면 휘어 겹치지 않게 그린다. 같은 내용은 '표' 보기의 관계 유형 표에 있다.
 */
const W = 1000;
const H = 660;
const CX = W / 2;
const CY = H / 2 + 22; // 위쪽 자기 관계 고리 · 이름이 잘리지 않게
const R = 245;

export function SchemaMap({ data }: { data: OntologyMapData }) {
  const [hover, setHover] = useState<string | null>(null);
  // 원 위 순서 — 많이 엮인 클래스끼리 이웃하게(탐욕 사슬) 놓아 선이 덜 엇갈리게
  const classes = useMemo(() => {
    const list = data.classes.filter((c) => c.total > 0);
    const w = new Map<string, number>();
    const key = (a: string, b: string) => (a < b ? `${a}|${b}` : `${b}|${a}`);
    const deg = new Map<string, number>();
    for (const s of data.schema) {
      if (s.from === s.to) continue;
      w.set(key(s.from, s.to), (w.get(key(s.from, s.to)) ?? 0) + Math.log1p(s.count));
      deg.set(s.from, (deg.get(s.from) ?? 0) + s.count);
      deg.set(s.to, (deg.get(s.to) ?? 0) + s.count);
    }
    if (!list.length) return list;
    const rest = [...list].sort((a, b) => (deg.get(b.label) ?? 0) - (deg.get(a.label) ?? 0) || a.label.localeCompare(b.label));
    const out = [rest.shift()!];
    while (rest.length) {
      const last = out[out.length - 1].label;
      let bi = 0;
      let bw = -1;
      rest.forEach((c, i) => {
        const v = w.get(key(last, c.label)) ?? 0;
        if (v > bw) {
          bw = v;
          bi = i;
        }
      });
      out.push(rest.splice(bi, 1)[0]);
    }
    return out;
  }, [data.classes, data.schema]);
  // 선 이름은 많은 것만 늘 보이고, 나머지는 클래스에 마우스를 올렸을 때
  const labelled = useMemo(() => new Set([...data.schema].sort((a, b) => b.count - a.count).slice(0, 10).map((s) => `${s.from}-${s.type}-${s.to}`)), [data.schema]);
  const pos = useMemo(() => {
    const out: Record<string, { x: number; y: number; r: number; color: string; ko: string; total: number }> = {};
    const max = Math.max(1, ...classes.map((c) => c.total));
    classes.forEach((c, i) => {
      const a = -Math.PI / 2 + (i * 2 * Math.PI) / Math.max(1, classes.length);
      out[c.label] = { x: CX + R * Math.cos(a), y: CY + R * Math.sin(a), r: 14 + 24 * Math.sqrt(c.total / max), color: colorOf(c.color), ko: c.ko, total: c.total };
    });
    return out;
  }, [classes]);
  const edges = useMemo(() => {
    const maxCount = Math.max(1, ...data.schema.map((s) => s.count));
    const seen: Record<string, number> = {};
    return data.schema
      .filter((s) => pos[s.from] && pos[s.to])
      .map((s) => {
        const pair = [s.from, s.to].sort().join("|");
        const k = (seen[pair] = (seen[pair] ?? -1) + 1);
        const a = pos[s.from];
        const b = pos[s.to];
        const width = 1 + 3.2 * (Math.log1p(s.count) / Math.log1p(maxCount));
        if (s.from === s.to) {
          // 자기 관계(예: 지표 → 지표 파생) — 바깥쪽 고리
          const ang = Math.atan2(a.y - CY, a.x - CX);
          const ox = Math.cos(ang);
          const oy = Math.sin(ang);
          const d = a.r + 26 + k * 14;
          const p1 = { x: a.x + Math.cos(ang - 0.5) * a.r, y: a.y + Math.sin(ang - 0.5) * a.r };
          const p2 = { x: a.x + Math.cos(ang + 0.5) * a.r, y: a.y + Math.sin(ang + 0.5) * a.r };
          const px = -oy;
          const py = ox;
          const c1 = { x: a.x + ox * d + px * 30, y: a.y + oy * d + py * 30 };
          const c2 = { x: a.x + ox * d - px * 30, y: a.y + oy * d - py * 30 };
          return { ...s, key: `${s.from}-${s.type}-${s.to}`, d: `M${p1.x},${p1.y} C${c1.x},${c1.y} ${c2.x},${c2.y} ${p2.x},${p2.y}`, lx: a.x + ox * (d + 6), ly: a.y + oy * (d + 6), width, color: a.color };
        }
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const len = Math.hypot(dx, dy) || 1;
        const nx = -dy / len;
        const ny = dx / len;
        // 같은 쌍 안에서 번갈아 양쪽으로, 방향(시작 → 끝)마다 다른 쪽
        const sign = (k % 2 === 0 ? 1 : -1) * (s.from < s.to ? 1 : -1);
        const off = (18 + Math.floor(k / 2) * 26) * sign;
        const mx = (a.x + b.x) / 2 + nx * off;
        const my = (a.y + b.y) / 2 + ny * off;
        // 원 둘레에서 시작 · 끝
        const sa = Math.atan2(my - a.y, mx - a.x);
        const sb = Math.atan2(my - b.y, mx - b.x);
        const x1 = a.x + Math.cos(sa) * a.r;
        const y1 = a.y + Math.sin(sa) * a.r;
        const x2 = b.x + Math.cos(sb) * (b.r + 6);
        const y2 = b.y + Math.sin(sb) * (b.r + 6);
        return { ...s, key: `${s.from}-${s.type}-${s.to}`, d: `M${x1},${y1} Q${mx},${my} ${x2},${y2}`, lx: (x1 + 2 * mx + x2) / 4, ly: (y1 + 2 * my + y2) / 4, width, color: a.color };
      });
  }, [data.schema, pos]);

  const title = `온톨로지 구조도 — 클래스 ${classes.length}개, 관계 유형 ${data.relTypes.length}개. ${data.schema
    .slice(0, 6)
    .map((s) => `${pos[s.from]?.ko ?? s.from} → ${relKo(s.type)} → ${pos[s.to]?.ko ?? s.to} ${s.count}개`)
    .join(", ")}`;

  return (
    <figure className="m-0" data-schema-map>
      <div className="overflow-hidden rounded-2xl" style={{ background: "#0b1220" }}>
        <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-labelledby="schema-map-title" className="block h-auto w-full">
          <title id="schema-map-title">{title}</title>
          <defs>
            <marker id="schema-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="9" markerHeight="9" markerUnits="userSpaceOnUse" orient="auto-start-reverse">
              <path d="M0,0 L10,5 L0,10 z" fill="rgba(226,232,240,0.8)" />
            </marker>
          </defs>
          {edges.map((e) => {
            const dim = hover && hover !== e.from && hover !== e.to;
            const showLabel = hover ? !dim : labelled.has(e.key);
            return (
              <g key={e.key} opacity={dim ? 0.1 : 1}>
                <path d={e.d} fill="none" stroke={e.color} strokeOpacity={hover && !dim ? 0.9 : 0.5} strokeWidth={e.width} markerEnd="url(#schema-arrow)" />
                {showLabel ? (
                  <text x={e.lx} y={e.ly} textAnchor="middle" fontSize="11" fontWeight="600" fill="#e2e8f0" stroke="#0b1220" strokeWidth="3" paintOrder="stroke">
                    {relKo(e.type)} {e.count.toLocaleString("ko-KR")}
                  </text>
                ) : null}
              </g>
            );
          })}
          {classes.map((c) => {
            const p = pos[c.label];
            const dim = hover && hover !== c.label && !edges.some((e) => (e.from === hover && e.to === c.label) || (e.to === hover && e.from === c.label));
            return (
              <g key={c.label} opacity={dim ? 0.25 : 1} onMouseEnter={() => setHover(c.label)} onMouseLeave={() => setHover(null)} style={{ cursor: "default" }}>
                <circle cx={p.x} cy={p.y} r={p.r} fill={p.color} fillOpacity={0.9} stroke="#0b1220" strokeWidth={2} />
                <text x={p.x} y={p.y + p.r + 15} textAnchor="middle" fontSize="13" fontWeight="700" fill="#f8fafc" stroke="#0b1220" strokeWidth="3" paintOrder="stroke">
                  {c.ko}
                </text>
                <text x={p.x} y={p.y + p.r + 29} textAnchor="middle" fontSize="10.5" fill="#94a3b8" stroke="#0b1220" strokeWidth="3" paintOrder="stroke">
                  {c.label} · {c.total.toLocaleString("ko-KR")}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
      <figcaption className="mt-xs text-[11.5px] text-steel">원 크기 = 개체 수, 화살표 굵기 = 관계 수(많은 10가지는 이름 표시). 클래스에 마우스를 올리면 그 클래스의 관계만 밝게 · 이름과 함께 보입니다. 같은 내용은 &apos;표&apos; 보기에 있습니다.</figcaption>
    </figure>
  );
}
