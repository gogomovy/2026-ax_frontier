"use client";

import { useMemo, type ReactNode } from "react";
import clsx from "clsx";
import { useGoalState } from "@/components/providers/GoalStateProvider";
import { IconBriefcase, IconBuilding, IconTarget } from "@/components/ui/icons";
import { Badge } from "@/components/ui/primitives";
import type { CascadeNode, Goal, Proposal } from "@/lib/types";

/** 노드 한 칸의 높이와 간격 — 띠(SVG)의 좌표 계산에 같은 값을 쓴다 */
const H = 52;
/** 왼쪽 두 열 줄 간격 (시안 201:2 — 52 + 32) */
const GAP = 32;
const PITCH = H + GAP;
/** 영업점 칸 사이 최소 간격 */
const BGAP = 17;
const GUTTER = 147;

type FlowState = "confirmed" | "pre" | "dashed";

interface FlowNode {
  id: string;
  col: 0 | 1 | 2;
  y: number;
  /** 칸 높이 — 영업점 칸은 배분 줄 수만큼 커진다 */
  h: number;
  /** 영업점 칸의 배분 줄 (설명 · 값) */
  lines?: { label?: string; value?: string }[];
  title: string;
  sub?: string;
  value?: string;
  tags: { label: string; tone: "neutral" | "info" | "attention" }[];
  state: FlowState;
  latest: boolean;
  /** 지금 보는 부서(highlightOrg)가 맡은 실행 사업 */
  own?: boolean;
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
 *  - highlightOrg: 사업부서 수행방안에서 그 부서가 맡은 실행 사업에 '우리 부서' 표시 (Phase K 후속 · SCP-04)
 *  - ownBorder: 우리 부서 실행 사업을 보라 테두리로 표시 · drawIn: 띠를 그리며 나타낸다 (사업부서 수행방안 시안 345:98 · 기본 꺼짐)
 */
export function CascadeFlow({
  nodes,
  goals,
  proposals,
  highlightOrg,
  ownBorder = false,
  drawIn = false,
}: {
  nodes: CascadeNode[];
  goals: Goal[];
  proposals: Proposal[];
  highlightOrg?: string | null;
  ownBorder?: boolean;
  drawIn?: boolean;
}) {
  const { overrides, proposalActions } = useGoalState();

  const { flow, links, height } = useMemo(() => {
    const fn: FlowNode[] = [];
    const ln: Link[] = [];
    // 왼쪽 두 열(경영목표 · 실행 사업)은 한 줄씩 같은 높이로 쌓는다 (시안 201:2 · 줄 간격 84)
    let row = 0;
    // 영업점은 본부(제목) 기준으로 합친다 — 여러 실행 사업이 한 본부로 모이면 띠도 한 칸으로 모인다
    type Bucket = { id: string; title: string; lines: { label?: string; value?: string }[]; srcs: { from: string; state: FlowState; latest: boolean }[]; sub?: string };
    const buckets: Bucket[] = [];
    const bucketOf = (key: string, title: string, sub?: string) => {
      let b = buckets.find((x) => x.id === key);
      if (!b) {
        b = { id: key, title, lines: [], srcs: [], sub };
        buckets.push(b);
      }
      return b;
    };

    for (const g of nodes) {
      const orphan = g.id === "plan-unlinked" || g.label.startsWith("연결 경영목표");
      const pre = !orphan && (g.label.startsWith("(제안)") || /확정 전/.test(g.detail ?? ""));
      const goalDef = goals.find((x) => x.id === g.id);
      const prop = proposals.find((p) => p.targetGoalId === g.id);
      const pending = prop ? !proposalActions[prop.id] : false;
      const changed =
        Boolean(g.changed) ||
        Boolean(goalDef && overrides[g.id]?.targetValue !== undefined && overrides[g.id]?.targetValue !== goalDef.targetValue);
      const gState: FlowState = orphan ? "dashed" : pre ? "pre" : "confirmed";
      const tags: FlowNode["tags"] = orphan
        ? []
        : pre
          ? [{ label: "확정 전", tone: "neutral" }]
          : [{ label: "✓ 확정", tone: "info" }, ...(changed ? [{ label: "최신", tone: "info" as const }] : pending ? [{ label: "수정 제안", tone: "neutral" as const }] : [])];

      const plans = g.children?.filter((c) => c.kind === "plan") ?? [];
      const gy = row * PITCH;
      const pState: FlowState = gState === "pre" ? "pre" : gState === "dashed" ? "dashed" : "confirmed";

      if (plans.length === 0) {
        fn.push({ id: `${g.id}#empty-plan`, col: 1, y: row * PITCH, h: H, title: "연결된 실행방안이 없어요", state: "dashed", tags: [], latest: false });
        ln.push({ from: g.id, to: `${g.id}#empty-plan`, weight: 2, state: "dashed", latest: false });
        row += 1;
      }
      for (const p of plans) {
        const branches = p.children?.filter((c) => c.kind === "branch_target") ?? [];
        fn.push({
          id: p.id,
          col: 1,
          y: row * PITCH,
          h: H,
          title: p.label,
          sub: [p.org, p.detail?.split(" · ").slice(1, 2)[0]].filter(Boolean).join(" · ") || p.detail,
          state: pState,
          tags: highlightOrg && p.org === highlightOrg ? [{ label: "우리 부서", tone: "info" }] : [],
          latest: changed,
          own: Boolean(highlightOrg && p.org === highlightOrg),
        });
        ln.push({ from: g.id, to: p.id, weight: pState === "dashed" ? 2 : 6 + Math.min(12, Math.max(1, branches.length) * 4), state: pState, latest: changed });
        row += 1;
        if (branches.length === 0) {
          const b = bucketOf(`${p.id}#empty-branch`, orphan ? "영업점 참고 중단" : "영업점 전파 없음");
          b.srcs.push({ from: p.id, state: "dashed", latest: false });
        }
        for (const br of branches) {
          const s = splitBranch(br.label, br.detail);
          const b = bucketOf(`branch:${s.title}`, s.title);
          if (s.sub || s.value) b.lines.push({ label: s.sub, value: s.value });
          b.srcs.push({ from: p.id, state: orphan ? "dashed" : gState === "pre" ? "pre" : "confirmed", latest: changed });
        }
      }
      const gSub = orphan ? g.detail : g.detail && g.org && g.detail.startsWith(g.org) ? g.detail : [g.org, g.detail].filter(Boolean).join(" · ");
      // 흐름도 칸은 좁아 '전년 대비'를 줄여 쓴다(시안: 기업여신 +7.8% 이상 확대)
      fn.push({ id: g.id, col: 0, y: gy, h: H, title: g.label.replace(/\s*전년 대비\s*/, " "), sub: gSub, state: gState, tags, latest: changed });
    }

    // 영업점 칸 — 이어진 실행 사업들의 가운데 높이에 두되, 앞 칸과 겹치지 않게 아래로 민다(간격 17)
    const yOf = new Map(fn.map((n) => [n.id, n.y]));
    const placed = buckets
      .map((b, i) => {
        const n = b.lines.length;
        const h = n === 0 ? 44 : 10 + 18 + 6 + n * 16 + (n - 1) * 5 + 10;
        const centers = b.srcs.map((s) => (yOf.get(s.from) ?? 0) + H / 2);
        const target = centers.reduce((a, c) => a + c, 0) / Math.max(1, centers.length) - h / 2;
        return { b, h, target, i };
      })
      .sort((a, c) => a.target - c.target || a.i - c.i);
    let bottom = -BGAP;
    for (const { b, h, target } of placed) {
      const y = Math.max(0, target, bottom + BGAP);
      bottom = y + h;
      const allDashed = b.srcs.every((s) => s.state === "dashed");
      const allPre = b.srcs.every((s) => s.state === "pre");
      const latest = b.srcs.some((s) => s.latest);
      fn.push({
        id: b.id,
        col: 2,
        y,
        h,
        title: b.title,
        sub: b.sub,
        lines: b.lines,
        state: allDashed ? "dashed" : allPre ? "pre" : "confirmed",
        tags: latest ? [{ label: "AI 보완 완료", tone: "info" }] : [],
        latest,
      });
      for (const s of b.srcs) ln.push({ from: s.from, to: b.id, weight: s.state === "dashed" ? 2 : 8, state: s.state, latest: s.latest });
    }
    return { flow: fn, links: ln, height: Math.max(H, row * PITCH - GAP, bottom) };
  }, [nodes, goals, proposals, overrides, proposalActions, highlightOrg]);


  const byId = new Map(flow.map((n) => [n.id, n]));

  // 한 칸으로 여러 띠가 모이거나 한 칸에서 여러 띠가 나갈 때, 띠 끝을 굵기만큼 나란히 쌓는다
  const w = (l: Link) => (l.state === "dashed" ? 2 : l.weight);
  const endY = (l: Link, side: "from" | "to") => {
    const id = side === "from" ? l.from : l.to;
    const node = byId.get(id)!;
    const group = links
      .filter((x) => (side === "from" ? x.from : x.to) === id)
      .sort((p, q) => (byId.get(side === "from" ? p.to : p.from)?.y ?? 0) - (byId.get(side === "from" ? q.to : q.from)?.y ?? 0));
    const total = group.reduce((acc, x) => acc + w(x), 0);
    let acc = 0;
    for (const x of group) {
      if (x === l) return node.y + node.h / 2 - total / 2 + acc + w(x) / 2;
      acc += w(x);
    }
    return node.y + node.h / 2;
  };

  const ribbons = (fromCol: 0 | 1) =>
    links
      .filter((l) => byId.get(l.from)?.col === fromCol)
      .map((l) => {
        const y1 = endY(l, "from");
        const y2 = endY(l, "to");
        const dashed = l.state === "dashed";
        return (
          <path
            key={`${l.from}>${l.to}`}
            d={`M0,${y1} C${GUTTER / 2},${y1} ${GUTTER / 2},${y2} ${GUTTER},${y2}`}
            fill="none"
            stroke={dashed ? "var(--color-hairline-soft)" : l.state === "pre" ? "var(--color-hairline-soft)" : "var(--color-primary)"}
            strokeOpacity={dashed || l.state === "pre" ? 1 : 0.42}
            strokeWidth={w(l)}
            strokeDasharray={dashed ? "4 4" : drawIn ? "100 100" : undefined}
            pathLength={!dashed && drawIn ? 100 : undefined}
            className={!dashed && drawIn ? "motion-safe:animate-draw" : undefined}
            strokeLinecap="butt"
          />
        );
      });

  return (
    <div>
      <div className="overflow-x-auto thin-scroll">
        <div className="min-w-[900px]">
          {/* 열 머리글 — 경영목표 → 실행 사업 → 영업점 전파 */}
          <div className="mb-[22px] grid grid-cols-[minmax(0,1fr)_147px_minmax(0,1fr)_147px_minmax(0,1fr)] items-center">
            {(["경영목표", "실행 사업", "영업점 전파"] as const).map((label, i) => {
              const Icon = ICON[i as 0 | 1 | 2];
              return (
                <div key={label} className={clsx("flex items-center gap-2.5", i === 0 ? "col-span-2 col-start-1 pr-2.5" : i === 1 ? "col-span-2 col-start-3 pr-2.5" : "col-start-5")}>
                  <span className="inline-flex h-[30px] shrink-0 items-center gap-1.5 rounded-pill bg-surface-soft pl-[3px] pr-[11px] text-[13px] font-bold text-ink-deep">
                    <span className="flex h-6 w-6 items-center justify-center rounded-circle bg-primary text-white">
                      <Icon size={13} />
                    </span>
                    {label}
                  </span>
                  {i < 2 ? <span aria-hidden="true" className="relative h-[2px] flex-1 bg-info-line-soft after:absolute after:-right-px after:-top-[3px] after:h-[7px] after:w-[7px] after:rotate-45 after:border-r after:border-t after:border-info-line" /> : null}
                </div>
              );
            })}
          </div>

          <div className="grid grid-cols-[minmax(0,1fr)_147px_minmax(0,1fr)_147px_minmax(0,1fr)]" style={{ height }}>
            {([0, 1, 2] as const).map((col) => (
              <div key={col} className="relative" style={{ gridColumn: col * 2 + 1 }}>
                {flow
                  .filter((n) => n.col === col)
                  .map((n) => (
                    <FlowBox key={n.id} node={n} icon={ICON[col]} ownBorder={ownBorder} />
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

      <ul className="mt-3.5 flex flex-wrap items-center gap-x-[18px] gap-y-1.5 pb-1.5 text-[11px] text-steel">
        <li className="inline-flex items-center gap-1.5">
          <span aria-hidden="true" className="h-1.5 w-[18px] rounded-[1.5px] bg-primary opacity-[0.42]" />
          확정된 전파 흐름
        </li>
        <li className="inline-flex items-center gap-1.5">
          <span aria-hidden="true" className="h-1.5 w-[18px] rounded-[1.5px] bg-hairline-soft" />
          확정 전 제안
        </li>
        <li className="inline-flex items-center gap-1.5">
          <span aria-hidden="true" className="w-[18px] border-t border-dashed border-icon" />
          연결 없음 · 중단
        </li>
        <li className="font-bold text-steel">띠 굵기 = 전파 규모 · 최근 확정 순</li>
      </ul>
    </div>
  );
}

function FlowBox({ node, icon: Icon, ownBorder = false }: { node: FlowNode; icon: (p: { className?: string; size?: number }) => ReactNode; ownBorder?: boolean }) {
  const dashed = node.state === "dashed";
  const lines = node.lines ?? [];
  const tagEls = node.tags.length ? (
    <span className="flex shrink-0 items-center gap-[7px]">
      {node.tags.map((t) => (
        <Badge key={t.label} tone={t.tone} className="!h-4 !px-1.5 !py-0 !text-[10px] !leading-[14px]">
          {t.label}
        </Badge>
      ))}
    </span>
  ) : null;
  return (
    <div
      className={clsx(
        "absolute inset-x-0 flex gap-2 rounded-[7px] border pl-[9px] pr-[11px]",
        node.col === 2 && lines.length ? "items-start py-[10px]" : "items-center",
        dashed
          ? "border-dashed border-hairline-soft bg-canvas opacity-70"
          : ownBorder && node.own
            ? "border-[1.5px] border-primary bg-info-faint"
            : node.latest
              ? "border-primary bg-canvas shadow-[0_0_0_0.5px_var(--color-primary)]"
              : "border-hairline-soft bg-canvas",
      )}
      style={{ top: node.y, height: node.h }}
      data-flow-node={node.id}
    >
      <span className={clsx("flex h-[26px] w-[26px] shrink-0 items-center justify-center rounded-md", dashed || node.state === "pre" ? "bg-track text-steel" : "bg-info-soft text-primary")}>
        <Icon size={13} />
      </span>
      {node.col === 2 && lines.length ? (
        <span className="flex min-w-0 flex-1 flex-col">
          <span className="flex items-center gap-[5px]">
            <span className="min-w-0 flex-1 truncate text-[13px] font-bold leading-[18px] text-ink-deep">
              {node.title}
            </span>
            {tagEls}
          </span>
          {lines.map((ln, i) => (
            <span key={i} className={clsx("flex h-4 items-center gap-[5px]", i === 0 ? "mt-1.5" : "mt-[5px]")}>
              <span className="min-w-0 flex-1 truncate text-[11px] leading-4 text-steel">
                {ln.label}
              </span>
              {ln.value ? <span className="tnum shrink-0 text-[12px] font-bold text-ink-deep">{ln.value}</span> : null}
            </span>
          ))}
        </span>
      ) : (
        <>
          <span className="min-w-0 flex-1">
            <span className={clsx("block truncate text-[13px] font-bold leading-[18px]", dashed ? "text-steel" : "text-ink-deep")}>
              {node.title}
            </span>
            {node.sub ? (
              <span className="mt-px block truncate text-[11px] leading-4 text-steel">
                {node.sub}
              </span>
            ) : null}
          </span>
          {node.value ? <span className="tnum shrink-0 text-[12px] font-bold text-ink-deep">{node.value}</span> : null}
          {tagEls}
        </>
      )}
    </div>
  );
}
