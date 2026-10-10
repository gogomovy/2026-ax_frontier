import clsx from "clsx";
import type { CascadeNode } from "@/lib/types";

const KIND = {
  goal: { label: "경영목표", dot: "bg-primary" },
  plan: { label: "수행방안·진행사업", dot: "bg-attention" },
  branch_target: { label: "영업점", dot: "bg-success" },
} as const;

/**
 * 경영목표 → 수행방안 → 영업점 전파 트리 (요구사항 PROP-03).
 * 목표 단위 카드 안에 하위 노드를 들여쓰기 목록으로 둔다.
 */
export function CascadeTree({ nodes }: { nodes: CascadeNode[] }) {
  return (
    <>
      <div className="mb-md flex flex-wrap items-center gap-x-lg gap-y-1 text-[11.5px] text-steel">
        {Object.values(KIND).map((k) => (
          <span key={k.label} className="inline-flex items-center gap-1.5">
            <span className={clsx("h-2 w-2 rounded-circle", k.dot)} aria-hidden="true" />
            {k.label}
          </span>
        ))}
      </div>
      <ul className="flex flex-col gap-md">
        {nodes.map((node) => (
          <li key={node.id} className="rounded-2xl border border-hairline-soft px-lg py-base">
            <NodeLine node={node} />
            {node.children?.length ? (
              <ul className="mt-2.5 flex flex-col gap-2 border-l border-hairline-soft pl-lg">
                {node.children.map((child) => (
                  <li key={child.id}>
                    <NodeLine node={child} />
                    {child.children?.length ? (
                      <ul className="mt-2 flex flex-col gap-2 border-l border-hairline-soft pl-lg">
                        {child.children.map((leaf) => (
                          <li key={leaf.id}>
                            <NodeLine node={leaf} />
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-2 text-[12px] text-stone">연결된 하위 수행방안이 없습니다.</p>
            )}
          </li>
        ))}
      </ul>
    </>
  );
}

function NodeLine({ node }: { node: CascadeNode }) {
  const kind = KIND[node.kind];
  return (
    <div className="flex items-start gap-2.5">
      <span className={clsx("mt-[7px] h-2 w-2 shrink-0 rounded-circle", kind.dot)} aria-label={kind.label} />
      <div className="min-w-0">
        <p className={clsx("leading-snug text-ink-deep", node.kind === "goal" ? "text-[14px] font-bold" : "text-[13px] font-medium")}>
          {node.label}
        </p>
        <p className="mt-0.5 text-[11.5px] text-stone">
          {node.detail && node.org && node.detail.startsWith(node.org)
            ? node.detail
            : [node.org, node.detail].filter(Boolean).join(" · ")}
        </p>
      </div>
    </div>
  );
}
