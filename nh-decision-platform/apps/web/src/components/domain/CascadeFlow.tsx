"use client";

import { useMemo, useState, type ReactNode } from "react";
import clsx from "clsx";
import { useGoalState } from "@/components/providers/GoalStateProvider";
import { IconBriefcase, IconBuilding, IconTarget } from "@/components/ui/icons";
import { Badge } from "@/components/ui/primitives";
import type { CascadeNode, Goal, Proposal } from "@/lib/types";

/** 노드 한 칸의 높이와 간격 — 띠(SVG)의 좌표 계산에 같은 값을 쓴다 */
const H = 72;
const GAP = 16;
const PITCH = H + GAP;
const GUTTER = 88;

type FlowState = "confirmed" | "pre" | "dashed";

interface FlowNode {
  id: string;
  col: 0 | 1 | 2;
  y: number;
  title: string;
  sub?: string;
  value?: string;
  tags: { label: string; tone: "neutral" | "info" | "attention" }[];
  state: FlowState;
  latest: boolean;
}
interface Link {
  from: string;
  to: string;
  weight: number;
  state: FlowState;
  latest: boolean;
}

/** `수도권1지역본부 — 기업여신 신규 취급 1.24조원` → 제목 · 설명 · 값 */
function splitBranch(label: string, detail?: string): { title: string; sub?: string; value?: string } {
  const [head, ...rest] = label.split(" — ");
  const tail = rest.join(" — ");
  if (!tail) return { title: label, sub: detail };
  const m = tail.match(/^(.*?)\s*([\d.,]+\s*(?:조원|억원|백만원|%|건))$/);
  return m ? { title: head, sub: m[1] || detail, value: m[2] } : { title: head, sub: tail };
}

const ICON = { 0: IconTarget, 1: IconBriefcase, 2: IconBuilding } as const;

/**
 * 경영목표 → 실행 사업 → 영업점 전파 흐름도 (가이드 7164 · 규칙: 표 대신 흐름으로).
 *  - 띠 굵기 = 전파 규모(아래로 이어진 노드 수), 확정된 흐름은 옅은 보라(primary/200), 확정 전 제안은 회색, 연결 없음은 가는 점선.
 *  - 최근 확정된 목표와 그 아래 경로는 보라 테두리. 숫자는 노드 안에만 두고 띠 위에는 쓰지 않는다.
 *  - 노드에 올리거나 포커스하면 그 경로만 강조하고 나머지는 흐리게 한다.
 */
export function CascadeFlow({ nodes, goals, proposals }: { nodes: CascadeNode[]; goals: Goal[]; proposals: Proposal[] }) {
  const { overrides, proposalActions } = useGoalState();
  const [focus, setFocus] = useState<string | null>(null);

  const { flow, links, height } = useMemo(() => {
    const fn: FlowNode[] = [];
    const ln: Link[] = [];
    let row = 0;

    for (const g of nodes) {
      const orphan = g.id === "plan-unlinked" || g.label.startsWith("연결 경영목표");
      const pre = !orphan && (g.label.startsWith("(제안)") || /확정 전/.test(g.detail ?? ""));
      const goalDef = goals.find((x) => x.id === g.id);
      const prop = proposals.find((p) => p.targetGoalId === g.id);
      const pending = prop ? !proposalActions[prop.id] : false;
      const changed = Boolean(goalDef && overrides[g.id]?.targetValue !== undefined && overrides[g.id]?.targetValue !== goalDef.targetValue);
      const gState: FlowState = orphan ? "dashed" : pre ? "pre" : "confirmed";
      const tags: FlowNode["tags"] = orphan
        ? []
        : pre
          ? [{ label: "확정 전", tone: "neutral" }]
          : [{ label: "확정", tone: "info" }, ...(changed ? [{ label: "최신", tone: "neutral" as const }] : pending ? [{ label: "수정 제안", tone: "attention" as const }] : [])];

      const plans = g.children?.filter((c) => c.kind === "plan") ?? [];
      const startRow = row;
      const planYs: number[] = [];

      if (plans.length === 0) {
        // 아래로 이어진 실행방안이 없는 목표 — 중단된 흐름을 점선 칸으로 보여 준다
        const y = row * PITCH;
        fn.push({ id: `${g.id}#empty-plan`, col: 1, y, title: "연결된 실행방안이 없어요", state: "dashed", tags: [], latest: false });
        ln.push({ from: g.id, to: `${g.id}#empty-plan`, weight: 2, state: "dashed", latest: false });
        row += 1;
      }
      for (const p of plans) {
        const branches = p.children?.filter((c) => c.kind === "branch_target") ?? [];
        const pStart = row;
        const bYs: number[] = [];
        if (branches.length === 0) {
          const y = row * PITCH;
          fn.push({ id: `${p.id}#empty-branch`, col: 2, y, title: "영업점 전파 없음", state: "dashed", tags: [], latest: false });
          ln.push({ from: p.id, to: `${p.id}#empty-branch`, weight: 2, state: "dashed", latest: false });
          row += 1;
        }
        for (const b of branches) {
          const y = row * PITCH;
          bYs.push(y);
          const s = splitBranch(b.label, b.detail);
          fn.push({ id: b.id, col: 2, y, title: s.title, sub: s.sub, value: s.value, state: gState === "pre" ? "pre" : "confirmed", tags: [], latest: changed });
          ln.push({ from: p.id, to: b.id, weight: 8, state: gState === "pre" ? "pre" : "confirmed", latest: changed });
          row += 1;
        }
        const py = bYs.length ? (bYs[0] + bYs[bYs.length - 1]) / 2 : pStart * PITCH;
        planYs.push(py);
        fn.push({
          id: p.id,
          col: 1,
          y: py,
          title: p.label,
          sub: [p.org, p.detail?.split(" · ").slice(1, 2)[0]].filter(Boolean).join(" · ") || p.detail,
          state: gState === "pre" ? "pre" : "confirmed",
          tags: [],
          latest: changed,
        });
        ln.push({ from: g.id, to: p.id, weight: 6 + Math.min(12, Math.max(1, branches.length) * 3), state: gState === "pre" ? "pre" : gState === "dashed" ? "dashed" : "confirmed", latest: changed });
      }
      const gy = planYs.length ? (planYs[0] + planYs[planYs.length - 1]) / 2 : startRow * PITCH;
      // detail 이 이미 "조직 · …" 으로 시작하면 조직을 한 번 더 붙이지 않는다
      const gSub = orphan ? g.detail : g.detail && g.org && g.detail.startsWith(g.org) ? g.detail : [g.org, g.detail].filter(Boolean).join(" · ");
      fn.push({ id: g.id, col: 0, y: gy, title: g.label, sub: gSub, state: gState, tags, latest: changed });
    }
    return { flow: fn, links: ln, height: Math.max(row, 1) * PITCH - GAP };
  }, [nodes, goals, proposals, overrides, proposalActions]);

  // 강조: 포커스한 노드와 그 위(상위) · 아래(하위) 경로
  const related = useMemo(() => {
    if (!focus) return null;
    const set = new Set<string>([focus]);
    // 아래(하위) 경로
    const down = [focus];
    while (down.length) {
      const x = down.pop()!;
      for (const l of links) if (l.from === x && !set.has(l.to)) (set.add(l.to), down.push(l.to));
    }
    // 위(상위) 경로
    const up = [focus];
    while (up.length) {
      const x = up.pop()!;
      for (const l of links) if (l.to === x && !set.has(l.from)) (set.add(l.from), up.push(l.from));
    }
    return set;
  }, [focus, links]);

  const byId = new Map(flow.map((n) => [n.id, n]));
  const dim = (id: string) => (related && !related.has(id) ? "opacity-35" : "");

  const ribbons = (fromCol: 0 | 1) =>
    links
      .filter((l) => byId.get(l.from)?.col === fromCol)
      .map((l) => {
        const a = byId.get(l.from)!;
        const b = byId.get(l.to)!;
        const y1 = a.y + H / 2;
        const y2 = b.y + H / 2;
        const dashed = l.state === "dashed";
        const on = !related || (related.has(l.from) && related.has(l.to));
        return (
          <path
            key={`${l.from}>${l.to}`}
            d={`M0,${y1} C${GUTTER / 2},${y1} ${GUTTER / 2},${y2} ${GUTTER},${y2}`}
            fill="none"
            stroke={dashed ? "var(--chart-axis)" : l.state === "pre" ? "var(--color-hairline-soft)" : "var(--color-primary-soft)"}
            strokeWidth={dashed ? 1.5 : l.weight}
            strokeDasharray={dashed ? "4 4" : undefined}
            opacity={on ? 1 : 0.3}
            strokeLinecap="butt"
          />
        );
      });

  return (
    <div>
      <div className="overflow-x-auto thin-scroll">
        <div className="min-w-[900px]">
          {/* 열 머리글 — 경영목표 → 실행 사업 → 영업점 전파 */}
          <div className="mb-5 grid grid-cols-[minmax(0,1fr)_88px_minmax(0,1fr)_88px_minmax(0,1fr)] items-center">
            {(["경영목표", "실행 사업", "영업점 전파"] as const).map((label, i) => {
              const Icon = ICON[i as 0 | 1 | 2];
              return (
                <div key={label} className={clsx("flex items-center gap-3", i === 0 ? "col-start-1" : i === 1 ? "col-start-3" : "col-start-5")}>
                  <span className="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-pill bg-info-soft px-3.5 text-[14px] font-bold text-ink-deep">
                    <Icon size={15} className="text-primary" />
                    {label}
                  </span>
                  {i < 2 ? <span aria-hidden="true" className="relative h-px flex-1 bg-info-line-soft after:absolute after:-right-px after:-top-[3px] after:h-[7px] after:w-[7px] after:rotate-45 after:border-r after:border-t after:border-info-line" /> : null}
                </div>
              );
            })}
          </div>

          <div className="grid grid-cols-[minmax(0,1fr)_88px_minmax(0,1fr)_88px_minmax(0,1fr)]" style={{ height }}>
            {([0, 1, 2] as const).map((col) => (
              <div key={col} className="relative" style={{ gridColumn: col * 2 + 1 }}>
                {flow
                  .filter((n) => n.col === col)
                  .map((n) => (
                    <FlowBox key={n.id} node={n} icon={ICON[col]} className={dim(n.id)} onFocus={() => setFocus(n.id)} onBlur={() => setFocus(null)} />
                  ))}
              </div>
            ))}
            {[0, 1].map((c) => (
              <svg key={c} aria-hidden="true" width={GUTTER} height={height} viewBox={`0 0 ${GUTTER} ${height}`} className="pointer-events-none block" style={{ gridColumn: c * 2 + 2, gridRow: 1 }}>
                {ribbons(c as 0 | 1)}
              </svg>
            ))}
          </div>
        </div>
      </div>

      <ul className="mt-6 flex flex-wrap items-center gap-x-5 gap-y-1.5 text-[12px] text-steel">
        <li className="inline-flex items-center gap-1.5">
          <span aria-hidden="true" className="h-1.5 w-6 rounded-sm bg-primary-soft" />
          확정된 전파 흐름
        </li>
        <li className="inline-flex items-center gap-1.5">
          <span aria-hidden="true" className="h-1.5 w-6 rounded-sm bg-hairline-soft" />
          확정 전 제안
        </li>
        <li className="inline-flex items-center gap-1.5">
          <span aria-hidden="true" className="w-6 border-t border-dashed border-icon" />
          연결 없음 · 중단
        </li>
        <li className="font-bold text-ink-deep">띠 굵기 = 전파 규모 · 최근 확정 순</li>
      </ul>
    </div>
  );
}

function FlowBox({ node, icon: Icon, className, onFocus, onBlur }: { node: FlowNode; icon: (p: { className?: string; size?: number }) => ReactNode; className?: string; onFocus: () => void; onBlur: () => void }) {
  const dashed = node.state === "dashed";
  return (
    <div
      tabIndex={dashed ? -1 : 0}
      onMouseEnter={dashed ? undefined : onFocus}
      onMouseLeave={dashed ? undefined : onBlur}
      onFocus={dashed ? undefined : onFocus}
      onBlur={dashed ? undefined : onBlur}
      className={clsx(
        "absolute inset-x-0 flex items-center gap-3 rounded-lg border px-3.5 transition-opacity",
        dashed ? "border-dashed border-hairline bg-transparent" : node.latest ? "border-primary bg-canvas shadow-[0_0_0_1px_var(--color-primary)]" : "border-hairline-soft bg-canvas",
        className,
      )}
      style={{ top: node.y, height: H }}
      data-flow-node={node.id}
    >
      <span className={clsx("flex h-8 w-8 shrink-0 items-center justify-center rounded-md", dashed ? "bg-track text-icon" : node.state === "pre" ? "bg-track text-steel" : "bg-info-soft text-primary")}>
        <Icon size={16} />
      </span>
<span className="min-w-0 flex-1">
        <span className={clsx("block text-[14px] leading-[1.35]", node.col === 0 ? "line-clamp-2" : "truncate", dashed ? "font-medium text-steel" : "font-bold text-ink-deep")} title={node.title}>
          {node.title}
        </span>
        {node.sub ? (
          <span className="block truncate text-[12px] leading-[1.4] text-steel" title={node.sub}>
            {node.sub}
          </span>
        ) : null}
      </span>
      {node.value ? <span className="tnum shrink-0 text-[14px] font-bold text-ink-deep">{node.value}</span> : null}
      {node.tags.length ? (
        <span className="flex shrink-0 flex-col items-end gap-1 xl:flex-row">
          {node.tags.map((t) => (
            <Badge key={t.label} tone={t.tone} className="!px-2 !py-[1px] !text-[12px]">
              {t.label}
            </Badge>
          ))}
        </span>
      ) : null}
    </div>
  );
}
